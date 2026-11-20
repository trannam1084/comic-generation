# Qwen Structured Story Backend — chuẩn bị Task 08B

Task 09B bổ sung public `review(messages, prompt_version=...)` dùng chung tokenizer/model/runtime và property `last_review` riêng; `generate(summary)` và baseline prompt giữ nguyên. Các phần Task 08A/08B dưới đây là tài liệu của baseline; xem [semantic_validation.md](semantic_validation.md) cho API mới, metadata isolation và giới hạn CPU fake tests. Notebook 05/06 vẫn pin commit baseline cũ; chưa có semantic reviewer GPU run sau refactor.

Task 09C.2 bổ sung `generate_repair(feedback)` và `last_repair` trên cùng runtime; explicit routing tách story_generation/semantic_review/story_repair. Baseline messages/model/configuration giữ nguyên; [qwen_repair.md](qwen_repair.md) mô tả API, prompt, Unicode/data boundary và metadata isolation. Chỉ có CPU injected tests cho repair, chưa có GPU repair results hoặc bằng chứng repair effectiveness. Các đoạn Task 08A/08B bên dưới giữ bối cảnh lịch sử.

## 1. Trạng thái và nguồn đối chiếu

Task 08A chỉ triển khai code và CPU unit tests bằng fakes, không tải weights hoặc chạy Qwen thật. Không tạo notebook outputs, benchmark hoặc kết quả structured generation giả. Notebook 02 được đọc và giữ nguyên smoke test cũ; số đo 102/78 tokens, 5.7 giây và budget 256 trong [environment.md](environment.md) thuộc thử nghiệm khác, không tái dùng làm kết quả cho prompt mới.

Nguồn chính thức đã đối chiếu:

