# Factory và configuration — Task 10A.1

## Phạm vi thực tế

Nguồn cấu hình `src/configuration.py`; `src/factory.py` re-export `PipelineConfig`, `load_pipeline_config` và tiếp tục cung cấp **một** `build_pipeline`. Không có factory/orchestration thứ hai. ComicResult và adapters Task07B giữ nguyên.

| Story backend | Story device | Image backend/device | Trạng thái |
|---|---|---|---|
| mock | cpu | mock/cpu | CPU mock PNG đã chạy thực tế |
| qwen | explicit cuda:N | mock/cpu | Factory wiring đã kiểm thử bằng CPU injected doubles; chưa chạy real factory inference |
| Bất kỳ | Bất kỳ | sdxl/API/khác | Raise unsupported configuration, không downgrade |

`PipelineConfig()` vẫn mock/mock/cpu, output root `<repository>/outputs`, seed42 và retry0. Mock chỉ hỗ trợ exact summary trong fixture; không tự sinh truyện mới. Real Qwen chỉ được chọn rõ ràng bằng story_backend và supported CUDA device; không tự chuyển cpu thành cuda:0.

## Python API và devices

```python
from src.factory import PipelineConfig, build_pipeline, load_pipeline_config

mock = build_pipeline(PipelineConfig(device="cpu"))  # Alias cũ vẫn hoạt động.

# Chỉ build: không gọi load/generate/review hoặc tải weights.
config = PipelineConfig(
    story_backend="qwen",
    story_device="cuda:0",
    image_device="cpu",
    cache_dir="/kaggle/working/hf_cache",
)
pipeline = build_pipeline(config)
# pipeline.generate(summary) là real inference; chỉ chạy trong task đã được phê duyệt.
```

| Field | Built-in default/quy tắc |
|---|---|
| story_backend | mock; chỉ mock/qwen, case-sensitive |
| image_backend | mock; concrete real backend TV2 chưa được tích hợp |
| device | Optional legacy alias cho cả hai stages; không trộn với split fields |
| story_device / image_device | Optional selectors; omitted resolve cpu, không tự chọn GPU |
| output_dir | outputs; nonblank str/Path, không NUL/lone surrogate |
| max_retries | None=auto; constructor resolve mock0/qwen2; strict integer không âm, reject bool |
| base_seed | 42; strict integer, reject bool; giữ negative integer tương thích TV2 |
| cache_dir | None; chỉ qwen; nonblank str/Path nếu được cung cấp |

Đọc `resolved_story_device`, `resolved_image_device`, `output_root`, `resolved_cache_dir` để lấy effective values. `device`, `story_device`, `image_device` có thể còn None như selectors chưa được chỉ định. Factory validate lại config trước wiring. Không có GPU availability/resource query ở build; runtime kiểm tra khi load. CUDA format giữ đúng existing backend `cuda:[0-9]+`.

Alias `device="cpu"` hỗ trợ usages Task07B; trộn alias và bất kỳ split field nào bị reject kể cả cùng giá trị, kể cả đến từ các config layers khác nhau. Để Qwen story GPU và mock image CPU, dùng split fields. Có thể clear alias từ lower layer bằng explicit override `{"device": None}`; không tự bỏ lower-layer keys để đoán ý caller.

Relative output/cache/YAML paths đều resolve từ repository root, không từ current working directory hoặc YAML parent directory. Config/build không tạo cache hay download model. Không truyền credentials trong paths hoặc config.

## Retry semantics và Dependency Injection

- Omitted/None max_retries: mock0, qwen2.
- Explicit0 luôn giữ0 cho B0; explicit1/2/... giữ nguyên.
- Constructor resolve default một lần. Khi tạo config từ config đã resolve (ví dụ dataclasses.replace), giá trị integer hiện có tiếp tục là explicit value; muốn backend-dependent default mới phải truyền None.
- Mock budget dương cần explicit repair backend; không có mock repair fallback.
- Qwen factory tạo **một QwenStoryBackend** rồi truyền cùng object làm initial và repair backend vào BoundedRepairController. max_retries0 không gọi repair.
- Controller acceptance/algorithm không đổi: JSON + Shared Schema + exact original summary; warnings/semantic verdict không kích hoạt repair. Downstream exceptions/history giữ contract Task07B.

