# Hướng dẫn đóng góp

## Quy trình branch

- `main`: Phiên bản ổn định.
- `feature/story-generation`: Story Generation và Validator.
- `feature/image-pipeline`: Image Generation, Renderer và UI.
- `feature/evaluation`: Dataset, Evaluation và Testing.

Không push trực tiếp vào `main`.

Mỗi thay đổi cần được đưa vào feature branch, kiểm thử và tạo Pull Request để review.

## Quy ước commit

Sử dụng các tiền tố:

- `feat:` Thêm chức năng.
- `fix:` Sửa lỗi.
- `docs:` Cập nhật tài liệu.
- `test:` Thêm hoặc sửa test.
- `refactor:` Tổ chức lại code.
- `chore:` Cập nhật cấu hình hoặc môi trường.

Ví dụ:

`feat: implement mock image generator`

`test: validate four-scene storyboard`

`docs: define storyboard data contract`

## Quy tắc viết code

- Sử dụng Python và tên biến tiếng Anh.
- Viết code theo module, tránh một file quá lớn.
- Mỗi function chính có docstring.
- Kiểm tra input và output.
- Không che giấu lỗi bằng dữ liệu giả.
- Không hardcode API keys.
- Không tự ý thay đổi data contract.
- Ghi rõ model, phiên bản, inference parameters và môi trường thử nghiệm.

## Yêu cầu Pull Request

Mỗi Pull Request phải mô tả:

1. Chức năng đã thêm hoặc sửa.
2. Các file đã thay đổi.
3. Cách chạy và kiểm thử.
4. Kết quả thực tế.
5. Lỗi hoặc giới hạn còn tồn tại.

Yêu cầu nhóm trưởng hoặc một thành viên khác review trước khi merge.

## Sử dụng GPU

- Chạy validation, mock, Pillow và unit tests trên CPU khi có thể.
- Chỉ bật Kaggle GPU khi cần inference.
- Lưu kết quả, log và thông số thử nghiệm.
- Tắt GPU session khi không sử dụng.

## Bảo mật và quyền sử dụng

Không commit API keys, access tokens, model checkpoints lớn hoặc dữ liệu không có quyền phân phối.

Không đưa `models/` cũ vào pipeline hoặc force-add các file ignored. Hai script legacy chỉ được giữ trong backup ngoài repository và các bản local hiện có; chưa đưa lên GitHub/`references/legacy/` khi quyền sử dụng chưa rõ. Không tự ý xóa bản local, khôi phục placeholder hoặc CSV cũ.

## Ownership và phối hợp ba thành viên

| Thành viên | Files chính |
|---|---|
| TV1 | `src/story_generator/`, `src/storyboard/`, `src/pipeline.py`, notebook 02 |
| TV2 | `src/image_generator/`, `src/comic_renderer/`, `app.py`, notebook 03 |
| TV3 | `data/`, `src/evaluation/`, notebook 04, test strategy và integration/evaluation tests |

Chủ module phối hợp TV3 viết unit tests theo chức năng trong các file riêng; tránh cùng sửa một file test lớn. TV3 phụ trách dữ liệu kiểm thử và tiêu chí đánh giá; không tự đổi interface để làm tests pass.

TV1 điều phối shared files: `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `docs/data_contract.md`, `configs/settings.yaml`, `.env.example`, `.gitignore`, `requirements.txt`. Khi thay đổi interface image/schema, cần TV2 review; khi thay đổi dataset/metrics/test contract, cần TV3 review. Thông báo phạm vi file trước khi làm, chia PR nhỏ, không sửa đè module của thành viên khác.

`src/image_generator/schemas.py` tại `899f99f` đang định nghĩa Storyboard của TV2. Chưa di chuyển/xóa schema này hoặc tạo schema song song với interface khác trước khi thống nhất [Data Contract sơ bộ](docs/data_contract.md). Commit này không sửa các shared files tài liệu/cấu hình nêu trên theo refs đã kiểm tra.

## Nền tảng và kiểm tra trước khi tích hợp

- Đọc `AGENTS.md`, kiểm tra working tree và backup trước khi đổi nền branch.
- Theo snapshot local ngày 18/11/2026, branch story-generation chậm hơn nền `809350b` 23 commit; nhánh image đi trước nền một commit; nhánh evaluation ở cùng nền. Đây không phải xác nhận trạng thái server hiện tại.
- Sau khi PR nền tảng được review/merge theo yêu cầu riêng, các thành viên đồng bộ branch với nền đã thống nhất khi working tree đã được bảo toàn. Không tự động stash, reset, clean, đổi branch hoặc chỉnh lịch sử.
- Development dự kiến dùng `mock`/`mock`/`cpu`; mock và loader chưa có implementation. Không yêu cầu GPU dependencies để làm tài liệu, schema hoặc CPU tests.
- Không tự động load model khi import. Backend thật chỉ được khởi tạo rõ ràng trong phiên Kaggle có cấu hình riêng.
- Kiểm tra diff, JSON/YAML, links nội bộ, secrets và tests phù hợp. Phân biệt syntax check, tests đã chạy và kết quả inference được nhóm cung cấp.
- PR nền tảng chỉ đưa các file tài liệu/cấu hình được duyệt vào staging; notebook 02 có thay đổi local từ trước cần PR riêng. Không stage toàn bộ working tree.
