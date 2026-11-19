import pandas as pd
import json
import time
from pathlib import Path
from openai import OpenAI


# ==========================================
# 1. CONFIGURATION
# ==========================================

INPUT_PATH = Path("data/metadata/candidate_stories.csv")

OUTPUT_PATH = Path("data/metadata/ai_evaluated_stories.csv")

# Chỉ thử 3 truyện trước
TEST_LIMIT = 3

# Model cần thay bằng model được cấp quyền
MODEL_NAME = "YOUR_MODEL_NAME"


# ==========================================
# 2. INITIALIZE CLIENT
# ==========================================

client = OpenAI()


# ==========================================
# 3. EVALUATION PROMPT
# ==========================================

def build_prompt(title, content):

    prompt = f"""
Bạn là chuyên gia đánh giá dữ liệu truyện
cho dự án Vietnamese Comic Generation.

Nhiệm vụ:
Đánh giá truyện dưới đây xem có phù hợp
để chuyển thành comic khoảng 4 cảnh hay không.

Chỉ đánh giá dựa trên nội dung truyện được cung cấp.
Không tự thêm sự kiện không có trong truyện.

Tên truyện:
{title}

Nội dung:
{content}

Hãy đánh giá 4 tiêu chí:

1. characters_clear:
   0 = Nhân vật không rõ
   1 = Nhân vật tương đối rõ
   2 = Nhân vật rõ ràng

2. events_clear:
   0 = Không có trình tự sự kiện rõ
   1 = Có sự kiện nhưng trình tự chưa rõ
   2 = Trình tự sự kiện rõ ràng

3. scene_suitable:
   0 = Khó chuyển thành comic
   1 = Có thể chuyển thành comic nhưng cần chỉnh sửa
   2 = Rất phù hợp để chia thành khoảng 4 cảnh

4. ending_clear:
   0 = Không có kết thúc rõ
   1 = Kết thúc tương đối rõ
   2 = Kết thúc rõ ràng

Tổng điểm:
score = tổng 4 tiêu chí, tối đa 8.

Đề xuất:
- selected_candidate = true nếu score >= 6
  và truyện phù hợp tạo comic.
- selected_candidate = false nếu không phù hợp.

Độ khó:
- easy
- medium
- hard

Trả về JSON duy nhất theo cấu trúc:

{{
    "characters_clear": 0,
    "events_clear": 0,
    "scene_suitable": 0,
    "ending_clear": 0,
    "score": 0,
    "selected_candidate": false,
    "difficulty": "easy",
    "reason": "Giải thích ngắn gọn bằng tiếng Việt"
}}

Không viết markdown.
Không viết nội dung bên ngoài JSON.
"""

    return prompt


# ==========================================
# 4. CALL AI
# ==========================================

def evaluate_story(title, content):

    prompt = build_prompt(title, content)

    response = client.responses.create(
        model=MODEL_NAME,
        input=prompt
    )

    result_text = response.output_text.strip()

    # Nếu AI trả về JSON trong markdown,
    # loại bỏ dấu markdown
    result_text = result_text.replace(
        "```json", ""
    ).replace(
        "```", ""
    ).strip()

    result = json.loads(result_text)

    return result


# ==========================================
# 5. LOAD CANDIDATE DATA
# ==========================================

print("Loading candidate stories...")

df = pd.read_csv(INPUT_PATH)

print(f"Candidate stories: {len(df)}")


# ==========================================
# 6. TEST ONLY FIRST 3 STORIES
# ==========================================

test_df = df.head(TEST_LIMIT).copy()

results = []


# ==========================================
# 7. EVALUATE STORIES
# ==========================================

for index, row in test_df.iterrows():

    print("\n================================")
    print(f"Evaluating: {row['title']}")
    print("================================")

    try:

        result = evaluate_story(
            title=row["title"],
            content=row["content"]
        )

        result["id"] = row["id"]

        result["title"] = row["title"]

        result["url"] = row["url"]

        result["content_length"] = row["content_length"]

        results.append(result)

        print("Score:", result["score"])

        print("Candidate:", result["selected_candidate"])

        print("Reason:", result["reason"])

    except Exception as error:

        print("Error:", error)

        results.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "content_length": row["content_length"],
            "characters_clear": None,
            "events_clear": None,
            "scene_suitable": None,
            "ending_clear": None,
            "score": None,
            "selected_candidate": None,
            "difficulty": None,
            "reason": f"Evaluation failed: {error}"
        })

    # Nghỉ ngắn giữa các request
    time.sleep(1)


# ==========================================
# 8. SAVE RESULTS
# ==========================================

result_df = pd.DataFrame(results)

OUTPUT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)

result_df.to_csv(
    OUTPUT_PATH,
    index=False,
    encoding="utf-8-sig"
)


# ==========================================
# 9. SUMMARY
# ==========================================

print("\n================================")
print("AI EVALUATION COMPLETED")
print("================================")

print(f"Evaluated stories: {len(result_df)}")

print(f"Output file: {OUTPUT_PATH}")

print("\nResults:")

print(
    result_df[
        [
            "title",
            "score",
            "selected_candidate",
            "difficulty"
        ]
    ].to_string(index=False)
)