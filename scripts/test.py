"""Report Dev/Test ID overlap independently of the current working directory."""
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEV_FILE = ROOT_DIR / "data" / "dev_cases.jsonl"
TEST_FILE = ROOT_DIR / "data" / "test_cases.jsonl"


def load_ids(path: Path) -> set[str]:
    ids = set()
    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path.name}, line {line_number}: record must be object")
            story_id = record.get("id")
            if not isinstance(story_id, str) or not story_id.strip():
                raise ValueError(f"{path.name}, line {line_number}: id must be non-empty string")
            ids.add(story_id)
    return ids


def main() -> int:
    dev_ids = load_ids(DEV_FILE)
    test_ids = load_ids(TEST_FILE)
    overlap = dev_ids & test_ids
    print(f"Dev: {len(dev_ids)}")
    print(f"Test: {len(test_ids)}")
    print(f"Overlap: {sorted(overlap)}")
    print(f"Total unique: {len(dev_ids | test_ids)}")
    return 1 if overlap else 0


if __name__ == "__main__":
    raise SystemExit(main())
