# Bounded Deterministic Repair Controller — Task 09C.1

Implementation TV1 — Trần Hải Nam. Controller đã có CPU tests với scripted backends. Task 09C.2 bổ sung [concrete Qwen repair backend/prompt](qwen_repair.md) trên shared runtime; chưa có thực nghiệm repair bằng model thật hoặc ComicPipeline integration.

## Contract và Dependency Injection

Module `src/story_generator/repair.py` sử dụng trực tiếp `StoryboardValidator` và Shared `Storyboard`; không khai báo schema truyện mới. Các contract cũ được giữ nguyên:

- `StoryBackend.generate(summary: str) -> str`: initial generation trả raw JSON.
- `StoryGenerator.generate(summary: str) -> Storyboard`: luồng một lần sinh hiện có, không bị thay đổi.
- Controller nhận raw backend riêng vì cần giữ output thất bại trước khi parse; không gọi StoryGenerator rồi làm mất raw/history qua exception.
- `RepairBackend.generate_repair(feedback: RepairFeedback) -> str`: một generation attempt mới. Caller inject implementation; controller không sở hữu model hoặc inference prompt. QwenStoryBackend.generate_repair dùng chung cached runtime với initial generation.

```python
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.repair import BoundedRepairController
import json
from pathlib import Path

# Chạy từ repository root, chỉ hỗ trợ summary đúng fixture của MockStoryBackend.
summary = json.loads(Path("examples/storyboard.json").read_text(encoding="utf-8"))["summary"]
controller = BoundedRepairController(MockStoryBackend(), max_retries=0)
result = controller.generate(summary)
assert result.status == "accepted_initial"
assert result.storyboard is not None
print(result.model_dump_json(indent=2))
```

Khi bật repair: `BoundedRepairController(initial_backend, repair_backend, max_retries=2)`. Budget dương yêu cầu backend có method `generate_repair`; baseline `max_retries=0` không cần repair backend. Constructor từ chối bool, non-integer hoặc số âm; interface không callable bị TypeError. Không thay backend thật bằng mock khi lỗi.

## Algorithm và acceptance policy

1. Kiểm tra original summary: str không rỗng/whitespace, encode UTF-8 strict được. Giữ nguyên whitespace hợp lệ, Unicode và case.
2. Attempt 0 gọi initial backend đúng một lần.
3. Gọi `validator.validate_raw(raw, expected_summary=original_summary)` trên từng raw mới.
4. Chấp nhận chỉ khi `production_success is True` và JSON syntax, structural validity, exact summary matching đều `passed`.
5. Nếu có hard errors hợp lệ và còn budget, tạo feedback rồi gọi repair backend một lần. Validate raw mới từ đầu, không dùng lại kết quả validation trước.
6. Dừng ngay khi accepted, backend failure hoặc hết budget. Attempts 1 và 2 là hai repair mặc định; tối đa ba backend method calls. Với baseline chỉ có một initial call.

Chỉ ba hard codes kích hoạt repair: `INVALID_JSON`, `SCHEMA_VIOLATION`, `SUMMARY_MISMATCH`. `UNUSED_CHARACTER`, `DUPLICATE_VISUAL_DESCRIPTION`, `DUPLICATE_SCENE_CAPTION` vẫn là warnings; output warnings-only được accepted mà không repair.

Không strip fences, extract JSON, tự thêm/sort scenes, overwrite summary, normalize Unicode hoặc tạo fallback storyboard. Repair là generation mới, không phải thao tác sửa dictionary trong controller. Các backend inject phải thực hiện contract một attempt, không tự retry ngầm.

`ValidationReport` hiện không trả nested Storyboard. Vì vậy chỉ sau khi accepted, controller materialize `Storyboard.model_validate_json(raw)` thêm một lần để trả Shared Storyboard. Không thay API validator hay policy parser Task 09A: duplicate object keys vẫn theo hành vi hiện có của parser, không thêm rejection rule; non-finite literals vẫn theo `allow_inf_nan=False`. Đây không phải validation/repair framework thứ hai.

## Feedback và attempt history

`RepairFeedback` chứa đúng:

- `original_summary`: independent input nguyên văn.
- `previous_raw_output`: output ngay trước đó, nguyên văn khi UTF-8 hợp lệ.
- `attempt_index`: index của repair sắp gọi, bắt đầu từ 1.
- `errors`: chỉ hard errors, gồm code, severity, location, message và relevant evidence. Schema evidence chỉ giữ Pydantic error type; report gốc vẫn giữ đầy đủ details.

Feedback không chứa backend metadata, stack traces hoặc environment. Backend nhận deep copy; việc sửa nested errors/evidence ở backend không thay canonical feedback hoặc report đã lưu. Raw strings bất biến; caller không nên thay nested lists/models của kết quả sau khi truyền qua module. Top-level record frozen không làm toàn bộ object graph immutable; cập nhật Storyboard phải validate lại.

