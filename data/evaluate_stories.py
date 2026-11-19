"""Optional AI-assisted candidate scoring utility.
Importing this module does not initialize an API client or access files.
Optional dependencies: pandas and openai.
"""
import json
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT_DIR / "data" / "metadata" / "candidate_stories.csv"
OUTPUT_PATH = ROOT_DIR / "data" / "metadata" / "ai_evaluated_stories.csv"
TEST_LIMIT = 3
MODEL_NAME = "YOUR_MODEL_NAME"


def build_prompt(title: str, content: str) -> str:
    return f"""
Bạn là chuyên gia đánh giá dữ liệu truyện cho dự án Vietnamese Comic Generation.
Chỉ đánh giá dựa trên nội dung truyện được cung cấp. Không tự thêm sự kiện.

Tên truyện: {title}
Nội dung: {content}

Đánh giá 4 tiêu chí từ 0 đến 2:
characters_clear, events_clear, scene_suitable, ending_clear.
score là tổng 4 tiêu chí, tối đa 8.
selected_candidate là true nếu score >= 6 và phù hợp tạo comic.
difficulty thuộc easy, medium, hard.

Trả về duy nhất JSON object có các trường:
characters_clear, events_clear, scene_suitable, ending_clear, score,
selected_candidate, difficulty, reason.
Không viết Markdown hay nội dung bên ngoài JSON.
"""


def evaluate_story(client, title: str, content: str) -> dict:
    response = client.responses.create(model=MODEL_NAME, input=build_prompt(title, content))
    result_text = response.output_text.strip()
    fence = chr(96) * 3
    if result_text.startswith(fence):
        lines = result_text.splitlines()
        result_text = "\n".join(line for line in lines if not line.strip().startswith(fence)).strip()
    result = json.loads(result_text)
    if not isinstance(result, dict):
        raise ValueError("AI response must be a JSON object")
    required = {
        "characters_clear", "events_clear", "scene_suitable", "ending_clear",
        "score", "selected_candidate", "difficulty", "reason",
    }
    missing = required - result.keys()
    if missing:
        raise ValueError(f"AI response missing fields: {', '.join(sorted(missing))}")
    return result


def main() -> int:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("Install optional dependency: python -m pip install pandas") from exc
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Install optional dependency: python -m pip install openai") from exc

    if MODEL_NAME == "YOUR_MODEL_NAME":
        raise SystemExit("Set MODEL_NAME to a model available to your API account.")
    if not INPUT_PATH.is_file():
        raise SystemExit(f"Input CSV not found: {INPUT_PATH}")
    try:
        df = pd.read_csv(INPUT_PATH)
    except pd.errors.EmptyDataError:
        raise SystemExit(f"Input CSV is empty: {INPUT_PATH}")

    required_columns = {"id", "title", "content"}
    missing = required_columns - set(df.columns)
    if missing:
        raise SystemExit(f"Input CSV missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        raise SystemExit("Input CSV contains headers but no candidate rows.")

    df = df.dropna(subset=["id", "title", "content"]).copy()
    df = df[df["content"].astype(str).str.strip().ne("")]
    if df.empty:
        raise SystemExit("No rows with non-empty id, title and content.")
    if "url" not in df.columns:
        df["url"] = ""
    if "content_length" not in df.columns:
        df["content_length"] = df["content"].astype(str).str.len()

    client = OpenAI()
    results = []
    for _, row in df.head(TEST_LIMIT).iterrows():
        print(f"Evaluating: {row['title']}")
        try:
            result = evaluate_story(client, str(row["title"]), str(row["content"]))
            result.update({
                "id": row["id"], "title": row["title"],
                "url": row["url"], "content_length": row["content_length"],
            })
        except Exception as error:
            result = {
                "id": row["id"], "title": row["title"], "url": row["url"],
                "content_length": row["content_length"],
                "characters_clear": None, "events_clear": None,
                "scene_suitable": None, "ending_clear": None, "score": None,
                "selected_candidate": None, "difficulty": None,
                "reason": f"Evaluation failed: {error}",
            }
        results.append(result)
        time.sleep(1)

    result_df = pd.DataFrame(results)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Evaluated: {len(result_df)}; saved: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
