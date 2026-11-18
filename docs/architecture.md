# Kiến trúc dự kiến của nhóm

## 1. Nguồn tham khảo và phương án đề xuất

Nhóm nêu tài liệu AI VIET NAM – AIO2025 – Project: Comic Generation làm nguồn tham khảo. Repository chưa chứa PDF, phiên bản hoặc trang trích dẫn; chưa đủ căn cứ đối chiếu chi tiết thuật toán/code nào thuộc PDF. Cần bổ sung dẫn chứng trước khi viết báo cáo nguồn gốc. Hai script legacy cũng chưa được xác minh nguồn upstream và quyền sử dụng.

Thiết kế dưới đây là phương án nhóm đang lựa chọn: LLM Prompting; Story Consistency Validation & Repair là đóng góp chính đề xuất; shared character descriptions là đóng góp bổ trợ đề xuất. Chưa có ablation hoặc development evaluation để kết luận hiệu quả hoặc tính mới so với tài liệu tham khảo. Không triển khai Transformer from scratch, GPT-2 fine-tuning, RAG hoặc retrieval.

## 2. Luồng xử lý mục tiêu

Vietnamese Summary → Input Validation → LLM Story Generation → Storyboard Validation & Repair → Image Prompt Builder → Image Generation → Caption Rendering → Four-Panel Comic.

Gradio UI dự kiến gọi pipeline, nhận kết quả và hiển thị lỗi phù hợp. Output mục tiêu là bốn ảnh với caption tiếng Việt trong layout 2×2. Đây là kiến trúc đích, chưa phải hệ thống đã hoạt động.

| Bước | Trách nhiệm dự kiến | Chủ trì |
|---|---|---|
| Input Validation | Kiểm tra input trước inference; giới hạn cụ thể chưa chốt | TV1 |
| LLM Story Generation | Từ summary tạo storyboard có cấu trúc | TV1 |
| Storyboard Validation & Repair | Kiểm tra cấu trúc, nhân vật, thứ tự và tính nhất quán; sửa có giới hạn, giữ lỗi nếu không sửa được | TV1 |
| Image Prompt Builder | Ghép base prompt, shared visual descriptions và art style; giữ caption | TV2 |
| Image Generation | Tạo ảnh từ final prompts; mock CPU và backend thật được chọn rõ ràng | TV2 |
| Caption Rendering | Ghép ảnh và caption tiếng Việt thành bốn khung | TV2 |
| Evaluation | Đo kết quả từng bước và ablation bằng dataset có quyền sử dụng | TV3 |
| Integration | Điều phối các interface, cấu hình và lỗi | TV1 |

## 3. Ranh giới dữ liệu và backend

Storyboard JSON sơ bộ được mô tả trong [data_contract.md](data_contract.md). `image_prompt_en` chỉ là base prompt; TV2 tạo final prompt riêng. Chưa quyết định di chuyển dataclasses hoặc đổi kiểu dữ liệu của code TV2. Không đưa trường output ảnh hoặc metadata inference vào JSON contract khi chưa review.

Development mặc định dùng story/image backend `mock`, device `cpu`. Mock là backend được chọn có chủ đích cho kiểm thử; không dùng fallback giả nội dung để che lỗi backend thật. LLM và diffusion inference được cấu hình riêng trên Kaggle, không tự tải model khi import. Config loader, exception types và retry policy chưa được triển khai hoặc chốt.

## 4. Trạng thái kiểm chứng và phối hợp

Tại nền `809350b`, các module `src/`, `app.py`, datasets và tests còn là placeholder. Notebook 02 local có code cho một smoke test Qwen, không có saved outputs. Kết quả nhóm ghi nhận được lưu trong [environment.md](environment.md), chưa chứng minh structured generation hay end-to-end.

Ref local `origin/feature/image-pipeline` có commit `899f99f` trên nền `809350b`: PromptBuilder, schemas, fixture và sáu test functions. Code này chưa có trong branch nền hiện tại; Task 03 chỉ đọc, không merge hoặc sửa. Không có thay đổi shared configuration trong commit đó.

Các điểm cần TV1/TV2 thống nhất trước integration: schema dùng chung ở đâu, list/tuple và serialization, validation/error boundaries, fixture chuẩn, final prompt metadata và cách chạy script. Xem [data_contract.md](data_contract.md). TV3 phối hợp chốt test cases và cách đo metrics; chưa tuyên bố metrics có implementation.

## 5. Legacy và giới hạn

`models/` bị xóa tại `809350b`; parent là `9abb8d211b5806d674cf9ff1abfdd940440780cf`. Nhóm quyết định giữ hai script trong backup ngoài repository, giữ nguyên bản local ignored, không đưa vào pipeline/GitHub/`references/legacy/` khi chưa rõ quyền sử dụng. Không khôi phục bốn file rỗng hoặc CSV cũ theo mặc định. Không có module mới được phát hiện phụ thuộc hai script tại snapshot audit.

Task nền tảng chỉ chuẩn hóa tài liệu và cấu hình; các module inference, validation, repair, rendering, UI và evaluation được dành cho nhiệm vụ riêng sau review.
