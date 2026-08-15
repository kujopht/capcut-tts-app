# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt

CEREBRAS_API_KEY: có
GROQ_API_KEY: có

| Model | Đoạn | Trạng thái | Độ trễ (s) | Token in/out |
|---|---|---|---|---|
| Cerebras · GPT-OSS 120B | hoi_thoai_xung_ho | ok | 0.72 | 369/135 |
| Cerebras · GPT-OSS 120B | tuong_thuat_dia_danh | ok | 0.49 | 372/71 |
| Cerebras · GPT-OSS 120B | he_thong_thuat_ngu | ok | 0.44 | 367/131 |
| Cerebras · GPT-OSS 120B | doi_thoai_nhieu_nhan_vat | ok | 0.47 | 367/174 |
| Groq · Qwen 3.6 27B | hoi_thoai_xung_ho | ok | 0.55 | 262/36 |
| Groq · Qwen 3.6 27B | tuong_thuat_dia_danh | loi | 0.20 | None/None |
| Groq · Qwen 3.6 27B | he_thong_thuat_ngu | loi | 0.19 | None/None |
| Groq · Qwen 3.6 27B | doi_thoai_nhieu_nhan_vat | loi | 0.31 | None/None |

## Nội dung dịch (để đối chiếu chất lượng thủ công)

**Cerebras · GPT-OSS 120B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Dược Lão, nhíu mày nhẹ nhàng, thì thầm: “Thưa sư phụ, ngài đã biết chuyện này từ lâu rồi, phải không?”

**Cerebras · GPT-OSS 120B · tuong_thuat_dia_danh**

Ngày hôm ấy, dưới chân núi Vân Triệt xuất hiện một màn sương mù dày đặc, hai bên lối lên núi rải rác những cây khô kêu rên rỉ âm u trong gió.

**Cerebras · GPT-OSS 120B · he_thong_thuat_ngu**

Bing! Chúc mừng chủ nhân đã đột phá tới tầng thứ chín của kỳ luyện khí, nhận được một bản công pháp “Phổ Thiên Quy”. Vui lòng kiểm tra kịp thời.

**Cerebras · GPT-OSS 120B · doi_thoai_nhieu_nhan_vat**

“Ngươi到底是誰？” cô gắt hỏi.  
“Ta？” anh cười lạnh, “Cô sẽ sớm biết được.”

**Groq · Qwen 3.6 27B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Dược Lão, khẽ nhíu mày, thấp giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?"

## Lỗi chất lượng đã xác nhận — KHÔNG được che giấu/chuẩn hoá

**1. Groq Qwen 3.6 27B dịch sai "师父" thành "Thư sư" thay vì "Sư phụ".**

Xác nhận **tái lập được** qua 3 lần chạy độc lập (không phải nhiễu ngẫu nhiên một lần), bao gồm cả lần chạy thật với Cerebras key vừa thêm:
- Lần 1 (trước khi gỡ GLM): *"...trầm giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*
- Lần 2 (sau khi gỡ GLM): *"...trầm giọng nói: "Thư sư, chuyện này ngài đã sớm biết rồi, phải không?""*
- Lần 3 (benchmark thật với Cerebras, 2026-08-15): *"...thấp giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*

"师父" (shī fù) là cách xưng hô đệ tử gọi sư phụ — bản dịch chuẩn Hán Việt phải là **"Sư phụ"**, không phải "Thư sư" (không có nghĩa trong tiếng Việt). Lỗi thật của Groq Qwen 3.6 27B, không phải lỗi cấu hình.

**Đối chiếu: Cerebras GPT-OSS 120B dịch ĐÚNG cùng câu này** ("Thưa sư phụ") trong benchmark thật ở trên — cùng một câu nguồn, hai model cho kết quả khác nhau rõ rệt về đúng/sai xưng hô.

**2. Cerebras GPT-OSS 120B để sót nguyên văn tiếng Trung trong bản dịch đoạn hội thoại nhiều nhân vật.**

Đoạn `doi_thoai_nhieu_nhan_vat` (nguồn: `"你到底是谁？"她厉声问道。\n"我？"他冷笑一声，"你很快就会知道了。"`) được Cerebras GPT-OSS 120B trả về là:

> "Ngươi到底是誰？" cô gắt hỏi.
> "Ta？" anh cười lạnh, "Cô sẽ sớm biết được."

Model dịch được phần đầu câu ("Ngươi"/"Ta") nhưng **bỏ sót "到底是誰" — giữ nguyên chữ Hán chưa dịch**, và câu thứ hai bị dịch thiếu ("你很快就会知道了" — "cậu sẽ sớm biết thôi" — không xuất hiện đầy đủ trong bản dịch, chỉ còn "Cô sẽ sớm biết được" ghép vào lời thoại của "Ta"). Đây là lỗi dịch KHÔNG ĐẦY ĐỦ thật của Cerebras GPT-OSS 120B trên đoạn hội thoại nhiều nhân vật — cần cân nhắc khi đánh giá độ tin cậy của model này làm nhà cung cấp chính, đặc biệt với đoạn thoại phức tạp/nhiều lượt.

**Ghi chú số token:** Cerebras dùng nhiều token đầu vào hơn Groq cho cùng nội dung (367-372 so với 262-265) và token đầu ra cũng cao hơn đáng kể ở 2/4 đoạn (135, 174 so với 36) — có thể do khác biệt tokenizer, hoặc do tham số `reasoning_effort: "low"` vẫn để lại một phần suy luận trong token đếm được (tài liệu Cerebras ghi `max_completion_tokens` tính cả token suy luận) dù nội dung hiển thị không có `<think>` lộ ra. Chưa đủ dữ liệu để kết luận chắc chắn nguyên nhân — cần thêm nhiều lần chạy nếu muốn xác nhận.