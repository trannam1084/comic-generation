import pandas as pd
from pathlib import Path

INPUT_FILE = Path("data/metadata/candidate_stories.csv")
OUTPUT_DIR = Path("data/metadata/ai_review_batches")

BATCH_SIZE = 5

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(INPUT_FILE)

required_columns = ["id", "title", "url", "content"]

for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"Missing column: {col}")

df = df.dropna(subset=["content"])
df = df.reset_index(drop=True)

prompt = """
Bạn là người đánh giá Dataset cho dự án Vietnamese Comic Generation.

Hãy đánh giá từng truyện để xác định mức độ phù hợp
khi chuyển thành comic khoảng 4 cảnh.

Đánh giá 4 tiêu chí, mỗi tiêu chí từ 0 đến 2:

1. characters_clear
0: Không rõ nhân vật
1: Nhân vật tương đối rõ
2: Nhân vật rõ ràng

2. events_clear
0: Sự kiện không có trình tự rõ
1: Trình tự tương đối rõ
2: Trình tự sự kiện rõ ràng

3. scene_suitable
0: Không phù hợp tạo comic
1: Có thể tạo comic nhưng cần chỉnh sửa
2: Rất phù hợp để chia khoảng 4 cảnh

4. ending_clear
0: Không có kết thúc rõ
1: Kết thúc tương đối rõ
2: Kết thúc rõ ràng

Tổng điểm score = tổng 4 tiêu chí, tối đa 8.

selected_candidate:
- true: Nếu score >= 6 và phù hợp tạo comic
- false: Nếu không phù hợp

difficulty:
- easy
- medium
- hard

Không bịa thêm sự kiện.
Không đánh giá chỉ dựa trên tên truyện.
Đánh giá dựa trên nội dung được cung cấp.

Trả về JSON array hợp lệ, không Markdown.

Mỗi truyện:

{
  "id": "story_001",
  "title": "...",
  "characters_clear": 0,
  "events_clear": 0,
  "scene_suitable": 0,
  "ending_clear": 0,
  "score": 0,
  "selected_candidate": false,
  "difficulty": "easy",
  "reason": "..."
}
"""

for start in range(0, len(df), BATCH_SIZE):

    batch = df.iloc[start:start + BATCH_SIZE]

    batch_number = start // BATCH_SIZE + 1

    output_file = OUTPUT_DIR / f"batch_{batch_number:03d}.txt"

    content = prompt + "\n\n"
    content += "=" * 50
    content += "\nSTORIES TO EVALUATE\n"
    content += "=" * 50 + "\n\n"

    for _, row in batch.iterrows():

        content += f"""
ID: {row['id']}
TITLE: {row['title']}
URL: {row['url']}

CONTENT:
{row['content']}

{'-' * 50}

"""

    output_file.write_text(content, encoding="utf-8")

    print(f"Created: {output_file}")

print("\nDone!")
print(f"Total stories: {len(df)}")
print(f"Batch size: {BATCH_SIZE}")
print(f"Total batches: {(len(df) + BATCH_SIZE - 1) // BATCH_SIZE}")