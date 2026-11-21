# Semantic Storyboard Validator — Rubric gán nhãn thủ công

**Phiên bản:** TV3 Semantic Storyboard Rubric v1.0 (bản dự thảo, chờ trưởng nhóm phê duyệt)  
**Nền tảng hợp đồng (contract baseline):** `main` — `src/storyboard/semantic_schema.py`, `src/storyboard/semantic_validator.py`, `src/storyboard/schema.py`, `docs/semantic_validation.md`  
**Phạm vi:** Gán nhãn thủ công cho các đầu ra development và các case control/exploratory được cung cấp trong file ZIP bàn giao.  
**Không phải prompt chạy mô hình.** Nhãn do con người tạo phải được lưu tách biệt với prompt và dự đoán của Qwen reviewer.

## 1. Mục đích và thứ tự ưu tiên của nguồn dữ liệu

Đánh giá mức độ trung thành về ngữ nghĩa bằng cách đối chiếu các nguồn theo thứ tự sau:

1. **`original_summary` độc lập** — nguồn chuẩn để xác định các sự kiện câu chuyện, nhân vật thực hiện hành động, quan hệ nhân quả và kết thúc.
2. **Danh mục `characters[]` của storyboard** — các mô tả ngoại hình dùng chung và các bản ghi định danh nhân vật.
3. **`scenes[].characters[]` của storyboard** — các tham chiếu đến ID trong danh mục nhân vật cho từng cảnh.
4. **`scenes[].caption_vi` của storyboard** — hành động và nội dung tự sự ở cấp cảnh bằng tiếng Việt.
5. **`scenes[].image_prompt_en` của storyboard** — cách diễn giải trực quan cảnh bằng tiếng Anh.

`storyboard.summary` không thay thế cho `original_summary`. Nếu hai phần tóm tắt khác nhau, hãy ghi nhận riêng và chính xác trong `structural_or_summary_notes`, vì taxonomy tám mã chuẩn không có mã `SUMMARY_MISMATCH`. Việc hai bản tóm tắt không khớp, tự nó, không chứng minh chuỗi cảnh sai về ngữ nghĩa. Hãy đánh giá các cảnh dựa trên nguồn độc lập `original_summary`.

Tính hợp lệ về cấu trúc, mức độ khớp với bản tóm tắt và tính hợp lệ về ngữ nghĩa là ba khía cạnh riêng biệt. Một đối tượng có cấu trúc hợp lệ và đủ bốn cảnh vẫn có thể sai về ngữ nghĩa. Ngược lại, không được ép các lỗi về tính hợp lệ cấu trúc vào một trong tám mã lỗi ngữ nghĩa.

## 2. Taxonomy chuẩn (sử dụng chính xác mã TV1)

Chỉ sử dụng tám mã chuẩn dưới đây. Không tự tạo bí danh hoặc bổ sung mã lỗi về sự dư thừa/lặp lại giữa các cảnh.

