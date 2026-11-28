# Checklist TV1 trước phát hành — 28/11/2026

Tài liệu này là checklist **chưa nghiệm thu**, không phải chứng nhận PASS.

## 1. Adjudication 12 B1 — P0
- [ ] Lưu nguyên bản 3 phiếu và bản 13 sửa kỹ thuật riêng, rà các thay đổi trích dẫn.
- [x] Panel thống nhất phương án B: giữ case_009_D02 và case_012_D03 (warning), loại case_010_D02/D03 khỏi tám mã semantic; ghi chú thiếu scene references riêng.
- [x] Panel đã thống nhất 19 findings: 11 error, 8 warning theo phương án B.
- [ ] Xác nhận danh sách người tham dự/ngày duyệt thực tế; không gán nhận xét của AI thành chữ ký panel.
- [ ] Nếu điều chỉnh, cập nhật adjudication.csv private, chạy lại tools/annotate.py validate + summarize, lưu log và bảng 8 mã.
- [x] Công bố đúng 19 findings/10 case trên 12 development B1, không coi là Test benchmark hay paired B0/B1 semantic evaluation.

## 2. Code, UI và khả năng tái hiện — P0
- [ ] Checkout commit cuối, chạy `python -m pytest -q` và lưu log, Python version, exit code.
- [ ] Chạy `python app.py --demo`: 4 scene, 4 ảnh mock, caption tiếng Việt, PNG 2×2, download và đường lỗi.
- [ ] Nếu yêu cầu live Qwen → SDXL, cần PR tích hợp riêng + chạy GPU thực nghiệm. `PipelineConfig(image_backend='sdxl')` hiện không hợp lệ.
- [ ] Nếu không kịp live full real, trình diễn mock có nhãn và trình chiếu 5 comic SDXL đã tạo thực cùng metadata; không đánh đồng hai chế độ.

## 3. Báo cáo cuối — P0
- [ ] B0/B1 10/12 → 12/12: chỉ diễn giải JSON/schema/exact-summary, không gọi là semantic accuracy.
- [x] Đã có bảng 8 mã và 19 findings phương án B; tiếp tục phân biệt số case và số finding.
- [ ] Task 6: 5 story × 2 seed × 2 arm = 20 comics; B-A +0.40 core, +0.20 extra; B thắng 4, A thắng 1, hòa 5. Không tuyên bố B tốt hơn A đã được chứng minh.
- [ ] 5 truyện SDXL thật: chọn 2–3 hình có metadata/seed và chú thích lỗi; tách khỏi 20 comic Task 6.
- [ ] Gắn screenshot Gradio thực tế và ghi mock hoặc real chính xác.
- [ ] Kiểm tra license model, quyền sử dụng dữ liệu, provenance, bảng/hình, DOCX/PDF.

## 4. Chốt bàn giao — P1
- [ ] Giữ annotation/gold/test private ngoài GitHub public; đưa vào gói trao giảng viên qua kênh chấp thuận.
- [ ] Kiểm tra secrets và file thừa trong Git diff.
- [ ] Ghi commit SHA, ngày nghiệm thu, hash ZIP minh chứng vào báo cáo.
- [ ] Chỉ sau khi kiểm thử và nhóm phê duyệt mới merge, tạo release tag.

## Phân công
- TV1: adjudication, README/architecture, báo cáo, tích hợp release.
- TV2: Gradio demo, 5 SDXL comics, Task 6 evidence và ảnh minh họa.
- TV3: rubric/taxonomy, validator, bảng 8 mã, kiểm thử độc lập.
