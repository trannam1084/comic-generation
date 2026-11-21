# Audit bộ dữ liệu 30 truyện Dev/Test — kiểm tra nguồn, key_events và trạng thái review

**Ngày kiểm tra:** 21/11/2026  
**Nguồn local được kiểm tra:** `full_story (2).csv`, `dataset_selection_reviewed.csv`, `dev_cases(2).jsonl`, `test_cases(2).jsonl`  
**Repo:** `trannam1084/comic-generation`, branch `feature/evaluation`, PR #20  
**Phạm vi:** audit provenance, split, trạng thái review, đối chiếu key_events với summary và raw source. Đây là audit thủ công/hỗ trợ kiểm tra; không phải xác nhận giấy phép bản quyền hay chứng nhận semantic gold.

## 1. Snapshot dữ liệu chính xác

Dùng hai snapshot cập nhật cuối:

- `dev_cases(2).jsonl`: 20 record; SHA-256 `cf499691c012bb7b93d391a9e7ccc8ecf1c54d6402a0207517b7a2b92563a2f3`.
- `test_cases(2).jsonl`: 10 record; SHA-256 `370e3e7d742e6acf5e6d07c5929eeae21c68d50e64ed6fb9221bb05eb586e737`.

Không dùng `dev_cases(1).jsonl` hoặc `dataset_prepared/dev_cases.jsonl` cũ: các file đó vẫn chứa split Dev trước khi bổ sung năm truyện Hard.

| Split | Easy | Medium | Hard | Tổng |
|---|---:|---:|---:|---:|
| Dev | 12 | 3 | 5 | 20 |
| Test | 6 | 4 | 0 | 10 |
| Tổng | 18 | 7 | 5 | 30 |

Dev IDs: `story_010`, `story_013`, `story_014`, `story_020`, `story_021`, `story_025`, `story_027`, `story_030`, `story_033`, `story_039`, `story_041`, `story_045`, `story_047`, `story_049`, `story_050`, `story_012`, `story_016`, `story_066`, `story_072`, `story_077`.

Test IDs: `story_002`, `story_006`, `story_017`, `story_022`, `story_031`, `story_036`, `story_040`, `story_044`, `story_048`, `story_053`.

## 2. Truy vết raw corpus và metadata selection

Đã đối chiếu 30 record cuối với `full_story (2).csv` (306 dòng) và `dataset_selection_reviewed.csv` (306 dòng):

- 30/30 `source_url` khớp đúng một dòng trong raw corpus.
- 30/30 `source_url` khớp đúng một dòng trong selection metadata.
- 30/30 record có `final_selected=Yes` và split metadata trùng Dev/Test.
- 28/30 title khớp nguyên văn raw corpus; hai title có hậu tố phân loại bị lược bỏ.
- 26/30 trường `source` khớp nguyên văn `author_or_source`; bốn trường có khác biệt định dạng/nội dung cần lưu vết.

### Sai khác provenance cần chú ý

| ID | Khác biệt phát hiện | Nhận định/việc cần làm |
|---|---|---|
| `story_016` | Raw corpus và selection metadata ghi `author_or_source=Unknown`, nhưng JSON record ghi `Hồ Lãng kể`. | Cần xác minh attribution “Hồ Lãng kể” từ nguồn gốc hoặc tài liệu có thẩm quyền; nếu không có bằng chứng, đổi thành attribution chưa xác định. Đây là mục ưu tiên cao. |
| `story_066` | Source trong JSON là tên truyện + “Truyện ngắn Vũ Duy Thông”; raw/selection chứa title website, mô tả và tên Vũ Duy Thông. | Có vẻ khác cách trình bày/chuẩn hóa; giữ raw attribution trong hồ sơ và xác nhận cách ghi chuẩn. |
| `story_072` | Title JSON là `Thờn Bơn đón trăng [Truyện thiếu nhi]`; raw title có thêm `hay cho bé`. Source JSON và raw author/source cũng khác cách trình bày nhưng cùng nêu Vũ Duy Thông. | Ghi lại việc rút gọn title và chuẩn hóa attribution; không coi là sai nếu nhóm có quy tắc đặt title rõ ràng. |
| `story_077` | Title JSON bỏ cụm `hay cho bé`; source JSON nêu truyện Grimm và sách Tập đọc lớp 2/1976, raw metadata có cùng nguồn nhưng cách viết khác. | Ghi lại chuẩn hóa title/source và duy trì dẫn chiếu đến xuất bản phẩm gốc. |

