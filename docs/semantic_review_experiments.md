# Semantic Reviewer v2 — Evidence-first development variant

## 1. Phạm vi và trạng thái

Task 09B.3A thêm variant explicit `storyboard-semantic-review-v2.0-evidence-first-001`.
Reviewer v1 `storyboard-semantic-review-v1.0-001` vẫn là default và không bị thay thế.
Chưa chạy GPU/API inference, chưa có raw responses hoặc kết quả chất lượng của v2.
Đây là giả thuyết cần kiểm chứng, không phải cải tiến đã được chứng minh.
Baseline story generation prompt, Qwen backend/model/revision, Shared Storyboard Schema,
semantic response schema và Repair policy không thay đổi. Chưa triển khai Repair Controller.

## 2. Evidence thực tế của S0: reviewer v1

Nguồn là ZIP Task 09B.2B, session `20261119T165713Z-8b17fe9c43`:

```text
580a56a88216e3766f7aec0096231b36b39b6425573e5b0f12eeebd5983b8930
```

Đã xác minh archive hash trước đọc, 69 members, 68 internal checksums, CRC,
member whitelist, duplicate paths, traversal và symlinks. Không sửa raw outputs,
reports, manifests hoặc annotation files. Tám raw reviewer responses khớp report.raw_reviewer_output.

| Case | Review status | Verdict | Issues | Actual explanation từ raw response |
|---|---|---|---|---|
| smoke_001 | completed | pass | [] | Storyboard accurately depicts the original summary without any issues. |
| pilot_001 | completed | pass | [] | Storyboard accurately depicts the original summary without any issues. |
| pilot_002 | completed | pass | [] | Storyboard accurately depicts the events and characters as described in the original summary without any issues. |
| pilot_003 | completed | uncertain | [] | Storyboard captions and image prompts do not provide enough evidence to determine if there are any issues with character identities, roles, fragmentation, object translation, visual language, key events, ending, or unsupported events. The provided information is consistent with the Vietnamese summary. |
| control_001 | completed | pass | [] | Storyboard accurately depicts the events described in the Vietnamese summary without any discrepancies. |
| control_002 | completed | pass | [] | Storyboard accurately depicts the original summary without any issues. |
| control_003 | completed | pass | [] | Storyboard accurately depicts the sequence of events as described in the Vietnamese summary. The actions, characters, and objects are consistent with the summary. |
| control_004 | completed | pass | [] | Storyboard accurately depicts the original summary without any discrepancies. |

Không có JSON/schema/evidence contract failures hoặc token-budget hits. Mọi issue list rỗng:
evidence validation không bị lỗi nhưng grounding của evidence **không rỗng** chưa được run này
kiểm chứng. Không suy ra tám storyboards đúng semantic hoặc reviewer đã phát hiện được lỗi.
`pilot_003` vẫn summary mismatch; semantic completed/uncertain không tạo production acceptance.
Hai error-control candidates nhận pass mà không có issue; chưa có human-confirmed labels để
công bố false-negative rate, accuracy, precision hoặc recall.

Generation regression smoke trong cùng run khớp Task 08B về prompt hash, model revision,
generation configuration và raw output. Điều này chỉ là quan sát một lần chạy, không chứng minh
GPU numerical equivalence tổng quát. Shared runtime đã hoạt động trên GPU với một explicit load,
một story generation và tám review calls; v2 mới chỉ có CPU fake tests.

## 3. Giả thuyết evidence-first

V1 trình bày response schema theo thứ tự verdict, explanation, issues. Một giả thuyết là việc
chọn verdict sớm có thể khuyến khích model hợp lý hóa kết luận rồi bỏ qua issue discovery.
Artifacts không chứng minh nguyên nhân này: self-review bias, model capacity, instruction following,
language understanding hoặc prompt complexity cũng có thể ảnh hưởng. Không gán causality từ
một development pilot không có experiment đối chứng.

