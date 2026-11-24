
import json

import pytest

from src.evaluation.metrics import (
    four_scene_rate,
    schema_valid_rate,
    keyword_recall,
    event_coverage,
)

def make_output(scene_count):
    return {
        "summary": "Synthetic test story.",
        "scenes": [
            {"index": index}
            for index in range(1, scene_count + 1)
        ],
    }


def test_four_scene_rate_accepts_exactly_four_scenes():
    result = four_scene_rate([make_output(4)])

    assert result.numerator == 1
    assert result.denominator == 1
    assert result.rate == 1.0
    assert result.percentage == 100.0

def test_four_scene_rate_works_with_json_string():
    output = json.dumps(make_output(4))

    result = four_scene_rate([output])

    assert result.numerator == 1
    assert result.rate == 1.0


def test_four_scene_rate_keeps_failed_cases_in_denominator():
    outputs = [
        make_output(4),
        make_output(3),
        None,
        "{invalid json}",
        make_output(5),
    ]

    result = four_scene_rate(outputs)

    assert result.numerator == 1
    assert result.denominator == 5
    assert result.rate == 0.2
    assert result.percentage == 20.0


def test_four_scene_rate_does_not_require_full_schema():
    # Chỉ có trường scenes; metric này không kiểm tra toàn bộ schema.
    output = {"scenes": [1, 2, 3, 4]}

    result = four_scene_rate([output])

    assert result.rate == 1.0


def test_four_scene_rate_empty_input_returns_none():
    result = four_scene_rate([])

    assert result.numerator == 0
    assert result.denominator == 0
    assert result.rate is None
    assert result.percentage is None


def test_four_scene_rate_rejects_invalid_container():
    with pytest.raises(TypeError):
        four_scene_rate("not a list of planned outputs")

def make_valid_storyboard(scene_count=4):
    return {
        "summary": "A boy finds a mysterious key.",
        "characters": [
            {
                "id": "boy",
                "visual": "A young boy wearing a blue shirt.",
            }
        ],
        "scenes": [
            {
                "index": index,
                "caption_vi": f"Cảnh truyện số {index}.",
                "image_prompt_en": f"A comic illustration of scene {index}.",
                "characters": ["boy"],
            }
            for index in range(1, scene_count + 1)
        ],
    }

def test_schema_valid_rate_accepts_valid_storyboard():
    output = json.dumps(make_valid_storyboard(), ensure_ascii=False)

    result = schema_valid_rate([output])

    assert result.numerator == 1
    assert result.denominator == 1
    assert result.rate == 1.0


def test_schema_valid_rate_rejects_invalid_json():
    result = schema_valid_rate(["{invalid json}"])

    assert result.numerator == 0
    assert result.denominator == 1
    assert result.rate == 0.0



@pytest.mark.parametrize("scene_count", [3, 5])
def test_schema_valid_rate_rejects_wrong_scene_count(scene_count):
    # make_valid_storyboard đã hỗ trợ tham số scene_count.
    output = make_valid_storyboard(scene_count)

    # Xác nhận fixture thực sự có đúng số cảnh cần kiểm tra.
    assert len(output["scenes"]) == scene_count

    raw = json.dumps(output, ensure_ascii=False)
    result = schema_valid_rate([raw])

    assert result.numerator == 0
    assert result.denominator == 1
    assert result.rate == 0.0



def test_schema_valid_rate_rejects_wrong_scene_order():
    output = make_valid_storyboard()
    output["scenes"][0]["index"] = 2

    result = schema_valid_rate([
        json.dumps(output, ensure_ascii=False)
    ])

    assert result.numerator == 0


def test_schema_valid_rate_rejects_missing_required_field():
    output = make_valid_storyboard()
    del output["scenes"][0]["caption_vi"]

    result = schema_valid_rate([
        json.dumps(output, ensure_ascii=False)
    ])

    assert result.numerator == 0


def test_schema_valid_rate_rejects_unknown_character():
    output = make_valid_storyboard()
    output["scenes"][0]["characters"] = ["unknown-character"]

    result = schema_valid_rate([
        json.dumps(output, ensure_ascii=False)
    ])

    assert result.numerator == 0


def test_schema_valid_rate_allows_warnings():
    output = make_valid_storyboard()
    output["characters"].append({
        "id": "unused",
        "visual": "An unused synthetic character."
    })

    result = schema_valid_rate([
        json.dumps(output, ensure_ascii=False)
    ])

    # UNUSED_CHARACTER is a warning, not a schema error.
    assert result.numerator == 1
    assert result.rate == 1.0


def test_schema_valid_rate_keeps_failed_cases_in_denominator():
    valid = json.dumps(make_valid_storyboard(), ensure_ascii=False)

    outputs = [
        valid,
        "{invalid}",
        None,
        "[]",
    ]

    result = schema_valid_rate(outputs)

    assert result.numerator == 1
    assert result.denominator == 4
    assert result.rate == 0.25


def test_schema_valid_rate_empty_input_returns_none():
    result = schema_valid_rate([])

    assert result.numerator == 0
    assert result.denominator == 0
    assert result.rate is None


def test_schema_valid_rate_rejects_invalid_container():
    with pytest.raises(TypeError):
        schema_valid_rate("not a sequence of outputs")

