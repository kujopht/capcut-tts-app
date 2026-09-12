# V0.9 — MẶT HỎNG THẬT CỦA "THỰC THI ĐẦU-CUỐI TRÊN AGENT HEADLESS"

> Trạng thái: **CHƯA PHÁT HÀNH.** Không merge, không gắn thẻ, không đóng băng.
> Nhánh `feat/v09-closed-loop-execution`. Kho Fanfic không bị chạm vào `main`.

## Câu hỏi được đặt ra

> "Trở ngại không còn là thiết kế vòng kín. Trở ngại là thực thi đầu-cuối LẶP
> LẠI ĐƯỢC trên agent headless thật. Tôi KHÔNG muốn cách 'chạy lại tới khi
> xanh'. Tôi muốn giảm hoặc loại bỏ phụ thuộc vào nhà cung cấp / runtime."

## Kết luận ngắn

**Không có phụ thuộc nhà cung cấp nào để loại bỏ.** Đếm trên sổ chính tắc:
trong 11 việc GHI thật đã chạy, **0 việc hỏng vì nhà cung cấp**. Agent viết
đúng tệp, đúng phạm vi, đúng dấu xác nhận — gần như mọi lần. Thứ hỏng là bốn
khuyết tật trong mã của CHÍNH Router, và cả bốn cùng một hình dạng:

> **hai cái nhìn về CÙNG một sự thật, nói ngược nhau, và tầng trên tin cái sai.**

Báo cáo trước của tôi quy cho "may rủi theo nhà cung cấp". Đó là một kết luận
SAI, và nó sai được chính vì khuyết tật số 2 dưới đây đã nguỵ trang lỗi sức
chứa thành lỗi provider.

## PHẦN A — MẶT HỎNG, ĐO ĐƯỢC

### A.1 Kiểm đếm mọi việc GHI thật đã chạy

| Chế độ | Số | Tầng | Nguyên nhân |
|---|---|---|---|
| **A** — cổng `diff` đánh hỏng một lần ghi ĐÚNG | 9/11 | Router | lệch tên trường (A.2) |
| **D** — chưa từng được giao cho phiên nào | 2/11 | Router | bế khoá khe phiên (A.3) |
| **B** — phong bì bị cắt ngang | **0** | — | KHÔNG TỒN TẠI (A.6) |
| **C** — lượt agent thật sự trả về rỗng | **0** | — | không quan sát được lần nào |

Bằng chứng phụ: tệp đích nằm trên đĩa với ĐÚNG chuỗi xác nhận trong **32**
worktree (`_v09_ghi_chu_kiemthu.md`) và **28** worktree
(`_v09_ghi_chu_handoff.md`). Agent làm đúng việc của nó.

### A.2 Khuyết tật 1 — cổng chấm worker trên một trường ta không bao giờ xin

* Lời nhắc gửi worker (`control_center/planner.py`) **BẮT BUỘC**:
  «liệt kê ĐƯỜNG DẪN của TỪNG tệp bạn đã tạo hoặc sửa vào trường `changes`».
* Bộ phân tích (`router_v3/packet.py::parse_result`) chỉ đọc `files_changed`.

Worker làm đúng — mọi phong bì thô đều có
`"changes": ["docs/reports/….md"]` — nhưng `kq.files_changed` vẫn RỖNG, nên
`cong_diff` kết luận *"worker không khai sửa gì nhưng đĩa đổi"*. **Mọi** việc
ghi hỏng một cách TẤT ĐỊNH. Không phải may rủi.

`envelope.py` đã nhận cả hai tên từ trước (`d.get("changes") or
d.get("files_changed")`); chỉ đường V3 còn lệch.

**Sửa:** `parse_result` nhận `changes` như BÍ DANH của `files_changed` (gộp cả
hai, khử trùng), và lược đồ JSON trong gói việc liệt kê cả hai tên để lược đồ
và lời nhắc không còn nói hai thứ khác nhau.

### A.3 Khuyết tật 2 — trần khe phiên biến thành BẾ KHOÁ

`sessions.py` có ba luật, và hai trong số đó đọc cùng một phiên ngược nhau:

* **Luật 2** từ chối dùng lại một phiên RẢNH (nguội quá ngưỡng, hoặc phạm vi
  ghi không chứa được phạm vi việc mới).
* **Luật 3** vẫn ĐẾM đúng phiên đó vào `len(phien)`, chạm trần, rồi **chờ nó**.

