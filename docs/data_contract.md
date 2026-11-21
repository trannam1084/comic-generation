# Shared Storyboard Data Contract v1.0

## 1. Quyết định và phạm vi

Contract v1.0 là quyết định kỹ thuật ban đầu do TV1 — Trần Hải Nam đề xuất và nhóm trưởng cho phép triển khai trong Task 04–05. TV2 — An Hoàng Anh và TV3 — Nguyễn Công Thành chưa xác nhận đầy đủ; các ý kiến migration/rendering/evaluation còn cần review. Quyết định này thay thế trạng thái sơ bộ của tài liệu Task 03, không đồng nghĩa code TV2 đã được migration hoặc pipeline đã hoàn thiện.

Nguồn schema chung dự kiến: `src/storyboard/schema.py`, gồm ba class công khai `Character`, `Scene`, `Storyboard`, sử dụng Pydantic v2. Schema chạy trên CPU, không load model và không cần Kaggle, torch, transformers hoặc diffusers. Fixture chuẩn là [examples/storyboard.json](../examples/storyboard.json).

Schema chỉ thực hiện structural validation và tính toàn vẹn references. Story Generator thật, Semantic Validator, Repair và integration với Image Pipeline không thuộc task này.

## 2. Fields và kiểu dữ liệu

Tất cả fields trong bảng đều bắt buộc. JSON dùng arrays; Python dùng list, không chấp nhận tuple/set/generator thay list khi validate Python input theo cấu hình mặc định.

| Model | Field | Kiểu Python | Quy tắc |
|---|---|---|---|
| Character | `id` | `str` | Không rỗng/whitespace; ID phân biệt hoa/thường, không tự trim hoặc đổi case |
| Character | `visual` | `str` | Không rỗng/whitespace; mô tả ngoại hình dùng chung |
| Scene | `index` | `int` | Integer strict; từ chối string, float và boolean |
| Scene | `caption_vi` | `str` | Không rỗng/whitespace; caption tiếng Việt theo mục tiêu hệ thống |
| Scene | `image_prompt_en` | `str` | Không rỗng/whitespace; base prompt tiếng Anh, chưa ghép shared descriptions/style |
| Scene | `characters` | `list[str]` | Có thể rỗng; không lặp ID trong một scene |
| Storyboard | `summary` | `str` | Không rỗng/whitespace; giữ tóm tắt gốc |
| Storyboard | `characters` | `list[Character]` | ID không trùng; có thể rỗng nếu mọi scene không có references |
| Storyboard | `scenes` | `list[Scene]` | Chính xác bốn phần tử; index theo đúng thứ tự 1, 2, 3, 4 |

Schema không xác định ngôn ngữ tự động. `visual` trong fixture dùng tiếng Anh để ghép vào image prompt; chưa có language detector. Không áp đặt giới hạn số từ/ký tự cho caption hoặc base prompt ở v1.0 vì renderer và image backend chưa được kiểm chứng.

## 3. Structural validation

Cả ba model kế thừa cấu hình `strict=True`, `extra="forbid"`, `revalidate_instances="always"`:

- Không tự ép kiểu string thành integer hoặc số thành string. Tất cả cấp đều từ chối extra fields; không silently drop dữ liệu.
- Field validators từ chối chuỗi rỗng/whitespace, ID nhân vật trùng, scene references trùng và index sai thứ tự.
- `Field(min_length=4, max_length=4)` giới hạn số scenes. Không tự sort hoặc xóa phần tử để làm input hợp lệ.
- Model validator chạy sau khi các fields hợp lệ để kiểm tra mọi character reference có trong catalog của Storyboard.
- ID/reference được so sánh chính xác. `rabbit` và `Rabbit` là hai ID khác nhau; ` rabbit ` không tự đổi thành `rabbit`. Khoảng trắng bao quanh một chuỗi có nội dung được giữ nguyên.
- Không chỉnh caption, summary, visual hoặc base prompt. Không tự repair input không hợp lệ.

Scene validate độc lập chỉ biết local fields; không thể kiểm tra reference có tồn tại trong catalog hoặc scene có thuộc bộ index 1–4 hay không. Các invariants liên scene/catalog chỉ được bảo đảm khi validate toàn bộ Storyboard.

Không truyền các override như `strict=False` hoặc nới `extra` khi dùng contract. Các cấu hình này là mặc định của API chuẩn, không phải cơ chế chống caller cố ý bỏ qua validation.

## 4. API và JSON serialization

Từ repository root, trong môi trường có Pydantic v2:

```python
from pathlib import Path
from src.storyboard.schema import Storyboard

raw_json = Path("examples/storyboard.json").read_text(encoding="utf-8")
storyboard = Storyboard.model_validate_json(raw_json)
data = storyboard.model_dump()  # dict với các collections dạng list
restored = Storyboard.model_validate(data)
encoded = restored.model_dump_json(indent=2)
round_trip = Storyboard.model_validate_json(encoded)
json_schema = Storyboard.model_json_schema()
```

`model_validate` dùng cho Python input; `model_validate_json` dùng cho JSON text/bytes. Cả hai đều giữ nội dung string hợp lệ. JSON arrays được parse thành lists; serialize model trở lại arrays. Ba model dùng nguyên các phương thức Pydantic chuẩn, không override và không dùng `model_construct` trong luồng thông thường.

JSON Schema mô tả fields, required, additionalProperties và số lượng scenes. Không giả định JSON Schema xuất ra diễn đạt đầy đủ custom validators: non-whitespace strings, index sequence, uniqueness theo ID và references vẫn phải kiểm tra bằng Pydantic runtime. Client chỉ kiểm tra JSON Schema chưa tương đương kiểm tra Contract v1.0 đầy đủ.

## 5. Ví dụ valid và invalid

Ví dụ tối thiểu hợp lệ về cấu trúc, không có nhân vật; nội dung chỉ dùng minh họa, không phải output của LLM hoặc benchmark:

```json
{
  "summary": "Một cơn mưa đi qua khu vườn.",
  "characters": [],
  "scenes": [
    {"index": 1, "caption_vi": "Mây kéo đến.", "image_prompt_en": "Clouds gather over a garden.", "characters": []},
    {"index": 2, "caption_vi": "Mưa rơi xuống khu vườn.", "image_prompt_en": "Rain falls over the garden.", "characters": []},
    {"index": 3, "caption_vi": "Cơn mưa dần tạnh.", "image_prompt_en": "The rain slowly stops.", "characters": []},
    {"index": 4, "caption_vi": "Nắng trở lại.", "image_prompt_en": "Sunlight returns to the garden.", "characters": []}
  ]
}
```

Các ví dụ invalid có thể tái hiện bằng fixture, mỗi lần đọc tạo một input độc lập:

```python
import json
from pathlib import Path
from pydantic import ValidationError
from src.storyboard.schema import Storyboard

data = json.loads(Path("examples/storyboard.json").read_text(encoding="utf-8"))
data["scenes"][0]["index"] = "1"  # Sai kiểu, không tự ép thành integer.
try:
    Storyboard.model_validate(data)
except ValidationError as exc:
    for error in exc.errors():
        print(error["loc"], error["type"])
# ('scenes', 0, 'index') int_type
```

| Input invalid | Error location điển hình | Error type |
|---|---|---|
| Thiếu caption | `('scenes', 0, 'caption_vi')` | `missing` |
| Caption rỗng/whitespace | `('scenes', 0, 'caption_vi')` | `value_error` |
| Extra field `seed` ở Storyboard | `('seed',)` | `extra_forbidden` |
| Ba hoặc năm scenes | `('scenes',)` | `too_short` / `too_long` |
| Index trùng/sai thứ tự | `('scenes',)` | `value_error` |
| Character ID trùng | `('characters',)` | `value_error` |
| Reference lặp trong scene | `('scenes', 0, 'characters')` | `value_error` |
| Reference không tồn tại | `()` | `value_error`; message nêu `scenes[position].characters`, scene index và IDs lỗi |
| Python tuple thay list scenes | `('scenes',)` | `list_type` |
| JSON sai cú pháp | `()` | `json_invalid` |

`loc` dùng chỉ số list từ 0, còn `Scene.index` dùng 1–4. Lỗi references ở root vì do model validator kiểm tra liên field. Validators có thể dừng ở lỗi đầu tiên trong nhóm kiểm tra; chưa phải một báo cáo gom mọi semantic/structural issue cho Repair. Tests kiểm tra type/location thay vì toàn bộ message, tránh ràng buộc vào wording của một phiên bản package.

## 6. Mutability và ranh giới Semantic Validation

Đối tượng đã validate không nên bị thay đổi trực tiếp sau khi truyền giữa các module. Pydantic models và lists bên trong chưa được đóng băng; mutation không tự chạy lại toàn bộ invariants. `revalidate_instances="always"` yêu cầu kiểm tra lại khi instance được đưa qua `model_validate`, kể cả nested instances.

Khi cập nhật, ưu tiên dump, sửa bản dữ liệu rồi validate lại:

```python
data = storyboard.model_dump()
data["scenes"][0]["caption_vi"] = "Caption mới."
updated = Storyboard.model_validate(data)
```

