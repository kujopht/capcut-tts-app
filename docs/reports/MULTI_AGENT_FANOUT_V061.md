# Toả đa agent — khuyết tật nghiệm thu tay `dist-v061` và cách sửa

Nhánh `feat/v061-memory-provider-vault` · 2026-09-10 · Mã: `scripts/control_center/toa.py`,
`engine.py`, `sessions.py`, `leader.py`, `web/app.js` · Bài kiểm: `scripts/tests/test_toa_v061.py` (22)
· Nghiệm thu EXE: `scripts/control_center_v061_toa_acceptance.py`.

## 1. Quan sát

Người dùng gõ:

> gọi 8 agent gemini 3.8 và phân mỗi đứa đi lục cho t 1 bộ fanfic audi

Mong đợi: 8 đơn vị việc độc lập, mỗi cái một tài khoản Antigravity nếu bể đủ.
Thực tế: Leader tạo MỘT việc to ("Khảo sát toàn bộ kho CapCut-TTS-App…"), Router
giao đúng một khe (`antigravity/AG02`). Bể 8 tài khoản đã kiểm toán trở thành vô
nghĩa.

## 2. Nguyên nhân gốc — đo trên mã, theo từng chặng

| Chặng | Điều xảy ra | Kết luận |
|---|---|---|
| **Leader → ý định/phân rã** | `engine._chat()` lấy `delegate_work.objective` — lời **diễn đạt lại** của Leader ("Khảo sát toàn bộ kho…") — làm `goal`, và **bỏ câu người dùng gõ**. `HUONG_DAN` không nói gì về số agent; `delegate_work` chỉ có `objective/hints/che_do`. | Số 8 chết ở đây. `che_do=MAX` là chế độ chất lượng, không phải số agent. |
| **Biểu diễn cardinality** | `RulePlanner.tach()` cắt câu theo dấu cứng/liên từ; `PlannedTask`, `Task`, `TaskContract` **không có trường nào** cho "số agent yêu cầu". Một mệnh đề → một việc. | Không có chỗ để giữ "8" dù Leader có muốn. |
| **Giao diện dispatch Router V4** | `Scheduler.decide()` chọn theo năng lực + `availability` (ưu tiên runtime rảnh) — với 8 việc nó trải trên ≥7 khe (bài kiểm `test_account_pool_v061`). Nó nhận **một** việc nên ra **một** placement. | **Không phải lỗi bộ lập lịch.** Không sửa một dòng nào trong `router_v4/`. |
| **Sức chứa bể** | 8 tài khoản, 10 khe. Nhưng `ControlCenter(max_parallel=3)` (mặc định desktop/web) và `SessionManager.max_sessions=max_parallel` chặn 3 việc song song cho MỌI dự án — kể cả khi có 8 việc. | Giới hạn thứ hai, độc lập với chặng 1, sẽ cắn ngay sau khi sửa chặng 1. |
| **Leader ấm chiếm khe** | Leader ghim AG01 (`LEADER:<project>` — V0.6.1 mới hiện ra). AG01 còn 2/3 khe. `availability` của AG01 = 0.67, AG02 = 1.0 → việc duy nhất rơi vào AG02. | Giải thích vì sao là AG02; không phải nguyên nhân. |
| **UI** | Bảng việc phẳng: không cha/con, không đếm chạy/chờ/xong. | Không hiện được 8 con — nhưng cũng không có gì để hiện. |

## 3. Yêu cầu → cách làm

