# LLM-assisted Semantic Storyboard Validator — Task 09B

Task 09B.3A: default vẫn là reviewer v1; variant evidence-first v2 phải chọn explicit.
Kết quả GPU pilot v1 Task 09B.2B và thiết kế comparison mới nằm trong
[Semantic review experiments](semantic_review_experiments.md). Các mô tả chưa chạy GPU bên dưới
ghi trạng thái tại Task 09B/09B.1; v2 hiện chỉ có CPU tests, chưa có kết quả GPU.

## 1. Quyết định và trạng thái

Đây là phương pháp TV1 đề xuất: structured LLM review bổ sung cho [deterministic validator](validation_and_repair.md), dùng cùng Qwen2.5-3B-Instruct runtime đã load. Một model instance giúp hạn chế VRAM/load overhead, nhưng **chưa có bằng chứng reviewer đạt độ chính xác đủ cao**. Self-review có thể lặp lại lỗi của model sinh truyện. Reviewer verdict không phải ground truth hoặc semantic score.

Task 09B chỉ triển khai và kiểm thử CPU bằng injected doubles/fake reviewer. Chưa chạy semantic reviewer GPU, gọi API inference, Kaggle execution, Repair hoặc Image Pipeline integration. Không sửa [Shared Storyboard Schema](data_contract.md), baseline generation prompt hay notebook 02/05/06. Không thêm dependencies; Pydantic v2 đã có trong CPU requirements.

## 2. Development evidence đã đọc

Đã xác minh SHA-256 trước khi đọc ZIP ngoài repository; kiểm tra archive paths và internal checksums, không extract/sửa raw output hoặc manifest:

| Archive | SHA-256 | Internal checksums |
|---|---|---|
| task08b/20261118T212907Z-e405160e63.zip | `82bcc30f9f08e4c44e3344c5887eff03ab6941170afe41aa92479b1025a1a617` | 4/4 |
| task08c/20261118T220702Z-31c52d49db.zip | `0ab0112f400881cefdec1d0c86fbebe88dd102493d2058b46f3f1b4d97af1d22` | 16/16 |

Root là `../comic-generation-experiments/` khi đứng tại repository root. Manifests xác nhận source generation `390b069b9d5c4a83e97481580790760bf963efff`, model revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, generation prompt `storyboard-v1.0-baseline-001`. Evaluation/diagnostics gốc vẫn giữ semantic review pending, không phải human labels.

Các quan sát sau là failure hypotheses để xây taxonomy, không phải kết quả một semantic reviewer mới:

- 08B: catalog/scene references có dấu hiệu không khớp identity/actor thể hiện trong caption và image prompt; visuals tiếng Việt, catalog dư và duplicate visuals. Chưa thể kết luận identity chỉ từ tên ID hoặc visual giống nhau.
- pilot_001: source/caption dùng đối tượng táo nhưng image prompts dùng “pear”; catalog có records theo hành động/cảm xúc và visuals tiếng Việt. Đây là động cơ kiểm tra translation/fragmentation/language, không phải luật hard-code cho câu chuyện này.
- pilot_002: actor tìm được đồ vật trong caption khác actor được mô tả trong image prompt; catalog có unused record/visual trùng. Hai diagnostics cuối không tự chứng minh semantic duplication.
- pilot_003: output summary chỉ giữ một phần nguồn nên production summary gate thất bại, dù structural schema hợp lệ; visuals tiếng Việt và hai nhân vật có mô tả giống nhau. Ngoại hình giống nhau không tự chứng minh cùng một identity.

Ba synthetic pilot cases không thuộc official dataset. Không đưa summaries, IDs hoặc những ví dụ riêng này vào production review prompt/rules hoặc unit fixtures. Chưa dùng official held-out data, không tạo benchmark semantic accuracy từ bốn cases.

## 3. Kiến trúc và public API

```text
Original summary độc lập + Shared Storyboard
  → argument checks → shared-schema revalidation/snapshot
  → semantic messages + prompt hash
  → một backend.review call
  → strict JSON parse → response schema → location/quote contract
  → SemanticValidationReport
```

Các modules:

- `src/storyboard/semantic_schema.py`: SemanticEvidence, SemanticIssue, SemanticReviewResponse và SemanticValidationReport.
- `src/storyboard/semantic_prompts.py`: SEMANTIC_PROMPT_VERSION và build_semantic_messages.
- `src/storyboard/semantic_validator.py`: SemanticReviewBackend Protocol và SemanticStoryboardValidator.
- `src/story_generator/qwen_backend.py`: public review API dùng chung inference path với generate.