Chi tiết theo từng record và raw text được lưu trong `dataset30_source_side_by_side.md`; bảng truy vết/rights ở `dataset_source_rights_register_30.csv`.

## 3. Trạng thái human review trong metadata

Trong `dataset_selection_reviewed.csv`:

- 306/306 record có trạng thái review khác rỗng.
- 296 `Reviewed`.
- 5 `Reviewed - approved for Dev`.
- 5 `Reviewed - not selected for updated Dev`.
- 30 record được chọn: 25 có trạng thái `Reviewed`, 5 record bổ sung Hard có trạng thái `Reviewed - approved for Dev`.
- Trong 30 record được chọn, split metadata là 20 Dev và 10 Test.

**Giới hạn audit trail:** trường `human_review` là trạng thái tổng quát; CSV hiện không lưu riêng reviewer ID, review date hoặc decision note cho từng record. `normalization_note` trong cả 30 JSONL cuối vẫn ghi nội dung AI-assisted và “cần người review đối chiếu nội dung nguồn trước khi dùng chính thức”. Vì vậy, metadata selection nói đã review nhưng note trên record chưa được đồng bộ. Không tự chuyển thành “semantic verified” chỉ dựa vào status `Reviewed`.

Đề xuất đồng bộ `normalization_note` sau khi TV3 xác nhận semantic review 30 truyện đã hoàn tất. Trước khi đó, dùng wording trung thực: AI-assisted normalization; selection/human review status có ghi nhận; key-event-to-summary alignment còn các mục cần rà soát ở bảng dưới.

## 4. Key-event grounding: cách kiểm tra và giới hạn

Đã tạo `dataset_key_event_alignment_screen.csv` cho 120 key events. Screen đo độ phủ token nội dung riêng biệt của key_event so với summary và raw source. Ngưỡng `<0.35` chỉ dùng để **đánh dấu cần đọc lại**, không phải tiêu chí pass/fail semantic. Phép so khớp từ vựng có thể bỏ sót đồng nghĩa, biến thể từ và suy luận tóm tắt hợp lý.

Có 11/120 events dưới ngưỡng 0.35. Kết quả đọc đối chiếu các trường hợp bị đánh dấu:

| ID / event | Nhận xét grounding | Hành động đề xuất |
|---|---|---|
| `story_010` / 1 | Raw source mô tả đất lồi lõm, cây rậm và nước ngập; summary hiện tại không nêu trạng thái ban đầu này. | Rút key_event về nội dung summary hoặc bổ sung câu vào summary từ raw source. |
| `story_013` / 1 | Raw source có chi tiết Sĩ nghe giảng ngoài cửa; summary chỉ nói ham học dù nghèo. | Rút gọn key_event thành “Sĩ ham học dù nhà nghèo” hoặc bổ sung chi tiết nghe giảng ngoài cửa vào summary. |
| `story_013` / 3 | Chi tiết người hỏi về đèn và Sĩ chỉ trăng/gọi là “ngọn đèn lớn” có trong raw source, nhưng không được nêu trong summary. | Thêm vào summary nếu là key event cần giữ; nếu không, chuyển khỏi key_events. |
| `story_030` / 1 | Summary nói hai sông thi nhau; phần Ping chê Mekong cồng kềnh là chi tiết raw source không có trong summary. | Bỏ phần chê bai, giữ việc hai sông thách/thi nhau theo summary. |
| `story_030` / 2 | Summary nói Ping hợp với các sông khác; tên Wang/Yom/Nan và hành trình cụ thể chỉ có trong raw source. | Dùng “Ping hợp với các sông khác” hoặc mở rộng summary nếu tên sông là chi tiết cần giữ. |
| `story_033` / 2 | Việc thử năm sáu đôi kính là raw-source detail; summary nói anh liên tục chê kính vì cầm lịch ngược. | Rút gọn theo nội dung summary, bỏ số lượng/thử nhiều đôi nếu không có trong summary. |
| `story_033` / 4 | Summary diễn đạt “anh thừa nhận nếu biết chữ thì đã không cần mua kính”; key_event “thú nhận không biết chữ” là tương đương ngữ nghĩa. | Có thể giữ; ghi nhận lexical screen false positive. |
| `story_041` / 1 | Vua đến Hồ Tây và lính ngăn dân tới gần có trong raw source, không có trong summary. | Rút khỏi key_events hoặc bổ sung summary từ nguồn nếu sự kiện mở đầu cần thiết. |
| `story_047` / 1 | Chi tiết hai người kết nghĩa và một người đỗ làm quan có trong raw source; summary chỉ nêu bạn cũ và vị quan từ chối tiếp. | Rút gọn bám summary hoặc bổ sung summary có căn cứ. |
| `story_040` / 1 (Test) | Summary nói Ngựa Con mải chăm chút vẻ ngoài và tự tin; soi bóng/chuẩn bị trang phục chi tiết hơn có trong raw source. | Giữ phần tóm lược appearance/self-confidence; tránh thêm chi tiết raw-only nếu yêu cầu strict grounding theo summary. Test set không dùng để tuning; chỉ cập nhật trước freeze theo governance. |
| `story_053` / 4 (Test) | Summary nói người quen hiểu tính anh và chọn cách nói khiến anh nắm tay; câu key_event “giải thích đã dùng cách nói phù hợp” là diễn giải tương đương nhưng phần hành động giải thích không nêu rõ trong summary. | Có thể rút gọn thành người quen dùng lời phù hợp tính anh, anh nắm tay và được cứu. |

