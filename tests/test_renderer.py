import unicodedata

import pytest
from PIL import Image, ImageDraw

from src.comic_renderer.renderer import (
    CaptionOverflowError,
    ComicRenderer,
    RenderConfig,
    wrap_text,
)
from src.image_generator.image_generator import MockImageGenerator
from src.image_generator.schemas import ScenePrompt

CAPTIONS = [
    "Thỏ tự tin thách rùa thi chạy.",
    "Cuộc đua bắt đầu, thỏ nhanh chóng vượt lên.",
    "Thỏ ngủ quên dưới gốc cây, rùa vẫn kiên trì tiến bước.",
    "Rùa về đích và giành chiến thắng.",
]


@pytest.fixture
def images():
    prompts = [ScenePrompt(i, "p", "n", ()) for i in range(1, 5)]
    return MockImageGenerator().generate_all(prompts)


@pytest.fixture
def renderer():
    return ComicRenderer()


def _glyph_bytes(font, ch: str) -> bytes:
    im = Image.new("L", (96, 96), 0)
    ImageDraw.Draw(im).text((8, 8), ch, font=font, fill=255)
    return im.tobytes()


def test_font_covers_vietnamese_letters(renderer):
    """Glyph thiếu sẽ bị vẽ thành ô vuông .notdef giống hệt ký tự U+10FFFF."""
    font = renderer._font(32)
    notdef = _glyph_bytes(font, "\U0010FFFF")
    missing = [
        ch
        for ch in "ăâêôơưđĂÂÊÔƠƯĐáàảãạấầẩẫậắằẳẵặếềểễệốồổỗộớờởỡợứừửữựýỳỷỹỵ"
        if _glyph_bytes(font, ch) == notdef
    ]
    assert not missing, f"Font thiếu glyph: {''.join(missing)}"


def test_wrap_respects_pixel_width(renderer):
    font = renderer._font(24)
    max_width = 300
    lines = wrap_text(CAPTIONS[2], font, max_width)
    assert len(lines) > 1
    for line in lines:
        assert font.getlength(line) <= max_width


def test_wrap_splits_overlong_word(renderer):
    font = renderer._font(24)
    lines = wrap_text("A" * 200, font, 200)
    assert len(lines) > 1
    assert all(font.getlength(line) <= 200 for line in lines)


def test_wrap_keeps_all_text(renderer):
    font = renderer._font(24)
    lines = wrap_text(CAPTIONS[2], font, 250)
    assert " ".join(lines) == CAPTIONS[2]


def test_render_gives_four_panels_and_expected_size(renderer, images):
    result = renderer.render(images, CAPTIONS)
    cfg = renderer.config
    assert len(result.panels) == 4
    pw, ph = cfg.panel_size, cfg.panel_size + cfg.caption_height
    assert result.panels[0].size == (pw, ph)
    assert result.comic.size == (
        2 * cfg.margin + 2 * pw + cfg.gap,
        2 * cfg.margin + 2 * ph + cfg.gap,
    )


def test_panels_placed_in_reading_order(renderer, images):
    result = renderer.render(images, CAPTIONS)
    cfg = renderer.config
    pw, ph = result.panels[0].size
    for i, panel in enumerate(result.panels):
        col, row = i % 2, i // 2
        x = cfg.margin + col * (pw + cfg.gap)
        y = cfg.margin + row * (ph + cfg.gap)
        assert result.comic.crop((x, y, x + pw, y + ph)).tobytes() == panel.tobytes()


def test_caption_area_is_not_blank(renderer, images):
    result = renderer.render(images, CAPTIONS)
    cfg = renderer.config
    for panel in result.panels:
        area = panel.crop((8, cfg.panel_size + 8, panel.width - 8, panel.height - 8))
        assert area.convert("L").getextrema()[0] < 128  # có pixel chữ tối


def test_nfd_and_nfc_captions_render_identically(renderer, images):
    nfd = [unicodedata.normalize("NFD", c) for c in CAPTIONS]
    a = renderer.render(images, CAPTIONS).comic.tobytes()
    b = renderer.render(images, nfd).comic.tobytes()
    assert a == b


def test_overflow_raises_instead_of_cutting_text(renderer, images):
    too_long = ["Thỏ " * 200] + CAPTIONS[1:]
    with pytest.raises(CaptionOverflowError):
        renderer.render(images, too_long)


def test_wrong_counts_raise(renderer, images):
    with pytest.raises(ValueError):
        renderer.render(images[:3], CAPTIONS[:3])
    with pytest.raises(ValueError):
        renderer.render(images, CAPTIONS[:3])


def test_unordered_scene_index_raises(renderer, images):
    with pytest.raises(ValueError):
        renderer.render(list(reversed(images)), CAPTIONS)


def test_empty_caption_raises(renderer, images):
    with pytest.raises(ValueError):
        renderer.render(images, ["  "] + CAPTIONS[1:])


def test_missing_font_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ComicRenderer(RenderConfig(font_path=tmp_path / "nope.ttf"))


def test_save_writes_five_png_files(renderer, images, tmp_path):
    result = renderer.render(images, CAPTIONS)
    paths = ComicRenderer.save(result, tmp_path)
    assert [p.name for p in paths] == [
        "panel_1.png", "panel_2.png", "panel_3.png", "panel_4.png", "comic.png",
    ]
    for p in paths:
        with Image.open(p) as im:
            assert im.format == "PNG"