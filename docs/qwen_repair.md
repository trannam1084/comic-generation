# Concrete Qwen Deterministic Repair Backend — Task 09C.2

TV1 — Trần Hải Nam. Implementation chạy trên shared Qwen runtime đã có, được kiểm thử CPU bằng injected doubles. **Chưa có GPU repair results, chưa chứng minh repair effectiveness.** Không sửa story generation prompt hoặc semantic reviewer V1/V2; không tích hợp ComicPipeline.

## Public API và ownership

```python
from src.story_generator.qwen_backend import QwenStoryBackend
from src.story_generator.repair import BoundedRepairController

backend = QwenStoryBackend(loader=scripted_loader)  # CPU double do test/caller cung cấp.
controller = BoundedRepairController(
    initial_backend=backend,
    repair_backend=backend,
    max_retries=2,
)
result = controller.generate(original_summary)
```

`scripted_loader` giữ nguyên injection API: nhận model_id, revision, device và cache_dir; trả `(tokenizer, model, runtime)`. Ví dụ trên chỉ minh họa wiring; không phải inference thật. Trong runtime GPU đã được phê duyệt, bỏ loader để dùng default loader; thao tác đó có thể tải weights và không được thực hiện trong task CPU này.

API mới của `QwenStoryBackend`:

- `generate_repair(feedback: RepairFeedback) -> str`: tối đa một `model.generate`, trả decoded continuation nguyên trạng.
- `last_repair`: deep-copy metadata snapshot của repair invocation gần nhất, hoặc None nếu chưa gọi.

Backend không parse/validate output Storyboard, không strip fences, retry/fallback hoặc gọi Semantic Reviewer. Controller chịu trách nhiệm deterministic validation, acceptance và budget; `StoryBackend.generate` và `StoryGenerator.generate` giữ contract cũ. Bốn scenes hợp lệ về cấu trúc không chứng minh nội dung đúng ngữ nghĩa.

## Repair prompt và data boundary

Module `src/story_generator/repair_prompts.py` xuất:

- `REPAIR_PROMPT_VERSION = "storyboard-repair-v1.0-deterministic-001"`.
- `build_repair_messages(feedback) -> list[dict[str, str]]`.

Builder trả đúng hai messages: English system instructions và user JSON data. System nhúng nguyên JSON Schema từ `Storyboard.model_json_schema()`; bổ sung constraints không biểu diễn đầy đủ trong schema: exact original summary, non-whitespace text, integer scene indices [1,2,3,4], unique case-sensitive IDs và valid/unique references. Yêu cầu complete JSON, Vietnamese captions, English base prompts/shared visuals, giữ nhân vật, major events và ending từ original summary; không extra fields, explanations, Markdown fences hoặc JSON patch.

User JSON có đúng original_summary, previous_raw_output, attempt_index và errors (code/severity/location/message/evidence). Independent original_summary là nguồn chính; failed candidate không phải source of truth. Không buộc giữ semantic mistakes trong candidate. Không parse/extract/sửa candidate trước inference; malformed text, fences hoặc chuỗi rỗng vẫn được giữ nguyên dưới dạng data.

Builder yêu cầu actual RepairFeedback instance và revalidate snapshot để phát hiện nested mutation. Summary không rỗng/whitespace, attempt index là integer >=1, errors không rỗng và chỉ chứa ba deterministic error codes với severity error. Reject wrong types, non-finite evidence hoặc invalid UTF-8 trong mọi string/key được gửi. Giữ Python strings/keys trước JSON serialization để tránh thay thế invalid Unicode keys; tuple locations trở thành JSON arrays. Không normalize NFC/NFD, trim hoặc dùng errors=ignore/replace. Escaped surrogate sequence trong raw ASCII text là data, không tự decode thành candidate mới.

Toàn bộ feedback, kể cả issue messages và evidence, được coi là untrusted data. Không nối nội dung của chúng vào system message; không thêm model logs, backend metadata, annotations, reviewer predictions, stack traces hoặc credential fields vào prompt. Boundary giảm injection risk, không bảo đảm model chống prompt injection tuyệt đối. Caller phải bảo đảm dữ liệu đầu vào không chứa credentials; giữ nguyên raw không đồng nghĩa tự phát hiện/redact mọi secret trong raw.

## Shared runtime và model preservation

Cả generate, review và generate_repair đều gọi shared `_generate_messages()`; không duplicate loader/tokenization/inference/decode. Một backend instance cache model/tokenizer/runtime sau lần load thành công và dùng lại tuần tự; không tạo model thứ hai cho repair.

