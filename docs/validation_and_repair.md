# Deterministic Storyboard Consistency Validator — Task 09A

## 1. Bối cảnh và provenance

Đây là implementation TV1 — Trần Hải Nam, sử dụng [Shared Contract v1.0](data_contract.md) trong `src/storyboard/schema.py`. Không thay schema, baseline prompt, Qwen backend, StoryGenerator hoặc code TV2/TV3. Tên tài liệu mô tả hướng phát triển Validation & Repair; **Repair chưa được triển khai** trong task này.

Theo kết quả development do nhóm trưởng cung cấp, không phải các thí nghiệm được chạy lại trong Task 09A:

- Task 08B, một summary: JSON/schema/exact summary đều PASS, nhưng manual review thấy bốn character records cho hai nhân vật, hai IDs không dùng, visual descriptions trùng nguyên văn, references mâu thuẫn caption/base prompt, sai ngôn ngữ, thiếu causality và chi tiết không được nguồn xác nhận.
- Task 08C, ba synthetic development cases do ChatGPT đề xuất: JSON syntax 3/3 PASS; structural schema 3/3 PASS; StoryGenerator success 2/3; summary mismatch 1/3; unused characters xuất hiện ở 2/3 cases; exact duplicate visual descriptions ở 3/3; visual descriptions sai ngôn ngữ theo manual review ở 2/3. Manual review còn phát hiện sai đối tượng dịch và sai vai trò nhân vật giữa caption/image prompt.

Các tỷ lệ trên đếm **cases có hiện tượng**, không phải số issues/characters. Không dùng official held-out test set, không suy ra official benchmark, độ chính xác validator hoặc chất lượng chung của Qwen. Task 09A không đọc experiment artifacts để tái tính các số liệu này. Unit fixtures là dữ liệu tổng hợp nhỏ do TV1 tạo cho kiểm thử, không phải LLM outputs.

## 2. Ba lớp kiểm tra

| Lớp | Nội dung | Trạng thái Task 09A |
|---|---|---|
| JSON/structural | JSON text; required fields, strict types, extra fields, bốn scenes, order 1–4, IDs/references theo shared schema | Đã triển khai reporting |
| Deterministic consistency | Exact summary, unused IDs, exact duplicate visuals/captions | Đã triển khai; summary mismatch là error, ba checks còn lại là warnings |
| Semantic/language | Ý nghĩa nhân vật/đối tượng, causality, events/ending, ngôn ngữ, paraphrase redundancy | Chưa kiểm tra; cần Task 09B/manual review |

Exact summary chỉ kiểm tra trường `summary` bằng input gốc. Summary giống input không chứng minh scenes giữ các sự kiện/kết thúc. Structural validity không đồng nghĩa production success hoặc semantic validity.

Không đưa heuristics vào Shared Storyboard Schema. Không tự sửa, merge, xóa, sort, normalize, strip fences, ghi đè summary hoặc retry/fallback.

## 3. Public API và luồng xử lý

Module `src/storyboard/validator.py` có ba class công khai:

```python
from src.storyboard.validator import (
    StoryboardValidator,
    ValidationIssue,
    ValidationReport,
)

validator = StoryboardValidator()
report = validator.validate_raw(raw_output, expected_summary=original_summary)
# Hoặc kiểm tra shared Storyboard instance đã có:
report = validator.validate(storyboard, expected_summary=original_summary)
encoded_report = report.model_dump_json(indent=2)
json_ready = report.model_dump(mode="json")
```

`validate_raw` nhận **str**, giữ nguyên raw trong `report.raw_output`. Không chấp nhận bytes/dict/None hoặc tự chuyển chúng thành string. Luồng xử lý:

