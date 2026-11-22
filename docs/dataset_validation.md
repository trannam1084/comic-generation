# Dataset JSONL validator

This repository publishes a reusable validator, not dataset records. Dev/Test JSONL files are supplied locally by the project owner and are not included in this tooling PR.

## Run the validator

Pass explicit file paths so the validator cannot silently depend on a bundled dataset:

```powershell
python scripts/validate_dataset.py --dev <path-to-dev.jsonl> --test <path-to-test.jsonl>
# Or run the same CLI as a module:
python -m scripts.validate_dataset --dev <path-to-dev.jsonl> --test <path-to-test.jsonl>
```

Optional fixed-size checks can be enabled for a particular experiment:

```powershell
python scripts/validate_dataset.py --dev <path-to-dev.jsonl> --test <path-to-test.jsonl> --expected-dev 20 --expected-test 10
# Equivalent module invocation:
python -m scripts.validate_dataset --dev <path-to-dev.jsonl> --test <path-to-test.jsonl> --expected-dev 20 --expected-test 10
```

The CLI exits with code 0 when validation passes and code 1 when a record, URL, identifier, split-overlap or expected-count check fails.

## What is checked

- JSONL syntax and object-shaped records.
- Required record fields and basic value types.
- Character objects and unique character IDs within a record.
- Non-empty key-event strings.
- HTTP(S) source URL shape.
- Difficulty and numeric selection-score ranges.
- Duplicate IDs/URLs within a split and across Dev/Test.
- Optional expected record counts.

The CLI requires `--dev` and `--test`; it has no default path pointing to a project dataset. Tests create temporary synthetic JSONL fixtures and do not read private or held-out data.

## Run synthetic unit tests

Install test dependencies and run:

```powershell
python -m pip install -r requirements-test.txt
python -m pip check
python -m pytest -rs -q tests/test_dataset.py tests/test_metadata_output_safety.py
```

The full CPU suite is run by GitHub Actions for pull requests and pushes to `main`.