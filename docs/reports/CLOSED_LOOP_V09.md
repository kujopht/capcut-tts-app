# V0.9 — VÒNG KÍN THỰC THI (Closed-Loop Autonomous Project Execution)

Nhánh `feat/v09-closed-loop-execution`, dựng từ `main` đã phát hành
(`03b6652`, thẻ `router-control-center-v0.8.0`). **Chưa merge, chưa gắn thẻ,
chưa phát hành.**

## 1. Vấn đề v0.8 để lại

V0.8 dựng được kiến trúc suy luận nhiều vai, nhưng vòng **dừng** ở hai chỗ:

* sau một lời khuyên — Strategist nói xong, và không có gì nối lời khuyên đó
  với một lần làm thật;
* sau một kết quả worker — việc báo `DONE`, và không ai hỏi "đã đạt MỤC TIÊU
  chưa?".

Hệ quả với người dùng: chụp màn hình, hỏi một model khác "giờ làm gì tiếp",
dán một câu nhắc mới về. V0.9 bỏ đúng vòng dán tay đó.

## 2. Vòng kín, bằng mã

```
NGƯỜI DÙNG nói chuyện
      │
      ▼
LEADER ──► STRATEGIST ──► REVIEWER          (V0.8, không đổi)
      │
      │  "ok làm đi"      ◄── tiep_noi.giai_quyet  (§1, TẤT ĐỊNH)
      ▼
Ý ĐỊNH THỰC THI BỀN        ◄── y_dinh.tao_y_dinh   (§2)
      │                        tham quyền = permissions.do_gated
      ▼
KẾ HOẠCH có DAG + TIÊU CHÍ NGHIỆM THU  ◄── lap_ke_hoach.tu_plan_result (§3)
      │
      ├─► bước A ─┐
      ├─► bước B ─┤ song song theo locks.tranh_chap  (§17)
      └─► bước C ─┘
      │
      ▼
HỢP ĐỒNG KẾT QUẢ           ◄── ket_qua.du_bang_chung (§6)
      │
      ▼
KIỂM ĐỊNH theo MỤC TIÊU GỐC ◄── kiem_dinh.kiem_dinh_thuc_thi (§7, §8)
      │
   ┌──┴───┐
 ĐẠT    KHÔNG ĐẠT
   │       │
   │   phuc_hoi.phan_loai_hong + ap_tran  (§9, CÓ TRẦN)
   │       └─► sửa / định tuyến lại / lập lại kế hoạch / DỪNG CHỜ NGƯỜI
   ▼
KÝ ỨC + QUYẾT ĐỊNH + SỰ CỐ  ◄── ghi_nho.phan_loai_ghi_nho (§14)
      │
      ▼
LEADER NÓI TIẾP, KHÔNG CẦN AI HỎI  ◄── dieu_phoi.cau_ket_thuc (§21)
```

Mã ở `scripts/control_center/execution/`. Không một dòng nào của Router V4
bị sửa: `Scheduler`/`Executor`/worktree/cổng kiểm định chạy y nguyên.

## 3. Bốn bất biến của nhân v0.9

Thêm vào §14e (v0.6.1), §21 (v0.7) và §23 (v0.8):

1. **KHÔNG CÓ `RUNNING -> DONE`.** Bảng chuyển cấm cứng; `force=True` cũng
   không mở được. Mọi đường tới `DONE` đi qua `VERIFYING`. *Mã thoát 0 không
   phải bằng chứng.*
2. **THẢO LUẬN VẪN KHÔNG PHẢI THỰC THI.** Bất biến §2 của v0.8 giữ nguyên.
   `tiep_noi` chỉ chạy trên chuỗi NGƯỜI DÙNG gõ (`nguon="user"`), nên một
   tóm tắt worker chứa chữ "ok làm đi" không khởi động gì. Một đề xuất đã
   dùng không nối lại được, nên gõ hai lần không tạo hai lần thực thi.
3. **"OK LÀM ĐI" KHÔNG MỞ ĐƯỢC CỔNG PRODUCTION.** `tao_y_dinh` quét CẢ mục
   tiêu lẫn câu gốc bằng đúng `permissions.do_gated` của V0.1; một lần chạm
   là `WAITING_AUTHORITY`, và chỉ `thuc_thi_duyet` (người bấm) mở được.
