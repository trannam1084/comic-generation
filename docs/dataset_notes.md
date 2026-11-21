# Dataset Notes — Comic Generation

## 1. Mục tiêu và phạm vi

Dataset đầu vào phục vụ pipeline tạo comic gồm summary, character annotations, key events và trường truy vết nguồn. Snapshot hiện có 30 record, 20 Dev và 10 Test. Đây là bộ dữ liệu thử nghiệm quy mô nhỏ; giữ riêng Test cho held-out evaluation, không dùng Test để tuning pipeline.

## 2. Cấu trúc repository

- data/dev_cases.jsonl
- data/test_cases.jsonl
- data/metadata/dataset_selection.csv
- data/metadata/ai_evaluated_stories.csv
- scripts/dataset_validation.py
- scripts/validate_dataset.py
- scripts/test.py
- tests/test_dataset.py

Full-text candidate corpus và generated AI batch artifacts không thuộc phạm vi public PR này.

## 3. Dataset record schema

Mỗi JSONL record có id, title, summary, characters, key_events, source, source_url, difficulty, selection_score và optional normalization_note. Schema này dành riêng cho dataset preparation, không thay thế Shared Storyboard Schema.

## 4. Split và difficulty

| Split | Easy | Medium | Hard | Total |
|---|---:|---:|---:|---:|
| Dev | 12 | 3 | 5 | 20 |
| Test | 6 | 4 | 0 | 10 |
| Total | 18 | 7 | 5 | 30 |

Năm truyện Hard được bổ sung vào Dev: story_012, story_016, story_066, story_072, story_077. Held-out Test hiện có 0 Hard cases.

## 5. Selection metadata và giới hạn human review

dataset_selection.csv ghi trạng thái lựa chọn/review của 306 ứng viên; ai_evaluated_stories.csv là AI-assisted scoring, không phải nhãn human gold. Các trạng thái Reviewed/Reviewed - approved for Dev phản ánh bước selection review trong metadata. Chúng không tự chứng minh rằng từng summary, character annotation và key event đã qua semantic adjudication. normalization_note trong JSONL vẫn ghi AI-assisted normalization và yêu cầu người review đối chiếu nguồn.

Không mô tả 30 record là semantic-certified hoặc human gold chỉ dựa trên selection metadata. Human semantic review cần lưu reviewer, ngày, rubric version, verdict, issue/evidence và adjudication riêng.

## 6. Nguồn, attribution và quyền sử dụng

source và source_url được giữ để truy vết. URL truy cập và attribution không tự cấp quyền tái sử dụng hoặc phân phối.

Audit ngày 2026-11-21 chưa tìm thấy giấy phép theo từng nguồn, văn bản cho phép, email chấp thuận hoặc hồ sơ rights-holder xác nhận phạm vi sử dụng nội bộ/công khai trong package đã kiểm tra. Trang nguồn story_016 hiển thị byline “Hồ Lãng kể”; raw corpus để trống và selection metadata ghi Unknown. Đây là byline trên host page, không phải xác minh độc lập về ấn bản gốc hoặc chủ thể quyền.

Footer TruyenDanGian.com trên trang đã kiểm tra thông báo đăng ký DMCA và yêu cầu ghi nguồn khi sao chép. Thông báo ghi nguồn không phải giấy phép phân phối lại. Vì vậy, quyền sử dụng cho cả phạm vi nội bộ và công khai hiện chưa được chứng minh bằng hồ sơ trong package. Giữ dữ liệu ở không gian riêng tư/hạn chế; không công khai full text, trích đoạn đáng kể hoặc dataset dẫn xuất như một corpus được phép tái sử dụng cho đến khi dự án/trường và chủ thể quyền làm rõ bằng văn bản.

Rights/attribution register của 30 nguồn được bàn giao riêng, không commit vào public PR.

## 7. Semantic fidelity và key events

Audit docs/dataset_semantic_fidelity_audit_30.md ghi việc đối chiếu 11 key-event flags với summary thực tế đưa vào Story Generator: 6 event text được sửa, 4 event bị loại, 1 lexical false-positive được giữ. Việc này chỉ giải quyết 11 mục bị đánh dấu; 109 event còn lại chưa được chứng nhận bằng review ngữ nghĩa thủ công toàn bộ. Structural validator không tự chứng minh semantic fidelity.

## 8. Offline Evaluation Harness gates

Theo src/offline_evaluation/contracts.py trên main, official evaluation cần split_frozen, review_approved, rights_approved và dataset_reference có SHA-256; official Test còn cần official_test_authorized=true. Source URL, selection status hoặc validator PASS không tự mở các gate này. Human annotation phải đạt full-case gold_ready theo src/offline_evaluation/semantic.py; case có finding uncertain không được partial-match.

## 9. Validation và dependencies

Core validator dùng Python standard library; tests cần pytest. Chạy từ repository root:

python scripts/validate_dataset.py
python -m pytest tests/test_dataset.py -v
python -m pytest -v

pandas cần cho các script corpus/metadata tiện ích; openai/API key chỉ cần khi chủ động chạy AI evaluation utilities. Không đưa API keys vào source control. Các script tiện ích không được gọi API hoặc ghi file khi import.

## 10. Giới hạn hiện tại

- Dataset 30 truyện nhỏ, không đại diện cho mọi thể loại/độ khó.
- Test có 0 Hard cases.
- Semantic fidelity review của toàn bộ 30 truyện chưa được xác nhận hoàn tất.
- Rights/permission cho internal và public use chưa có chứng cứ hồ sơ trong package đã kiểm tra.
- Nghiệm thu dataset/PR và nghiệm thu human gold là hai quyết định riêng.
