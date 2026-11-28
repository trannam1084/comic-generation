# Comic Generation — Sinh truyện tranh từ tóm tắt tiếng Việt

## 1. Giới thiệu đề tài

Comic Generation là đồ án xây dựng hệ thống chuyển một đoạn tóm tắt truyện tiếng Việt thành truyện tranh bốn khung, có caption tiếng Việt và bố cục 2×2. Nhóm sử dụng LLM Prompting để sinh Storyboard, kiểm tra dữ liệu có cấu trúc, tạo mô tả ảnh và ghép ảnh với caption.

Đóng góp chính là **Story Consistency Validation & Repair**: kiểm tra đầu ra bằng các điều kiện xác định và giới hạn số lần yêu cầu model sinh lại khi có lỗi. Mô tả ngoại hình nhân vật dùng chung được bổ sung vào prompts để hỗ trợ tính nhất quán giữa các cảnh; hiệu quả về ngữ nghĩa và hình ảnh vẫn cần đánh giá riêng.

**Trạng thái cập nhật ngày 28/11/2026:** PR #27 (Gradio), #36 (backend SDXL), #38 (evaluation framework), #39 (story runner) và #40 (Task 6 A/B) đã merge vào `main`. Tuy vậy, factory vẫn mặc định ảnh mock, `PipelineConfig` chưa cho chọn `image_backend=sdxl`, và `python app.py --demo` chỉ chạy mock/CPU. Kết quả SDXL thật là các lần chạy GPU riêng lưu artifacts ngoài repository; chưa nghiệm thu live Gradio Qwen → SDXL.

## 2. Kiến trúc hệ thống

```text
Tóm tắt tiếng Việt độc lập
  → StoryStage: BoundedRepairController
      → Sinh raw Storyboard bằng Qwen hoặc fixture mock
      → Deterministic Validation: JSON, Shared Schema, exact summary
      → Bounded Repair nếu có hard error và còn budget
  → Shared Storyboard gồm đúng 4 scenes
  → PromptBuilder: base prompt + shared character descriptions + art style
  → Image Generation: backend mock CPU hiện có trong factory
  → ComicRenderer: ảnh + captions tiếng Việt
  → Comic PNG bố cục 2×2
```

Điểm vào dùng chung là `build_pipeline(PipelineConfig(...))`, sau đó gọi `pipeline.generate(summary)`. Kết quả `ComicResult` cung cấp `storyboard`, `prompts`, `images` và `comic_path`. Factory dùng cùng một Qwen backend cho initial generation và repair, giữ model runtime đã load trong backend đó. Backend thật được load khi sinh truyện; import hoặc build factory không tự tải weights.

Xem [pipeline và adapters](docs/pipeline.md), [configuration](docs/configuration.md) và [thiết kế kiến trúc ban đầu](docs/architecture.md). Các tài liệu theo task có thể giữ mô tả lịch sử; cần phân biệt mốc triển khai với mốc thực nghiệm.

## 3. Chức năng đã triển khai

| Thành phần | Chức năng hiện có trên main |
| --- | --- |
| Shared Storyboard Schema | Pydantic schema cho summary, character catalog và đúng 4 scenes; kiểm tra thứ tự 1–4, IDs và references. |
| Deterministic Validation | Kiểm tra JSON syntax, Shared Schema và summary khớp chính xác original input; lưu errors và warnings riêng. |
| Bounded Repair | Hệ thống chỉ yêu cầu mô hình sinh lại Storyboard khi phát hiện lỗi JSON không hợp lệ (`INVALID_JSON`), sai cấu trúc (`SCHEMA_VIOLATION`) hoặc nội dung tóm tắt không khớp với đầu vào (`SUMMARY_MISMATCH`). Số lần sửa được giới hạn, tối đa hai lần đối với cấu hình Qwen mặc định. Quá trình sửa dừng ngay khi Storyboard đạt yêu cầu. |
| Shared factory và configuration | Hỗ trợ mock story + mock image trên CPU và Qwen story trên CUDA + mock image trên CPU; cấu hình Python trực tiếp hoặc explicit YAML/environment loader. |
| PromptBuilder | Ghép base image prompt với shared visual descriptions và art style, giữ scene alignment. |
| Image Generation và ComicRenderer | MockImageGenerator tạo ảnh kiểm thử bằng Pillow; renderer ghép bốn panels, captions và comic PNG trong unique output directory. |
| Semantic Reviewer V1/V2 | Structured LLM review phục vụ offline analysis; verdict không phải ground truth và không kích hoạt automatic acceptance/repair. |
| Offline Evaluation Harness | Validate frozen plan, paired B0/B1 records, provenance hashes; tính structural/coverage/cost metrics và chuẩn bị human semantic matching. |

