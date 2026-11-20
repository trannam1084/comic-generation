# Story Generator và Mock Backend — Task 06

## 1. Phạm vi và interface

`StoryGenerator` điều phối một lần gọi backend rồi validate output bằng [Shared Storyboard Contract v1.0](data_contract.md). Mock chỉ trả fixture đã chuẩn bị; không phải AI story generation, không chứng minh chất lượng truyện và không tạo benchmark.

Các module:

- `src/story_generator/backend.py`: `StoryBackend`, một `typing.Protocol` có `generate(summary: str) -> str`. Output là raw storyboard JSON string. Interface chỉ phụ thuộc standard library.
- `src/story_generator/mock_backend.py`: `MockStoryBackend`, đọc một fixture có sẵn.
- `src/story_generator/story_generator.py`: `StoryGenerator` và ba exception types tối giản.

Protocol dùng structural typing: backend có method phù hợp có thể được inject mà không kế thừa một class chung. Protocol không được dùng làm runtime validator; người triển khai backend chịu trách nhiệm tuân theo interface, và Generator kiểm tra kiểu raw output.

```python
generator = StoryGenerator(backend)
storyboard = generator.generate(summary)
```

Dependency Injection nghĩa là caller chọn backend và truyền vào constructor. Generator không tự chọn backend theo môi trường, không tự load model, không chuyển backend lỗi sang mock. Import các module này không đọc fixture, tải model hoặc gọi API. Đọc fixture chỉ xảy ra khi caller khởi tạo MockStoryBackend rõ ràng.

## 2. Mock Backend và fixture matching

Fixture mặc định là [examples/storyboard.json](../examples/storyboard.json), được tìm từ đường dẫn module, không dựa vào working directory. Caller có thể truyền `MockStoryBackend(fixture_path=...)`; nên dùng đường dẫn tuyệt đối cho test hoặc ứng dụng chạy từ nhiều thư mục. Đường dẫn custom tương đối được hiểu theo working directory do caller lựa chọn.

Constructor đọc UTF-8 và validate fixture bằng `Storyboard.model_validate_json`. Lỗi file/encoding/JSON/schema được giữ nguyên để phát hiện lỗi cấu hình sớm. Backend giữ raw text và summary của fixture trong instance như một snapshot: thay đổi file sau khi khởi tạo không thay kết quả của instance đó; tạo instance mới để đọc fixture mới.

`generate(summary)` chỉ trả nguyên raw text khi input bằng chính xác summary trong fixture, gồm cả case, dấu câu và whitespace. Summary khác bị từ chối bằng ValueError với thông báo chưa có fixture. Không lấy scenes của truyện có sẵn rồi ghi đè summary để giả lập truyện mới. Không đọc lại file, gọi LLM hoặc tạo output khác trong generate.

Với cùng instance/fixture và input được hỗ trợ, raw output deterministic. Mỗi lần Generator parse raw JSON lại thành một Storyboard mới; mutation kết quả ở caller không làm thay đổi fixture hoặc kết quả lần generate tiếp theo.

## 3. Input/output và luồng xử lý

Input là string có ít nhất một ký tự không phải whitespace. Generator dùng strip chỉ để kiểm tra rỗng, không dùng kết quả strip để thay input. Output là shared `Storyboard`, không phải final image prompts hoặc ảnh.

1. Kiểm tra input; nếu sai thì chưa gọi backend.
2. Gọi `backend.generate(summary)` đúng một lần.
3. Kiểm tra raw output là str; không ép bytes/dict/None thành JSON string.
4. Parse và structural validation bằng `Storyboard.model_validate_json(raw_output)`.
5. So sánh chính xác `storyboard.summary == summary`.
6. Trả Storyboard nếu tất cả bước thành công.

Không retry, repair, fallback hoặc ghi đè summary ở bất kỳ bước nào. Caption và base image prompts giữ nguyên. Kiểm tra summary bằng input chỉ là consistency guard cho trường summary; không chứng minh scenes bám nội dung hay kết thúc đúng.

## 4. Error handling

