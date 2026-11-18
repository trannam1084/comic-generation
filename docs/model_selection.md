# Lựa chọn model sơ bộ

## 1. Phương pháp và tiêu chí

Nhóm chọn LLM Prompting, không fine-tuning hoặc quantization trong smoke test hiện tại. Model cần được xem xét về tiếng Việt, structured output, tài nguyên một Tesla T4, latency và license. Chưa có so sánh có kiểm soát để xếp hạng hoặc tuyên bố model tốt nhất.

## 2. Ứng viên chính đã smoke test

| Thuộc tính | Ghi nhận của nhóm |
|---|---|
| Model ID | `Qwen/Qwen2.5-3B-Instruct` |
| Revision | `aa8e72537993ba99e69dfaafa59ed015b17504d1` |
| Precision và thiết bị | FP16, một Tesla T4 (`cuda:0`) |
| Decoding | Greedy, `max_new_tokens=256` |
| Quantization / fine-tuning | Không / Không |
| Input / generated tokens | 102 / 78 |
| Inference / tốc độ | 5.7 giây / 13.68 token/giây |
| Peak allocated VRAM | 5.77 GiB |
| Kết quả | Đúng bốn cảnh tiếng Việt; cảnh 3 và 4 có nội dung trùng lặp |

Đây là một mẫu truyện thỏ và rùa, chưa phải development evaluation. Notebook hiện yêu cầu bốn cảnh đánh số, không sinh đầy đủ storyboard JSON. Số đo được nhóm cung cấp và chưa được tái chạy trong Task 03; notebook không lưu outputs. Mô tả chi tiết: [environment.md](environment.md).

## 3. Ghi nhận License Review cho phạm vi nghiên cứu

File [LICENSE chính thức tại revision đã dùng](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/aa8e72537993ba99e69dfaafa59ed015b17504d1/LICENSE) mang tên Qwen Research License Agreement và cấp quyền cho mục đích non-commercial; commercial use cần license riêng theo văn bản đó. Không suy ra model mang MIT chỉ vì repository của nhóm có MIT License.

Đây là ghi nhận nguồn license, không phải kết luận nhóm đã hoàn tất review hoặc được phép mọi hình thức phân phối. Cần đối chiếu mục đích sử dụng, điều kiện redistribution/attribution và artifacts dự định chia sẻ. Không đưa weights hoặc credential vào Git. Code tham khảo, PDF và dữ liệu bên ngoài cần review quyền sử dụng riêng.

Task 08A đã đối chiếu văn bản tại đúng revision, release date September 19, 2024; dự án có phạm vi nghiên cứu sinh viên phi thương mại. Xem [model_license.md](model_license.md) về các điều khoản 1(i), 2, 3 và 4(b), cùng các giới hạn của ghi nhận này. Không mô tả Qwen2.5-3B-Instruct là Apache 2.0; chưa suy ra toàn bộ artifacts của dự án được phép phân phối.

## 4. Image backend và các việc còn mở

Image backend chưa được lựa chọn chính thức. Chuỗi `sdxl` xuất hiện trong comment kiểu dữ liệu `GeneratedImage.backend` ở `899f99f` không phải quyết định chọn model của nhóm. Development dùng `mock` như cấu hình dự kiến; backend chưa được triển khai tại nền hiện tại.

Các bước đánh giá tiếp theo cần được giao thành task riêng:

1. Hoàn tất License Review và giữ bản ghi model ID/revision.
2. Chốt development set, structured contract và tiêu chí đo với TV3.
3. Đo khả năng tuân thủ JSON, nội dung và lỗi trên development set; so sánh baseline với Validation & Repair.
4. Đánh giá shared character descriptions sau khi có image backend và ablation phù hợp.
5. Lưu logs/outputs cùng cấu hình thực tế để tái lập; không suy rộng từ một smoke test.

## 5. Structured backend chuẩn bị trong Task 08A

Đã có code QwenStoryBackend và CPU tests bằng fakes, chưa chạy structured inference thật. Cấu hình chuẩn bị: một `cuda:0`, FP16, greedy, batch 1, `max_new_tokens=1024`, không quantization/fine-tuning, không auto device_map. Tokenizer và model cùng pin revision ở mục 2.

Budget 1024 là cấu hình structured baseline mới, không thay thế kết quả smoke test cũ dùng 256. Prompt `storyboard-v1.0-baseline-001` không dùng fixture thỏ/rùa làm few-shot. Xem [qwen_inference.md](qwen_inference.md) để chuẩn bị Task 08B; CPU tests không chứng minh inference, chất lượng JSON hoặc hiệu quả phương pháp trên Qwen thật.