`SemanticStoryboardValidator(backend).validate(original_summary, storyboard)` nhận nguồn độc lập và shared Storyboard instance. Không nhận dict/legacy dataclass rồi tự ép kiểu. Invalid arguments trả `not_checked/invalid_arguments`. Instance được revalidate một lần để phát hiện mutation; structural-invalid trả `not_checked/invalid_source_storyboard`, không gọi reviewer. Model và lists không được đóng băng toàn bộ; caller không nên mutate models/report trong khi truyền giữa modules.

Source hợp lệ được snapshot thành dữ liệu độc lập. Summary matching được ghi riêng. **Offline analysis cho phép review structurally valid Storyboard có summary mismatch**: prompt vẫn dùng original_summary độc lập và report giữ `summary_matching=failed`. Kể cả reviewer nói pass, production output gate vẫn chưa đạt. Task này không bổ sung hoặc thực thi production acceptance policy; không đổi ValidationReport/StoryGenerator/ComicPipeline của Task 09A.

Mỗi invocation tối đa một reviewer call; không retry, fallback, strip fences, regex extraction hoặc Repair. Module không ghi file, log raw output hoặc tự tìm credentials.

## 4. Reviewer response contract

Các model dùng Pydantic v2 `strict=True`, `extra="forbid"`. JSON arrays thành Python lists, không nhận tuple thay list hoặc silently coerce index/field types.

SemanticReviewResponse có ba fields bắt buộc:

- `verdict`: `pass`, `fail` hoặc `uncertain`.
- `explanation`: string có nội dung, giữ nguyên whitespace của text hợp lệ.
- `issues`: list SemanticIssue, có thể rỗng.

Verdict policy: pass chỉ đi cùng issues rỗng; fail cần ít nhất một error issue; uncertain chỉ có warnings hoặc issues rỗng, cần giải thích việc abstain. Các combination mâu thuẫn bị schema từ chối. Policy được viết trong prompt; đây là contract kỹ thuật của phiên bản đầu, cần review/evaluation tiếp.

SemanticIssue gồm code, severity (`error`/`warning`), location, message không rỗng và evidence list có ít nhất một phần tử. Taxonomy:

| Code | Ý nghĩa reviewer được yêu cầu xem xét |
|---|---|
| CHARACTER_IDENTITY_MISMATCH | Catalog/references/nội dung thể hiện entity identity mâu thuẫn |
| CHARACTER_ROLE_MISMATCH | Actor/action/role giữa các biểu diễn không khớp |
| CHARACTER_FRAGMENTATION | Một entity bị tách thành records vì hành động/cảm xúc, cần evidence cụ thể |
| OBJECT_TRANSLATION_MISMATCH | Đối tượng giữa Vietnamese source/caption và English prompt bị đổi nghĩa |
| VISUAL_LANGUAGE_MISMATCH | Shared visual description không phải tiếng Anh, không chỉ một tên riêng |
| MISSING_KEY_EVENT | Thiếu diễn biến chính có ảnh hưởng câu chuyện, không yêu cầu mọi chi tiết nhỏ |
| ENDING_CONTRADICTION | Kết thúc mâu thuẫn original summary |
| UNSUPPORTED_STORY_EVENT | Bổ sung diễn biến làm đổi cốt truyện thiếu căn cứ, phân biệt visual elaboration vô hại |

Code không hard-map sang error: reviewer chọn error khi có căn cứ hoặc warning khi chưa chắc. Không triển khai semantic scene redundancy. Không dùng duplicate visual/unused character làm bằng chứng duy nhất để khẳng định cùng identity; không đánh lỗi tùy ý về trang phục/ngoại hình/bối cảnh không mâu thuẫn nguồn.

## 5. Location và evidence grounding

Location là list field names/string và integer positions **từ 0**, không phải Scene.index hoặc ID. Boolean/float/negative positions bị schema từ chối; path ngoài snapshot bị runtime từ chối. Issue location `[]` là toàn storyboard, có thể dùng cho missing event toàn cục. Path có thể tới collection hoặc record khi issue liên quan nhiều fields.

Mỗi SemanticEvidence có `source`, `location`, `quote`:

