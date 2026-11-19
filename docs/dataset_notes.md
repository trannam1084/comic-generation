# Dataset Notes — Comic Generation

## 1. Mục tiêu và phạm vi

Tài liệu mô tả dataset truyện đầu vào phục vụ phát triển pipeline tạo comic: summary, character annotations, key events và các trường nguồn. Dataset hiện có **30 record**, chia **20 Dev** và **10 Test**. Đây là bộ dữ liệu thử nghiệm nhỏ; không xem là bộ test đã chứng nhận nếu chưa hoàn tất kiểm tra nội dung và quyền sử dụng.

## 2. Cấu trúc repository hiện tại

```text
data/
├── dev_cases.jsonl
├── test_cases.jsonl
└── metadata/
    ├── ai_evaluated_stories.csv
    └── dataset_selection.csv
scripts/
├── dataset_validation.py
├── validate_dataset.py
└── test.py
tests/
└── test_dataset.py
docs/
└── dataset_notes.md
```

Full-text candidate corpus và AI batch artifacts không nằm trong PR hiện tại.

## 3. Dataset record schema

Mỗi dòng JSONL là một JSON object gồm:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | string | ID duy nhất |
| `title` | string | Tên truyện |
| `summary` | string | Tóm tắt |
| `characters` | array<object> | Mỗi nhân vật có `id`, `name`, `description` |
| `key_events` | array<string> | Sự kiện theo thứ tự |
| `source` | string | Thông tin nguồn |
| `source_url` | URL | Địa chỉ nguồn |
| `difficulty` | enum | `easy`, `medium`, `hard` |
| `selection_score` | number | Điểm chọn sơ bộ, thang 0–8 |
| `normalization_note` | string (optional) | Ghi chú chuẩn hóa và giới hạn review |

Schema này dành riêng cho dataset preparation, không thay thế Shared Storyboard Schema.

## 4. Split và difficulty

- Dev: 20 truyện.
- Test: 10 truyện.
- Tổng: 30 truyện.
- Năm truyện hard được chọn bổ sung vào Dev: `story_012`, `story_016`, `story_066`, `story_072`, `story_077`.
- Test split giữ nguyên.

Không dùng nội dung Test để điều chỉnh prompt, chọn tham số hoặc sửa pipeline trước held-out evaluation. Thay đổi split sau khi đánh giá bắt đầu phải được ghi nhận và tạo phiên bản dataset mới.

Phân bố difficulty chính thức phải được tính trực tiếp từ hai JSONL hiện hành; không suy diễn từ toàn bộ candidate metadata hoặc bảng AI scoring rộng hơn tập 30 record.

## 5. Metadata và human review

- `metadata/dataset_selection.csv`: theo dõi ứng viên, quyết định chọn, split và trạng thái human review.
- `metadata/ai_evaluated_stories.csv`: kết quả AI-assisted scoring, không phải xác nhận của người review.
- Chỉ các hàng có trạng thái review rõ ràng mới được xem là đã review. `Pending` không được tính là đã review.
- Tại thời điểm kiểm tra branch `feature/evaluation`, trong 30 record được chọn có **5** hàng `Reviewed - approved for Dev` và **25** hàng `Pending`. Ngoài 30 record được chọn có 5 hàng `Reviewed - not selected for updated Dev`.
- Ghi chú `normalization_note` thể hiện rõ nội dung có AI hỗ trợ và có thể cần đối chiếu.

## 6. Nguồn và quyền sử dụng

Các record giữ `source` và `source_url` để truy vết. URL tồn tại hoặc truy cập được không chứng minh quyền sao chép, chuẩn hóa, phân phối hay sử dụng thương mại. Trước khi public dataset, nhóm cần kiểm tra điều khoản từng nguồn, giấy phép/điều kiện sử dụng và nguồn văn bản gốc. Không đưa full-text corpus hoặc batch chứa toàn văn vào repository nếu chưa xác minh quyền phân phối.

## 7. Human review — semantic fidelity

Validator chỉ kiểm tra cấu trúc, kiểu dữ liệu, URL hình thức, ID và số lượng; không chứng minh summary, characters hay key_events trung thành với truyện nguồn. Reviewer cần kiểm tra từng record:

1. Summary giữ đúng nhân vật và kết cục, không thêm chi tiết không có trong nguồn.
2. Mỗi character có xuất hiện trong nguồn; description không gán tính cách/sự kiện thiếu căn cứ.
3. Mỗi key event thực sự xuất hiện và đúng thứ tự; không bỏ mất sự kiện thiết yếu.
4. Nếu rút gọn để làm comic, ghi rõ phần lược bỏ; không biến suy luận thành sự kiện nguồn.
5. Ghi trạng thái review và người/ngày review trong metadata theo quy ước nhóm.

Repository hiện không có bằng chứng xác nhận toàn bộ 30 record đã được đối chiếu từng dòng với văn bản nguồn. Trong lần kiểm tra gần nhất, chỉ thực hiện cross-check nguồn ở một số record (ưu tiên 5 record hard); việc đó không thay thế review độc lập cho cả dataset. Với 25 record đang Pending, không tuyên bố semantic review đã hoàn tất.

## 8. Dependencies và cách chạy

Core validator dùng Python standard library. Unit tests cần `pytest`.

```bash
python -m pip install pytest
python scripts/validate_dataset.py
python -m pytest tests/test_dataset.py -v
python -m pytest -v
```

Các script tiện ích chuẩn bị corpus là optional:

| Script | Dependencies |
|---|---|
| `data/inspect_dataset.py` | `pandas` |
| `data/prepare_ai_review.py` | `pandas` |
| `data/save_ai_review.py` | `pandas` |
| `data/evaluate_stories.py` | `pandas`, `openai`, `OPENAI_API_KEY`, model được cấp quyền |

Cài khi cần:

```bash
python -m pip install pandas openai
```

Không đưa API key vào source control. Các script tiện ích không gọi API hoặc đọc/ghi file khi import; thao tác chỉ chạy khi thực thi trực tiếp.

## 9. Validation

```bash
python scripts/validate_dataset.py
```

Có thể chạy từ thư mục gốc hoặc thư mục khác. Validator kiểm tra JSONL, record object, trường bắt buộc, nested character fields, key events, difficulty, selection_score, số lượng và ID/URL trùng giữa hai split. Đây là kiểm tra integrity, không phải xác minh bản quyền hay tính đúng đắn ngữ nghĩa.

## 10. Giới hạn và trạng thái

- Dataset chỉ có 30 truyện, chưa đại diện đầy đủ các thể loại và độ khó.
- AI scores không thay thế human review.
- Các record có ghi chú cần review và metadata Pending chưa được xác nhận.
- Quyền sử dụng từng nguồn chưa được chứng minh chỉ bằng source URL.
- Chưa xem dataset là bộ held-out evaluation chính thức cho tới khi semantic review và quyền sử dụng được xác nhận.

**Phụ trách:** TV3 — Dataset Preparation  
**Dự án:** Comic Generation
