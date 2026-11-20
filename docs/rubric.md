# Semantic Storyboard Validator — Human Annotation Rubric

**Version:** 1.0 — Draft  
**Project:** Vietnamese Comic Generation  
**Purpose:** Human evaluation of semantic errors in generated storyboards  
**Evaluation scope:** Development outputs and control cases only

---

## 1. Mục tiêu

Rubric này được sử dụng để đánh giá các lỗi ngữ nghĩa trong storyboard bằng cách đối chiếu:

1. Original story summary.
2. Character catalog.
3. Storyboard captions.
4. Image prompts.

Mục tiêu là xác định storyboard có giữ đúng nội dung và ý nghĩa của câu chuyện gốc hay không, bao gồm danh tính nhân vật, vai trò, sự kiện, đạo cụ và kết thúc.

Rubric tập trung vào tám issue types:

| Issue code | Issue type |
|---|---|
| CHAR_ID_MISMATCH | Character identity mismatch |
| CHAR_ROLE_MISMATCH | Character role mismatch |
| CHAR_FRAGMENTATION | Character fragmentation |
| OBJ_TRANSLATION_MISMATCH | Object translation mismatch |
| VISUAL_LANGUAGE_MISMATCH | Visual language mismatch |
| MISSING_KEY_EVENT | Missing key event |
| ENDING_CONTRADICTION | Ending contradiction |
| UNSUPPORTED_STORY_EVENT | Unsupported story event |

## 2. Nguyên tắc annotation

### 2.1. Source of truth

Sử dụng các nguồn theo chức năng:

- **Original summary:** nguồn chính để xác định nội dung, sự kiện, quan hệ và kết cục câu chuyện.
- **Character catalog:** nguồn tham chiếu danh tính, thuộc tính nhận diện và vai trò nhân vật.
- **Captions:** thể hiện diễn biến, hành động và nội dung được kể trong từng cảnh.
- **Image prompts:** thể hiện cách diễn giải nội dung thành hình ảnh, nhân vật, đạo cụ và phong cách thị giác.

Không tự bổ sung sự kiện vào summary hoặc character catalog dựa trên suy đoán của người annotation.

### 2.2. Phân biệt semantic error và creative variation

Không phải mọi chi tiết khác biệt so với summary đều là lỗi.

**Không mặc định ghi lỗi đối với:**
- Góc máy, bố cục và phối cảnh khác nhau.
- Ánh sáng, thời tiết hoặc màu nền được sáng tạo hợp lý.
- Biểu cảm và tư thế phù hợp với hành động.
- Chi tiết trang trí không thay đổi ý nghĩa câu chuyện.
- Cách diễn đạt khác nhau nhưng vẫn giữ đúng sự kiện.
- Mô tả ngoại hình khác nhau giữa các cảnh nếu vẫn nhận diện được cùng nhân vật.

**Chỉ ghi lỗi khi có bằng chứng về sự sai lệch ngữ nghĩa**, chẳng hạn nhân vật bị thay đổi danh tính, vai trò bị đảo ngược, sự kiện quan trọng bị bỏ hoặc xuất hiện sự kiện mới làm thay đổi cốt truyện.

### 2.3. Character identity không đồng nghĩa visual description

Hai mô tả hình ảnh khác nhau không đủ để kết luận hai nhân vật là hai cá thể khác nhau.

Ví dụ:

- “Ông lão mặc áo nâu, tóc bạc.”
- “Người đàn ông lớn tuổi, tóc trắng, mặc trang phục truyền thống.”

Hai mô tả này có thể cùng chỉ một nhân vật.

Chỉ xác định Character Fragmentation khi có bằng chứng rằng một nhân vật nguồn bị chia thành nhiều thực thể hoặc ID khác nhau trong storyboard.

---

## 3. Chi tiết tám loại lỗi

### 3.1. CHAR_ID_MISMATCH — Character identity mismatch

**Định nghĩa:** Nhân vật xuất hiện trong storyboard không đúng danh tính của nhân vật tương ứng trong character catalog hoặc bị nhầm với một nhân vật khác.

**Điều kiện ghi nhận:**
- Nhân vật được gán sai tên hoặc sai ID.
- Hình ảnh hoặc mô tả thể hiện rõ nhân vật khác với nhân vật catalog.
- Hai nhân vật có danh tính riêng biệt bị nhầm lẫn.

