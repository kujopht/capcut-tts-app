# Gốc dữ liệu CHÍNH TẮC — kết thúc khuyết tật liên tục (V0.6.1, 2026-09-10)

Khuyết tật: danh tính dự án ỔN ĐỊNH (`project_id="fanfic"` → `fanfic-dcf29d1141`,
chỉ băm từ project_id) nhưng CHỖ LƯU thì neo vào VỊ TRÍ MÃ. Cùng một dự án ra
nhiều quyển sổ độc lập, và lời khuyên "luôn mở bằng `router-cc-desktop.cmd`" là
băng dán, không phải kiến trúc. Báo cáo này thay băng dán bằng kiến trúc.

## 1. Trước / sau

| | Đường dẫn |
|---|---|
| source-mode CŨ | `C:\FanficWorkers\router-control-center\.router\…` (`parents[2]` của `desktop.py`) |
| đóng gói CŨ | `<cạnh EXE>\.router\…` — đo được: `dist-v06\Router Control Center\.router`, `dist-v0612\…\.router` (sổ của `dist-v061` đã bị `--clean` xoá cùng thư mục app) |
| TUI/web CŨ | `Path.cwd()` — đổi theo chỗ mở terminal |
| **CHÍNH TẮC (nay)** | **`C:\Users\nguye\AppData\Local\RouterControlCenter`** (+ `.router/` bên trong) |
| namespace Fanfic | `fanfic-dcf29d1141` — KHÔNG đổi (chỉ theo `project_id`) |

`scripts/control_center/duong_du_lieu.py` là **nơi duy nhất** định nghĩa gốc.
Thứ tự: tham số tường minh (`--root`, cho bài kiểm) → `$ROUTER_CC_DATA_ROOT` →
`%LOCALAPPDATA%\RouterControlCenter` (ngoài Windows: `$XDG_DATA_HOME` rồi
`~/.routercontrolcenter`). **Không nhánh nào đọc `__file__`, `cwd`,
`sys.executable`, hay thư mục dist.**

Đã sửa mọi điểm vào: `desktop.py` (bỏ nhánh `frozen`→cạnh EXE), `webmain.py`
và `__main__.py` (bỏ `Path.cwd()`), và `ControlCenter.__init__` (mặc định khi
người gọi không nói rõ — lưới an toàn cho cả đường Qt).

Giữ tầng `.router/` bên trong gốc CÓ CHỦ ĐÍCH: mọi module (`store.py`,
`memory/service.py`, `attachments.py`, `desktop_shell.py`, `ghi_utf8.py`) đã
dựng đường từ `<gốc>/.router/...`, nên đổi gốc là đổi TẤT CẢ cùng lúc và di trú
chỉ là chuyển một cây thư mục. Hơi dư một tầng, đổi lại là diff nhỏ nhất và
không có module nào tự suy đường riêng.

## 2. Phiên bản KHO tách khỏi phiên bản ứng dụng

`<gốc>/.router/kho.json` giữ `phien_ban_kho` (hiện `1` = bố cục
`.router/{control_center,memory,attachments,v4,worktrees}`), ghi NGUYÊN TỬ
(tệp tạm + `os.replace`). `dam_bao_kho()` mở → đọc → nâng nếu cũ → chạy tiếp;
sổ MỚI HƠN mã thì **ném `KhoLoi` và DỪNG**, không hạ cấp âm thầm. Ứng dụng lên
phiên bản KHÔNG tạo sổ mới (bài kiểm `test_mo_lai_khong_tao_so_moi` so
`tao_luc` trước/sau).

## 3. Một người ghi (`KhoaKho`)

Nhiều bản dựng nay trỏ CÙNG một sổ, nên `desktop_shell.quyet_dinh()` có một
nhánh nguy hiểm: `tu_chay` khi tệp khoá trỏ một pid còn sống mà backend không
trả lời token của ta — trước đây vô hại (mỗi bản một sổ), nay là **người ghi
thứ hai trên một SQLite**. `KhoaKho` là khoá OS độc quyền trên
`<gốc>/.router/kho.lock`, giành TRƯỚC khi mở `ControlCenter`; không giành được
thì hiện câu **"Kho dữ liệu Router đang được dùng…"** kèm gốc + pid đang giữ,
rồi thoát mã 4. Không giết tiến trình nào. Đường bình thường (bấm đôi lần hai)
vẫn là `noi_lai` — nối vào backend đang sống, không mở sổ thứ hai.

