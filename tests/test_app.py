import dataclasses
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import app
from app import load_example_summary, run_generation, sanitize_message
from src.configuration import PipelineConfig
from src.factory import build_pipeline
from src.image_generator.image_generator import BaseImageGenerator
from src.pipeline import ComicPipeline, PipelineContractError
from src.pipeline_adapters import StoryStageError

SUMMARY = load_example_summary()


# ---------- Công cụ test ----------

class CountingPipeline:
    """Bọc pipeline thật để đếm số lần UI gọi generate."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def generate(self, summary):
        self.calls.append(summary)
        return self.inner.generate(summary)


class SpyPipeline:
    """Chỉ dùng cho kết quả/lỗi mà factory thật không tạo ra được (hợp đồng sai, kết quả hỏng)."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def generate(self, summary):
        self.calls.append(summary)
        if self.error is not None:
            raise self.error
        return self.result


class FailingImageBackend(BaseImageGenerator):
    """Image backend thật (qua factory) nhưng luôn lỗi; đếm số lần bị gọi để kiểm tra không retry."""

    name = "failing"

    def __init__(self, error):
        self.error = error
        self.calls = 0

    def generate(self, prompt, seed):
        self.calls += 1
        raise self.error


class FailingStoryStage:
    def __init__(self, error):
        self.error = error

    def generate(self, summary):
        raise self.error


def shared_pipeline(tmp_path, **dependencies):
    return build_pipeline(PipelineConfig(output_dir=tmp_path), **dependencies)


@pytest.fixture
def pipeline(tmp_path):
    return shared_pipeline(tmp_path)


@pytest.fixture
def result(pipeline):
    return pipeline.generate(SUMMARY)


def leaky_story_error():
    error = StoryStageError("backend_error")
    try:
        raise RuntimeError(r"raw model output C:\Users\hoang\secret.json token=abc123456")
    except RuntimeError as cause:
        error.__cause__ = cause
    error.attempts = ("RAW_MODEL_OUTPUT_SECRET",)
    return error


# ---------- Chạy trên pipeline dùng chung (factory thật) ----------

def test_example_summary_available():
    assert isinstance(SUMMARY, str) and SUMMARY.strip()


def test_success_through_shared_factory(pipeline):
    out = run_generation(pipeline, SUMMARY)
    assert out.ok, out.status
    assert len(out.gallery) == 4
    assert all(isinstance(image, Image.Image) for image, _ in out.gallery)
    assert [caption.split(":")[0] for _, caption in out.gallery] == [f"Cảnh {i}" for i in range(1, 5)]
    assert Path(out.comic_path).is_file()
    assert len(json.loads(out.storyboard_json)["scenes"]) == 4
    for i in range(1, 5):
        assert f"[Cảnh {i}]" in out.prompts_text
    assert out.run_info.count("backend=mock") == 4
    assert "Tổng thời gian" in out.run_info and "Hoàn thành" in out.status


def test_shared_factory_output_is_a_real_comic(pipeline):
    out = run_generation(pipeline, SUMMARY)
    with Image.open(out.comic_path) as comic:
        assert comic.format == "PNG"
        assert comic.size == (1060, 1320)


def test_unsupported_summary_is_a_clear_error_not_a_fake_comic(pipeline):
    out = run_generation(pipeline, "Một câu chuyện khác hẳn.")
    assert not out.ok and out.status.startswith("LỖI")
    assert out.gallery == [] and out.comic_path is None


def test_two_runs_never_overwrite_each_other(pipeline):
    first = pipeline.generate(SUMMARY)
    first_bytes = first.comic_path.read_bytes()
    second = pipeline.generate(SUMMARY)
    assert first.comic_path != second.comic_path
    assert first.comic_path.is_file() and second.comic_path.is_file()
    assert first.comic_path.read_bytes() == first_bytes


# ---------- Đúng một lần gọi pipeline.generate, không retry/fallback ----------

def test_success_calls_generate_exactly_once(pipeline, caplog):
    counting = CountingPipeline(pipeline)
    with caplog.at_level(logging.INFO):
        out = run_generation(counting, SUMMARY)
    assert out.ok and counting.calls == [SUMMARY]
    assert caplog.text.count("Gọi pipeline.generate một lần") == 1


def test_failure_does_not_retry_or_fall_back(tmp_path):
    backend = FailingImageBackend(RuntimeError("hết VRAM"))
    counting = CountingPipeline(shared_pipeline(tmp_path, image_backend=backend))
    out = run_generation(counting, SUMMARY)
    assert not out.ok and "RuntimeError" in out.status
    assert out.gallery == [] and out.comic_path is None
    assert len(counting.calls) == 1 and backend.calls == 1


