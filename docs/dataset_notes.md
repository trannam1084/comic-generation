# Ghi chú về bộ dữ liệu truyện (Dataset Notes)

## 1. Mục tiêu

Tài liệu này ghi lại cách chuẩn bị và tổ chức bộ dữ liệu truyện dùng cho dự án **Comic Generation**. Bộ dữ liệu được dùng làm đầu vào cho các bước xử lý tiếp theo, chẳng hạn tóm tắt truyện, xác định nhân vật, trích xuất các sự kiện chính và xây dựng storyboard.

Trong giai đoạn hiện tại, bộ dữ liệu tập trung vào khoảng **30 truyện** đã được chọn sơ bộ và chuẩn hóa.

## 2. Nguồn dữ liệu

Các truyện được lấy từ tập dữ liệu ứng viên (`candidate_stories.csv`) đã được đánh giá và chọn lọc sơ bộ.

- Nguồn gốc dữ liệu: tập truyện ứng viên của dự án.
- Các trường nguồn (`source`, `source_url`) được giữ lại khi có thông tin.
- Cần kiểm tra lại nguồn, đường dẫn và quyền sử dụng dữ liệu trước khi dùng cho mục đích phát hành hoặc chia sẻ công khai.

## 3. Tiêu chí lựa chọn truyện

Truyện được đánh giá sơ bộ theo các tiêu chí:

| Tiêu chí | Điểm tối đa | Ý nghĩa |
|---|---:|---|
| Nhân vật rõ ràng | 2 | Có thể xác định nhân vật và vai trò |
| Sự kiện rõ ràng | 2 | Các sự kiện chính có thể tóm tắt |
| Phù hợp chia cảnh | 2 | Nội dung có thể chuyển thành các cảnh truyện tranh |
| Kết thúc rõ ràng | 2 | Có diễn biến/kết thúc đủ rõ để xử lý |

Tổng điểm tối đa là **8**. Việc chọn truyện ở giai đoạn này là chọn sơ bộ; cần tiếp tục rà soát thủ công trước khi đưa vào bộ dữ liệu chính thức.

## 4. Cấu trúc dữ liệu chuẩn hóa

Mỗi truyện được chuẩn hóa thành một bản ghi với các trường sau:

| Trường | Kiểu dữ liệu | Mô tả |
|---|---|---|
| `id` | string | Mã định danh duy nhất của truyện |
| `title` | string | Tên truyện |
| `summary` | string | Tóm tắt nội dung bằng tiếng Việt |
| `characters` | list | Danh sách nhân vật; mỗi nhân vật có thông tin nhận diện cơ bản |
| `key_events` | list | Các sự kiện chính theo đúng thứ tự diễn biến |
| `source` | string | Tên/nguồn dữ liệu nếu có |
| `source_url` | string | URL nguồn nếu có |
| `difficulty` | string | Mức độ xử lý dự kiến: `easy`, `medium`, `hard` |
| `selection_score` | number | Điểm đánh giá sơ bộ của truyện |

### Ví dụ cấu trúc JSON

```json
{
  "id": "story_001",
  "title": "Tên truyện",
  "summary": "Tóm tắt ngắn gọn nội dung truyện.",
  "characters": [
    {
      "id": "character_1",
      "name": "Tên nhân vật",
      "description": "Mô tả ngắn để nhận diện nhân vật."
    }
  ],
  "key_events": [
    "Sự kiện thứ nhất",
    "Sự kiện thứ hai",
    "Sự kiện thứ ba"
  ],
  "source": "Nguồn dữ liệu",
  "source_url": "",
  "difficulty": "easy",
  "selection_score": 8
}
```

> Đây là cấu trúc dữ liệu phục vụ bước chuẩn bị dataset. Cấu trúc này không thay thế hoặc tự ý thay đổi schema storyboard dùng chung của dự án.

## 5. Chia tập dữ liệu

Bộ 30 truyện được chia thành hai tập:

| Tập | Số lượng | Mục đích |
|---|---:|---|
| Dev | 20 truyện | Dùng để phát triển, thử nghiệm và điều chỉnh pipeline/prompt |
| Test | 10 truyện | Giữ riêng để đánh giá pipeline sau khi hoàn thiện |

Không sử dụng nội dung trong tập **Test** để điều chỉnh prompt trong quá trình phát triển, nhằm hạn chế việc đánh giá bị thiên lệch.

## 6. Các tệp dữ liệu

Các tệp dự kiến trong thư mục dataset:

```text
data/dataset/
├── raw/
│   └── shortlist_top30.csv
├── processed/
│   ├── all_30_normalized.csv
│   ├── all_30_normalized.json
│   └── all_30_normalized.jsonl
├── dev_cases.jsonl
└── test_cases.jsonl
```

- `raw/`: lưu dữ liệu ứng viên/đầu vào ban đầu.
- `processed/`: lưu dữ liệu đã chuẩn hóa.
- `dev_cases.jsonl`: 20 truyện phục vụ phát triển.
- `test_cases.jsonl`: 10 truyện dùng cho đánh giá riêng.

## 7. Kiểm tra dữ liệu

Trước khi sử dụng dataset, cần kiểm tra:

- Mỗi truyện có `id` duy nhất.
- Các trường bắt buộc (`id`, `title`, `summary`, `characters`, `key_events`) không bị thiếu.
- `characters` và `key_events` đúng kiểu danh sách.
- Nội dung chuỗi không rỗng hoặc chỉ chứa khoảng trắng.
- `key_events` được sắp xếp theo thứ tự diễn biến.
- Không có truyện trùng lặp ngoài ý muốn.
- ID giữa tập Dev và Test không bị trùng.
- Các thông tin `source`/`source_url` được giữ lại khi có.
- Kiểm tra thủ công tính rõ ràng của nhân vật, sự kiện và khả năng chia thành các cảnh truyện tranh.

Có thể chạy script kiểm tra dữ liệu tại:

```bash
python scripts/validate_dataset.py
```

## 8. Giới hạn hiện tại

- Việc đánh giá và lựa chọn truyện ban đầu có thể có sai sót; cần rà soát thủ công.
- Mô tả nhân vật và sự kiện có thể cần chỉnh sửa để nhất quán hơn.
- Một số truyện có thể thiếu thông tin nguồn hoặc URL.
- Dataset hiện tại là bộ dữ liệu thử nghiệm quy mô nhỏ, chưa đại diện cho mọi thể loại truyện hoặc mọi trường hợp phức tạp.
- Chưa xem đây là bộ dữ liệu cuối cùng cho đánh giá chính thức nếu chưa có sự xác nhận của nhóm.

## 9. Quy trình cập nhật

Khi bổ sung hoặc chỉnh sửa truyện:

1. Cập nhật bản dữ liệu nguồn.
2. Chuẩn hóa bản ghi theo cấu trúc thống nhất.
3. Kiểm tra các trường bắt buộc và ID.
4. Xác định truyện thuộc Dev hay Test.
5. Không chuyển truyện qua lại giữa Dev và Test tùy tiện sau khi đã bắt đầu đánh giá.
6. Chạy script validation.
7. Rà soát thủ công các thay đổi.
8. Ghi lại thay đổi trong commit hoặc pull request.

---

**Phụ trách:** TV3 – Dataset Preparation  
**Dự án:** Comic Generation  
**Trạng thái:** Bộ dữ liệu chuẩn hóa sơ bộ, chờ rà soát và xác nhận của nhóm.
