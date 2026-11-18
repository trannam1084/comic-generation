import json
from pathlib import Path

import pytest

from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import Storyboard

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "storyboard_sample.json"


@pytest.fixture
def storyboard() -> Storyboard:
    return Storyboard.from_dict(json.loads(SAMPLE.read_text(encoding="utf-8")))


def test_returns_four_prompts_in_order(storyboard):
    prompts = PromptBuilder().build(storyboard)
    assert [p.scene_index for p in prompts] == [1, 2, 3, 4]


def test_shared_characters_injected(storyboard):
    prompts = PromptBuilder(use_shared_characters=True).build(storyboard)
    for p in prompts:
        assert "White rabbit with long ears and a red scarf" in p.prompt
        assert "Small green turtle with a brown shell" in p.prompt


def test_independent_mode_has_no_character_visuals(storyboard):
    prompts = PromptBuilder(use_shared_characters=False).build(storyboard)
    for p in prompts:
        assert "red scarf" not in p.prompt


def test_original_scene_prompt_preserved(storyboard):
    prompts = PromptBuilder().build(storyboard)
    assert "A rabbit challenges a turtle to a race on a forest path" in prompts[0].prompt


def test_unknown_character_raises(storyboard):
    bad = Storyboard.from_dict(
        {
            "summary": "x",
            "characters": [{"id": "rabbit", "visual": "r"}],
            "scenes": [
                {"index": i, "caption_vi": "c", "image_prompt_en": "p", "characters": ["fox"]}
                for i in range(1, 5)
            ],
        }
    )
    with pytest.raises(ValueError):
        PromptBuilder().build(bad)


def test_wrong_scene_count_raises(storyboard):
    short = Storyboard(summary="x", characters=storyboard.characters, scenes=storyboard.scenes[:3])
    with pytest.raises(ValueError):
        PromptBuilder().build(short)