**Ví dụ:**

Summary và catalog xác định:
- Nhân vật A là người cha.
- Nhân vật B là người con.

Caption hoặc image prompt gán hành động và danh tính của A cho B.

**Không ghi lỗi khi:**
- Một nhân vật được gọi bằng tên riêng và đại từ phù hợp.
- Mô tả trang phục thay đổi nhưng không có bằng chứng thay đổi danh tính.
- Nhân vật được biểu diễn bằng góc nhìn hoặc góc máy khác.

### 3.2. CHAR_ROLE_MISMATCH — Character role mismatch

**Định nghĩa:** Nhân vật đúng danh tính nhưng thực hiện sai vai trò, hành động hoặc mối quan hệ quan trọng trong câu chuyện.

**Điều kiện ghi nhận:**
- Người giúp đỡ bị thể hiện thành người gây trở ngại.
- Nhân vật nhận nhiệm vụ bị thể hiện thành người giao nhiệm vụ.
- Quan hệ cha/con, chủ/tớ hoặc người trao/nhận vật phẩm bị đảo ngược.
- Nhân vật thực hiện hành động trái với vai trò đã xác định trong nguồn.

**Không ghi lỗi khi:**
- Nhân vật thể hiện cảm xúc khác nhau theo diễn biến.
- Nhân vật có thêm hành động phụ hợp lý.
- Vai trò không được xác định rõ trong summary.

### 3.3. CHAR_FRAGMENTATION — Character fragmentation

**Định nghĩa:** Một nhân vật nguồn bị biểu diễn như nhiều nhân vật độc lập trong storyboard mà không có cơ sở từ câu chuyện.

**Điều kiện ghi nhận:**
- Cùng một nhân vật được tạo thành hai hoặc nhiều identity khác nhau.
- Nhân vật bị gán nhiều ID hoặc tên khác nhau dù nguồn xác nhận chỉ có một cá thể.
- Sự phân tách khiến diễn biến hoặc quan hệ nhân vật trở nên sai lệch.

**Không ghi lỗi khi:**
- Hai nhân vật có ngoại hình tương tự nhau.
- Một nhân vật có nhiều tư thế, biểu cảm hoặc bộ trang phục.
- Một nhân vật được mô tả bằng nhiều câu prompt khác nhau.

**Quy tắc quan trọng:** Duplicate visual descriptions không mặc định là duplicate identity.

### 3.4. OBJ_TRANSLATION_MISMATCH — Object translation mismatch

**Định nghĩa:** Đạo cụ hoặc vật thể quan trọng trong câu chuyện bị chuyển thành một vật thể khác hoặc bị thay đổi thuộc tính làm sai chức năng và ý nghĩa.

**Điều kiện ghi nhận:**
- Một vật phẩm quan trọng bị thay bằng vật phẩm khác.
- Vật được trao, lấy, đánh mất hoặc sử dụng không đúng với nội dung.
- Đặc điểm vật thể bị thay đổi làm ảnh hưởng đến diễn biến.

**Ví dụ:**

Summary nói nhân vật tìm thấy một chiếc chìa khóa; image prompt lại thể hiện một chiếc vòng cổ như vật phẩm được tìm thấy.

**Không ghi lỗi khi:**
- Màu sắc hoặc chất liệu được thay đổi nhưng không ảnh hưởng chức năng.
- Góc nhìn làm vật thể trông khác nhau.
- Vật thể được thể hiện theo phong cách minh họa khác.

### 3.5. VISUAL_LANGUAGE_MISMATCH — Visual language mismatch

**Định nghĩa:** Cách thể hiện hình ảnh không phù hợp với yêu cầu hoặc ngữ nghĩa thị giác được xác định cho storyboard.

**Điều kiện ghi nhận:**
- Image prompt mô tả sai trạng thái thị giác thiết yếu của cảnh.
- Nhân vật hoặc môi trường được thể hiện theo hướng làm thay đổi ý nghĩa hành động.
- Chỉ dẫn thị giác mâu thuẫn rõ ràng với định hướng hình ảnh đã được cung cấp.

**Ví dụ:**

Caption mô tả một khu rừng ban đêm, nhưng image prompt lại yêu cầu khung cảnh ban ngày và ánh nắng mạnh, trong khi sự tương phản thời gian là yếu tố quan trọng của câu chuyện.

