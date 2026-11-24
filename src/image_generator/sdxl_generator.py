"""Real Image Generator: SDXL (Lykon/dreamshaper-xl-v2-turbo) qua diffusers.

- Import và constructor không tải model, không import torch/diffusers (nạp lười ở lần generate đầu).
- Revision của model được ghim cố định (40 ký tự hex), không dùng tên branch.
- Lỗi luôn được raise: không retry, không fallback sang mock, không thay bằng ảnh khác.
"""

from __future__ import annotations

import importlib.metadata as metadata
import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from .image_generator import BaseImageGenerator
from .schemas import GeneratedImage, ScenePrompt

logger = logging.getLogger(__name__)

DEFAULT_REPO_ID = "Lykon/dreamshaper-xl-v2-turbo"
# Revision đã kiểm tra ở bước 3.1/3.2 trên Kaggle (T4, diffusers 0.42.0).
DEFAULT_REVISION = "f70ad5bce436c640d23fc02cd0a6ccc787280b6e"

# Chỉ tải các file fp16 cần dùng (~6.5 GiB). Repo còn 3 checkpoint đơn file 6.6 GiB ở thư mục gốc
# mà pipeline không cần; các pattern dưới đây cố ý không khớp chúng.
ALLOW_PATTERNS = (
    "model_index.json",
    "scheduler/*",
    "tokenizer/*",
    "tokenizer_2/*",
    "text_encoder/config.json",
    "text_encoder/model.fp16.safetensors",
    "text_encoder_2/config.json",
    "text_encoder_2/model.fp16.safetensors",
    "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors",
    "vae/config.json",
    "vae/diffusion_pytorch_model.fp16.safetensors",
)

_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_DEVICE_RE = re.compile(r"cuda(:\d+)?")
_LIBRARIES = ("torch", "diffusers", "transformers", "accelerate", "huggingface_hub")


