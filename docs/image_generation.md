# Image Generation (Task 3 và Task 6)

Tài liệu mô tả backend sinh ảnh thật của nhóm: `SDXLImageGenerator`, model được dùng, môi trường đã kiểm chứng, số đo, kết quả thử nghiệm sơ bộ và các giới hạn đã biết. Mọi số liệu dưới đây lấy từ lần chạy thật trên Kaggle; chỗ nào chưa được xác minh thì ghi rõ là `<điền: ...>`. Mục 10 trình bày thí nghiệm Task 6 (character consistency).

## 1. Tổng quan

- Mục tiêu: từ storyboard hợp lệ (đúng 4 cảnh), sinh đúng 4 ảnh theo thứ tự cảnh, lưu seed và thông số suy luận, không âm thầm thay ảnh lỗi bằng ảnh giả.
- `SDXLImageGenerator` (`src/image_generator/sdxl_generator.py`) kế thừa `BaseImageGenerator`, nên thay thế được cho `MockImageGenerator` mà pipeline không đổi.
- Backend chỉ chạy trên GPU CUDA. Không có CUDA thì báo lỗi rõ ràng, không fallback sang mock.
- Mock backend vẫn dùng cho kiểm thử CPU, UI demo và các test.

## 2. Model

| Mục                        | Giá trị                                                                                                    |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Model                      | `Lykon/dreamshaper-xl-v2-turbo` (tinh chỉnh từ `stabilityai/stable-diffusion-xl-base-1.0`, theo thẻ model) |
| Pipeline class             | `StableDiffusionXLPipeline` (nạp qua `AutoPipelineForText2Image`)                                          |
| Revision cố định           | `f70ad5bce436c640d23fc02cd0a6ccc787280b6e` (cập nhật lần cuối 2024-02-19)                                  |
| Hugging Face Hub           | https://huggingface.co/Lykon/dreamshaper-xl-v2-turbo                                                       |
| Truy cập                   | Công khai, không bị khóa (`gated: False`, `private: False`) khi kiểm tra ngày 2026-11-20                   |
| License ghi trên thẻ model | `openrail++`                                                                                               |

**Điều khoản license liên quan đến đồ án:** Thẻ model chỉ ghi nhãn `openrail++` và repo không có file license riêng; nhãn này tương ứng với CreativeML Open RAIL++-M License (26/07/2023) của model nền, toàn văn tại https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md (chưa thấy điều khoản bổ sung của tác giả bản tinh chỉnh). Giấy phép cho phép dùng và phân phối model miễn phí, không đòi quyền với ảnh sinh ra (người dùng chịu trách nhiệm về ảnh), nhưng cấm một số mục đích (Attachment A: vi phạm pháp luật, gây hại cho trẻ vị thành niên, tạo thông tin sai lệch hoặc phỉ báng, phân biệt đối xử, tư vấn y tế, ...). Nếu phân phối lại model hoặc cung cấp qua dịch vụ trực tuyến cho người khác thì phải đưa các hạn chế này vào điều khoản sử dụng và kèm bản sao giấy phép; đồ án chỉ tải model lúc chạy, không đưa trọng số vào Git và chỉ dùng cho mục đích học tập. Đây là tóm tắt của nhóm, không phải tư vấn pháp lý.

**File được tải (fp16, tổng 6,46 GiB):** `unet` 4.897 MiB, `text_encoder_2` 1.325 MiB, `text_encoder` 235 MiB, `vae` 160 MiB, cùng các file cấu hình, `tokenizer`, `tokenizer_2` và `scheduler`.

**File cố ý không tải:** ba checkpoint đơn file ở thư mục gốc repo (`DreamShaperXL_Turbo_v2.safetensors`, `..._V2-SFW.safetensors`, `..._v2_1.safetensors`, mỗi file khoảng 6.618 MiB). Danh sách tải nằm trong `ALLOW_PATTERNS`; có test bảo đảm các pattern này không khớp ba file trên.

## 3. Môi trường đã kiểm chứng