**Không ghi lỗi khi:**
- Màu sắc, ánh sáng hoặc phong cách nghệ thuật thay đổi nhưng vẫn bảo toàn ngữ nghĩa.
- Có biến đổi phong cách giữa các ảnh nếu không làm thay đổi danh tính hoặc nội dung.
- Chỉ khác nhau về bố cục hoặc kỹ thuật tạo ảnh.

### 3.6. MISSING_KEY_EVENT — Missing key event

**Định nghĩa:** Một sự kiện quan trọng trong original summary không được thể hiện hoặc không thể nhận diện trong storyboard.

**Điều kiện ghi nhận:**
- Một sự kiện cần thiết để hiểu mạch truyện bị bỏ qua.
- Một hành động gây ra kết quả quan trọng không xuất hiện.
- Sự kiện quyết định động cơ hoặc chuyển biến của nhân vật không được thể hiện.

**Không ghi lỗi khi:**
- Một sự kiện được diễn đạt bằng hình ảnh thay vì lời kể.
- Hai sự kiện liên tiếp được gộp thành một cảnh nhưng vẫn bảo toàn quan hệ nguyên nhân – kết quả.
- Một chi tiết phụ không thiết yếu được lược bỏ hợp lý.

### 3.7. ENDING_CONTRADICTION — Ending contradiction

**Định nghĩa:** Kết thúc storyboard mâu thuẫn với kết cục được xác định trong original summary.

**Điều kiện ghi nhận:**
- Người chiến thắng và người thất bại bị đảo ngược.
- Nhân vật được cứu trong nguồn nhưng lại kết thúc trong trạng thái không được cứu.
- Nhân vật trở về trong nguồn nhưng storyboard thể hiện họ không trở về.
- Kết quả cuối cùng làm thay đổi thông điệp hoặc ý nghĩa truyện.

**Không ghi lỗi khi:**
- Kết thúc được rút gọn nhưng vẫn giữ đúng kết quả.
- Phần kết được minh họa theo cách khác nhưng không thay đổi ý nghĩa.
- Summary không mô tả kết thúc đủ rõ để xác định mâu thuẫn.

### 3.8. UNSUPPORTED_STORY_EVENT — Unsupported story event

**Định nghĩa:** Storyboard thêm sự kiện, hành động hoặc mối quan hệ quan trọng không có căn cứ trong original summary hoặc character catalog.

**Điều kiện ghi nhận:**
- Xuất hiện một sự kiện mới làm thay đổi diễn biến.
- Nhân vật có hành động quan trọng không được hỗ trợ bởi nguồn.
- Xuất hiện một nhân vật mới tham gia vào cốt truyện mà không có căn cứ.
- Thêm xung đột hoặc kết quả mới làm thay đổi ý nghĩa truyện.

**Không ghi lỗi khi:**
- Thêm biểu cảm, cử chỉ và tương tác phụ hợp lý.
- Thêm đồ vật nền hoặc chi tiết trang trí.
- Thêm yếu tố thị giác giúp thể hiện bối cảnh nhưng không tạo ra sự kiện mới.
- Một hành động được suy ra trực tiếp và hợp lý từ sự kiện đã nêu, không làm thay đổi cốt truyện.

---

## 4. Quy tắc xác định trạng thái

Mỗi annotation phải có một trong hai trạng thái.

| Status | Tiêu chí |
|---|---|
| confirmed | Có bằng chứng rõ ràng từ source và storyboard cho thấy lỗi thực sự xảy ra. |
| uncertain | Có dấu hiệu nghi ngờ nhưng thông tin chưa đủ để kết luận chắc chắn. |

### confirmed

Chỉ sử dụng khi:
- Có thể xác định chính xác vị trí lỗi.
- Có evidence cụ thể.
- Có thể chỉ ra nội dung nguồn và nội dung storyboard mâu thuẫn hoặc sai lệch.
- Không có một cách diễn giải hợp lý khác giải thích sự khác biệt.

### uncertain

Sử dụng khi:
- Summary thiếu thông tin nhận diện.
- Character catalog chưa đủ rõ.
- Image prompt có thể có nhiều cách diễn giải.
- Không đủ bằng chứng để xác định một nhân vật hay vật thể.
- Sự khác biệt có thể là sáng tạo hợp lý hoặc là lỗi ngữ nghĩa.