**Một lỗi THẬT bài kiểm bắt được:** bản đầu mở tệp khoá bằng `"a+"` rồi
`msvcrt.locking(..., 1)`. `locking` khoá 1 byte **tại vị trí hiện tại**; với
`"a+"` vị trí là EOF, nên sau khi bản đầu ghi JSON vào tệp, bản thứ hai khoá
một byte KHÁC và **không xung đột** — khoá vô dụng. Sửa: tệp khoá là bìa thuần
(≥1 byte, `seek(0)` trước khi khoá, không bao giờ cắt), thông tin người giữ
sang `kho.lock.info`.

## 4. Di trú an toàn — `di_tru.py` + `scripts/router_cc_di_tru.py`

`python scripts/router_cc_di_tru.py` (xem trước, mặc định) ·
`--chay` (ghi thật) · `--dat-moc` · `--chi-du-an fanfic` · `--goc <dir>`.

* **KHÔNG quét cả máy** — chỉ ứng viên tường minh: kho nguồn + mọi
  `dist-*/<app>/` cạnh nó.
* **Nhận dạng theo LƯỢC ĐỒ + DANH TÍNH**: `memory.db` phải có `su_kien`/`ky_uc`;
  `ns` quy về `project_id` bằng cách so `khong_gian_ten(pid)` với bảng
  `projects` của `control.db` **cùng gốc**. Không quy được → BỎ QUA, không đoán.
* **Xem trước không ghi một byte nào** (bài kiểm khẳng định).
* **Sao lưu đích trước mọi lần ghi** → `<gốc>/sao_luu/<mốc>/` + `GHI_CHU.txt`
  hướng dẫn phục hồi.
* **Gieo rồi gộp**: đích trống → sao NGUYÊN cây `.router` của nguồn giàu nhất
  (giữ đúng từng id, từng dòng L0, từng mắt xích bằng chứng). Nguồn còn lại →
  **gộp quyển ký ức** với khử trùng.
* **Khử trùng**: `su_kien` theo dấu vân tay `dau`; `ky_uc` theo `ma` (mã ổn
  định theo NỘI DUNG nên ghi lại là no-op). Ánh xạ id **ưu tiên giữ nguyên id**
  khi đích đã có đúng dòng đó — nếu luôn quy về dòng đầu tiên trùng vân tay thì
  `bang_chung` sinh hàng mới mỗi lần chạy (đã vấp, xem §4.1).
* **Không ghi đè bản mới hơn**: `ky_uc` trùng `ma` thì giữ bản `ts_sua` lớn hơn
  (bài kiểm sửa nội dung ở đích rồi chạy lại và đòi nội dung đó còn nguyên).
* **Giữ nguồn gốc**: `bang_chung.su_kien_id` và `ky_uc.nguon_id` được ánh xạ
  theo id mới, nên "vì sao nhớ điều này" vẫn lần về đúng dòng L0.
* **Xung đột có cấu trúc → GIỮ CẢ HAI**: `quyet_dinh` trùng `ma` nhưng trỏ ký
  ức khác thì bản đến được **đánh số lại** (`qd_` kế tiếp); cùng `ky_uc_ma` thì
  bỏ (đã có). Không ghi đè, supersession có sẵn lo "bản nào hiệu lực".
* **L0 bất biến**: chỉ THÊM, không sửa/xoá dòng nào.
* **Không trích bí mật**: bài kiểm khẳng định `di_tru.py` không chứa
  `kho_bi_mat`/`CredRead`/`CredWrite`/`keyring`. Khoá provider vẫn ở Windows
  Credential Manager; chỉ `providers.db` (chỉ có `credential_ref`) đi theo cây.
* **Không xoá sổ cũ.** `--dat-moc` chỉ ghi `DA_DI_TRU.json` ("KHÔNG xoá tự động").

### 4.1 Ba lỗi idempotency bài kiểm/lần chạy hai bắt được (đã sửa)

1. `bang_chung` tăng 102 → 107 ở lần chạy hai: ánh xạ id quy mọi dòng trùng vân
   tay về dòng ĐẦU TIÊN ở đích, nên mắt xích bằng chứng của dòng thứ hai thành
   một khoá chính MỚI. Sửa bằng ưu tiên ánh xạ đồng nhất; và đếm `rowcount`
   thật thay vì đếm số lần thử.
