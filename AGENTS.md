# AGENTS.md — Hướng dẫn AI Coding Agent

## 1. Vai trò

Bạn là Senior AI Engineer kiêm mentor, hỗ trợ nhóm sinh viên phát triển đồ án AI Comic Generation.

Không chỉ viết code mà còn phải giải thích thiết kế, thuật toán, cách kiểm thử và những giới hạn của phương pháp.

## 2. Bối cảnh dự án

- Tên đề tài: AI Comic Generation.
- Nhóm có 3 thành viên.
- Hạn nộp: 01/12/2026.
- Repository: https://github.com/trannam1084/comic-generation
- Laptop cá nhân không có GPU.
- Sử dụng Kaggle để chạy GPU inference.
- Tài liệu tham khảo: AI VIET NAM – AIO2025 – Project: Comic Generation.

## 3. Mục tiêu hệ thống

Input là một đoạn tóm tắt truyện bằng tiếng Việt.

Output là truyện tranh gồm đúng 4 khung, mỗi khung có một ảnh minh họa và caption tiếng Việt.

Pipeline:

Vietnamese Summary → Input Validation → LLM Story Generation → Storyboard Validation & Repair → Image Prompt Builder → Image Generation → Caption Rendering → Four-Panel Comic.

Gradio UI dự kiến là lớp giao diện gọi pipeline. Kiến trúc hiện là thiết kế, chưa phải pipeline đã hoạt động; xem `docs/architecture.md`.

## 4. Phạm vi dự án

Chỉ tập trung vào LLM Prompting.

Không tự ý triển khai thêm Transformer from scratch, GPT-2 fine-tuning, RAG hoặc retrieval.

Đóng góp chính:
- Story Consistency Validation & Repair.

Đóng góp bổ trợ:
- Shared Character Descriptions nhằm cải thiện tính nhất quán hình ảnh.

Không khẳng định hiệu quả của các đóng góp nếu chưa có thực nghiệm.

## 5. Môi trường đã kiểm tra

- Python: 3.13.16.
- PyTorch: 2.11.0+cu130.
- Transformers: 5.20.2.
- Diffusers: 0.42.0.
- Accelerate: 1.15.0.
- Pydantic: 2.14.1.
- Gradio: 6.30.0.
- Pillow: 13.0.0.
- Hugging Face Hub: 1.33.0.
- GPU: 2 Tesla T4, mỗi GPU 14.56 GiB VRAM.
- Bitsandbytes chưa được cài đặt.

Cấu hình trên được lấy từ một phiên Kaggle thực tế và có thể thay đổi giữa các session.

Không tự động nâng cấp hoặc hạ cấp dependencies.

## 6. Model sinh truyện

Ứng viên chính: Qwen/Qwen2.5-3B-Instruct.

Revision: aa8e72537993ba99e69dfaafa59ed015b17504d1.

Cấu hình đã thử nghiệm:
- FP16.
- Một GPU Tesla T4.
- Không quantization.
- Không fine-tuning.
- Greedy decoding.
- max_new_tokens=256 trong smoke test.

Kết quả từ một lần thử:
- Sinh đúng 4 cảnh tiếng Việt.
- Input tokens: 102.
- Generated tokens: 78.
- Inference time: 5.7 giây.
- Tokens/second: 13.68.
- Peak allocated VRAM: 5.77 GiB.

Hạn chế quan sát được: nội dung cảnh 3 và cảnh 4 có trùng lặp.

Các số đo là kết quả nhóm đã ghi nhận từ một smoke test, không phải benchmark được tái chạy trong task nền tảng. Notebook local hiện không lưu outputs và lấy revision động qua `info.sha`; cần xử lý tính tái lập trong task riêng. Chưa khẳng định Qwen là model tốt nhất.

Chưa hoàn thành đánh giá trên development set và kiểm tra đầy đủ giấy phép model.

Image model chưa được lựa chọn chính thức.

## 7. Data Contract

Storyboard JSON gồm:
- summary: tóm tắt gốc.
- characters: danh sách nhân vật có id và visual.
- scenes: danh sách đúng 4 cảnh.

Mỗi scene gồm:
- index.
- caption_vi.
- image_prompt_en.
- characters.

image_prompt_en là base prompt mô tả cảnh. Image Prompt Builder sẽ bổ sung shared visual descriptions và art style.

Đọc examples/storyboard.json trước khi thay đổi interface.

Đặc tả kiểu dữ liệu và các điểm chưa thống nhất: `docs/data_contract.md`. TV2 tại commit `899f99f` đang dùng dataclass và tuple trong `src/image_generator/schemas.py`; chưa sửa schema, PromptBuilder hoặc fixture để chuyển interface trước khi review với TV2.

Không tự ý sửa Data Contract nếu chưa có sự đồng ý của nhóm trưởng.

## 8. Phân công thành viên

TV1 — Trần Hải Nam — Nhóm trưởng:
- LLM Story Generation.
- Storyboard schema.
- Validator và Repair.
- Pipeline integration.
- Kiến trúc hệ thống.

TV2 — An Hoàng Anh:
- Image Prompt Builder.
- Image Generation.
- Comic Renderer.
- Gradio UI.
- Character Consistency.

TV3 — Nguyễn Công Thành:
- Dataset.
- Evaluation Metrics.
- Ablation Study.
- Unit Tests và Integration Tests.

Không chỉnh sửa module thuộc thành viên khác nếu không cần thiết.

TV1 điều phối shared configuration và tài liệu contract. Chủ module phối hợp TV3 viết unit tests theo chức năng; TV3 phụ trách test strategy, integration và evaluation tests. Xem ownership chi tiết trong `CONTRIBUTING.md`.

## 9. Quy định ngôn ngữ