| Thành phần        | Phiên bản                                                                           |
| ----------------- | ----------------------------------------------------------------------------------- |
| Nền tảng          | Kaggle Notebook, Python 3.13.16                                                     |
| GPU               | Tesla T4, 14,56 GiB, compute capability 7.5 (notebook thấy T4 x2, chỉ dùng một GPU) |
| PyTorch           | 2.11.0+cu130 (CUDA 13.0)                                                            |
| diffusers         | 0.42.0                                                                              |
| transformers      | 5.20.2                                                                              |
| accelerate        | 1.15.0                                                                              |
| huggingface_hub   | 1.33.0                                                                              |
| safetensors       | 0.8.0                                                                               |
| Pillow            | 13.0.0                                                                              |
| numpy             | 2.1.3                                                                               |
| pydantic / PyYAML | 2.14.1 / 6.0.3                                                                      |

Chưa kiểm chứng trên GPU khác, phiên bản thư viện khác hay hệ điều hành khác.

## 4. Cách dùng

```python
from src.configuration import PipelineConfig
from src.factory import build_pipeline
from src.image_generator.sdxl_generator import SDXLConfig, SDXLImageGenerator

generator = SDXLImageGenerator(SDXLConfig())  # chưa tải model
pipeline = build_pipeline(PipelineConfig(output_dir="outputs/real"), image_backend=generator)
result = pipeline.generate(summary)
```

Cấu hình mặc định (`SDXLConfig`), trùng với smoke test và ví dụ trên thẻ model: 6 bước, `guidance_scale` 2,0, 1024×1024, `float16`, variant `fp16`, scheduler `DPMSolverMultistepScheduler`, device `cuda`.

Hành vi cần nhớ:

- **Nạp lười:** import và constructor không import `torch`/`diffusers` và không tải model. Model được tải và nạp ở lần `generate` đầu tiên, rồi dùng lại cho các cảnh sau.
- **Revision bắt buộc là mã commit 40 ký tự hex**, tên branch như `main` bị từ chối.
- **Seed:** `generate_all(prompts, base_seed)` dùng seed `base_seed + scene_index`, độc lập với nội dung prompt. Cùng cảnh ở hai cấu hình prompt khác nhau luôn dùng cùng seed (yêu cầu cho thí nghiệm A/B). Seed được truyền tường minh qua `torch.Generator`.
- **Không thay ảnh lỗi bằng ảnh giả:** lỗi nạp hoặc sinh ảnh được raise nguyên vẹn, không retry, không fallback. Kết quả bị từ chối (`ImageGenerationError`) nếu pipeline không trả đúng một ảnh PIL, ảnh sai kích thước so với cấu hình, hoặc ảnh gần như đen hoặc trống (độ lệch chuẩn độ xám dưới 5 hoặc độ sáng trung bình dưới 5; ngưỡng chỉnh được trong `SDXLConfig`).
- **Log:** mỗi `GeneratedImage.params` chứa repo, revision, dtype, variant, scheduler, số bước, guidance, kích thước, device, thời gian nạp model và phiên bản `torch`, `diffusers`, `transformers`, `accelerate`, `huggingface_hub`.

## 5. Số đo (Kaggle T4, một GPU)

| Chỉ số                                        | Giá trị                                                                    | Nguồn                             |
| --------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------- |
| Tải model fp16                                | khoảng 36 giây (lần đo trong smoke test)                                   | Bước 3.2                          |
| Nạp model qua `SDXLImageGenerator` (gồm tải)  | 79,0 giây (phiên tương tác), 39,85 giây (Version 1)                        | Phụ thuộc đường truyền từng phiên |
| Sinh một ảnh 1024×1024                        | 8,77 đến 9,41 giây (Version 1)                                             | `metadata.json`                   |
| Ảnh đầu tiên sau khi nạp                      | 13,8 đến 17,8 giây (gồm khởi động)                                         | Smoke test và phiên tương tác     |
| Pipeline đủ 4 cảnh (story mock, SDXL, render) | 37,18 giây (Version 1)                                                     | `metadata.json`                   |
| VRAM sau khi nạp model                        | 6,57 GiB                                                                   | Smoke test                        |
| VRAM đỉnh                                     | 9,73 GiB trên 14,56 GiB                                                    | Smoke test và Version 1           |
| Độ dài prompt                                 | 46 đến 48 token (prompt), 38 token (negative của E0); giới hạn 77 của CLIP | Đo ở bước 3.2 và 3.2d             |