@pytest.mark.parametrize("blank", ["", "   ", "\n\t", None, 123])
def test_blank_summary_is_rejected_without_calling_pipeline(blank, pipeline):
    counting = CountingPipeline(pipeline)
    out = run_generation(counting, blank)
    assert not out.ok and out.status.startswith("LỖI")
    assert counting.calls == []


def test_summary_is_passed_verbatim_to_pipeline(pipeline):
    raw = "  " + SUMMARY + "\n"
    counting = CountingPipeline(pipeline)
    run_generation(counting, raw)
    assert counting.calls == [raw]


# ---------- StoryStageError: không in raw output hay bí mật ----------

def test_story_stage_error_shows_only_category(tmp_path, caplog):
    pipeline = shared_pipeline(tmp_path, story_stage=FailingStoryStage(leaky_story_error()))
    with caplog.at_level(logging.DEBUG):
        out = run_generation(pipeline, SUMMARY)
    assert not out.ok and "backend_error" in out.status
    assert out.gallery == [] and out.comic_path is None
    for leaked in ["RAW_MODEL_OUTPUT_SECRET", "raw model output", "hoang", "secret.json", "abc123456"]:
        assert leaked not in out.status
        assert leaked not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_story_stage_error_with_unsafe_category_is_sanitized(tmp_path):
    error = StoryStageError(r"loi tai C:\Users\hoang\x.txt token=abc123456")
    pipeline = shared_pipeline(tmp_path, story_stage=FailingStoryStage(error))
    out = run_generation(pipeline, SUMMARY)
    assert "hoang" not in out.status and "abc123456" not in out.status


# ---------- Lọc thông tin nhạy cảm của lỗi khác ----------

LEAKY_ERRORS = [
    (FileNotFoundError(r"Không tìm thấy font: C:\Users\hoang\Desktop\secret_project\NotoSans.ttf"), ["hoang", "secret_project", "C:\\"]),
    (RuntimeError("không ghi được /kaggle/working/private_run/comic.png"), ["private_run", "/kaggle"]),
    (RuntimeError("401 khi gọi https://huggingface.co/api/models?token=hf_abcdefgh12345678"), ["hf_abcdefgh", "huggingface.co"]),
    (RuntimeError("Authorization: Bearer abc.def.ghi-SECRETVALUE"), ["SECRETVALUE", "abc.def"]),
    (RuntimeError("cấu hình sai api_key=TOPSECRET123456 và password: hunter2pass"), ["TOPSECRET", "hunter2pass"]),
    (ValueError("UNC \\\\fileserver\\share\\private\\data.bin bị lỗi"), ["fileserver", "private"]),
]


@pytest.mark.parametrize("error,secrets", LEAKY_ERRORS)
def test_backend_error_is_sanitized_in_ui_and_logs(error, secrets, tmp_path, caplog):
    pipeline = shared_pipeline(tmp_path, image_backend=FailingImageBackend(error))
    with caplog.at_level(logging.DEBUG):
        out = run_generation(pipeline, SUMMARY)
    assert not out.ok and type(error).__name__ in out.status
    for secret in secrets:
        assert secret not in out.status
        assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_contract_error_is_reported_with_stage_and_sanitized(caplog):
    error = PipelineContractError("render", r"Lỗi ở C:\Users\hoang\x.png token=abc12345")
    with caplog.at_level(logging.DEBUG):
        out = run_generation(SpyPipeline(error=error), SUMMARY)
    assert not out.ok and "render" in out.status and "không hợp lệ" in out.status
    assert "hoang" not in out.status and "abc12345" not in out.status
    assert "hoang" not in caplog.text and "abc12345" not in caplog.text


def test_sanitize_keeps_ordinary_messages_and_truncates():
    plain = "Chế độ demo chỉ hỗ trợ đúng tóm tắt mẫu (bấm ví dụ bên dưới ô nhập)."
    assert sanitize_message(plain) == plain
    assert len(sanitize_message("lỗi " * 500)) <= app.MAX_ERROR_CHARS + 1
    assert "\n" not in sanitize_message("a\nb\n\nc")


def test_error_with_empty_message_still_names_type(tmp_path):
    pipeline = shared_pipeline(tmp_path, image_backend=FailingImageBackend(RuntimeError()))
    assert "RuntimeError" in run_generation(pipeline, SUMMARY).status


# ---------- Kiểm tra tối thiểu trước khi báo thành công ----------

