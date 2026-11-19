import json
from pathlib import Path

import pytest

from src.image_generator.image_generator import BaseImageGenerator, MockImageGenerator
from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import Storyboard

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "storyboard_sample.json"


@pytest.fixture
def prompts():
    sb = Storyboard.from_dict(json.loads(SAMPLE.read_text(encoding="utf-8")))
    return PromptBuilder().build(sb)


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


def test_images_differ_between_scenes(prompts):
    results = MockImageGenerator().generate_all(prompts)
    assert results[0].image.tobytes() != results[1].image.tobytes()


def test_wrong_prompt_count_raises(prompts):
    with pytest.raises(ValueError):
        MockImageGenerator().generate_all(prompts[:3])


def test_invalid_size_raises():
    with pytest.raises(ValueError):
        MockImageGenerator(width=0)


def test_mock_is_substitutable_for_base():
    assert isinstance(MockImageGenerator(), BaseImageGenerator)