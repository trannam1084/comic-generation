import pytest

from src.image_generator.ab_rubric import rated_characters


def _sb(characters, scene_chars):
    return {
        "characters": [{"id": c, "visual": f"visual of {c}"} for c in characters],
        "scenes": [
            {"index": i, "caption_vi": "x", "image_prompt_en": "y", "characters": chars}
            for i, chars in enumerate(scene_chars, start=1)
        ],
    }


def test_two_characters_in_all_scenes_are_rated():
    result = rated_characters(_sb(["a", "b"], [["a", "b"]] * 4))
    assert [(r.char_no, r.character_id, r.scenes) for r in result] == [(1, "a", (1, 2, 3, 4)), (2, "b", (1, 2, 3, 4))]


def test_character_in_one_scene_is_not_rated_and_numbers_are_dense():
    result = rated_characters(_sb(["a", "b", "c"], [["a", "b"], ["a"], ["c"], ["c", "a"]]))
    assert [(r.char_no, r.character_id) for r in result] == [(1, "a"), (2, "c")]


def test_vietnamese_ids_with_spaces_are_kept_verbatim():
    result = rated_characters(_sb(["BÀ CON", "DU KHÁCH"], [["BÀ CON"], ["DU KHÁCH", "BÀ CON"], ["DU KHÁCH"], []]))
    assert [r.character_id for r in result] == ["BÀ CON", "DU KHÁCH"]


def test_empty_scene_characters_is_allowed():
    assert rated_characters(_sb(["a"], [["a"], [], ["a"], []]))[0].scenes == (1, 3)


def test_no_eligible_character_returns_empty_list():
    assert rated_characters(_sb(["a", "b"], [["a"], ["b"], [], []])) == []


def test_duplicate_mention_in_same_scene_counts_once():
    assert rated_characters(_sb(["a"], [["a", "a"], [], [], []])) == []


def test_unknown_character_in_scene_raises():
    with pytest.raises(ValueError, match="chưa khai báo"):
        rated_characters(_sb(["a"], [["a"], ["ghost"], [], []]))


def test_duplicate_character_id_raises():
    with pytest.raises(ValueError, match="trùng"):
        rated_characters(_sb(["a", "a"], [["a"]] * 4))