| # | Yêu cầu | Hiện thực |
|---|---|---|
| 1 | Giữ cardinality tường minh | `toa.xet_toa(text)` đọc **câu người dùng** (không phải lời Leader): "gọi 8 agent" → 8; "cho 4 agent mỗi đứa…" → 4 + `moi_agent_mot`; "chia cho mỗi agent một dataset: a, b, c" → 3 (đếm liệt kê); số chữ ("tám agent", "eight agents"); 1 agent hoặc >32 → không toả; câu mơ hồ → `None`. |
| 2 | Cha + N con độc lập, không trùng | `engine._tao_toa()`: 1 việc cha (vật chứa, `WAITING`, không giao agent — `_san_sang` bỏ qua) + N con (`parent_id`, không phụ thuộc nhau). Mỗi con: `AGENT i/N`, chỉ trả **một** kết quả, phân vùng theo thứ tự liệt kê ổn định (i, i+N, …) hoặc mục được giao riêng, dòng `KẾT QUẢ [i/N]: …` để gộp được. Hợp đồng/phong bì quyền/khoá tài nguyên lấy từ việc mẫu của bộ phân rã (GATED giữ nguyên). |
| 3 | Gán tài khoản theo bể thật, không im lặng cắt | `toa.tinh_suc_chua(fabric, …)`: runtime đủ điều kiện (cấp phát, nhận dispatch, đúng provider/model nếu nêu, trạng thái nhận việc được), khe rảnh = `concurrency − in_flight` (đã trừ `LEADER:`), tài khoản rảnh, trần song song. `SessionManager.decide(tranh_runtime=…)`: con tránh runtime anh em đang chạy khi còn chỗ khác, hết thì rơi về. `mark_started` ngay lúc giao (trước đây chỉ trong luồng → hai con cùng nhịp xếp lên một tài khoản đã đầy — bài kiểm bắt). |
| 4 | Tách chế độ / số agent / trần | Ba trường riêng: `delegate_work.che_do`, `YeuCauToa.so_agent`, `SucChua.tran_song_song`. `max_parallel` mặc định đổi `3 → 0 = tự theo bể` (tổng khe runtime đã cấp phát, kẹp 3..12; `--max-parallel N` tường minh vẫn thắng). |
| 5 | Leader nói thật | Engine viết câu sức chứa từ fabric và **nối vào** reply: "Đã tách thành N tác vụ độc lập… Hiện K/N worker slots khả dụng; K chạy ngay, N−K chờ slot (giới hạn bởi …)". Leader nhận khối "YÊU CẦU SONG SONG TƯỜNG MINH" với đúng các số trước khi trả lời; `HUONG_DAN` luật 6. Chỉ tạo 1 việc thì không có câu "đã tách N". |
| 6 | UI | Bảng Tasks: dòng cha đếm `N con: chạy · chờ · xong · hỏng · chặn`, các con thụt vào (`↳ [i/N]`); chi tiết cha: sức chứa lúc tách, từng con với runtime/model, tổng hợp. Agents: mỗi worker một dòng (sẵn có). |
| 7 | Kết quả | `_tong_hop_toa()` khi mọi con kết thúc (BLOCKED thì cha chờ): khử trùng ứng viên (gấp dấu, bỏ trang trí), giữ nguồn gốc từng con (việc, runtime, model, phiên), cha `DONE` (hoặc `FAILED` nếu 0 con xong); MỘT tin tổng hợp trong chat (không rải N tin con); Leader (phiên ấm, nếu đang mở) tóm tắt một lượt. |
| 8 | Bài kiểm | `test_toa_v061.py` — 20 bài, xem mục 5. |
| 9 | Nghiệm thu EXE | `control_center_v061_toa_acceptance.py --so 4 --max-parallel 3` — xem mục 6. |

## 4. Hành vi mới, cụ thể

Với câu gốc trên máy này (8 tài khoản, 10 khe, Leader chiếm 1 ở AG01, trần tự
động = 10):

```
Đã tách thành 8 tác vụ độc lập (việc cha `router.tXXXX-cha`). Bể worker antigravity:
8 tài khoản rảnh / 8 đủ điều kiện, 9 slot trống (Leader đang chiếm 1 chỗ ở AG01);
trần song song của Control Center: 10. Model ghim theo yêu cầu: gemini-3.8-flash-high.
8/8 worker slots khả dụng — dispatch 8 worker song song.
```

Nếu AG01 không còn chỗ (ví dụ trần 7 hoặc AG01 đầy): "Hiện 7/8 worker slots khả
dụng; 7 chạy ngay, 1 chờ slot (giới hạn bởi khe tài khoản)". Con thứ tám chạy khi
một khe rảnh ra — không ai cắt yêu cầu xuống 7.

## 5. Bộ kiểm (`scripts/tests/test_toa_v061.py`, fabric giả 2 runtime × 2 khe)

| Yêu cầu đề bài | Bài |
|---|---|
| "8 agents" → 8 con | `test_cau_that_cua_nghiem_thu_tay`, `test_moi_con_mot_phan_vung_khong_trung`, `test_4_agent_thanh_cha_va_4_con_khong_viec_to` |
| "each agent" | `test_cac_dang_tuong_minh`, `test_moi_agent_mot_voi_danh_sach_dem_duoc`, `test_moi_agent_mot_muc_liet_ke`, `test_liet_ke_thi_moi_con_mot_muc` |
| bể nhỏ hơn yêu cầu | `test_dem_tu_fabric_va_tru_cho_leader` (8 xin / 4 khe → 4 chạy, 4 chờ), `test_suc_chua_nho_hon_yeu_cau_thi_xep_hang_va_noi_that` |
| Leader ấm chiếm một tài khoản | `test_dem_tu_fabric_va_tru_cho_leader`, `test_leader_chiem_mot_khe_thi_bao_dung_va_khong_vuot` (RT01 ≤ 1 con) |
| phần dư xếp hàng | `test_suc_chua_nho_hon_yeu_cau…` (2 chạy + 2 chờ → rồi 4 xong) |
| chọn tài khoản phân biệt | `test_giao_nhieu_tai_khoan_va_tong_hop` (RT01 + RT02) |
| một con hỏng không huỷ anh em | `test_mot_con_hong_khong_huy_anh_em` (3 xong, 1 hỏng sau 3 lượt thử) |
| gộp sau khi xong | `test_giao_nhieu_tai_khoan_va_tong_hop`, `test_tong_hop_khu_trung_giu_nguon_goc`, `test_khu_trung_ung_vien_giua_cac_con`, `test_khong_co_khong_thanh_ung_vien` |
| không giao trùng | `test_giao_nhieu_tai_khoan_va_tong_hop` (mỗi con đúng một lượt) |
| câu mơ hồ không sinh 8 agent | `test_cau_mo_ho_KHONG_toa`, `test_cau_mo_ho_khong_tu_sinh_8_agent`, `test_che_do_MAX_khong_phai_so_agent` |
| ghim provider/model chỉ khi nêu | `test_neu_nguoi_dung_neu_model_thi_ghim_provider` |
| trần tự động theo bể | `test_tran_song_song_tu_dong_theo_be` |
| UI: cha/con trong bảng việc; WebSocket theo dự án đang chọn | `TestUIToa.test_bang_viec_ve_cha_con`, `test_websocket_theo_du_an_dang_chon` |

