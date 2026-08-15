# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt

CEREBRAS_API_KEY: THIẾU — model Cerebras bị bỏ qua
GROQ_API_KEY: có

| Model | Đoạn | Trạng thái | Độ trễ (s) | Token in/out |
|---|---|---|---|---|
| Cerebras · GPT-OSS 120B | hoi_thoai_xung_ho | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | tuong_thuat_dia_danh | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | he_thong_thuat_ngu | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | doi_thoai_nhieu_nhan_vat | skipped | — | None/None |
| Groq · Qwen 3.6 27B | hoi_thoai_xung_ho | ok | 0.45 | 262/35 |
| Groq · Qwen 3.6 27B | tuong_thuat_dia_danh | loi | 0.14 | None/None |
| Groq · Qwen 3.6 27B | he_thong_thuat_ngu | loi | 0.14 | None/None |
| Groq · Qwen 3.6 27B | doi_thoai_nhieu_nhan_vat | loi | 0.12 | None/None |

## Nội dung dịch (để đối chiếu chất lượng thủ công)

**Groq · Qwen 3.6 27B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Dược Lão, khẽ nhíu mày, trầm giọng nói: “Thư sư, chuyện này ngài đã sớm biết rồi, phải không?”

## Lỗi chất lượng đã xác nhận — KHÔNG được che giấu/chuẩn hoá

**Groq Qwen 3.6 27B dịch sai "师父" thành "Thư sư" thay vì "Sư phụ".**

Xác nhận **tái lập được** qua 2 lần chạy độc lập (không phải nhiễu ngẫu nhiên một lần):
- Lần 1 (2026-08-15, trước khi gỡ GLM): *"...trầm giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*
- Lần 2 (2026-08-15, sau khi gỡ GLM): *"...trầm giọng nói: "Thư sư, chuyện này ngài đã sớm biết rồi, phải không?""*

"师父" (shī fù) là cách xưng hô đệ tử gọi sư phụ trong tiên hiệp/huyền huyễn — bản dịch chuẩn Hán Việt phải là **"Sư phụ"**, không phải "Thư sư" (không có nghĩa trong tiếng Việt, có vẻ là một lỗi dịch âm/ghép chữ sai của model). Đây là lỗi thật của Groq Qwen 3.6 27B, không phải lỗi cấu hình phía Fanfic World — cần cân nhắc khi đánh giá Qwen làm nhà cung cấp dự phòng độc lập cho các đoạn có xưng hô sư đồ.