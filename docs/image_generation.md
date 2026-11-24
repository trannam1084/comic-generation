# Image Generation (Task 3)

Tài liệu mô tả backend sinh ảnh thật của nhóm: `SDXLImageGenerator`, model được dùng, môi trường đã kiểm chứng, số đo, kết quả thử nghiệm sơ bộ và các giới hạn đã biết. Mọi số liệu dưới đây lấy từ lần chạy thật trên Kaggle; chỗ nào chưa được xác minh thì ghi rõ là `<điền: ...>`.

## 1. Tổng quan

- Mục tiêu: từ storyboard hợp lệ (đúng 4 cảnh), sinh đúng 4 ảnh theo thứ tự cảnh, lưu seed và thông số suy luận, không âm thầm thay ảnh lỗi bằng ảnh giả.
- `SDXLImageGenerator` (`src/image_generator/sdxl_generator.py`) kế thừa `BaseImageGenerator`, nên thay thế được cho `MockImageGenerator` mà pipeline không đổi.
- Backend chỉ chạy trên GPU CUDA. Không có CUDA thì báo lỗi rõ ràng, không fallback sang mock.
- Mock backend vẫn dùng cho kiểm thử CPU, UI demo và các test.

## 2. Model

| Mục | Giá trị |
|---|---|
| Model | `Lykon/dreamshaper-xl-v2-turbo` (tinh chỉnh từ `stabilityai/stable-diffusion-xl-base-1.0`, theo thẻ model) |
| Pipeline class | `StableDiffusionXLPipeline` (nạp qua `AutoPipelineForText2Image`) |
| Revision cố định | `f70ad5bce436c640d23fc02cd0a6ccc787280b6e` (cập nhật lần cuối 2024-02-19) |
| Hugging Face Hub | https://huggingface.co/Lykon/dreamshaper-xl-v2-turbo |
| Truy cập | Công khai, không bị khóa (`gated: False`, `private: False`) khi kiểm tra ngày 2026-11-20 |
| License ghi trên thẻ model | `openrail++` |

**Điều khoản license liên quan đến đồ án:** Thẻ model chỉ ghi nhãn `openrail++` và repo không có file license riêng; nhãn này tương ứng với CreativeML Open RAIL++-M License (26/07/2023) của model nền, toàn văn tại https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md (chưa thấy điều khoản bổ sung của tác giả bản tinh chỉnh). Giấy phép cho phép dùng và phân phối model miễn phí, không đòi quyền với ảnh sinh ra (người dùng chịu trách nhiệm về ảnh), nhưng cấm một số mục đích (Attachment A: vi phạm pháp luật, gây hại cho trẻ vị thành niên, tạo thông tin sai lệch hoặc phỉ báng, phân biệt đối xử, tư vấn y tế, ...). Nếu phân phối lại model hoặc cung cấp qua dịch vụ trực tuyến cho người khác thì phải đưa các hạn chế này vào điều khoản sử dụng và kèm bản sao giấy phép; đồ án chỉ tải model lúc chạy, không đưa trọng số vào Git và chỉ dùng cho mục đích học tập. Đây là tóm tắt của nhóm, không phải tư vấn pháp lý.

**File được tải (fp16, tổng 6,46 GiB):** `unet` 4.897 MiB, `text_encoder_2` 1.325 MiB, `text_encoder` 235 MiB, `vae` 160 MiB, cùng các file cấu hình, `tokenizer`, `tokenizer_2` và `scheduler`.

**File cố ý không tải:** ba checkpoint đơn file ở thư mục gốc repo (`DreamShaperXL_Turbo_v2.safetensors`, `..._V2-SFW.safetensors`, `..._v2_1.safetensors`, mỗi file khoảng 6.618 MiB). Danh sách tải nằm trong `ALLOW_PATTERNS`; có test bảo đảm các pattern này không khớp ba file trên.

## 3. Môi trường đã kiểm chứng

