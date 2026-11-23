# Chuẩn bị offline evaluation — Task 11A

Trạng thái: CPU preparation, chưa chạy official evaluation. Package TV1
`src/offline_evaluation/` độc lập với `src/evaluation/` của TV3 và không gọi
`ComicPipeline`, Qwen, semantic reviewer hoặc image inference. Không thay production
schemas, prompt, repair policy hoặc rubric đang ở PR #20.

## Specification và source of truth

Bốn tài liệu TV1 cung cấp được đọc như proposed specification, không phải lệnh
cho phép inference, publish hoặc tạo human gold. SHA-256 của bytes đã đọc:

| Tài liệu | SHA-256 |
| --- | --- |
| TASK11_EVALUATION_PROTOCOL.md | `c8ea4595bf2d02e70b28cb91ff8856640a9668cb4b0ec24b2b82dfc3a31da5fd` |
| EVIDENCE_AND_RELEASE_CHECKLIST.md | `0dc0cfc675c916fbe8a315358cd91e55c03007f7bde462c149ad1730904976e7` |
| evaluation_plan.template.json | `38a6e5db09e48323e30b36a15580f8a8abad23af2ecac910931f0ba614b7a05b` |
| human_annotation.template.json | `29b7f1afb84b1765572ecb4e3642866abfd457afede1cd44989b3917f6db2130` |

Production contracts được đối chiếu trực tiếp:
[Shared Storyboard](../src/storyboard/schema.py),
[deterministic validator](../src/storyboard/validator.py),
[RepairResult và attempts](../src/story_generator/repair.py),
[semantic schema](../src/storyboard/semantic_schema.py) và
[semantic validator](../src/storyboard/semantic_validator.py).
Exact evidence theo production là **exact substring** của string tại source/path
đã chỉ định, không phải normalize Unicode hoặc quote từ field khác.
Evaluation không thay JSON parser policy của deterministic validator.

Hai JSON templates đính kèm có version draft và placeholders/null. Chúng không
phải frozen records; không tự điền approval hay đổi `draft_not_approved` thành
approved. Contract evaluation riêng có version `task11-offline-v1`, strict types,
extra fields bị reject, UTF-8 strict, duplicate JSON keys ở mọi cấp và non-finite
numbers bị reject. Đây là parsing policy của evaluation artifacts, không áp dụng
lại lên nội dung raw storyboard strings.

## Public API và dữ liệu

- `EvaluationPlan`: `status="frozen"`, source commit, model revision, story/repair
  system-message hashes, policy hash, `cases`, `planned_runs`, dataset gates và
  optional rubric version. Mỗi case có independent summary byte hash và origin.
  `planned_runs` phải có đúng một B0 và B1 cho mỗi ID; duplicate IDs bị reject.
- `PairedCaseResult`: independent `original_summary`, exact shared `initial_raw`,
  hoặc initial failure với explicit `initial_failure_stage` (`input_validation/backend`);
  hai `VariantResult` B0/B1. Mỗi variant có
  state `completed/failed/not_run`, initial hash, production `RepairResult` hoặc
  partial `RepairAttempt` history cho unexpected validator failure, và failure reason.
- `InferenceCost`: ledger của actual backend invocations, unique `call_id` và unique
  `(case_id, attempt_index)`. Purpose `story_generation/story_repair`; attempt index
  0/1/2; completed/failed; raw/prompt hashes; measured tokens, model latency, backend
  wall time, VRAM và budget hit khi có. Replay không có ledger entry. `model_generate_calls`
  nhận 0/1 khi có explicit `model_generate_count_source="observed"`; nếu không có
  independent observation thì để null và source `not_available`. Không derive từ
  `RepairAttempt` count hoặc từ việc backend đã được gọi.
