"""VÒNG KÍN THỰC THI — V0.9.

V0.8 dựng được kiến trúc suy luận (Leader -> Strategist -> Reviewer), nhưng
vòng DỪNG lại ngay sau lời khuyên, hoặc ngay sau khi một worker trả kết quả.
Người dùng phải tự chụp màn hình, tự hỏi một model khác "giờ làm gì tiếp",
rồi dán một câu nhắc mới về. Gói này đóng nốt vòng đó:

    thảo luận -> Ý ĐỊNH THỰC THI được duyệt -> KẾ HOẠCH có DAG
      -> việc cho Router V4 -> KẾT QUẢ có hợp đồng -> KIỂM ĐỊNH
      -> (đạt) ký ức/quyết định/sự cố   |   (hỏng) lập lại kế hoạch CÓ TRẦN
      -> Leader NÓI TIẾP trong cùng hội thoại

BỐN ĐIỀU GÓI NÀY KHÔNG LÀM, và không được ai làm hộ:

1. **KHÔNG biến một lời khuyên thành một việc.** Bất biến §2 của v0.8 giữ
   nguyên: chỉ câu NGƯỜI DÙNG xin làm mới mở cửa thực thi. `tiep_noi.py`
   nối "ok làm đi" về đúng đề xuất trước đó — nó KHÔNG tự khởi động gì.
2. **KHÔNG nới rào quyền.** Ranh giới production/ngoài đi qua đúng
   `permissions.do_gated` mà V0.1 đã dựng, và một lần chạm là
   `WAITING_AUTHORITY`, không phải một lần hỏi thêm.
3. **KHÔNG cho `RUNNING -> DONE`.** Máy trạng thái cấm cứng: mọi đường tới
   `DONE` đi qua `VERIFYING`. Mã thoát 0 không phải bằng chứng.
4. **KHÔNG lưu dòng suy nghĩ.** Sổ giữ quyết định, tóm tắt lý do, THAM
   CHIẾU bằng chứng và trạng thái — không giữ vết suy luận thô.
"""