Mỗi `RepairAttempt` lưu index, `initial`/`repair`, raw preservation mode, validation report, canonical feedback nếu có, metadata snapshot/status, failure category, diagnostics và `elapsed_seconds`. Thời gian attempt đo wall time quanh backend method (có thể gồm load nếu backend lazy), không được gọi là `model.generate` latency. `RepairResult.elapsed_seconds` đo toàn bộ invocation. Không tự tạo model token/VRAM metrics.

Optional metadata đọc qua public `last_run` (initial) hoặc `last_repair` (repair). Chỉ capture snapshot JSON/UTF-8-safe có fresh `call_id` và raw khớp call hiện tại; thiếu identity, stale/mismatch hoặc getter/serialization lỗi thì discard và ghi diagnostic. Backend không hỗ trợ metadata vẫn hoạt động. Allowlist chỉ giữ provenance/generation metrics/parameters/package versions; không copy arbitrary runtime dictionaries, credentials hay messages. Snapshot là deep copy, không live reference. Fresh partial raw từ metadata có thể được giữ khi backend exception; stale metadata không được tái sử dụng. Nếu metadata có purpose, initial phải story_generation; repair nhận canonical story_repair hoặc legacy alias repair đã có trong generic backends. Sai purpose bị discard. Legacy optional metadata thiếu purpose giữ behavior cũ; concrete Qwen luôn cung cấp canonical story_repair. Không retry để lấy metadata.

## Result và failure handling

| Status | Ý nghĩa | Storyboard |
|---|---|---|
| `accepted_initial` | Attempt 0 đạt ba gates | Shared Storyboard |
| `accepted_after_repair` | Một repair đạt ba gates | Shared Storyboard |
| `budget_exhausted` | Hết budget, tất cả raw còn invalid | None |
| `input_failure` | Original summary sai kiểu/rỗng/Unicode transport | None |
| `backend_failure` | Backend exception, output sai kiểu hoặc không transport UTF-8 được | None |

Backend loading/CUDA/OOM/transport exceptions đều dừng ngay, không kích hoạt repair hoặc model fallback. Report giữ exception type chain nhưng không chép exception messages/stack traces có thể chứa credentials. Caller có thể sử dụng backend public error metadata theo allowlist. `backend_output_type` không được chuyển dict/bytes/None thành str.

Unexpected validator/materialization failure không bị gán nhầm thành lỗi model: raise `RepairControllerError` với `failure_category="validation_failure"`, partial `.attempts` và original exception ở `__cause__`. Nếu gate/error contract bất nhất cũng dừng bằng exception này. Không gọi thêm backend trong các trường hợp đó.

## Unicode transport và raw preservation

- Original summary chứa lone surrogate: `input_failure/invalid_summary_unicode`, không gọi backend; original_summary trong result là None, có diagnostic được gắn nhãn `python_unicode_escape`.
- Backend trả literal surrogate trong Python str: `backend_failure/invalid_output_unicode`, dừng, không gửi nó vào repair request. `raw_output=None`, preservation `escaped_diagnostic`; diagnostic có `original_utf8_preserved=false` và escaped text. Đây không phải nguyên raw UTF-8 và không phải text đã repair.
- Raw JSON có escaped surrogate sequence nhưng raw text encode UTF-8 được: giữ nguyên và đưa qua deterministic parser. Kết quả parser hiện có quyết định error; controller không decode/sửa sequence để vượt gate.
- Unicode scalar hợp lệ, tiếng Việt, emoji, NFC/NFD được giữ nguyên. Exact summary không tự normalize hai dạng thành giống nhau.

Các records thông thường serialize bằng `model_dump_json()` và ghi UTF-8 được. Unexpected lỗi của validator có history/exception contract riêng, không sanitize report hỏng để tiếp tục.

## Semantic boundary và experimental evidence

Theo kết quả development nhóm trưởng cung cấp từ Task 09B.3B.2: historical V1 có 8/8 completed nhưng không issues; V2 có 1/10 completed và 9 schema failures, 13 raw proposed issues nhưng 0 accepted grounded issues. Không token-budget hits hoặc infrastructure failures. Các số liệu này không được chạy lại trong Task 09C.1 và không phải official benchmark.

Chưa có human-confirmed annotations; không suy ra accuracy/precision/recall hoặc repair effectiveness. V1/V2 giữ để offline analysis, không tham gia production hard gate hoặc automatic repair trigger. Structurally accepted không chứng minh semantic correctness. Controller không import/call semantic reviewer.

## Kiểm thử và giới hạn

```bash
.venv/bin/python -m pytest tests/test_repair_controller.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Scripted doubles kiểm tra orchestration, budget, feedback/history, warnings policy, failure handling, metadata isolation và Unicode; không tải model/network/GPU. Tests không chứng minh model có thể sửa đúng truyện. Concrete backend/prompt đã có trong Task 09C.2; muốn thử repair thật vẫn cần phê duyệt inference riêng và human evaluation. StoryStage/ComicPipeline integration, semantic-triggered repair và Repair efficacy evaluation chưa triển khai.
