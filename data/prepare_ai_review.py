"""Create prompt batches from the optional candidate corpus.
Importing this module creates no directories or files.
Optional dependency: pandas.

Existing batch_*.txt files are protected by default. Use --output-dir for a
new folder or --overwrite only when replacement is intentional.
"""
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT_DIR / "data" / "metadata" / "candidate_stories.csv"
OUTPUT_DIR = ROOT_DIR / "data" / "metadata" / "ai_review_batches"
BATCH_SIZE = 5
REQUIRED_COLUMNS = {"id", "title", "url", "content"}

try:
    from data.output_safety import atomic_write_text, ensure_outputs_available
except ModuleNotFoundError:
    from output_safety import atomic_write_text, ensure_outputs_available

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR,
                        help="Batch directory (default: data/metadata/ai_review_batches).")
    parser.add_argument("--overwrite", action="store_true",
                        help="Explicitly allow replacing target batch files that already exist.")
    args = parser.parse_args()
    output_dir = args.output_dir.expanduser().resolve()

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

    batch_count = (len(df) + BATCH_SIZE - 1) // BATCH_SIZE
    output_files = [output_dir / f"batch_{number:03d}.txt" for number in range(1, batch_count + 1)]
    try:
        # Preflight every target before writing any batch to avoid partial overwrite.
        ensure_outputs_available(output_files, overwrite=args.overwrite)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc

    for batch_number, start in enumerate(range(0, len(df), BATCH_SIZE), start=1):
        batch = df.iloc[start:start + BATCH_SIZE]
        sections = [PROMPT, "\nSTORIES TO EVALUATE\n"]
        for _, row in batch.iterrows():
            sections.append(
                f"ID: {row['id']}\nTITLE: {row['title']}\nURL: {row['url']}\n"
                f"CONTENT:\n{row['content']}\n{'-' * 50}\n"
            )
        output_file = output_files[batch_number - 1]
        try:
            atomic_write_text(output_file, "\n".join(sections),
                              encoding="utf-8", overwrite=args.overwrite)
        except FileExistsError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Created: {output_file}")
    print(f"Total stories: {len(df)}; batches: {batch_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
