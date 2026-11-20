# Môi trường và kết quả kiểm thử ban đầu

Các thông số và output bên dưới được giữ từ ghi chép smoke test của nhóm. Task nền tảng không chạy lại GPU inference hoặc xác minh độc lập các phiên bản này. Notebook 02 hiện có code nhưng không lưu outputs/execution counts; không xem ghi chép này là log thực thi đính kèm repository.

## 1. Môi trường thực nghiệm

Nhóm sử dụng Kaggle Notebooks để thực thi các mô hình AI do máy tính cá nhân không có GPU chuyên dụng.

Cấu hình phần cứng:

- GPU: 2 × NVIDIA Tesla T4.
- VRAM: 14.56 GiB trên mỗi GPU.
- Compute capability: 7.5.
- NVIDIA Driver: 580.178.04.
- CUDA build: 13.0.

## 2. Phiên bản phần mềm

| Thư viện | Phiên bản |
|---|---|
| Python | 3.13.16 |
| PyTorch | 2.11.0+cu130 |
| Transformers | 5.20.2 |
| Diffusers | 0.42.0 |
| Accelerate | 1.15.0 |
| Gradio | 6.30.0 |
| Pydantic | 2.14.1 |
| Pillow | 13.0.0 |
| Hugging Face Hub | 1.33.0 |
| Safetensors | 0.8.0 |

Thư viện Bitsandbytes chưa được cài đặt. Tuy nhiên, điều này không ảnh hưởng đến thử nghiệm hiện tại vì nhóm sử dụng FP16 và không thực hiện quantization.

## 3. Kiểm thử môi trường

Các thư viện chính được import thành công. Cả hai GPU đều thực hiện được phép nhân ma trận FP16 trên PyTorch.

Kết quả cho thấy môi trường đáp ứng được các yêu cầu tính toán cơ bản để tiến hành thử nghiệm mô hình.

## 4. Mô hình sinh truyện

- Tên mô hình: Qwen2.5-3B-Instruct.
- Model ID: Qwen/Qwen2.5-3B-Instruct.
- Revision: aa8e72537993ba99e69dfaafa59ed015b17504d1.
- Precision: FP16.
- Thiết bị thực thi: cuda:0.
- Phương pháp: LLM Prompting.
- Fine-tuning: Không.
- Quantization: Không.
- Decoding: Greedy decoding.
- Giới hạn token sinh mới: 256.

## 5. Nội dung kiểm thử

Đầu vào:

Một con thỏ thách rùa thi chạy. Thỏ chủ quan ngủ quên giữa đường. Rùa kiên trì về đích và chiến thắng.

Đầu ra thực tế:

1. Một con thỏ tự tin thách đấu với rùa về một cuộc chạy đua.
2. Trong khi rùa đang cố gắng tập trung, thỏ ngủ quên trên đường.
3. Rùa tiếp tục chạy không ngừng nghỉ, cuối cùng về đích trước thỏ.
4. Rùa chiến thắng cuộc chạy đua nhờ sự kiên trì của mình.

## 6. Kết quả đo lường

| Chỉ số | Giá trị |
|---|---:|
| Thời gian nạp model trong phiên thử nghiệm | 4.23 giây |
| VRAM allocated sau khi nạp model | 5.75 GiB |
| VRAM reserved sau khi nạp model | 11.57 GiB |
| Số token đầu vào | 102 |
| Số token sinh ra | 78 |
| Thời gian inference | 5.7 giây |
| Tốc độ sinh token | 13.68 token/giây |
| Peak allocated VRAM | 5.77 GiB |
| Số cảnh sinh ra | 4 |

Thời gian nạp model không được sử dụng để suy ra thời gian tải toàn bộ trọng số qua Internet vì trạng thái cache chưa được xác định.

## 7. Nhận xét

Mô hình đã sinh thành công nội dung tiếng Việt gồm bốn cảnh theo yêu cầu. Các nhân vật chính và kết thúc của câu chuyện được giữ nguyên.

