# Shared Pipeline Integration — Task 07B và 10A.1

## 1. Trạng thái và kiến trúc thực tế

Task 07A tạo shared orchestration; Task 07B nối các production interfaces đã có trên main thành CPU mock pipeline. Không tạo pipeline implementation thứ hai. Chạy thành công tạo bốn mock images, captions tiếng Việt và comic PNG layout 2×2 bằng Pillow. Mock images chỉ có màu nền/số cảnh/seed, **không phải diffusion results**; MockStoryBackend chỉ trả fixture cho exact sample summary, không phải AI sinh truyện tùy ý. Chưa có full real AI pipeline.

```text
original summary
  → RepairStoryStageAdapter → BoundedRepairController → MockStoryBackend
  → Shared Storyboard
  → LegacyPromptBuilderAdapter → PromptBuilder TV2
  → ImageStageAdapter → MockImageGenerator.generate_all
  → ComicPanel[4] (scene index + caption + GeneratedImage)
  → RenderStageAdapter → ComicRenderer.render → save → comic.png
```

Story/Repair prompts, Qwen backend, deterministic validator, Shared Schema và semantic reviewers giữ nguyên. Semantic verdict không tham gia acceptance/automatic repair. Pipeline stage được gọi tối đa một lần; bên trong StoryStage, production controller có bounded generation attempts theo explicit retry configuration. Không thêm outer retry/fallback.

## 2. Shared interfaces và public API

`ComicPipeline.generate(summary) -> ComicResult` giữ nguyên. `ComicResult` gồm shared `storyboard`, list `prompts`, list `images` và `comic_path: Path`. `ComicPanel` giữ `scene_index`, `caption_vi`, `generated_image`. Không thêm metadata/style/seed vào Storyboard hoặc sửa TV2 schemas.

| Stage | Interface orchestration | Concrete handoff |
|---|---|---|
| Story | `generate(summary) -> Storyboard` | `RepairStoryStageAdapter(controller)` gọi controller một lần |
| Prompt | `build(storyboard) -> list[ScenePrompt]` | Existing `LegacyPromptBuilderAdapter(PromptBuilder())` |
| Image | `generate(prompts) -> list[GeneratedImage]` | `ImageStageAdapter` gọi TV2 `generate_all(prompts, base_seed=...)` một lần |
| Render | `render(panels: list[ComicPanel]) -> Path` | `RenderStageAdapter` gọi TV2 `render(images, captions)` rồi `save(RenderResult, run_dir)` |

Pipeline vẫn kiểm tra đúng bốn prompts/images, scene indices strict [1,2,3,4], không sort hoặc thêm/bỏ phần tử. PromptBuilder nhận copy Storyboard đã revalidate; nếu mutate input, pipeline dừng. Caption ghép theo scene index. Base prompts/captions/catalog không bị adapters ghi đè. Shared Pydantic/list sang legacy dataclass/tuple vẫn mapping tường minh qua adapter hiện có; cần TV2 migration trước khi bỏ adapter. ScenePrompt/GeneratedImage thuộc ownership TV2.

## 3. StoryStage và failure contract

`RepairStoryStageAdapter.generate(summary)` truyền original summary nguyên văn, gọi đúng một controller invocation. Chỉ trả Storyboard khi result là `accepted_initial` hoặc `accepted_after_repair`, có accepted history/report và storyboard. Adapter revalidate Shared Storyboard, yêu cầu cả JSON/schema/exact summary PASS, kiểm tra accepted raw parse ra cùng board và summary khớp input. Không sửa raw, trim/normalize/sort hoặc tạo storyboard thay thế.

`StoryStageError(RuntimeError)` có:

- `category`: failed controller status (`input_failure`, `backend_failure`, `budget_exhausted`), hoặc `controller_exception`, `invalid_controller_result`, `invalid_accepted_result`.
- `result`: deep-copy RepairResult khi có, gồm original summary, diagnostics, attempts và failure category.
- `attempts`: snapshot history riêng, kể cả partial attempts khi controller raise unexpected exception.
- `__cause__`: original exception qua chaining với unexpected/controller boundary errors.

Failed result không bị trả thành success; downstream prompt/image/render không được gọi. Không gọi controller/model lần hai để xử lý lỗi. Không lưu mutable `last_result`, nên không có stale result slot giữa invocations. Dependencies vẫn có thể mutable; chỉ hỗ trợ sử dụng tuần tự, chưa có thread-safety claim. Với UI concurrent, TV2 cần quản lý dependency lifetime/concurrency riêng.

## 4. Image và renderer boundary

Image adapter validate list/four prompts/order trước gọi `generate_all`. Seed giữ semantics TV2: **base_seed + scene_index**, mặc định [43,44,45,46]. Backend exceptions propagate nguyên trạng; không fallback sang mock nếu injected backend thất bại.

Render adapter nhận đúng bốn ComicPanel theo [1,2,3,4], strict index types, Pillow image payload và nonblank captions. Mỗi invocation tạo atomic unique directory `comic-<random>/` bằng `tempfile.mkdtemp` dưới output root đã resolve; không dùng summary hoặc timestamp giây làm path. Không ghi đè previous runs.

TV2 renderer nhận hai lists images/captions, trả RenderResult và save năm files:

```text
outputs/comic-<unique>/
  panel_1.png
  panel_2.png
  panel_3.png
  panel_4.png
  comic.png
```