Không tự chuyển uncertain thành confirmed chỉ vì người annotation nghi ngờ mạnh.

---

## 5. Annotation location

Location phải chỉ ra được vị trí nhỏ nhất có thể xác định.

Ví dụ:

- `scene_01.caption`
- `scene_02.image_prompt`
- `scene_03.character_id`
- `scene_02.object`
- `scene_01-scene_04.character_consistency`
- `story.ending`

Đối với lỗi liên quan nhiều cảnh, phải ghi rõ toàn bộ các cảnh có liên quan.

Không ghi chung chung như `storyboard error` hoặc `character problem`.

---

## 6. Annotation output schema

Mỗi annotation bắt buộc có đúng năm trường:

| Field | Ý nghĩa |
|---|---|
| issue_code | Một trong tám issue code đã định nghĩa |
| location | Vị trí cụ thể trong storyboard |
| evidence | Trích dẫn hoặc mô tả bằng chứng có thể truy vết |
| explanation | Giải thích vì sao đây là lỗi hoặc vì sao chưa thể kết luận |
| status | `confirmed` hoặc `uncertain` |

Ví dụ cấu trúc:

\`\`\`json
{
  "issue_code": "CHAR_ID_MISMATCH",
  "location": "scene_02.image_prompt",
  "evidence": {
    "source": "character_catalog",
    "reference": "Nhân vật A được xác định là người cha.",
    "observed": "Image prompt mô tả nhân vật này là người con."
  },
  "explanation": "Image prompt gán sai danh tính nhân vật so với character catalog.",
  "status": "confirmed"
}
\`\`\`

Đây chỉ là ví dụ minh họa schema, không phải annotation của một mẫu thực tế.

Một storyboard có thể có nhiều annotation. Mỗi annotation phải mô tả một lỗi độc lập, tránh ghi trùng cùng một vấn đề dưới nhiều issue code nếu không có các sai lệch riêng biệt.

Nếu một storyboard không có lỗi, không tạo annotation giả. Ghi nhận trường hợp đó trong bảng tổng hợp đánh giá của sample.

---

## 7. Quy trình human annotation

1. Đọc original summary để hiểu toàn bộ câu chuyện.
2. Đọc character catalog để xác định từng nhân vật và vai trò.
3. Đọc lần lượt captions theo thứ tự cảnh.
4. Đối chiếu image prompts với captions và character catalog.
5. Kiểm tra tám issue types theo định nghĩa.
6. Thu thập evidence và xác định location.
7. Gán status confirmed hoặc uncertain.
8. Kiểm tra lại các trường hợp sáng tạo hợp lý để tránh false positives.
9. Lưu annotation độc lập với dữ liệu của Qwen semantic reviewer.

Không sử dụng official Test dataset cho hoạt động phát triển hoặc điều chỉnh rubric.

---

## 8. Phân biệt Human Annotation và Qwen Semantic Review

Hai nguồn kết quả phải được lưu độc lập.

**Human Annotation**
- Do người đánh giá thực hiện.
- Sử dụng rubric này.
- Được dùng làm reference để so sánh.
- Không đưa vào reviewer prompt.

**Qwen Semantic Review**
- Được thực hiện bằng reviewer đã thiết kế riêng.
- Lưu kết quả độc lập.
- Không nhận trước human annotations.
- Không được điều chỉnh prompt dựa trên nhãn human của cùng development sample trong quá trình đánh giá so sánh.

Việc này nhằm tránh information leakage và bảo đảm kết quả so sánh có ý nghĩa.

---

## 9. Phạm vi thực nghiệm ban đầu

- Chỉ dùng bốn development outputs do người phụ trách cung cấp.
- Sử dụng thêm các control cases để kiểm tra khả năng phân biệt lỗi và chi tiết sáng tạo hợp lý.
- Không sử dụng official Test dataset.
- Không gọi AI API.
- Không chạy GPU.
- Không tự tạo hoặc suy đoán annotation cho dữ liệu chưa được cung cấp.

Sau khi hoàn thành annotation, có thể tổng hợp:
- Số lượng confirmed theo issue code.
- Số lượng uncertain theo issue code.
- Các trường hợp creative variation được chấp nhận.
- Các trường hợp khó phân biệt hoặc cần điều chỉnh hướng dẫn.

**Trạng thái:** Rubric v1 — chuẩn bị cho development annotation.