| Giai đoạn | Exception công khai | Nguyên nhân/debug |
|---|---|---|
| Input sai kiểu/rỗng/whitespace | `StoryInputError(ValueError)` | Backend chưa được gọi |
| Backend.generate phát sinh Exception | `StoryBackendError(RuntimeError)` | Giữ exception gốc tại `__cause__` qua `raise ... from exc` |
| Raw output không phải str | `StoryOutputError(ValueError)` | Message có kiểu output nhận được; không tự ép kiểu |
| JSON/schema không hợp lệ | `StoryOutputError(ValueError)` | `__cause__` là Pydantic ValidationError, giữ `errors()` với loc/type |
| Output summary khác input | `StoryOutputError(ValueError)` | Không sửa summary hoặc trả storyboard sai |
| Khởi tạo mock thất bại | Native file/encoding error hoặc ValidationError | Xảy ra trước khi inject backend, không bị Generator che giấu |

Ba exception types giúp caller phân biệt input, backend và output mà không cần phân tích message. Không tạo thêm framework exception hoặc fallback. `StoryOutputError.raw_output` giữ output nhận được, kể cả output sai kiểu, để caller debug hoặc bước Repair tương lai sử dụng mà không phải gọi backend lại. Module không tự log raw output.

```python
from pydantic import ValidationError
from src.story_generator.story_generator import (
    StoryInputError, StoryBackendError, StoryOutputError,
)

try:
    storyboard = generator.generate(summary)
except StoryInputError as exc:
    print("Input không hợp lệ:", str(exc))
except StoryBackendError as exc:
    print("Backend thất bại:", type(exc.__cause__).__name__)
except StoryOutputError as exc:
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        for error in cause.errors():
            print(error["loc"], error["type"])
    else:
        print("Output không hợp lệ:", str(exc))
```

## 5. Chạy thử trên CPU

Chạy từ root repository bằng `.venv` hiện có, chỉ cần Pydantic v2; pytest dùng cho tests. Không cần API key, GPU packages hoặc network.

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.story_generator import StoryGenerator

summary = json.loads(
    Path("examples/storyboard.json").read_text(encoding="utf-8")
)["summary"]
storyboard = StoryGenerator(MockStoryBackend()).generate(summary)
print(storyboard.model_dump_json(indent=2))
PY
```

Input khác fixture không được hỗ trợ. Caller muốn thử câu chuyện khác phải cung cấp fixture hợp lệ tương ứng, không coi mock là backend có khả năng sinh truyện mới.

Kiểm thử:

```bash
.venv/bin/python -m pytest tests/test_story_generator.py -v
.venv/bin/python -m pytest -v
.venv/bin/python -m pip check
git diff --check
```

Tests dùng mock và fake nhỏ, kiểm tra call count trên success/failure để chứng minh không tự retry/fallback. Một test chạy process mới, chặn import GPU/provider packages và chặn network operations bằng audit hook. Không cấm import socket của standard library vì Pydantic có thể import gián tiếp module này qua metadata; import module không đồng nghĩa gọi network.

## 6. Mở rộng sau này và giới hạn

Qwen backend tương lai chỉ cần cung cấp `generate(summary: str) -> str` rồi được inject qua constructor. Model loading phải là thao tác rõ ràng, tách khỏi import/interface chung; chưa triển khai backend Qwen, structured prompting hoặc inference trong task này.

Repair tương lai nên là bước điều phối riêng, sử dụng output lỗi và ValidationError được giữ lại, áp dụng retry budget đã thống nhất. Interface backend và Generator hiện không tự retry; chưa triển khai repair prompt, retry policy hoặc fallback. Không biến việc nhận exception thành benchmark thành công giả.

Chưa có Semantic Validation, Input length policy, timeout/cancellation, async/batch API, Image Generation, Renderer, Gradio hoặc pipeline hoàn chỉnh. Caller vẫn cần tôn trọng quy tắc mutation/revalidation của shared schema. Code của Hoàng Anh/Công Thành và tests schema cũ không bị sửa trong Task 06.