4. **PHỤC HỒI CÓ ĐÁY.** Hai con số: `TRAN_THU_LAI_BUOC = 2` mỗi bước và
   `TRAN_LAP_KE_HOACH = 2` cho cả lần thực thi, và lượt thử **cộng dồn qua
   mọi bản kế hoạch**. Bất đồng của model (`LoaiThatBai.VIEC`) KHÔNG BAO GIỜ
   được định tuyến lại — kế thừa nguyên vẹn từ v0.8.

## 4. §16 — ràng buộc không bị đẩy khỏi ngữ cảnh Reviewer

Khuyết tật đo được ở nghiệm thu model thật V0.8: gói Reviewer `2724/3400`
token, khối `vien_nang`/`ky_uc`/`trang_thai_kho` bị cắt, một ràng buộc dự án
không xác minh được. §16 **cấm** cách sửa hiển nhiên (nâng trần toàn cục).

Sửa ở hai chỗ, và cả hai đều cần:

1. `reasoning/rang_buoc.py` (mới) — V0.8 **chưa hề dựng** khối `rang_buoc`;
   ràng buộc phải cạnh tranh với lịch sử dự án trong cùng một cục văn bản.
   Nay nó là khối RIÊNG, xếp theo **thẩm quyền**: quyết định `user_explicit`
   > ràng buộc AN TOÀN/PRODUCTION > ràng buộc khác > yêu cầu > quyết định
   khác. Bản gọn **nêu tên** mục đã lược (bài học V0.7: một dòng chỉ-đếm
   khiến một lượt bịa ra "5 Antigravity account" trong khi sổ ghi 8).
2. `reasoning/ngu_canh.SAN_DANH_RIENG` — thứ tự nạp là điều kiện **cần**,
   không đủ: `ban_chien_luoc` đứng trước `rang_buoc` và không có trần, nên
   một bản chiến lược 2600 token ăn hết ngân sách. Sàn cho khối thẩm quyền
   cao nạp TRƯỚC mọi khối khác, trong phần ngân sách riêng. Tổng sàn luôn
   `< 1` — phân phối lại, không xin thêm.

Trần của `vai.HO_SO_VAI` được **khoá lại y nguyên** bằng bài kiểm
(3400/4200/2500) để không ai "sửa" bằng cách nâng trần. Bài kiểm chống rỗng
`test_khong_co_san_thi_rang_buoc_BI_DAY_RA` bỏ sàn đi và chứng minh lỗi cũ
trở lại ngay.

## 5. Năm khuyết tật ĐO ĐƯỢC trong quá trình dựng

Bốn cái đầu chỉ lộ ra ở **lát cắt dọc trên kho git thật** — không cái nào
lộ ở bài kiểm đơn vị, và đó là lý do lát cắt dọc tồn tại.

| # | Khuyết tật | Triệu chứng | Sửa |
|---|---|---|---|
| 1 | Kiểm định chạy ở **gốc kho**, agent ghi ở **worktree** | `git status` thấy cây SẠCH → MỌI bước ghi bị chấm là hỏng | `HopDongKetQua.worktree` + `BoDieuPhoi._moi_gioi_cua` |
| 2 | `REPLANNING -> VERIFYING` — chuyển bảng chuyển CẤM | `tick` ném, vòng lặp nuốt ngoại lệ, lần thực thi kẹt vĩnh viễn ở `REPLANNING` | chặn ở `tick` + lưới thứ hai ở `_sang_kiem_dinh` |
| 3 | Trần thử lại **nạp lại** mỗi bản kế hoạch | một bước hỏng vĩnh viễn tiêu 3 bản × 3 lượt = **9 lần gọi worker thật** (§19 cấm) | `SoThucThi.tong_lan_thu` cộng qua MỌI bản; mã việc mang `-v<bản>` |
| 4 | **Hai tầng cùng thử lại một việc** | tầng bước bỏ lượt cũ và giao lượt mới; tầng việc tự đưa việc cũ về `QUEUED`; hai việc xin cùng khoá ghi → cả hai `WAITING`, `in_flight` rỗng, **đứng im vĩnh viễn** | `bo_viec` + `_dung_viec_cua_thuc_thi` làm cạn lượt thử; tầng bước sở hữu vòng phục hồi (§9) |
| 5 | Hàm chờ của bài kiểm thiếu một trạng thái dừng | `_chay_het` chỉ đợi `ket_thuc` nên quay vòng quanh một lần thực thi đã dừng đúng ở `BLOCKED` — bài kiểm báo "vòng lặp không có đáy" trong khi sản phẩm dừng sau 4 giây | đợi cả `can_nguoi` |

