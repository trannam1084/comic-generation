# Data Contract sơ bộ — cần review cùng TV2

## 1. Phạm vi

Tài liệu mô tả cấu trúc đã có trong `AGENTS.md` và [examples/storyboard.json](../examples/storyboard.json), đồng thời ghi các điểm cần thống nhất. Không thay đổi schema implementation, PromptBuilder hoặc fixture của TV2 trong Task 03. Chưa công bố một interface mới đã được tất cả thành viên phê duyệt.

## 2. Cấu trúc JSON dự kiến

| Đối tượng | Trường | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|---|
| Storyboard | `summary` | `str` | Tóm tắt gốc bằng tiếng Việt |
| Storyboard | `characters` | `list[Character]` | Các nhân vật và shared visual descriptions |
| Storyboard | `scenes` | `list[Scene]` | Đúng bốn cảnh |
| Character | `id` | `str` | Định danh nhân vật |
| Character | `visual` | `str` | Mô tả ngoại hình dùng lại trong image prompts |
| Scene | `index` | `int` | Chỉ số cảnh; example hiện dùng 1, 2, 3, 4 |
| Scene | `caption_vi` | `str` | Caption tiếng Việt |
| Scene | `image_prompt_en` | `str` | Base prompt tiếng Anh, chưa ghép style và shared descriptions |
| Scene | `characters` | `list[str]` | Các character IDs xuất hiện trong cảnh |

Trong JSON, các `list[...]` biểu diễn bằng arrays. Ngôn ngữ của `visual` cần thống nhất; example hiện dùng tiếng Anh để ghép vào prompt. TV2 bổ sung shared character descriptions và art style thành final image prompt; không ghi đè base prompt/caption để che mất input gốc.

Example hiện parse được, có đúng bốn scenes theo thứ tự 1–4, ID nhân vật không trùng và không có reference không tồn tại. Đây là kiểm tra fixture mẫu, chưa phải chứng minh Validator đã có implementation.

## 3. Compatibility với commit 899f99f

| Nội dung | Code TV2 hiện có | Điểm cần thống nhất |
|---|---|---|
| Vị trí schema | `src/image_generator/schemas.py` định nghĩa Character/Scene/Storyboard | TV1 phụ trách `src/storyboard/schema.py`, hiện còn trống. Cần một nguồn định nghĩa chung; chưa di chuyển hoặc tạo schema cạnh tranh |
| Collection types | Frozen dataclasses dùng tuple; `from_dict` chuyển arrays thành tuples | JSON arrays tương thích khi parse example, nhưng object Python/list và serialization chưa có interface chung |
| Parsing | `from_dict` truy cập key, chỉ chuyển `KeyError` thành `ValueError` | Type hints không kiểm tra runtime types; input sai kiểu có thể lỗi khác, extra fields đang bị bỏ qua |
| Validation | Builder kiểm tra đúng bốn scenes và reference nhân vật tồn tại | Chưa kiểm tra index duy nhất/đúng thứ tự, ID trùng hoặc chuỗi rỗng; ID trùng có thể bị ghi đè trong lookup dict |
| Thứ tự cảnh | Builder giữ thứ tự collection đầu vào | Không tự sort theo index; cần chốt reject hay normalize input sai thứ tự |
| Final prompt | `ScenePrompt` có scene_index/prompt/negative_prompt/character_ids | Kiểu output nội bộ của image, chưa phải trường mới trong Storyboard JSON |
| Caption | Builder không sửa caption và không đưa caption vào ScenePrompt | Renderer cần nhận caption từ nguồn đã chốt, không chỉ từ ScenePrompt |
| Fixture | `data/storyboard_sample.json` tương đương example hiện tại | Hai bản có thể lệch về sau; cần chọn nguồn fixture chuẩn hoặc check đồng bộ |
| Cấu hình | Style/negative prompt nằm trong defaults của Builder; có `use_shared_characters` | Chưa có shared loader. Không tự đưa setting mới vào interface của TV2 |

Sáu test functions hiện có bao phủ: bốn prompts theo fixture, chèn shared descriptions, tắt shared descriptions, giữ nội dung base prompt, unknown character và scene count sai. Task nền tảng chỉ đọc tests, chưa chạy pytest. Chưa có assertions chuyên biệt cho caption bất biến, input đảo thứ tự/index trùng, ID trùng hoặc type errors.

`scripts/show_prompts.py` đọc đường dẫn tương đối theo working directory và import `src`; cần thống nhất cách chạy/module path khi tích hợp. Chưa sửa script hoặc packaging trong Task 03.

## 4. Các quyết định cần TV1/TV2/TV3 review

1. Nguồn schema chung, cách adapter/import và phương thức serialize về JSON; giữ compatibility với code đang phát triển.
2. Quy tắc index 1–4, thứ tự, uniqueness, character references và cách xử lý dữ liệu sai.
3. Chuỗi rỗng/whitespace, độ dài, ngôn ngữ `visual`, extra fields và character list rỗng có được chấp nhận không.
4. Ranh giới schema validation và semantic validation: lỗi cấu trúc, nội dung lặp, bám summary, kết thúc truyện; không coi một parser là semantic validator.
5. Exception/result format, retry budget và log Repair; không fallback sang nội dung giả khi backend lỗi.
6. Fixture chuẩn, caption truyền tới renderer, metadata ảnh/seed/style và ablation flag; không tự mở rộng Storyboard JSON.

Nhóm trưởng và TV2 phải thống nhất interface trước thay đổi code; TV3 phối hợp xác định contract tests và dữ liệu lỗi. Task này chỉ ghi nhận các quyết định còn mở.
