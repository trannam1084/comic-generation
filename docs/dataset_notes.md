# Dataset Notes — Comic Generation

## 1. Mục tiêu và phạm vi

Tài liệu mô tả dataset truyện đầu vào phục vụ phát triển pipeline tạo comic: summary, character annotations, key events và các trường nguồn. Dataset hiện có **30 record**, chia **20 Dev** và **10 Test**. Đây là bộ dữ liệu thử nghiệm quy mô nhỏ; cần giữ riêng Test để đánh giá held-out và không sử dụng Test để điều chỉnh pipeline.

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

Dataset được chia thành:

| Split | Easy | Medium | Hard | Tổng |
|---|---:|---:|---:|---:|
| Dev | 12 | 3 | 5 | 20 |
| Test | 6 | 4 | 0 | 10 |
| **Tổng** | **18** | **7** | **5** | **30** |

Năm truyện Hard được chọn bổ sung vào Dev: `story_012`, `story_016`, `story_066`, `story_072`, `story_077`. Test split giữ nguyên.

Điểm `selection_score`: 25 record có điểm 8 và 5 record có điểm 7. Phân bố trên được tính trực tiếp từ hai JSONL hiện hành, không suy diễn từ toàn bộ candidate metadata hoặc bảng AI scoring rộng hơn tập 30 record.

Không dùng nội dung Test để điều chỉnh prompt, chọn tham số hoặc sửa pipeline trước held-out evaluation. Thay đổi split sau khi đánh giá bắt đầu phải được ghi nhận và tạo phiên bản dataset mới.

## 5. Metadata và human review

- `metadata/dataset_selection.csv`: theo dõi 306 ứng viên, quyết định chọn, split và trạng thái human review.
- `metadata/ai_evaluated_stories.csv`: kết quả AI-assisted scoring, không phải xác nhận của người review.
- Theo bản metadata được TV3 cập nhật, **306/306 ứng viên** đã có trạng thái review; không còn hàng `Pending`.
- Trong 30 record được chọn: **25** hàng có trạng thái `Reviewed`, **5** truyện Hard có trạng thái `Reviewed - approved for Dev`.
- Ngoài 30 record được chọn có **5** hàng `Reviewed - not selected for updated Dev`.
- `normalization_note` thể hiện nội dung có AI hỗ trợ và có thể ghi chú các điểm cần chú ý khi sử dụng.

Trạng thái trong CSV phản ánh kết quả human review do TV3 cập nhật. Validator chỉ kiểm tra tính toàn vẹn dữ liệu, không tự đánh giá chất lượng hoặc độ trung thành ngữ nghĩa của phần review.

## 6. Nguồn và quyền sử dụng

Các record giữ `source` và `source_url` để truy vết. **Theo xác nhận của TV3, việc xác minh điều kiện sử dụng các nguồn cho phạm vi dataset hiện tại đã hoàn tất.**

Cần phân biệt URL truy vết với bằng chứng về quyền sử dụng: `source_url` tự nó không phải giấy phép. Nhóm cần duy trì hồ sơ tham chiếu đến điều khoản, giấy phép hoặc xác nhận quyền tương ứng, đặc biệt khi thay đổi phạm vi sử dụng hoặc phát hành dataset ra ngoài phạm vi đã xác minh. Full-text candidate corpus và AI batch artifacts không được đưa trở lại repository nếu chưa kiểm tra riêng quyền phân phối các nội dung đó.

## 7. Human review — semantic fidelity

Validator kiểm tra cấu trúc, kiểu dữ liệu, URL hình thức, ID và số lượng; validator không thể kết luận summary, characters hay key_events có trung thành với truyện nguồn hay không.

Checklist semantic fidelity dành cho người review:

1. Summary giữ đúng nhân vật và kết cục, không thêm chi tiết không có trong nguồn.
2. Mỗi character có xuất hiện trong nguồn; description không gán tính cách/sự kiện thiếu căn cứ.
3. Mỗi key event thực sự xuất hiện và đúng thứ tự; không bỏ mất sự kiện thiết yếu.
4. Nếu rút gọn để làm comic, ghi rõ phần lược bỏ; không biến suy luận thành sự kiện nguồn.
5. Ghi trạng thái review và người/ngày review trong metadata theo quy ước nhóm.

Theo xác nhận của TV3 và trạng thái trong `dataset_selection.csv`, human review cho các ứng viên đã được đánh dấu hoàn tất. Việc validator PASS không thay thế việc duy trì audit trail hoặc rà soát lại khi record được chỉnh sửa.

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

Có thể chạy từ thư mục gốc hoặc thư mục khác. Validator kiểm tra JSONL, record object, trường bắt buộc, nested character fields, key events, difficulty, selection_score, số lượng và ID/URL trùng giữa hai split. Đây là kiểm tra integrity, không phải xác minh bản quyền hoặc tính đúng đắn ngữ nghĩa.

## 10. Giới hạn và trạng thái

- Dataset có 30 truyện, chưa đại diện đầy đủ cho mọi thể loại hoặc độ khó.
- AI scores không thay thế human review.
- Human review đã được TV3 đánh dấu hoàn tất trong metadata; nên duy trì người review, ngày review và ghi chú theo từng record nếu nhóm cần audit trail chi tiết.
- Điều kiện sử dụng nguồn cho phạm vi dataset hiện tại đã được TV3 xác minh; cần xác minh lại nếu phạm vi sử dụng hoặc hình thức phân phối thay đổi.
- Không xem dataset là benchmark đại diện cho mọi trường hợp của bài toán.

**Phụ trách:** TV3 — Dataset Preparation  
**Dự án:** Comic Generation