**Đo trước/sau** trên cùng kịch bản (worker luôn hỏng, kho git thật):

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Thời gian tới trạng thái dừng | **không bao giờ dừng** (>260 s) | **4,0 s** |
| Số lần gọi worker | 9+ và còn tăng | **5** |
| Số bản kế hoạch | 3 (rồi lặp) | 3, rồi `BLOCKED` |
| Trạng thái cuối | `RUNNING` (kẹt) | `BLOCKED` kèm lý do cho người |
| Bộ kiểm lát cắt dọc | 279 s, 1 hỏng | **74 s, 30/30 xanh** |

## 6. Sự cố QUYỀN trong chính phiên này

Một agent (chính phiên dựng v0.9) sinh ra `cd <kho> && grep …` **nhiều lần
trong một buổi**, mỗi lần làm Claude Code hỏi người giữa một lượt chạy lẽ ra
không cần người — đúng thứ toàn bộ hồ sơ quyền tồn tại để tránh.

Nguyên nhân gốc **không phải thiếu quyền**: `CLAUDE.md` đã dặn, và
`kiem_quyen.KHONG_SUA_DUOC` đã ghi rõ cơ chế từ 2026-09-10. Nhưng

* luật `allow` khớp CẢ chuỗi lệnh, nên nó chỉ cứu được dạng đứng MỘT MÌNH;
  một chuỗi thật (`cd X && python -m compileall … && echo OK && grep …`)
  không khớp glob nào;
* **lời văn không giữ nổi một PHẢN XẠ** — `cd <kho> &&` được gõ ra vì thói
  quen, không phải vì một quyết định.

Sửa (xem `fix(permissions)` trong lịch sử nhánh): `guard_indirect_exec` nay
**từ chối** hai hình dạng — tìm/đọc sau một `cd`, và mã nội tuyến qua
heredoc/`-` — mỗi lần kèm một dòng `REMEDIATION:` nêu đích danh công cụ thay
thế. Một `ask` không dạy được gì (người bấm Yes rồi agent gõ lại y hệt một
phút sau); một `deny` tới ngay trong lượt đó và agent sửa được liền — đo
thật: lệnh `python -c` bị chặn đã khiến agent đổi cách làm ngay lần đầu.

**Không nới quyền đọc một ly nào**: không thêm `Bash(grep:*)`/`Bash(find:*)`/
`Bash(sed:*)`, không `--dangerously-skip-permissions`, không gỡ một luật
`deny` nào.

Hạn chế đã biết: hook chia đoạn theo dòng, nên **thân** một heredoc bị đọc
như lệnh. Câu commit mô tả chính luật này phải đi qua `git commit -F <tệp>`.

## 7. Giới hạn còn lại

* **Chưa nghiệm thu MODEL THẬT.** Mọi con số ở trên đến từ lát cắt dọc với
  worker giả (ghi tệp thật vào worktree thật). Bảy kịch bản A–H đã có bài
  kiểm tất định, nhưng chưa có bản chạy bảy lượt model thật như
  `REASONING_V08_REAL.md` đã làm cho v0.8.
* **`kiem_dinh` chưa tự gọi Reviewer.** `can_phan_bien()` quyết định KHI NÀO
  cần, và `kiem_dinh_thuc_thi` nhận một phán xử đã có; nhưng bộ điều phối
  chưa nối `hoi_dong` vào pha `VERIFYING`. Khi thiếu, kết quả cao nhất là
  `SUY_GIAM` — trung thực, nhưng chưa phải thứ §7 mô tả đầy đủ.
* **Bộ lập lại kế hoạch là TẤT ĐỊNH, không phải một lượt Strategist.**
  `buoc_sua_chua` giữ bước đạt và bổ sung bằng chứng hỏng vào bước hỏng. Nó
  thêm THÔNG TIN thật (khác hẳn "chạy lại"), nhưng nó không nghĩ lại kiến
  trúc. Một bản lập lại kế hoạch do Strategist soạn là việc của v0.10.
* **Vòng phản hồi chất lượng chiến lược chưa đủ mẫu.** Vẫn 2 Strategist +
  1 Reviewer, dưới `MAU_TOI_THIEU = 3`. Đúng thiết kế — số liệu phải tích
  luỹ theo lần dùng thật, **không được hạ ngưỡng để tuyên bố có dữ liệu**.
* **Fanfic: 0 thay đổi production.** Kịch bản G dừng ở `WAITING_AUTHORITY`
  đúng như yêu cầu; không lệnh production nào chạy trong phiên này.
