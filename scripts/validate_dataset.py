"""Run dataset validation from any current working directory."""

from pathlib import Path
import sys

try:
    from scripts.dataset_validation import validate_dataset_files
except ModuleNotFoundError:
    # Also supports direct execution when scripts/ is the import root.
    from dataset_validation import validate_dataset_files


ROOT_DIR = Path(__file__).resolve().parents[1]
DEV_FILE = ROOT_DIR / "data" / "dev_cases.jsonl"
TEST_FILE = ROOT_DIR / "data" / "test_cases.jsonl"


def main() -> int:
    print(f"Checking: {DEV_FILE}")
    print(f"Checking: {TEST_FILE}")

    errors, counts = validate_dataset_files(DEV_FILE, TEST_FILE)

    print(
        f"\nRecords: Dev={counts['dev_records']}, "
        f"Test={counts['test_records']}, Total={counts['total_records']}"
    )

    if errors:
        print("\nDataset validation FAILED:")
        for error in errors:
            print(f" - {error}")
        return 1

    print("\nDataset validation PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
