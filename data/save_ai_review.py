"""Merge AI review JSON into optional metadata CSV files.
Importing this module performs no directory or file operations.
Optional dependency: pandas.

Existing metadata CSVs are protected by default. Use alternative output paths
or pass --overwrite explicitly after taking a backup.
"""
import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT_DIR / "data" / "metadata" / "ai_review_results"
OUTPUT_FILE = ROOT_DIR / "data" / "metadata" / "ai_evaluated_stories.csv"
SELECTED_FILE = ROOT_DIR / "data" / "metadata" / "selected_stories.csv"

try:
    from data.output_safety import atomic_write_text, ensure_outputs_available
except ModuleNotFoundError:
    from output_safety import atomic_write_text, ensure_outputs_available

REQUIRED_COLUMNS = [
    "id", "title", "characters_clear", "events_clear", "scene_suitable",
    "ending_clear", "score", "selected_candidate", "difficulty", "reason",
]
SCORE_COLUMNS = ["characters_clear", "events_clear", "scene_suitable", "ending_clear"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE,
                        help="Full evaluation CSV output path.")
    parser.add_argument("--selected-output", type=Path, default=SELECTED_FILE,
                        help="Selected-only CSV output path.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Explicitly allow replacing existing output files.")
    args = parser.parse_args()
    output_file = args.output.expanduser().resolve()
    selected_file = args.selected_output.expanduser().resolve()
    if output_file == selected_file:
        raise SystemExit("--output and --selected-output must be different paths.")
    try:
        # Protect the existing curated metadata before reading or transforming results.
        ensure_outputs_available([output_file, selected_file], overwrite=args.overwrite)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("Install optional dependency: python -m pip install pandas") from exc

    if not RESULT_DIR.is_dir():
        raise SystemExit(f"AI review results directory not found: {RESULT_DIR}")
    json_files = sorted(RESULT_DIR.glob("batch_*.json"))
    if not json_files:
        raise SystemExit(f"No batch_*.json result files found in {RESULT_DIR}")

    all_results = []
    for json_file in json_files:
        print(f"Reading: {json_file.name}")
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot read {json_file.name}: {exc}") from exc
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise SystemExit(f"{json_file.name} must contain a JSON array of objects")
        all_results.extend(data)

    if not all_results:
        raise SystemExit("Review result files contain no records.")
    df = pd.DataFrame(all_results)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit(f"Review results missing columns: {', '.join(sorted(missing))}")

    text_columns = ["id", "title", "difficulty", "reason"]
    if df[text_columns].isna().any().any():
        raise SystemExit("Review results contain missing required metadata.")
    for column in text_columns:
        if df[column].astype(str).str.strip().eq("").any():
            raise SystemExit(f"Review results contain blank values in {column}.")

    for column in SCORE_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")
        invalid_scores = (
            values.isna()
            | ~values.between(0, 2)
            | values.mod(1).ne(0)
        )
        if invalid_scores.any():
            bad_values = df.loc[invalid_scores, column].tolist()
            raise SystemExit(
                f"Invalid score(s) in column {column}: {bad_values}. "
                "Expected integer values 0, 1 or 2; fractional values "
                "are not rounded or truncated."
            )
        # Conversion is safe only after exact integer values are validated.
        df[column] = values.astype(int)

    df["score"] = df[SCORE_COLUMNS].sum(axis=1)
    if not df["difficulty"].isin(["easy", "medium", "hard"]).all():
        raise SystemExit("difficulty must be easy, medium or hard")
    if not df["selected_candidate"].isin([True, False]).all():
        raise SystemExit("selected_candidate must contain booleans")

    duplicate_mask = df["id"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate_rows = df.loc[duplicate_mask]
        identical_ids = []
        conflicting_ids = []
        for story_id, group in duplicate_rows.groupby("id", sort=False):
            unique_payloads = group.drop(columns=["id"]).drop_duplicates()
            target = identical_ids if len(unique_payloads) == 1 else conflicting_ids
            target.append(str(story_id))

        details = []
        if identical_ids:
            details.append("identical duplicate rows: " + ", ".join(identical_ids))
        if conflicting_ids:
            details.append("conflicting rows: " + ", ".join(conflicting_ids))
        raise SystemExit(
            "Duplicate story IDs detected; refusing to silently drop or overwrite "
            "records. " + "; ".join(details)
        )

    selected_df = df[df["selected_candidate"] == True].copy()
    selected_df = selected_df.sort_values(by="score", ascending=False)

    # Re-check targets immediately before writes. Both files were preflighted above.
    try:
        ensure_outputs_available([output_file, selected_file], overwrite=args.overwrite)
        atomic_write_text(output_file, df.to_csv(index=False),
                          encoding="utf-8-sig", overwrite=args.overwrite)
        atomic_write_text(selected_file, selected_df.to_csv(index=False),
                          encoding="utf-8-sig", overwrite=args.overwrite)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Evaluation completed. Total: {len(df)}; selected: {len(selected_df)}")
    print(f"Saved: {output_file}")
    print(f"Saved: {selected_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
