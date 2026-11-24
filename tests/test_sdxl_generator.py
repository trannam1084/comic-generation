import fnmatch
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.configuration import PipelineConfig
from src.factory import build_pipeline
from src.image_generator import sdxl_generator
from src.image_generator.image_generator import BaseImageGenerator
from src.image_generator.schemas import ScenePrompt
from src.image_generator.sdxl_generator import (
    ALLOW_PATTERNS,
    DEFAULT_REPO_ID,
    DEFAULT_REVISION,
    ImageGenerationError,
    SDXLConfig,
    SDXLImageGenerator,
)

ROOT = Path(__file__).resolve().parent.parent
SIZE = 256  # kích thước nhỏ cho test CPU
CONFIG = SDXLConfig(height=SIZE, width=SIZE)


def noisy_image(width=SIZE, height=SIZE):
    return Image.effect_noise((width, height), 60).convert("RGB")


def make_prompts(indices=(1, 2, 3, 4)):
    return [ScenePrompt(i, f"prompt {i}", f"negative {i}", ("rabbit",)) for i in indices]


class FakeScheduler:
    pass


class FakePipeline:
    """Giả lập pipeline diffusers: ghi lại mọi lời gọi, trả ảnh theo hàm đã chọn."""

    def __init__(self, image_fn=None, error=None):
        self.calls = []
        self.scheduler = FakeScheduler()
        self._image_fn = image_fn or (lambda kwargs: noisy_image(kwargs["width"], kwargs["height"]))
        self._error = error

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(images=[self._image_fn(kwargs)])


class Loader:
    def __init__(self, pipeline=None, error=None):
        self.pipeline = pipeline if pipeline is not None else FakePipeline()
        self.error = error
        self.calls = 0

    def __call__(self, config):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.pipeline


class GeneratorFactory:
    def __init__(self):
        self.calls = []

    def __call__(self, device, seed):
        self.calls.append((device, seed))
        return ("generator", device, seed)


def make_generator(pipeline=None, **kwargs):
    loader = Loader(pipeline)
    factory = GeneratorFactory()
    generator = SDXLImageGenerator(CONFIG, pipeline_loader=loader, generator_factory=factory, **kwargs)
    return generator, loader, factory


# ---------- Nạp lười, không kéo thư viện nặng ----------

def test_constructor_does_not_load_model():
    loader = Loader()
    SDXLImageGenerator(CONFIG, pipeline_loader=loader)
    assert loader.calls == 0


def test_import_and_constructor_do_not_import_gpu_packages():
    script = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname.split('.')[0] in {'torch', 'diffusers', 'transformers', 'huggingface_hub', 'accelerate'}:\n"
        "            raise AssertionError('Forbidden import: ' + fullname)\n"
        "sys.meta_path.insert(0, Block())\n"
        "from src.image_generator.sdxl_generator import SDXLImageGenerator, SDXLConfig\n"
        "SDXLImageGenerator(SDXLConfig())\n"
    )
    completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_model_loads_once_for_all_four_scenes():
    generator, loader, _ = make_generator()
    results = generator.generate_all(make_prompts(), base_seed=42)
    assert len(results) == 4
    assert loader.calls == 1
    assert generator.model_load_sec is not None


# ---------- Kết quả và thông số ----------

def test_generate_all_records_scene_seed_backend_and_images():
    generator, _, factory = make_generator()
    results = generator.generate_all(make_prompts(), base_seed=42)
    assert [r.scene_index for r in results] == [1, 2, 3, 4]
    assert [r.seed for r in results] == [43, 44, 45, 46]
    assert all(r.backend == "sdxl" and isinstance(r.image, Image.Image) for r in results)
    assert all(r.elapsed_sec >= 0 for r in results)
    assert factory.calls == [("cuda", 43), ("cuda", 44), ("cuda", 45), ("cuda", 46)]


def test_pipeline_receives_exact_prompt_and_inference_arguments():
    pipeline = FakePipeline()
    generator, _, _ = make_generator(pipeline)
    generator.generate_all(make_prompts(), base_seed=100)
    assert len(pipeline.calls) == 4
    first = pipeline.calls[0]
    assert first["prompt"] == "prompt 1" and first["negative_prompt"] == "negative 1"
    assert first["num_inference_steps"] == 6 and first["guidance_scale"] == 2.0
    assert first["height"] == SIZE and first["width"] == SIZE
    assert first["generator"] == ("generator", "cuda", 101)
    assert [call["generator"][2] for call in pipeline.calls] == [101, 102, 103, 104]