| Thành phần | Phiên bản |
|---|---|
| Nền tảng | Kaggle Notebook, Python 3.13.16 |
| GPU | Tesla T4, 14,56 GiB, compute capability 7.5 (notebook thấy T4 x2, chỉ dùng một GPU) |
| PyTorch | 2.11.0+cu130 (CUDA 13.0) |
| diffusers | 0.42.0 |
| transformers | 5.20.2 |
| accelerate | 1.15.0 |
| huggingface_hub | 1.33.0 |
| safetensors | 0.8.0 |
| Pillow | 13.0.0 |
| numpy | 2.1.3 |
| pydantic / PyYAML | 2.14.1 / 6.0.3 |

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

| Chỉ số | Giá trị | Nguồn |
|---|---|---|
| Tải model fp16 | khoảng 36 giây (lần đo trong smoke test) | Bước 3.2 |
| Nạp model qua `SDXLImageGenerator` (gồm tải) | 79,0 giây (phiên tương tác), 39,85 giây (Version 1) | Phụ thuộc đường truyền từng phiên |
| Sinh một ảnh 1024×1024 | 8,77 đến 9,41 giây (Version 1) | `metadata.json` |
| Ảnh đầu tiên sau khi nạp | 13,8 đến 17,8 giây (gồm khởi động) | Smoke test và phiên tương tác |
| Pipeline đủ 4 cảnh (story mock, SDXL, render) | 37,18 giây (Version 1) | `metadata.json` |
| VRAM sau khi nạp model | 6,57 GiB | Smoke test |
| VRAM đỉnh | 9,73 GiB trên 14,56 GiB | Smoke test và Version 1 |
| Độ dài prompt | 46 đến 48 token (prompt), 38 token (negative của E0); giới hạn 77 của CLIP | Đo ở bước 3.2 và 3.2d |

**Tính lặp lại:** cùng seed cho ảnh giống hệt từng pixel trong một phiên. Giữa hai phiên Kaggle độc lập (một phiên tương tác, một phiên Save & Run All), 9 file ảnh (`comic.png`, `panel_1..4.png`, `raw/scene_1..4.png`) có SHA-256 trùng hoàn toàn. Điều này chỉ được kiểm chứng trong môi trường ở mục 3; không bảo đảm trên GPU hoặc phiên bản thư viện khác.

SHA-256 của ảnh gốc `raw/` (dùng để so khớp khi chạy lại):

| File | SHA-256 |
|---|---|
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

| Mục | Giá trị |
|---|---|
| Notebook | `comic-gen-03-image-inference` (Private), Version 1, `scriptVersionId` 372563258 |
| Cách chạy | Save & Run All, 2 phút 40 giây, GPU T4 x2 (dùng một GPU) |
| Mã nguồn | `af9ada647266478ee331a4dc799e1354a9df3b15` |
| Model, revision | `Lykon/dreamshaper-xl-v2-turbo`, `f70ad5bce436c640d23fc02cd0a6ccc787280b6e` |
| Gói tải về (`results.zip`) | SHA-256 `4FB58606427D56DFF70F97919A14B6EE0793EAD9B09E5601A66537EEE1E7A42F` |
| `task03_run.zip` bên trong | SHA-256 `2898213BD65E09F91C985E22495BB1AE7B260C64F28E77A71ACCDA222DBB72DB` so với dòng "ZIP:" trong đầu ra của Cell chạy pipeline là khớp `2898213bd65e09f91c985e22495bb1ae7b260c64f28e77a71accda222dbb72db` |
| Kiểm tra `SHA256SUMS` trên bản giải nén | 10/10 file khớp |
| `metadata.json` | SHA-256 `9d117c4d76df9b6e606b081499bc8d0b1db7b0cf2e0fb1dabad3a8114474d4ff` |
| Ngày tải | `22/11/2026` |

Dữ liệu thô nằm ngoài repo; chỉ các số liệu tổng hợp ở trên được đưa vào tài liệu.

## 10. Việc chưa làm

- **Task 6:** so sánh A (prompt độc lập) và B (shared character descriptions) với nhiều seed hơn, cùng seed và cùng thông số suy luận cho hai phương án, chấm ẩn nhãn. Chưa khẳng định B tốt hơn A.
- Đo mức khớp giữa ảnh và caption, độ đọc được của caption trên ảnh thật.
- Đề xuất với nhóm trưởng: đưa cấu hình E0 vào mặc định của `PromptBuilder` nếu nhóm đồng ý.
