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

## 9. Development trên CPU và nhóm dependencies

Development mặc định: story backend `mock`, image backend `mock`, device `cpu`. `requirements.txt` chỉ chứa các dependency CPU dự kiến, không pin phiên bản chưa kiểm chứng:

| Nhóm | Dependencies | Mục đích và trạng thái |
|---|---|---|
| CPU cơ sở | `pydantic`, `Pillow`, `PyYAML`, `pytest` | Dự kiến phục vụ schema, rendering, YAML và tests; chưa có mock pipeline để chạy |
| LLM inference, chọn riêng trên Kaggle | `torch`, `transformers`, `accelerate`, `huggingface-hub`, `safetensors` | Cần xác minh trong session được sử dụng; không nằm trong requirements CPU |
| Diffusion inference, sau khi chốt backend | `torch`, `diffusers`, `accelerate`, `safetensors`; có thể cần `transformers`, `huggingface-hub` theo backend | Chưa phải dependency set đã chốt hoặc đã kiểm thử cho model ảnh |
| UI, khi có task triển khai | `gradio` | Không bắt buộc cho mock/module tests; UI chưa triển khai |

Không chạy cài đặt tự động. Không suy ra các phiên bản ghi ở mục 2 là lockfile hoặc yêu cầu cho laptop. PyTorch/CUDA phải được chọn phù hợp với môi trường Kaggle thực tế. Bitsandbytes không thuộc phương án smoke test FP16 hiện tại.

Nếu cần tách file sau này, có thể đề xuất `requirements-llm.txt`, `requirements-diffusion.txt` và `requirements-ui.txt`; chưa tạo hoặc pin các file đó trong task nền tảng. Chỉ lock dependencies sau khi có kiểm thử tương ứng.

## 10. Cấu hình và tính tái lập

`configs/settings.yaml` ghi các giá trị nền dự kiến; `.env.example` có các biến tương ứng. Chưa có code đọc YAML hoặc `.env`, nên đổi file cấu hình hiện chưa thay đổi hành vi module. Đề xuất thứ tự ưu tiên cho loader tương lai: tham số chạy rõ ràng → environment variables → YAML; cần review trước khi triển khai. Credentials chỉ lấy từ secret store/environment, không lưu trong YAML.

| Biến môi trường | Trường YAML |
|---|---|
| `STORY_BACKEND` | `story.backend` |
| `IMAGE_BACKEND` | `image.backend` |
| `DEVICE` | `runtime.device` |
| `OUTPUT_DIR` | `runtime.output_dir` |
| `MAX_RETRIES` | `runtime.max_retries` |

`runtime.max_retries = 2` là giá trị development dự kiến; nghĩa retry là số lần thử lại sau lần đầu cần được xác nhận cùng interface Repair. Không dùng giá trị này để tuyên bố Repair đã tồn tại.

Khi chuẩn bị chạy Kaggle trong task riêng:

1. Ghi nhận phiên bản Python/packages, GPU/VRAM và trạng thái cache thực tế.
2. Chọn cấu hình inference tách khỏi mặc định CPU; ghi rõ model ID và revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, FP16, một T4, không quantization/fine-tuning.
3. Kiểm tra quyền sử dụng và khả năng truy cập model; không in credential.
4. Notebook hiện lấy `REVISION = info.sha`, có thể đổi theo upstream; cần task riêng để pin revision và lưu bằng chứng chạy. Task nền tảng giữ nguyên notebook.
5. Lưu prompt, thông số decoding, outputs và metrics đã loại secret; phân biệt thời gian load từ cache với thời gian download.
6. Kiểm thử structured storyboard riêng; smoke test bốn cảnh văn bản chưa chứng minh Data Contract.

Notebook dùng đường dẫn `/kaggle/working`; không chạy trực tiếp notebook inference trên laptop CPU. Model chỉ được load bởi thao tác inference rõ ràng, không tự load khi import module. Chưa có lệnh chạy mock end-to-end để hướng dẫn ở thời điểm này.
