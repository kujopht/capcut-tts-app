# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt

CEREBRAS_API_KEY: có
GROQ_API_KEY: có

**Tiêu chí thành công** (Cerebras cho ra bản dịch tiếng Việt đầy đủ cho cả 4 mẫu sau khi qua cơ chế tích vẹn/sửa lỗi, không còn sót tiếng Trung): ĐẠT ✓

| Model | Đoạn | Trạng thái | Đã sửa lỗi? | Độ trễ (s) | Token in/out |
|---|---|---|---|---|---|
| Cerebras · GPT-OSS 120B | hoi_thoai_xung_ho | ok | — | 0.70 | 369/189 |
| Cerebras · GPT-OSS 120B | tuong_thuat_dia_danh | ok | — | 0.45 | 372/77 |
| Cerebras · GPT-OSS 120B | he_thong_thuat_ngu | ok | — | 0.55 | 367/331 |
| Cerebras · GPT-OSS 120B | doi_thoai_nhieu_nhan_vat | ok | có | 0.92 | 463/145 |
| Groq · Qwen 3.6 27B | hoi_thoai_xung_ho | ok | — | 0.42 | 262/35 |
| Groq · Qwen 3.6 27B | tuong_thuat_dia_danh | loi | — | 0.19 | None/None |
| Groq · Qwen 3.6 27B | he_thong_thuat_ngu | loi | — | 0.19 | None/None |
| Groq · Qwen 3.6 27B | doi_thoai_nhieu_nhan_vat | loi | — | 0.22 | None/None |

## Nội dung dịch (để đối chiếu chất lượng thủ công)

**Cerebras · GPT-OSS 120B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Yếu Lão, nhíu mày nhẹ, thì thầm: “Thưa thầy, chuyện này ngài đã biết từ lâu rồi, phải không?”

**Cerebras · GPT-OSS 120B · tuong_thuat_dia_danh**

Ngày hôm ấy, dưới chân núi Vân Trạch xuất hiện một lớp sương mù dày đặc, hai bên lối mòn phủ đầy những cây khô râm ran, gió thổi qua làm chúng rên rỉ âm u.

**Cerebras · GPT-OSS 120B · he_thong_thuat_ngu**

Bíp! Chúc mừng cư chủ đã đột phá tới tầng thứ chín của kỳ luyện khí, nhận được một bản công pháp “Phổ Thiên Kết”, xin kiểm tra kịp thời.

**Cerebras · GPT-OSS 120B · doi_thoai_nhieu_nhan_vat**

_Lần đầu (KHÔNG đạt: Còn sót 4 ký tự Hán chưa dịch trong bản dịch.):_ “Ngươi到底是誰？” cô gắt hỏi.  
“Ta？” anh cười lạnh, “Cô sẽ sớm biết được.”

_Sau khi sửa lỗi:_

“Ngươi thật ra là ai?” cô hỏi dữ dội.  
“Tao?” anh cười lạnh một tiếng, “Ngươi sẽ sớm biết được.”

**Groq · Qwen 3.6 27B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Dược Lão, hơi nhíu mày, khẽ nói: “Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?”

## Lỗi chất lượng đã xác nhận — KHÔNG được che giấu/chuẩn hoá

**1. Groq Qwen 3.6 27B dịch sai "师父" thành "Thư sư" thay vì "Sư phụ".**

Xác nhận **tái lập được lần thứ TƯ độc lập** (không phải nhiễu ngẫu nhiên):
- Lần 1 (trước khi gỡ GLM): *"...trầm giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*
- Lần 2 (sau khi gỡ GLM): *"...trầm giọng nói: "Thư sư, chuyện này ngài đã sớm biết rồi, phải không?""*
- Lần 3 (benchmark thật đầu tiên với Cerebras): *"...thấp giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*
- Lần 4 (benchmark sau khi thêm cơ chế tích vẹn/sửa lỗi, 2026-08-15): *"...khẽ nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*

"师父" (shī fù) là cách xưng hô đệ tử gọi sư phụ — bản dịch chuẩn Hán Việt phải là **"Sư phụ"**. Lỗi thật của Groq Qwen 3.6 27B — validator tính vẹn KHÔNG bắt được lỗi này theo đúng thiết kế (đây là lỗi NGỮ NGHĨA/từ vựng, không phải thiếu nội dung/còn sót tiếng Trung — nằm ngoài phạm vi validator).

**Đối chiếu: Cerebras GPT-OSS 120B dịch ĐÚNG cùng câu này** cả 2 lần benchmark thật ("Thưa sư phụ" / "Thưa thầy") — Cerebras nhất quán đúng hơn Groq ở điểm này.

**2. ĐÃ SỬA: Cerebras GPT-OSS 120B từng để sót nguyên văn tiếng Trung trong đoạn hội thoại nhiều nhân vật.**

Lần benchmark đầu tiên (trước khi có cơ chế tích vẹn), mẫu `doi_thoai_nhieu_nhan_vat` bị Cerebras để sót "到底是誰" chưa dịch. **Sau khi thêm `translation_integrity.kiem_tra_tinh_ven` + cơ chế sửa lỗi (repair retry)**, benchmark thật lần này (2026-08-15) xác nhận:
- Lần đầu: **vẫn tái lập đúng lỗi cũ** ("到底是誰" còn sót) — chứng minh đây không phải lỗi ngẫu nhiên đã tự hết.
- Cơ chế phát hiện lỗi (rule `han_residue`) kích hoạt đúng, gửi lại CÙNG đoạn cho Cerebras kèm chỉ dẫn sửa lỗi.
- Lần sửa lỗi: Cerebras trả về bản dịch tiếng Việt đầy đủ, không còn ký tự Hán nào — **ĐẠT tiêu chí thành công**.
- Tổng cộng đoạn này tốn 2 lần gọi model (1 lần đầu + 1 lần sửa lỗi) thay vì 1 — chi phí thêm CHỈ xảy ra khi thật sự cần.

**3. Ghi nhận mới: tên riêng "药老" không nhất quán giữa hai lần gọi Cerebras.**

Trong lần benchmark này, Cerebras dịch "药老" thành **"Yếu Lão"** (mẫu `hoi_thoai_xung_ho`) — khác với lần benchmark trước đó cùng mẫu này cho ra **"Dược Lão"** (cách phiên âm Hán Việt đúng, cũng là cách Groq luôn dùng). Đây là dấu hiệu Cerebras GPT-OSS 120B **không ổn định về tên riêng giữa các lần gọi khác nhau** — đáng cân nhắc nếu tên nhân vật cần nhất quán xuyên suốt một bộ truyện dài (glossary khoá theo `project.custom_instruction`/từ điển thuật ngữ đã có sẵn trong hệ thống có thể giảm thiểu vấn đề này, nhưng đáng theo dõi thêm).

**Ghi chú số token:** với cơ chế sửa lỗi mới, mẫu cần sửa lỗi (`doi_thoai_nhieu_nhan_vat`) tốn 463 token đầu vào/145 token đầu ra — cao hơn hẳn 3 mẫu còn lại (do gồm CẢ prompt gốc lẫn prompt sửa lỗi cộng dồn qua 2 lần gọi).