Hai lỗi thật khác mà bộ kiểm bắt được trong khi viết: (1) khe runtime chỉ được
đánh dấu trong luồng `_chay` → hai con giao trong cùng một nhịp xếp lên một
tài khoản đã đầy (nay `mark_started` ngay lúc giao); (2) kết quả cha được báo
về chat HAI lần — luồng con cuối và lưới an toàn trong `tick()` cùng qua phép
kiểm "đã báo" (nay kiểm + ghi trong một khoá, `_khoa_bao`; cũng bịt cửa sổ
đua vốn có cho việc thường).

## 6. Nghiệm thu bản EXE — `dist-v0611`

Vì sao `dist-v0611`, không phải `dist-v061`: lúc rebuild, HAI bản EXE từ
`dist-v061` còn đang mở (nghiệm thu tay của người vận hành) và khoá
`control.db` của thư mục đó; `--clean` dừng giữa chừng, `_internal` của
`dist-v061` chỉ còn 36 tệp. Bản đang mở vẫn chạy; mở mới từ `dist-v061` sẽ
hỏng cho tới khi build lại. Bản có toả được build vào thư mục mới:
`dist-v0611/Router Control Center/Router Control Center.exe` — 11 653 545 byte,
sha256 `db9e05817f88b781f48ca9d18750ad7254bfdd2208fb945bd7ec0e26f144e927`,
`_internal` 278 tệp (`dist-v0611/BAN_TOT_v0611.txt`).

`scripts/control_center_v061_toa_acceptance.py --exe "dist-v0611/…" --so 4 --max-parallel 3`
— việc con RẺ và AN TOÀN (mỗi agent trả lời một dòng "agent i sẵn sàng", không
đọc tệp, không chạy lệnh) nhưng là `agy` THẬT trên tài khoản Antigravity THẬT;
trần 3 với 4 agent cố ý tạo một con phải chờ.

| Lần | Kết quả | Ghi chú |
|---|---|---|
| 1 | 12/15 | **Cốt lõi ĐẠT**: 4 agent → 1 cha + 4 con (23 s); Leader THẬT trả lời *"tách thành 1 việc cha và 4 việc con độc lập cho 4 agent Gemini 3.8. Do trần song song của Control Center là 3 nên hiện có 3/4 worker slots khả dụng: 3 việc chạy ngay, 1 việc chờ slot"*; con chạy trên **AG02, AG03, AG04**; không bao giờ >3 cùng lúc; có lúc 3 chạy + 1 chờ; UI cha/con; cha DONE 4/4, nguồn gốc giữ; MỘT tin tổng hợp. **Hỏng**: 2c (harness đọc ô chat cắt 1 500 ký tự, dòng của engine bị đẩy ra ngoài), 4b (đọc bảng Agents trước nhịp vẽ), 6 (4 cửa sổ chủ `WindowsTerminal.exe` — cùng lúc bộ kiểm UI Textual của chính đợt này và hai bản EXE của người vận hành đang chạy). |
| 2 | **14/15** | 2c ĐẠT (đọc tin `delegation` từ API): Leader: *"1 việc cha và 4 việc con độc lập với model Gemini 3.8 Flash (High). Hiện tại có 3/4 worker slot khả dụng (giới hạn bởi trần song song của Control Center là 3): 3 việc chạy ngay, 1 việc chờ slot"*; **6 ĐẠT** (0 vi phạm / 130 s, app sinh agy×6, git×16, ssh×5). Còn 4b: bảng Agents rỗng lúc đọc — hai probe riêng (gieo phiên vào sổ, mở EXE) cho thấy bảng VẼ ĐÚNG `antigravity · AG02/AG03`, 0 lỗi JS → lỗi ở harness/thời điểm đọc, không ở UI; lần 3 ghi kèm API sessions + lỗi JS ngay lúc đọc. |
| 3 | **14/15** | Leader: *"Hệ thống tách thành 4 tác vụ độc lập: hiện có 3 việc chạy ngay, 1 việc chờ slot do giới hạn bởi trần song song của Control Center là 3"*; AG02/AG03/AG04; 6 ĐẠT (0 vi phạm / 141 s). **4b hỏng có bằng chứng quyết định**: bảng Agents rỗng trong khi `/api/state` cùng lúc trả `[(AG02, BUSY), (AG03, BUSY), (AG04, BUSY)]` và 0 lỗi JS → giao diện KHÔNG nhận đẩy sống cho dự án đang xem. |
| 4 | **14/15** — **4b ĐẠT** | Sau khi sửa WebSocket: bảng Agents = `antigravity · AG02 | AG03 | AG04` đúng lúc API trả ba phiên BUSY, 0 lỗi JS. Leader: *"tách thành 1 việc cha và 4 việc con độc lập. Do trần song song của Control Center là 3, hiện tại 3 việc sẽ chạy ngay và 1 việc chờ slot"*. Hỏng duy nhất: **6** — 4 cửa sổ chủ `WindowsTerminal.exe`, và danh sách tiến trình "vừa xuất hiện" ghi rõ `bash.exe`/`conhost.exe` **của chính phiên làm việc này** (lệnh `sha256sum`/`tasklist` chạy song song với bài đo). Lần 2 và 3 — không lệnh nào chạy cạnh — đều 0 vi phạm (130 s, 141 s). |

