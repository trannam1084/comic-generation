"""Merge AI review JSON into metadata CSV files.
Importing this module performs no file-system operations.
Optional dependency: pandas.
"""
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT_DIR / "data" / "metadata" / "ai_review_results"
OUTPUT_FILE = ROOT_DIR / "data" / "metadata" / "ai_evaluated_stories.csv"
SELECTED_FILE = ROOT_DIR / "data" / "metadata" / "selected_stories.csv"

REQUIRED_COLUMNS = [
    "id", "title", "characters_clear", "events_clear", "scene_suitable",
    "ending_clear", "score", "selected_candidate", "difficulty", "reason",
]
SCORE_COLUMNS = ["characters_clear", "events_clear", "scene_suitable", "ending_clear"]


def main() -> int:
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
        if values.isna().any() or not values.between(0, 2).all():
            raise SystemExit(f"Invalid or missing score in column {column}")
        df[column] = values.astype(int)

    df["score"] = df[SCORE_COLUMNS].sum(axis=1)
    if not df["difficulty"].isin(["easy", "medium", "hard"]).all():
        raise SystemExit("difficulty must be easy, medium or hard")
    if not df["selected_candidate"].isin([True, False]).all():
        raise SystemExit("selected_candidate must contain booleans")

    df = df.drop_duplicates(subset=["id"], keep="last")
    selected_df = df[df["selected_candidate"] == True].copy()
    selected_df = selected_df.sort_values(by="score", ascending=False)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    selected_df.to_csv(SELECTED_FILE, index=False, encoding="utf-8-sig")
    print(f"Evaluation completed. Total: {len(df)}; selected: {len(selected_df)}")
    print(f"Saved: {OUTPUT_FILE}")
    print(f"Saved: {SELECTED_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