- source `original_summary`: location phải `[]`, quote lấy từ original summary độc lập.
- source `storyboard`: path phải tồn tại và trỏ đến một string field, ví dụ `["scenes", 0, "caption_vi"]`, `["characters", 0, "visual"]` hoặc một reference string. Không quote cả list/dict hoặc integer index bằng cách tự stringify.
- quote phải không rỗng và là exact substring của source string, không normalize, dịch hoặc thay wording.

Mọi issues được kiểm tra cả location và quote trước khi nhận verdict, kể cả warnings. FAIL chỉ được trả ở completed report khi có error issue qua contract này. **“Supported” ở đây chỉ là structurally grounded**: đúng path và quote không chứng minh claim, logic suy luận, ngôn ngữ hoặc causality đúng. Reviewer có thể quote đúng rồi diễn giải sai. Tests cố tình minh họa giới hạn đó. Runtime không bảo đảm đã quote đủ cả hai vế của contradiction; prompt yêu cầu khi có thể, human annotation vẫn cần.

## 6. Prompt và JSON policy

Prompt version riêng: **storyboard-semantic-review-v1.0-001**. System instructions tiếng Anh cùng response JSON Schema; user message chứa JSON object gồm `original_summary` và toàn bộ `storyboard`. Không có assistant few-shot hoặc development cases. Input instruction-like vẫn ở data boundary; đây là biện pháp giảm prompt injection, không bảo đảm model miễn nhiễm.

Prompt yêu cầu đọc catalog, references, captions, prompts; phân biệt identity/action/emotion; actor/action/object alignment; events/ending; English visuals; evidence/abstention; không sinh/sửa storyboard hoặc viết thêm ngoài JSON.

Semantic validator dùng `json.loads` một lần với `object_pairs_hook` từ chối duplicate keys **ở mọi cấp** và `parse_constant` từ chối NaN/Infinity/-Infinity; sau đó validate response một lần bằng Pydantic. Không strip text hoặc sửa JSON. Numeric overflow sai kiểu ở schema được report với JSON-safe error evidence; không đổi raw reviewer text.

Policy này riêng cho semantic reviewer response. Shared Storyboard Schema, generation prompt và deterministic validator không bị đổi: Task 09A vẫn có duplicate-key last-value-wins limitation. Nếu caller chỉ dùng trực tiếp SemanticReviewResponse.model_validate_json thì Pydantic parser mặc định cũng không phải duplicate-key protection; entry point bảo đảm policy là SemanticStoryboardValidator.validate. JSON Schema không biểu diễn đầy đủ custom verdict rules, exact quotes hoặc runtime locations.

## 7. Shared Qwen runtime và baseline regression

Public API hiện có `generate(summary) -> str` giữ nguyên. API bổ sung:

```python
# Chỉ wiring, constructor không load weights.
from src.story_generator.qwen_backend import QwenStoryBackend
from src.storyboard.semantic_validator import SemanticStoryboardValidator

backend = QwenStoryBackend(device="cuda:0", max_new_tokens=1024, repetition_penalty=1.0)
semantic_validator = SemanticStoryboardValidator(backend)
# Chỉ sau khi được phép GPU inference:
# storyboard = StoryGenerator(backend).generate(original_summary)
# report = semantic_validator.validate(original_summary, storyboard)
```

Backend.review(messages, prompt_version=...) nhận đúng một system/user message pair, copy messages và dùng cùng tokenizer/model/runtime đã cache. Không có consumer nào truy cập `_components` hoặc tạo thêm Qwen instance. Load thực tế một lần khi đã load thành công; generate/review nội bộ gọi load nhưng dùng cache. Không thread-safe hoặc async batching claim.

Generate và review dùng chung inference implementation; model ID/revision, FP16/cuda:0, no quantization/trust_remote_code/device_map, greedy defaults, batch 1 và raw continuation decode policy giữ nguyên. Story messages gọi nguyên build_story_messages, prompt version vẫn `storyboard-v1.0-baseline-001`. Các tests cũ giữ nguyên, thêm regression tests cho custom messages, parameters, slicing, metadata isolation và chỉ load một lần. Điều này không chứng minh hai output GPU bitwise identical; chưa chạy GPU sau refactor.

