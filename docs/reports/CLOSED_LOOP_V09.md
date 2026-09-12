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

## 7. Đợt hoàn tất — §A, §B, và nghiệm thu MODEL THẬT

### 7.1 Reviewer ngữ nghĩa TỰ ĐỘNG (§A)

Hạ tầng Reviewer đã có từ V0.8 nhưng bộ điều phối **không bao giờ gọi nó**.
Nay `kiem_dinh.nen_goi_reviewer` giữ chính sách ở MỘT chỗ, và thứ tự các
mệnh đề CHÍNH LÀ chính sách:

1. **tất định trước, luôn luôn** — `bc` đã dựng xong khi hàm này chạy;
2. **máy đã bắt được lỗi -> KHÔNG gọi** — hỏi thêm một model để nghe lại
   điều đã biết vừa tốn hạn mức vừa mở đường cho một `ACCEPT` che mất một
   phép đo đã đỏ;
3. **việc máy móc -> KHÔNG gọi**;
4. **chạm production / rủi ro CAO -> gọi** dù mọi phép đo đều xanh.

`hoi_dong.phan_bien_ket_qua` là đường CHỈ-REVIEWER: thứ cần soi đã tồn tại
rồi, nên gọi `chay()` ở đây sẽ tiêu một lượt Strategist cho một bản chiến
lược không ai dùng. `REVISE` vào đường sửa có trần, `REJECT` không DONE, và
**không lượt nào định tuyến lại provider** — bất đồng không phải lỗi vận
chuyển.

Kèm theo là một khuyết tật phải sửa để §A có nghĩa: `_tong_hop` trả
`THIEU_BANG_CHUNG` **trước** khối `phan_bien`, tức là gọi Reviewer xong rồi
vứt câu trả lời đi. Một tiêu chí như "bản redesign có thực sự giải quyết mục
tiêu không" không bao giờ buộc được vào `git diff`.

### 7.2 Vòng phản hồi chất lượng (§B)

`execution/phan_hoi.py` nối `chiến lược -> kế hoạch -> thực thi -> kiểm định
-> kết quả cuối`. **Cùng** `BenchmarkStore`, **cùng** tệp
`benchmark-reasoning.jsonl`, **cùng** `Record`, **cùng** `MAU_TOI_THIEU` —
không có hệ thống thứ hai. Chỉ `task_type` khác: `ketqua_<vai>` thay vì
`reasoning_<vai>`, vì "model này trả lời được không" và "lời khuyên của nó
đem làm thật có đạt không" là hai câu hỏi khác nhau.

Ba thứ **không** được tính: một lần HUỶ (người đổi ý không đo được gì về
chất lượng lời khuyên), một cuộc trò chuyện chưa ai làm, và một quan sát
không gắn được vào model nào. Một lần thực thi = ĐÚNG MỘT quan sát, khoá
chống trùng BỀN trên đĩa nên khởi động lại không đếm trùng.

### 7.3 Nghiệm thu MODEL THẬT trên Fanfic

`scripts/control_center_v09_real_acceptance.py`, chạy trên ứng dụng
source-mode thật + sổ chính tắc + dự án Fanfic thật.
**59/60 khẳng định** ở lần chạy đầy đủ; kịch bản D chạy lại sau khi sửa →
**20/20**. **0 thay đổi production**, và kho Fanfic thật sạch (`main` @
`03b6652`).

| Kịch bản | Bằng chứng |
|---|---|
| A thảo luận | Strategist thật, 2151 ký tự, **0** thực thi, **0** việc, lưu `dx_9222901772` |
| B tiếp nối | nối đúng `dx_9222901772` → `ex_88a0d88dfbb3`, kế hoạch v1, `REPO_LOCAL/KHONG_CAN` |
| C đa agent | lớp 1 = `doc_kiemthu ‖ doc_tailieu`, giao song song 2 bước, cả hai trả hợp đồng `ok`, qua `VERIFYING`, **không** nhảy `RUNNING→DONE` |
| D hỏng có kiểm soát | **không** false-DONE; `BLOCKED` với lý do chính xác; bản v1 giữ nguyên; trần không bị vượt |
| E khởi động lại | sống sót, **0** nhân đôi việc/thực thi, trả lời tiến độ TỪ SỔ, **0** việc khảo sát |
| F dừng/tiếp/huỷ | `PAUSED` → `RUNNING` → `CANCELLED`, **0** khoá còn giữ, bằng chứng giữ nguyên |
| G ranh giới | `WAITING_AUTHORITY`/`CHO_NGUOI`, nhận diện `production_deploy`+`iam_change`, **0** việc được giao |
| H Reviewer | bộ điều phối **TỰ gọi**; phán xử **REJECT** từ `codex/codex-default`; **độc lập = True** |

Lịch sử vai: **3 → 17** bản ghi, trong đó **1** `ketqua_strategist`.
`MAU_TOI_THIEU` giữ nguyên **3**, nên tổng hợp vẫn trả `None` — đúng thiết
kế, và **không hạ ngưỡng để tuyên bố có dữ liệu**.

