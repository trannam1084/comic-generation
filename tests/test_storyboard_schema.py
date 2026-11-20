"""Kiểm thử structural Contract v1.0 trên CPU, không tải model."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.storyboard.schema import Character, Scene, Storyboard


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "storyboard.json"


@pytest.fixture
def payload():
    """Đọc mới mỗi test để không chia sẻ dữ liệu mutable giữa các test."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_standard_fixture_preserves_structure_and_content(payload):
    original = deepcopy(payload)
    storyboard = Storyboard.model_validate(payload)
    assert len(storyboard.scenes) == 4
    assert all(isinstance(scene, Scene) for scene in storyboard.scenes)
    assert all(isinstance(character, Character) for character in storyboard.characters)
    assert [scene.index for scene in storyboard.scenes] == [1, 2, 3, 4]
    assert storyboard.model_dump() == original
    assert payload == original
    assert isinstance(storyboard.characters, list)
    assert isinstance(storyboard.scenes, list)
    assert all(isinstance(scene.characters, list) for scene in storyboard.scenes)


def test_python_and_json_round_trips(payload):
    storyboard = Storyboard.model_validate(payload)
    assert Storyboard.model_validate(storyboard.model_dump()) == storyboard
    encoded = storyboard.model_dump_json()
    assert json.loads(encoded) == payload
    assert Storyboard.model_validate_json(encoded) == storyboard


def test_json_schema_exposes_count_and_forbids_extra_fields():
    schema = Storyboard.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["scenes"]["minItems"] == 4
    assert schema["properties"]["scenes"]["maxItems"] == 4
    for name in ["Character", "Scene"]:
        assert schema["$defs"][name]["additionalProperties"] is False


def test_no_characters_when_all_references_are_empty(payload):
    payload["characters"] = []
    for scene in payload["scenes"]:
        scene["characters"] = []
    assert Storyboard.model_validate(payload).model_dump() == payload


def test_one_scene_without_characters(payload):
    payload["scenes"][1]["characters"] = []
    assert Storyboard.model_validate(payload).scenes[1].characters == []


def test_valid_text_is_not_trimmed_or_normalized(payload):
    payload["summary"] = "  " + payload["summary"] + "\n"
    payload["characters"][0]["visual"] = "  White rabbit.  "
    payload["characters"][0]["id"] = " Rabbit "
    for scene in payload["scenes"]:
        scene["characters"][0] = " Rabbit "
        scene["caption_vi"] = "\t" + scene["caption_vi"] + "  "
        scene["image_prompt_en"] = "  " + scene["image_prompt_en"] + "\n"
    assert Storyboard.model_validate(payload).model_dump() == payload


def test_character_ids_are_case_sensitive(payload):
    payload["characters"].append({"id": "Rabbit", "visual": "Another rabbit"})
    payload["scenes"][0]["characters"].append("Rabbit")
    assert Storyboard.model_validate(payload).model_dump() == payload


@pytest.mark.parametrize("bad_json", ["{", '{"summary": "x",}', "not json"])
def test_malformed_json_is_rejected(bad_json):
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate_json(bad_json)
    assert caught.value.errors()[0]["type"] == "json_invalid"


@pytest.mark.parametrize(
    "model,section,fields",
    [
        (Storyboard, "storyboard", ["summary", "characters", "scenes"]),
        (Character, "character", ["id", "visual"]),
        (Scene, "scene", ["index", "caption_vi", "image_prompt_en", "characters"]),
    ],
)
def test_all_fields_are_required(payload, model, section, fields):
    source = {
        "storyboard": payload,
        "character": payload["characters"][0],
        "scene": payload["scenes"][0],
    }[section]
    for field in fields:
        data = deepcopy(source)
        del data[field]
        with pytest.raises(ValidationError) as caught:
            model.model_validate(data)
        assert any(
            error["loc"] == (field,) and error["type"] == "missing"
            for error in caught.value.errors()
        )


@pytest.mark.parametrize("section", ["storyboard", "character", "scene"])
def test_extra_fields_are_rejected_at_every_level(payload, section):
    target, location = {
        "storyboard": (payload, ("extra",)),
        "character": (payload["characters"][0], ("characters", 0, "extra")),
        "scene": (payload["scenes"][0], ("scenes", 0, "extra")),
    }[section]
    target["extra"] = "not allowed"
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert any(
        error["loc"] == location and error["type"] == "extra_forbidden"
        for error in caught.value.errors()
    )


@pytest.mark.parametrize("count,error_type", [(3, "too_short"), (5, "too_long")])
def test_exactly_four_scenes_required(payload, count, error_type):
    payload["scenes"] = (payload["scenes"] + [deepcopy(payload["scenes"][0])])[:count]
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == ("scenes",)
    assert caught.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize("indices", [[1, 1, 3, 4], [4, 3, 2, 1], [0, 1, 2, 3], [1, 2, 3, 5]])
def test_scene_indices_must_be_exactly_one_to_four_in_order(payload, indices):
    for scene, index in zip(payload["scenes"], indices):
        scene["index"] = index
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == ("scenes",)
    assert caught.value.errors()[0]["type"] == "value_error"
    assert [scene["index"] for scene in payload["scenes"]] == indices