| Mã chuẩn | Tiêu chí gán nhãn | Bằng chứng khẳng định cần có | Dương tính giả thường gặp cần tránh |
|---|---|---|---|
| `CHARACTER_IDENTITY_MISMATCH` | Tham chiếu trong cảnh, mô tả ngoại hình trong catalog, caption hoặc prompt gán nội dung cho sai thực thể trong câu chuyện. | Có mâu thuẫn cụ thể giữa nguồn/cảnh/catalog, xác định được thực thể nào đang bị thể hiện sai. | Chỉ dựa vào cách viết ID; người có ngoại hình giống nhau; nhân vật mặc quần áo khác; prompt chung chung không xác định một người cụ thể. |
| `CHARACTER_ROLE_MISMATCH` | Người thực hiện, tiếp nhận hoặc gây ra một hành động khác với nguồn hoặc khác với nội dung tương ứng trong caption/prompt. | Xác định được mâu thuẫn giữa nhân vật thực hiện hành động và hành động; không chỉ là việc prompt hình ảnh bỏ tên nhân vật. | Prompt thể hiện một hành động hình ảnh phụ trợ trong khi caption mô tả sự kiện chính của cảnh, nếu hai hành động vẫn có thể đồng thời xảy ra. |
| `CHARACTER_FRAGMENTATION` | Một thực thể trong nguồn bị tách thành nhiều bản ghi trong catalog do thay đổi hành động, cảm xúc hoặc trạng thái cảnh, tạo ra các định danh/tham chiếu trùng lặp. | Nguồn cho thấy chỉ có một thực thể, nhưng catalog/tham chiếu lại tạo nhiều bản ghi được đặt tên theo trạng thái cho cùng thực thể đó; các tham chiếu trùng xuất hiện đồng thời là bằng chứng mạnh. | Chỉ có mô tả ngoại hình trùng nhau; chỉ có bản ghi không được sử dụng; hai người khác nhau có ngoại hình tương tự. |
| `OBJECT_TRANSLATION_MISMATCH` | Một đối tượng cụ thể bị dịch sai hoặc bị thay thế bằng một đối tượng khác về mặt ngữ nghĩa giữa nguồn/caption và image prompt tiếng Anh. | Có trích dẫn chính xác tên đối tượng trong nguồn và phần văn bản image prompt mâu thuẫn với nó. | Khác màu sắc/chất liệu/góc nhìn; diễn giải trực quan hợp lý nhưng vẫn giữ nguyên danh tính/chức năng của đối tượng. |
| `VISUAL_LANGUAGE_MISMATCH` | Mô tả `Character.visual` dùng chung không đáp ứng yêu cầu sử dụng tiếng Anh của hợp đồng. | Chuỗi chính xác tại `characters[i].visual` rõ ràng được viết bằng ngôn ngữ khác, không chỉ là tên riêng hoặc một token ngắn mơ hồ. | Caption tiếng Việt; tên riêng; thuật ngữ ngắn pha trộn ngôn ngữ; image prompt hoặc caption (mã này chỉ áp dụng cho `Character.visual` dùng chung). |
| `MISSING_KEY_EVENT` | Một sự kiện quan trọng trong nguồn, cần thiết để giữ nguyên quan hệ nhân quả, động cơ hoặc kết quả, không xuất hiện trong toàn bộ chuỗi cảnh. | Có một sự kiện cụ thể trong `original_summary`, đồng thời đã rà soát cả bốn cảnh và xác định không có cách thể hiện tương đương về hình ảnh/nội dung tự sự. | Bỏ sót chi tiết nhỏ; rút gọn nội dung; sự kiện được thể hiện bằng hình ảnh dù không có từ ngữ tương ứng; sự kiện không có trong `storyboard.summary` nhưng vẫn xuất hiện trong các cảnh. |
| `ENDING_CONTRADICTION` | Cảnh/kết quả cuối cùng mâu thuẫn với phần kết trong nguồn độc lập. | Có trích dẫn chính xác kết quả trong nguồn và caption/image prompt cuối thể hiện kết quả không tương thích. | Kết thúc được rút gọn nhưng vẫn phù hợp; cách thể hiện hình ảnh khác nhưng cùng một kết quả. |
| `UNSUPPORTED_STORY_EVENT` | Một sự kiện/hành động/mối quan hệ mới không có căn cứ trong nguồn và làm thay đổi đáng kể cốt truyện. | Có đoạn văn bản storyboard chính xác khẳng định sự kiện được thêm vào, đồng thời việc đối chiếu nguồn xác nhận sự kiện đó làm thay đổi cốt truyện mà không có căn cứ. | Tư thế, góc máy, ánh sáng, bối cảnh, quần áo, đạo cụ nền vô hại hoặc hành động kết nối hợp lý không làm thay đổi câu chuyện. |

### Nguyên tắc tránh kết luận nhầm về định danh và phân mảnh nhân vật