`last_run` chỉ là snapshot story generation gần nhất, không bị review ghi đè. `last_review` chỉ là snapshot review gần nhất. Hai properties trả deepcopy; mỗi call mới khởi tạo metadata riêng trước input/load/generation. Thêm `purpose` (`story_generation`/`semantic_review`) và `call_id` mới; giữ prompt version/hash/messages theo đúng call. StoryGenerator từ chối input trước backend vẫn không tự reset last_run; consumer không gắn snapshot cũ vào input mới.

Semantic validator chỉ đọc last_review. Với metadata được cung cấp, nó kiểm tra call_id mới, purpose, version, prompt hash/messages và raw return value khớp. Stale/mismatched/nonserializable metadata bị từ chối, không gắn vào report. Backend protocol cho phép last_review=None; khi đó report giữ metadata None và local provenance, không giả tạo model/metrics. Nếu backend error mà có fresh raw trong last_review, vẫn giữ raw; nếu metadata cũ thì bỏ metadata cũ.

Generation parameters mặc định dùng chung cho cả hai purposes; chưa có per-purpose tuning hoặc seed policy mới. Latency/VRAM vẫn do backend đo khi chạy thật; injected mode để None. Budget 1024 có thể chưa đủ cho review dài; chưa đo tokenizer/context usage của semantic prompt trên GPU. Không tự tăng budget, bỏ schema, truncate input hoặc retry khi output bị cắt.

## 8. Runtime report và error categories

SemanticValidationReport tách execution khỏi model response:

- `review_status`: completed, failed hoặc not_checked.
- `response`: SemanticReviewResponse chỉ khi mọi checks thành công. `verdict`/`issues` là computed projections, không phải verdict runtime tự bịa.
- `raw_reviewer_output`: giữ nguyên khi có string output encode UTF-8 strict được, kể cả lỗi JSON/schema/contract/backend; trường hợp không transport được dùng escaped diagnostics như mô tả bên dưới.
- `raw_reviewer_output_preservation`: not_available, verbatim hoặc escaped_diagnostic; không đánh đồng diagnostic representation với raw text.
- `diagnostics`: danh sách runtime diagnostics có nhãn, gồm Unicode transport và Pydantic error serialization fallback.
- `error_category` và JSON-safe errors; Pydantic loc/type/message/context được giữ qua error JSON khi serialize được, exception context/non-finite constants thành strings. Nếu serializer thất bại thì giữ structured details trong phạm vi an toàn và ghi rõ input/context bị lược bỏ. Backend errors chỉ lưu exception/cause types để tránh vô tình log credentials trong message/traceback.
- `source_structural_validity`, `summary_matching`, original summary và detached storyboard snapshot.
- provenance gồm attempt ID, prompt version/hash, purpose, input hashes, Pydantic version và mode offline_analysis; backend metadata chứa model/revision/parameters/metrics khi được cung cấp.
- `human_annotation_status=not_checked`, không có semantic scores.

| Runtime category | Review status | Verdict |
|---|---|---|
| invalid_arguments | not_checked | None |
| invalid_source_storyboard | not_checked | None |
| reviewer_backend_failure | failed | None |
| reviewer_output_type | failed | None |
| invalid_reviewer_json | failed | None |
| invalid_reviewer_unicode | failed | None |
| reviewer_schema_violation | failed | None |
| invalid_issue_location / invalid_issue_evidence | failed | None |
| reviewer_metadata_error | failed | None |
| Không có runtime error | completed | pass/fail/uncertain do model trả |

Source/raw generation output vẫn thuộc caller/backend.last_run; semantic validator không overwrite hoặc tự suy ra original raw từ Storyboard. Caller khi chạy thật cần ghi Git/source revision thực tế, package/hardware versions và lưu artifacts riêng; report không tự lấy một Git SHA rồi khẳng định source chưa có local changes. JSON serialization phục vụ outbound reports; computed fields cần loại bỏ hoặc dùng round_trip serialization nếu rehydrate bằng strict Pydantic model.

### Unicode robustness hardening — Task 09B.1-Fix

Hai P1 được tái hiện trước sửa: (1) decoded lone surrogate làm semantic response schema báo ValidationError, nhưng `error.json()` tiếp tục ném ValueError; (2) source string chứa surrogate vượt qua kiểm tra type/nonblank rồi gây UnicodeEncodeError khi hash messages. Không có GPU/API inference trong reproduction hoặc fix.