**Tính lặp lại:** cùng seed cho ảnh giống hệt từng pixel trong một phiên. Giữa hai phiên Kaggle độc lập (một phiên tương tác, một phiên Save & Run All), 9 file ảnh (`comic.png`, `panel_1..4.png`, `raw/scene_1..4.png`) có SHA-256 trùng hoàn toàn. Điều này chỉ được kiểm chứng trong môi trường ở mục 3; không bảo đảm trên GPU hoặc phiên bản thư viện khác.

SHA-256 của ảnh gốc `raw/` (dùng để so khớp khi chạy lại):

| File              | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| `raw/scene_1.png` | `83f8a78dd1d50ec2e7fce0b66954c50d7427494d6768be207d91da79b3c35c08` |
| `raw/scene_2.png` | `bf7d87b373b4ec7bde1c7c41061ac6aa244338dcbe32b6620775e4ba6aecc801` |
| `raw/scene_3.png` | `96048acb1836e94778f42355cc6c446724dd525a6dd8574fd109786e07e58e75` |
| `raw/scene_4.png` | `cba017afcbce82e1bbdb3c29a166068c326ff6d4223c9009fb6815a4098b7544` |

## 6. Thử nghiệm sơ bộ về prompt (pilot)

> Các số dưới đây do một người chấm bằng mắt từ ảnh, chưa chấm ẩn nhãn, chỉ có 4 seed (43 đến 46) mỗi cảnh. Cần người khác trong nhóm kiểm tra lại trước khi dùng trong báo cáo. Đây là quan sát để định hướng, không phải kết luận thống kê.

Cảnh dùng để thử: cảnh 1 (thỏ thách rùa) và cảnh 3 (thỏ ngủ, rùa đi qua). Tiêu chí: (a) một cảnh liền, (b) thỏ và rùa tách biệt, (c) không lai (thỏ không mang mai rùa, rùa không có tai thỏ), (d) khăn đỏ chỉ trên thỏ, (e) đúng một thỏ và một rùa.

1. **Style và negative (cảnh 1, 4 seed):** style `comic book illustration` cho ảnh một cảnh liền 3/4, ảnh bị chia khung ở seed 43. Style `children's storybook illustration, ..., single scene` cho 4/4. Thêm từ chống khung vào negative không thay đổi kết quả của style comic (vẫn 3/4). Nhóm dùng cấu hình **E0** từ đó: style storybook cộng negative có từ chống khung.
2. **Mô tả nhân vật (số ảnh không lai trên 4 seed, cảnh 1 và cảnh 3):** không mô tả (A0) 1/4 và 1/4; mô tả hiện tại (B1) 2/4 và 2/4; viết lại tách hai con (B2) 2/4 và 1/4. Khăn đỏ chỉ xuất hiện khi có mô tả nhân vật (hiển nhiên vì A0 không nhắc khăn). **Chênh lệch nằm trong dao động ngẫu nhiên, chưa đủ để kết luận phương án nào nhất quán hơn.**
3. **Từ chống lai và guidance (E0 đến E3):** thêm từ chống lai vào negative, tăng guidance từ 2,0 lên 3,5, hoặc cả hai đều cho 2/4 ảnh không lai ở mỗi cảnh, đúng bằng E0. Cùng những seed bị lỗi ở cả bốn cấu hình (seed 43 và 46 ở cảnh 1; seed 43 và 44 ở cảnh 3), nghĩa là **seed ảnh hưởng mạnh hơn các tham số này**. Guidance 3,5 làm màu đậm hơn, không giảm lỗi.

Lần chạy chính thức (Version 1, E0, seed 43 đến 46, một ảnh mỗi cảnh), chấm sơ bộ: (a) 4/4, (b) khoảng 3/4, (c) 1/4, (d) khoảng 3/4, (e) 0/4. Người chấm: <An Hoàng Anh>, ngày <22/11/2026>; chưa chấm ẩn nhãn.