Giữ injection points `initial_backend`, `repair_backend`, `story_stage`, `prompt_stage`, `image_backend`, `renderer_backend`. Trong mock mode, các explicit dependencies override default constructors như Task07B; caller phải hiểu đây là injected implementation, không phải chứng cứ default mock có chức năng tương ứng.

Trong selected **qwen mode**, reject story_stage/initial_backend/repair_backend overrides để không silently thay selected real backend bằng mock/scripted alternative hoặc bỏ retry config. Test seam riêng `qwen_loader=...` dùng exact loader API của Qwen backend, nhận model_id/revision/device/cache_dir, trả tokenizer/model/runtime doubles. Đây không phải fake production Qwen backend. Prompt/image/renderer injection vẫn dùng được; qwen_loader trong mock mode hoặc non-callable loader bị reject. StoryStage override không kết hợp với nonzero retry config.

## Shared runtime và frozen configuration

Qwen model/tokenizer: Qwen/Qwen2.5-3B-Instruct, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`. FP16, batch1, greedy, max_new_tokens1024, repetition_penalty1.0, num_beams1, num_return_sequences1; không quantization, auto device_map hoặc remote code.

Factory dùng public constructor/device/cache_dir/loader, không đổi inference implementation, generation parameters hoặc prompt versions. Story prompt `storyboard-v1.0-baseline-001`; repair `storyboard-repair-v1.0-deterministic-001`; Semantic V1/V2 giữ nguyên và không được gọi. Import/build không load tokenizer/model, không import GPU packages; lazy load khi actual generate được gọi. Một successful load được cache cho cả initial/repair trong cùng backend instance.

## Explicit YAML/environment loader

```python
import os
from src.factory import load_pipeline_config, build_pipeline

config = load_pipeline_config(
    "configs/settings.yaml",
    environ=os.environ,          # Explicit opt-in; không có ambient environment mặc định.
    overrides={"output_dir": "outputs/local"},
)
pipeline = build_pipeline(config)
```

Precedence: **built-in defaults → YAML → supported environment overrides → explicit flat caller overrides**. Merge raw settings trước, rồi validate effective config và resolve retry default; không resolve mock default0 sớm rồi vô tình áp nó cho qwen.

`load_pipeline_config()` không tham số chỉ trả built-in defaults. `build_pipeline(PipelineConfig(...))` không gọi loader, không tự đọc YAML/environment. Không có implicit dotenv parser. `.env.example` chỉ là template để caller tự export hoặc truyền mapping; không chạy source/.env parsing tự động.

YAML sections/keys được hỗ trợ:

```yaml
story:
  backend: mock
  device: cpu
  cache_dir: null
image:
  backend: mock
  device: cpu
  base_seed: 42
runtime:
  output_dir: outputs
  max_retries: null
