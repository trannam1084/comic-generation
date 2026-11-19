from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from PIL import Image, ImageDraw, ImageFont

from .schemas import GeneratedImage, ScenePrompt

logger = logging.getLogger(__name__)

EXPECTED_SCENES = 4


class BaseImageGenerator(ABC):
    """Interface chung cho mọi image backend (mock, SDXL, API...)."""

    name: str = "base"

    @abstractmethod
    def generate(self, prompt: ScenePrompt, seed: int) -> GeneratedImage:
        """Sinh ảnh cho một cảnh. Phải raise lỗi nếu thất bại, không trả ảnh thay thế."""

    def generate_all(
        self, prompts: list[ScenePrompt], base_seed: int = 42
    ) -> list[GeneratedImage]:
        """Sinh lần lượt các ảnh, giữ nguyên thứ tự cảnh."""
        if len(prompts) != EXPECTED_SCENES:
            raise ValueError(
                f"Cần đúng {EXPECTED_SCENES} prompt, nhận được {len(prompts)}"
            )
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
        if width <= 0 or height <= 0:
            raise ValueError("width và height phải > 0")
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
        big = ImageFont.load_default(size=self.height // 3)
        small = ImageFont.load_default(size=self.height // 22)

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