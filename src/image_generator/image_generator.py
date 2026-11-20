from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from PIL import Image, ImageDraw, ImageFont

from .schemas import GeneratedImage, ScenePrompt

logger = logging.getLogger(__name__)

EXPECTED_SCENES = 4
MIN_IMAGE_SIZE = 64  # nhỏ hơn mức này thì cỡ chữ và tọa độ khung vẽ không còn hợp lệ


def validate_scene_prompts(prompts: object) -> None:
    """Raise ValueError nếu prompts không phải đúng 4 ScenePrompt hợp lệ, scene_index = [1, 2, 3, 4]."""
    if not isinstance(prompts, (list, tuple)):
        raise ValueError(f"prompts phải là list hoặc tuple, nhận {type(prompts).__name__}")
    if len(prompts) != EXPECTED_SCENES:
        raise ValueError(f"Cần đúng {EXPECTED_SCENES} prompt, nhận được {len(prompts)}")

    for position, p in enumerate(prompts, start=1):
        if not isinstance(p, ScenePrompt):
            raise ValueError(f"Prompt thứ {position} không phải ScenePrompt: {type(p).__name__}")
        if isinstance(p.scene_index, bool) or not isinstance(p.scene_index, int):
            raise ValueError(f"Prompt thứ {position}: scene_index phải là int, nhận {p.scene_index!r}")
        if not isinstance(p.prompt, str) or not p.prompt.strip():
            raise ValueError(f"Prompt thứ {position}: prompt phải là chuỗi không rỗng")
        if not isinstance(p.negative_prompt, str):
            raise ValueError(f"Prompt thứ {position}: negative_prompt phải là chuỗi")

    indices = [p.scene_index for p in prompts]
    if indices != list(range(1, EXPECTED_SCENES + 1)):
        raise ValueError(f"scene_index phải đúng [1, 2, 3, 4] theo thứ tự, nhận {indices}")


class BaseImageGenerator(ABC):
    """Interface chung cho mọi image backend (mock, SDXL, API...)."""

    name: str = "base"

    @abstractmethod
    def generate(self, prompt: ScenePrompt, seed: int) -> GeneratedImage:
        """Sinh ảnh cho một cảnh. Phải raise lỗi nếu thất bại, không trả ảnh thay thế."""

    def generate_all(
        self, prompts: list[ScenePrompt], base_seed: int = 42
    ) -> list[GeneratedImage]:
        """Kiểm tra toàn bộ đầu vào rồi mới sinh lần lượt 4 ảnh, giữ nguyên thứ tự cảnh."""
        validate_scene_prompts(prompts)
        if isinstance(base_seed, bool) or not isinstance(base_seed, int):
            raise ValueError(f"base_seed phải là int, nhận {base_seed!r}")

        results: list[GeneratedImage] = []
        for p in prompts:
            seed = base_seed + p.scene_index
            logger.info("[%s] scene %d, seed=%d", self.name, p.scene_index, seed)
            results.append(self.generate(p, seed))
        return results


class MockImageGenerator(BaseImageGenerator):
    """Sinh ảnh placeholder bằng Pillow, chạy CPU, dùng để kiểm tra pipeline."""

    name = "mock"

    # 4 màu nền khác nhau để dễ phân biệt cảnh bằng mắt.
    _COLORS = [(205, 225, 245), (215, 240, 215), (250, 235, 205), (240, 215, 225)]

    def __init__(self, width: int = 512, height: int = 512) -> None:
        for label, value in (("width", width), ("height", height)):
            if isinstance(value, bool) or not isinstance(value, int) or value < MIN_IMAGE_SIZE:
                raise ValueError(
                    f"{label} phải là số nguyên >= {MIN_IMAGE_SIZE}, nhận {value!r}"
                )
        self.width = width
        self.height = height

    def generate(self, prompt: ScenePrompt, seed: int) -> GeneratedImage:
        start = time.perf_counter()
        color = self._COLORS[(prompt.scene_index - 1) % len(self._COLORS)]
        img = Image.new("RGB", (self.width, self.height), color)
        draw = ImageDraw.Draw(img)

        draw.rectangle(
            [(4, 4), (self.width - 5, self.height - 5)], outline=(80, 80, 80), width=3
        )
        big = ImageFont.load_default(size=max(8, self.height // 3))
        small = ImageFont.load_default(size=max(8, self.height // 22))

        draw.text(
            (self.width / 2, self.height / 2),
            str(prompt.scene_index),
            font=big,
            fill=(60, 60, 60),
            anchor="mm",
        )
        draw.text(
            (self.width / 2, self.height - 24),
            f"MOCK  seed={seed}",
            font=small,
            fill=(90, 90, 90),
            anchor="mm",
        )

        elapsed = time.perf_counter() - start
        return GeneratedImage(
            scene_index=prompt.scene_index,
            image=img,
            seed=seed,
            backend=self.name,
            elapsed_sec=elapsed,
            params={"width": self.width, "height": self.height},
        )