Tuy nhiên, nội dung của cảnh thứ ba và thứ tư có sự trùng lặp. Quan hệ nguyên nhân giữa sự chủ quan và việc ngủ quên của nhân vật thỏ cũng chưa được thể hiện đầy đủ.

Đây là cơ sở để nhóm nghiên cứu cơ chế Story Consistency Validation & Repair nhằm cải thiện cấu trúc và mức độ bám sát nội dung đầu vào.

## 8. Giới hạn của thử nghiệm

Thử nghiệm mới được thực hiện trên một mẫu đầu vào.

Chưa đủ dữ liệu để kết luận về chất lượng sinh truyện tổng quát, tỷ lệ tuân thủ JSON schema hoặc hiệu quả của các phương pháp cải tiến.

Nhóm cần hoàn thành kiểm tra giấy phép model, thiết lập development set và thực hiện các thử nghiệm tiếp theo trước khi đưa ra kết luận chính thức.

## 9. Development CPU và optional inference dependencies

Các mục1–8 giữ nguyên smoke-test record lịch sử, không phải phiên bản package bắt buộc cho laptop. Shared CPU mock pipeline đã chạy được ở Task07B; Task10A.1 thêm Qwen factory wiring bằng injected CPU tests, không chạy GPU hoặc cài package.

- Default mock/direct Python config cần Pydantic v2 và Pillow; pytest cho tests.
- `PyYAML6.0.3` đã được cài vào project .venv Python3.12.3 theo approval Task10A.1.1;12existing packages giữ nguyên versions. Chỉ explicit YAML loader cần dependency này, import lazy. Actual YAML integration đã PASS; không dùng injected parser để thay thế bằng chứng parsing thật.
- LLM stack trong requirements-llm.txt chọn riêng cho Kaggle; không import/load tại factory build. Story/repair model và tokenizer pin revision cũ; không quantization hoặc automatic device_map.
- Diffusion/Gradio không cần cho default mock hoặc CPU factory tests; concrete image factory wiring và UI ngoài Task10A.1.
- requirements.txt vẫn khai báo PyYAML không pin;6.0.3 là actual tested version, không phải lockfile mới. Không sửa requirements hoặc nâng/hạ packages để vượt tests.

## 10. Active configuration API

Xem [configuration.md](configuration.md) và [pipeline.md](pipeline.md). `PipelineConfig()` vẫn mock/mock/cpu, mock retry0; qwen mode yêu cầu explicit CUDA story device và default retry2, explicit retry0 không bị ghi đè. Story/image devices độc lập; legacy device alias không trộn split fields.

`build_pipeline(config)` không đọc YAML/.env/environment. `load_pipeline_config` là opt-in loader với precedence defaults → YAML → documented environment mapping → explicit caller overrides. Không parse .env ngầm; template chỉ phục vụ caller tự export. Credentials không được config loader đọc hoặc persist. Output/cache/YAML relative paths dựa trên repository root.

Default CLI `.venv/bin/python scripts/run_pipeline.py` vẫn chỉ CPU mock, tạo unique ignored output directory. Build real-story pipeline không tải weights; gọi generate trong actual runtime có thể lazy-load model nên cần phê duyệt inference riêng. Không chạy notebook/GPU inference trên laptop. Chưa có automatic GPU cleanup/offloading manager hoặc bảo đảm đủ VRAM cho story và diffusion cùng lúc.

## 11. Strict YAML regression verification — Task10A.1.2

Private SafeLoader-derived loader reject duplicate mapping keys/sections trước dict construction ở mọi level; so sánh constructed keys, reject non-hashable keys và merge keys. Không sửa global PyYAML state hoặc cho unsafe object constructors. Aliases không bypass mapping checks; intentional overrides giữa defaults/YAML/environment/explicit layers vẫn hợp lệ, không implicit .env loading.

Actual PyYAML6.0.3:178targeted tests PASS,877full CPU tests PASS,0skipped/failed/errors; pip check PASS.30regression cases mới và hai original P1 probes xác nhận duplicate YAML bị reject. Default mock CLI vẫn chạy CPU với actual PNG1060×1320. Không chạy real Qwen factory inference/GPU hoặc thay frozen prompts/controller semantics.