- `Character.id` là khóa tham chiếu, tự nó không phải bằng chứng ngữ nghĩa đầy đủ. Hãy đọc kết hợp `visual` trong catalog, caption các cảnh, image prompt và `original_summary`.
- Mô tả ngoại hình giống hệt hoặc gần giống nhau không tự động có nghĩa hai bản ghi là cùng một cá nhân. Hai người khác nhau có thể được cố ý mô tả giống nhau.
- Mô tả ngoại hình khác nhau cũng không tự động có nghĩa là hai cá nhân khác nhau: quần áo, tư thế, cách thể hiện tuổi tác hoặc trạng thái cảm xúc có thể thay đổi, trừ khi câu chuyện quy định khác.
- Không kết luận catalog bị phân mảnh chỉ vì có các bản ghi không được sử dụng. Hãy giải thích liệu cùng một thực thể trong nguồn có bị tách thành các bản ghi mang tên trạng thái/hành động hay không, và các tham chiếu có thực sự sử dụng những bản ghi đó hay không.

## 3. Mức độ nghiêm trọng: `error` hoặc `warning`

Mức độ nghiêm trọng (severity) là trục đánh giá tác động, độc lập với độ chắc chắn thể hiện qua `status`. Không được gán cứng một mã lỗi với một mức severity cố định.

- **`error`** — lỗi làm thay đổi hoặc mâu thuẫn đáng kể với một thực thể trong nguồn, nhân vật thực hiện/hành động, danh tính đối tượng, sự kiện quan trọng hoặc kết thúc; hoặc tạo các định danh catalog riêng biệt cho cùng một nhân vật theo cách có thể khiến hình ảnh dựng ra các nhân vật trùng lặp và phá vỡ tính liên tục.
- **`warning`** — có sai khác thực sự về hợp đồng/phong cách nhưng ý nghĩa câu chuyện cơ bản vẫn có thể khôi phục, hoặc bằng chứng quan sát được còn hạn chế và tác động chưa được xác lập. Trường hợp `Character.visual` đã xác nhận không dùng tiếng Anh thường được xếp `warning` nếu người đọc song ngữ vẫn hiểu rõ nội dung; chỉ nâng mức khi sai khác ngôn ngữ gây ra lỗi đáng kể về định danh/ý nghĩa.

Severity không đồng nghĩa với độ tin cậy. Trong một phản hồi dự thảo, issue có `status=uncertain` chỉ nên đi kèm mức severity thận trọng (`warning`). Nếu adjudication sau đó xác lập được một mâu thuẫn có tác động đáng kể, hãy cập nhật cả status và severity, đồng thời ghi lại lý do.

## 4. Trạng thái issue, kết luận case và trạng thái review

### Trường `status` của issue

- **`confirmed`** — bằng chứng đủ để kết luận sai khác ngữ nghĩa được mô tả thực sự tồn tại.
- **`uncertain`** — có khả năng tồn tại sai khác nhưng dữ liệu chưa đủ để phân định các cách diễn giải cạnh tranh. Hãy nêu chính xác điểm nào còn mơ hồ.

### Verdict của case (các giá trị chuẩn `pass` / `fail` / `uncertain`)

| Verdict | Quy tắc |
|---|---|
| `pass` | Đã review đầy đủ và không tìm thấy issue nào có căn cứ; `issues` bắt buộc phải rỗng. Template trống/chưa review không bao giờ được coi là pass. |
| `fail` | Có ít nhất một issue đã xác nhận với `severity=error`. Có thể đồng thời tồn tại các issue mức warning. |
| `uncertain` | Không có error nào đã được xác nhận, nhưng vẫn còn một hoặc nhiều phát hiện ở mức warning/uncertain, hoặc bằng chứng chưa đủ để kết luận pass/fail. |

Các quy tắc này khớp với hợp đồng nghiêm ngặt của `SemanticReviewResponse` trên nhánh `main`: `pass` không được chứa bất kỳ issue nào; `fail` yêu cầu ít nhất một issue mức error; `uncertain` không được chứa issue mức error. Không đưa các giả thuyết lỗi mức error còn tạm thời vào phản hồi production. Hãy giữ chúng trong bản dự thảo annotation của con người với `status=uncertain` cho đến khi được adjudicate.

### Metadata review của case