- `EvaluationInput`: explicit offline batch gồm `plan`, `pairs`, `costs`.
- `evaluate_pairs(plan, pairs, costs) -> dict`: revalidate records, inventory,
  summary hashes, shared raw hashes, attempt order/budget/feedback và stored reports
  bằng production validator. Accepted Storyboard phải khớp accepted raw. Không
  gọi controller hoặc backend. Missing/extra paired cases và extra physical calls
  bị reject; phải cung cấp explicit not-run records.
- `ArtifactReference`, `verify_reference(reference, payload)`: xác minh byte hash
  trên bytes caller cung cấp; không tự mở path trong untrusted record.
- `parse_record(raw_bytes, Model)`: strict parsing; `json_bytes(record)` cung cấp
  canonical UTF-8 serialization cho evaluation artifacts.
- `blank_annotation(...)`: template pending, verdict null, findings rỗng,
  adjudicated false. Không tạo human labels.
- `annotation_readiness(...)`, `prepare_semantic_matches(...)`: kiểm tra provenance,
  gold gate, traceable evidence và chuẩn bị matches; **không tính semantic scores**.
- `write_session(parent, artifacts)`: tạo atomic unique `evaluation-*` directory,
  exclusive writes và `checksums.json`; flat artifact whitelist do caller cung cấp.
  Không overwrite prior run. Nếu write thất bại, giữ partial directory để audit.

Model metadata trong production attempts là optional. Nếu repair metadata có sẵn,
ledger phải khớp call ID, revision, prompt hash và các measurements được cung cấp.
Generic backend metadata có thể thiếu purpose hoặc dùng alias `repair` theo controller
contract; không bắt generic backend giả Qwen metadata. Các measurements trong ledger
là dữ liệu caller nhập từ artifacts đã xác minh, harness không chứng minh lại rằng GPU
đã thực thi. System hashes trong plan không phải per-input full-message hashes.

## TV3 Event Inventory integrity gate

Khi tính Event Coverage/Event Order trên annotation đã adjudicate, nên bật
inventory gate bằng file `data/dev_key_event_alignment_team_approved.csv`.
Loader chỉ nhận các dòng có đồng thời:
- `event_reference_status=approved_reference`;
- `team_confirmation_status=team_confirmed`;
- `aligned_key_event` không rỗng.

Các dòng bị loại chỉ được bỏ qua khi hai trạng thái loại trừ khớp nhau:
`excluded_from_event_reference` và `excluded_from_reference`.
Trạng thái lẫn lộn hoặc pending bị từ chối, không tự suy diễn thành approved.
Mỗi event được ánh xạ ổn định thành `E{event_no}`; thứ tự được sắp theo
`event_no`. Trước khi tính metric, evaluator yêu cầu tập case ID và tập
Event ID annotation khớp chính xác inventory; thiếu/thừa/trùng đều dừng bằng lỗi.

Ví dụ chạy Dev từ repository root:

```bash
python -m src.evaluation.evaluate /path/to/dev_event_annotations.jsonl \
  --json-out outputs/dev_evaluation.json \
  --csv-out outputs/dev_evaluation_cases.csv \
  --event-inventory-csv data/dev_key_event_alignment_team_approved.csv \
  --event-inventory-split Dev
```

Gate này kiểm tra tính đầy đủ và provenance trạng thái của event reference; nó
không tự xác minh nội dung semantic của event hoặc tính đúng đắn của human label.
Không bật inventory gate nghĩa là report sẽ ghi `event_inventory_status=not_checked`.
Không sử dụng inventory Dev để đánh giá Test.

## Metrics và denominators

`N` là số planned cases. `completed` của mỗi variant chỉ gồm interpretable controller
results: accepted initial, accepted after repair hoặc budget exhausted. Backend/input/
validator failures tách riêng khỏi completed. Initial generation infrastructure failure
không tạo replay candidate: B0/B1 not-run với reason, failed backend ledger entry vẫn
được giữ. Input validation failure trước backend không có ledger entry; giữ exact
blank/whitespace summary, category `invalid_summary`, stage `input_validation`. Đây là
production nonblank-input gate, không mở rộng quy tắc acceptance. Invalid typed hoặc
non-UTF-8 records tiếp tục bị reject, không tạo hash giả.