V2 yêu cầu tìm supported issues trước, rồi viết explanation ngắn và verdict cuối cùng.
Checklist bao phủ independent original summary; toàn bộ catalog/references; actor/action/object
alignment giữa nguồn/caption/prompt; major causal events và ending; English visual descriptions.
Tám semantic codes giữ nguyên. Không ép phải tìm lỗi, không dùng quota issues tối thiểu,
không thêm few-shot hoặc case-specific expected answers. Cho phép uncertain khi thiếu căn cứ.
Không yêu cầu chain-of-thought hay checklist transcript trong response.

Exact evidence cần quote đúng source/path; contradiction nên quote hai phía khi có.
Omission dùng quote sự kiện có trong source và location storyboard liên quan, không bịa
quote của một đoạn vắng mặt. Prompt không tự chứng minh reasoning hay kết luận semantic đúng.
Data boundary giảm rủi ro prompt injection, không bảo đảm chống injection tuyệt đối.

## 4. Public API và compatibility

```python
from src.storyboard.semantic_prompts import (
    EVIDENCE_FIRST_PROMPT_VERSION, build_semantic_messages,
)
from src.storyboard.semantic_validator import SemanticStoryboardValidator

# Không thay đổi caller cũ: default vẫn là v1.
v1 = SemanticStoryboardValidator(backend)

# V2 phải chọn explicit. Dùng cùng backend đã load, không tạo model thứ hai.
v2 = SemanticStoryboardValidator(backend, prompt_version=EVIDENCE_FIRST_PROMPT_VERSION)
report = v2.validate(original_summary, storyboard)

messages = build_semantic_messages(
    original_summary, storyboard, prompt_version=EVIDENCE_FIRST_PROMPT_VERSION,
)
```

`prompt_version` là keyword-only. Version ngoài allowlist bị từ chối bằng ValueError khi
cấu hình validator hoặc gọi builder; không gọi reviewer hoặc âm thầm fallback v1.
Không thay chữ ký backend.review(messages, prompt_version=...). Consumer không đọc private
fields của Qwen backend. Một validate invocation tối đa một review call; source invalid dừng trước call.

Default v1 giữ nguyên system/user messages cho cùng input, bao gồm serialization/schema presentation.
V2 dùng cùng SemanticReviewResponse.model_json_schema(), chỉ reorder properties và required trong
bản trình bày mới thành issues, explanation, verdict. Không thêm domain model, sửa validators,
nới extra fields hoặc thay tám codes/verdict/runtime status policies.

JSON key order là hướng dẫn generation, **không phải validation rule mới**. JSON đúng contract
vẫn được nhận khi model trả verdict trước issues; không sort/rewrite raw response. Report/model_dump
vẫn theo public Pydantic model hiện có. Không thay schema để đạt field order.

Parser strict duplicate-key/non-finite policy, Unicode transport, exact NFC/NFD evidence matching,
location checks, raw preservation và error categories đều giữ nguyên. Evidence quote hợp lệ về
cấu trúc/grounding không đồng nghĩa issue đúng ngữ nghĩa. Không tích hợp production acceptance.

Provenance và backend metadata dùng đúng selected prompt_version và hash của full messages từng call.
Không chấp nhận metadata fresh nhưng gắn sai version/hash. last_review là snapshot review gần nhất,
không phải một history store theo variant; caller cần lưu report/snapshot ngay sau mỗi call.
last_run của generation không bị review ghi đè. Không thêm thread-safety claims.

## 5. Freeze và thiết kế comparison

System prompt + schema presentation v2 được freeze local trước khi tạo hai exploratory cases mới.
Các hashes tại môi trường CPU Pydantic 2.14.3:

| Thành phần | SHA-256 |
|---|---|
| V1 system message | 179c1420e52d0ff83b7b0716dee0679f29da10252c71225e2da7ab2e29ce2862 |
| V2 system message | 0602c2601e681f2a6e078e1d657122ec769b99e1128e0daddd1f6888ec3462e1 |

Đây là hashes template + schema, không phải per-input full-message hash. Schema/dependency drift
cần kiểm tra lại trước experiment; không mặc định package versions khác luôn tạo cùng messages.
Local freeze chưa phải source commit đã publish hoặc quyền chạy GPU.