**Transport policy:** chấp nhận Unicode scalar hợp lệ, gồm tiếng Việt, NFC/NFD, emoji và supplementary characters. Từ chối code points U+D800–U+DFFF trong Python strings tại boundary cần encode UTF-8 strict. Không dùng errors=ignore/replace, không normalize và không tự ghép surrogate code points của Python string thành scalar. Exact evidence comparison giữ nguyên: NFC/NFC và NFD/NFD có thể match; NFC/NFD không tự match.

Original summary được kiểm tra trước khi đưa vào report/messages. Sau một lần shared-schema revalidation, toàn bộ snapshot được duyệt, bao gồm summary, character IDs/visuals, captions/base prompts, references và mọi string/key thực sự đi vào messages. Không chỉ kiểm tra một vài fields được hard-code. Source lỗi dừng trước build/hash prompt, đọc last_review hoặc gọi backend; không tạo prompt/input hashes giả và không gắn metadata cũ.

- Original summary không encode được: not_checked/invalid_arguments, reviewer 0 calls, original_summary trong report là None; diagnostic giữ vị trí và escaped representation.
- Storyboard có surrogate nhưng vẫn structurally valid: not_checked/invalid_source_storyboard, source_structural_validity=passed, summary_matching=not_checked, snapshot trong report là None. Đây là transport failure, không đổi Shared Storyboard Schema thành Unicode/semantic validator. Caller data giữ nguyên.
- Storyboard structurally invalid: source_structural_validity=failed, dùng cùng safe error reporting; không gọi reviewer.

**Reviewer raw preservation:** phân biệt hai tầng string:

1. Raw JSON chứa escaped sequence như `\ud800`: chính raw text vẫn là UTF-8 hợp lệ, được giữ verbatim. JSON decoder tạo lone surrogate trong decoded field; schema từ chối và report failed/reviewer_schema_violation, verdict None. Không sửa raw hoặc cố render decoded character lỗi.
2. Raw Python string chứa surrogate code point trực tiếp: report failed/invalid_reviewer_unicode, verdict None, raw_reviewer_output=None và preservation=escaped_diagnostic. Diagnostics chứa location `["raw_reviewer_output"]`, representation=`python_unicode_escape`, escaped_text và original_utf8_preserved=false. Đây là biểu diễn ASCII của Python code points, **không phải raw UTF-8 đã được bảo toàn hay output đã repair**. Kể cả hai surrogate code points high/low đứng cạnh nhau trong Python string vẫn không encode strict được.

Valid escaped surrogate pairs trong JSON khác trường hợp trên: theo `json.loads` thực tế, `\ud83d\ude00` được decode thành scalar emoji U+1F600, được chấp nhận; raw JSON vẫn giữ nguyên. Reviewer luôn được gọi đúng một lần cho output failures. Nếu backend cũng phát exception, category chính vẫn reviewer_backend_failure và diagnostic Unicode đi kèm, không giả verdict.

Fresh metadata cũng được kiểm tra Unicode trước khi gắn vào report. Metadata không thể transport bị bỏ khỏi review_metadata và ghi diagnostic có nhãn; current raw có thể giữ qua diagnostic nếu identity guards đã xác nhận đúng call. Không lấy raw từ stale metadata. Fields/location của diagnostic không phải semantic issue locations; lỗi dictionary key dùng marker `<key>` và vị trí entry để không đưa chính invalid key vào JSON path.

**Safe Pydantic errors:** thử error.json như trước cho các lỗi thông thường, giữ input/context khi an toàn. Nếu serializer lỗi hoặc kết quả chứa invalid Unicode, fallback sang native errors(include_input=False, include_context=False). Giữ loc/type/msg/url khi biểu diễn được, ghi diagnostic pydantic_error_serialization_fallback với exception types và omitted_fields=[input, ctx]. String không transport được trong details/location dùng object có nhãn python_unicode_escape; không silently thay ký tự. Nếu ngay cả fallback lấy details thất bại thì report có minimal validation_error diagnostic, không để exception serializer thoát khỏi validator. Raw UTF-8 hợp lệ vẫn nguyên trạng để đối chiếu các fields bị lược bỏ.

Các labels escaped chỉ dùng cho diagnostics/errors, không đưa vào prompt, evidence comparison hoặc source data. Reports được kiểm tra cả model_dump_json và json.dumps(mode-json, ensure_ascii=False), encode strict và ghi/đọc UTF-8 file. Category invalid_reviewer_unicode và hai reporting fields là bổ sung runtime; model-generated response schema, tám issue codes, verdict policy, prompt version, duplicate-key/non-finite policy, Qwen backend và baseline story generation không đổi.