Kết luận nghiệm thu: mọi bước về TOẢ (2, 2b, 2c, 2d, 3, 3b, 3c, 4, 4b, 5, 5b,
5c, 7) ĐẠT trên bản đóng gói ở lần 4; bước 6 ĐẠT ở lần 2 và 3. Chi phí: mỗi lần
4 lượt Gemini Flash một dòng + 2 lượt Leader.

### 6.2 Bản cuối — `dist-v061` build lại SẠCH từ `d59accd` (sau khi người vận hành đóng app)

`dist-v061/Router Control Center/Router Control Center.exe` — 11 653 545 byte,
sha256 `d0c04e9262d2d8e430ef97df8033c36b2984e1c2aaa8d0b0071e15873588c877`,
`_internal` 278 tệp (`dist-v061/BAN_TOT_v061.txt`). Mở bình thường qua
`ShellExecuteW` (bước 1 của cả hai lần). Harness thêm bước 8: kho git tạm sạch
trước/sau (việc CHỈ ĐỌC; `.router/` của chính app được loại).

| Kịch bản | Kết quả | Đo được |
|---|---|---|
| A — `--so 4 --max-parallel 3` (mỗi agent một dòng) | **15/16** | 1 cha + 4 con, yêu cầu giữ 4; Leader: *"tách 4 việc; 3 chạy ngay, 1 chờ slot (… hiện 3/4 worker slots khả dụng)"*; AG02/AG03/AG04; ≤3 cùng lúc; 3+1 chờ; Tasks + Agents sống; cha DONE 4/4; MỘT tin tổng hợp; **6 ĐẠT: 0 vi phạm / 102 s**; kho sạch. Bước 8 hỏng lần này chỉ vì harness chưa loại `.router/` (sửa ngay). |
| B — câu NGUYÊN VĂN *"gọi 8 agent gemini 3.8 và phân mỗi đứa đi lục cho t 1 bộ fanfic audio"*, `--max-parallel 6`, kho tạm gieo 12 bộ fanfic audio tổng hợp | **15/16** | **1 cha + 8 con, yêu cầu giữ nguyên 8**; Leader: *"tách thành 8 việc độc lập cho 8 agent (Gemini 3.8 Flash High) tìm fanfic audio: 6 việc chạy ngay, 2 việc chờ slot do trần song song của Control Center là 6"* + dòng engine *"8 tài khoản rảnh / 8 đủ điều kiện, 8 slot trống (Leader đang chiếm 1 chỗ ở AG01)"*; **6 tài khoản thật AG02–AG07** cùng lúc, không bao giờ >6, có lúc 6 chạy + 2 chờ; Tasks 1 cha + 8 con, Agents 6 dòng sống; cha DONE **8/8, 8 ứng viên, 0 trùng**, nguồn gốc từng con; MỘT tin tổng hợp; kho git sạch trước/sau. Hỏng: **6** — 7 cửa sổ chủ `WindowsTerminal.exe` lúc `agy` sinh (4.1 s, 22 s), trong khi **22/22 console do Router tạo đều ẩn**; không lệnh nào của phiên làm việc chạy cạnh. |