1. Kiểm tra argument `expected_summary`: None hoặc string không rỗng/whitespace. Caller truyền sai kiểu nhận TypeError; string rỗng nhận ValueError. Không trim input hợp lệ.
2. `pydantic_core.from_json(raw_output, allow_inf_nan=False)` parse output đúng một lần bằng cùng JSON engine của Pydantic; từ chối NaN/Infinity/-Infinity vì chúng không phải JSON chuẩn. API được đối chiếu với package local; pydantic-core đã là dependency của Pydantic v2, không thêm package. Markdown fences là INVALID_JSON, không được bóc bỏ.
3. JSON parse thất bại: `json_syntax=failed`; structural/summary là `not_checked`; chưa gọi Pydantic.
4. JSON parse thành công: gọi `Storyboard.model_validate(data)` đúng một lần, sử dụng strict shared schema. Không khai báo lại fields/rules của Storyboard.
5. Schema thất bại: structural `failed`, summary `not_checked`, không chạy consistency checks trên catalog/scenes chưa đáng tin cậy.
6. Schema hợp lệ: structural `passed`; nếu có expected summary thì so sánh exact, nếu không thì `not_checked`. Chạy ba consistency checks kể cả khi có summary mismatch để giữ diagnostics.

`validate` chỉ nhận shared Storyboard, không tự nhận legacy dataclass/dict. Revalidate instance đúng một lần vì model/lists hiện mutable và có `revalidate_instances="always"`. JSON syntax là `not_checked`, raw là None: validator không thể suy ra original JSON text từ instance. Mutation trước khi gọi có thể trở thành SCHEMA_VIOLATION; validator không sửa input.

Validator không gọi StoryGenerator hoặc backend. Reporting dùng lại **cùng schema và exact-summary policy**, không thay exception API của [StoryGenerator](story_generator.md). Report không chứa nested Storyboard để việc tạo report không vô tình revalidate Storyboard thêm lần nữa. Parse JSON của error serialization không phải parse lại raw output.

`production_success` là computed field ba trạng thái:

- False khi JSON/structural/summary có `failed`.
- True khi structural và summary đều `passed`, tương thích output gate của StoryGenerator cho input hợp lệ. Warnings không đổi True thành False.
- None khi chưa đủ thông tin, ví dụ không có expected summary.

Tên này không xác nhận đã gọi backend, đã render comic hoặc đã kiểm tra ngữ nghĩa. Với instance, JSON `not_checked` vẫn có thể đi cùng True vì đang xét các output invariants kiểm tra được. `semantic_validity` và `visual_language_validity` luôn `not_checked` trong phiên bản này.

## 4. Report và error taxonomy

ValidationReport/ValidationIssue dùng Pydantic v2 cho dữ liệu reporting và serialization, chỉ phụ thuộc CPU requirements hiện có. Report có các status fields, `raw_output`, `issues`, `pydantic_errors` và computed `production_success`. Evidence dùng `JsonValue`, không chứa exception object. Không tự ghi file, log raw, gọi API hoặc tải model.

| Issue code | Severity | Location/evidence |
|---|---|---|
| INVALID_JSON | error | Root `()`; message gốc của JSON decoder (kèm line/column khi decoder cung cấp) |
| SCHEMA_VIOLATION | error | Giữ loc Pydantic; mỗi lỗi thành một issue, evidence chứa toàn bộ chi tiết lỗi JSON |
| SUMMARY_MISMATCH | error | `("summary",)`; expected và actual nguyên trạng |
| UNUSED_CHARACTER | warning | `("characters", position, "id")`; character ID không dùng |
| DUPLICATE_VISUAL_DESCRIPTION | warning | Visual của phần tử đầu nhóm; visual nguyên văn, tất cả IDs và catalog positions |
| DUPLICATE_SCENE_CAPTION | warning | Caption của phần tử đầu nhóm; caption nguyên văn, tất cả scene indices và list positions |

List positions trong location từ **0**; `Scene.index` từ **1**. Location root cho lỗi unknown reference vẫn ở root theo shared model validator; không tự bịa lại vị trí chi tiết. Message Pydantic giữ nguyên trong issue.

