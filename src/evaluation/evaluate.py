"""Batch evaluator for TV3 story-to-comic metrics.

Input format: UTF-8 JSONL, one planned case per line::

    {
      "case_id": "dev_001",
      "raw_output": "{... raw storyboard JSON ...}",
      "keyword_groups": [["ông lão", "lão tiều phu"], ["chiếc rìu"]],
      "event_annotations": [
        {
          "event_id": "E1",
          "reference_order": 1,
          "annotator_1_label": "covered",
          "annotator_1_scene_index": 1,
          "annotator_2_label": "covered",
          "annotator_2_scene_index": 1,
          "adjudicated_label": "covered",
          "adjudicated_scene_index": 1
        }
      ]
    }

`raw_output` is null when generation failed or no output was produced. The case
still remains in the planned denominator for Four Scene Rate and Schema Valid
Rate. `event_annotations` is optional, but when used it must be supplied for
all planned cases (including failed-output cases) or for none of them.

Event Coverage needs adjudicated event labels. Event Order additionally needs
`reference_order` and scene-index labels for both annotators and the adjudicated
result. Event Order fields must be populated for every reference event or for
none of them; partial order annotations are rejected.

This module only evaluates supplied records. It does not call the LLM, image
backend, ComicPipeline, or human annotators.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.evaluation.metrics import (
    EventOrderMetric,
    RateMetric,
    event_coverage,
    event_order,
    four_scene_rate,
    keyword_recall,
    schema_valid_rate,
)


_EVENT_ORDER_FIELDS = (
    "reference_order",
    "annotator_1_scene_index",
    "annotator_2_scene_index",
    "adjudicated_scene_index",
)


def _is_non_string_sequence(value: object) -> bool:
    """Return whether value is a sequence but not a text/bytes object."""
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _validate_records(records: Sequence[object]) -> list[dict[str, Any]]:
    """Validate JSONL case records and normalize optional annotation fields."""
    if not _is_non_string_sequence(records):
        raise TypeError("records must be a sequence of case mappings")

    normalized: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()

    for line_number, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise TypeError(f"record #{line_number} must be a JSON object")

        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(
                f"record #{line_number}: case_id must be a non-empty string"
            )
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)

        if "raw_output" not in record:
            raise ValueError(f"{case_id}: missing required field raw_output")
        raw_output = record["raw_output"]
        if raw_output is not None and not isinstance(raw_output, str):
            raise TypeError(f"{case_id}: raw_output must be a string or null")

        if "keyword_groups" not in record:
            raise ValueError(f"{case_id}: missing required field keyword_groups")
        keyword_groups = record["keyword_groups"]
        if not _is_non_string_sequence(keyword_groups):
            raise TypeError(f"{case_id}: keyword_groups must be a list")

        event_annotations = record.get("event_annotations")
        if event_annotations is not None:
            if not _is_non_string_sequence(event_annotations):
                raise TypeError(f"{case_id}: event_annotations must be a list or null")
            if len(event_annotations) == 0:
                raise ValueError(
                    f"{case_id}: event_annotations cannot be empty when supplied"
                )

        normalized.append(
            {
                "case_id": case_id,
                "raw_output": raw_output,
                "keyword_groups": keyword_groups,
                "event_annotations": event_annotations,
            }
        )

    return normalized


def load_event_inventory_csv(
    path: str | Path, *, split: str = "Dev"
) -> dict[str, list[str]]:
    """Load team-approved event references from the alignment CSV."""
    if split not in {"Dev", "Test"}:
        raise ValueError("split must be 'Dev' or 'Test'")

    input_path = Path(path)
    required_columns = {
        "split", "id", "event_no", "aligned_key_event",
        "event_reference_status", "team_confirmation_status",
    }
    inventory: dict[str, list[tuple[int, str]]] = {}

    with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{input_path}: CSV is empty or has no header")
        missing = required_columns - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"{input_path}: missing required columns {sorted(missing)}"
            )

        for line_number, row in enumerate(reader, start=2):
            if row.get("split") != split:
                continue
            case_id = row.get("id")
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(f"{input_path}, line {line_number}: empty story id")

            reference_status = row.get("event_reference_status")
            confirmation_status = row.get("team_confirmation_status")
            if (
                reference_status == "excluded_from_event_reference"
                and confirmation_status == "excluded_from_reference"
            ):
                continue
            if not (
                reference_status == "approved_reference"
                and confirmation_status == "team_confirmed"
            ):
                raise ValueError(
                    f"{input_path}, line {line_number}: inconsistent or "
                    "unapproved event reference status"
                )

            event_no_text = row.get("event_no")
            if (
                not isinstance(event_no_text, str)
                or not event_no_text.isdigit()
                or int(event_no_text) < 1
            ):
                raise ValueError(
                    f"{input_path}, line {line_number}: event_no must be a positive integer"
                )
            aligned_event = row.get("aligned_key_event")
            if not isinstance(aligned_event, str) or not aligned_event.strip():
                raise ValueError(
                    f"{input_path}, line {line_number}: approved event has no aligned_key_event"
                )

            event_no = int(event_no_text)
            events = inventory.setdefault(case_id, [])
            if any(existing_no == event_no for existing_no, _ in events):
                raise ValueError(
                    f"{input_path}, line {line_number}: duplicate event_no "
                    f"{event_no} for {case_id}"
                )
            events.append((event_no, f"E{event_no}"))

    if not inventory:
        raise ValueError(f"{input_path}: no approved events found for split {split}")
    return {
        case_id: [event_id for _, event_id in sorted(events)]
        for case_id, events in inventory.items()
    }


def validate_event_inventory(
    records: Sequence[Mapping[str, Any]],
    event_inventory: Mapping[str, Sequence[str]],
) -> None:
    """Require exact case and event-ID parity with the approved inventory."""
    if not isinstance(event_inventory, Mapping) or not event_inventory:
        raise ValueError("event_inventory must be a non-empty mapping")
    if any(not isinstance(case_id, str) or not case_id.strip() for case_id in event_inventory):
        raise ValueError("event_inventory case IDs must be non-empty strings")

    record_ids = [record["case_id"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("records contain duplicate case_id values")

    expected_case_ids = set(event_inventory)
    actual_case_ids = set(record_ids)
    missing_cases = sorted(expected_case_ids - actual_case_ids)
    extra_cases = sorted(actual_case_ids - expected_case_ids)
    if missing_cases or extra_cases:
        raise ValueError(
            "case inventory mismatch; "
            f"missing cases={missing_cases}, extra cases={extra_cases}"
        )

    records_by_id = {record["case_id"]: record for record in records}
    for case_id in sorted(expected_case_ids):
        raw_expected_ids = event_inventory[case_id]
        if isinstance(raw_expected_ids, (str, bytes, bytearray)) or not isinstance(raw_expected_ids, Sequence):
            raise ValueError(f"{case_id}: reference event IDs must be a sequence")
        expected_ids = list(raw_expected_ids)
        if not expected_ids or any(
            not isinstance(event_id, str) or not event_id.strip()
            for event_id in expected_ids
        ):
            raise ValueError(f"{case_id}: reference inventory has invalid event IDs")
        if len(expected_ids) != len(set(expected_ids)):
            raise ValueError(f"{case_id}: reference inventory has duplicate event IDs")

        annotations = records_by_id[case_id]["event_annotations"]
        if annotations is None:
            raise ValueError(
                f"{case_id}: event_annotations are required when event inventory is enabled"
            )

        actual_ids: list[str] = []
        for event in annotations:
            if not isinstance(event, Mapping):
                raise TypeError(f"{case_id}: each event annotation must be a mapping")
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError(f"{case_id}: each event needs a non-empty event_id")
            actual_ids.append(event_id)

        if len(actual_ids) != len(set(actual_ids)):
            raise ValueError(f"{case_id}: duplicate event IDs in annotations")
        missing_events = sorted(set(expected_ids) - set(actual_ids))
        extra_events = sorted(set(actual_ids) - set(expected_ids))
        if missing_events or extra_events:
            raise ValueError(
                f"{case_id}: event inventory mismatch; "
                f"missing events={missing_events}, extra events={extra_events}"
            )


def _metric_dict(metric: RateMetric) -> dict[str, int | float | None]:
    """Convert RateMetric to a JSON-serializable dictionary."""
    return {
        "numerator": metric.numerator,
        "denominator": metric.denominator,
        "rate": metric.rate,
        "percentage": metric.percentage,
    }


def _event_order_metric_dict(
    metric: EventOrderMetric | None,
) -> dict[str, int | float | None]:
    """Convert EventOrderMetric to a JSON-serializable dictionary."""
    if metric is None:
        return {
            "correct_pairs": 0,
            "evaluable_pairs": 0,
            "total_reference_pairs": 0,
            "same_scene_pairs": 0,
            "accuracy": None,
            "accuracy_percentage": None,
            "pair_coverage": None,
            "pair_coverage_percentage": None,
        }

    return {
        "correct_pairs": metric.correct_pairs,
        "evaluable_pairs": metric.evaluable_pairs,
        "total_reference_pairs": metric.total_reference_pairs,
        "same_scene_pairs": metric.same_scene_pairs,
        "accuracy": metric.accuracy,
        "accuracy_percentage": metric.accuracy_percentage,
        "pair_coverage": metric.pair_coverage,
        "pair_coverage_percentage": metric.pair_coverage_percentage,
    }


def _event_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one normalized evaluator case to an event metric API."""
    return {
        "case_id": case["case_id"],
        "events": case["event_annotations"],
    }


