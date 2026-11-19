"""Inspect the optional raw story CSV. Importing the module performs no file I/O."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "raw" / "full_story.csv"


def main() -> int:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("Install optional dependency: python -m pip install pandas") from exc
    if not DATA_PATH.is_file():
        raise SystemExit(f"Raw CSV not found: {DATA_PATH}")
    try:
        df = pd.read_csv(DATA_PATH)
    except pd.errors.EmptyDataError:
        raise SystemExit(f"Raw CSV is empty: {DATA_PATH}")

    required = {"url", "title", "content"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Raw CSV missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        print("Raw CSV contains headers but no rows.")
        return 0

    print("===== DATASET INFORMATION =====")
    print("Rows:", len(df))
    print("Columns:", df.columns.tolist())
    print("\n===== MISSING VALUES =====")
    print(df.isnull().sum())
    print("\n===== DUPLICATES =====")
    print("URL:", df["url"].duplicated().sum())
    print("Title:", df["title"].duplicated().sum())
    print("\n===== CONTENT LENGTH =====")
    print(df["content"].fillna("").astype(str).str.len().describe())
    print("\n===== SAMPLE TITLES =====")
    for title in df["title"].head(20):
        print("-", title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
