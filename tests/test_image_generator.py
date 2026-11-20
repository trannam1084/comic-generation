import pytest

from src.image_generator.image_generator import (
    BaseImageGenerator,
    MockImageGenerator,
    MIN_IMAGE_SIZE,
)
from src.image_generator.schemas import ScenePrompt


def make_prompts(indices):
    return [ScenePrompt(i, f"prompt {n}", "neg", ("rabbit",)) for n, i in enumerate(indices)]


@pytest.fixture
def prompts():
    return make_prompts([1, 2, 3, 4])


class SpyGenerator(MockImageGenerator):
    """Đếm số lần generate để chứng minh lỗi đầu vào được bắt trước khi sinh ảnh."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def generate(self, prompt, seed):
        self.calls += 1
        return super().generate(prompt, seed)


def test_mock_returns_four_images_in_order(prompts):
    results = MockImageGenerator().generate_all(prompts)
    assert [r.scene_index for r in results] == [1, 2, 3, 4]


def test_mock_image_size_and_backend(prompts):
    results = MockImageGenerator(width=256, height=320).generate_all(prompts)
    for r in results:
        assert r.image.size == (256, 320)
        assert r.backend == "mock"


def test_seed_is_recorded_and_deterministic(prompts):
    gen = MockImageGenerator()
    a = [r.seed for r in gen.generate_all(prompts, base_seed=100)]
    b = [r.seed for r in gen.generate_all(prompts, base_seed=100)]
    assert a == b == [101, 102, 103, 104]


def test_same_scene_same_seed_regardless_of_prompt_text(prompts):
    """Ablation: cùng scene ở hai cấu hình prompt khác nhau phải dùng cùng seed."""
    other = [ScenePrompt(p.scene_index, "khác hẳn", "neg", ()) for p in prompts]
    gen = MockImageGenerator()
    assert [r.seed for r in gen.generate_all(prompts)] == [r.seed for r in gen.generate_all(other)]


def test_images_differ_between_scenes(prompts):
    results = MockImageGenerator().generate_all(prompts)
    assert results[0].image.tobytes() != results[1].image.tobytes()


def test_wrong_prompt_count_raises(prompts):
    with pytest.raises(ValueError):
        MockImageGenerator().generate_all(prompts[:3])
    with pytest.raises(ValueError):
        MockImageGenerator().generate_all(prompts + make_prompts([5]))


@pytest.mark.parametrize(
    "indices",
    [
        [1, 1, 3, 4],   # trùng
        [1, 2, 3, 3],   # trùng ở cuối
        [4, 3, 2, 1],   # đảo ngược
        [2, 1, 3, 4],   # đảo một cặp
        [0, 1, 2, 3],   # ngoài khoảng (bắt đầu từ 0)
        [2, 3, 4, 5],   # ngoài khoảng (bắt đầu từ 2)
        [1, 2, 3, 5],   # thiếu 4, thừa 5
        [-1, 2, 3, 4],  # âm
    ],
)
def test_invalid_scene_indices_raise_before_generating(indices):
    gen = SpyGenerator()
    with pytest.raises(ValueError):
        gen.generate_all(make_prompts(indices))
    assert gen.calls == 0


@pytest.mark.parametrize("bad_index", ["1", 1.0, True, None])
def test_non_integer_scene_index_raises(bad_index):
    prompts = make_prompts([1, 2, 3, 4])
    prompts[0] = ScenePrompt(bad_index, "p", "n", ())
    gen = SpyGenerator()
    with pytest.raises(ValueError):
        gen.generate_all(prompts)
    assert gen.calls == 0


@pytest.mark.parametrize("bad_prompt", ["", "   ", None, 123])
def test_malformed_prompt_text_raises(bad_prompt):
    prompts = make_prompts([1, 2, 3, 4])
    prompts[2] = ScenePrompt(3, bad_prompt, "n", ())
    gen = SpyGenerator()
    with pytest.raises(ValueError):
        gen.generate_all(prompts)
    assert gen.calls == 0


def test_malformed_negative_prompt_raises():
    prompts = make_prompts([1, 2, 3, 4])
    prompts[1] = ScenePrompt(2, "p", None, ())
    with pytest.raises(ValueError):
        MockImageGenerator().generate_all(prompts)


@pytest.mark.parametrize(
    "bad_item", [{"scene_index": 1, "prompt": "p"}, None, "scene 1", 1]
)
def test_non_scene_prompt_item_raises(bad_item):
    prompts = make_prompts([1, 2, 3, 4])
    prompts[3] = bad_item
    gen = SpyGenerator()
    with pytest.raises(ValueError):
        gen.generate_all(prompts)
    assert gen.calls == 0


@pytest.mark.parametrize("not_a_list", [None, "abc", 4, {1: "a"}])
def test_prompts_container_must_be_list_or_tuple(not_a_list):
    with pytest.raises(ValueError):
        MockImageGenerator().generate_all(not_a_list)


@pytest.mark.parametrize("bad_seed", [1.5, "42", None, True])
def test_invalid_base_seed_raises(prompts, bad_seed):
    with pytest.raises(ValueError):
        MockImageGenerator().generate_all(prompts, base_seed=bad_seed)


@pytest.mark.parametrize(
    "width,height",
    [
        (0, 512), (512, 0), (-1, 512),
        (MIN_IMAGE_SIZE - 1, 512), (512, MIN_IMAGE_SIZE - 1),
        (512.0, 512), ("512", 512), (True, 512),
    ],
)
def test_invalid_size_raises(width, height):
    with pytest.raises(ValueError):
        MockImageGenerator(width=width, height=height)


def test_minimum_size_still_renders(prompts):
    results = MockImageGenerator(width=MIN_IMAGE_SIZE, height=MIN_IMAGE_SIZE).generate_all(prompts)
    assert all(r.image.size == (MIN_IMAGE_SIZE, MIN_IMAGE_SIZE) for r in results)


def test_mock_is_substitutable_for_base():
    assert isinstance(MockImageGenerator(), BaseImageGenerator)