2. `vien_nang` + `nhat_ky_sua` chèn vô điều kiện → mỗi lần chạy thêm 1 viên
   nang + 7 dòng audit. Sửa: khử trùng theo TOÀN BỘ nội dung hàng.
3. `chi_du_an` bị đường GIEO bỏ qua (gieo sao cả cây, gồm dự án ngoài phạm vi).
   Sửa: có `chi_du_an` thì KHÔNG gieo, đi đường gộp có lọc. Bài kiểm
   `test_cach_ly_du_an_la` khoá lại.

## 5. Di trú Fanfic — đã chạy thật

Nguồn khám phá: **3** (source-mode, `dist-v06`, `dist-v0612`). App được **đóng
sạch trước khi di trú** để SQLite checkpoint WAL (đã kiểm: cả hai `-wal` biến mất).

| Bước | Số đo |
|---|---|
| Gieo từ source-mode | 7.710 `su_kien` · 95 `ky_uc` · 102 `bang_chung` · 1 `quyet_dinh` · 9 `diem_dung` |
| Gộp `dist-v06` (fanfic) | **18 mới, 14 trùng**, 1 ky_uc trùng, 1 bằng chứng mới, 4 điểm dừng |
| Gộp `dist-v0612` (fanfic) | 2 mới, 2 trùng |
| Gộp router (hai bản) | 3 mới, 5 trùng |
| **Tổng** | **23 dòng L0 mới · 21 khử trùng · 1 mắt xích bằng chứng · 10 điểm dừng** |
| Chạy lại (×2) | `su_kien_trung=7757 ky_uc_trung=96`, **mọi số đếm bất động** → idempotent |

**Astra Decision giữ được: CÓ.** `qd_0001` → `ku_dd605f187deff41e`,
`tin_cay=user_explicit`, nguồn `chat_user#7654`, mắt xích bằng chứng trỏ đúng
dòng L0 nguyên văn.

**Thu hoạch ngoài dự tính:** dòng L0 GỐC mà người dùng gõ vào bản `dist-v06`
(10:40) — chính tuyên bố "tưởng đã mất" — nay nằm trong quyển chính tắc là
`sk#7722`, bên cạnh bản gõ lại `sk#7654`. Lịch sử L0 được cứu, không bịa.

**Bằng chứng SSH giữ được: CÓ.** 39 dòng L0 và 4 ký ức nhắc `fanficappw`, gồm
các incident nêu đúng lỗi chính tả `fanficappwrrite.pem`
(`ku_e89c32e257818256`, `ku_4020d7924251a1ac`).

## 6. Nghiệm thu LIÊN TỤC HAI CHIỀU — `control_center_v061_lien_tuc_acceptance.py`

Bản đóng gói dùng cho pha B/C: `dist-v0613` (sha `c5ca22f0…`, dựng từ mã mới).
**KHÔNG copy tay tệp DB nào.** **15/15 ĐẠT:**

| Pha | Kết quả |
|---|---|
| A. source-mode tạo D1 | ĐẠT — `qd_0002` (`NGUON-213243`) vào SỔ CHÍNH TẮC; tệp khoá ở gốc chính tắc |
| B. bản ĐÓNG GÓI mở lại | ĐẠT — tệp khoá ở **gốc chính tắc** (không cạnh EXE); thấy đúng quyển (7.736 `su_kien`, 2 quyết định) |
| B4. **source → đóng gói** | **ĐẠT** — đọc lại đúng `qd_0002` bằng diễn giải khác, **0 việc mới**: *"Theo quyết định `qd_0002` (bản ghi `ku_530d9c93b38d7478`…): Mã kiểm liên tục là `NGUON-213243`…"* |
| C. đóng gói tạo D2 | ĐẠT — `qd_0003` (`GOI-213243`) ghi vào cùng sổ |
| D2. **đóng gói → source** | **ĐẠT** — đọc lại đúng `qd_0003`, **0 việc mới** |
| D3. cả hai cùng MỘT quyển | ĐẠT — `['qd_0001','qd_0002','qd_0003']` |
| D4. Astra còn nguyên | ĐẠT |

## 7. Hồi quy sau khi đổi kiến trúc kho

