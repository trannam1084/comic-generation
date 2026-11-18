# Comic Pipeline Orchestration — Task 07A

## 1. Trạng thái repository và phạm vi

Khi bắt đầu Task 07A, branch TV1 ở `376fbca`; sau fetch, `origin/main` ở `b04455a`. Main có PromptBuilder và dataclasses của TV2, trong khi `src/image_generator/image_generator.py` và `src/comic_renderer/renderer.py` vẫn là placeholder. Task 07A không merge main, đổi branch hoặc sửa các module TV2.

Task này triển khai orchestration và kiểm thử CPU bằng test doubles, không hoàn thành Task 07B hoặc full mock pipeline. Artifact do renderer double tạo chỉ là JSON/text kiểm thử alignment, không phải comic thực tế hoặc bằng chứng chất lượng hình ảnh.

## 2. Dependency Injection và interfaces

`ComicPipeline` không tự tạo backend, chọn model, tải weights hoặc đọc toàn bộ cấu hình. Caller phải inject bốn dependencies:

| Dependency | Interface | Trạng thái |
|---|---|---|
| Story Generator | `generate(summary: str) -> Storyboard` | Dùng implementation Task 06 và shared schema |
| Prompt Builder | `build(storyboard: Storyboard) -> list[ScenePrompt]` | Input shared; dùng adapter tạm với builder legacy TV2 |
| Image Generator | `generate(prompts: list[ScenePrompt]) -> list[GeneratedImage]` | Interface orchestration đề xuất, cần TV2 xác nhận |
| Renderer | `render(panels: list[ComicPanel]) -> Path` | Interface orchestration đề xuất, cần TV2 xác nhận |

Bốn Protocols chỉ mô tả các method cần thiết để type checking và thay dependency; không phải runtime validation framework. Không có registry, auto factory, backend fallback hoặc inference trong pipeline.

Story Generator và PromptBuilder có implementation thật được dùng trong tests; hai stage còn thiếu được inject bằng doubles trong `tests/test_pipeline.py`, không ghi code giả vào production modules thuộc TV2.

## 3. Kết quả và caption handoff

`ComicResult` là dataclass gồm:

- `storyboard`: shared Pydantic Storyboard.
- `prompts`: list các ScenePrompt nguyên interface TV2.
- `images`: list các GeneratedImage nguyên interface TV2.
- `comic_path`: Path của artifact do Renderer trả.

`ComicPanel` chỉ là envelope integration ghép `scene_index`, `caption_vi`, `generated_image`. Đây không phải một Storyboard schema khác. Renderer đọc payload qua `panel.generated_image.image`; các metadata seed/backend/params vẫn nằm trong GeneratedImage. Không đưa style, seed hoặc inference metadata vào Storyboard.

Result/Panel dùng frozen dataclass để không gán lại fields trực tiếp, nhưng Storyboard, lists và image payload bên trong vẫn mutable. Caller phải tuân thủ [quy tắc revalidation](data_contract.md), không suy ra deep immutability.

## 4. Luồng xử lý và scene alignment

1. Gọi Story Generator đúng một lần. Yêu cầu trả shared Storyboard, revalidate instance thành bản riêng và kiểm tra summary khớp input.
2. Truyền một bản Storyboard riêng cho PromptBuilder. Nếu builder mutate bản input này, pipeline báo lỗi thay vì coi thành công; instance của caller được giữ nguyên.
3. Kiểm tra prompts là list đúng bốn ScenePrompt, scene_index là integer thực sự và theo thứ tự chính xác 1, 2, 3, 4.
4. Truyền bản copy của list prompts cho Image Generator, gọi một lần.
5. Kiểm tra images là list đúng bốn GeneratedImage, index strict theo thứ tự 1–4 và image payload không phải None.
6. Tạo lookup ảnh theo scene index sau khi kiểm tra uniqueness/order; ghép đúng ảnh với caption từ Storyboard. Không dùng sort để chữa output sai.
7. Gọi Renderer một lần với bốn ComicPanel đã align.
8. Chỉ trả ComicResult nếu Renderer trả Path trỏ tới file tồn tại, không rỗng.

Không ép tuple/generator thành list để che interface sai; không bỏ/thay/tạo thêm prompt hoặc ảnh. Không retry, repair hoặc fallback. `runtime.max_retries` trong settings chưa được dùng ở orchestration này; chưa có config loader.

## 5. Error propagation

Exceptions từ dependencies hoặc shared Pydantic validation được propagate nguyên trạng. Pipeline không wrap mất type/cause, không gọi stage sau khi stage trước phát sinh lỗi. Tests xác minh exception identity, call count và thứ tự gọi tại từng stage.