@pytest.mark.parametrize("index", ["1", True, False, 1.0, 1.5, None])
@pytest.mark.parametrize("json_mode", [False, True])
def test_scene_index_is_strict_integer(payload, index, json_mode):
    payload["scenes"][0]["index"] = index
    with pytest.raises(ValidationError) as caught:
        if json_mode:
            Storyboard.model_validate_json(json.dumps(payload))
        else:
            Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == ("scenes", 0, "index")
    assert caught.value.errors()[0]["type"] == "int_type"


def test_duplicate_character_id_is_rejected(payload):
    payload["characters"].append(deepcopy(payload["characters"][0]))
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == ("characters",)
    assert caught.value.errors()[0]["type"] == "value_error"
    assert len(payload["characters"]) == 3


@pytest.mark.parametrize("field", ["id", "visual"])
@pytest.mark.parametrize("value", ["", " \t\n", "\u2003"])
def test_character_text_cannot_be_blank(payload, field, value):
    payload["characters"][0][field] = value
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == ("characters", 0, field)
    assert caught.value.errors()[0]["type"] == "value_error"


@pytest.mark.parametrize("reference", ["fox", "Rabbit", " rabbit "])
def test_unknown_character_reference_is_rejected(payload, reference):
    payload["scenes"][1]["characters"] = [reference]
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    error = caught.value.errors()[0]
    assert error["loc"] == ()  # Model validator: lỗi liên field ở root.
    assert error["type"] == "value_error"
    assert "scenes[1].characters" in error["msg"]
    assert reference in error["msg"]


def test_no_character_catalog_with_references_is_rejected(payload):
    payload["characters"] = []
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["type"] == "value_error"


def test_duplicate_references_in_scene_are_rejected(payload):
    payload["scenes"][0]["characters"] = ["rabbit", "rabbit"]
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == ("scenes", 0, "characters")
    assert caught.value.errors()[0]["type"] == "value_error"
    assert payload["scenes"][0]["characters"] == ["rabbit", "rabbit"]


@pytest.mark.parametrize("field", ["caption_vi", "image_prompt_en", "summary"])
@pytest.mark.parametrize("value", ["", " \t\n", "\u2003"])
def test_story_text_cannot_be_blank(payload, field, value):
    target = payload if field == "summary" else payload["scenes"][0]
    target[field] = value
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    expected = (field,) if field == "summary" else ("scenes", 0, field)
    assert caught.value.errors()[0]["loc"] == expected
    assert caught.value.errors()[0]["type"] == "value_error"


@pytest.mark.parametrize("section", ["storyboard", "character", "scene", "reference"])
def test_string_fields_do_not_coerce_numbers(payload, section):
    if section == "storyboard":
        payload["summary"] = 123
        location = ("summary",)
    elif section == "character":
        payload["characters"][0]["id"] = 123
        location = ("characters", 0, "id")
    elif section == "scene":
        payload["scenes"][0]["caption_vi"] = 123
        location = ("scenes", 0, "caption_vi")
    else:
        payload["scenes"][0]["characters"] = [123]
        location = ("scenes", 0, "characters", 0)
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    assert caught.value.errors()[0]["loc"] == location
    assert caught.value.errors()[0]["type"] == "string_type"


@pytest.mark.parametrize("field", ["characters", "scenes", "scene_characters"])
@pytest.mark.parametrize("wrong_type", ["tuple", "dict", "string", "none"])
def test_python_collections_must_be_lists(payload, field, wrong_type):
    target = payload["scenes"][0] if field == "scene_characters" else payload
    key = "characters" if field == "scene_characters" else field
    value = {"tuple": tuple(target[key]), "dict": {}, "string": "[]", "none": None}[wrong_type]
    target[key] = value
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    location = ("scenes", 0, "characters") if field == "scene_characters" else (field,)
    assert caught.value.errors()[0]["loc"] == location
    assert caught.value.errors()[0]["type"] == "list_type"


def test_no_hard_caption_or_prompt_length_limit(payload):
    payload["scenes"][0]["caption_vi"] = "a" * 10000
    payload["scenes"][0]["image_prompt_en"] = "b" * 10000
    assert Storyboard.model_validate(payload).model_dump() == payload


def test_structural_schema_does_not_detect_changed_story_ending(payload):
    payload["scenes"][3]["caption_vi"] = "Thỏ về đích trước và chiến thắng rùa."
    payload["scenes"][3]["image_prompt_en"] = "The rabbit wins the race ahead of the turtle."
    storyboard = Storyboard.model_validate(payload)
    assert storyboard.scenes[3].caption_vi == payload["scenes"][3]["caption_vi"]
    assert storyboard.summary == payload["summary"]


def test_mutated_model_requires_revalidation(payload):
    storyboard = Storyboard.model_validate(payload)
    storyboard.scenes[0].caption_vi = ""
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(storyboard)
    assert caught.value.errors()[0]["loc"] == ("scenes", 0, "caption_vi")
