from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from src.image_generator.schemas import GeneratedImage

EXPECTED_PANELS = 4
# renderer.py nằm ở <root>/src/comic_renderer/ nên parents[2] là thư mục gốc repo.
DEFAULT_FONT_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSans-VariableFont_wdth,wght.ttf"
)


class CaptionOverflowError(ValueError):
    """Caption quá dài, không vừa khung kể cả khi đã giảm về cỡ chữ nhỏ nhất."""


@dataclass(frozen=True)
class RenderConfig:
    panel_size: int = 512            # ảnh được fit về hình vuông panel_size x panel_size
    caption_height: int = 130        # chiều cao vùng caption bên dưới ảnh
    font_path: Path = DEFAULT_FONT_PATH
    font_size: int = 24              # cỡ chữ ưu tiên
    min_font_size: int = 14          # nhỏ hơn mức này thì báo lỗi, không cắt chữ
    line_spacing: int = 4
    text_padding: int = 12
    border_width: int = 4            # viền quanh mỗi panel
    gap: int = 12                    # khoảng cách giữa các panel
    margin: int = 12                 # lề quanh toàn bộ truyện
    background: tuple[int, int, int] = (255, 255, 255)
    border_color: tuple[int, int, int] = (20, 20, 20)
    text_color: tuple[int, int, int] = (20, 20, 20)


@dataclass
class RenderResult:
    panels: list[Image.Image]
    comic: Image.Image
    font_sizes: list[int] = field(default_factory=list)  # cỡ chữ thực tế đã dùng cho từng panel


def _split_long_word(word: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Cắt một từ dài hơn max_width thành nhiều đoạn theo từng ký tự."""
    chunks: list[str] = []
    current = ""
    for ch in word:
        if current and font.getlength(current + ch) > max_width:
            chunks.append(current)
            current = ch
        else:
            current += ch
    if current:
        chunks.append(current)
    return chunks


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Xuống dòng theo chiều rộng thực tế (pixel) của chữ, không đếm số ký tự."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if font.getlength(word) <= max_width:
            current = word
        else:
            chunks = _split_long_word(word, font, max_width)
            lines.extend(chunks[:-1])
            current = chunks[-1]
    if current:
        lines.append(current)
    return lines


class ComicRenderer:
    """Chèn caption tiếng Việt vào từng ảnh và ghép 4 panel theo layout 2x2."""

    def __init__(self, config: RenderConfig | None = None) -> None:
        self.config = config or RenderConfig()
        if not Path(self.config.font_path).is_file():
            # Cố ý không fallback sang font mặc định: font đó có thể thiếu dấu tiếng Việt.
            raise FileNotFoundError(
                f"Không tìm thấy font: {self.config.font_path}. "
                "Hãy đặt file font hỗ trợ tiếng Việt vào assets/fonts/."
            )

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.config.font_path), size)

    @staticmethod
    def _line_height(font: ImageFont.FreeTypeFont) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent

    def _fit_caption(self, caption: str) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
        cfg = self.config
        max_width = cfg.panel_size - 2 * cfg.text_padding
        max_height = cfg.caption_height - 2 * cfg.text_padding
        for size in range(cfg.font_size, cfg.min_font_size - 1, -1):
            font = self._font(size)
            lines = wrap_text(caption, font, max_width)
            line_h = self._line_height(font)
            total = len(lines) * line_h + (len(lines) - 1) * cfg.line_spacing
            if lines and total <= max_height:
                return font, lines, size
        raise CaptionOverflowError(
            f"Caption không vừa khung ở cỡ chữ tối thiểu {cfg.min_font_size}: {caption!r}"
        )

    def render_panel(self, image: Image.Image, caption: str) -> tuple[Image.Image, int]:
        """Trả về (panel, cỡ chữ đã dùng). Raise CaptionOverflowError nếu caption không vừa."""
        cfg = self.config
        # NFC chỉ để đo và vẽ cho đúng dấu; caption gốc của storyboard không bị sửa.
        text = unicodedata.normalize("NFC", caption).strip()
        if not text:
            raise ValueError("Caption rỗng")

        font, lines, size = self._fit_caption(text)

        picture = ImageOps.fit(
            image.convert("RGB"), (cfg.panel_size, cfg.panel_size), Image.LANCZOS
        )
        panel = Image.new(
            "RGB", (cfg.panel_size, cfg.panel_size + cfg.caption_height), cfg.background
        )
        panel.paste(picture, (0, 0))

        draw = ImageDraw.Draw(panel)
        line_h = self._line_height(font)
        total = len(lines) * line_h + (len(lines) - 1) * cfg.line_spacing
        y = cfg.panel_size + (cfg.caption_height - total) // 2
        for line in lines:
            draw.text(
                (cfg.panel_size / 2, y), line, font=font, fill=cfg.text_color, anchor="ma"
            )
            y += line_h + cfg.line_spacing

        draw.rectangle(
            [(0, 0), (panel.width - 1, panel.height - 1)],
            outline=cfg.border_color,
            width=cfg.border_width,
        )
        return panel, size

    def render(self, images: list[GeneratedImage], captions: list[str]) -> RenderResult:
        """Ghép đúng 4 panel theo thứ tự đọc: 1 2 / 3 4."""
        cfg = self.config
        if len(images) != EXPECTED_PANELS or len(captions) != EXPECTED_PANELS:
            raise ValueError(
                f"Cần đúng {EXPECTED_PANELS} ảnh và {EXPECTED_PANELS} caption, "
                f"nhận {len(images)} ảnh và {len(captions)} caption"
            )
        indices = [g.scene_index for g in images]
        if any(b <= a for a, b in zip(indices, indices[1:])):
            raise ValueError(f"scene_index của ảnh phải tăng dần, nhận {indices}")

        panels: list[Image.Image] = []
        sizes: list[int] = []
        for generated, caption in zip(images, captions):
            panel, size = self.render_panel(generated.image, caption)
            panels.append(panel)
            sizes.append(size)

        pw, ph = panels[0].size
        width = 2 * cfg.margin + 2 * pw + cfg.gap
        height = 2 * cfg.margin + 2 * ph + cfg.gap
        comic = Image.new("RGB", (width, height), cfg.background)
        for i, panel in enumerate(panels):
            col, row = i % 2, i // 2
            comic.paste(
                panel, (cfg.margin + col * (pw + cfg.gap), cfg.margin + row * (ph + cfg.gap))
            )
        return RenderResult(panels=panels, comic=comic, font_sizes=sizes)

    @staticmethod
    def save(result: RenderResult, out_dir: str | Path) -> list[Path]:
        """Xuất panel_1..4.png và comic.png. Trả về danh sách file đã ghi."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i, panel in enumerate(result.panels, start=1):
            path = out / f"panel_{i}.png"
            panel.save(path)
            paths.append(path)
        comic_path = out / "comic.png"
        result.comic.save(comic_path)
        paths.append(comic_path)
        return paths