- `human_review_state`: `pending_human_review` trước khi review; `in_progress` trong khi đang review; chỉ dùng `completed` khi một người thực sự hoàn tất việc đánh giá case.
- `annotation_status`: `confirmed` khi kết luận cấp case có đủ căn cứ và không còn mơ hồ ngữ nghĩa chưa được giải quyết; `uncertain` khi sau review vẫn còn điểm chưa rõ.
- Phải ghi `review_date`, thông tin annotator và `rubric_version`.
- Bản nháp do AI/pre-annotation tạo ra tuyệt đối không được đặt `human_review_state=completed`, cũng không được trình bày verdict đề xuất của nó như nhãn gold do con người xác nhận.

### Trạng thái review khi chạy hệ thống không phải verdict ngữ nghĩa

`SemanticValidationReport.review_status` trong production có các giá trị `completed`, `failed` và `not_checked`; trường này tách biệt với `SemanticReviewResponse.verdict`:

- `completed` nghĩa là phản hồi đã vượt qua kiểm tra parsing, schema nghiêm ngặt và hợp đồng location/evidence. Chỉ khi đó `verdict` mới được điền.
- `failed` nghĩa là lời gọi reviewer/đầu ra/hợp đồng bị lỗi. Đây **không phải** verdict ngữ nghĩa `fail` và không có verdict ngữ nghĩa.
- `not_checked` nghĩa là nguồn/đối số không đủ điều kiện để review (ví dụ storyboard nguồn không hợp lệ). Đây không phải `pass` hay `fail`.

Human annotations được lưu riêng. Báo cáo chính hiện tại cung cấp `human_annotation_status="not_checked"`; không chèn nhãn con người vào prompt Qwen hoặc giả vờ rằng chúng là một phần của báo cáo chạy hệ thống. Verdict của một case do con người đánh giá là nhãn phục vụ evaluation, không phải trạng thái thực thi runtime.

## 5. Vị trí và bằng chứng trích dẫn chính xác (hợp đồng TV1)

### Đường dẫn đánh chỉ số từ 0 (zero-based)

`location` là một danh sách đường dẫn JSON gồm tên trường và vị trí phần tử trong mảng, trong đó vị trí mảng bắt đầu từ 0. Hãy dùng vị trí trong mảng, không dùng giá trị `Scene.index` (từ 1 đến 4) và không dùng character ID thay cho vị trí phần tử.

Ví dụ:

- `characters[2].visual` → `["characters", 2, "visual"]`
- caption của cảnh thứ hai → `["scenes", 1, "caption_vi"]`
- tham chiếu nhân vật đầu tiên của cảnh thứ ba → `["scenes", 2, "characters", 0]`
- toàn bộ storyboard/tìm kiếm sự kiện bị thiếu ở phạm vi chung → `[]` (hoặc `["scenes"]` nếu muốn gắn issue với tập hợp cảnh).

Quy tắc: thành phần đường dẫn phải là chuỗi không rỗng hoặc số nguyên không âm biểu thị vị trí. Giá trị boolean không được xem là vị trí số nguyên. `issue.location` phải trỏ tới một vị trí tồn tại trong snapshot storyboard. Với một issue duy nhất trải trên nhiều trường, hãy dùng một `location` chính và liệt kê các đường dẫn còn lại trong phần mở rộng dành cho định dạng human là `related_locations`; không nhân đôi issue.

### Đối tượng evidence

Cấu trúc evidence chuẩn:

```json
{"source":"original_summary","location":[],"quote":"exact source substring"}
```

hoặc

```json
{"source":"storyboard","location":["scenes",1,"caption_vi"],"quote":"exact field substring"}
```

Quy tắc:

- `source` phải chính xác là `original_summary` hoặc `storyboard`.
- `original_summary` là một chuỗi duy nhất; vì vậy `location` của evidence này bắt buộc là `[]`.
- Evidence có `source=storyboard` phải trỏ đến một **trường chuỗi** đang tồn tại, bao gồm cả chuỗi tham chiếu nhân vật riêng lẻ nếu cần. Không trích dẫn toàn bộ object/mảng hoặc chuyển số nguyên thành chuỗi để trích dẫn.
- `quote` phải là một đoạn con chính xác, không rỗng, của chuỗi được khai báo tại đường dẫn đó. Không dịch, diễn giải lại, đổi chữ hoa/thường, cắt khoảng trắng hoặc chuẩn hóa Unicode (các dạng NFC/NFD không thể thay thế cho nhau).
- Với mâu thuẫn, hãy trích dẫn cả hai phía khi có thể. Với sự kiện bị bỏ sót, trích dẫn sự kiện từ `original_summary` và neo issue vào tập hợp cảnh/toàn storyboard; tuyệt đối không tự tạo câu trích dẫn cho phần văn bản không tồn tại.
- Việc đường dẫn/trích dẫn chính xác chỉ chứng minh khả năng truy vết. Điều đó không chứng minh phần giải thích hoặc suy luận ngữ nghĩa là đúng.

Khi xuất sang `SemanticIssue`, ánh xạ trường human `explanation` thành trường chuẩn `message`; chỉ xuất `code`, `severity`, `location`, `message`, `evidence`. Các trường chỉ dành cho định dạng human gồm `issue_id`, `status` và `related_locations`; không được đưa chúng vào `SemanticReviewResponse` production nghiêm ngặt nếu chưa có thay đổi schema được version riêng.

## 6. Đơn vị issue và chính sách so khớp (phải chốt trước khi so sánh với Qwen)

### Đơn vị phân tích

Một issue là một sai khác ngữ nghĩa nền tảng, riêng biệt trong một case. Nhiều trích dẫn hoặc vị trí cảnh cùng chứng minh một sai khác phải được gộp thành một issue (`location` làm vị trí neo + `related_locations` + danh sách evidence). Không tạo một issue cho mỗi câu trích dẫn hoặc lặp lại cùng một lỗi ánh xạ đối tượng/nhân vật ở mọi cảnh nếu đó là một lỗi nhất quán. Có thể tạo các issue riêng khi bản chất quan hệ nhân quả thực sự khác nhau (ví dụ: hai nhân vật khác nhau trong nguồn, mỗi người đều bị phân mảnh thành nhiều bản ghi riêng).

### So khớp một-một

Một dự đoán của Qwen chỉ khớp với một issue human đã xác nhận khi đáp ứng tất cả điều kiện sau:

1. Cùng một case.
2. Chính xác cùng một mã issue chuẩn (không ánh xạ mã gần đúng/bí danh).
3. Cùng một sai khác nền tảng về thực thể/hành động/đối tượng/sự kiện/kết quả sau khi xem xét phần giải thích và bằng chứng.
4. `location` của dự đoán bằng vị trí neo của issue human hoặc một trong các `related_locations` của issue đó; không tự động coi đường dẫn cha, tiền tố đường dẫn hoặc `[]` là ký tự đại diện.
5. Cả hai phía đều có bằng chứng truy vết được và hỗ trợ cùng một sai khác. Trích dẫn không cần giống nhau từng byte, nhưng mỗi trích dẫn phải độc lập là đoạn con chính xác tại nguồn/đường dẫn đã khai báo.

Sử dụng so khớp một-một: một dự đoán chỉ có thể khớp tối đa một issue gold, và một issue gold chỉ có thể khớp tối đa một dự đoán. Các dự đoán trùng không được ghép sẽ được tính là dự đoán không khớp (có khả năng là false positive) và đồng thời được báo cáo trong chẩn đoán dự đoán trùng; không được âm thầm loại bỏ bản trùng. Các issue gold của con người bị trùng phải được adjudicate trước khi freeze.

### Severity và uncertainty khi so khớp