## 7. Giới hạn đã biết

- **Nhân vật bị lai và dư nhân vật:** thỏ mang mai rùa, rùa có tai thỏ, và nhiều ảnh có thêm thỏ hoặc rùa ngoài hai nhân vật của truyện. Đây là hạn chế của model khi một prompt có hai con vật; chỉnh style, negative hay guidance trong pilot không khắc phục được.
- **Ảnh chưa luôn khớp caption:** ví dụ cảnh 3 thỏ thường không ngủ dưới gốc cây, cảnh 4 không thấy rõ vạch đích. Chưa đo mức khớp ảnh với caption bằng thực nghiệm.
- **Phụ thuộc môi trường:** tính lặp lại chỉ kiểm chứng trên T4 với bộ phiên bản ở mục 3.
- **Phụ thuộc mạng:** mỗi phiên Kaggle mới tải lại khoảng 6,5 GiB; thời gian tải thay đổi giữa các phiên.
- **Cảnh báo của thư viện:** diffusers 0.42.0 in cảnh báo `upcast_vae` đã lỗi thời (sẽ bị bỏ ở bản 1.0). Hiện không ảnh hưởng kết quả; cần theo dõi khi nâng cấp diffusers.
- **Chỉ một GPU, batch 1:** không có `device_map` tự động, không chạy được trên CPU.
- **Chưa là mặc định của pipeline:** cấu hình E0 được notebook truyền tường minh vào `PromptBuilder`. `PromptBuilder()` mặc định (dùng trong `build_pipeline`) vẫn là style và negative ban đầu. Đổi mặc định cần thống nhất với nhóm trưởng.

Cấu hình E0:

- style: `children's storybook illustration, clean line art, vibrant colors, single scene`
- negative: `text, letters, watermark, signature, blurry, low quality, deformed, extra limbs, multiple panels, collage, split screen, comic page, frame, border, grid`

## 8. Chạy lại trên Kaggle

1. Tạo notebook mới ở chế độ **Private**, accelerator **GPU T4 x2**, **Internet bật**.
2. Nhập `notebooks/03_image_inference.ipynb`. Notebook clone repo ở commit cố định và chạy lại được từ đầu bằng Run All.
3. Bấm **Save Version**, chọn **Save & Run All (Commit)**.
4. Tải đầu ra về máy, bỏ vào thư mục **ngoài repo** (ví dụ `comic-generation-experiments/task03/`). Không đưa ảnh, ZIP, model hay cache vào Git.
5. Kiểm tra toàn vẹn: giải nén **bản sao** của `task03_run.zip`, rồi trong thư mục `run_task03` chạy:

   ```powershell
   Get-Content SHA256SUMS | ForEach-Object {
       $expected, $name = $_ -split '  ', 2
       $actual = (Get-FileHash -Algorithm SHA256 $name).Hash.ToLower()
       "{0}  {1}" -f ($(if ($actual -eq $expected) { 'KHOP' } else { 'LECH' })), $name
   }
   ```

6. Tắt phiên khi xong để không tốn quota GPU.

Không đặt token hay khóa API vào notebook. Repo công khai nên không cần xác thực GitHub khi clone.

## 9. Dấu vết của lần chạy chính thức