def make_keyword_output(captions, summary="Một câu chuyện mẫu"):
    return {
        "summary": summary,
        "scenes": [
            {"caption_vi": caption}
            for caption in captions
        ],
    }


def test_keyword_recall_finds_keyword():
    output = make_keyword_output(["Ông lão đi vào khu rừng."])

    result = keyword_recall(
        [output],
        [[["ông lão"]]],
    )

    assert result.numerator == 1
    assert result.denominator == 1
    assert result.rate == 1.0


def test_keyword_recall_accepts_synonym():
    output = make_keyword_output(["Lão tiều phu đi vào rừng."])

    result = keyword_recall(
        [output],
        [[["ông lão", "lão tiều phu"]]],
    )

    assert result.numerator == 1
    assert result.denominator == 1


def test_keyword_recall_is_case_insensitive():
    output = make_keyword_output(["ÔNG LÃO đi vào rừng."])

    result = keyword_recall(
        [output],
        [[["ông lão"]]],
    )

    assert result.rate == 1.0


def test_keyword_recall_does_not_search_summary():
    output = make_keyword_output(
        ["Ông lão đi vào rừng."],
        summary="Ông lão tìm thấy chiếc rìu.",
    )

    result = keyword_recall(
        [output],
        [[["chiếc rìu"]]],
    )

    assert result.numerator == 0
    assert result.denominator == 1
    assert result.rate == 0.0


def test_keyword_recall_calculates_micro_average():
    output_1 = make_keyword_output(["Ông lão cầm chiếc rìu."])
    output_2 = make_keyword_output(["Cậu bé đi học."])

    result = keyword_recall(
        [output_1, output_2],
        [
            [["ông lão"], ["chiếc rìu"]],
            [["cậu bé"]],
        ],
    )

    assert result.numerator == 3
    assert result.denominator == 3
    assert result.rate == 1.0


def test_keyword_recall_keeps_missing_output_in_denominator():
    output = make_keyword_output(["Ông lão đi vào rừng."])

    result = keyword_recall(
        [output, None],
        [
            [["ông lão"]],
            [["chiếc rìu"]],
        ],
    )

    assert result.numerator == 1
    assert result.denominator == 2
    assert result.rate == 0.5


def test_keyword_recall_empty_reference_returns_none():
    output = make_keyword_output(["Ông lão đi vào rừng."])

    result = keyword_recall([output], [[]])

    assert result.numerator == 0
    assert result.denominator == 0
    assert result.rate is None

def make_event_case(case_id, labels):
    return {
        "case_id": case_id,
        "events": [
            {
                "event_id": f"E{index}",
                "annotator_1_label": label,
                "annotator_2_label": label,
                "adjudicated_label": label,
            }
            for index, label in enumerate(labels, start=1)
        ],
    }


def test_event_coverage_all_events_covered():
    result = event_coverage([
        make_event_case("story_001", ["covered", "covered"])
    ])

    assert result.numerator == 2
    assert result.denominator == 2
    assert result.rate == 1.0


def test_event_coverage_counts_not_covered():
    result = event_coverage([
        make_event_case("story_001", ["covered", "not_covered"])
    ])

    assert result.numerator == 1
    assert result.denominator == 2
    assert result.rate == 0.5


def test_event_coverage_keeps_uncertain_in_denominator():
    result = event_coverage([
        make_event_case(
            "story_001",
            ["covered", "uncertain", "not_covered"],
        )
    ])

    assert result.numerator == 1
    assert result.denominator == 3
    assert result.rate == pytest.approx(1 / 3)


def test_event_coverage_uses_adjudicated_label():
    case = {
        "case_id": "story_001",
        "events": [
            {
                "event_id": "E1",
                "annotator_1_label": "covered",
                "annotator_2_label": "not_covered",
                "adjudicated_label": "covered",
            }
        ],
    }

    result = event_coverage([case])

    assert result.numerator == 1
    assert result.denominator == 1
    assert result.rate == 1.0


def test_event_coverage_calculates_micro_average():
    result = event_coverage([
        make_event_case("story_001", ["covered", "not_covered"]),
        make_event_case("story_002", ["covered"]),
    ])

    assert result.numerator == 2
    assert result.denominator == 3
    assert result.rate == pytest.approx(2 / 3)


def test_event_coverage_empty_input_returns_none():
    result = event_coverage([])

    assert result.numerator == 0
    assert result.denominator == 0
    assert result.rate is None


def test_event_coverage_rejects_invalid_label():
    case = make_event_case("story_001", ["unknown"])

    with pytest.raises(ValueError, match="adjudicated_label"):
        event_coverage([case])


def test_event_coverage_rejects_missing_annotator_label():
    case = make_event_case("story_001", ["covered"])
    del case["events"][0]["annotator_1_label"]

    with pytest.raises(ValueError, match="annotator_1_label"):
        event_coverage([case])



def test_event_coverage_rejects_invalid_label():
    case = make_event_case("story_001", ["covered"])

    # Chỉ cố tình làm sai nhãn cuối cùng.
    case["events"][0]["adjudicated_label"] = "unknown"

    with pytest.raises(ValueError, match="adjudicated_label"):
        event_coverage([case])
