"""Explicit offline CLI; chỉ đọc batch đã chọn, không discover dataset/inference outputs."""

import argparse
from pathlib import Path

from .contracts import EvaluationInput
from .integrity import json_bytes, parse_record, sha256_bytes, write_session
from .structural import evaluate_pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline B0/B1 evaluation; no inference.")
    parser.add_argument("--input", required=True, type=Path, help="Explicit frozen evaluation batch JSON.")
    parser.add_argument("--expected-sha256", required=True, help="Independently frozen batch byte hash.")
    parser.add_argument("--output-root", type=Path,
                        default=Path(__file__).resolve().parents[2] / "outputs" / "evaluations")
    args = parser.parse_args()
    payload = args.input.read_bytes()
    if sha256_bytes(payload) != args.expected_sha256:
        parser.error("Input batch SHA-256 mismatch.")
    try:
        batch = parse_record(payload, EvaluationInput)
        aggregate = evaluate_pairs(batch.plan, batch.pairs, batch.costs)
    except (ValueError, TypeError):
        parser.error("Invalid evaluation batch or records; no output written.")
    session = write_session(args.output_root, {
        "aggregates.json": json_bytes(aggregate),
        "plan.json": json_bytes(batch.plan),
        "input_reference.json": json_bytes({"input_sha256": sha256_bytes(payload)}),
    })
    print(session)


if __name__ == "__main__":
    main()
