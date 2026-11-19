"""Create prompt batches from the optional candidate corpus.
Importing this module creates no directories or files.
"""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT_DIR / "data" / "metadata" / "candidate_stories.csv"
OUTPUT_DIR = ROOT_DIR / "data" / "metadata" / "ai_review_batches"
BATCH_SIZE = 5
REQUIRED_COLUMNS = {"id", "title", "url", "content"}

PROMPT = """
Bạn là người đánh giá Dataset cho dự án Vietnamese Comic Generation.
Đánh giá từng truyện theo 4 tiêu chí từ 0 đến 2:
characters_clear, events_clear, scene_suitable, ending_clear.
score là tổng điểm (tối đa 8); difficulty thuộc easy, medium, hard.
Không bịa thêm sự kiện; dựa trên nội dung truyện, không chỉ tên truyện.
Trả về JSON array hợp lệ, không Markdown. Mỗi object phải có id, title,
characters_clear, events_clear, scene_suitable, ending_clear, score,
selected_candidate, difficulty và reason.
"""


def main() -> int:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("Install optional dependency: python -m pip install pandas") from exc
    if not INPUT_FILE.is_file():
        raise SystemExit(f"Candidate CSV not found: {INPUT_FILE}")
    try:
        df = pd.read_csv(INPUT_FILE)
    except pd.errors.EmptyDataError:
        raise SystemExit(f"Candidate CSV is empty: {INPUT_FILE}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise SystemExit(f"Candidate CSV missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        raise SystemExit("Candidate CSV contains headers but no rows.")
    df = df.dropna(subset=["id", "title", "url", "content"])
    df = df[df["content"].astype(str).str.strip().ne("")]
    if df.empty:
        raise SystemExit("No complete candidate rows with non-empty content.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_count = (len(df) + BATCH_SIZE - 1) // BATCH_SIZE
    for number, start in enumerate(range(0, len(df), BATCH_SIZE), start=1):
        batch = df.iloc[start:start + BATCH_SIZE]
        sections = [PROMPT, "\nSTORIES TO EVALUATE\n"]
        for _, row in batch.iterrows():
            sections.append(
                f"ID: {row['id']}\nTITLE: {row['title']}\nURL: {row['url']}\n"
                f"CONTENT:\n{row['content']}\n{'-' * 50}\n"
            )
        output_file = OUTPUT_DIR / f"batch_{number:03d}.txt"
        output_file.write_text("\n".join(sections), encoding="utf-8")
        print(f"Created: {output_file}")
    print(f"Total stories: {len(df)}; batches: {batch_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
