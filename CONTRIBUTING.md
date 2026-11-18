# Contribution Guidelines

## Branch Workflow

- `main`: Phiên bản ổn định.
- `feature/story-generation`: Story Generation và Validator.
- `feature/image-pipeline`: Image Generation, Renderer và UI.
- `feature/evaluation`: Dataset, Evaluation và Testing.

Không push trực tiếp vào `main`.

Mỗi thay đổi cần được đưa vào feature branch, kiểm thử và tạo Pull Request để review.

## Commit Convention

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

## Coding Guidelines

- Sử dụng Python và tên biến tiếng Anh.
- Viết code theo module, tránh một file quá lớn.
- Mỗi function chính có docstring.
- Kiểm tra input và output.
- Không che giấu lỗi bằng dữ liệu giả.
- Không hardcode API keys.
- Không tự ý thay đổi data contract.
- Ghi rõ model, phiên bản, inference parameters và môi trường thử nghiệm.

## Pull Request Requirements

Mỗi Pull Request phải mô tả:

1. Chức năng đã thêm hoặc sửa.
2. Các file đã thay đổi.
3. Cách chạy và kiểm thử.
4. Kết quả thực tế.
5. Lỗi hoặc giới hạn còn tồn tại.

Yêu cầu nhóm trưởng hoặc một thành viên khác review trước khi merge.

## GPU Usage

- Chạy validation, mock, Pillow và unit tests trên CPU khi có thể.
- Chỉ bật Kaggle GPU khi cần inference.
- Lưu kết quả, log và thông số thử nghiệm.
- Tắt GPU session khi không sử dụng.

## Security

Không commit API keys, access tokens, model checkpoints lớn hoặc dữ liệu không có quyền phân phối.