**Memory-first — 10/10 ĐẠT** (`--chi recall`): tuyên bố cách cuối **42 tin** (>14
nên transcript KHÔNG thể là nguồn); Astra trả đúng kèm `ku_dd605f…`, 0 việc
mới; **sự cố SSH: 0 worker dispatch**; "production farmer còn chạy không?" vẫn
đi **live probe** (SSH 73 s trước, ACTIVE) → SỐNG > KÝ ỨC giữ nguyên.

**WebReader — 9/9 ĐẠT** (`--chi web`): `WEB_READ 200 application/json (github
api) 72061B`, **0 `tool_permission_denied`**, **0 worker** cho câu hỏi đơn
giản, trả lời grounded (World Monitor v2.10.0, 08/09/2026), nguồn gốc có băm
`a27b7780…`; việc NẶNG `fanfic.ta789-1` mang bằng chứng web trong hợp đồng.

### 7.1 Một hồi quy THẬT bắt được và sửa: Leader tự gọi công cụ bị chối

Lần chạy đầu, câu SSH **dispatch một worker**. Đọc sự kiện thì thấy nó KHÔNG
phải quyết định của Leader:

```
LEADER_UNAVAILABLE: LeaderLoi: Leader trả về rỗng; stderr: … a tool required the
"read_file" permission that headless mode cannot prompt for, so it was auto-denied
```

Leader (chạy qua `agy` headless) tự chọn `read_file` để đi đọc kho, bị TỰ CHỐI
QUYỀN, lượt trả về rỗng → engine rơi về bộ phân rã và TẠO VIỆC. Đây là chế độ
hỏng CÓ TRƯỚC (cũng thấy lúc 19:54 và 20:13 với `read_url`), nhưng nó vô hiệu
hoá đúng điều memory-first hứa. Sửa hai lớp, không nới quyền nào:

1. **`HUONG_DAN`: nói thẳng Leader KHÔNG CÓ CÔNG CỤ NÀO** — không đọc tệp,
   không mở URL, không chạy lệnh; mọi thứ cần đã nằm trong các khối dữ liệu
   (trạng thái, SỐNG, KÝ ỨC + bằng chứng L0, NỘI DUNG WEB). Thiếu thì HỎI hoặc
   uỷ thác.
2. **`engine._chat`: Leader không dùng được + câu hỏi LỊCH SỬ → KHÔNG dispatch.**
   Trả lời trực tiếp từ khối ký ức đã dựng, ghi sự kiện
   `MEMORY_ANSWER_FALLBACK`, 0 khe AG. Nguyên tắc "mất Leader không được mất
   khả năng giao việc" giữ nguyên cho việc THẬT; một câu hỏi lịch sử không phải
   việc.

Sau khi sửa: SSH recall **0 dispatch**, và Leader trả lời trung thực rằng chi
tiết bị rút gọn vì trần token, kèm mã bản ghi — thay vì bịa hoặc dispatch.

## 8. Bộ kiểm — `scripts/tests/test_goc_du_lieu_v061.py` (27)

Gốc bất biến: `%LOCALAPPDATA%`; **cwd không ảnh hưởng** (kể cả chdir sâu);
**vị trí EXE + `sys.frozen` không ảnh hưởng** (bản đóng gói và bản nguồn ra
CÙNG gốc, và gốc không chứa `dist-v99`); thư mục phiên bản/worktree không ảnh
hưởng; ghi đè tường minh > biến môi trường; mọi đường con treo từ gốc.
Danh tính: `khong_gian_ten("fanfic") == "fanfic-dcf29d1141"` bất kể cwd.
Phiên bản kho: đặt/đọc/nâng, mở lại không tạo sổ mới, sổ mới hơn mã thì DỪNG.
Một người ghi: bản thứ hai bị chặn + câu nói rõ, gốc khác không tranh nhau,
context manager. Di trú: nhận dạng theo lược đồ, bỏ `memory.db` sai lược đồ,
xem trước không ghi, **idempotent**, khử trùng vân tay, sao lưu, **không ghi đè
bản mới hơn**, **cách ly dự án lạ**, không tự di trú chính nó, đặt mốc không
xoá gì, **giữ nguồn gốc bằng chứng sau gộp**. Bí mật: `di_tru`/`duong_du_lieu`
không chạm kho bí mật.

Toàn bộ bộ kiểm cũ (ký ức, WebReader, khoá đọc/ghi, toả, leader, core) vẫn xanh.

## 9. Sao lưu / phục hồi

