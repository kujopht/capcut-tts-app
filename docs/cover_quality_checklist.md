# Danh sách kiểm tra chất lượng ảnh bìa (thủ công)

Đây là bảng kiểm THỦ CÔNG dành cho MỘT NGƯỜI xem ảnh bìa thật (đã sinh ra
qua `server/cover_pipeline.py` / Beam RTX4090) và tự tay điền — **không**
có bất kỳ đoạn code nào tự động điền bảng này. Xem cấu trúc dữ liệu song
song ở `server/cover_quality_checklist.py::CoverQualityEvaluation` (cùng
đúng bộ trường, dùng khi cần lưu/kiểm tra bằng code, ví dụ lưu kèm một
job record).

Mission "Media AI Production Foundation" yêu cầu rõ: **không** xây "AI
visual judge" (giám khảo thị giác máy tính tự động) ở giai đoạn này — chỉ
một schema đánh giá thủ công.

## Thông tin ảnh

- Novel ID / Job ID: ______________________
- Provider đã dùng (vd `beam`): ______________________
- Prompt (chép nguyên văn hoặc link log): ______________________
- Ngày đánh giá: ______________________
- Người đánh giá: ______________________

## Bảng kiểm

| Hạng mục | Giá trị |
|---|---|
| Số nhân vật đếm được thực tế trên ảnh (`character_count`) | ____ |
| Nhân vật chính có nhận ra đúng danh tính không (`primary_identity_recognizable`) | [ ] Có / [ ] Không |
| Nhân vật phụ có nhận ra đúng danh tính không (`secondary_identity_recognizable`) | [ ] Có / [ ] Không |
| Có hiện tượng trộn lẫn đặc điểm giữa hai nhân vật không (`identity_blending_observed`) | [ ] Có / [ ] Không |
| Có người/khuôn mặt thừa xuất hiện ngoài ý muốn không (`duplicate_people_observed`) | [ ] Có / [ ] Không |
| Khuôn mặt các nhân vật chính có lộ rõ không (`faces_visible`) | [ ] Có / [ ] Không |
| Bố cục tổng thể có chấp nhận được không (`composition_acceptable`) | [ ] Có / [ ] Không |
| Có artifact giống chữ/glyph giả do model vẽ nhầm không (`text_artifact_observed`) | [ ] Có / [ ] Không |
| **Kết luận: ảnh này có dùng được cho sản xuất không** (`production_ready`) | [ ] Có / [ ] Không |

## Ghi chú tự do (`notes`)

______________________________________________________________
______________________________________________________________
______________________________________________________________

---

*Bảng này là công cụ đánh giá thủ công — không tự động hoá việc điền các
ô trên bằng bất kỳ phân tích ảnh/model thị giác nào. Xem
`server/cover_quality_checklist.py` cho phiên bản dataclass tương ứng
(dùng để lưu trữ/truy vấn bằng code sau khi con người đã điền xong).*