def _event_order_annotations_available(cases: Sequence[Mapping[str, Any]]) -> bool:
    """Return True only when all annotated events have the full order schema.

    Event Coverage annotations may exist without Event Order fields. If Event
    Order fields are started, they must be complete for every reference event
    across every planned case so that the pair denominator cannot silently vary.
    """
    field_presence: list[bool] = []

    for case in cases:
        annotations = case["event_annotations"]
        if annotations is None:
            return False

        for event in annotations:
            if not isinstance(event, Mapping):
                # event_coverage() will raise the more specific type error.
                continue

            present = [field in event for field in _EVENT_ORDER_FIELDS]
            if any(present) and not all(present):
                missing = [
                    field for field, has_value in zip(_EVENT_ORDER_FIELDS, present)
                    if not has_value
                ]
                raise ValueError(
                    f"{case['case_id']}: Event Order fields must be supplied "
                    f"together for each event; missing {missing}"
                )
            field_presence.append(all(present))

    if not field_presence or not any(field_presence):
        return False
    if not all(field_presence):
        raise ValueError(
            "Event Order annotations must be provided for all reference events or none"
        )
    return True


def evaluate_records(
    records: Sequence[object],
    *,
    event_inventory: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Evaluate all planned records and return aggregate and per-case results.

    Four Scene Rate and Schema Valid Rate use every planned case as denominator.
    Keyword Recall is micro-averaged over all supplied keyword groups.
    Event Coverage uses final human-adjudicated labels and is unavailable when
    annotations are omitted. Event Order is calculated only when complete
    scene-index annotations are supplied for every reference event.
    """
    cases = _validate_records(records)
    if event_inventory is not None:
        validate_event_inventory(cases, event_inventory)

    outputs = [item["raw_output"] for item in cases]
    keyword_groups_by_case = [item["keyword_groups"] for item in cases]

    four_scene = four_scene_rate(outputs)
    schema_valid = schema_valid_rate(outputs)
    keywords = keyword_recall(outputs, keyword_groups_by_case)

    annotation_supplied = [item["event_annotations"] is not None for item in cases]
    if any(annotation_supplied) and not all(annotation_supplied):
        raise ValueError(
            "event_annotations must be provided for all planned cases or none"
        )

    if cases and all(annotation_supplied):
        event_metric = event_coverage([_event_case(item) for item in cases])
        event_status = "available"
    else:
        event_metric = None
        event_status = "not_available"

    order_available = (
        _event_order_annotations_available(cases)
        if event_status == "available"
        else False
    )
    if order_available:
        order_metric = event_order([_event_case(item) for item in cases])
        order_status = "available"
    else:
        order_metric = None
        order_status = "not_available"

    aggregate_metrics: dict[str, dict[str, int | float | None]] = {
        "four_scene_rate": _metric_dict(four_scene),
        "schema_valid_rate": _metric_dict(schema_valid),
        "keyword_recall": _metric_dict(keywords),
        "event_coverage": (
            _metric_dict(event_metric)
            if event_metric is not None
            else {
                "numerator": 0,
                "denominator": 0,
                "rate": None,
                "percentage": None,
            }
        ),
        "event_order": _event_order_metric_dict(order_metric),
    }

    per_case_results: list[dict[str, Any]] = []
    for item in cases:
        case_output = item["raw_output"]
        case_scene_metric = four_scene_rate([case_output])
        case_schema_metric = schema_valid_rate([case_output])
        case_keyword_metric = keyword_recall(
            [case_output], [item["keyword_groups"]]
        )

        if item["event_annotations"] is None:
            event_numerator: int | None = None
            event_denominator: int | None = None
            event_rate: float | None = None
        else:
            case_event_metric = event_coverage([_event_case(item)])
            event_numerator = case_event_metric.numerator
            event_denominator = case_event_metric.denominator
            event_rate = case_event_metric.rate

        if not order_available:
            case_order_values = {
                "event_order_correct_pairs": None,
                "event_order_evaluable_pairs": None,
                "event_order_total_reference_pairs": None,
                "event_order_same_scene_pairs": None,
                "event_order_accuracy": None,
                "event_order_pair_coverage": None,
            }
        else:
            case_order_metric = event_order([_event_case(item)])
            case_order_values = {
                "event_order_correct_pairs": case_order_metric.correct_pairs,
                "event_order_evaluable_pairs": case_order_metric.evaluable_pairs,
                "event_order_total_reference_pairs": case_order_metric.total_reference_pairs,
                "event_order_same_scene_pairs": case_order_metric.same_scene_pairs,
                "event_order_accuracy": case_order_metric.accuracy,
                "event_order_pair_coverage": case_order_metric.pair_coverage,
            }

        per_case_results.append(
            {
                "case_id": item["case_id"],
                "four_scene_pass": case_scene_metric.numerator == 1,
                "schema_valid_pass": case_schema_metric.numerator == 1,
                "keyword_recall_numerator": case_keyword_metric.numerator,
                "keyword_recall_denominator": case_keyword_metric.denominator,
                "keyword_recall_rate": case_keyword_metric.rate,
                "event_coverage_numerator": event_numerator,
                "event_coverage_denominator": event_denominator,
                "event_coverage_rate": event_rate,
                **case_order_values,
            }
        )

    return {
        "report_version": "tv3-evaluation-v2",
        "planned_cases": len(cases),
        "completed_outputs": sum(item["raw_output"] is not None for item in cases),
        "failed_or_missing_outputs": sum(item["raw_output"] is None for item in cases),
        "event_coverage_status": event_status,
        "event_order_status": order_status,
        "event_inventory_status": "validated" if event_inventory is not None else "not_checked",
        "event_inventory_cases": len(event_inventory) if event_inventory is not None else None,
        "event_inventory_events": (
            sum(len(ids) for ids in event_inventory.values())
            if event_inventory is not None
            else None
        ),
        "metrics": aggregate_metrics,
        "case_results": per_case_results,
        "limitations": [
            "This evaluator aggregates Four Scene Rate, Schema Valid Rate, Keyword Recall, Event Coverage, and Event Order.",
            "Event Coverage requires final human-adjudicated labels for every planned case.",
            "Event Order additionally requires reference_order and scene-index labels from both annotators and the adjudicated result for every reference event.",
            "Hallucination and Generation Time are not integrated yet.",
            "The evaluator does not run the LLM, ComicPipeline, image backend, or human annotators.",
        ],
    }


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read UTF-8 JSONL and include line number in malformed-JSON errors."""
    input_path = Path(path)
    records: list[dict[str, Any]] = []

    with input_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {input_path}: {exc.msg}"
                ) from exc
            records.append(record)

    return records