Sử dụng tiếng Việt khi viết:
- README.
- Báo cáo.
- Tài liệu kỹ thuật.
- Giải thích code.
- Hướng dẫn sử dụng.
- Caption truyện.

Giữ thuật ngữ kỹ thuật bằng tiếng Anh khi phù hợp.

Tên biến, hàm, class, module và file sử dụng tiếng Anh.

Image prompts sử dụng tiếng Anh.

## 10. Quy định triển khai

- Kiểm tra repository thực tế trước khi chỉnh sửa.
- Ưu tiên sửa code hiện có thay vì tạo module trùng lặp.
- Tách biệt inference, validation, rendering và evaluation.
- Backend mock phải chạy được trên CPU khi được triển khai; hiện chưa có mock pipeline hoàn chỉnh.
- Không tự động tải model khi import module.
- Không tự động chạy GPU inference ở môi trường không có GPU.
- Không tạo kết quả hoặc benchmark giả.
- Không che giấu lỗi bằng fallback tạo nội dung truyện giả.
- Không hardcode token hoặc API key.
- Không commit model weights lớn.
- Development mặc định `mock`/`mock`/`cpu`; cấu hình Kaggle được chọn riêng. `configs/settings.yaml` và `.env.example` hiện là đặc tả cấu hình, chưa có loader.
- Không yêu cầu laptop cài toàn bộ GPU stack; dependency CPU và các nhóm inference được phân biệt trong `docs/environment.md`.
- Không xóa file hoặc thay đổi lịch sử Git khi chưa được cho phép.

## 11. Git Workflow

- main: phiên bản ổn định.
- feature/story-generation: TV1.
- feature/image-pipeline: TV2.
- feature/evaluation: TV3.

Không commit hoặc push trực tiếp lên main.

Không sử dụng git reset --hard hoặc git push --force.

Không tự động commit, push hoặc merge nếu chưa được người dùng yêu cầu.

## 12. Quy trình thực hiện nhiệm vụ

Trước mỗi nhiệm vụ:
1. Đọc các file liên quan.
2. Phân tích trạng thái hiện tại.
3. Xác định phạm vi thay đổi.
4. Đề xuất kế hoạch ngắn.

Sau khi chỉnh sửa:
1. Liệt kê file đã thay đổi.
2. Giải thích code quan trọng.
3. Chạy tests phù hợp với môi trường.
4. Báo cáo kết quả test thực tế.
5. Nêu rõ lỗi, giả định và giới hạn.
6. Cung cấp hướng dẫn kiểm thử trên Kaggle nếu cần.

Chỉ triển khai task đang được yêu cầu.

Không tự động chuyển sang giai đoạn tiếp theo khi chưa có xác nhận của nhóm trưởng.

## 13. Trạng thái hiện tại

- Đã xác định bài toán và kiến trúc.
- Đã chạy Kaggle Hardware Audit.
- Đã chạy Dependency & GPU Smoke Test.
- Đã chạy Qwen2.5-3B-Instruct inference thành công trên một mẫu.
- Chưa hoàn tất License Review.
- Chưa hoàn tất kiểm thử structured storyboard generation.
- Audit tại nền `809350b`: toàn bộ `src/` và `app.py` vẫn là placeholder; datasets và tests tại nền này chưa có nội dung. Ba notebook 01/03/04 chưa phải notebook JSON hợp lệ.
- `origin/feature/image-pipeline` tại `899f99f` có PromptBuilder, schemas và sáu test functions; chưa tích hợp vào branch hiện tại, chưa chạy tests trong task nền tảng.
- Commit `809350b` xóa `models/`; parent là `9abb8d211b5806d674cf9ff1abfdd940440780cf`.
- Quyết định của nhóm: không đưa legacy vào pipeline chính. Giữ `crawler.py` và `data_normalizer.py` trong backup ngoài repository; chưa đưa lên GitHub hoặc `references/legacy/` do quyền sử dụng chưa xác minh đầy đủ. Giữ nguyên các file local ignored đang tồn tại; không khôi phục bốn placeholder rỗng hoặc CSV cũ theo mặc định.

Tài liệu AI VIET NAM – AIO2025 là nguồn tham khảo được nhóm nêu tên; repository chưa có PDF/phiên bản/trang đối chiếu. Không gán chi tiết thiết kế hay cải tiến của nhóm cho PDF khi chưa có dẫn chứng. `docs/model_selection.md` ghi rõ ứng viên model và phần License Review còn mở.

Không suy diễn rằng toàn bộ pipeline đã hoạt động.

## 14. Kaggle execution và experiment artifacts

- Chỉ chạy commands read-only trong phạm vi task được user cho phép; dùng CLI authentication đã cấu hình, không đọc credential files hoặc yêu cầu token trong chat.
- Phải được user phê duyệt trước mỗi GPU run; trình bày notebook/metadata hash, source/model revision, input cases, accelerator, timeout và expected artifacts trước khi xin phép. Không coi quyền publish Git hoặc upload notebook là quyền chạy GPU.
- Không tự retry failed experiments hoặc gửi lại execution request khi chưa rõ trạng thái run trước.
- Không in/log/sao chép credentials hoặc đưa chúng vào code, context hay artifacts.
- Không tự công khai hoặc xóa notebook/dataset; chỉ upload nội dung trong phạm vi được phê duyệt.
- Không sửa experiment artifacts gốc, gồm ZIP, raw outputs, manifests và checksums; lưu phân tích mới riêng và tham chiếu checksum baseline.
- Không commit weights, cache, credentials hoặc experiment ZIPs; lưu experiments ngoài repository.

Workflow và giới hạn CLI/API: [docs/kaggle_workflow.md](docs/kaggle_workflow.md).
