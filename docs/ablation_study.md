# Kế hoạch Ablation Study — TV3

**Trạng thái:** protocol draft; chưa có kết quả ablation chính thức trong tài liệu này.

## 1. Mục tiêu

Đo đóng góp của cơ chế deterministic Storyboard Validation & Repair trong pipeline
sinh storyboard 4 cảnh. Ablation chính là so sánh paired giữa:

- **B0 — Baseline:** cùng cấu hình story generation và deterministic validation,
  không gọi Repair (repair budget = 0).
- **B1 — Validation + Repair:** dùng cùng initial generation output với B0,
  bật Repair theo policy đã được nhóm thống nhất (tối đa hai repair attempts).

B0/B1 là hai điều kiện xử lý trên cùng initial raw output, không phải hai lần
generation độc lập. Vì vậy không được mô tả đây là so sánh hai lần sampling.

## 2. Dataset và split

- Dùng Dev20 để phát triển protocol, kiểm tra evaluator và phân tích lỗi.
- Giữ Test10 held-out; không dùng để chỉnh prompt, repair policy, rubric hoặc metric.
- Giữ nguyên planned case inventory; không loại case vì generation/repair thất bại.
- Ghim source commit, model revision, prompt/system-message hashes, policy hash,
  input bytes hash và cấu hình decoding cho mỗi run.
- Event Coverage/Event Order chỉ tính khi từng variant có annotation đúng variant
  và khớp approved Event ID inventory. Không tái sử dụng nhãn của B0 cho B1 hoặc ngược lại.

## 3. Metrics

| Metric | Mục đích | Denominator |
|---|---|---|
| Four Scene Rate | Sinh đúng 4 scenes | Toàn bộ planned cases |
| Schema Valid Rate | JSON + Shared Storyboard Schema hợp lệ | Toàn bộ planned cases |
| Event Coverage | Key events được thể hiện | Toàn bộ approved reference events |
| Event Order Accuracy | Thứ tự các cặp event đánh giá được | Chỉ evaluable pairs |
| Event Order Pair Coverage | Mức bao phủ của Event Order | Tất cả reference event pairs |
| Repair Success | Initial invalid được Repair thành accepted | Eligible initial failures; báo rõ định nghĩa denominator |
| Generation/Repair latency | Chi phí thời gian | Chỉ các lượt có phép đo thực tế |

Không gộp Event Order Accuracy với Pair Coverage. Không báo accuracy đơn độc khi
pair coverage thấp. null/N/A biểu thị không có denominator hoặc thiếu phép đo;
không đổi thành 0.

Hallucination, image-caption alignment và character consistency không nằm trong
ablation B0/B1 hiện tại vì evaluator này chưa tích hợp các phép đo đó. Chỉ bổ sung
khi có rubric, nguồn evidence, output metadata và quy trình annotation được duyệt.

## 4. Quy trình thực nghiệm

1. Freeze Dev case inventory, summaries, model revision, generation prompt và repair policy.
2. Sinh initial raw output một lần cho mỗi case; lưu raw bytes/hash và run metadata.
3. Tạo B0 từ initial raw output với repair budget 0.
4. Tạo B1 từ đúng initial raw output đó với repair budget tối đa 2.
5. Lưu toàn bộ attempt history, validation reports, accepted raw/storyboard, failure
   category và measurements có nguồn gốc.
6. Chạy structural evaluator riêng cho từng variant.
7. Human review semantic cho B0 và B1 độc lập, không để reviewer thấy nhãn của variant kia
   trước khi hoàn tất annotation của mình.
8. Chỉ tính Event Coverage/Event Order sau khi mapping Event ID và adjudication được
   xác nhận cho đúng variant.
9. Báo paired case table, aggregate rates, failure categories và missingness.
10. Lưu hashes/config/artifact references; không sửa raw outputs hoặc manifest gốc.

## 5. Phân tích và cách diễn giải

- Báo numerator, denominator, percentage và số case fail cho từng metric.
- Báo paired transition: invalid→valid, valid→valid, valid→invalid, invalid→invalid.
- Repair Success không thay thế planned Structural Acceptance Rate.
- Phân tích các case repair làm thay đổi nội dung, summary mismatch, retry exhaustion,
  malformed JSON và schema errors.
- Với Dev20, ưu tiên descriptive statistics và case-level evidence; không suy rộng
  thống kê cho mọi truyện tiếng Việt.
- Nếu B0/B1 dùng cùng initial raw, không gọi khác biệt output là hiệu quả của sampling.
- AI Review A/B nếu cùng model qua hai pass không phải hai annotator độc lập; không
  tính inter-annotator agreement từ hai pass này.

## 6. Điều kiện để chạy GPU

Chưa chạy GPU trong task chuẩn bị protocol. Trước mỗi lần chạy cần xác nhận riêng:
notebook/script hash, source commit, model revision, input case IDs và hash, accelerator,
timeout, expected artifacts, output location và quyền sử dụng dữ liệu. Không tự retry
một run có trạng thái chưa rõ.

## 7. Trạng thái hiện tại và giới hạn

- TV3 evaluator hiện có Four Scene Rate, Schema Valid Rate, Keyword Recall,
  Event Coverage và Event Order.
- Hallucination và Generation Time chưa tích hợp vào src/evaluation/.
- Notebook 04_evaluation.ipynb trước đây là file rỗng; notebook runner chỉ được
  dùng để chạy batch đã chuẩn bị, không tự tạo annotation hoặc gọi model.
- Approved Dev event inventory có 76 event trên 20 case; 4 dòng bị loại khỏi reference.
- Inventory gate kiểm tra case/event completeness và trạng thái approval trong CSV,
  không chứng minh semantic correctness của event hoặc human label.
- Không có kết quả ablation mới được tạo trong tài liệu này.
