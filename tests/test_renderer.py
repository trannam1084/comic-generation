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

            
# ---------- scene_index phải đúng [1, 2, 3, 4] ----------

def _with_indices(images, indices):
    from src.image_generator.schemas import GeneratedImage

    return [
        GeneratedImage(i, g.image, g.seed, g.backend, g.elapsed_sec, g.params)
        for g, i in zip(images, indices)
    ]


@pytest.mark.parametrize(
    "indices",
    [
        [1, 1, 3, 4],   # trùng
        [1, 2, 4, 4],   # trùng ở cuối
        [1, 2, 4, 5],   # thiếu 3
        [0, 1, 2, 3],   # ngoài khoảng
        [2, 3, 4, 5],   # ngoài khoảng
        [1, 2, 3, 5],   # thừa 5
        [-1, 2, 3, 4],  # âm
        [2, 1, 3, 4],   # đảo
    ],
)
def test_scene_indices_must_be_exactly_one_to_four(renderer, images, indices):
    with pytest.raises(ValueError):
        renderer.render(_with_indices(images, indices), CAPTIONS)


@pytest.mark.parametrize("bad_index", ["1", 1.0, True, None])
def test_non_integer_scene_index_raises(renderer, images, bad_index):
    bad = _with_indices(images, [1, 2, 3, 4])
    bad[0].scene_index = bad_index
    with pytest.raises(ValueError):
        renderer.render(bad, CAPTIONS)


def test_non_string_caption_raises(renderer, images):
    with pytest.raises(ValueError):
        renderer.render(images, [None] + CAPTIONS[1:])


def test_image_without_pil_image_raises(renderer, images):
    bad = _with_indices(images, [1, 2, 3, 4])
    bad[1].image = "not an image"
    with pytest.raises(ValueError):
        renderer.render(bad, CAPTIONS)


# ---------- RenderConfig hợp lệ ----------

@pytest.mark.parametrize(
    "kwargs",
    [
        {"panel_size": 0},
        {"panel_size": -5},
        {"caption_height": 0},
        {"font_size": 0},
        {"min_font_size": 0},
        {"font_size": 10, "min_font_size": 20},
        {"line_spacing": -1},
        {"gap": -1},
        {"margin": -1},
        {"text_padding": 2, "border_width": 4},       # chữ đè lên viền
        {"panel_size": 20, "text_padding": 10},        # không còn chỗ cho chữ (rộng)
        {"caption_height": 20, "text_padding": 10},    # không còn chỗ cho chữ (cao)
        {"border_width": 200, "text_padding": 200},    # viền quá lớn
        {"panel_size": 512.0},
        {"font_size": True},
        {"background": (255, 255)},
        {"text_color": (0, 0, 300)},
        {"border_color": [0, 0, 0]},
    ],
)
def test_invalid_render_config_raises(kwargs):
    with pytest.raises(ValueError):
        RenderConfig(**kwargs)


# ---------- chữ không vượt vùng hiển thị (kể cả config tùy chỉnh) ----------

def _assert_no_ink_outside_text_area(panel, cfg):
    """Mọi pixel trong dải padding (giữa viền và vùng chữ) phải còn nguyên màu nền."""
    w, h = panel.size
    top = cfg.panel_size
    b, p = cfg.border_width, cfg.text_padding
    strips = [
        (b, top, w - b, top + p),            # dải trên vùng chữ
        (b, h - p, w - b, h - b),            # dải dưới vùng chữ
        (b, top, p, h - b),                  # dải trái
        (w - p, top, w - b, h - b),          # dải phải
    ]
    for box in strips:
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        extrema = panel.crop(box).getextrema()
        assert all(lo == hi == cfg.background[i] for i, (lo, hi) in enumerate(extrema)), (
            f"Chữ tràn ra ngoài vùng hiển thị tại dải {box}"
        )


CUSTOM_CONFIGS = [
    {},
    {"panel_size": 300, "caption_height": 90, "font_size": 30, "text_padding": 10, "border_width": 3},
    {"panel_size": 256, "caption_height": 70, "font_size": 20, "min_font_size": 8, "text_padding": 6, "border_width": 2},
    {"panel_size": 512, "caption_height": 200, "font_size": 60, "text_padding": 20, "border_width": 6},
    {"panel_size": 400, "caption_height": 110, "font_size": 18, "text_padding": 4, "border_width": 4},
]


@pytest.mark.parametrize("kwargs", CUSTOM_CONFIGS)
def test_caption_never_overflows_text_area(images, kwargs):
    renderer = ComicRenderer(RenderConfig(**kwargs))
    for caption in CAPTIONS + ["Thỏ ngủ quên ở " + "gốc cây " * 4]:
        try:
            panel, _ = renderer.render_panel(images[0].image, caption)
        except CaptionOverflowError:
            continue  # báo lỗi rõ ràng cũng là hành vi hợp lệ, miễn không tràn âm thầm
        _assert_no_ink_outside_text_area(panel, renderer.config)


def test_lines_fit_inside_text_area_by_measurement(renderer):
    cfg = renderer.config
    max_width = cfg.panel_size - 2 * cfg.text_padding
    max_height = cfg.caption_height - 2 * cfg.text_padding
    for caption in CAPTIONS:
        font, lines, _ = renderer._fit_caption(caption)
        line_h = renderer._line_height(font)
        total = len(lines) * line_h + (len(lines) - 1) * cfg.line_spacing
        assert total <= max_height
        assert all(font.getlength(line) <= max_width for line in lines)


def test_text_narrower_than_one_glyph_raises_overflow(images):
    """Vùng chữ hẹp hơn một ký tự: phải báo lỗi, không vẽ chữ tràn."""
    renderer = ComicRenderer(
        RenderConfig(panel_size=30, caption_height=60, font_size=40, min_font_size=30,
                     text_padding=10, border_width=1)
    )
    with pytest.raises(CaptionOverflowError):
        renderer.render_panel(images[0].image, "WWW")