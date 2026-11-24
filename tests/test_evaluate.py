"""Tests for src.evaluation.evaluate."""

import json

import pytest

from src.evaluation.evaluate import (
    evaluate_records,
    load_event_inventory_csv,
    validate_event_inventory,
    load_jsonl,
    main,
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
    """Create Event Coverage annotations without Event Order scene labels."""
    return [
        {
            "event_id": f"E{index}",
            "annotator_1_label": label,
            "annotator_2_label": label,
            "adjudicated_label": label,
        }
        for index, label in enumerate(labels, start=1)
    ]


def make_event_order_annotations(scene_indices, labels=None):
    """Create complete Event Coverage + Event Order annotation records."""
    if labels is None:
        labels = ["covered"] * len(scene_indices)
    annotations = []
    for index, (scene_index, label) in enumerate(
        zip(scene_indices, labels, strict=True), start=1
    ):
        observed_index = scene_index if label == "covered" else None
        annotations.append(
            {
                "event_id": f"E{index}",
                "reference_order": index,
                "annotator_1_label": label,
                "annotator_1_scene_index": observed_index,
                "annotator_2_label": label,
                "annotator_2_scene_index": observed_index,
                "adjudicated_label": label,
                "adjudicated_scene_index": observed_index,
            }
        )
    return annotations


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
    assert report["event_order_status"] == "not_available"
    assert report["metrics"]["event_order"]["accuracy"] is None
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
    assert report["case_results"][1]["event_coverage_rate"] == 0.0
    assert report["event_order_status"] == "not_available"


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


def test_evaluate_records_calculates_event_order_pair_metrics():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": make_valid_raw(),
            "keyword_groups": [["cậu bé"]],
            # Event order: 1 -> scene 1, 2 -> scene 3, 3 -> scene 2.
            # Thus two of the three reference pairs are correctly ordered.
            "event_annotations": make_event_order_annotations([1, 3, 2]),
        }
    ]

    report = evaluate_records(records)

    assert report["event_order_status"] == "available"
    metric = report["metrics"]["event_order"]
    assert metric["correct_pairs"] == 2
    assert metric["evaluable_pairs"] == 3
    assert metric["total_reference_pairs"] == 3
    assert metric["same_scene_pairs"] == 0
    assert metric["accuracy"] == pytest.approx(2 / 3)
    assert metric["pair_coverage"] == pytest.approx(1.0)
    assert report["case_results"][0]["event_order_accuracy"] == pytest.approx(2 / 3)


def test_evaluate_records_event_order_excludes_uncovered_event_pairs():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": None,
            "keyword_groups": [],
            "event_annotations": make_event_order_annotations(
                [1, None, 3], labels=["covered", "not_covered", "covered"]
            ),
        }
    ]

    report = evaluate_records(records)
    metric = report["metrics"]["event_order"]

    assert metric["correct_pairs"] == 1
    assert metric["evaluable_pairs"] == 1
    assert metric["total_reference_pairs"] == 3
    assert metric["accuracy"] == pytest.approx(1.0)
    assert metric["pair_coverage"] == pytest.approx(1 / 3)


def test_evaluate_records_event_order_counts_same_scene_pairs_separately():
    records = [
        {
            "case_id": "dev_001",
            "raw_output": make_valid_raw(),
            "keyword_groups": [],
            "event_annotations": make_event_order_annotations([1, 2, 2, 4]),
        }
    ]

    report = evaluate_records(records)
    metric = report["metrics"]["event_order"]

    assert metric["total_reference_pairs"] == 6
    assert metric["same_scene_pairs"] == 1
    assert metric["evaluable_pairs"] == 5
    assert metric["correct_pairs"] == 5
    assert metric["accuracy"] == pytest.approx(1.0)
    assert metric["pair_coverage"] == pytest.approx(5 / 6)


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


def test_evaluate_records_rejects_partial_event_order_annotations():
    events = make_event_order_annotations([1, 2])
    del events[1]["adjudicated_scene_index"]
    records = [
        {
            "case_id": "dev_001",
            "raw_output": None,
            "keyword_groups": [],
            "event_annotations": events,
        }
    ]

    with pytest.raises(ValueError, match="Event Order fields must be supplied together"):
        evaluate_records(records)


def test_evaluate_records_rejects_incomplete_event_order_inventory():
    events = make_event_order_annotations([1, 2])
    events[1] = {
        "event_id": "E2",
        "annotator_1_label": "covered",
        "annotator_2_label": "covered",
        "adjudicated_label": "covered",
    }
    records = [
        {
            "case_id": "dev_001",
            "raw_output": None,
            "keyword_groups": [],
            "event_annotations": events,
        }
    ]

    with pytest.raises(ValueError, match="all reference events or none"):
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
    assert report["metrics"]["event_order"]["accuracy"] is None
    assert report["event_coverage_status"] == "not_available"
    assert report["event_order_status"] == "not_available"


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
                "event_annotations": make_event_order_annotations([1, 2]),
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
    assert saved["metrics"]["event_order"]["evaluable_pairs"] == 1
    assert "case_id" in saved_csv
    assert "event_coverage_rate" in saved_csv
    assert "event_order_accuracy" in saved_csv

