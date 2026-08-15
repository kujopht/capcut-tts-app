# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt

CEREBRAS_API_KEY: THIẾU — model Cerebras bị bỏ qua
GROQ_API_KEY: có

| Model | Đoạn | Trạng thái | Độ trễ (s) | Token in/out |
|---|---|---|---|---|
| Cerebras · GLM 4.7 | hoi_thoai_xung_ho | skipped | — | None/None |
| Cerebras · GLM 4.7 | tuong_thuat_dia_danh | skipped | — | None/None |
| Cerebras · GLM 4.7 | he_thong_thuat_ngu | skipped | — | None/None |
| Cerebras · GLM 4.7 | doi_thoai_nhieu_nhan_vat | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | hoi_thoai_xung_ho | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | tuong_thuat_dia_danh | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | he_thong_thuat_ngu | skipped | — | None/None |
| Cerebras · GPT-OSS 120B | doi_thoai_nhieu_nhan_vat | skipped | — | None/None |
| Groq · Qwen 3.6 27B | hoi_thoai_xung_ho | ok | 0.38 | 262/36 |
| Groq · Qwen 3.6 27B | tuong_thuat_dia_danh | ok | 0.30 | 265/42 |
| Groq · Qwen 3.6 27B | he_thong_thuat_ngu | ok | 0.28 | 264/38 |
| Groq · Qwen 3.6 27B | doi_thoai_nhieu_nhan_vat | loi | 0.12 | None/None |

## Nội dung dịch (để đối chiếu chất lượng thủ công)

**Groq · Qwen 3.6 27B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Dược Lão, khẽ nhíu mày, trầm giọng nói: “Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?”

**Groq · Qwen 3.6 27B · tuong_thuat_dia_danh**

Một ngày nọ, dưới chân Vân Xích Sơn nổi lên một trận sương mù dày đặc, những cây khô héo hai bên đường núi phát ra tiếng gào thét trầm thấp trong gió.

**Groq · Qwen 3.6 27B · he_thong_thuat_ngu**

“Ting! Chúc mừng chủ nhân đột phá đến Luyện Khí Cửu Tầng, nhận được công pháp ‘Thiên Sơn Quyết’ một bộ, xin vui lòng kiểm tra kịp thời.”