import json
from pathlib import Path

DATASET_DIR = Path("data")

FILES = [
    DATASET_DIR / "dev_cases.jsonl",
    DATASET_DIR / "test_cases.jsonl",
]

REQUIRED_FIELDS = {
    "id",
    "title",
    "summary",
    "characters",
    "key_events",
    "source",
    "source_url",
}


def validate_jsonl(file_path):
    print(f"\nChecking: {file_path}")

    if not file_path.exists():
        print("[FAIL] File does not exist")
        return False

    ids = set()
    record_count = 0
    errors = []

    with file_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                errors.append(
                    f"Line {line_number}: empty line"
                )
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as error:
                errors.append(
                    f"Line {line_number}: invalid JSON - {error}"
                )
                continue

            record_count += 1

            # Required fields
            missing_fields = REQUIRED_FIELDS - set(data.keys())

            if missing_fields:
                errors.append(
                    f"Line {line_number}: missing fields "
                    f"{missing_fields}"
                )

            # Unique ID
            story_id = data.get("id")

            if story_id in ids:
                errors.append(
                    f"Line {line_number}: duplicate ID {story_id}"
                )

            ids.add(story_id)

            # Non-empty strings
            for field in ["id", "title", "summary", "source"]:
                value = data.get(field)

                if not isinstance(value, str):
                    errors.append(
                        f"Line {line_number}: {field} must be string"
                    )
                elif not value.strip():
                    errors.append(
                        f"Line {line_number}: {field} is empty"
                    )

            # Characters
            characters = data.get("characters")

            if not isinstance(characters, list):
                errors.append(
                    f"Line {line_number}: characters must be list"
                )

            # Key events
            key_events = data.get("key_events")

            if not isinstance(key_events, list):
                errors.append(
                    f"Line {line_number}: key_events must be list"
                )
            elif len(key_events) < 2:
                errors.append(
                    f"Line {line_number}: too few key events"
                )

    if errors:
        print("[FAIL]")
        for error in errors:
            print(" -", error)
        return False

    print(f"[PASS] {record_count} records")
    return True


def main():
    results = []

    for file_path in FILES:
        results.append(validate_jsonl(file_path))

    if all(results):
        print("\nAll dataset files passed validation.")
    else:
        print("\nDataset validation failed.")


if __name__ == "__main__":
    main()