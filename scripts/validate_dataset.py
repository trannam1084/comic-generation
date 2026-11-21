"""Validate caller-supplied Dev and Test JSONL files; no dataset is bundled."""
import argparse
from pathlib import Path

from scripts.dataset_validation import validate_dataset_files

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, required=True, help="Path to a Dev JSONL file.")
    parser.add_argument("--test", type=Path, required=True, help="Path to a Test JSONL file.")
    parser.add_argument("--expected-dev", type=int, default=None, help="Optional expected Dev count.")
    parser.add_argument("--expected-test", type=int, default=None, help="Optional expected Test count.")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dev_file = args.dev.expanduser().resolve()
    test_file = args.test.expanduser().resolve()
    print(f"Checking Dev: {dev_file}")
    print(f"Checking Test: {test_file}")
    errors, counts = validate_dataset_files(dev_file, test_file, expected_dev=args.expected_dev, expected_test=args.expected_test)
    print(f"\nRecords: Dev={counts['dev_records']}, Test={counts['test_records']}, Total={counts['total_records']}")
    if errors:
        print("\nDataset validation FAILED:")
        for error in errors:
            print(f" - {error}")
        return 1
    print("\nDataset validation PASSED.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