Về bước 6: bộ đo không quy được cửa sổ của Windows Terminal (tiến trình
phiên-toàn-cục, "ứng dụng terminal mặc định") về app; mọi console mà Router
sinh ra đều ẩn (`an_cua_so()` hoạt động — bộ đo đếm `console ẩn`). Hiện tượng
đã ghi từ V0.4/V0.6, tần suất tăng theo số lần sinh `agy` (4 agent: 0/102 s;
8 agent: 7). Nó nằm ở đường sinh tiến trình của `agy`/launcher, không phải ở
toả, và **không sửa trong đợt này** (đề bài: không thêm tính năng) — để lại
làm việc tiếp theo có bài đo riêng.

Sổ ký ức/`control.db` của mỗi lần nằm trong kho tạm và bị xoá sau bài; không
kho thật nào bị sửa; không tài khoản nào bị đăng nhập lại hay xoay.

### 6.1 Lỗi giao diện thật bắt được ở bước 4b — WebSocket không theo dự án đang chọn

`noiWs()` mở WebSocket MỘT lần lúc tải trang với `project=` của dự án được
chọn lúc đó (dự án đầu trong sổ: `fanfic`). Chọn dự án khác (`router`) chỉ
gọi `lamMoi()` — một lần `GET /api/state` — và **không mở lại** kết nối. Từ
đó mọi gói đẩy sống là của `fanfic`; `fanfic` không đổi gì nên server (so dấu
vân tay trước khi gửi) **không đẩy gì**. Bảng Tasks trông "sống" chỉ vì lần gửi
chat có một lượt fetch lại; bảng Agents của `router` không bao giờ nhận được
ba phiên vừa dựng. Không phải lỗi mới của toả — mọi thao tác đổi dự án từ V0.2
đều thế — nhưng chính toả lộ ra nó, vì đây là lần đầu bài nghiệm thu nhìn vào
bảng Agents của một dự án được chọn SAU khi tải.

Sửa (`web/app.js`): `wsDuAn` theo dõi dự án của kết nối; chọn dự án → đóng kết
nối cũ có chủ ý (không tự nối lại) → mở kết nối mới; gói `state` có
`selected` khác dự án đang chọn bị bỏ qua. Bài kiểm nguồn
`TestUIToa.test_websocket_theo_du_an_dang_chon` khoá ba điều đó.

## 7. Khuyết tật nghiệm thu tay #2 — toả đúng số nhưng chạy TUẦN TỰ vì khoá tài nguyên

Câu thật (2026-09-10, bản `dist-v061` sha `d0c04e92…`):

```
gọi 4 agent gemini 3.8, mỗi agent kiểm tra một phần khác nhau của repo này:
1. README/docs
2. tests
3. source architecture
4. git history
không được trùng phạm vi nhau
```

Quan sát: 1 cha + 4 con được tạo đúng, nhưng chỉ MỘT con chạy; ba con còn lại
`WAITING` với lý do "tranh chấp với khoá `FILESYSTEM · readme/docs` do việc
`…-1` đang giữ"; con [1/4] `FAILED`. `max_parallel` lúc đó là 12, sự kiện
`TOA_SPLIT` ghi 9 khe rỗi — trần song song **không** phải giới hạn.

### 7.1 Nguyên nhân gốc — đọc từ sổ `control.db` của lần chạy tay (chỉ đọc)

Chuỗi hỏng đi qua **bốn** chặng, chặng nào cũng cần thiết:

| Chặng | Điều đã xảy ra | Bằng chứng |
|---|---|---|
| Phân loại việc (`planner.loai_viec`) | Câu bị xếp `testing` vì mẫu cũ khớp DANH TỪ trần `tests` (mục 2 của danh sách). `testing` là lớp GHI: `repo_write=True`, `worktree_required=True`. | `contract.requirements.repo_write = true`, `execution.worktree_required = true` trong cả 4 con |
| Phạm vi (`planner.tai_nguyen`) | Lớp GHI lấy `allowed_scope` từ token giống đường dẫn duy nhất trong câu → `['README/docs']`; sinh **một** khoá `FILESYSTEM:README/docs`. | `resources = ["FILESYSTEM:README/docs"]` |
| Toả (`engine._tao_toa`) | Sao chép `resources` của MẪU vào **cả bốn** con — con "tests", con "source architecture", con "git history" đều xin khoá `readme/docs`. | 4 con cùng `resources`, 4 hợp đồng cùng `allowed_scope` |
| Khoá (`locks.py`) | Khoá không có CHẾ ĐỘ: mọi khoá đều độc quyền. Con 1 giữ → con 2–4 `WAITING`. Khi con 1 kết thúc, con 2 nhận khoá, con 3–4 vẫn chờ. | `LOCK_ACQUIRED` một lần, ba `TASK_WAITING "tranh chấp…"` |

