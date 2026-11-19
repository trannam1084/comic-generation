# AI Comic Generation

Sinh truyện tranh bốn khung từ tóm tắt tiếng Việt.

## 1. Giới thiệu và trạng thái

AI Comic Generation là đồ án xây dựng hệ thống tự động tạo truyện tranh gồm đúng 4 khung từ một đoạn tóm tắt truyện bằng tiếng Việt.

Thiết kế dự kiến sử dụng Large Language Model (LLM) để sinh nội dung có cấu trúc, mô hình sinh ảnh để minh họa từng cảnh và Pillow để kết hợp ảnh với caption tiếng Việt.

Đồ án tham khảo tài liệu AI VIET NAM – AIO2025 – Project: Comic Generation. Repository chưa lưu PDF/phiên bản/trang trích dẫn để đối chiếu; không coi nội dung thiết kế bên dưới là trích dẫn đã xác minh từ PDF. Phương án nhóm đề xuất được phân biệt trong [kiến trúc](docs/architecture.md).

**Đang phát triển; chưa có pipeline end-to-end hoạt động.**

Tại nền `809350b`, toàn bộ `src/` và `app.py` vẫn là placeholder; datasets và tests chưa có nội dung. Notebook 02 local có code smoke test, chưa lưu outputs. Ba notebook còn lại chỉ có newline, chưa phải notebook JSON hợp lệ. Task nền tảng chỉ cập nhật tài liệu/cấu hình.

Theo refs local đã kiểm tra ngày 18/11/2026, `origin/feature/image-pipeline` có commit `899f99f` triển khai PromptBuilder và sáu test functions; chưa được tích hợp hoặc chạy tests trong task nền tảng. Không suy ra code của branch này đã có tại `main`.

## 2. Đầu vào và đầu ra mục tiêu

**Input:** Một đoạn tóm tắt truyện bằng tiếng Việt.

**Output:**

- Storyboard JSON gồm đúng 4 cảnh.
- 4 image prompts tiếng Anh.
- 4 ảnh minh họa.
- Caption tiếng Việt cho từng cảnh.
- Truyện tranh hoàn chỉnh theo layout 2×2.

## 3. Kiến trúc dự kiến

Vietnamese Summary
→ Input Validation
→ LLM Story Generation
→ Storyboard Validation & Repair
→ Image Prompt Builder
→ Image Generation
→ Caption Rendering
→ Four-Panel Comic

Chi tiết trách nhiệm và ranh giới module: [docs/architecture.md](docs/architecture.md).

## 4. Phương pháp nhóm đề xuất

Nhóm tập trung vào một phương pháp sinh truyện chính: LLM Prompting.

Các cải tiến đề xuất:

### Story Consistency Validation & Repair

Kiểm tra tính hợp lệ của storyboard, số lượng cảnh, thứ tự, nhân vật và mức độ bám sát nội dung đầu vào. Yêu cầu sinh lại hoặc sửa nội dung khi phát hiện lỗi.

### Character Description Consistency

Tái sử dụng mô tả ngoại hình nhân vật trong image prompts nhằm cải thiện sự nhất quán giữa các khung.

Hiệu quả của các cải tiến sẽ được đánh giá bằng thực nghiệm.

## 5. Công nghệ và môi trường development

- Python
- PyTorch
- Hugging Face Transformers
- Hugging Face Diffusers
- Pydantic
- Pillow
- Gradio
- Pytest
- Kaggle Notebooks
- Git & GitHub

Development mặc định: story backend `mock`, image backend `mock`, device `cpu`. Đây là cấu hình thiết kế; mock backend và config loader chưa được triển khai. Không có lệnh chạy ứng dụng end-to-end tại thời điểm này.

`requirements.txt` chỉ liệt kê dependency CPU dự kiến, không kéo PyTorch/Transformers/Diffusers/Gradio. Không pin phiên bản chưa kiểm chứng. Các nhóm dependency LLM và diffusion được ghi riêng trong [docs/environment.md](docs/environment.md); không yêu cầu laptop cài toàn bộ GPU stack.

`configs/settings.yaml` là cấu hình nền dự kiến; `.env.example` mô tả các biến tương ứng và credential để trống. Cách đọc/ghi đè cấu hình cần thống nhất trước khi triển khai loader. Không load model khi import module.

## 6. Môi trường và smoke test

Nhóm sử dụng laptop để phát triển source code và Kaggle Notebooks để chạy GPU inference.

Hardware audit ban đầu:

| Component | Configuration |
|---|---|
| Python | 3.13.16 |
| PyTorch | 2.11.0+cu130 |
| GPU | 2 × NVIDIA Tesla T4 |
| VRAM | 14.56 GiB per GPU |
| CUDA available | True |

