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


def _require_int(name: str, value: object, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} phải là số nguyên >= {minimum}, nhận {value!r}")


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

    def __post_init__(self) -> None:
        for name in ("panel_size", "caption_height", "font_size", "min_font_size"):
            _require_int(name, getattr(self, name), minimum=1)
        for name in ("line_spacing", "text_padding", "border_width", "gap", "margin"):
            _require_int(name, getattr(self, name), minimum=0)
        if self.min_font_size > self.font_size:
            raise ValueError("min_font_size không được lớn hơn font_size")
        if self.text_padding < self.border_width:
            raise ValueError("text_padding phải >= border_width để chữ không đè lên viền")
        if self.panel_size - 2 * self.text_padding < 1:
            raise ValueError("panel_size quá nhỏ so với text_padding: không còn chỗ cho chữ")
        if self.caption_height - 2 * self.text_padding < 1:
            raise ValueError("caption_height quá nhỏ so với text_padding: không còn chỗ cho chữ")
        if 2 * self.border_width >= min(self.panel_size, self.caption_height):
            raise ValueError("border_width quá lớn so với kích thước panel")
        for name in ("background", "border_color", "text_color"):
            color = getattr(self, name)
            if (
                not isinstance(color, tuple)
                or len(color) != 3
                or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in color)
            ):
                raise ValueError(f"{name} phải là tuple RGB gồm 3 số nguyên 0..255, nhận {color!r}")


@dataclass
class RenderResult:
    panels: list[Image.Image]
    comic: Image.Image
    font_sizes: list[int] = field(default_factory=list)  # cỡ chữ thực tế đã dùng cho từng panel


def line_width(font: ImageFont.FreeTypeFont, text: str) -> float:
    """Độ rộng cần thiết: lấy mức lớn hơn giữa advance width và bề rộng nét vẽ thực tế."""
    left, _, right, _ = font.getbbox(text)
    return max(font.getlength(text), right - left)


def _split_long_word(word: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Cắt một từ dài hơn max_width thành nhiều đoạn theo từng ký tự."""
    chunks: list[str] = []
    current = ""
    for ch in word:
        if current and line_width(font, current + ch) > max_width:
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
        if line_width(font, candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if line_width(font, word) <= max_width:
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
            fits_width = all(line_width(font, line) <= max_width for line in lines)
            if lines and fits_width and total <= max_height:
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
        if not isinstance(images, (list, tuple)) or not isinstance(captions, (list, tuple)):
            raise ValueError("images và captions phải là list hoặc tuple")
        if len(images) != EXPECTED_PANELS or len(captions) != EXPECTED_PANELS:
            raise ValueError(
                f"Cần đúng {EXPECTED_PANELS} ảnh và {EXPECTED_PANELS} caption, "
                f"nhận {len(images)} ảnh và {len(captions)} caption"
            )
        for position, (generated, caption) in enumerate(zip(images, captions), start=1):
            if not isinstance(generated, GeneratedImage) or not isinstance(generated.image, Image.Image):
                raise ValueError(f"Ảnh thứ {position} không phải GeneratedImage chứa PIL Image")
            if isinstance(generated.scene_index, bool) or not isinstance(generated.scene_index, int):
                raise ValueError(
                    f"Ảnh thứ {position}: scene_index phải là int, nhận {generated.scene_index!r}"
                )
            if not isinstance(caption, str):
                raise ValueError(f"Caption thứ {position} phải là chuỗi, nhận {type(caption).__name__}")
        indices = [g.scene_index for g in images]
        if indices != list(range(1, EXPECTED_PANELS + 1)):
            raise ValueError(f"scene_index của ảnh phải đúng [1, 2, 3, 4] theo thứ tự, nhận {indices}")

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