def test_params_are_recorded_for_the_log():
    generator, _, _ = make_generator()
    image = generator.generate_all(make_prompts())[0]
    params = image.params
    assert params["repo_id"] == DEFAULT_REPO_ID and params["revision"] == DEFAULT_REVISION
    assert params["dtype"] == "float16" and params["variant"] == "fp16"
    assert params["num_inference_steps"] == 6 and params["guidance_scale"] == 2.0
    assert (params["height"], params["width"]) == (SIZE, SIZE)
    assert params["scheduler"] == "FakeScheduler" and params["device"] == "cuda"
    assert params["model_load_sec"] == generator.model_load_sec
    assert set(params["versions"]) == {"torch", "diffusers", "transformers", "accelerate", "huggingface_hub"}


def test_same_scene_same_seed_independent_of_prompt_text():
    """Ablation: cùng cảnh ở hai cấu hình prompt khác nhau phải dùng cùng seed."""
    generator, _, factory = make_generator()
    other = [ScenePrompt(p.scene_index, "khac han", "neg", ()) for p in make_prompts()]
    generator.generate_all(make_prompts(), base_seed=42)
    first_run = list(factory.calls)
    factory.calls.clear()
    generator.generate_all(other, base_seed=42)
    assert factory.calls == first_run


def test_is_substitutable_for_base_generator():
    assert isinstance(SDXLImageGenerator(CONFIG, pipeline_loader=Loader()), BaseImageGenerator)


# ---------- Lỗi phải nổi lên, không retry, không fallback ----------

def test_load_failure_propagates_without_retry_or_fallback():
    loader = Loader(error=RuntimeError("không tải được model"))
    generator = SDXLImageGenerator(CONFIG, pipeline_loader=loader, generator_factory=GeneratorFactory())
    with pytest.raises(RuntimeError, match="không tải được model"):
        generator.generate_all(make_prompts())
    assert loader.calls == 1


def test_generation_failure_stops_at_first_scene():
    pipeline = FakePipeline(error=RuntimeError("hết VRAM"))
    generator, loader, _ = make_generator(pipeline)
    with pytest.raises(RuntimeError, match="hết VRAM"):
        generator.generate_all(make_prompts())
    assert len(pipeline.calls) == 1 and loader.calls == 1


def test_loader_returning_nothing_is_an_error():
    generator = SDXLImageGenerator(CONFIG, pipeline_loader=lambda config: None)
    with pytest.raises(ImageGenerationError):
        generator.generate(make_prompts()[0], 43)


@pytest.mark.parametrize(
    "output",
    [
        SimpleNamespace(images=None),
        SimpleNamespace(images=[]),
        SimpleNamespace(images=["khong phai anh"]),
        SimpleNamespace(),
    ],
)
def test_invalid_pipeline_output_is_an_error(output):
    class Pipeline(FakePipeline):
        def __call__(self, **kwargs):
            return output

    generator, _, _ = make_generator(Pipeline())
    with pytest.raises(ImageGenerationError):
        generator.generate(make_prompts()[0], 43)


def test_two_images_from_pipeline_is_an_error():
    pipeline = FakePipeline()
    pipeline.__class__ = type("Two", (FakePipeline,), {
        "__call__": lambda self, **kw: SimpleNamespace(images=[noisy_image(), noisy_image()])})
    generator, _, _ = make_generator(pipeline)
    with pytest.raises(ImageGenerationError):
        generator.generate(make_prompts()[0], 43)


def test_wrong_image_size_is_an_error():
    generator, _, _ = make_generator(FakePipeline(image_fn=lambda kw: noisy_image(SIZE + 8, SIZE)))
    with pytest.raises(ImageGenerationError, match="Kích thước"):
        generator.generate(make_prompts()[0], 43)


@pytest.mark.parametrize(
    "image_fn",
    [
        lambda kw: Image.new("RGB", (SIZE, SIZE), (0, 0, 0)),         # đen hoàn toàn
        lambda kw: Image.new("RGB", (SIZE, SIZE), (128, 128, 128)),   # xám phẳng, không có chi tiết
    ],
)
def test_black_or_blank_image_is_an_error_not_a_result(image_fn):
    generator, _, _ = make_generator(FakePipeline(image_fn=image_fn))
    with pytest.raises(ImageGenerationError, match="đen hoặc trống"):
        generator.generate(make_prompts()[0], 43)


# ---------- Đầu vào sai bị bắt trước khi nạp model ----------

@pytest.mark.parametrize("bad_prompt", [None, "prompt", {"prompt": "x"}])
def test_non_scene_prompt_is_rejected_before_loading(bad_prompt):
    generator, loader, _ = make_generator()
    with pytest.raises(ValueError):
        generator.generate(bad_prompt, 43)
    assert loader.calls == 0