Model và tokenizer giữ revision `aa8e72537993ba99e69dfaafa59ed015b17504d1` của `Qwen/Qwen2.5-3B-Instruct`; default cuda:0, FP16, batch 1, greedy, max_new_tokens=1024, repetition_penalty=1.0, num_beams=1, num_return_sequences=1. Không quantization, device_map tự động hoặc trust_remote_code. Existing loader injection và raw decoding policy giữ nguyên. Không có thread-safety claim.

## Metadata routing và isolation

| Inference purpose | Public snapshot |
|---|---|
| story_generation | last_run |
| semantic_review | last_review |
| story_repair | last_repair |

Unsupported internal purposes bị từ chối trước prepare/load và không ghi vào slot bất kỳ. Mỗi supported invocation tạo fresh call_id và metadata slot tương ứng **trước** input preparation; failed repair không tái dùng successful metadata cũ. Generate/review không ghi đè last_repair; repair không ghi đè last_run/last_review.

Repair snapshot có purpose/version/hash/messages, model/revision, generation parameters, execution mode/device/precision/batch, package versions, token counts khi đã có, raw output, error_category và hit_max_new_tokens. Prompt hash là SHA-256 của actual messages theo cùng JSON serialization đã dùng cho baseline. Input failure chưa build được prompt thì không tạo prompt hash giả.

Default GPU runtime đo generation_latency_seconds quanh model.generate với CUDA synchronize. Peak allocated VRAM bao gồm allocations của model đã tồn tại. End-to-end controller time khác model latency; hit_max_new_tokens không chứng minh chắc chắn truncation. Injected doubles để latency/VRAM/GPU name là None; synthetic token IDs không phải đo token usage Qwen.

Controller chỉ capture public snapshots có fresh call_id, raw alignment và JSON/UTF-8-safe allowlisted metadata. Task này bổ sung kiểm tra purpose nếu field được cung cấp: initial phải story_generation, repair nhận canonical story_repair hoặc legacy alias repair của generic backends; explicit mismatch bị discard, không đổi acceptance hoặc retry. Legacy optional metadata thiếu purpose giữ compatibility Task 09C.1; concrete Qwen luôn dùng canonical story_repair và không route alias trong shared runtime. Không gửi metadata vào repair feedback và không coi metadata bị discard là lỗi Storyboard.

## Acceptance, failure và context limit

Default max_retries=2 nghĩa một initial generation và tối đa hai repair attempts. Baseline max_retries=0 vẫn chỉ initial. Chỉ INVALID_JSON, SCHEMA_VIOLATION và SUMMARY_MISMATCH có thể kích hoạt repair; warnings và semantic verdict không tham gia.

Backend giữ exception gốc. Các phases input_error, load_error, tokenization_error, generation_error và decode_error có fresh metadata, không retry hoặc fallback. Controller dừng backend_failure với partial history khi backend exception, wrong output type hoặc Unicode transport failure. Unexpected validator errors giữ exception chaining theo contract controller.

Full feedback, previous raw và schema có thể vượt context window, nhất là raw dài/malformed. Implementation không tự truncate, bỏ errors/schema, tăng max_new_tokens hoặc đổi sampling để chạy tiếp; tokenization/generation failures được propagate. Chưa đo repair prompt token budget trên tokenizer thật. Trước GPU run cần kiểm tra context/resources và được phê duyệt riêng; CPU tests không chứng minh model xử lý được candidate dài.

## CPU verification và giới hạn

```bash
.venv/bin/python -m pytest tests/test_repair_prompts.py tests/test_qwen_repair_backend.py -q
.venv/bin/python -m pytest tests/test_qwen_backend.py tests/test_repair_controller.py tests/test_story_prompts.py tests/test_semantic_validation.py tests/test_semantic_prompt_variants.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
git diff --check
```

Tests dùng synthetic feedback/scripted continuation, không official Dev/Test data hoặc human annotations. Kiểm tra initial success, deterministic failures rồi repair, second repair, exhaustion, infrastructure failures, one-load/no-retry, metadata isolation, baseline regression và Unicode/data boundary. Chúng chứng minh phần mềm điều phối đúng; không chứng minh repair cải thiện semantic correctness hoặc thực nghiệm Qwen repair thành công. Semantic reviewers vẫn chỉ phục vụ offline analysis; không có semantic-triggered repair hoặc Repair efficacy benchmark.

Kết quả local Task 09C.2: 84 repair prompt/backend tests PASS; 297 existing Qwen/controller/story-prompt/semantic regression tests PASS; full CPU suite 699 PASS, không failed/skipped/errors. pip check PASS. Không thay đổi package versions hoặc chạy GPU/API inference trong task này.