Cấu hình Kaggle có thể thay đổi giữa các phiên làm việc.

Ứng viên LLM chính đã chạy smoke test trên một mẫu: `Qwen/Qwen2.5-3B-Instruct`, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, FP16, một Tesla T4, greedy decoding, không quantization hoặc fine-tuning.

Theo kết quả nhóm đã ghi nhận: input 102 tokens; sinh 78 tokens trong 5.7 giây, 13.68 token/giây; peak allocated VRAM 5.77 GiB; đúng bốn cảnh nhưng cảnh 3 và 4 có nội dung trùng lặp. Đây là smoke test văn bản đánh số, chưa chứng minh tuân thủ storyboard JSON. Notebook hiện không lưu outputs; các số đo chưa được tái kiểm chứng trong task nền tảng.

Không khẳng định Qwen là model tốt nhất. License Review và development evaluation chưa hoàn thành; image backend chưa được chốt. Xem [môi trường](docs/environment.md) và [lựa chọn model](docs/model_selection.md).

## 7. Đánh giá dự kiến

Các chỉ số dự kiến:

- Four Scene Rate
- Schema Valid Rate
- Keyword Recall
- Event Coverage
- Narrative Coherence
- Hallucination
- Character Consistency
- Image-Caption Alignment
- Caption Readability
- Generation Time

Nhóm dự kiến so sánh baseline với phiên bản có Validation & Repair và shared character descriptions. Định nghĩa metrics, datasets và thực nghiệm chưa hoàn tất; chưa có kết quả chứng minh hiệu quả các cải tiến.

## 8. Phân công

| Thành viên | Trách nhiệm |
|---|---|
| TV1 – Nhóm trưởng | LLM, Storyboard, Validation, Repair, Integration |
| TV2 | Image Generation, Character Consistency, Pillow, Gradio |
| TV3 | Dataset, Evaluation, Ablation Study, Testing |

Shared files và quy trình review: [CONTRIBUTING.md](CONTRIBUTING.md).

## 9. Cấu trúc repository

- `src/story_generator/`: LLM prompting và repair.
- `src/storyboard/`: Schema và validator.
- `src/image_generator/`: Image prompts và image backends.
- `src/comic_renderer/`: Caption và comic rendering.
- `src/evaluation/`: Evaluation metrics.
- `notebooks/`: Kaggle experiments.
- `examples/`: Storyboard mẫu.
- `data/`: Development và test datasets.
- `tests/`: Unit tests và integration tests.
- `docs/`: Project documentation.
- `app.py`: Gradio application.

Các đường dẫn trên thể hiện trách nhiệm dự kiến, không phải xác nhận implementation đã hoàn tất. [Data Contract sơ bộ](docs/data_contract.md) đối chiếu example hiện tại với code của TV2.

`models/` cũ đã bị xóa ở commit `809350b`. Hai script legacy được giữ trong backup ngoài repository; các bản local đang ignored được giữ nguyên. Chưa đưa chúng vào pipeline, GitHub hoặc `references/legacy/` do chưa xác minh đầy đủ quyền sử dụng. Không khôi phục bốn placeholder rỗng hoặc CSV cũ theo mặc định.

## 10. Lộ trình

- [x] Xác định bài toán và kiến trúc dự kiến
- [x] Ghi nhận Kaggle hardware audit và dependency/GPU smoke test
- [x] Ghi nhận Qwen inference smoke test trên một mẫu
- [ ] Hoàn tất License Review và development evaluation
- [ ] Thống nhất Data Contract sơ bộ với TV2 và kiểm thử structured generation
- [ ] Hoàn thiện môi trường tái lập và lưu bằng chứng thực thi
- [ ] Mock end-to-end pipeline trên CPU
- [ ] LLM Story Generation, Validation & Repair
- [ ] Image Generation, rendering và Gradio
- [ ] Evaluation, ablation study và báo cáo cuối kỳ

## 11. Tài liệu tham khảo

- AI VIET NAM – AIO2025 – Project: Comic Generation.
- Hugging Face Transformers Documentation.
- Hugging Face Diffusers Documentation.
- PyTorch Documentation.
- Kaggle Notebooks.

## 12. Giới hạn và quyền sử dụng

Đây là đồ án học thuật đang phát triển. Nội dung sinh có thể sai hoặc thiếu nhất quán. MIT của repository không thay thế license của model, code tham khảo hoặc dataset bên ngoài. Phải xác minh quyền sử dụng trước khi phân phối các tài sản đó.
