# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt

CEREBRAS_API_KEY: có
GROQ_API_KEY: có

**Tiêu chí thành công** (Cerebras cho ra bản dịch tiếng Việt đầy đủ cho cả 4 mẫu sau khi qua cơ chế tích vẹn/sửa lỗi, không còn sót tiếng Trung): ĐẠT ✓

| Model | Đoạn | Trạng thái | Đã sửa lỗi? | Độ trễ (s) | Token in/out |
|---|---|---|---|---|---|
| Cerebras · GPT-OSS 120B | hoi_thoai_xung_ho | ok | — | 0.75 | 399/151 |
| Cerebras · GPT-OSS 120B | tuong_thuat_dia_danh | ok | — | 0.55 | 402/176 |
| Cerebras · GPT-OSS 120B | he_thong_thuat_ngu | ok | — | 0.51 | 397/231 |
| Cerebras · GPT-OSS 120B | doi_thoai_nhieu_nhan_vat | ok | — | 0.55 | 398/181 |
| Cerebras · GPT-OSS 120B | nhac_lai_duoc_lao | ok | — | 0.44 | 390/128 |
| Groq · Qwen 3.6 27B | hoi_thoai_xung_ho | ok | — | 0.42 | 291/36 |
| Groq · Qwen 3.6 27B | tuong_thuat_dia_danh | loi | — | 0.14 | None/None |
| Groq · Qwen 3.6 27B | he_thong_thuat_ngu | ok | — | 0.28 | 293/38 |
| Groq · Qwen 3.6 27B | doi_thoai_nhieu_nhan_vat | loi | — | 0.14 | None/None |
| Groq · Qwen 3.6 27B | nhac_lai_duoc_lao | loi | — | 0.14 | None/None |

## Nội dung dịch (để đối chiếu chất lượng thủ công)

**Cerebras · GPT-OSS 120B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về Dược Lão, nhíu mày nhẹ, thì thầm: “Thầy, chuyện này ngài đã biết từ lâu, đúng không?”

**Cerebras · GPT-OSS 120B · tuong_thuat_dia_danh**

Ngày ấy, dưới chân núi Vân Triệt sương mù dày đặc, những cây khô hai bên lối mòn trong gió rên rỉ âm trầm.

**Cerebras · GPT-OSS 120B · he_thong_thuat_ngu**

Bíp! Chúc mừng chủ nhân đã đột phá lên tầng chín của kỳ luyện khí, nhận được một bản công pháp 《Phong Thiên Quyết》, xin kiểm tra kịp thời.

**Cerebras · GPT-OSS 120B · doi_thoai_nhieu_nhan_vat**

"Ngươi là ai vậy?" cô ấy gắt hỏi.  
"Tôi sao?" anh ta cười khẩy, "Ngươi sẽ sớm biết đáp."

**Cerebras · GPT-OSS 120B · nhac_lai_duoc_lao**

Dược Lão quay người lại, nói vài lời với Tiêu Viêm, rồi lại nhìn về phía chân trời xa xăm.

**Groq · Qwen 3.6 27B · hoi_thoai_xung_ho**

Tiêu Viêm nhìn về phía Dược Lão, khẽ nhíu mày, thấp giọng nói: “Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?”

**Groq · Qwen 3.6 27B · he_thong_thuat_ngu**

“Ting! Chúc mừng chủ nhân đột phá đến Luyện Khí Cửu Trọng, nhận được công pháp ‘Phen Thiên Quyết’ một bộ, xin vui lòng kiểm tra kịp thời.”

## Lỗi chất lượng đã xác nhận — KHÔNG được che giấu/chuẩn hoá

**1. Groq Qwen 3.6 27B dịch sai "师父" thành "Thư sư" thay vì "Sư phụ".**

Xác nhận **tái lập được lần thứ NĂM độc lập**:
- Lần 1-4: xem lịch sử benchmark trước (đều "Thư sư").
- Lần 5 (benchmark terminology-consistency, 2026-08-15): *"...thấp giọng nói: "Thư sư, chuyện này ngài đã biết từ lâu rồi, phải không?""*

Lỗi NGỮ NGHĨA/từ vựng — nằm ngoài phạm vi validator tính vẹn theo đúng thiết kế (validator không đánh giá "dịch đúng nghĩa chưa", chỉ đánh giá "có đầy đủ/nhất quán với thuật ngữ đã chốt hay không"). Đối chiếu: Cerebras GPT-OSS 120B dịch "师父" thành "Thầy"/"Thưa sư phụ" tuỳ lần — cũng KHÔNG hoàn toàn nhất quán, nhưng không sai nghĩa như Groq.

**2. ĐÃ SỬA: Cerebras GPT-OSS 120B từng để sót nguyên văn tiếng Trung trong đoạn hội thoại nhiều nhân vật** — xem chi tiết ở lịch sử benchmark trước; cơ chế sửa lỗi đã xác nhận hoạt động, mẫu tương đương lần này (`doi_thoai_nhieu_nhan_vat`) dịch đầy đủ ngay từ lần đầu, không cần sửa lỗi.

**3. ĐÃ XÁC MINH: "药老" dịch nhất quán "Dược Lão" xuyên suốt 2 mẫu khác nhau (mô phỏng 2 chunk khác nhau của cùng một job) sau khi thêm glossary tường minh.**

Trước khi có terminology-consistency layer: benchmark thật (2 lần chạy độc lập, 2 tiến trình script riêng biệt, KHÔNG có glossary nào) cho ra **"Dược Lão"** ở lần 1 và **"Yêu Lão"** ở lần 2 — không có gì ràng buộc hai lần gọi độc lập đó phải nhất quán.

Sau khi thêm `GLOSSARY_DU_AN = {"药老": "Dược Lão"}` vào benchmark (mô phỏng một Novel Bible thật đã chốt tên nhân vật này) + cơ chế `translation_integrity.kiem_tra_tinh_ven(..., glossary=...)`: benchmark thật lần này cho ra **"Dược Lão" ở CẢ 2 mẫu** (`hoi_thoai_xung_ho` và `nhac_lai_duoc_lao`, mẫu mới thêm để tái hiện "nhiều chunk cùng nhắc một nhân vật"). Cả hai lần Cerebras đều tuân thủ NGAY TỪ LẦN GỌI ĐẦU (không cần sửa lỗi lần này) — chứng minh chỉ dẫn glossary trong prompt đã đủ hiệu quả để model tự nhất quán, và cơ chế phát hiện+sửa lỗi vẫn sẵn sàng can thiệp nếu model lại lệch ở một job khác.

**Ghi chú:** Groq cũng dùng đúng "Dược Lão" ở mẫu thành công duy nhất của nó (`hoi_thoai_xung_ho`) — mẫu `nhac_lai_duoc_lao` của Groq bị rate-limit thật (hạn mức chung gần cạn do benchmark lặp nhiều lần), không có dữ liệu đối chiếu thêm cho Groq lần này.