"""Synthetic unit fixtures do TV1 tạo; không dùng official/held-out dataset hoặc LLM."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from src.storyboard.schema import Storyboard
from src.storyboard import validator as validator_module
from src.storyboard.validator import StoryboardValidator, ValidationReport


@pytest.fixture
def payload():
    return {
        "summary": "Một người chăm vườn và cùng bạn ngắm cây lớn lên.",
        "characters": [
            {"id": "c_alpha", "visual": "A gardener wearing a green shirt."},
            {"id": "c_beta", "visual": "A visitor wearing a blue hat."},
        ],
        "scenes": [
            {"index": 1, "caption_vi": "Người làm vườn gieo hạt.",
             "image_prompt_en": "The gardener plants a seed.", "characters": ["c_alpha"]},
            {"index": 2, "caption_vi": "Người làm vườn tưới nước.",
             "image_prompt_en": "The gardener waters the soil.", "characters": ["c_alpha"]},
            {"index": 3, "caption_vi": "Cây vươn lên trong nắng.",
             "image_prompt_en": "A plant grows in sunlight.", "characters": []},
            {"index": 4, "caption_vi": "Hai người cùng ngắm cây.",
             "image_prompt_en": "The gardener and visitor admire the plant.",
             "characters": ["c_alpha", "c_beta"]},
        ],
    }


def raw_report(payload, expected_summary=None):
    return StoryboardValidator().validate_raw(
        json.dumps(payload, ensure_ascii=False), expected_summary=expected_summary
    )


def test_valid_raw_has_no_issues_and_matches_output_gate(payload):
    raw = " \n" + json.dumps(payload, ensure_ascii=False) + "\n"
    report = StoryboardValidator().validate_raw(raw, expected_summary=payload["summary"])
    assert isinstance(report, ValidationReport)
    assert report.raw_output == raw
    assert report.json_syntax == report.structural_validity == report.summary_matching == "passed"
    assert report.issues == report.pydantic_errors == []
    assert report.production_success is True


def test_instance_does_not_claim_json_was_checked(payload):
    report = StoryboardValidator().validate(
        Storyboard.model_validate(payload), expected_summary=payload["summary"]
    )
    assert report.json_syntax == "not_checked"
    assert report.structural_validity == report.summary_matching == "passed"
    assert report.raw_output is None
    assert report.production_success is True


@pytest.mark.parametrize("method", ["validate", "validate_raw"])
def test_missing_expected_summary_is_not_checked(payload, method):
    value = Storyboard.model_validate(payload) if method == "validate" else json.dumps(payload)
    report = getattr(StoryboardValidator(), method)(value)
    assert report.summary_matching == "not_checked"
    assert report.production_success is None


@pytest.mark.parametrize("raw", ["", " ", "{", '{"summary": "x",}', "not JSON", "```json\n{}\n```"])
def test_malformed_json_and_markdown_fences(raw):
    report = StoryboardValidator().validate_raw(raw, expected_summary="Một input.")
    assert report.raw_output == raw
    assert report.json_syntax == "failed"
    assert report.structural_validity == report.summary_matching == "not_checked"
    assert report.production_success is False
    assert [(issue.code, issue.severity, issue.location) for issue in report.issues] == [
        ("INVALID_JSON", "error", ())
    ]
    assert report.pydantic_errors == []  # Không tạo lỗi Pydantic giả khi chưa gọi schema.
    assert report.issues[0].evidence["decoder"] == "pydantic_core.from_json"
    assert report.issues[0].evidence["error"]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_constants_are_rejected_without_coercion(constant):
    report = StoryboardValidator().validate_raw('{"summary": ' + constant + "}")
    assert report.issues[0].code == "INVALID_JSON"
    assert report.structural_validity == "not_checked"


def test_numeric_overflow_error_evidence_remains_json_serializable():
    raw = '{"summary":1e999}'
    report = StoryboardValidator().validate_raw(raw)
    assert report.raw_output == raw
    assert report.json_syntax == "passed"
    assert report.structural_validity == "failed"
    assert report.pydantic_errors[0]["input"] == "Infinity"
    json.dumps(report.model_dump(mode="json"), allow_nan=False)


def test_invalid_unicode_escape_uses_same_json_engine_as_shared_schema():
    raw = '{"summary":"\\ud800"}'
    report = StoryboardValidator().validate_raw(raw)
    assert report.json_syntax == "failed"
    assert report.structural_validity == "not_checked"
    assert report.raw_output == raw


@pytest.mark.parametrize("value", [None, [], 12, True, "valid JSON string"])
def test_valid_json_with_wrong_root_is_a_schema_failure(value):
    report = StoryboardValidator().validate_raw(json.dumps(value))
    assert report.json_syntax == "passed"
    assert report.structural_validity == "failed"
    assert report.summary_matching == "not_checked"
    assert report.issues[0].code == "SCHEMA_VIOLATION"


@pytest.mark.parametrize(
    "change,location,error_type",
    [
        (lambda p: p["scenes"][0].pop("caption_vi"), ("scenes", 0, "caption_vi"), "missing"),
        (lambda p: p["scenes"][0].update(index="1"), ("scenes", 0, "index"), "int_type"),
        (lambda p: p["scenes"][0].update(index=True), ("scenes", 0, "index"), "int_type"),
        (lambda p: p["scenes"][0].update(index=1.0), ("scenes", 0, "index"), "int_type"),
        (lambda p: p["scenes"].pop(), ("scenes",), "too_short"),
        (lambda p: p.update(seed=12), ("seed",), "extra_forbidden"),
        (lambda p: p["scenes"][0].update(characters=["unknown"]), (), "value_error"),
        (lambda p: p["scenes"][1].update(index=1), ("scenes",), "value_error"),
        (lambda p: p["characters"][1].update(id="c_alpha"), ("characters",), "value_error"),
    ],
)
def test_schema_error_locations_types_and_context_are_preserved(payload, change, location, error_type):
    change(payload)
    with pytest.raises(ValidationError) as caught:
        Storyboard.model_validate(payload)
    report = raw_report(payload, expected_summary=payload["summary"])
    expected_errors = json.loads(caught.value.json())
    assert report.json_syntax == "passed"
    assert report.structural_validity == "failed"
    assert report.summary_matching == "not_checked"
    assert report.production_success is False
    assert report.pydantic_errors == expected_errors
    assert (location, error_type) in [(issue.location, issue.evidence["pydantic_error"]["type"])
                                    for issue in report.issues]
    assert all(issue.severity == "error" and issue.code == "SCHEMA_VIOLATION" for issue in report.issues)
    assert all(issue.evidence["pydantic_error"] == detail
               for issue, detail in zip(report.issues, expected_errors))
    json.loads(report.model_dump_json())  # ctx.error không làm hỏng serialization.


@pytest.mark.parametrize("transform", [lambda s: s + " ", lambda s: s.upper(), lambda s: "Một truyện khác."])
def test_summary_matching_is_exact_and_does_not_overwrite(payload, transform):
    expected = transform(payload["summary"])
    report = raw_report(payload, expected_summary=expected)
    assert report.json_syntax == report.structural_validity == "passed"
    assert report.summary_matching == "failed"
    assert report.production_success is False
    assert report.issues[0].code == "SUMMARY_MISMATCH"
    assert report.issues[0].location == ("summary",)
    assert report.issues[0].evidence == {"expected": expected, "actual": payload["summary"]}
    assert json.loads(report.raw_output)["summary"] == payload["summary"]


def test_unused_character_is_warning(payload):
    payload["scenes"][-1]["characters"] = ["c_alpha"]
    report = raw_report(payload, expected_summary=payload["summary"])
    assert [(i.code, i.severity, i.location, i.evidence) for i in report.issues] == [
        ("UNUSED_CHARACTER", "warning", ("characters", 1, "id"), {"character_id": "c_beta"})
    ]
    assert report.production_success is True


def test_reference_only_in_final_scene_counts_as_used(payload):
    assert payload["scenes"][-1]["characters"] == ["c_alpha", "c_beta"]
    assert all("c_beta" not in scene["characters"] for scene in payload["scenes"][:-1])
    assert raw_report(payload).issues == []


def test_duplicate_visuals_only_warn_do_not_merge_identity(payload):
    payload["characters"][1]["visual"] = payload["characters"][0]["visual"]
    original = deepcopy(payload)
    report = raw_report(payload, expected_summary=payload["summary"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.code == "DUPLICATE_VISUAL_DESCRIPTION" and issue.severity == "warning"
    assert issue.location == ("characters", 0, "visual")
    assert issue.evidence["character_ids"] == ["c_alpha", "c_beta"]
    assert report.production_success is True
    assert payload == original
    assert len(json.loads(report.raw_output)["characters"]) == 2


@pytest.mark.parametrize("transform", [lambda s: " " + s, lambda s: s.upper(), lambda s: s + "."])
def test_visual_comparison_does_not_normalize(payload, transform):
    payload["characters"][1]["visual"] = transform(payload["characters"][0]["visual"])
    assert raw_report(payload).issues == []


def test_duplicate_caption_reports_all_positions_and_scene_indices(payload):
    payload["scenes"][1]["caption_vi"] = payload["scenes"][3]["caption_vi"] = payload["scenes"][0]["caption_vi"]
    report = raw_report(payload, expected_summary=payload["summary"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.code == "DUPLICATE_SCENE_CAPTION" and issue.severity == "warning"
    assert issue.location == ("scenes", 0, "caption_vi")
    assert issue.evidence["scene_positions"] == [0, 1, 3]
    assert issue.evidence["scene_indices"] == [1, 2, 4]
    assert report.production_success is True


def test_caption_comparison_is_exact(payload):
    payload["scenes"][1]["caption_vi"] = payload["scenes"][0]["caption_vi"] + " "
    assert raw_report(payload).issues == []


def test_empty_character_catalog_is_valid(payload):
    payload["characters"] = []
    for scene in payload["scenes"]:
        scene["characters"] = []
    assert raw_report(payload, expected_summary=payload["summary"]).production_success is True
    assert raw_report(payload).issues == []


def test_stable_issue_order_and_group_order(payload):
    payload["characters"].extend([
        {"id": "c_gamma", "visual": payload["characters"][0]["visual"]},
        {"id": "c_delta", "visual": payload["characters"][1]["visual"]},
    ])
    payload["scenes"][2]["caption_vi"] = payload["scenes"][0]["caption_vi"]
    payload["scenes"][3]["caption_vi"] = payload["scenes"][1]["caption_vi"]
    reports = [raw_report(payload, expected_summary="Tóm tắt khác.") for _ in range(3)]
    assert reports[0].model_dump_json() == reports[1].model_dump_json() == reports[2].model_dump_json()
    assert [(i.code, i.location) for i in reports[0].issues] == [
        ("SUMMARY_MISMATCH", ("summary",)),
        ("UNUSED_CHARACTER", ("characters", 2, "id")),
        ("UNUSED_CHARACTER", ("characters", 3, "id")),
        ("DUPLICATE_VISUAL_DESCRIPTION", ("characters", 0, "visual")),
        ("DUPLICATE_VISUAL_DESCRIPTION", ("characters", 1, "visual")),
        ("DUPLICATE_SCENE_CAPTION", ("scenes", 0, "caption_vi")),
        ("DUPLICATE_SCENE_CAPTION", ("scenes", 1, "caption_vi")),
    ]


def test_no_input_mutation_or_cross_call_state(payload):
    board = Storyboard.model_validate(payload)
    original = board.model_dump()
    payload_original = deepcopy(payload)
    validator = StoryboardValidator()
    assert validator.validate(board).issues == []
    assert board.model_dump() == original
    assert payload == payload_original
    board.characters[1].visual = board.characters[0].visual
    report = validator.validate(board)
    assert report.issues[0].code == "DUPLICATE_VISUAL_DESCRIPTION"
    report.issues[0].evidence["character_ids"].clear()
    assert validator.validate(board).issues[0].evidence["character_ids"] == ["c_alpha", "c_beta"]


def test_mutated_instance_is_revalidated_not_trusted(payload):
    board = Storyboard.model_validate(payload)
    board.scenes[0].index = "1"
    report = StoryboardValidator().validate(board)
    assert report.json_syntax == "not_checked"
    assert report.structural_validity == "failed"
    assert report.issues[0].location == ("scenes", 0, "index")
    assert report.pydantic_errors[0]["type"] == "int_type"
    assert board.scenes[0].index == "1"


def test_report_is_json_serializable(payload):
    report = raw_report(payload, expected_summary="Khác input.")
    encoded = report.model_dump_json()
    decoded = json.loads(encoded)
    assert decoded == json.loads(json.dumps(report.model_dump(mode="json"), allow_nan=False))
    assert decoded["issues"][0]["location"] == ["summary"]
    assert decoded["production_success"] is False
    assert decoded["semantic_validity"] == decoded["visual_language_validity"] == "not_checked"
    assert json.loads(decoded["raw_output"]) == payload


def test_one_output_parse_and_one_shared_schema_validation(payload, monkeypatch):
    raw = json.dumps(payload)
    parser = validator_module.from_json
    shared_validate = Storyboard.model_validate
    parsed_raw = []
    validated = []

    def parse_spy(value, *args, **kwargs):
        if value == raw:
            parsed_raw.append(value)
        return parser(value, *args, **kwargs)

    def validate_spy(value, *args, **kwargs):
        validated.append(value)
        return shared_validate(value, *args, **kwargs)

    monkeypatch.setattr(validator_module, "from_json", parse_spy)
    monkeypatch.setattr(Storyboard, "model_validate", validate_spy)
    report = StoryboardValidator().validate_raw(raw)
    assert report.structural_validity == "passed"
    assert len(parsed_raw) == len(validated) == 1


def test_no_schema_call_when_json_invalid(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Không validate schema khi parse thất bại.")
    monkeypatch.setattr(Storyboard, "model_validate", forbidden)
    assert StoryboardValidator().validate_raw("{").json_syntax == "failed"


@pytest.mark.parametrize("value", [None, 12, True, b"{}", {}])
def test_raw_api_refuses_non_strings(value):
    with pytest.raises(TypeError):
        StoryboardValidator().validate_raw(value)


def test_instance_api_refuses_dict_instead_of_silently_coercing(payload):
    with pytest.raises(TypeError):
        StoryboardValidator().validate(payload)


@pytest.mark.parametrize("value,error", [(12, TypeError), (False, TypeError), ("", ValueError), (" \t", ValueError)])
def test_invalid_expected_summary_is_caller_error(payload, value, error):
    with pytest.raises(error):
        raw_report(payload, expected_summary=value)


def test_semantic_and_language_failures_are_not_claimed_as_detected(payload):
    payload["characters"][0]["visual"] = "Một người mặc áo xanh chăm sóc khu vườn."
    payload["characters"][1]["visual"] = "A person named Nguyễn."
    payload["scenes"][0]["image_prompt_en"] = "A visitor throws away a key instead of planting."
    payload["scenes"][3]["caption_vi"] = "Cây đã chết và mọi người bỏ đi."
    report = raw_report(payload, expected_summary=payload["summary"])
    assert report.production_success is True  # Gate cấu trúc/summary, không phải semantic success.
    assert report.issues == []
    assert report.semantic_validity == report.visual_language_validity == "not_checked"


def test_cpu_import_and_validation_without_gpu_or_network():
    script = '''
import sys
def block(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
        raise AssertionError("Network không được sử dụng")
    if event == "import" and args[0].split(".")[0] in {"torch", "transformers", "diffusers"}:
        raise AssertionError("GPU package không được import")
sys.addaudithook(block)
from src.storyboard.validator import StoryboardValidator
report = StoryboardValidator().validate_raw("{")
assert report.json_syntax == "failed"
assert not {"torch", "transformers", "diffusers"}.intersection(sys.modules)
'''
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
