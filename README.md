# AI Comic Generation

Vietnamese Summary-to-Four-Panel Comic Generation

## 1. Giới thiệu (Overview)

AI Comic Generation là đồ án xây dựng hệ thống tự động tạo truyện tranh gồm đúng 4 khung từ một đoạn tóm tắt truyện bằng tiếng Việt.

Hệ thống sử dụng Large Language Model (LLM) để sinh nội dung có cấu trúc, mô hình sinh ảnh để minh họa từng cảnh và Pillow để kết hợp ảnh với caption tiếng Việt.

Đồ án tham khảo tài liệu AI VIET NAM – AIO2025 – Project: Comic Generation.

**Project status: In Development**

## 2. Input & Output

**Input:** Một đoạn tóm tắt truyện bằng tiếng Việt.

**Output:**
- Storyboard JSON gồm đúng 4 cảnh.
- 4 image prompts tiếng Anh.
- 4 ảnh minh họa.
- Caption tiếng Việt cho từng cảnh.
- Truyện tranh hoàn chỉnh theo layout 2×2.

## 3. System Architecture

Vietnamese Summary
→ Input Validation
→ LLM Story Generation
→ Storyboard Validation & Repair
→ Image Prompt Builder
→ Image Generation
→ Caption Rendering
→ Four-Panel Comic

## 4. Proposed Method

Nhóm tập trung vào một phương pháp sinh truyện chính: LLM Prompting.

Các cải tiến đề xuất:

### Story Consistency Validation & Repair

Kiểm tra tính hợp lệ của storyboard, số lượng cảnh, thứ tự, nhân vật và mức độ bám sát nội dung đầu vào. Yêu cầu sinh lại hoặc sửa nội dung khi phát hiện lỗi.

### Character Description Consistency

Tái sử dụng mô tả ngoại hình nhân vật trong image prompts nhằm cải thiện sự nhất quán giữa các khung.

Hiệu quả của các cải tiến sẽ được đánh giá bằng thực nghiệm.

## 5. Technology Stack

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

Model LLM và Image Generation backend sẽ được xác định sau compatibility test và inference smoke test.

## 6. Computing Environment

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

## 7. Evaluation

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

Nhóm thực hiện các thử nghiệm so sánh baseline với phiên bản có Validation & Repair và shared character descriptions.

## 8. Team Responsibilities

| Member | Responsibility |
|---|---|
| Member 1 – Team Leader | LLM, Storyboard, Validation, Repair, Integration |
| Member 2 | Image Generation, Character Consistency, Pillow, Gradio |
| Member 3 | Dataset, Evaluation, Ablation Study, Testing |

## 9. Repository Structure

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

## 10. Development Roadmap

- [x] Problem definition and architecture planning
- [x] Kaggle hardware audit
- [ ] Model compatibility check
- [ ] Environment smoke test
- [ ] Storyboard data contract
- [ ] Mock end-to-end pipeline
- [ ] LLM story generation
- [ ] Storyboard validation and repair
- [ ] Real image generation
- [ ] Comic rendering
- [ ] Gradio interface
- [ ] Evaluation and ablation study
- [ ] Final report and demonstration

## 11. References

- AI VIET NAM – AIO2025 – Project: Comic Generation.
- Hugging Face Transformers Documentation.
- Hugging Face Diffusers Documentation.
- PyTorch Documentation.
- Kaggle Notebooks.

## 12. Disclaimer

This repository is an academic project under development. Generated content may contain inaccuracies or inconsistencies. Model licenses and dataset usage rights must be verified before redistribution.
