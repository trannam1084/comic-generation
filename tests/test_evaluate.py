"""Tests for src.evaluation.evaluate."""

import json

import pytest

from src.evaluation.evaluate import (
    evaluate_records,
    load_jsonl,
    write_csv_report,
    write_json_report,
)


def make_valid_raw():
    storyboard = {
        "summary": "Một cậu bé tìm thấy chiếc chìa khóa.",
        "characters": [
            {"id": "boy", "visual": "A young boy with a blue shirt."}
        ],
        "scenes": [
            {
                "index": index,
                "caption_vi": caption,
                "image_prompt_en": f"Comic scene {index}",
                "characters": ["boy"],
            }
            for index, caption in enumerate(
                [
                    "Cậu bé đi vào khu rừng.",
                    "Cậu bé nhìn thấy chiếc chìa khóa.",
                    "Cậu bé nhặt chiếc chìa khóa lên.",
                    "Cậu bé mở chiếc rương bằng chìa khóa.",
                ],
                start=1,
            )
        ],
    }
    return json.dumps(storyboard, ensure_ascii=False)


def make_event_annotations(labels):
    """Create adjudicated event records with both annotator labels populated."""
    return [
        {
            "event_id": f"E{index}",
            "annotator_1_label": label,
            "annotator_2_label": label,
            "adjudicated_label": label,
        }
        for index, label in enumerate(labels, start=1)
    ]


def test_evaluate_records_returns_aggregate_and_case_rows():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": make_valid_raw(),
            "keyword_groups": [["cậu bé"], ["chiếc chìa khóa"]],
        },
        {
            "case_id": "dev_002",
            "raw_output": None,
            "keyword_groups": [["ông lão"]],
        },
    ]

    report = evaluate_records(records)

    assert report["planned_cases"] == 2
    assert report["completed_outputs"] == 1
    assert report["failed_or_missing_outputs"] == 1
    assert report["metrics"]["four_scene_rate"]["numerator"] == 1
    assert report["metrics"]["four_scene_rate"]["denominator"] == 2
    assert report["metrics"]["schema_valid_rate"]["numerator"] == 1
    assert report["metrics"]["schema_valid_rate"]["denominator"] == 2
    assert report["metrics"]["keyword_recall"]["numerator"] == 2
    assert report["metrics"]["keyword_recall"]["denominator"] == 3
    assert report["event_coverage_status"] == "not_available"
    assert report["metrics"]["event_coverage"]["rate"] is None
    assert len(report["case_results"]) == 2


def test_evaluate_records_calculates_event_coverage():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": make_valid_raw(),
            "keyword_groups": [["cậu bé"]],
            "event_annotations": make_event_annotations(["covered", "not_covered"]),
        },
        {
            "case_id": "dev_002",
            "raw_output": None,
            "keyword_groups": [["ông lão"]],
            "event_annotations": make_event_annotations(["uncertain"]),
        },
    ]

    report = evaluate_records(records)

    assert report["event_coverage_status"] == "available"
    event_metric = report["metrics"]["event_coverage"]
    assert event_metric["numerator"] == 1
    assert event_metric["denominator"] == 3
    assert event_metric["rate"] == pytest.approx(1 / 3)
    assert report["case_results"][0]["event_coverage_numerator"] == 1
    assert report["case_results"][0]["event_coverage_denominator"] == 2
    assert report["case_results"][1]["event_coverage_rate"] == 0.0  # uncertain is in denominator, not numerator


def test_evaluate_records_event_coverage_keeps_failed_output_in_denominator():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": None,
            "keyword_groups": [["ông lão"]],
            "event_annotations": make_event_annotations(["not_covered", "not_covered"]),
        }
    ]

    report = evaluate_records(records)

    assert report["metrics"]["event_coverage"]["numerator"] == 0
    assert report["metrics"]["event_coverage"]["denominator"] == 2
    assert report["metrics"]["event_coverage"]["rate"] == 0.0


def test_evaluate_records_rejects_partial_event_annotations():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": None,
            "keyword_groups": [],
            "event_annotations": make_event_annotations(["not_covered"]),
        },
        {
            "case_id": "dev_002",
            "raw_output": None,
            "keyword_groups": [],
        },
    ]

    with pytest.raises(ValueError, match="all planned cases or none"):
        evaluate_records(records)


def test_evaluate_records_rejects_duplicate_case_ids():
    record = {"case_id": "same", "raw_output": None, "keyword_groups": []}
    with pytest.raises(ValueError, match="duplicate case_id"):
        evaluate_records([record, record])


def test_evaluate_records_requires_raw_output():
    with pytest.raises(ValueError, match="raw_output"):
        evaluate_records([{"case_id": "dev_001", "keyword_groups": []}])


def test_evaluate_records_requires_keyword_groups():
    with pytest.raises(ValueError, match="keyword_groups"):
        evaluate_records([{"case_id": "dev_001", "raw_output": None}])


def test_evaluate_records_accepts_empty_inventory():
    report = evaluate_records([])

    assert report["planned_cases"] == 0
    assert report["metrics"]["four_scene_rate"]["rate"] is None
    assert report["metrics"]["schema_valid_rate"]["rate"] is None
    assert report["metrics"]["keyword_recall"]["rate"] is None
    assert report["metrics"]["event_coverage"]["rate"] is None
    assert report["event_coverage_status"] == "not_available"


def test_load_jsonl_reads_records_and_skips_blank_lines(tmp_path):
    source = tmp_path / "cases.jsonl"
    source.write_text(
        '{"case_id":"dev_001","raw_output":null,"keyword_groups":[]}\n\n',
        encoding="utf-8",
    )

    records = load_jsonl(source)

    assert len(records) == 1
    assert records[0]["case_id"] == "dev_001"


def test_load_jsonl_reports_bad_line_number(tmp_path):
    source = tmp_path / "cases.jsonl"
    source.write_text('{"case_id":"ok"}\n{bad json}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        load_jsonl(source)


def test_report_writers_create_json_and_csv(tmp_path):
    report = evaluate_records(
        [
            {
                "case_id": "dev_001",
                "raw_output": make_valid_raw(),
                "keyword_groups": [["cậu bé"]],
                "event_annotations": make_event_annotations(["covered"]),
            }
        ]
    )
    json_path = tmp_path / "reports" / "evaluation.json"
    csv_path = tmp_path / "reports" / "cases.csv"

    write_json_report(report, json_path)
    write_csv_report(report, csv_path)

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    saved_csv = csv_path.read_text(encoding="utf-8-sig")
    assert saved["planned_cases"] == 1
    assert "case_id" in saved_csv
    assert "event_coverage_rate" in saved_csv