Adapter kiểm tra saved paths đúng run directory, không symlink, tồn tại/non-empty; dùng Pillow xác minh PNG/CRC và comic dimensions khớp RenderResult trước success. Renderer default panel512×512, caption height130, margin/gap12 tạo **1060×1320** comic. Rendering dùng Noto Sans font đã có cùng provenance/license trong `assets/fonts/`; không tải font hoặc fallback font thiếu dấu. TV2 renderer normalize NFC để đo/vẽ, không đổi captions trong Storyboard.

Nếu render/save/verification thất bại, exception propagate, không ComicResult thành công. Có thể giữ empty/partial unique run directory phục vụ debug; không xóa previous runs hoặc tự cleanup artifacts của lần lỗi. Backend được inject là trusted Python dependency; path checks không phải security sandbox cho code backend tùy ý.

## 5. Configuration và factory

Task10A.1 mở rộng existing factory, không thay adapters/orchestration Task07B. `PipelineConfig` và `load_pipeline_config` được re-export qua `src.factory`; nguồn config là `src/configuration.py`. Xem [configuration.md](configuration.md) cho field/device rules, precedence, DI policy và limitations.

Default `build_pipeline(PipelineConfig())` vẫn mock/mock/cpu, output root dựa trên repository, base_seed42 và max_retries0. Mock chỉ hỗ trợ exact fixture summary. Qwen mode cần explicit story_backend=qwen và story_device=cuda:N; image_device=cpu, retry mặc định2, explicit0 giữ nguyên. Một QwenStoryBackend instance làm cả initial và repair backend; chỉ lazy load khi generate, không gọi load/generate/review khi build.

`build_pipeline` không đọc ambient config. Caller opt-in `load_pipeline_config(yaml_path, environ=..., overrides=...)`: defaults → YAML → supported environment → explicit overrides. Không implicit .env loader. YAML import lazy; PyYAML6.0.3 đã được cài theo approval và actual YAML integration đã PASS. Private SafeLoader-derived parser reject duplicate keys/sections ở mọi level và reject merge keys; intentional cross-layer overrides vẫn hợp lệ. Mock/direct Python config không cần YAML. Settings và .env.example đã cập nhật sang mock defaults cùng auto retry để không ghi đè Qwen default khi chọn real mode.

Qwen selection không cho story-stage/backend override bypass selected backend; dùng public qwen_loader test seam để inject tokenizer/model/runtime doubles. Những injection points Task07B vẫn giữ trong mock mode; prompt/image/render injection giữ ở cả hai modes. Không fake real backend, thêm retry/fallback hoặc semantic-triggered repair.

```python
from src.factory import PipelineConfig, build_pipeline

pipeline = build_pipeline(PipelineConfig())
result = pipeline.generate(
    "Thỏ thách rùa thi chạy. Thỏ chủ quan ngủ quên giữa đường, còn rùa kiên trì về đích và chiến thắng."
)
print(result.comic_path)
```

## 6. CLI và CPU setup

Dùng project `.venv` hiện có, cần Pydantic v2 và Pillow để chạy mock; pytest cho tests. Không cần PyYAML, GPU stack hoặc Gradio cho path này. Không cài dependencies tự động.

Từ repository root:

```bash
.venv/bin/python scripts/run_pipeline.py
.venv/bin/python scripts/run_pipeline.py --output-dir outputs --base-seed 100
.venv/bin/python -m pytest tests/test_pipeline_integration.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
git diff --check
```

Có thể gọi script bằng absolute path từ cwd khác; default fixture/font/output paths vẫn dựa vào repository. CLI dùng independent sample string khớp exact `examples/storyboard.json`; không đổi fixture summary hoặc đọc output để giả lập success. Thành công in actual PNG path. Chỉ thêm PNG artifacts dưới ignored outputs hoặc tmp_path, không lưu notebook/model artifacts.

## 7. Gradio handoff và những phần còn lại

TV2 có thể inject pipeline đã build vào UI, gọi `pipeline.generate(summary)` và dùng `result.comic_path`. Với story failure, đọc `StoryStageError.category/result/attempts`; log/report phù hợp, không tự gọi lại backend hoặc fallback. Image/render exceptions có thể được UI hiển thị an toàn theo exception contract. Task này không sửa `app.py` hoặc merge UI PR.

CPU mock chỉ nhận exact fixture summary. Qwen story + mock image đã có factory wiring và CPU injected tests ở Task10A.1; chưa chạy real factory invocation. Real image backend/credential management chưa được tích hợp. Không coi bounded repair hoặc semantic reviewers là đã nâng chất lượng nội dung trong pipeline mock.

Task09D.2B riêng đã ghi nhận paired development structural acceptance10/12→12/12, hai initial failures accepted sau first repair. Đây là GPU experiment riêng trên development inputs, không phải kết quả của CPU integration tests và không chứng minh semantic correctness. Story/Repair components và prompts đã freeze; task này không tune/rerun GPU.

## 8. Verification sau strict YAML fix — Task10A.1.2

Targeted config/factory+integration178PASS; full CPU877PASS, không skipped/failed/errors. Hai original duplicate YAML probes đều reject trước factory build/load. Strict loader giữ safe constructors/global PyYAML state, không echo key/value; malformed/empty/invalid shape/object tags vẫn reject. Actual default CPU mock CLI tiếp tục tạo unique1060×1320PNG. Không thay adapters, shared Qwen runtime, Story/Repair prompts hoặc acceptance algorithm. Không có real factory GPU inference trong task này.