`PipelineContractError(ValueError)` chỉ dành cho lỗi do pipeline tự phát hiện ở boundary. Thuộc tính `stage` là `story`, `prompts`, `images` hoặc `render`. Ví dụ: prompt count sai dừng trước Image Generator; image index sai dừng trước Renderer; artifact thiếu/rỗng/không phải file không tạo ComicResult thành công. Lỗi filesystem trong quá trình kiểm tra artifact cũng được propagate, không bị đổi thành trạng thái thành công.

Kiểm tra artifact chỉ xác nhận Path/file/non-empty, không decode định dạng ảnh, đo chất lượng hoặc chứng minh freshness của file. Renderer chịu trách nhiệm thực sự tạo artifact đúng lần gọi và format được nhóm thống nhất. Payload GeneratedImage hiện khai báo Any trong TV2; pipeline chỉ reject None, chưa xác minh đó là PIL Image. Không tự cài Pillow hoặc dựng renderer để làm thay phần việc này.

## 6. Adapter compatibility chuyển tiếp

`src/storyboard/compat.py` thuộc phạm vi TV1, có `LegacyPromptBuilderAdapter`. Caller bọc builder legacy một cách rõ ràng:

```python
from src.image_generator.prompt_builder import PromptBuilder
from src.storyboard.compat import LegacyPromptBuilderAdapter

prompt_stage = LegacyPromptBuilderAdapter(PromptBuilder())
```

Adapter revalidate shared Storyboard trước, rồi dựng các dataclasses đã tồn tại của TV2 bằng mapping từng field. Characters/scenes và scene references chuyển từ list sang tuple rõ ràng; text, IDs, thứ tự và caption giữ nguyên. Không thêm schema độc lập, không dùng model_construct hoặc bỏ qua validation. PromptBuilder tiếp tục tạo final prompts riêng; base image prompts không bị ghi đè.

Adapter là giải pháp tạm thời; cần bỏ wrapper khi Hoàng Anh migration PromptBuilder sang shared Pydantic/list. Không truyền shared Storyboard trực tiếp cho builder legacy chỉ vì duck typing có thể chạy: khi đó ScenePrompt.character_ids có thể thành list trái type annotation tuple hiện tại. ScenePrompt và GeneratedImage vẫn thuộc Image Pipeline.

## 7. Ví dụ kiểm thử orchestration trên CPU

Từ repository root, dùng `.venv` hiện có:

```bash
.venv/bin/python -m pytest tests/test_pipeline.py::test_success_uses_real_story_generator_and_prompt_builder -v
.venv/bin/python -m pytest tests/test_pipeline.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Test thành công dùng `StoryGenerator(MockStoryBackend())`, PromptBuilder thật qua adapter, image double tạo payload kiểm thử và renderer double ghi JSON artifact trong pytest tmp_path. Assertions kiểm tra cả captions, image identity/index, input arguments, call order và artifact. Một test process mới chặn import GPU/provider packages và mọi socket/urllib network operation trong lúc import/chạy pipeline.

Ví dụ cách lắp ghép; hai biến doubles dưới đây phải được cung cấp từ test harness, chưa phải backend production có sẵn:

```python
from src.pipeline import ComicPipeline
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.story_generator import StoryGenerator
from src.image_generator.prompt_builder import PromptBuilder
from src.storyboard.compat import LegacyPromptBuilderAdapter

pipeline = ComicPipeline(
    story_generator=StoryGenerator(MockStoryBackend()),
    prompt_builder=LegacyPromptBuilderAdapter(PromptBuilder()),
    image_generator=image_double,
    renderer=renderer_double,
)
result = pipeline.generate(summary_matching_fixture)
```

Test doubles chỉ kiểm tra wiring, sequencing và failure boundaries. Chúng không thực hiện sinh ảnh/render captions như Mock Image Generator hoặc Renderer thực tế TV2 sẽ xây, và không được quảng bá là comic backend đã hoàn tất.

## 8. Những điều kiện còn thiếu

- Hoàng Anh xác nhận interfaces image/render và ComicPanel handoff, triển khai backend CPU/mock và Renderer thật với font tiếng Việt/artifact format.
- Migration PromptBuilder sang shared schema, bỏ adapter sau khi cập nhật interface/tests; chưa sửa tests TV2 trong task này.
- Integration thực tế giữa Storyboard, final prompts, image payloads và renderer output, gồm file/resource lifecycle và lỗi backend thực.
- Thống nhất image token limits, caption/layout limits, payload type checks và output format khi đã có backend.
- Không có Qwen Backend, Semantic Validator, Repair/retry, diffusion, Gradio hoặc evaluation trong Task 07A. Task 07B và full mock pipeline vẫn chưa hoàn thành.