Không coi `model_copy(update=...)` hoặc `model_construct` là đường validate cho dữ liệu thay đổi. Không coi kết quả serialize là bằng chứng instance chưa bị mutate.

Storyboard đúng cấu trúc nhưng đổi kết thúc từ rùa thắng sang thỏ thắng vẫn có thể pass schema. Unit test minh họa giới hạn này, không tuyên bố semantic error đã được phát hiện. Semantic Validator tương lai mới đánh giá bám summary, quan hệ nhân quả, trùng lặp, kết thúc và mức phù hợp ngôn ngữ. Schema không chứng minh chất lượng truyện/ảnh.

Retry policy dự kiến: tối đa **hai lần repair sau lần sinh storyboard đầu tiên**; tối đa ba lượt nếu tính lần đầu và hai repair. Chưa triển khai retry, LLM hoặc Repair trong task này; `runtime.max_retries = 2` là cấu hình nền dự kiến.

## 7. Ownership và migration cho TV2

- TV1 — Trần Hải Nam: shared schema, structural/semantic validation, Repair, Story Generation và Integration.
- TV2 — An Hoàng Anh: PromptBuilder, Image Generation, Renderer, Gradio; giữ các output types nội bộ Image Pipeline.
- TV3 — Nguyễn Công Thành: dataset, evaluation, test strategy và phối hợp contract/integration tests.

Code TV2 tại `899f99f` chưa được sửa hoặc đưa vào branch TV1 trong task này. Fields Character/Scene/Storyboard giữ nguyên tên; dataclasses/tuple cũ không được tự động chuyển đổi bởi strict schema.

Hướng migration dự kiến, cần TV2 review trước khi triển khai:

1. Thay imports Character/Scene/Storyboard bằng shared schema. Dùng `Storyboard.model_validate(data)` hoặc `model_validate_json`, thay `Storyboard.from_dict`.
2. Nếu chuyển một legacy dataclass instance, chuyển các tuples thành lists rõ ràng, kể cả nested scene references, rồi validate. `dataclasses.asdict` riêng lẻ chưa bảo đảm chuyển tuple thành list.
3. PromptBuilder vẫn tạo final prompt riêng, không ghi đè `image_prompt_en` hoặc `caption_vi`. Giữ `ScenePrompt` và `GeneratedImage` thuộc Image Pipeline; không đưa seed/style/inference params vào Storyboard.
4. Chuyển `scene.characters` thành `tuple(scene.characters)` khi tạo `ScenePrompt.character_ids` để bảo toàn interface tuple hiện có. Renderer phải nhận caption từ Storyboard hoặc interface đã thống nhất, vì ScenePrompt hiện không mang caption.
5. Malformed inputs có thể bị reject ngay tại parse bằng `ValidationError`, trước `PromptBuilder.build`; cập nhật vị trí assertions tương ứng. Không dùng `model_construct` để ép input sai qua parse nhằm giữ nguyên tests cũ.
6. Fixture chuẩn là `examples/storyboard.json`; `data/storyboard_sample.json` ở nhánh image hiện tương đương, cần thống nhất dùng chung hoặc kiểm tra đồng bộ. Không sửa fixture của TV2 trong task này.

Các điểm còn mở: font/layout và khả năng hiển thị caption dài; token limits của image backend; style/ablation configuration; final prompt metadata; exception/result interface của Semantic Validator/Repair; migration import paths. Không tự đặt hard length limits trước khi kiểm chứng renderer/backend và chưa tuyên bố đã có đồng thuận đầy đủ của TV2/TV3.

## 8. Kiểm thử trên CPU và dependencies

Cần Python hỗ trợ cú pháp `typing.Self` (3.11 trở lên), Pydantic v2 và pytest. `requirements.txt` giới hạn Pydantic ở major v2 cho API này, không lock exact version hoặc yêu cầu GPU stack. Task đã tạo `.venv` riêng với quyền người dùng; không nâng cấp Python hệ thống.

Từ root repository:

```bash
.venv/bin/python -m pytest tests/test_storyboard_schema.py -v
.venv/bin/python -m pytest -v
git diff --check
```

Tests đọc fixture độc lập, kiểm tra strict types/collections, extra fields, count/order, text rỗng, uniqueness/references, round-trip, JSON Schema, mutation/revalidation và giới hạn semantic. Không cần Kaggle, model weights hoặc network để chạy.

API được đối chiếu với [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), [validators](https://docs.pydantic.dev/latest/concepts/validators/) và [configuration](https://docs.pydantic.dev/latest/api/config/) trong tài liệu chính thức Pydantic, cùng package thực tế trong `.venv`.