`attempted` ở experiment level gồm case có backend ledger hoặc explicit initial input
failure. Attempted ở variant level là variant được gọi, kể cả replay. Completed paired,
failed cases, partial cases và not-run cộng lại đúng N. Initial input failures và initial
infrastructure failures có counters riêng. Không gộp các khái niệm này.

| Metric | Công thức |
| --- | --- |
| Coverage của variant | completed / N |
| Structural Acceptance Rate, planned | accepted / N |
| Completed-case acceptance | accepted / completed; luôn báo kèm planned rate |
| Acceptance improvement, pp | 100 × (accepted B1 − accepted B0) / N |
| Conditional Repair Success | accepted_after_repair / eligible initial failures có ít nhất một repair backend invocation |
| Mean repair backend invocations, planned | actual repair backend invocations / N |

Zero denominator luôn là `null`, không phải 100%. Báo riêng first-/second-repair
success, eligible nhưng chưa repair do stop policy, exhaustion, failure categories,
not-run, initial JSON+schema pass và exact-summary gate. Warnings không làm fail
acceptance hoặc kích hoạt repair. B0 dùng budget 0, B1 budget 2; status/attempt count
phải phù hợp actual production histories. Revalidation errors không được biến thành
repair success. Summary mismatch vẫn là deterministic failure, không là semantic code.
Conditional repair denominator **bao gồm** repair backend invocation fail trước
`model.generate`; báo riêng `repair_backend_failure_cases`, eligibility và attempted
repair cases. Không gọi mẫu số này là số cases đã thực thi model.generate.

`backend_failure` trong RepairResult chỉ nhận production infrastructure categories
(`backend_exception/backend_output_type/invalid_output_unicode`) với failed final attempt
không có validation report. Không đổi nhãn deterministic exhaustion thành backend failure.
Category của failed wrapper phải khớp RepairResult/partial exception history.

Kết quả có plan hash, final accepted Storyboard canonical hashes, final exact-summary
checks và deterministic error codes/locations. Giữ independent original summary tách
khỏi storyboard.summary. Thay raw hoặc summary dù chỉ whitespace cũng đổi hash;
không NFC/NFD normalization.

## Logical và physical cost

- Physical ledger = mỗi initial backend invocation **một lần** + actual repair backend invocations.
- B0 logical = shared initial backend invocations.
- B1 logical = shared initial backend invocations + actual repairs.
- Không cộng B0 logical + B1 logical thành physical cost.
- `B0_logical/B1_logical` là **quy thuộc shared physical calls** theo design, không
  phải observed per-variant execution count. Khi initial generation đã xảy ra nhưng
  B0 `not_run`, shared initial cost vẫn được quy thuộc B0_logical; B0 attempted vẫn 0.
  Đây không phải bằng chứng B0 đã chạy. Variant state/coverage mới mô tả execution.
  Task11A.3 chỉ làm rõ nhãn này và thêm regression test, không đổi cost formulas/totals.
- Logical ledger mô tả cost của shared inputs/repairs đã quan sát; không giả lập
  measurements cho missing/not-run calls hoặc infer cost cho một full pipeline chưa chạy.
- Tổng input/generated tokens, model.generate seconds và backend wall seconds tách
  riêng. Missing measurement làm total thành `null`; vẫn báo known subtotal, coverage
  và status `available/partial/not_available`. Genuine measured zero giữ nguyên 0.
  VRAM lấy peak với coverage, không cộng peaks. Token hits có observation coverage.
- Count `backend_invocations` không phải số model.generate. Aggregate `model_generate_calls`
  chỉ có total khi tất cả invocations có independent observed counts; nếu thiếu, giữ null
  và known subtotal/coverage/status. Empty actual ledger có count 0; load failure có
  thể có backend count 1 và observed model count 0. Không fabricate latency 0 cho load failure.