## 9. Demo CPU bằng fake reviewer

Ví dụ do TV1 tạo, không lấy từ bốn development cases. Fake chỉ minh họa runtime contract, không tạo kết quả semantic detection của Qwen hoặc metrics giả:

```python
import json
from src.storyboard.schema import Storyboard
from src.storyboard.semantic_validator import SemanticStoryboardValidator

class FakeReviewer:
    last_review = None  # Không có model/latency/VRAM metadata.

    def review(self, messages, *, prompt_version):
        return json.dumps({
            "verdict": "uncertain",
            "explanation": "Synthetic abstention for a software demo, not model inference.",
            "issues": [],
        })

original_summary = "Một người viết thư rồi về nhà."
storyboard = Storyboard.model_validate({
    "summary": "Một người viết thư rồi về nhà.",
    "characters": [],
    "scenes": [
        {"index": i, "caption_vi": caption, "image_prompt_en": prompt, "characters": []}
        for i, caption, prompt in [
            (1, "Trang giấy được mở ra.", "A sheet of paper."),
            (2, "Những dòng chữ xuất hiện.", "Written lines on paper."),
            (3, "Lá thư được gấp lại.", "A folded letter."),
            (4, "Cửa nhà khép lại.", "A closed door."),
        ]
    ],
})
report = SemanticStoryboardValidator(FakeReviewer()).validate(original_summary, storyboard)
print(report.review_status, report.verdict, report.summary_matching)
print(report.human_annotation_status, report.review_metadata)
```

Kết quả runtime demo: completed, uncertain, passed; human annotation not_checked và metadata None. Đây không phải nhận xét chất lượng câu chuyện.

## 10. Human annotation và kế hoạch đánh giá

Self-review bias có thể khiến cùng model hợp lý hóa lỗi sinh truyện, dùng prior knowledge thay nguồn, hallucinate evidence, bỏ sót actor/translation hoặc overflag sáng tạo vô hại. Exact quote check không phát hiện reasoning sai; descriptions giống nhau không đủ xác định entity. Language review của model cũng có false positives với proper names/code-switching và false negatives với đoạn ngắn. Prompt injection có thể vẫn ảnh hưởng verdict.

Kế hoạch chưa thực thi: viết annotation guide theo taxonomy; có annotators độc lập và adjudication cho cases bất đồng; đánh dấu unknown/ambiguous; lưu source/storyboard cùng issue location và evidence. Không dùng reviewer output làm label hoặc dùng diagnostics như nhãn semantic tự động.

Chọn development data có provenance, giữ official held-out set không dùng cho prompt tuning. Sau khi được phép, chạy reviewer baseline cố định trên Kaggle, ghi response parse/contract failure/abstention, error/warning counts và mọi failed/not_checked records. Chỉ sau human annotation mới tính precision/recall theo code, false positives/negatives, case-level agreement, abstention coverage và phân tích self-review bias. Định nghĩa denominators rõ; không loại reviewer failures để tạo tỷ lệ đẹp. Chưa có scores, thresholds, comparison model hoặc kết quả GPU nào trong Task 09B.

## 11. Kiểm thử và phần chưa triển khai

```bash
.venv/bin/python -m pytest tests/test_semantic_validation.py tests/test_qwen_backend.py tests/test_story_prompts.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Tests dùng synthetic independent payloads/deep copies/fakes, chặn network/GPU imports khi phù hợp; không sửa tests cũ để đạt PASS. Bao phủ strict schemas/verdict conflicts, evidence/location checks, JSON/non-finite/duplicate-key policy, prompt boundaries, summary mismatch offline mode, raw/metadata preservation, stale rejection, one reviewer call và shared-model load một lần. Không dùng model_construct hoặc official held-out set.

Chưa có Repair Controller, automatic production acceptance, ComicPipeline/Image Pipeline integration, semantic scene redundancy, GPU reviewer benchmark hoặc Kaggle notebook/run mới. Notebook 05/06 vẫn pin backend commit cũ cho baseline đã được thực nghiệm; muốn thử semantic reviewer/refactor cần source commit mới được review và user phê duyệt từng GPU run theo [Kaggle workflow](kaggle_workflow.md).