def write_json_report(report: Mapping[str, Any], path: str | Path) -> None:
    """Write an UTF-8 JSON report; output destination is explicit."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv_report(report: Mapping[str, Any], path: str | Path) -> None:
    """Write one row per planned case, including Event Coverage and Event Order."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "case_id",
        "four_scene_pass",
        "schema_valid_pass",
        "keyword_recall_numerator",
        "keyword_recall_denominator",
        "keyword_recall_rate",
        "event_coverage_numerator",
        "event_coverage_denominator",
        "event_coverage_rate",
        "event_order_correct_pairs",
        "event_order_evaluable_pairs",
        "event_order_total_reference_pairs",
        "event_order_same_scene_pairs",
        "event_order_accuracy",
        "event_order_pair_coverage",
    ]

    case_results = report.get("case_results")
    if not isinstance(case_results, list):
        raise ValueError("report must contain case_results as a list")

    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(case_results)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: python -m src.evaluation.evaluate input.jsonl --json-out ... --csv-out ..."""
    parser = argparse.ArgumentParser(
        description="Aggregate TV3 structural, keyword, Event Coverage, and Event Order metrics."
    )
    parser.add_argument("input_jsonl", help="One planned case per JSONL line.")
    parser.add_argument(
        "--json-out", required=True, help="Destination for aggregate JSON report."
    )
    parser.add_argument(
        "--csv-out", required=True, help="Destination for per-case CSV report."
    )
    parser.add_argument(
        "--event-inventory-csv",
        help="Optional team-approved event inventory CSV; enables exact case/event parity checks.",
    )
    parser.add_argument(
        "--event-inventory-split", choices=("Dev", "Test"), default="Dev",
        help="Split selected from --event-inventory-csv (default: Dev).",
    )
    args = parser.parse_args(argv)

    records = load_jsonl(args.input_jsonl)
    inventory = (
        load_event_inventory_csv(args.event_inventory_csv, split=args.event_inventory_split)
        if args.event_inventory_csv
        else None
    )
    report = evaluate_records(records, event_inventory=inventory)
    write_json_report(report, args.json_out)
    write_csv_report(report, args.csv_out)

    print(f"Evaluated planned cases: {report['planned_cases']}")
    print(f"Event Coverage status: {report['event_coverage_status']}")
    print(f"Event Order status: {report['event_order_status']}")
    print(f"JSON report: {args.json_out}")
    print(f"CSV report: {args.csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