`pydantic_errors` lấy từ JSON serialization của ValidationError: giữ `loc`, `type`, `msg`, `input`, `url` và `ctx` nếu có. Vì report phải serialize, exception như ValueError trong `ctx.error` được Pydantic chuyển thành string; không giữ Python exception object sống. Numeric overflow như input `1e999` có thể thành Infinity trong error serialization; constant không hữu hạn ở evidence được giữ dưới dạng string tên constant để JSON report hợp lệ. Raw output vẫn giữ nguyên để truy vết. Location được biểu diễn tuple trong issue và array khi xuất JSON. JSON syntax failure dùng decoder error thật, `pydantic_errors=[]` vì chưa gọi schema; không giả tạo `json_invalid` của Pydantic. Các message có thể thay đổi theo package version; consumers dựa vào code/type/location.

Giữ raw/evidence có thể chứa toàn bộ nội dung input. Caller chịu trách nhiệm lưu trữ phù hợp và không đưa credentials vào dữ liệu; module không tự in/log report.

## 5. Thuật toán và stable order

### UNUSED_CHARACTER

Lấy hợp của references từ **mọi** scene, sau đó duyệt catalog theo thứ tự gốc. ID không có trong tập hợp tạo một warning. Nhân vật chỉ xuất hiện ở scene cuối vẫn được tính là used; ID phân biệt case và whitespace theo contract.

### DUPLICATE_VISUAL_DESCRIPTION

Group characters bằng nguyên string visual trong dict giữ insertion order. Mỗi nhóm có ít nhất hai records tạo **một** warning với toàn bộ IDs/positions. Hai nhân vật khác nhau có ngoại hình giống nhau là khả năng hợp lệ; warning không kết luận duplicate identity.

### DUPLICATE_SCENE_CAPTION

Group scenes bằng nguyên string caption; nhóm ít nhất hai scenes tạo một warning. Không so sánh image prompt hoặc suy luận hai scenes có cùng ý nghĩa. Caption giống nhau có thể có chủ ý, nên vẫn chỉ warning.

Không normalized comparison ở Task 09A: không trim, đổi case, Unicode normalization hoặc paraphrase matching. Một khoảng trắng/dấu câu khác có thể làm mất exact match. Nếu thêm normalized checks sau này cần issue code/evidence/policy và tests riêng, không thay nghĩa của exact checks.

Thứ tự issues ổn định: lỗi Pydantic theo thứ tự schema trả về; với schema valid thì SUMMARY_MISMATCH trước, UNUSED_CHARACTER theo catalog, duplicate-visual groups theo vị trí xuất hiện đầu, duplicate-caption groups theo thứ tự scenes. Không sort input hoặc dùng thứ tự iteration của set để tạo issues.

Với C character records, S scenes, R references và T tổng độ dài text được hash/so sánh, phần consistency có expected time O(C + S + R + T), bộ nhớ phụ O(C + S + số IDs được dùng), ngoài input/report. Shared schema và JSON parsing có chi phí riêng theo kích thước dữ liệu; không phải benchmark đo runtime. S cố định bằng 4 theo contract.

## 6. Demo tổng hợp chạy CPU

Ví dụ sau do TV1 tạo để minh họa reporting, không phải output inference hoặc benchmark. Summary gốc được khai báo độc lập, không lấy từ output model để tự xác nhận chính nó.

```python
import json
from src.storyboard.validator import StoryboardValidator

original_summary = "Một người chăm vườn."
synthetic = {
    "summary": "Một người chăm vườn.",
    "characters": [
        {"id": "p1", "visual": "A person wearing green."},
        {"id": "p2", "visual": "A person wearing green."},
    ],
    "scenes": [
        {"index": 1, "caption_vi": "Người ấy chăm cây.", "image_prompt_en": "A person plants a seed.", "characters": ["p1"]},
        {"index": 2, "caption_vi": "Người ấy chăm cây.", "image_prompt_en": "A person waters the plant.", "characters": ["p1"]},
        {"index": 3, "caption_vi": "Lá mới mọc lên.", "image_prompt_en": "New leaves appear.", "characters": []},
        {"index": 4, "caption_vi": "Khu vườn xanh hơn.", "image_prompt_en": "A green garden.", "characters": []},
    ],
}
report = StoryboardValidator().validate_raw(
    json.dumps(synthetic, ensure_ascii=False), expected_summary=original_summary
)
print(report.json_syntax, report.structural_validity, report.summary_matching)
print(report.production_success)
print([(issue.code, issue.severity, issue.location) for issue in report.issues])
```