Hậu quả kéo theo: vì tuần tự nên bộ lập lịch chỉ dùng **AG02** (rồi AG03 khi
con 2 được giao lại) — REUSE theo phạm vi, không có anh em nào chạy cùng lúc
để "tránh runtime anh em" phát huy. Cha KHÔNG giữ khoá nào (`resources: []`) —
đã kiểm tường minh.

**Con [1/4] hỏng vì sao:** `failure_reason = tool_permission_denied`; stderr
của `agy`: *"a tool required the `read_file` permission that headless mode
cannot prompt for, so it was auto-denied"*. Con chạy trong worktree
`.router/worktrees/AG02/…` (vì bị coi là việc GHI). Đây **không** phải lỗi
đồng thời; nó là hệ quả trực tiếp của việc xếp sai lớp: một việc chỉ đọc bị
đẩy vào đường GHI (worktree + phong bì quyền GHI) mà nó không cần. Con 2 chạy
lại thì hỏng `gate_diff` ("báo ok cho một việc CÓ GHI nhưng không tệp nào
đổi") — cũng cùng gốc: việc đọc bị đo bằng thước của việc ghi. Không tự động
"cho qua" lỗi nào; sửa gốc là xếp lớp đúng.

### 7.2 Sửa — không tắt khoá, không nới an toàn GHI

1. **Khoá có chế độ READ/WRITE** (`locks.py`, `model.ResourceLock.mode`, cột
   `locks.mode` tự nâng cho sổ cũ). Ma trận: READ+READ sống chung (mỗi người
   đọc một hàng `…#r:<task>`); READ+WRITE giao nhau tranh chấp (cả hai
   chiều); WRITE+WRITE giao nhau tranh chấp; không giao nhau thì song song.
   Chuỗi cũ `FILESYSTEM:x` không chế độ = WRITE (không nới gì cho dữ liệu cũ).
2. **Phạm vi chính xác, giao nhau tất định** (`locks.chuan_hoa/xung_dot`):
   `docs/`, `docs/**`, `Docs\sub` → `docs`, `docs/sub`; gốc kho `.`/`*` giao
   với mọi đường dẫn; giao nhau theo ĐOẠN (`web/admin` ≠ `web/administration`);
   tệp là một đường dẫn (`web/index.txt` giao `web`). Lớp mới `LockKind.GIT`:
   `history` (đọc: log/show/blame/status/diff/rev-parse) tách khỏi `worktree`
   (ghi); `*` giao mọi trạng thái git. Đọc lịch sử git **không** giữ khoá hệ tệp.
3. **Phân loại đọc trước khi phân loại lớp** (`planner._Y_DOC/_Y_GHI`): có ý
   đọc (kiểm tra/xem/lục/review/audit/…) mà không có động từ GHI → `analysis`/
   `review` (chỉ đọc, không worktree, khoá READ). Mẫu `testing` chỉ còn khớp
   ĐỘNG TỪ quanh "test" hoặc từ chuyên môn — danh từ `tests` trần không còn là
   việc testing. Có động từ GHI thì vẫn là lớp GHI như cũ (bài kiểm khoá lại).
4. **Tài nguyên theo TỪNG con** (`toa.chia_con`): đọc danh sách nhiều dòng
   `1. … 2. …`, mỗi mục một con; mục có đường dẫn → `READ FILESYSTEM <đường>`,
   mục không đường dẫn → `READ FILESYSTEM .`, mục "git history" → `READ GIT
   history` **duy nhất**. Việc GHI: `WRITE FILESYSTEM <đường của mục>` hay
   phạm vi mẫu — vẫn tuần tự khi trùng chỗ. Mỗi con nhận dòng "Tài nguyên/phạm
   vi của bạn: …" trong mục tiêu.
5. **Cha là hộp chứa**: không xin khoá, không chiếm khe, chuyển `RUNNING` khi
   con đầu tiên được nhận (trước đó cha `WAITING` trong khi con chạy — sai về
   nghĩa), `recover()` không coi cha là mồ côi.
6. **Đo song song THẬT**: mỗi con ghi `khoang_chay {bat_dau, ket_thuc,
   runtime, model}` đúng lúc `executor.run` bắt đầu/kết thúc; tổng hợp của cha
   tính `song_song_toi_da` bằng quét mốc (sweep-line) — con số này là "số
   khoảng chạy giao nhau nhiều nhất", không phải đếm trạng thái `RUNNING`.
7. **UI**: hàng con hiện `· AG0x · READ docs, READ git:history`; chi tiết cha
   hiện "song song thực đo tối đa k/N".
8. **Con "git history" nhận NHẬT KÝ GIT do Router đọc** (`nguon_git.
   git_nhat_ky_doc` → `engine._kem_nhat_ky_git`). Lần chạy đóng gói đầu
   (§7.5, lần 1) cho thấy: ba con đọc tệp xong, riêng con [4/4] chết
   `tool_permission_denied` — agent headless bị TỰ CHỐI quyền `command`
   (không ai để hỏi) nên không có cách nào tự `git log`. Router có sẵn đường
   đọc git an toàn (ba lệnh đọc, tham số cố định, timeout, không cửa sổ) nên
   đọc thay: nhánh, tổng số commit, 80 commit mới nhất (mã · ngày · tác giả ·
   tiêu đề), cắt ở 6 000 ký tự, **lọc bí mật** (`memory.bi_mat.loc`) trước
   khi vào payload việc. Quyền của agent KHÔNG đổi, không thêm cờ nào; kho
   không phải git → không đính, việc chạy như cũ. Cùng cách cho việc đọc git
   không toả (đường planner).
9. **Nhả khoá ngay khi việc ở trạng thái cuối**, trước thử lại / báo chat /
   gộp cha — không đợi `finally` của luồng. Lần chạy đóng gói đầu bắt được
   "cha DONE mà khoá READ `.` của con [3/4] còn giữ": `_tong_hop_toa` chạy
   TRONG luồng của con cuối, vài ms trước `finally`. Nhả sớm cũng đóng một
   cửa sổ cũ: `_thu_lai_neu_dang` xếp lại việc trong khi luồng còn giữ khoá,
   lượt sau xin lại (cùng chủ → được), rồi `finally` nhả sạch — kể cả khoá
   lượt sau. Bài kiểm bọc `_tong_hop_toa` và khẳng định mọi con đã ở trạng
   thái cuối đều KHÔNG còn khoá tại thời điểm gộp.

### 7.3 Bốn con của câu thật sinh ra gì (đo bằng bài kiểm, không phải mô tả)

| Con | Lớp | Tài nguyên | Chế độ | Worktree |
|---|---|---|---|---|
| [1/4] README/docs | analysis | `READ:FILESYSTEM:README/docs` | READ | không |
| [2/4] tests | analysis | `READ:FILESYSTEM:tests` | READ | không |
| [3/4] source architecture | analysis | `READ:FILESYSTEM:.` (không có đường dẫn → gốc kho, chỉ đọc) | READ | không |
| [4/4] git history | analysis | `READ:GIT:history` | READ | không |

Cha: `resources = ()`. Bốn khoá READ cùng sống trong sổ, `0` sự kiện tranh chấp.

### 7.4 Bộ kiểm mới — `scripts/tests/test_khoa_doc_ghi_v061.py`

Fabric giả **4 runtime × 1 khe, 4 tài khoản** (để "bốn tài khoản phân biệt
cùng lúc" là điều đo được):

* `TestKhoaDocGhi` (10): READ+READ cùng chỗ; READ+WRITE giao nhau hai chiều;
  WRITE+WRITE giao/không giao; gốc kho giao mọi đường dẫn; chuẩn hoá phạm vi;
  git đọc không giữ khoá hệ tệp và không giao `worktree`; chuỗi cũ = WRITE;
  cùng tài nguyên xin cả READ và WRITE thì giữ WRITE; trả/reclaim không rò
  khoá READ; sổ cũ được nâng cột `mode`.
* `TestPhanLoaiDoc` (4): câu thật → chỉ đọc, không worktree, mọi khoá READ;
  danh từ `tests`/`README` không thành việc ghi; động từ GHI không bao giờ rơi
  về lớp chỉ đọc; việc ghi khoá WRITE, việc đọc git khoá GIT.
* `TestToaTaiNguyenCon` (3): danh sách nhiều dòng → 4 phân vùng, 4 tài nguyên
  riêng; con GHI giữ WRITE theo đường dẫn riêng; `song_song_toi_da` quét mốc.
* `TestBonConDocSongSong` (4): **4 con chỉ đọc chạy đồng thời trên RT01–RT04**,
  cha `RUNNING`, 4 khoá READ, 0 tranh chấp, `song_song_toi_da == 4` từ khoảng
  chạy thật, không rò khoá, không `RUNNING/WAITING` tồn; **2 con GHI cùng tệp
  vẫn tuần tự** (1 chạy + 1 chờ với sự kiện tranh chấp WRITE, `song_song_toi_da
  == 1`); một con hỏng không rò khoá và anh em vẫn song song; `recover()` không
  coi cha là mồ côi.

Các bài cũ về an toàn đồng thời giữ nguyên (`test_control_center_core` chỉ
đổi hình dạng bộ ba `(kind, resource, mode)`; `test_toa_v061` đếm CON khi cha
cũng `RUNNING`).

### 7.5 Nghiệm thu bản EXE đóng gói — `dist-v0612`

Bản `dist-v061` **đang được người vận hành mở** lúc làm việc này (PID thật,
ba `agy` con — kiểm bằng ảnh chụp tiến trình, không phải `tasklist /FI`, vốn
bị Git Bash đổi `/FI` thành đường dẫn và in rỗng), nên bản mới dựng vào
`dist-v0612` (`build_desktop_exe.py --dist dist-v0612 --clean`); `dist-v061`
vẫn là bản CŨ cho tới khi app đóng và dựng lại. Harness:
`control_center_v061_toa_acceptance.py --kich-ban kiem-tra|ghi --max-parallel 4`
(kịch bản `kiem-tra` = câu NGUYÊN VĂN ở đầu §7; `ghi` = 2 agent thêm một dòng
vào CÙNG một tệp `docs/ghi_chu_nghiem_thu.md` trên kho tạm).

**Lần 1 (`kiem-tra`, sha `e6ef4afe…`) — 19/22**, và hai bước hỏng là hai
phát hiện thật:

| Bước | Kết quả | Vì sao |
|---|---|---|
| 2e · 4 tài nguyên READ riêng, không worktree | ĐẠT | `READ:FILESYSTEM:README/docs` · `READ:FILESYSTEM:tests` · `READ:FILESYSTEM:.` · `READ:GIT:history` |
| 3 · nhiều tài khoản AG thật | ĐẠT | AG02, AG03, AG04, AG05 — cùng lúc 4 |
| 3d/3e/3f · cha RUNNING, 0 tranh chấp, 4 chạy cùng lúc | ĐẠT | |
| 5e · khoảng chạy thật giao nhau | ĐẠT | `song_song_toi_da = 4`; bốn khoảng đều bắt đầu 17:56:33 |
| 5d · không con hỏng | **HỎNG** | con [4/4] git history `tool_permission_denied` — agent headless không được chạy `git log` (§7.2 mục 8) |
| 5f · không rò khoá | **HỎNG** | `FILESYSTEM . read` của con [3/4] còn giữ đúng lúc cha DONE — `_tong_hop_toa` chạy trước `finally` của luồng con (§7.2 mục 9) |
| 6 · cửa sổ console | HỎNG | 5 cửa sổ `WindowsTerminal.exe` (chủ `svchost`) lúc `agy` sinh — vấn đề đã biết từ §6.2, không do Router |

**Lần 2 (`kiem-tra`, dựng lại sạch, sha `5e6d0ab7…`) — 21/22**: 4/4 con
DONE (con git history trả "commit 225b012 … commit duy nhất trên nhánh
main" — đọc từ nhật ký Router đính), AG02–AG05 cùng lúc, `song_song_toi_da =
4` (bốn khoảng 18:16:39 → 18:17:13/18:18:04/18:17:22/18:17:13), 0 tranh chấp,
cha RUNNING → DONE 4/4, **0 khoá còn giữ** (đo sau khi cha DONE), kho tạm
sạch trước/sau. Bước duy nhất còn hỏng là 6 (cửa sổ Windows Terminal, như
trên). Sổ của lần chạy giữ ở `%TEMP%\cc-desk-acc-3uuwoguo\.router\…`.

**Kịch bản `ghi` (2 con GHI cùng tệp) — khoá WRITE độc quyền còn nguyên:**
con 1 `LOCK_ACQUIRED … (WRITE)` 18:19:14; con 2 `QUEUED → WAITING (… tranh
chấp với khoá FILESYSTEM 'docs/ghi_chu_nghiem_thu.md' (WRITE) do việc …-1
đang giữ)`; con 2 chỉ nhận khoá lúc 18:20:23, MỘT giây sau `LOCK_RELEASED`
của con 1; không lúc nào 2 con cùng RUNNING; `song_song_toi_da = 1`; cả hai
DONE; tệp trong worktree cô lập `.router/worktrees/AG02/…` có ĐỦ hai dòng
(Agent 1 rồi Agent 2), tệp ở gốc kho tạm KHÔNG đổi; không khoá còn giữ. Con
2 DÙNG LẠI phiên/worktree của con 1 (REUSE theo phạm vi — đúng, vì tuần tự);
hai bước "nhiều tài khoản"/"nhiều hàng Agents" của harness viết cho kịch bản
song song đã được ghi đúng nghĩa cho kịch bản tuần tự; lần chạy lại
(`%TEMP%\cc-desk-acc-9pwv5p7q`) **20/21**, bước hỏng duy nhất là 6 (một cửa
sổ Windows Terminal lúc `agy` sinh — lần chạy trước đó 0 vi phạm, nên đây là
chuyện ngẫu nhiên ở phía `agy`/Windows Terminal, không phải Router). Quan sát phụ, không
thuộc khuyết tật này: agent không khai `changes`, engine đối soát đĩa
(`UNDERDECLARED_CHANGES`, 1 tệp trong phạm vi) rồi DONE — phong bì vẫn mang
`failure_reason=gate_diff`, chỉ là nhãn.

**Số lần đụng vào production / kho thật: 0** — mọi việc chạy trên kho git
tạm của harness; việc đọc không đổi gì (bước 8 sạch trước/sau), việc ghi chỉ
đổi tệp trong worktree cô lập của kho tạm.
