import json
import pandas as pd
from pathlib import Path

RESULT_DIR = Path("data/metadata/ai_review_results")

OUTPUT_FILE = Path(
    "data/metadata/ai_evaluated_stories.csv"
)

SELECTED_FILE = Path(
    "data/metadata/selected_stories.csv"
)

RESULT_DIR.mkdir(parents=True, exist_ok=True)

all_results = []

# Đọc toàn bộ JSON kết quả đánh giá
for json_file in sorted(RESULT_DIR.glob("batch_*.json")):

    print(f"Reading: {json_file.name}")

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"{json_file.name} must contain a JSON array"
        )

    all_results.extend(data)


if not all_results:
    print("No evaluation results found!")
    exit()


df = pd.DataFrame(all_results)

required_columns = [
    "id",
    "title",
    "characters_clear",
    "events_clear",
    "scene_suitable",
    "ending_clear",
    "score",
    "selected_candidate",
    "difficulty",
    "reason"
]

for col in required_columns:

    if col not in df.columns:
        raise ValueError(f"Missing column: {col}")


# Kiểm tra điểm từng tiêu chí
score_columns = [
    "characters_clear",
    "events_clear",
    "scene_suitable",
    "ending_clear"
]

for col in score_columns:

    if not df[col].between(0, 2).all():
        raise ValueError(
            f"Invalid score in column {col}"
        )


# Tính lại tổng điểm để tránh sai lệch
df["score"] = df[score_columns].sum(axis=1)


# Loại ID trùng nếu một truyện bị đánh giá nhiều lần
df = df.drop_duplicates(
    subset=["id"],
    keep="last"
)


# Lưu toàn bộ kết quả đánh giá
df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


# Lọc những truyện được chọn
selected_df = df[
    df["selected_candidate"] == True
].copy()


selected_df = selected_df.sort_values(
    by="score",
    ascending=False
)


selected_df.to_csv(
    SELECTED_FILE,
    index=False,
    encoding="utf-8-sig"
)


print("\nEvaluation completed!")
print(f"Total evaluated: {len(df)}")
print(f"Selected: {len(selected_df)}")
print(f"Rejected: {len(df) - len(selected_df)}")

print(f"\nSaved: {OUTPUT_FILE}")
print(f"Saved: {SELECTED_FILE}")