| Mục                                     | Giá trị                                                                                                                                                                                                      |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Notebook                                | `comic-gen-03-image-inference` (Private), Version 1, `scriptVersionId` 372563258                                                                                                                             |
| Cách chạy                               | Save & Run All, 2 phút 40 giây, GPU T4 x2 (dùng một GPU)                                                                                                                                                     |
| Mã nguồn                                | `af9ada647266478ee331a4dc799e1354a9df3b15`                                                                                                                                                                   |
| Model, revision                         | `Lykon/dreamshaper-xl-v2-turbo`, `f70ad5bce436c640d23fc02cd0a6ccc787280b6e`                                                                                                                                  |
| Gói tải về (`results.zip`)              | SHA-256 `4FB58606427D56DFF70F97919A14B6EE0793EAD9B09E5601A66537EEE1E7A42F`                                                                                                                                   |
| `task03_run.zip` bên trong              | SHA-256 `2898213BD65E09F91C985E22495BB1AE7B260C64F28E77A71ACCDA222DBB72DB` so với dòng "ZIP:" trong đầu ra của Cell chạy pipeline là khớp `2898213bd65e09f91c985e22495bb1ae7b260c64f28e77a71accda222dbb72db` |
| Kiểm tra `SHA256SUMS` trên bản giải nén | 10/10 file khớp                                                                                                                                                                                              |
| `metadata.json`                         | SHA-256 `9d117c4d76df9b6e606b081499bc8d0b1db7b0cf2e0fb1dabad3a8114474d4ff`                                                                                                                                   |
| Ngày tải                                | `22/11/2026`                                                                                                                                                                                                 |

Dữ liệu thô nằm ngoài repo; chỉ các số liệu tổng hợp ở trên được đưa vào tài liệu.

## 10. Task 6: Character consistency (A và B)

So sánh hai cách sinh image prompt: **A** là prompt độc lập theo từng cảnh (không có mô tả nhân vật), **B** là prompt có mô tả nhân vật dùng chung (`PromptBuilder(use_shared_characters=True)`). Khác với pilot ở mục 6, thí nghiệm này dùng nhiều truyện khác cốt truyện, hai seed và chấm ẩn nhãn bởi người chấm độc lập. Chưa khẳng định B tốt hơn A khi chưa có kết quả chấm.

### 10.1 Thiết kế

| Mục             | Giá trị                                                                                                                                                                                                                         |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Đơn vị so sánh  | Một truyện tranh 4 khung, theo cặp (truyện, `base_seed`): A và B cùng seed theo từng cảnh, cùng model và revision, cùng thông số suy luận, cùng style và negative E0; chỉ khác việc có chèn mô tả nhân vật dùng chung hay không |
| Truyện          | 5 storyboard đã được nhóm trưởng duyệt (`story_013`, `story_020_v2`, `story_027`, `story_033_v2`, `story_050`); nội dung nằm ngoài repo                                                                                         |
| Seed            | `base_seed` 100 (tầng lõi, seed cảnh 101 đến 104) và 200 (tầng bổ sung, seed cảnh 201 đến 204); không trùng seed của pilot (43 đến 46)                                                                                          |
| Số truyện tranh | 5 truyện × 2 seed × 2 nhánh = 20 (mỗi tầng 10)                                                                                                                                                                                  |
| Chấm ẩn nhãn    | Mã truyện tranh `C01...` (lõi) và `E01...` (bổ sung); thứ tự xáo trộn bằng `shuffle_seed` 2026 (lõi) và 2027 (bổ sung); khóa A/B lưu riêng, không gửi người chấm                                                                |

### 10.2 Chạy thật

| Mục                                                          | Giá trị                                                                                                            |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Notebook                                                     | `notebooks/03c_ab_experiment.ipynb` (xóa output trước khi commit; storyboard nằm trong dataset private của Kaggle) |
| Môi trường                                                   | Kaggle, Tesla T4 (một GPU), ngày 25/11/2026                                                                        |
| Mã nguồn                                                     | `3772bb4e947e70265c1ae0b46c039a71b1004555` (nhánh `feature/image-pipeline`)                                        |
| Model, revision                                              | như mục 2                                                                                                          |
| Kết quả                                                      | 20 truyện tranh trong 948,9 giây (gồm nạp model 67,4 giây); VRAM đỉnh 9,74 GiB; không dùng mock fallback           |
| `ab_experiment_full.zip` (có khóa A/B, không gửi người chấm) | SHA-256 `5698623549aa63672153fa28497f2b4e9e66809e04f43df5342edc6cb2fa9470`                                         |
| `ab_for_raters_core.zip`                                     | SHA-256 `f01aec93252855296d7a6969ec12f8433d2efebb810f22bd1dd2877383da6ead`                                         |
| `ab_for_raters_extra.zip`                                    | SHA-256 `d3222730dddc341959690e87d9993115e031ceb6d1a879e6dcf43686aa7e5319`                                         |