Trước mỗi lần ghi: `<gốc>/sao_luu/<YYYYmmdd-HHMMSS>/{control_center,memory}` +
`GHI_CHU.txt`. Phục hồi: đóng Router, xoá `control_center/` và `memory/` ở gốc
dữ liệu, copy hai thư mục từ bản sao lưu về. Không có sao lưu đám mây (cố ý).
Hiện có 3 bản sao lưu từ các lần chạy hôm nay.

## 10. Trả lời gọn (các trường đề bài)

| Trường | Giá trị |
|---|---|
| Gốc source-mode CŨ | `C:\FanficWorkers\router-control-center\.router` |
| Gốc đóng gói CŨ | `dist-v06\Router Control Center\.router`, `dist-v0612\…\.router` (sổ `dist-v061` đã bị `--clean` xoá) |
| **Gốc CHÍNH TẮC mới** | `C:\Users\nguye\AppData\Local\RouterControlCenter` |
| Namespace Fanfic ổn định | `fanfic-dcf29d1141` (project_id `fanfic`) |
| Nguồn di trú khám phá | 3 (source-mode, dist-v06, dist-v0612) |
| Bản ghi di trú / khử trùng | gieo 7.710 L0 + 95 ký ức; gộp thêm **23 L0 mới, 21 khử trùng**, 1 bằng chứng, 10 điểm dừng |
| Astra Decision giữ được | **CÓ** (`qd_0001`; dòng L0 gốc từ dist-v06 cũng được cứu: `sk#7722`) |
| Bằng chứng SSH giữ được | **CÓ** (39 L0 · 4 ký ức, gồm incident nêu `fanficappwrrite.pem`) |
| source → đóng gói recall | **PASS** (`qd_0002`, 0 việc mới) |
| đóng gói → source recall | **PASS** (`qd_0003`, 0 việc mới) |
| Khoá kho / một người ghi | **PASS** (khoá OS + câu nói rõ; sửa lỗi khoá-sai-byte) |
| Nâng phiên bản lược đồ | **PASS** (kho v1, nâng bậc, chặn sổ mới hơn mã) |
| Hồi quy memory-first | **PASS 10/10** |
| Hồi quy WebReader | **PASS 9/9** |
| Bài kiểm | 27 mới + toàn bộ bộ cũ xanh |
| Số lần sửa production | **0** |

## 11. Giới hạn còn lại (nói thẳng)

1. **Tầng `.router/` bên trong gốc chính tắc là dư một bậc** — giữ có chủ đích
   để không module nào phải đổi cách dựng đường. Thuần thẩm mỹ.
2. **Worktree nay nằm dưới gốc chính tắc.** Các worktree cũ đăng ký trong git
   của kho vẫn còn; `doi_soat()` sẽ ĐÁNH DẤU chúng, không xoá (luật "không tự
   xoá worktree" giữ nguyên).
3. **Bậc nâng phiên bản kho chỉ có v1.** Nhánh nâng đã có chỗ đặt, chưa có bậc
   thứ hai để chứng minh một lần nâng thật.
4. **`control.db` (việc/chat/sự kiện) chỉ đi theo đường GIEO**, không gộp từ
   nhiều nguồn — id việc/tin nhắn sẽ đụng nhau. Quyển KÝ ỨC thì gộp đầy đủ.
   Hệ quả: lịch sử chat/việc của `dist-v06`/`dist-v0612` không vào sổ chính
   tắc (dữ liệu vẫn còn nguyên ở sổ cũ, đã đặt mốc).
5. **Chi tiết sự cố SSH có thể bị trần token của gói ngữ cảnh rút gọn** — bản
   ghi CÓ trong sổ và tìm được qua `/api/memory/search`, nhưng gói cho Leader
   có trần riêng nên câu trả lời đôi khi nói "bị rút gọn". Đó là giới hạn NGÂN
   SÁCH, không phải mất dữ liệu; nâng nó là việc riêng (không phải task này).
6. **Bản đóng gói vẫn chịu Smart App Control** — `dist-v0613` chạy được lần
   này, nhưng bản chưa ký luôn là xổ số theo băm (xem
   `SMART_APP_CONTROL_V061.md`). Không liên quan tới gốc dữ liệu.
7. **Sổ cũ được giữ NGUYÊN** kèm `DA_DI_TRU.json`. Dọn dẹp là quyết định của
   người vận hành, không tự động.