@pytest.mark.parametrize("bad_seed", [-1, True, 1.5, "43", None])
def test_invalid_seed_is_rejected_before_loading(bad_seed):
    generator, loader, _ = make_generator()
    with pytest.raises(ValueError):
        generator.generate(make_prompts()[0], bad_seed)
    assert loader.calls == 0


@pytest.mark.parametrize("indices", [(1, 2, 3), (1, 1, 3, 4), (4, 3, 2, 1), (0, 1, 2, 3)])
def test_invalid_prompt_list_is_rejected_before_loading(indices):
    generator, loader, _ = make_generator()
    with pytest.raises(ValueError):
        generator.generate_all(make_prompts(indices))
    assert loader.calls == 0


# ---------- Cấu hình ----------

def test_default_config_pins_model_and_revision():
    config = SDXLConfig()
    assert config.repo_id == "Lykon/dreamshaper-xl-v2-turbo"
    assert config.revision == "f70ad5bce436c640d23fc02cd0a6ccc787280b6e"
    assert (config.num_inference_steps, config.guidance_scale) == (6, 2.0)
    assert (config.height, config.width, config.device) == (1024, 1024, "cuda")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"revision": "main"},
        {"revision": "f70ad5bc"},
        {"revision": "F70AD5BCE436C640D23FC02CD0A6CCC787280B6E"},
        {"revision": 123},
        {"repo_id": ""},
        {"repo_id": "khong-co-gach-cheo"},
        {"num_inference_steps": 0},
        {"num_inference_steps": True},
        {"num_inference_steps": 1.5},
        {"guidance_scale": -1},
        {"guidance_scale": float("nan")},
        {"guidance_scale": True},
        {"height": 250},
        {"width": 0},
        {"height": 4096},
        {"width": 1024.0},
        {"device": "cpu"},
        {"device": "cuda:x"},
        {"device": "gpu"},
        {"cache_dir": 5},
        {"min_pixel_std": -1},
        {"min_pixel_mean": float("inf")},
    ],
)
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        SDXLConfig(**kwargs)


def test_wrong_constructor_arguments_are_rejected():
    with pytest.raises(TypeError):
        SDXLImageGenerator({"height": 1024})
    with pytest.raises(TypeError):
        SDXLImageGenerator(CONFIG, pipeline_loader="khong goi duoc")
    with pytest.raises(TypeError):
        SDXLImageGenerator(CONFIG, generator_factory=42)


def test_download_patterns_exclude_the_huge_root_checkpoints():
    """Ba checkpoint đơn file ở thư mục gốc (~6.6 GiB mỗi file) không được phép bị tải."""
    for name in ("DreamShaperXL_Turbo_V2-SFW.safetensors",
                 "DreamShaperXL_Turbo_v2.safetensors",
                 "DreamShaperXL_Turbo_v2_1.safetensors"):
        assert not any(fnmatch.fnmatch(name, pattern) for pattern in ALLOW_PATTERNS), name
    for needed in ("unet/diffusion_pytorch_model.fp16.safetensors", "vae/diffusion_pytorch_model.fp16.safetensors",
                   "text_encoder/model.fp16.safetensors", "text_encoder_2/model.fp16.safetensors"):
        assert needed in ALLOW_PATTERNS
    assert not any(pattern.endswith("model.safetensors") or pattern == "*" for pattern in ALLOW_PATTERNS)


def test_default_loader_requires_cuda_and_never_falls_back(monkeypatch):
    """Không có CUDA thì phải báo lỗi rõ ràng. Giả lập torch để chạy được trên CPU."""
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_diffusers = SimpleNamespace(AutoPipelineForText2Image=object, DPMSolverMultistepScheduler=object)
    fake_hub = SimpleNamespace(snapshot_download=lambda *a, **k: pytest.fail("không được tải model khi thiếu CUDA"))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    with pytest.raises(ImageGenerationError, match="CUDA"):
        sdxl_generator._load_pipeline(CONFIG)


# ---------- Tích hợp với pipeline dùng chung ----------

def test_works_as_image_backend_of_the_shared_pipeline(tmp_path):
    from app import load_example_summary

    generator, loader, _ = make_generator()
    pipeline = build_pipeline(PipelineConfig(output_dir=tmp_path), image_backend=generator)
    result = pipeline.generate(load_example_summary())
    assert result.comic_path.is_file() and result.comic_path.stat().st_size > 0
    assert [image.backend for image in result.images] == ["sdxl"] * 4
    assert [image.scene_index for image in result.images] == [1, 2, 3, 4]
    assert loader.calls == 1