- S0: giữ artifacts reviewer v1 đã có; không rerun hoặc regenerate baseline storyboards.
- S1: v2 trên đúng tám original summaries/raw storyboards cũ và cùng configuration.
- Dùng Qwen/Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1,
  FP16/cuda:0/batch 1, greedy, max_new_tokens=1024, repetition_penalty=1.0,
  num_beams=1, num_return_sequences=1. Không Repair/retry/fallback hoặc tăng token budget.
- Đây là prompt tuning trên development cases đã quan sát; không phải held-out evaluation.
  Không dùng official Test dataset.
- Freeze input hashes, prompt/source revisions, package/runtime audit và cùng execution policy.
  So sánh latency với thận trọng vì hardware/session/cache có thể khác, không chỉ prompt.
- Ghi đầy đủ response syntax/schema/evidence failure, abstention, issue counts/codes,
  token-budget hits, token usage, latency/VRAM và failed/not_checked records với denominator rõ.
  Không chỉ chọn cases hoặc runs có kết quả thuận lợi.

Gói ngoài repository tại `../comic-generation-experiments/task09b3a/`:

- prompt_freeze.json: hashes/version/timestamp trước exploratory case authoring.
- comparison_design.json: S0/S1 design, tám baseline raw hashes và cấu hình.
- exploratory/inference_inputs.json: hai stories mới, cùng Shared Storyboard Schema.
- design_notes/exploratory_provenance.json: AI design intents, chưa human confirmation;
  tách khỏi inference inputs và không đưa vào model prompt.

Hai cases mới: explore_001 về người quản thư và sách bị ướt; explore_002 về người gác đèn biển.
Một clean candidate và một object-translation mismatch candidate được thiết kế sau freeze,
chưa có predictions. Chúng độc lập về nội dung với tám cases cũ nhưng cùng taxonomy và do AI hỗ trợ,
nên vẫn có author bias. Đây chỉ là exploratory transfer check sau freeze, không là official held-out
benchmark. Nếu tiếp tục tune sau khi xem predictions thì phải ghi rõ đó là vòng development mới.

## 6. Human annotation và giới hạn

Giữ nguyên annotation package Task 09B.2A. Không sửa labels theo reviewer predictions.
Annotators review independent original summary, catalog/references, captions và image prompts;
lưu code/severity/location/evidence cùng uncertainty, reviewer và adjudication information.
Phải chốt issue matching policy, denominators, cách xử lý abstention/reviewer failure trước metrics.
Không dùng AI suggestions hoặc mutation intent làm human ground truth. Nên annotate độc lập trước
khi xem predictions; nếu đã nhìn thấy S0 predictions, ghi rõ exposure và cân nhắc annotator độc lập.

Chưa có human-confirmed annotations nên chỉ báo inference observations; không tính semantic accuracy,
precision/recall hoặc false-positive/false-negative rates. control_004 có thể là implicit event/compression;
không ép thành missing-event label. Grounding pass có thể vẫn reasoning sai; model có thể bịa rationale,
bỏ sót issue, overflag sáng tạo vô hại hoặc không tuân thủ evidence-first ordering. V2 dài hơn v1 có thể
tăng input-token cost và chưa chắc hiệu quả với budget 1024; không tự thay budget hoặc truncate inputs.

## 7. CPU verification và phần chưa triển khai

```bash
.venv/bin/python -m pytest tests/test_semantic_prompt_variants.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Tests kiểm tra v1 hash, explicit v2/version/hash, schema presentation không đổi semantics,
independent source/data boundary, strict parser, exact evidence/location, metadata isolation,
shared model load một lần, source failures và không retry/Repair. Fakes chỉ chứng minh wiring và
software contract; không tạo semantic reviewer outputs thực tế hoặc GPU accuracy evidence.

Chưa có S1 Kaggle notebook/upload/run approval, published source SHA cho variant, human labels,
semantic quality comparison hoặc Repair Controller. Không sửa notebooks 02/05/06/07 hay baseline artifacts.