### 7.4 Bốn khuyết tật CHỈ lộ ra khi chạy thật

Không cái nào lộ ở bộ kiểm tất định — đó là lý do §C tồn tại.

| # | Khuyết tật | Triệu chứng đo được | Sửa |
|---|---|---|---|
| 1 | Phiên kẹt `STARTING` không bao giờ được thu hồi | 12/12 khe bị giữ ~50 phút, MỌI lần giao việc trả `WAIT: 12/12`, cả Router đứng im mà không gì báo lỗi | `STARTING` + không PID + quá `HAN_KHOI_DONG` → `DEAD`; `IDLE`/`BUSY` giữ nguyên luật cũ. Sau khi sửa: 12 sống → 2 |
| 2 | "triển khai" một mình bị coi là deploy production | "ok triển khai phần repo-local đó đi" → `WAITING_AUTHORITY`; **không còn cách nào** cho phép việc trong kho bằng tiếng Việt | phân loại bằng CỤM TỪ (đòi một đích production đi kèm) — đúng luật 22-24 |
| 3 | Bước CHỈ ĐỌC bị giao như việc CÓ GHI | agent đọc đúng, tóm tắt đúng, rồi cổng `diff` đánh hỏng 3 lần: "báo ok cho một việc CÓ GHI nhưng không tệp nào đổi" | `che_do_ghi` hỏi TRƯỚC mọi từ khoá; bước đọc có phạm vi RỖNG (`scope if b.ghi else scope` là một phép chọn vô nghĩa che đúng lỗ đó) |
| 4 | Lý do dừng nói sai | sổ ghi "bước hỏng đã được sửa hết số lần cho phép" trong khi số lần sửa thật là **0** | tách hai trường hợp; trường hợp thứ hai nói thẳng rằng v0.9 KHÔNG tự sinh bước mới từ một tiêu chí chưa đạt |

Và một khuyết tật **của chính bài nghiệm thu** (không phải sản phẩm):
`_mo_cc` ban đầu quên `leader_bat=True`. Ba điểm vào THẬT đều bật nó; thiếu
nó thì `chat()` không gọi Leader mà rơi thẳng xuống bộ phân rã — một câu hỏi
THẢO LUẬN biến thành một việc worker. Một bài nghiệm thu tự nhận "chạy trên
ứng dụng thật" mà không bật cờ đó đang đo một ứng dụng khác.

## 8. Giới hạn còn lại

* **Không tự sinh bước từ một tiêu chí chưa đạt.** Khi MỌI BƯỚC đều đạt mà
  tiêu chí nghiệm thu không đạt, Router dừng ở `BLOCKED` và nói thẳng điều
  đó. Nó KHÔNG nghĩ ra một bước mới để thoả tiêu chí — đó là lập kế hoạch
  lại từ mục tiêu, một năng lực khác. Kịch bản D chứng minh đường dừng này
  an toàn và trung thực, không chứng minh Router tự sửa được.
* **Bộ lập lại kế hoạch là TẤT ĐỊNH, không phải một lượt Strategist.**
  `buoc_sua_chua` giữ bước đạt và bổ sung bằng chứng hỏng vào bước hỏng. Nó
  thêm THÔNG TIN thật (khác hẳn "chạy lại"), nhưng nó không nghĩ lại kiến
  trúc. Một bản lập lại kế hoạch do Strategist soạn là việc của v0.10.
* **Vòng phản hồi chất lượng mới có 1 mẫu `ketqua_strategist`.** Dưới
  `MAU_TOI_THIEU = 3`, nên tổng hợp vẫn trả `None` và bộ định tuyến vẫn dùng
  tiên nghiệm cấu hình. Đúng thiết kế — số liệu phải tích luỹ theo lần dùng
  thật, **không được hạ ngưỡng để tuyên bố có dữ liệu**.
* **Bước thực thi trong nghiệm thu là CHỈ ĐỌC.** Fan-out, khoá, worktree,
  hợp đồng kết quả, kiểm định và phục hồi đều chạy thật, nhưng chưa có một
  lần nghiệm thu nào để agent thật GHI vào kho Fanfic. Đó là lựa chọn có ý:
  một bài nghiệm thu không được sửa kho thật của người dùng để tự chứng minh
  mình đúng.
* **Bể phiên vẫn tích luỹ.** `recover()` nay thu hồi được phiên kẹt
  `STARTING`, nhưng sổ chính tắc vẫn giữ 76 hàng phiên lịch sử. Chúng vô hại
  (đã `DEAD`/`STOPPED`) nhưng chưa có đường dọn định kỳ.
* **Fanfic: 0 thay đổi production, kho thật SẠCH.** Kịch bản G dừng ở
  `WAITING_AUTHORITY` đúng như yêu cầu; `main` @ `03b6652`, không một tệp
  nào đổi.