### Kết luận semantic fidelity hiện tại

- 120/120 key events đều được liên kết với một raw source row duy nhất qua source URL; token-overlap screen cho thấy nội dung của đa số events có từ/cụm tương ứng trong raw source.
- Tuy vậy, một số key_events chứa chi tiết có trong raw full text nhưng không có trong field `summary`. Điều này không nhất thiết là hallucination so với truyện nguồn, nhưng chưa đáp ứng cách hiểu nghiêm ngặt “key_events có căn cứ trong input summary”.
- Cần xử lý các dòng được đánh dấu trước khi tuyên bố toàn bộ 120 events đã được xác minh theo summary. Trường hợp `story_033` event 4 là false positive lexical đã nêu; `story_040` và `story_053` có thể là diễn giải tương đương nhưng nên rút gọn để rõ ràng.
- Không dùng 0.35 hoặc bất kỳ ngưỡng token nào làm nhãn semantic tự động.

## 5. Hồ sơ quyền sử dụng nguồn

`docs/dataset_notes.md` trên branch PR #20 ghi rằng TV3 đã xác minh điều kiện sử dụng nguồn cho phạm vi dataset hiện tại; tài liệu cũng nói rõ `source_url` không tự nó là giấy phép và nhóm cần duy trì hồ sơ giấy phép/điều khoản/xác nhận tương ứng.

Trong các file local được kiểm tra ở đợt audit này, chưa tìm thấy một rights register/license terms/permission email/permission snapshot riêng cho từng nguồn. Vì vậy:

- Trạng thái được báo cáo: TV3 đã xác nhận việc review điều kiện sử dụng ở phạm vi hiện tại đã hoàn tất.
- Bằng chứng trong package hiện có: URL, title, author/source, raw full text và metadata selection.
- Bằng chứng chưa tìm thấy tại local: giấy phép/điều khoản lưu trữ, email chấp thuận, hoặc bản ghi quyền dùng/phân phối theo từng nguồn.
- Không kết luận rằng dữ liệu được cấp phép tái phân phối công khai chỉ dựa vào URL hoặc lời ghi trong metadata.

Đề nghị TV3 bổ sung/đính kèm quyền sử dụng evidence cho từng nguồn hoặc một bản xác nhận tập trung liệt kê URL, phạm vi (nội bộ/đồ án/công bố), mục đích, điều kiện attribution và ngày kiểm tra. Đặc biệt xác minh attribution `story_016`.

## 6. Đồng bộ và hành động đề xuất

1. Giữ nguyên raw corpus `full_story (2).csv`; không crawl hoặc tạo lại dữ liệu.
2. Dùng `dev_cases(2).jsonl` và `test_cases(2).jsonl` làm snapshot hiện hành; không nhầm với Dev snapshot cũ.
3. Chốt 11 key_event rows được đánh dấu: sửa summary hoặc key_event để quan hệ summary → key_events rõ ràng; với Test, không dùng để tuning prompt/model, chỉ chỉnh lỗi dữ liệu đã xác minh theo quy trình versioned.
4. Đồng bộ `normalization_note` sau khi semantic review được chốt; không tự đổi metadata status thành “semantic pass”.
5. Bổ sung rights evidence/attribution register và lưu cùng phiên bản dataset.
6. Sau mọi thay đổi, tạo dataset version mới, cập nhật SHA-256, chạy lại `scripts/validate_dataset.py` và tests; giữ bản gốc để truy vết.