- [Model card tại revision đã pin](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/aa8e72537993ba99e69dfaafa59ed015b17504d1/README.md): chat template và decode continuation.
- [Transformers model loading](https://huggingface.co/docs/transformers/main_classes/model): revision, dtype và placement.
- [Chat templates](https://huggingface.co/docs/transformers/chat_templating): roles, generation prompt và special tokens.
- [Generation API](https://huggingface.co/docs/transformers/main_classes/text_generation): token budget và greedy decoding.
- [PyTorch inference mode](https://docs.pytorch.org/docs/stable/generated/torch.autograd.grad_mode.inference_mode.html).
- [License tại revision](model_license.md), phạm vi nghiên cứu sinh viên phi thương mại.

Model card có ví dụ auto dtype/device_map; backend của nhóm chủ động chọn FP16 và `model.to(device)` trên một GPU rõ ràng theo yêu cầu dự án. Dùng keyword `dtype` như notebook smoke test đã ghi nhận với Transformers 5.20.2. Code/API chưa được chạy thật trên phiên Kaggle mới; không tự nâng cấp packages chỉ vì model card đề xuất bản mới.

## 2. Backend và cấu hình

`QwenStoryBackend` trong `src/story_generator/qwen_backend.py` giữ Protocol `generate(summary: str) -> str`; StoryGenerator không bị thay đổi. Constructor/import không tải model. Có thể explicit `load()` hoặc lazy load khi gọi generate lần đầu, sau đó cache model/tokenizer đã load thành công trong instance.

| Cấu hình | Baseline |
|---|---|
| Model ID | `Qwen/Qwen2.5-3B-Instruct` |
| Model và tokenizer revision | `aa8e72537993ba99e69dfaafa59ed015b17504d1` |
| Device | `cuda:0`, một GPU rõ ràng |
| Precision | FP16 |
| Generation | `do_sample=False`, `num_beams=1`, `num_return_sequences=1` |
| Budget | `max_new_tokens=1024` |
| Repetition penalty | `1.0`, có thể cấu hình số hữu hạn dương |
| Batch | 1 |
| Remote code | `trust_remote_code=False` |
| Weights | `use_safetensors=True`, không quantization/fine-tuning |

Caller có thể cấu hình device dạng `cuda:N`, token budget, repetition_penalty và cache_dir. Không nhận device_map tự động hoặc kwargs tùy ý làm thay baseline. Cache_dir được truyền cho cả tokenizer/model; không tự log credentials hoặc đọc toàn bộ environment vào metadata.

Default loader kiểm tra GPU khả dụng trước khi gọi Hugging Face loaders, load model FP16 rồi gọi `model.to(device)` và `model.eval()`. Vì không dùng auto placement/offload, cần đủ CPU RAM và GPU VRAM khi load; chưa kiểm chứng tài nguyên cho structured run. Không fallback CPU/mock nếu GPU/dependency không sẵn sàng.

Model.generate chạy trong inference_mode; inputs được chuyển tới cùng device. Chat template dùng `tokenize=False, add_generation_prompt=True`, rồi tokenize với `add_special_tokens=False` để không thêm special tokens lần hai. Backend chỉ decode tokens sau input length, `skip_special_tokens=True`, `clean_up_tokenization_spaces=False`; không strip text/Markdown, không parse hoặc repair JSON, không retry.

Một instance dành cho luồng tuần tự, chưa thread-safe. Load thành công được cache; failure không tự lặp trong một lần generate. Nếu caller chủ động gọi lại load/generate sau load failure thì có thể thử load lại; đây không phải retry policy đã triển khai.

## 3. Prompt baseline và budget

Module `prompts.py` có version **storyboard-v1.0-baseline-001**. System instructions bằng tiếng Anh; phần JSON Schema nhúng được xuất nguyên từ Shared Storyboard model, có thể mang descriptions tiếng Việt từ code schema.

Prompt yêu cầu bốn cảnh chronological/distinct, index integer 1–4, giữ ending/key events, caption Việt, base prompts/visual descriptions Anh, IDs/references hợp lệ, không lặp scenes, không thêm fields hoặc Markdown fences. Custom runtime rules như non-whitespace, uniqueness, index sequence và references được mô tả thêm vì JSON Schema không diễn đạt hết.

User role chỉ chứa JSON object với summary gốc; text trong summary là dữ liệu, không có quyền đổi contract. Không dùng fixture thỏ/rùa hoặc assistant few-shot trong baseline. Đây là instruction boundary được thiết kế, không bảo đảm LLM miễn nhiễm prompt injection hoặc luôn tuân thủ JSON.

Schema được minify để giảm chi phí prompt; lưu input token count thực tế khi chạy Task 08B. Chưa đo prompt tokens/context usage trên tokenizer thật cho baseline này. Không silently truncate input, bỏ schema hoặc đổi prompt khi vượt context; lỗi được propagate. Nếu thay template/schema hướng dẫn, cần bump prompt version và giữ hash/messages của run để tái lập.

## 4. Metadata tách khỏi return value

Backend vẫn trả str. `backend.last_run` là bản deepcopy metadata của lần gọi backend.generate gần nhất, chưa tự ghi file hoặc log. Không chứa model/tensors/credential fields.

Ghi nhận model/revision, prompt version/hash/messages, generation parameters thực truyền và model_generation_config (defaults từ model nếu có), batch/device/precision, input/generated counts, hit_max_new_tokens, raw output và package versions. Parameters truyền trực tiếp override defaults của model. Default runtime đo latency quanh model.generate với CUDA synchronize; reset/query peak allocated VRAM cho device đã chọn, ghi GPU model. Peak tính cả allocation model đang tồn tại, không phải chỉ phần VRAM tăng thêm của generation.

Các loader được inject được gắn `execution_mode="injected"`; không đo latency/VRAM/GPU name, để None thay vì trình bày fake work như inference thật. Token counts trong tests dùng IDs tổng hợp, không phải token counts của Qwen. Metadata giả lập không được xuất thành benchmark.

`hit_max_new_tokens` nghĩa số generated tokens đã đạt budget, có thể gồm EOS. Không phải bằng chứng chắc chắn output bị cắt; EOS có thể xuất hiện đúng token cuối. Backend không tự retry khi chạm budget.

`validation_outcome` ban đầu là `not_checked`: backend không parse JSON. StoryGenerator/caller chịu trách nhiệm schema và summary matching. Khi lưu manifest, caller cập nhật bản metadata copy bằng kết quả thực tế; không tự mô tả generated text là valid trước validation.

Error categories của backend: input_error, load_error, tokenization_error, generation_error, decode_error; giữ exception gốc, không fallback. Lỗi schema/summary được phân loại ở caller, không đổi thành lỗi backend. Nếu StoryGenerator reject input trước khi gọi backend, last_run có thể vẫn là run cũ; không gắn run cũ vào input mới. Tương tự, explicit load() thất bại trước generate cần ghi sự kiện load riêng.

## 5. Workflow Kaggle đề xuất cho Task 08B — chưa chạy

1. Xác nhận quyền sử dụng theo [model_license.md](model_license.md), nguồn input và quyền chia sẻ artifacts.
2. Hardware audit: một T4 được chọn, CUDA available, GPU name/VRAM, CPU RAM/disk; ghi trạng thái cache. Không suy ra hai GPU sẽ tự được dùng.
3. Ghi Python/PyTorch/Transformers/HF Hub/Safetensors/Pydantic versions của session. [requirements-llm.txt](../requirements-llm.txt) chỉ là nhóm inference không lock; CPU requirements không kéo GPU stack. Không chạy cài đặt trong Task 08A; nếu cần cài trong Task 08B phải chọn torch build phù hợp CUDA và được cấp quyền riêng.
4. Kiểm tra access bằng HfApi.model_info với model ID và **revision cố định**, không lấy info.sha mới nhất làm revision. Không in token; không dùng gated/private status để suy ra license.
5. Tạo backend với cache `/kaggle/working/hf_cache`, gọi load() rõ ràng một lần. Việc này có thể tải weights nếu cache thiếu; chỉ thực hiện trong Task 08B đã được cho phép.
6. Chạy một structured inference qua StoryGenerator; lưu input, prompt/version/hash và raw output chưa sửa. Không dùng fixture làm few-shot; không chạy official test set.
7. Ghi runtime schema validation, summary match, errors loc/type. Không gọi đây là semantic validation hoặc đánh giá tổng quát.
8. Lưu run manifest, raw UTF-8 và metrics trong outputs/run riêng; ghi Git commit/source version, timestamp và môi trường thực tế. Đừng đưa credentials/weights vào Git. Raw output lỗi vẫn cần giữ để debug, không thay bằng mock.
9. Cleanup sau khi đã giữ metadata: bỏ references tới backend/model/tensors, gc.collect và torch.cuda.empty_cache. Việc này dành cho notebook/run thực tế, không có GPU cleanup giả trong CPU tests.

Ví dụ dưới đây **chỉ để Task 08B**, không chạy trong Task 08A:

```python
import json
from pathlib import Path
from pydantic import ValidationError
from src.story_generator.qwen_backend import QwenStoryBackend
from src.story_generator.story_generator import (
    StoryGenerator, StoryBackendError, StoryOutputError,
)

# summary là một string hợp lệ đã chọn cho run, không chứa credential.
backend = QwenStoryBackend(cache_dir="/kaggle/working/hf_cache")
backend.load()  # Có thể tải weights; cần quyền riêng trong Task 08B.
generator = StoryGenerator(backend)
validation = {"status": "not_checked"}
try:
    storyboard = generator.generate(summary)
    validation = {"status": "passed", "error_category": None}
except StoryOutputError as exc:
    cause = exc.__cause__
    category = "schema_validation" if isinstance(cause, ValidationError) else (
        "output_type" if not isinstance(exc.raw_output, str) else "summary_mismatch"
    )
    validation = {
        "status": "failed",
        "error_category": category,
        "errors": [{"loc": list(e["loc"]), "type": e["type"]} for e in cause.errors()]
                  if isinstance(cause, ValidationError) else [],
    }
except StoryBackendError:
    validation = {"status": "not_checked", "error_category": "backend_failure"}

manifest = backend.last_run
if manifest is not None:
    manifest["validation_outcome"] = validation["status"]
    manifest["validation"] = validation
    run_dir = Path("/kaggle/working/outputs/structured-run-001")
    run_dir.mkdir(parents=True, exist_ok=False)  # Không ghi đè run cũ.
    raw = manifest["raw_output"]
    if isinstance(raw, str):
        (run_dir / "raw_output.txt").write_text(raw, encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

Ví dụ không bắt input error vì summary phải được kiểm tra trước; không save dữ liệu từ last_run cũ. Bổ sung timestamp/Git SHA/hardware audit và xử lý explicit-load failure trong notebook Task 08B. Không tự bỏ lỗi generation/validation để tiếp tục pipeline ảnh.

## 6. CPU tests và giới hạn

```bash
.venv/bin/python -m pytest tests/test_qwen_backend.py tests/test_story_prompts.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Fakes mô phỏng tensor shape/slicing, tokenizer/model factory và inference context, không cài/import GPU packages thật. Tests xác nhận logic/API/exception chains và mock vẫn hoạt động; chưa xác nhận compatibility thực thi trên Kaggle, VRAM, latency, JSON success rate, prompt budget hoặc chất lượng Vietnamese/English của Qwen. Semantic Validation và Repair nằm ngoài Task 08A.