Nhưng một phiên RẢNH không bao giờ "xong việc" để nhả khe — chỉ phiên BẬN mới
làm được thế. Nên cái chờ đó là vĩnh viễn. Và vì mỗi bước GHI có phạm vi
riêng, không bước nào dùng lại được phiên của bước khác: mỗi lần thử đẻ một
phiên mới cho tới khi chạm trần, rồi **mọi** lần giao việc sau đó trả về
`WAIT: đã có 12/12 phiên sống`.

Hai nguồn rò nuôi cái trần đó:

* **Rò khi giao hỏng.** `_giao_khong_luoi` dựng phiên ở bước (2); bước (3)
  (hết lease runtime) và bước (4) (việc bị vòng khác nhận trước) `return` mà
  chỉ trả KHOÁ và LEASE. Phiên vừa dựng ở lại sổ mãi ở `STARTING`, và
  `SessionState.STARTING.alive` là `True`. **Đo được: 8 phiên rò trong MỘT
  lần chạy.**
* **Nhãn việc chết.** Ba phiên `IDLE` nguội hơn **bốn tiếng** vẫn mang
  `current_task` trỏ tới việc đã `FAILED` từ lâu; `recover()` chỉ dọn
  `current_task` cho phiên `BUSY` nên cái nhãn đó ở lại mãi.

**Sửa:** luật 2b thu hồi khe của phiên RẢNH mà luật 2 vừa từ chối (nguội
trước, rồi LRU) và của phiên `STARTING` không PID đã quá hạn khởi động — vừa
đủ một khe, không dọn sạch bể; `_nha_phien_moi` trả lại phiên vừa dựng khi lần
giao hỏng; `_dang_giu_viec` lấy **trạng thái việc** (`TaskState.active`) làm
nguồn thẩm quyền thay vì cái nhãn phiên còn nhớ, và FAIL CLOSED khi không tra
cứu được. Không bao giờ đụng phiên `BUSY` hay phiên đang giữ việc sống, và
không xoá worktree (chỉ đánh dấu).

### A.4 Khuyết tật 3 — lỗi SỨC CHỨA bị khai là lỗi NHÀ CUNG CẤP

`HopDongKetQua.rong` không phân biệt được hai chuyện rất khác nhau:

1. agent đã chạy thật và trả về rỗng → chuyện của nhà cung cấp;
2. **chưa hề có agent nào được giao việc** → chuyện của sức chứa.

Cả hai rơi vào `LoaiThatBai.RUNTIME` → `LoaiHong.PROVIDER`. Nên một lần chạy
bị bế khoá ở A.3 — **không gọi provider lần nào** — vẫn được báo cáo là
"provider hỏng". Đây là cơ chế đã làm cả một vòng chẩn đoán (và báo cáo trước
của tôi) đi sai hướng.

**Sửa:** `HopDongKetQua.chua_chay` đọc dấu vết ĐỊNH TUYẾN
(`provider`/`model`/`runtime_id`/`duration`/`exit_code`) — sạch cả năm nghĩa là
không có lượt nào. Loại riêng `LoaiHong.CHUA_GIAO`, hành động `THU_LAI` và
**không bao giờ** `DINH_TUYEN_LAI`: đổi nhà cung cấp không tạo thêm khe.

### A.5 Khuyết tật 4 — đối soát chữa trạng thái VIỆC mà không chữa PHONG BÌ

`_doi_soat_khai_thieu` đối soát lời khai thiếu với `git` thật rồi trả `True`,
và bên gọi nâng **trạng thái việc** lên `DONE`. Nhưng phong bì vẫn mang
`status="failed"` + `failure_reason="gate_diff"`. `HopDongKetQua` dựng từ
phong bì nên **tầng BƯỚC** đọc phải cái sai, kết luận bước HỎNG, và đi sửa
chữa một việc vừa `DONE`.

Đo được trên `ex_ca0dc426af20`: bước `ghi_tailieu` **đạt đối soát ba lần liên
tiếp**, ba lần `RUNNING -> DONE`, và cả ba lần tầng bước vẫn xếp `KHÔNG_ĐẠT`
→ sửa chữa → lập lại kế hoạch → `BLOCKED`. Tệp đã nằm trên đĩa với đúng dấu
xác nhận **từ lần đầu**. Sổ còn in `"việc hỏng; phiên giữ ấm"` ngay dưới một
dòng `TASK_FINISHED DONE`.

**Sửa:** khi đối soát ĐẠT, phong bì cũng phải nói xong (`status="ok"`,
`failure_reason=""`); khi TỪ CHỐI thì không được đụng vào. Và sự kiện vòng đời
phiên lấy kết luận cuối (`moi`) thay vì `kq.ok`.