Dữ liệu thô nằm ngoài repo; chỉ các số liệu tổng hợp ở trên được đưa vào tài liệu.

### 10.3 Phiếu chấm và cách phân tích

Mã nguồn: `src/image_generator/ab_rubric.py` (phiếu), `ab_experiment.py` (sinh ảnh), `ab_pack.py` (gói chấm ẩn nhãn), `ab_analysis.py` (phân tích).

- **Phiếu chấm** có một dòng toàn truyện (`panels_duplicate_figure` và `panels_blended_figure`, mỗi chỉ số từ 0 đến 4 khung) và một dòng cho mỗi nhân vật xuất hiện ở ít nhất 2 cảnh theo storyboard (`identity_consistency`, từ 1 đến 5, hoặc `NA` nếu người chấm chỉ thấy nhân vật ở dưới 2 khung). Chỉ số chính là `identity_consistency`.
- Người chấm chỉ so các khung có giống nhau hay không, không chấm ảnh có khớp mô tả nhân vật hay không. Chỉ số khớp thiết kế (ví dụ đúng màu theo mô tả) không đưa vào phiếu vì A không có mô tả, nên A thua ở chỉ số đó là điều hiển nhiên và nó không đo độ nhất quán.
- **Cách tính:** với mỗi người chấm, điểm của một truyện tranh là trung bình các nhân vật không `NA`; sau đó lấy trung bình các người chấm; so B với A theo từng truyện (B trừ A) và đếm số truyện B tốt hơn, A tốt hơn, hòa. Không dùng p-value, vì với 5 truyện kiểm định dấu hai phía có p nhỏ nhất 0,0625 nên không thể đạt mức 0,05. Báo cáo còn có hướng chênh lệch theo từng người chấm, số ô `NA` theo từng nhánh và độ đồng thuận giữa người chấm.

Chạy lại phân tích cho một tầng (cần thư mục `packs/core` lấy từ `ab_experiment_full.zip` đã giải nén, vì chỉ bản đầy đủ có khóa A/B):

```powershell
$env:PYTHONPATH = "."
python -m src.image_generator.ab_analysis --tier-dir <thư mục packs\core> --rater <TEN1>=<file1.csv> --rater <TEN2>=<file2.csv> --out <thư mục báo cáo mới>
```

### 10.4 Kết quả

Hai người chấm là TV1 và TV3 (hai thành viên khác của nhóm, không viết pipeline ảnh), được nhờ chấm một mình và không biết nhánh A hay B. Cả hai chấm đủ cả tầng lõi lẫn tầng bổ sung (mỗi tầng 10 truyện tranh, 26 dòng phiếu). Hai tầng cùng truyện nhưng khác seed, nên báo cáo từng tầng riêng và không gộp thành một con số. Báo cáo thô (`summary.md`, `analysis.json`, `per_comic.csv`) nằm ngoài repo.

**Chỉ số chính `identity_consistency` (thang 1 đến 5, cao hơn là tốt):**

| Truyện                      | Lõi: A | Lõi: B | Lõi: B trừ A | Bổ sung: A | Bổ sung: B | Bổ sung: B trừ A |
| --------------------------- | ------ | ------ | ------------ | ---------- | ---------- | ---------------- |
| `story_013`                 | 1,50   | 2,50   | +1,00        | 4,50       | 4,50       | +0,00            |
| `story_020_v2`              | 2,50   | 2,50   | +0,00        | 1,25       | 1,25       | +0,00            |
| `story_027`                 | 1,83   | 1,83   | +0,00        | 3,00       | 2,50       | -0,50            |
| `story_033_v2`              | 3,00   | 4,00   | +1,00        | 1,50       | 2,50       | +1,00            |
| `story_050`                 | 2,50   | 2,50   | +0,00        | 2,50       | 3,00       | +0,50            |
| Trung bình                  | 2,27   | 2,67   | +0,40        | 2,55       | 2,75       | +0,20            |
| B tốt hơn / A tốt hơn / hòa |        |        | 2 / 0 / 3    |            |            | 2 / 1 / 2        |