- Đổi tên output `actual_calls` thành `backend_invocations` trong proposed contract
  chưa publish để tránh nhầm generation budget với backend invocation count.
- Model-load, pipeline/controller/stage wall time không được suy ra bằng cách cộng
  nested durations hoặc lấy latency replay đại diện inference. Chưa aggregate các
  measurements đó trong harness này. Không dùng rounded quota delta như exact billing.

## Human annotation và matching boundary

Human extension dùng production `SemanticIssue`/`SemanticEvidence` với đúng tám codes:
`CHARACTER_IDENTITY_MISMATCH`, `CHARACTER_ROLE_MISMATCH`, `CHARACTER_FRAGMENTATION`,
`OBJECT_TRANSLATION_MISMATCH`, `VISUAL_LANGUAGE_MISMATCH`, `MISSING_KEY_EVENT`,
`ENDING_CONTRADICTION`, `UNSUPPORTED_STORY_EVENT`.
`VISUAL_LANGUAGE_MISMATCH` chỉ áp dụng shared Character.visual bằng tiếng Anh theo
contract. Harness không tự gán correctness cho reasoning hoặc tự tìm semantic lỗi.

`HumanAnnotation` lưu case ID, independent summary hash, Storyboard hash, rubric version,
annotator/date, `human_review_state` (`pending_human_review/in_progress/completed`),
annotation status, adjudication, prior prediction exposure, verdict, findings và notes.
Each finding là `AnnotatedFinding` gồm finding ID, **human-assigned underlying
discrepancy ID**, production issue, related_locations và confirmed/uncertain status.
Đây là extension evaluation, không thêm related_locations vào runtime semantic schema.

Pending/in-progress không được chứa final verdict hoặc gold approval. Completed empty
issues chỉ là clean gold nếu có explicit confirmed/adjudicated PASS và reviewed rubric.
Uncertain case verdict/annotation không mở gold gate. **Full case gold gate** còn yêu
cầu không có finding `status=uncertain`; readiness báo `unresolved_findings` riêng.
Completed case verdict `fail` chỉ khẳng định có confirmed error, không chứng minh mọi
finding đã được adjudicate.

Nếu có unresolved uncertain finding nhưng case `annotation_status=confirmed` hoặc
`adjudicated=True`, `HumanAnnotation` reject combination mâu thuẫn. Consistent completed
`fail` với confirmed error + uncertain warning có thể lưu để audit với annotation status
`uncertain`, adjudicated false, nhưng `gold_ready=False` và không gọi matching. Không
xóa uncertain findings, không đổi chúng thành confirmed và không tự tạo human approval.
Prior exposure được lưu; không tuyên bố blind tuyệt đối.

`AnnotatedFinding` chỉ nhận uncertain finding với severity `warning`, theo TV3 draft
rubric section 3 tại `origin/feature/evaluation` commit
`7756d3015ed20590dd6ae7c867c7ec6662749517`. Tentative `error` + `uncertain` bị reject,
không tự downgrade severity. Các giả thuyết chưa đủ căn cứ có thể giữ ở draft notes,
không xuất thành confirmed error. Không sửa TV3 rubric hoặc production SemanticIssue.

`SemanticCase` chứa target Storyboard, independent summary, annotation và production
`SemanticValidationReport`. Annotation và reviewer snapshot phải thuộc đúng case target.
Storyboard hash dùng `sha256(json_bytes(storyboard))`; đây là canonical parsed-content
hash, **không phải** hash của raw generation. Raw hashes ở paired results là exact UTF-8
bytes, không reconstruct JSON để thay raw.