Kết quả deterministic dự kiến: `passed passed passed`, `True`, rồi ba warnings theo thứ tự UNUSED_CHARACTER tại character position 1, DUPLICATE_VISUAL_DESCRIPTION tại position 0, DUPLICATE_SCENE_CAPTION tại scene position 0. Không sửa p2 hoặc caption trùng.

## 7. Interface cho Repair Controller và Evaluation

- TV1/Repair tương lai nhận expected summary độc lập, raw output và ValidationReport. Dùng error codes/location/evidence để quyết định hành động sau khi được phê duyệt. Warning không tự động là lý do repair; Task 09A không chạy retry budget hoặc sửa JSON/nội dung.
- Không gọi lại backend chỉ để lập report. Không ghép validator như một wrapper gọi lại StoryGenerator trên cùng raw. Khi một integration đã có raw và cần report, dùng `validate_raw` làm một reporting pass; nếu chỉ có Storyboard từ StoryGenerator thì dùng `validate` và chấp nhận JSON status not_checked. Lần revalidate instance phục vụ phát hiện mutation, không phải gọi model lại.
- TV3/Evaluation dùng `model_dump(mode="json")` hoặc `model_dump_json`, giữ cả failed/not_checked records. Tách syntax/schema/summary success khỏi warning occurrence, severity và semantic review. None không được chuyển thành PASS; không loại failed outputs khỏi denominator. Report không tự tính scores/rates hoặc benchmark.
- TV2 không phải đổi PromptBuilder/ScenePrompt/GeneratedImage trong task này; các warning không tự đổi catalog, captions, references hoặc base image prompts trước rendering.
- Schema v1.0, backend protocol và StoryGenerator exceptions giữ nguyên. Chưa tự tích hợp validator vào ComicPipeline hoặc notebook 05/06.

## 8. False positives, false negatives và phần chưa triển khai

Unused catalog record có thể là dữ liệu dự phòng có chủ ý. Exact duplicate visual có thể mô tả hai người khác nhau. Caption lặp có thể là lựa chọn kể chuyện. Vì thế ba checks chỉ cảnh báo, không xác nhận nhân vật/cảnh bị trùng ngữ nghĩa và không tác động production output gate.

Exact comparison bỏ sót mô tả/caption tương đương nhưng viết khác, dịch khác hoặc chỉ khác whitespace. Reference hợp lệ nhưng trỏ sai nhân vật trong caption vẫn pass structural checks. Không phát hiện character role mismatch, object translation mismatch, missing key events, ending contradiction, semantic character duplication hoặc semantic scene redundancy. Test cố tình đưa những lỗi này vào dữ liệu vẫn pass để minh họa giới hạn, không phải tuyên bố validator đã phát hiện chúng.

**Hoãn language detection sang Task 09B.** Không có VISUAL_LANGUAGE_SUSPECT ở Task 09A; dấu tiếng Việt hoặc một tên riêng không đủ làm ground truth. Mô tả tiếng Việt hoặc tên riêng có dấu không tự tạo language issue. Cần phương pháp được kiểm chứng và khả năng abstain trước khi bổ sung heuristic/model.

Chưa có Semantic Validator, LLM-as-a-judge, Repair Controller, repair prompts, API calls, inference, dataset evaluation hoặc integration tự động. Baseline Qwen prompt `storyboard-v1.0-baseline-001` và pinned backend tại commit `390b069b9d5c4a83e97481580790760bf963efff` không thay đổi.

## 9. Kiểm thử local

```bash
.venv/bin/python -m pytest tests/test_storyboard_validator.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Tests tạo payload/deep copy độc lập, không đọc official held-out data. Bao phủ syntax/fences, strict schema errors, Pydantic context/location/type, summary exact match, warning groups, reference ở scene cuối, empty catalog, mutation/revalidation, stable order, serialization, parse/schema call count và semantic boundary. Một subprocess chặn GPU package imports/network để kiểm tra CPU-only behavior. Không cần cài thêm dependencies hoặc chạy Kaggle.