```

Legacy `runtime.device` map tới alias device; không kết hợp split YAML devices. Reject unknown sections/keys và non-mapping root/sections. Explicit overrides dùng flat PipelineConfig field names, không nhận unknown fields. Lower-layer values được override có thể bị thay thế theo precedence; effective values được validate strict, không coercion YAML booleans/floats thành integers.

YAML dùng private loader kế thừa `yaml.SafeLoader`, import lazy, theo safe-constructor API của [official PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation). Không tự viết YAML parser, dùng unsafe Loader/FullLoader hoặc sửa global PyYAML constructors/state.

Trước khi tạo mapping dictionary, loader construct từng key bằng PyYAML rồi kiểm tra hash/equality của constructed keys. Duplicate keys/sections bị reject ở root và mọi nested mapping, kể cả cùng value, quoted/unquoted tương đương hoặc scalar aliases. Các keys bằng nhau theo constructed Python semantics (ví dụ true và1) cũng là duplicate. Non-hashable keys fail rõ ràng; không stringify để vượt validation. Cùng key name ở hai mappings riêng biệt vẫn hợp lệ.

**YAML merge keys (`<<` / merge tag) bị reject**, không flatten/merge rồi giữ first/last value. Ordinary scalar/mapping aliases được parser hỗ trợ nhưng không bypass duplicate checks; chưa mở rộng thành general YAML resource-security framework. Quoted string `"<<"` không phải merge semantics; vẫn phải vượt known-key validation của configuration schema.

Duplicate/merge/unhashable mapping errors trả ValueError với fixed reason và line/column, không echo key, arbitrary value hay document. Empty/non-mapping documents và malformed YAML vẫn fail theo contract. Missing PyYAML raise ConfigurationDependencyError rõ ràng, không fallback defaults hoặc tự cài. Unsafe object constructors tiếp tục bị reject. `yaml_loader` là trusted parser test seam; production path luôn dùng strict SafeLoader-derived policy khi không inject parser.

Duplicate rejection áp dụng trong từng YAML mapping, **không cấm intentional overrides giữa YAML/environment/explicit layers**. Precedence và final-backend retry resolution giữ nguyên.

| Environment key | Field |
|---|---|
| STORY_BACKEND / IMAGE_BACKEND | story_backend / image_backend |
| STORY_DEVICE / IMAGE_DEVICE | story_device / image_device |
| DEVICE | legacy device alias |
| OUTPUT_DIR | output_dir |
| MAX_RETRIES | max_retries; integer text hoặc exact `auto` |
| BASE_SEED | base_seed; integer text |
| STORY_CACHE_DIR | cache_dir; empty string nghĩa None |

Chỉ lookup các documented keys; unrelated environment variables được bỏ qua, không đọc credential values như HF_TOKEN/IMAGE_API_KEY, không dump/print/persist environment. Integer text không được strip và không chấp nhận true/false, float hoặc whitespace. Unknown YAML/explicit fields bị reject, không silently ignore. Credentials không thuộc config này; authentication thuộc runtime được phê duyệt riêng.

## Dependencies, tests và giới hạn

Task10A.1.1 được user cho phép cài duy nhất **PyYAML6.0.3** vào project .venv Python3.12.3;12existing packages giữ nguyên versions và pip check PASS. Task10A.1.2 không cài/nâng/hạ package. `requirements.txt` vẫn khai báo `PyYAML` không pin:6.0.3 là **actual tested version**, không phải version constraint mới.

Actual YAML integration đã chạy với real configs/settings.yaml và temporary YAML fixtures. Targeted config/factory+integration suite **178PASS**; full CPU suite **877PASS**, không skipped/failed/errors. Có30regression cases mới cho duplicate root/nested/quoted/equivalent keys, merge keys, aliases, invalid/unsafe documents, global PyYAML isolation, intentional precedence và safe error display. Hai original P1 probes từng accepted retry2/che unknown section đều được giữ thành permanent tests và hiện reject. Existing CPU mock path vẫn chạy khi YAML/GPU/UI imports bị chặn; parsing không load model hoặc gọi network.

```bash
.venv/bin/python -m pytest tests/test_pipeline_configuration.py tests/test_pipeline_integration.py -q
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_pipeline.py
.venv/bin/python -m pip check
git diff --check
```

CLI mặc định không đổi, vẫn mock; real mode chọn explicit Python config. Chưa thêm CLI real execution shortcut, metadata global state hoặc per-request evaluation envelope. Nếu cần metadata export sau này, thiết kế request-scoped result/callback riêng; không gắn mutable global last-result.

TV2 có thể build rồi inject pipeline vào UI để gọi generate(summary), lấy comic_path và xử lý StoryStageError; không sửa UI trong task này. TV2 cần bàn giao concrete image backend/generate_all contract, device/seed semantics, resource requirements và failure policy trước real image factory wiring. Hiện ImageStageAdapter giữ generate_all + seed semantics đã có.

Mỗi lần build Qwen pipeline tạo backend riêng; không global runtime cache giữa nhiều pipelines, không thread-safety claim. Tái sử dụng một pipeline theo luồng tuần tự để tránh load nhiều model. Chưa có public unload/offload manager; bỏ pipeline/backend references và GPU cleanup phải do caller quản lý trong phiên được phê duyệt. Không tự phân phối nhiều GPU hoặc chứng minh đủ VRAM khi chạy đồng thời story và diffusion. CPU doubles chỉ xác nhận wiring/software contracts, không chứng minh GPU factory inference hoặc semantic quality.