One-to-one matching cần human `DiscrepancyLink(prediction_index, discrepancy_id,
confirmed_by)`. Cùng case, canonical code, discrepancy đã adjudicate và exact anchor
hoặc related location mới match; không parent/`[]` wildcard. **Exact root `[]` match
exact root `[]`**; không dùng truthiness để loại root. Root và scene-specific location
không match nhau trừ khi path kia nằm trong explicit human related_locations. Cả gold và predictions
phải có exact traceable evidence, original-summary evidence path `[]`, storyboard
paths zero-based và resolve tới string cho quote. Exact substring phù hợp không chứng
minh semantic claim đúng. Duplicate predictions chỉ match gold một lần; severity
agreement tách khỏi identity. Unlinked predictions còn cần human adjudication;
không mặc định mọi unmatched là FP. Với full-case gate, bất kỳ unresolved finding nào
cũng chặn matching cho cả case; không xuất partial confirmed-subset TP/FP/FN dưới nhãn
full gold-ready.

Policy boundary: Task11A.3 yêu cầu full-case gate này. TV3 draft sections 3–4 quy định
uncertain severity và case-level confirmed không còn ambiguity; section 6 cũng mô tả
confirmed-only primary matching và case fail có thể kèm uncertain findings. Nếu muốn
partial confirmed-subset matching, cần API/policy version riêng và **team-lead sign-off**;
không âm thầm coi đó là full gold. Cần chốt interpretation này cùng TV3 trước official
gold/matching freeze; tài liệu này không tự nghiệm thu rubric draft.

Reviewer `failed/not_checked` giữ verdict null, matching not_checked và không sinh
false semantic FAIL hoặc FN counts. API này chỉ chuẩn bị match inventory, luôn giữ
`semantic_metrics=null`. Precision/recall/F1, matching policy approval và denominator
cho abstentions cần TV1/TV3 chốt riêng trước official scoring.

## Dataset freeze và chống leakage

Trong Task 11A chỉ dùng independent synthetic CPU fixtures do test author khai báo.
Không đọc official JSONL/metadata CSV, không dùng official Test để debug/tune. Không
lấy reviewer predictions, expected labels hoặc design intents làm generation inputs.
Module không có inference API, dataset discovery hoặc `.env` loading; human labels
ở package riêng, không xuất sang model prompts.

Official plan cần frozen split, approved review/rights, dataset hash reference và
riêng official Test authorization. Các flags là **declarations cần external sign-off**,
không phải bằng chứng tự sinh bởi harness. Caller phải xác minh split bytes với manifest,
source/model/prompt/policy hashes và quyền dùng dữ liệu trước khi tạo frozen batch.
Không tự suy ra approval từ PR merged. Không đổi split/rubric/matching sau khi xem Test
predictions. Giữ toàn bộ planned IDs, failed và not-run records; không cherry-pick hoặc rerun.

PR #20 và #27 vẫn open tại audit Task 11A. Split/rubric/rights/human audit thuộc TV3;
real image/UI handoff thuộc TV2. B2 image ablation chưa được harness triển khai, không
tạo số liệu hay coi CPU mock images là diffusion results. Những development GPU results
đã báo cáo trước đây không được harness này tái chạy hoặc dùng làm official accuracy.

## Reproducible CPU workflow

Không cần package mới ngoài CPU dependencies hiện có. Direct Python API nhận explicit
records; không ngầm đọc ambient environment. Batch JSON theo `EvaluationInput.model_json_schema()`;
draft templates cần được người phụ trách freeze/convert rõ ràng, không auto-upgrade.
Giữ frozen batch nguyên bytes và expected SHA-256 ở approval manifest riêng.

Linux, từ repository root:

```bash
.venv/bin/python -m pytest tests/test_offline_evaluation.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
.venv/bin/python -m src.offline_evaluation --input /path/to/frozen_batch.json --expected-sha256 FROZEN_BATCH_SHA256 --output-root outputs/evaluations
```

