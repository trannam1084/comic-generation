"""Batch evaluator for the current TV3 story-to-comic metrics.

Input format: UTF-8 JSONL, one planned case per line::

    {
      "case_id": "dev_001",
      "raw_output": "{... raw storyboard JSON ...}",
      "keyword_groups": [["ông lão", "lão tiều phu"], ["chiếc rìu"]],
      "event_annotations": [
        {
          "event_id": "E1",
          "annotator_1_label": "covered",
          "annotator_2_label": "covered",
          "adjudicated_label": "covered"
        }
      ]
    }

`raw_output` is null when generation failed or no output was produced. The case
still remains in the planned denominator for Four Scene Rate and Schema Valid
Rate. `event_annotations` is optional, but when used it must be supplied for
all planned cases (including failed-output cases) or for none of them.

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
    RateMetric,
    event_coverage,
    four_scene_rate,
    keyword_recall,
    schema_valid_rate,
)


_ALLOWED_EVENT_LABELS = {"covered", "not_covered", "uncertain"}


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


def _metric_dict(metric: RateMetric) -> dict[str, int | float | None]:
    """Convert RateMetric to a JSON-serializable dictionary."""
    return {
        "numerator": metric.numerator,
        "denominator": metric.denominator,
        "rate": metric.rate,
        "percentage": metric.percentage,
    }


def _event_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one normalized evaluator case to the Event Coverage API."""
    return {
        "case_id": case["case_id"],
        "events": case["event_annotations"],
    }


def evaluate_records(records: Sequence[object]) -> dict[str, Any]:
    """Evaluate all planned records and return aggregate and per-case results.

    Four Scene Rate and Schema Valid Rate use every planned case as denominator.
    Keyword Recall is micro-averaged over all supplied keyword groups.
    Event Coverage uses final human-adjudicated labels and is unavailable when
    annotations are omitted. Partial annotation coverage is rejected to avoid
    silently changing its denominator.
    """
    cases = _validate_records(records)

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
            }
        )

    return {
        "report_version": "tv3-evaluation-v1",
        "planned_cases": len(cases),
        "completed_outputs": sum(item["raw_output"] is not None for item in cases),
        "failed_or_missing_outputs": sum(item["raw_output"] is None for item in cases),
        "event_coverage_status": event_status,
        "metrics": aggregate_metrics,
        "case_results": per_case_results,
        "limitations": [
            "This evaluator currently aggregates Four Scene Rate, Schema Valid Rate, Keyword Recall, and Event Coverage.",
            "Event Coverage requires final human-adjudicated labels for every planned case.",
            "Event Order, Hallucination, and Generation Time are not integrated yet.",
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
    """Write one row per planned case, including Event Coverage when available."""
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
        description="Aggregate the currently implemented TV3 evaluation metrics."
    )
    parser.add_argument("input_jsonl", help="One planned case per JSONL line.")
    parser.add_argument(
        "--json-out", required=True, help="Destination for aggregate JSON report."
    )
    parser.add_argument(
        "--csv-out", required=True, help="Destination for per-case CSV report."
    )
    args = parser.parse_args(argv)

    records = load_jsonl(args.input_jsonl)
    report = evaluate_records(records)
    write_json_report(report, args.json_out)
    write_csv_report(report, args.csv_out)

    print(f"Evaluated planned cases: {report['planned_cases']}")
    print(f"Event Coverage status: {report['event_coverage_status']}")
    print(f"JSON report: {args.json_out}")
    print(f"CSV report: {args.csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