- So khớp ngữ nghĩa chính dựa trên code + sai khác nền tảng + location + evidence. So sánh severity riêng như một chỉ số đồng thuận về mức nghiêm trọng; bất đồng severity không làm mất một kết quả so khớp ngữ nghĩa vốn hợp lệ.
- Chỉ các issue human có `status=confirmed` mới được đưa vào phép so khớp gold đã xác nhận chính (primary confirmed-gold matching).
- Các phát hiện human ở trạng thái uncertain phải được báo cáo riêng; không tính chúng là positive hoặc negative đã xác nhận, và không chấm dự đoán của Qwen đối với chúng như FP/FN dứt khoát.
- Một case có issue error đã xác nhận vẫn có thể có verdict `fail` dù đồng thời chứa các phát hiện warning/uncertain. Một case không có error đã xác nhận nhưng còn phát hiện chưa được giải quyết phải là `uncertain`, không phải `pass`.

### Mẫu số và xử lý thất bại

Trước khi so sánh, cần công bố danh sách case đủ điều kiện, danh sách issue đã xác nhận, chính sách so khớp và danh sách lời gọi dự kiến. Báo cáo riêng: số lời gọi reviewer hoàn thành/thất bại/chưa chạy, quyết định hợp lệ, trường hợp từ chối/uncertain, số issue gold đã xác nhận, số dự đoán được chấp nhận, số cặp khớp, dự đoán không khớp và issue gold không khớp. Không được loại các lần reviewer thất bại/từ chối khỏi danh mục mà không báo cáo độ bao phủ. Không tính chỉ số từ các annotation đang pending/uncertain như thể chúng là nhãn negative.

## 7. Biến thể sáng tạo: mặc định không phải lỗi

Chấp nhận các cách dàn dựng hình ảnh/tự sự vô hại nếu vẫn giữ nguyên danh tính trong nguồn, hành động, trình tự nhân quả và kết thúc: bố cục, góc nhìn, tư thế, biểu cảm, ánh sáng, quần áo, phông nền, đạo cụ không ảnh hưởng đến cốt truyện và các chi tiết kết nối hợp lý. Một hành động chuẩn bị (ví dụ: gom dụng cụ trước khi tiến hành sửa chữa đã được nêu) không tự động là sự kiện không có căn cứ làm thay đổi cốt truyện. Khi hữu ích cho adjudication, hãy ghi nhận các biến thể được chấp nhận; không coi chúng là lỗi.

## 8. Phạm vi và tính độc lập

- Chỉ gán nhãn cho bốn đầu ra development, bốn case control và hai case exploratory được cung cấp. Manifest dùng ID trung tính không ánh xạ `case_001`…`case_010` vào các nhóm này; không suy đoán nhóm dựa trên thứ tự hoặc nội dung. Nếu cần báo cáo phân tầng, điều phối viên phải cung cấp bảng ánh xạ riêng.
- Không sử dụng bộ Test chính thức gồm 30 câu chuyện để tinh chỉnh rubric hoặc phát triển reviewer.
- Không xem nhãn kỳ vọng, mô tả mutation, gợi ý AI hoặc dự đoán Qwen trước khi annotation được freeze.
- Human annotations phải được lưu tách biệt với prompt và input của Qwen reviewer. Không chèn bất kỳ nhãn human nào vào prompt reviewer.
- Giữ nguyên các case gốc đã freeze, manifest, checksums và template trống; lưu annotation thành một package mới. Khai báo trung thực việc đã tiếp xúc với dữ liệu/dự đoán trước đó; không tuyên bố review mù nếu đã xem prediction/nhãn thiết kế trước đó.
- Rubric này là **bản dự thảo TV3 v1.0** cho đến khi được trưởng nhóm chấp thuận. Mọi thay đổi sau khi đã xem dự đoán cần có version mới và ghi chú adjudication/audit.

## 9. Các quan sát ngoài phạm vi

Nếu một quan sát không đáp ứng bất kỳ mã nào trong tám mã chuẩn (ví dụ: vấn đề vệ sinh kiểu dữ liệu trong catalog, các dòng catalog không được sử dụng nhưng không có bằng chứng ngữ nghĩa, sai khác chính xác của `storyboard.summary`, hoặc vấn đề cấu trúc không thuộc ngữ nghĩa), hãy ghi vào `structural_or_summary_notes` hoặc `additional_notes`. Không ép quan sát đó vào một mã gần giống.