Warnings không tự kích hoạt repair. Backend/infrastructure failure được báo lỗi và giữ history, không tự fallback sang mock để tạo kết quả thành công.

| PR liên quan | Trạng thái đã xác minh |
| --- | --- |
| [#33 — Offline Evaluation Harness](https://github.com/trannam1084/comic-generation/pull/33) | Đã merge, gồm root matching và human gold-readiness fixes. |
| [#20 — Dataset và evaluation của TV3](https://github.com/trannam1084/comic-generation/pull/20) | Đã đóng, không merge; không coi đây là official dataset/rubric trên `main`. |
| [#27 — Gradio UI của TV2](https://github.com/trannam1084/comic-generation/pull/27) | Đã merge; demo CLI hiện dùng mock/CPU. |

## 4. Công nghệ sử dụng

| Công nghệ | Vai trò |
| --- | --- |
| Python | Pipeline, configuration, validation, evaluation và scripts. CPU development đã kiểm thử với Python 3.12.3. |
| Pydantic v2 | Shared Schema và structured validation/repair/evaluation records. |
| Qwen/Qwen2.5-3B-Instruct | Mô hình ngôn ngữ được sử dụng để sinh Storyboard và tạo lại nội dung khi hệ thống phát hiện lỗi cấu trúc hoặc dữ liệu không hợp lệ. |
| Pillow và Noto Sans | Mock images, caption tiếng Việt và ghép comic PNG. Font có sẵn trong repository. |
| PyYAML | Explicit configuration loader với safe parsing và reject duplicate keys. |
| pytest | CPU unit/integration tests bằng fixtures và injected doubles. |
| Kaggle, Git và GitHub | GPU experiments, lưu provenance và review mã nguồn. |

Các thực nghiệm Qwen nêu dưới đây dùng revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, FP16, `cuda:0`, batch 1, greedy decoding và `max_new_tokens=1024`. Story prompt là `storyboard-v1.0-baseline-001`; repair prompt là `storyboard-repair-v1.0-deterministic-001`.

Gradio đã merge; đường demo mặc định là mock. SDXL backend và story runner đã merge và có kết quả Kaggle GPU thực, nhưng factory chưa cho chọn SDXL qua cấu hình và chưa nghiệm thu UI real Qwen → SDXL. Việc có interface Image Generation không đồng nghĩa đã có kết quả ảnh diffusion.

## 5. Cài đặt môi trường

Chạy các lệnh từ repository root. Môi trường CPU không cần PyTorch, Transformers, Diffusers hoặc Gradio. [requirements.txt](requirements.txt) khai báo Pydantic, Pillow, PyYAML và pytest; comments dùng ASCII để tránh lỗi đọc requirements theo Windows cp1258.

**Linux, với Python 3.12 đã cài:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

**Windows PowerShell, với Python 3.12 và Python Launcher đã cài:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Bước cài packages cần nguồn package phù hợp; các ví dụ CPU mock bên dưới không tải model, font hay gọi dịch vụ mạng. Không cần đặt `PYTHONUTF8=1` để che lỗi đọc fixture. Việc chạy toàn bộ main trên Windows 11 vẫn cần xác nhận riêng.

Dependencies GPU được tách trong [requirements-llm.txt](requirements-llm.txt) và [tài liệu môi trường](docs/environment.md), không nằm trong hướng dẫn CPU này. Không tự nâng/hạ packages hoặc tải weights khi chỉ muốn xem demo mock.

## 6. Hướng dẫn chạy CPU mock pipeline

Linux:

```bash
.venv/bin/python scripts/run_pipeline.py
.venv/bin/python scripts/run_pipeline.py --output-dir outputs/demo --base-seed 42
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_pipeline.py
.\.venv\Scripts\python.exe scripts/run_pipeline.py --output-dir outputs/demo --base-seed 42
```

Script gọi shared factory với `story_backend=mock`, `image_backend=mock`, CPU và retry budget 0. Nó dùng đúng independent sample summary tương ứng [examples/storyboard.json](examples/storyboard.json):

> Thỏ thách rùa thi chạy. Thỏ chủ quan ngủ quên giữa đường, còn rùa kiên trì về đích và chiến thắng.

MockStoryBackend chỉ hỗ trợ đúng tóm tắt mẫu này, không sinh truyện tùy ý. CLI hiện không có tham số nhập summary mới hoặc chọn GPU backend.

Thành công sẽ in actual output path. Mỗi lần chạy tạo thư mục riêng, không ghi đè lần trước:

```text
outputs/comic-<unique>/
  panel_1.png
  panel_2.png
  panel_3.png
  panel_4.png
  comic.png
```

Với `--output-dir outputs/demo`, thư mục run nằm bên dưới `outputs/demo/`. Comic mặc định có kích thước **1060 × 1320 pixels**. Các ảnh mock có màu nền, số cảnh và seed để kiểm tra luồng xử lý; chúng không minh họa nội dung truyện bằng diffusion.

Có thể chạy CPU tests từ repository root:

```bash
.venv/bin/python -m pytest -q
```

Trên Windows dùng `.\.venv\Scripts\python.exe -m pytest -q`. Lần verification Ubuntu ở Task 11A.4 ghi nhận **1002 tests PASS**; đây là kiểm thử phần mềm, không phải số mẫu đánh giá chất lượng model.

Cấu hình nâng cao dùng `PipelineConfig` và `load_pipeline_config`. Precedence của loader là defaults → YAML → supported environment overrides → explicit caller overrides; không tự đọc `.env`. Mock default retry 0, Qwen default retry 2, explicit retry 0 được giữ nguyên. Lệnh demo luôn dùng CPU mock, không ngầm chuyển sang Qwen. Chi tiết tại [configuration](docs/configuration.md).

## 7. Kết quả thực nghiệm và phân tích

### Paired B0/B1 development comparison — Task 09D.2B

Mỗi case có một initial Qwen raw output duy nhất, dùng chung cho cả hai variants. B0 có `max_retries=0`; B1 có `max_retries=2` và chỉ repair khi production controller yêu cầu. Bộ 12 inputs gồm bốn summaries đã dùng trong development và tám summaries synthetic exploratory mới.

| Variant | Structural accepted | Tỷ lệ trên 12 planned cases |
| --- | ---: | ---: |
| B0 — no repair | 10/12 | 83,33% |
| B1 — bounded repair | 12/12 | 100% |

Mức tăng Structural Acceptance là **+16,67 điểm phần trăm (percentage points)**. Hai initial failures tự nhiên của lần chạy đều được accepted sau first repair.

Đổi lại, tổng `model.generate` latency quy thuộc B1 tăng khoảng **20,16%** so với B0 trong cùng experiment. Đây là model-generation latency, không phải whole-pipeline wall time. Initial generation chỉ thực thi một lần mỗi case; không cộng hai logical totals để tính physical GPU cost.

Nguồn: `aggregate.json` trong session `20261120T172149Z-1797b06e5c`. Đây là development comparison, không phải official held-out benchmark; không chứng minh generalization hoặc semantic correctness.

### Real Qwen story + CPU mock image smoke — Task 10A.1.3B

Một lần chạy qua production factory và ComicPipeline trên Kaggle sử dụng Qwen trên Tesla T4 và mock images trên CPU:

| Chỉ số | Kết quả ghi nhận |
| --- | ---: |
| Initial generation / repair | 1 initial + 1 repair |
| Accepted controller status | `accepted_after_repair` |
| Image prompts / mock images | 4 / 4 |
| Comic PNG | 1060 × 1320 pixels |
| Peak allocated VRAM | Khoảng 6,11 GiB |
| Pipeline elapsed | Khoảng 108,465 giây |

Nguồn: `timing_summary.json`, `controller_result.json` và `pipeline_outcome.json` trong session `20261120T192019Z-5e2ff11a82`. Pipeline elapsed gồm lazy load và các stages, không tương đương thời gian `model.generate` riêng.

**Structural Acceptance** ở đây nghĩa là JSON, Shared Schema và exact original-summary matching đều PASS. Nó không xác nhận truyện đúng về nhân vật, vai trò, sự kiện hoặc kết thúc. Smoke này cũng không phải full diffusion comic generation.

Evidence ZIPs được lưu ngoài repository, không commit raw outputs hoặc weights. SHA-256 để đối chiếu:

- Task 09D.2B — `20261120T172149Z-1797b06e5c.zip`: `bb8805673c5ad918ae8f818b4d831da7a40a55d492c993411e6e0aa82c62d57b`.
- Task 10A.1.3B — `20261120T192019Z-5e2ff11a82.zip`: `9e7932229b7c95726c8cdb0738f3e466059ba48649b143c32b88398ce37349cd`.

## 8. Thiết kế đánh giá

[Offline Evaluation Harness](docs/evaluation_workflow.md) đã merge qua PR #33 và được kiểm thử bằng synthetic CPU fixtures. Harness xử lý records đã có, không điều phối inference mới.

- Freeze planned case inventory, input/output hashes, source/model/prompt revisions và evaluation policy trước khi scoring.
- B0/B1 phải có cùng initial raw hash. Acceptance dùng planned denominator; báo riêng coverage, failed, partial và not-run cases.
- Conditional Repair Success dùng số eligible initial failures đã thực sự gọi repair backend làm mẫu số; zero denominator trả `null`.
- Tách physical cost khỏi logical B0/B1 cost, backend invocation khỏi observed model.generate count; missing measurements giữ `null/not_available`.

Để đánh giá nội dung truyện có hợp lý và bám sát tóm tắt ban đầu hay không, nhóm dự kiến đối chiếu kết quả của mô hình với các nhận xét do con người thực hiện. Chỉ những nhận xét đã được kiểm tra và thống nhất mới được dùng làm dữ liệu chuẩn để đánh giá. Các trường hợp còn chưa chắc chắn được ghi nhận riêng, không tự động tính là đúng hoặc sai.

- Semantic Evaluation cần human annotations độc lập với reviewer predictions, tám canonical issue codes và evidence truy vết đúng source/path/quote.
- Full gold gate không mở khi còn unresolved uncertain findings. One-to-one matching cần explicit human discrepancy mapping; exact evidence không chứng minh semantic reasoning đúng.

Official dataset/split/rubric ở PR #20 chưa được nghiệm thu. Chưa có official Test scores hoặc semantic precision/recall/F1; không dùng synthetic fixtures làm official gold và không đưa human labels vào model prompts. Real-image comparison cần TV2 bàn giao backend/evidence và quy trình đánh giá ảnh riêng.

## 9. Cấu trúc repository

```text
src/
  story_generator/      # Story backends, prompts và Bounded Repair
  storyboard/           # Shared Schema, deterministic/semantic validators, compat
  image_generator/      # PromptBuilder, image interfaces và mock backend
  comic_renderer/       # Captions và ghép comic PNG
  offline_evaluation/   # TV1 offline structural/cost/semantic matching preparation
  evaluation/           # Khu vực evaluation của TV3
  factory.py            # Shared factory
  configuration.py      # Explicit configuration và loader
  pipeline.py           # ComicPipeline và ComicResult
  pipeline_adapters.py  # Story/Prompt/Image/Render integration boundaries
scripts/                # CPU demo và các tiện ích
configs/                # Cấu hình mẫu
examples/               # Storyboard fixture
assets/fonts/           # Font renderer và license/provenance
notebooks/              # Các notebooks đã được version trong repository
tests/                 # Unit và integration tests
docs/                  # Tài liệu kỹ thuật theo từng task
data/                  # Khu vực dữ liệu; official dataset còn chờ review
```

`app.py` có Gradio demo entry point `python app.py --demo` trên `main` (mock); chưa nghiệm thu production entry point Qwen → SDXL. Các notebooks thực nghiệm local và ZIP artifacts không mặc nhiên là files đã phát hành trong repository.

## 10. Phân công nhóm

| Thành viên | Trách nhiệm chính |
| --- | --- |
| TV1 — Trần Hải Nam, nhóm trưởng | Story Generation, Shared Schema, Deterministic Validation, Bounded Repair, factory/pipeline integration và offline harness. |
| TV2 — An Hoàng Anh | PromptBuilder, Image Generation, ComicRenderer, character consistency và Gradio UI. |
| TV3 — Nguyễn Công Thành | Dataset, rubric/human annotation, evaluation methodology, ablation và test strategy. |

Ownership và phối hợp review được mô tả trong [CONTRIBUTING.md](CONTRIBUTING.md).

## 11. Giới hạn hiện tại

- B0/B1 mới được so sánh trên 12 development inputs; integration smoke chỉ gồm một input. Chưa đủ bằng chứng để kết luận khả năng tổng quát hóa.
- Structurally accepted vẫn có thể sai ngữ nghĩa. Semantic Reviewer V1/V2 giữ cho offline analysis, không dùng làm production hard gate hoặc automatic repair trigger.
- Mock images không phản ánh khả năng minh họa hoặc character consistency của model ảnh. Chưa nghiệm thu SDXL/real diffusion trong shared factory.
- Human adjudication 12 B1 development Storyboard đã được TV1/TV2/TV3 thống nhất phương án B (19 finding: 11 error, 8 warning); không suy rộng sang official held-out Test. Gradio UI PR #27 đã merge, nhưng demo được kiểm chứng là mock.
- Chưa xác nhận toàn bộ main trên Windows 11; môi trường GPU và dependency versions có thể khác giữa các Kaggle sessions.
- Chưa có automatic GPU offloading manager hoặc đánh giá đầy đủ tài nguyên khi kết hợp Qwen với real image backend.

## 12. Tài liệu tham khảo và quyền sử dụng

- AI VIET NAM — AIO2025 — Project: Comic Generation: tài liệu nhóm dùng làm nguồn tham khảo. Repository chưa lưu PDF/phiên bản/trang để đối chiếu; không gán các cải tiến của nhóm thành nội dung đã xác minh từ tài liệu này.
- Hướng dẫn và provenance Qwen: [Qwen inference](docs/qwen_inference.md), [Qwen repair](docs/qwen_repair.md), [model/license review](docs/model_license.md).
- Contracts: [data contract](docs/data_contract.md), [validation và repair](docs/validation_and_repair.md), [repair controller](docs/repair_controller.md), [semantic validation](docs/semantic_validation.md).
- Thực nghiệm và tái lập: [Kaggle workflow](docs/kaggle_workflow.md), [offline evaluation](docs/evaluation_workflow.md).

Mã nguồn repository sử dụng [MIT License](LICENSE). Model, dataset, tài liệu tham khảo và font có điều kiện sử dụng riêng; xem [font provenance](assets/fonts/PROVENANCE.md) và [font license](assets/fonts/OFL.txt). MIT của repository không thay thế quyền sử dụng các tài sản bên ngoài. Legacy scripts được giữ ngoài pipeline; không phân phối chúng hoặc dữ liệu chưa được xác minh quyền sử dụng.


## Trạng thái nghiệm thu trước bàn giao (28/11/2026)

- **Demo CPU:** `python app.py --demo` dùng mock story và mock image. Phải giữ banner rõ đây không phải ảnh SDXL thật.
- **GPU artifacts:** 5 comic real SDXL story runner và 20 comic Task 6 A/B là hai thí nghiệm riêng; mô tả, notebook và điều kiện chạy xem `docs/image_generation.md`.
- **Human adjudication:** 12 B1 và ba phiếu cá nhân là dữ liệu private, không commit vào GitHub public. Ba thành viên đã thống nhất phương án B: 19 semantic findings (11 error, 8 warning) trên 10 case, hai case NO_ERROR; riêng case_010_D02/D03 được ghi là vấn đề scene references bên ngoài tám mã semantic. Đây là nhãn development human-panel, không phải Test benchmark.
- **Release:** chạy pytest và smoke UI trên commit cuối, ghi logs, hash artifacts, xác minh báo cáo rồi mới tag.

Chi tiết trong [checklist bàn giao TV1](docs/tv1_release_checklist.md).