def test_load_event_inventory_csv_uses_only_team_approved_rows(tmp_path):
    source = tmp_path / "approved_events.csv"
    source.write_text(
        "split,id,event_no,aligned_key_event,event_reference_status,team_confirmation_status\n"
        'Dev,story_001,3,"Sự kiện thứ ba",approved_reference,team_confirmed\n'
        'Dev,story_001,2,"Sự kiện bị loại",excluded_from_event_reference,excluded_from_reference\n'
        'Dev,story_001,1,"Sự kiện thứ nhất",approved_reference,team_confirmed\n'
        'Test,story_002,1,"Test event",approved_reference,team_confirmed\n',
        encoding="utf-8",
    )

    inventory = load_event_inventory_csv(source, split="Dev")

    assert inventory == {
        "story_001": [
            "story_001_event_01",
            "story_001_event_03",
        ]
    }


def test_load_event_inventory_csv_rejects_unconfirmed_approval(tmp_path):
    source = tmp_path / "bad_events.csv"
    source.write_text(
        "split,id,event_no,aligned_key_event,event_reference_status,team_confirmation_status\n"
        'Dev,story_001,1,"Sự kiện",approved_reference,pending\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="inconsistent or unapproved"):
        load_event_inventory_csv(source)


def test_validate_event_inventory_rejects_missing_case():
    records = [
        {"case_id": "story_001", "raw_output": None, "keyword_groups": [],
         "event_annotations": make_event_annotations(["covered"])}
    ]

    with pytest.raises(ValueError, match="case inventory mismatch"):
        validate_event_inventory(
            records,
            {"story_001": ["E1"], "story_002": ["E1"]},
        )


@pytest.mark.parametrize(
    ("annotations", "message"),
    [
        (["covered"], "missing events"),
        (["covered", "covered", "covered"], "extra events"),
    ],
)
def test_validate_event_inventory_rejects_event_set_mismatch(annotations, message):
    records = [
        {"case_id": "story_001", "raw_output": None, "keyword_groups": [],
         "event_annotations": make_event_annotations(annotations)}
    ]

    with pytest.raises(ValueError, match=message):
        validate_event_inventory(records, {"story_001": ["E1", "E2"]})


def test_validate_event_inventory_rejects_duplicate_event_ids():
    records = [
        {"case_id": "story_001", "raw_output": None, "keyword_groups": [],
         "event_annotations": [
             {"event_id": "E1", "annotator_1_label": "covered",
              "annotator_2_label": "covered", "adjudicated_label": "covered"},
             {"event_id": "E1", "annotator_1_label": "covered",
              "annotator_2_label": "covered", "adjudicated_label": "covered"},
         ]}
    ]

    with pytest.raises(ValueError, match="duplicate event IDs"):
        validate_event_inventory(records, {"story_001": ["E1", "E2"]})


def test_evaluate_records_reports_inventory_validation():
    records = [
        {"case_id": "story_001", "raw_output": None, "keyword_groups": [],
         "event_annotations": make_event_annotations(["covered", "uncertain"])}
    ]

    report = evaluate_records(
        records,
        event_inventory={"story_001": ["E1", "E2"]},
    )

    assert report["event_inventory_status"] == "validated"
    assert report["event_inventory_cases"] == 1
    assert report["event_inventory_events"] == 2
    assert report["metrics"]["event_coverage"]["numerator"] == 1
    assert report["metrics"]["event_coverage"]["denominator"] == 2

def test_cli_can_enforce_approved_event_inventory(tmp_path):
    input_path = tmp_path / "annotations.jsonl"
    inventory_path = tmp_path / "approved_events.csv"
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "cases.csv"

    cli_annotations = make_event_annotations(["covered", "not_covered"])
    for event_no, event in enumerate(cli_annotations, start=1):
        event["event_id"] = f"story_001_event_{event_no:02d}"

    record = {
        "case_id": "story_001",
        "raw_output": None,
        "keyword_groups": [],
        "event_annotations": cli_annotations,
    }
    input_path.write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    inventory_path.write_text(
        "split,id,event_no,aligned_key_event,event_reference_status,team_confirmation_status\n"
        'Dev,story_001,1,"Sự kiện thứ nhất",approved_reference,team_confirmed\n'
        'Dev,story_001,2,"Sự kiện thứ hai",approved_reference,team_confirmed\n',
        encoding="utf-8",
    )

    exit_code = main([
        str(input_path),
        "--json-out", str(json_path),
        "--csv-out", str(csv_path),
        "--event-inventory-csv", str(inventory_path),
    ])

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["event_inventory_status"] == "validated"
    assert report["event_inventory_events"] == 2
    assert csv_path.is_file()