def test_missing_comic_file_is_not_success(result):
    bad = dataclasses.replace(result, comic_path=result.comic_path.parent / "khong_ton_tai.png")
    out = run_generation(SpyPipeline(bad), SUMMARY)
    assert not out.ok and "comic_path" in out.status and out.gallery == []
    assert "khong_ton_tai" not in out.status


def test_empty_comic_file_is_not_success(result, tmp_path):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    out = run_generation(SpyPipeline(dataclasses.replace(result, comic_path=empty)), SUMMARY)
    assert not out.ok and "comic_path" in out.status


def test_directory_as_comic_path_is_not_success(result, tmp_path):
    assert not run_generation(SpyPipeline(dataclasses.replace(result, comic_path=tmp_path)), SUMMARY).ok


@pytest.mark.parametrize("count", [0, 3, 5])
def test_wrong_number_of_images_is_not_success(result, count):
    images = (list(result.images) * 2)[:count]
    out = run_generation(SpyPipeline(dataclasses.replace(result, images=images)), SUMMARY)
    assert not out.ok and "images" in out.status and out.comic_path is None


@pytest.mark.parametrize("count", [0, 3, 5])
def test_wrong_number_of_prompts_is_not_success(result, count):
    prompts = (list(result.prompts) * 2)[:count]
    out = run_generation(SpyPipeline(dataclasses.replace(result, prompts=prompts)), SUMMARY)
    assert not out.ok and "prompts" in out.status


def test_non_list_images_is_not_success(result):
    out = run_generation(SpyPipeline(dataclasses.replace(result, images=None)), SUMMARY)
    assert not out.ok and "images" in out.status


def test_result_without_expected_fields_is_not_success():
    out = run_generation(SpyPipeline(object()), SUMMARY)
    assert not out.ok and "không hợp lệ" in out.status


def test_unreadable_but_complete_result_is_reported(result):
    broken = SimpleNamespace(
        comic_path=result.comic_path,
        images=result.images,
        prompts=result.prompts,
        storyboard=SimpleNamespace(scenes=[1, 2, 3, 4]),
    )
    out = run_generation(SpyPipeline(broken), SUMMARY)
    assert not out.ok and "không đọc được" in out.status


# ---------- Cấu hình demo, allowed_paths, main ----------

def test_demo_pipeline_comes_from_shared_factory_with_mock_story():
    pipeline, config = app.build_demo_pipeline()
    assert isinstance(pipeline, ComicPipeline)
    assert config.story_backend == "mock"
    assert Path(config.output_root).resolve() == app.DEMO_OUTPUT_DIR.resolve()


def test_launch_allows_only_demo_output_directory():
    _, config = app.build_demo_pipeline()
    allowed = app.launch_kwargs(7860, config.output_root)["allowed_paths"]
    assert allowed == [str(app.DEMO_OUTPUT_DIR.resolve())]
    assert str(app.OUTPUT_DIR.resolve()) not in allowed


def test_main_without_demo_refuses_to_start():
    with pytest.raises(SystemExit):
        app.main([])


def test_app_no_longer_contains_private_demo_pipeline():
    assert not hasattr(app, "_DemoPipeline")


# ---------- Giao diện Gradio ----------

def _markdown_texts(demo):
    return [str(getattr(block, "value", "")) for block in demo.blocks.values()
            if type(block).__name__ == "Markdown"]


def test_gradio_demo_mode_shows_banner_and_title(pipeline):
    gr = pytest.importorskip("gradio")
    demo = app.create_demo(pipeline, demo_mode=True)
    assert isinstance(demo, gr.Blocks)
    assert any("CHẾ ĐỘ DEMO" in text for text in _markdown_texts(demo))
    assert "DEMO" in (demo.title or "")


def test_gradio_without_demo_mode_has_no_banner(pipeline):
    pytest.importorskip("gradio")
    demo = app.create_demo(pipeline, demo_mode=False)
    assert not any("CHẾ ĐỘ DEMO" in text for text in _markdown_texts(demo))


def test_demo_mode_must_be_decided_by_the_caller(pipeline):
    pytest.importorskip("gradio")
    with pytest.raises(TypeError):
        app.create_demo(pipeline)


def test_gradio_click_keeps_concurrency_limit_one(pipeline):
    pytest.importorskip("gradio")
    demo = app.create_demo(pipeline, demo_mode=True)
    click_fns = [fn for fn in demo.fns.values() if getattr(fn.fn, "__name__", "") == "on_click"]
    assert len(click_fns) == 1
    assert click_fns[0].concurrency_limit == 1