Windows PowerShell, từ repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_offline_evaluation.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m src.offline_evaluation --input C:\approved\frozen_batch.json --expected-sha256 FROZEN_BATCH_SHA256 --output-root outputs\evaluations
Get-FileHash C:\approved\frozen_batch.json -Algorithm SHA256
```

CLI chỉ đọc explicit batch, xác minh expected byte hash rồi validate toàn bộ trước khi
ghi. Session directory mới chứa `aggregates.json`, `plan.json`, `input_reference.json`,
`checksums.json`. Không copy raw batch/annotations/env/logs vào outputs; caller giữ
batch gốc ở external evidence archive. UTF-8 được chỉ định hoặc parse từ strict UTF-8 bytes;
không cần `PYTHONUTF8=1`. Không tuyên bố Windows PASS khi chỉ chạy Ubuntu.

Checksums manifest không hash chính nó. Đối chiếu từng member SHA-256 với manifest;
parent/root là explicit output configuration, không lấy summary/case ID làm path.
Chỉ lưu artifacts đã sanitize; tuyệt đối không credentials, signed URLs, weights/cache
hoặc raw environment dumps. API không tự kiểm chứng mọi secret có thể tồn tại trong
arbitrary user-provided bytes; CLI output whitelist không chứa raw batch.

## Evidence CPU và phần chưa chạy

`tests/test_offline_evaluation.py` ghi rõ provenance synthetic, không đọc fixtures từ
official dataset. Tests dùng scripted backends để tạo **production RepairResult**,
không chạy model. Kiểm tra paired hashes, complete inventory, invalid histories,
feedback, cost double counting, strict JSON/hash contracts, pending gold gates,
one-to-one matching, uncertain findings, failed reviewer, exact Unicode evidence,
write-once/checksums và actual offline CLI subprocess.

Verification Ubuntu/project .venv của Task 11A: **104 targeted tests PASS**, full CPU
suite **981 PASS**, không failed/skipped/errors; `pip check` và `git diff --check` PASS.
CLI subprocess test chạy với `-X utf8=0`; đây không thay thế Windows verification.

Task 11A.1 review tái hiện và sửa các P1 trong offline files:

- Classification: deterministic history bị gán nhầm backend_failure; wrapper category
  có thể mâu thuẫn result. `_validate_history` và `VariantResult` hiện reject cả hai.
- Call accounting: ledger backend chưa tách observation của model.generate. Thêm observed
  count/source và coverage, giữ unknown là null; không infer từ attempt count.
- Pre-backend input failure: trước đây không có representation riêng. Nay có stage,
  counter và planned denominator, không fabricate backend entry hoặc model call.
- Strict boundary: Pydantic JSON-mode serializer của Optional[int] có thể đổi mutated
  True thành 1 trước revalidation. `checked_copy` hiện strict-validate Python-mode data
  trước serialization; `json_bytes` giữ nguyên primitive types thay vì coercion đó.

Regression tests giữ same-case/code/location nhưng khác human discrepancy tách biệt,
genuine zero vs missing latency, load failure trước generation, zero/unknown model counts
và replay cost accounting. Không sửa production contracts hoặc tests của thành viên khác.
Sau review: **115 targeted PASS**, full CPU **992 PASS**, không failed/skipped/errors;
pip check, git diff --check, syntax, whitespace, secret screening và docs links PASS.

P2/dependencies còn lại: ledger observation và approval declarations cần external evidence
audit, human discrepancy crosswalk/rubric/gold cần TV1/TV3 sign-off; chưa có Windows runtime
verification. Không coi các flags hoặc findings synthetic là official human approval.

Task11A.3 sửa hai P1 root location/full-gold readiness, kiểm tra uncertain severity theo
draft và làm rõ P2 logical cost attribution mà không đổi structural metrics.
Verification Ubuntu/project .venv: **125 targeted PASS**, full CPU **1002 PASS**, không
failed/skipped/errors. Root-to-root, explicit related root, duplicate root, unresolved
findings, severity rejection, no fabricated approval và not-run logical attribution
được kiểm tra bằng synthetic fixtures; không phải semantic model quality evidence.
Chưa có official metric results, human-confirmed gold package, semantic scores, real
image evaluation hoặc Windows runtime verification từ task này. Cần TV3 chốt frozen
dataset/rubric/adjudication/matching protocol và TV2 chốt real image/Gradio contracts
trước các giai đoạn đánh giá tương ứng.