### A.6 Chế độ B ("phong bì bị cắt") KHÔNG tồn tại

Tôi từng đọc các nhật ký thô ~450 byte kết thúc giữa chừng
(`Unterminated string`) như bằng chứng phản hồi bị đứt. Sai: đó là
`raw_excerpt`, và `parse_result` của V3 **cắt nó còn 400 ký tự CÓ CHỦ ĐÍCH** —
`executor.py` đã ghi rõ điều này từ 2026-09-03 và cố ý không đọc lại chuỗi đó
để suy ra trạng thái. Phong bì đầy đủ nằm trong sổ. Không một phản hồi nhà
cung cấp nào bị cắt.

## Vì sao KHÔNG làm "Router tự ghi tệp"

Hướng sửa được đề nghị — agent trả nội dung tệp INLINE, Router tự ghi vào
worktree đã có thẩm quyền, kiểm định đọc hiện vật do Router ghi — nhắm vào
một chế độ hỏng mà **số liệu nói là chưa từng xảy ra**: agent headless không
ghi được tệp. Trong 11 lượt, agent ghi được tệp **mọi lần nó được giao việc**.
Thêm đường ghi đó bây giờ là thêm kiến trúc (điều đang bị cấm) để chữa một
bệnh không có, đồng thời bỏ mất một tính chất đang đúng: hiện vật được kiểm là
thứ agent THẬT SỰ tạo ra, không phải thứ Router chép lại hộ.

Nếu chế độ C (lượt thật sự rỗng) xuất hiện với tần suất đáng kể ở thanh lặp
lại, hướng đó nên được xét lại — với số đo, không với phỏng đoán.

## PHẦN B — THANH LẶP LẠI: **KHÔNG ĐẠT**

| Bài | Yêu cầu | Kết quả |
|---|---|---|
| Kịch bản C kết thúc `DONE` | 5/5 | **0/5 — HỎNG** |
| Kịch bản D `v1 → v2 → DONE` | 5/5 | chưa chạy (chặn bởi C) |
| Khởi động lại giữa lúc sửa chữa | 3/3 | chưa chạy (chặn bởi C) |
| Nhắc quyền tương tác | 0 | **0** ✓ |
| Thay đổi production | 0 | **0** ✓ |

Từng lần, không giấu lần nào:

| Lần | Mã thoát | Khẳng định | Phút | Production |
|---|---|---|---|---|
| 1 | 1 | 23/25 | 3.0 | 0 |
| 2 | 1 | 21/25 | 2.9 | 0 |
| 3 | 1 | 21/25 | 11.6 | 0 |
| 4 | 1 | 21/25 | 4.1 | 0 |
| 5 | 1 | 21/25 | 12.1 | 0 |

Cùng một chữ ký mọi lần: `LOI_HIEN_THUC` → sửa chữa ×2 → lập lại kế hoạch
→ cạn ngân sách → `BLOCKED`.

### Mâu thuẫn CÒN MỞ (chưa giải thích được)

Trên `ex_b6072e6a1522`, việc `fanfic.ghi_tailieu-r2`:

* `UNDERDECLARED_CHANGES` có ghi → đối soát ĐÃ chạy và ĐÃ trả `True`;
* `TASK_STATE RUNNING -> DONE` → bên gọi đã nâng trạng thái;
* cảnh báo của đối soát **có** trong phong bì đã lưu;
* nhưng `envelope.status` vẫn là `'failed'`, `failure_reason='gate_diff'`.

`pb.status = "ok"` nằm ở `engine.py:3712`, **trước** dòng ghi cảnh báo ở
3714 — và cảnh báo thì đã được lưu. `ghi_ket_qua` ghi đè nguyên `result_json`
chứ không trộn. `ExecutionResult.to_dict()` đọc phong bì sống. Mỗi mắt xích
đều đã kiểm và đều đúng, nhưng dữ liệu quan sát nói ngược lại.

**Chưa kết luận.** Tôi đã suy đoán sai hai lần liên tiếp về chỗ này (một lần
đổ cho "bản ghi cũ", một lần đổ cho "trạng thái bị ghi đè"), nên sẽ KHÔNG
đoán lần thứ ba. Bước tiếp theo là một **bài kiểm tích hợp tất định** chạy
đúng đường `_chay` với một Executor giả trả về đúng hình dạng này, rồi đọc
lại `store.task(...).result["envelope"]["status"]` — thay vì đọc thêm nhật ký
của trạng thái dùng chung.