**Chỉ số phụ (số khung có lỗi, thấp hơn là tốt):**

| Chỉ số                    | Tầng    | Trung bình A | Trung bình B | B tốt hơn | A tốt hơn | Hòa |
| ------------------------- | ------- | ------------ | ------------ | --------- | --------- | --- |
| `panels_duplicate_figure` | lõi     | 0,60         | 0,80         | 1         | 1         | 3   |
| `panels_duplicate_figure` | bổ sung | 1,20         | 1,20         | 1         | 1         | 3   |
| `panels_blended_figure`   | lõi     | 1,10         | 0,70         | 2         | 0         | 3   |
| `panels_blended_figure`   | bổ sung | 1,20         | 1,00         | 2         | 0         | 3   |

**B trừ A theo từng người chấm, `identity_consistency` (trong ngoặc: số truyện B tốt hơn / A tốt hơn):**

| Người chấm | Lõi           | Bổ sung       |
| ---------- | ------------- | ------------- |
| TV1        | +0,00 (0 / 0) | +0,00 (1 / 1) |
| TV3        | +0,80 (2 / 0) | +0,40 (1 / 0) |

**Độ đồng thuận giữa hai người chấm:**

| Chỉ số                    | Tầng    | Số ô so sánh | Sai khác tuyệt đối trung bình | Chấm trùng nhau | Lệch không quá 1 |
| ------------------------- | ------- | ------------ | ----------------------------- | --------------- | ---------------- |
| `identity_consistency`    | lõi     | 12           | 1,00                          | 8%              | 92%              |
| `identity_consistency`    | bổ sung | 12           | 0,67                          | 33%             | 100%             |
| `panels_duplicate_figure` | lõi     | 10           | 1,00                          | 60%             | 70%              |
| `panels_duplicate_figure` | bổ sung | 10           | 1,20                          | 30%             | 80%              |
| `panels_blended_figure`   | lõi     | 10           | 1,40                          | 30%             | 50%              |
| `panels_blended_figure`   | bổ sung | 10           | 1,80                          | 20%             | 30%              |

Số ô `NA` bằng nhau giữa hai nhánh ở cả hai tầng (trung bình 1,0 trên 8 ô nhân vật mỗi nhánh, mỗi người chấm).

**Đọc kết quả (thống kê mô tả, không có p-value):**

- **Chỉ số chính:** B cao hơn A ở 4 trong 10 cặp (truyện, seed), thấp hơn ở 1, bằng nhau ở 5; chênh lệch trung bình +0,40 (lõi) và +0,20 (bổ sung) trên thang 1 đến 5. Các cặp cùng truyện không độc lập với nhau. Chỉ một truyện (`story_033_v2`) cho B cao hơn A ở cả hai seed; `story_013` chỉ ở seed lõi, `story_027` thậm chí A cao hơn ở seed bổ sung, nên hướng chênh lệch không ổn định giữa các seed.
- **Seed ảnh hưởng mạnh hơn việc chọn A hay B:** với cùng một truyện và cùng một nhánh, điểm đổi trung bình khoảng 1,3 điểm khi đổi từ seed 100 sang seed 200, so với chênh lệch A và B trong cùng một tầng trung bình khoảng 0,4 điểm. Điều này phù hợp với nhận xét ở mục 6 rằng seed ảnh hưởng mạnh hơn các tham số prompt.
- **Người chấm:** ở tầng lõi, phần B cao hơn A đến từ TV3; TV1 không ghi nhận chênh lệch nào. TV1 chủ yếu cho điểm 2 ở tầng lõi (10 trong 12 ô nhân vật không `NA`), còn TV3 cho điểm cao hơn TV1 ở 10 trong 12 ô chung (trung bình +0,83), nên mức chuẩn của hai người khác nhau. Ở tầng bổ sung mức chuẩn gần nhau hơn (trung bình +0,17) và thứ hạng điểm của hai người tương đồng hơn (hệ số tương quan hạng Spearman 0,81, so với 0,55 ở tầng lõi).
- **Chỉ số phụ:** `panels_duplicate_figure` không có hướng ổn định (1 truyện B tốt hơn, 1 truyện A tốt hơn ở cả hai tầng). `panels_blended_figure` thấp hơn ở B trong 2 trên 5 truyện ở cả hai tầng (cùng hai truyện là `story_033_v2` và `story_050`), nhưng chỉ TV3 ghi nhận chênh lệch và độ đồng thuận ở chỉ số này thấp nhất, nên chưa coi là bằng chứng.
- **Kết luận thận trọng:** chưa đủ cơ sở để khẳng định B nhất quán nhân vật hơn A. Dữ liệu chỉ gợi ý B không kém A và có thể nhỉnh nhẹ ở chỉ số chính, nhưng hiệu ứng nhỏ hơn dao động do seed và do người chấm.