class ImageGenerationError(RuntimeError):
    """Sinh ảnh thất bại hoặc kết quả không hợp lệ. Không bao giờ được thay bằng ảnh giả."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class SDXLConfig:
    """Cấu hình suy luận. Mặc định trùng với smoke test đã chạy thành công (6 bước, guidance 2.0)."""

    repo_id: str = DEFAULT_REPO_ID
    revision: str = DEFAULT_REVISION
    num_inference_steps: int = 6
    guidance_scale: float = 2.0
    height: int = 1024
    width: int = 1024
    device: str = "cuda"
    cache_dir: str | Path | None = None
    min_pixel_std: float = 5.0   # ảnh có độ lệch chuẩn xám thấp hơn mức này bị coi là trống
    min_pixel_mean: float = 5.0  # ảnh có độ sáng trung bình thấp hơn mức này bị coi là đen

    def __post_init__(self) -> None:
        if not isinstance(self.repo_id, str) or "/" not in self.repo_id.strip("/"):
            raise ValueError("repo_id phải có dạng 'chu-so-huu/ten-model'")
        if not isinstance(self.revision, str) or not _REVISION_RE.fullmatch(self.revision):
            raise ValueError("revision phải là mã commit đầy đủ 40 ký tự hex (không dùng tên branch)")
        if not _is_int(self.num_inference_steps) or self.num_inference_steps < 1:
            raise ValueError("num_inference_steps phải là số nguyên >= 1")
        if not _is_number(self.guidance_scale) or self.guidance_scale < 0:
            raise ValueError("guidance_scale phải là số hữu hạn >= 0")
        for name in ("height", "width"):
            value = getattr(self, name)
            if not _is_int(value) or not 256 <= value <= 2048 or value % 8 != 0:
                raise ValueError(f"{name} phải là số nguyên từ 256 đến 2048 và chia hết cho 8")
        if not isinstance(self.device, str) or not _DEVICE_RE.fullmatch(self.device):
            raise ValueError("device phải là 'cuda' hoặc 'cuda:N' (backend này không chạy trên CPU)")
        if self.cache_dir is not None and not isinstance(self.cache_dir, (str, Path)):
            raise ValueError("cache_dir phải là str, Path hoặc None")
        for name in ("min_pixel_std", "min_pixel_mean"):
            if not _is_number(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} phải là số hữu hạn >= 0")


def _load_pipeline(config: SDXLConfig) -> Any:
    """Tải đúng các file fp16 ở revision đã ghim rồi nạp pipeline lên GPU. Import nặng nằm ở đây."""
    import torch
    from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler
    from huggingface_hub import snapshot_download

    if not torch.cuda.is_available():
        raise ImageGenerationError(
            "CUDA không khả dụng. Backend SDXL không chạy trên CPU và không fallback sang mock."
        )
    local_dir = snapshot_download(
        config.repo_id,
        revision=config.revision,
        allow_patterns=list(ALLOW_PATTERNS),
        cache_dir=str(config.cache_dir) if config.cache_dir is not None else None,
    )
    pipeline = AutoPipelineForText2Image.from_pretrained(local_dir, dtype=torch.float16, variant="fp16")
    pipeline.scheduler = DPMSolverMultistepScheduler.from_config(pipeline.scheduler.config)
    pipeline.set_progress_bar_config(disable=True)
    return pipeline.to(config.device)


def _make_generator(device: str, seed: int) -> Any:
    import torch

    return torch.Generator(device=device).manual_seed(seed)


def _library_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in _LIBRARIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


class SDXLImageGenerator(BaseImageGenerator):
    """Sinh ảnh thật bằng SDXL. Dùng thay cho MockImageGenerator mà không đổi pipeline."""

    name = "sdxl"

    def __init__(
        self,
        config: SDXLConfig | None = None,
        *,
        pipeline_loader: Callable[[SDXLConfig], Any] | None = None,
        generator_factory: Callable[[str, int], Any] | None = None,
    ) -> None:
        if config is not None and not isinstance(config, SDXLConfig):
            raise TypeError("config phải là SDXLConfig")
        for label, hook in (("pipeline_loader", pipeline_loader), ("generator_factory", generator_factory)):
            if hook is not None and not callable(hook):
                raise TypeError(f"{label} phải là callable")
        self.config = config if config is not None else SDXLConfig()
        self._loader = pipeline_loader if pipeline_loader is not None else _load_pipeline
        self._generator_factory = generator_factory if generator_factory is not None else _make_generator
        self._pipeline: Any = None
        self.model_load_sec: float | None = None

    def _ensure_loaded(self) -> Any:
        if self._pipeline is None:
            start = time.perf_counter()
            pipeline = self._loader(self.config)  # lỗi được giữ nguyên, không retry
            if pipeline is None or not callable(pipeline):
                raise ImageGenerationError("Loader không trả về pipeline hợp lệ.")
            self.model_load_sec = time.perf_counter() - start
            self._pipeline = pipeline
            logger.info("Đã nạp model %s (revision %s) sau %.1fs",
                        self.config.repo_id, self.config.revision[:8], self.model_load_sec)
        return self._pipeline

    def _params(self, pipeline: Any) -> dict[str, Any]:
        scheduler = getattr(pipeline, "scheduler", None)
        return {
            "repo_id": self.config.repo_id,
            "revision": self.config.revision,
            "dtype": "float16",
            "variant": "fp16",
            "scheduler": type(scheduler).__name__ if scheduler is not None else None,
            "num_inference_steps": self.config.num_inference_steps,
            "guidance_scale": self.config.guidance_scale,
            "height": self.config.height,
            "width": self.config.width,
            "device": self.config.device,
            "model_load_sec": self.model_load_sec,
            "versions": _library_versions(),
        }

    def _check_image(self, images: object) -> Image.Image:
        if not isinstance(images, (list, tuple)) or len(images) != 1:
            raise ImageGenerationError("Pipeline phải trả về đúng một ảnh.")
        image = images[0]
        if not isinstance(image, Image.Image):
            raise ImageGenerationError("Pipeline trả về dữ liệu không phải ảnh PIL.")
        expected = (self.config.width, self.config.height)
        if image.size != expected:
            raise ImageGenerationError(f"Kích thước ảnh {image.size} khác cấu hình {expected}.")
        gray = ImageStat.Stat(image.convert("L"))
        mean, std = gray.mean[0], gray.stddev[0]
        if std < self.config.min_pixel_std or mean < self.config.min_pixel_mean:
            raise ImageGenerationError(
                f"Ảnh sinh ra gần như đen hoặc trống (mean={mean:.1f}, std={std:.1f}); "
                "không thay bằng ảnh khác."
            )
        return image

    def generate(self, prompt: ScenePrompt, seed: int) -> GeneratedImage:
        if not isinstance(prompt, ScenePrompt):
            raise ValueError("prompt phải là ScenePrompt")
        if not _is_int(seed) or seed < 0:
            raise ValueError(f"seed phải là số nguyên >= 0, nhận {seed!r}")

        pipeline = self._ensure_loaded()
        generator = self._generator_factory(self.config.device, seed)
        start = time.perf_counter()
        output = pipeline(
            prompt=prompt.prompt,
            negative_prompt=prompt.negative_prompt,
            num_inference_steps=self.config.num_inference_steps,
            guidance_scale=self.config.guidance_scale,
            height=self.config.height,
            width=self.config.width,
            generator=generator,
        )
        image = self._check_image(getattr(output, "images", None))
        elapsed = time.perf_counter() - start
        logger.info("[sdxl] cảnh %d, seed=%d, %.2fs", prompt.scene_index, seed, elapsed)
        return GeneratedImage(
            scene_index=prompt.scene_index,
            image=image,
            seed=seed,
            backend=self.name,
            elapsed_sec=elapsed,
            params=self._params(pipeline),
        )