**File điểm gốc (SHA-256):**

| File                         | Tầng    | Người chấm | SHA-256                                                            |
| ---------------------------- | ------- | ---------- | ------------------------------------------------------------------ |
| `TV1_rating_sheet_1.csv`     | lõi     | TV1        | `32163148bbb1a5ff7346a6fa0ffbcd627628fcd6d4f8b551c85cbe69f59f4b2c` |
| `TV1_rating_sheet_2.csv`     | bổ sung | TV1        | `1b6be296d1bb2446aaf1861af59a26ed2e78ae931ca75411da3f6c7b751d1e9a` |
| `TV3_rating_sheet.csv`       | lõi     | TV3        | `a976a4027238696457f07ccf7f3f5d4fa8eb477e2e4b6eb1bbbcec03e1f1cabf` |
| `TV3_rating_sheet_extra.csv` | bổ sung | TV3        | `11ed29510e275f2e5e883b841ceb563d300a50fc9d69e75088374a01dfb61f6f` |

### 10.5 Giới hạn riêng của Task 6

- Mẫu rất nhỏ (5 truyện), người chấm theo cảm nhận; kết quả là thống kê mô tả, không đủ để kết luận phương án nào tốt hơn một cách tổng quát.
- Số nhân vật được chấm nhất quán trong 5 truyện lần lượt là 1, 2, 3, 1, 1 (theo thứ tự `story_013`, `story_020_v2`, `story_027`, `story_033_v2`, `story_050`); ba truyện chỉ có một nhân vật để chấm nên chỉ số chính ở các truyện đó dựa trên rất ít dữ liệu.
- Mỗi tầng có cả hai nhánh A và B của cùng một truyện, nên người chấm có thể nhận ra các cặp dù đã ẩn nhãn.
- `manifest.json` chỉ ghi khi chạy xong cả bộ; nếu phiên Kaggle dừng giữa chừng phải chạy lại trong thư mục mới. `inference_params` trong manifest lấy từ ảnh đầu tiên, chưa kiểm tra mọi ảnh dùng cùng thông số.

- Chỉ có hai người chấm và họ có mức chuẩn khác nhau (mục 10.4); độ đồng thuận thấp, nhất là ở `panels_blended_figure`. Điểm được giữ nguyên như người chấm đã nộp, không chỉnh lại sau khi biết kết quả.
- Thí nghiệm chỉ có hai seed cho mỗi truyện và hai tầng không độc lập; không đủ để tách tác động của việc chọn A hay B khỏi tác động của seed.

## 11. Việc chưa làm

- **Task 6:** đã chấm và phân tích (mục 10.4); chưa khẳng định B tốt hơn A. Muốn kết luận chắc hơn cần thêm seed, thêm truyện và thêm người chấm.
- Tùy chọn: chạy riêng một truyện làm failure case (lưu tách khỏi bộ A/B) nếu còn thời gian.
- Đo mức khớp giữa ảnh và caption, độ đọc được của caption trên ảnh thật.
- Đề xuất với nhóm trưởng: đưa cấu hình E0 vào mặc định của `PromptBuilder` nếu nhóm đồng ý.
