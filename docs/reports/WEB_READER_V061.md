# WebReader — Router tự đọc web công khai (khuyết tật `read_url` headless, V0.6.1, 2026-09-10)

Phạm vi: NỀN ĐỌC chỉ-đọc. KHÔNG browser automation, không DOM/click/type/đăng
nhập/screenshot/localhost — đó là các lớp sau (Browser Runtime). Không
`--dangerously-skip-permissions`, không nới chính sách quyền của agent.

## 1. Hiện tượng

Người dùng gõ: `https://github.com/koala73/worldmonitor/releases/tag/v2.10.0
github này là gì v`. Router tách đúng MỘT việc analysis chỉ-đọc, dispatch AG02.
Việc **FAILED sau ~17s**:

```
jetski: no output produced — a tool required the "read_url" permission that
headless mode cannot prompt for, so it was auto-denied.
failure_reason: tool_permission_denied
```

## 2. Đường năng lực web hiện tại (trace, không đoán)

| Chặng | Sự thật đo được |
|---|---|
| `read_url` định nghĩa ở đâu | **KHÔNG ở Router.** Nó là công cụ của CLI Antigravery (`agy`). Router không cấp, không cấm riêng nó. |
| Hồ sơ quyền của worker | `PoolAntigravityAdapter` / `AntigravityLauncherAdapter`: việc CHỈ ĐỌC → **không cờ quyền nào**; việc CÓ GHI → `--mode accept-edits` + `--add-dir <worktree>`. |
| AG01..AG08 giống nhau? | **Giống hệt** — cùng một lớp adapter, cùng `dangerously_skip_permissions=False`. Cờ nguy hiểm bị chặn ở MỨC MÃ (`_KHONG_BAO_GIO_DUNG`), không chỉ ở tài liệu. |
| Nạp lúc nào | Lúc `start_session()` (mỗi phiên worker), không nạp lại giữa phiên. |
| Router có fetch URL sẵn? | **KHÔNG.** `urllib` chỉ dùng cho API cục bộ/desktop shell/provider — không có bộ đọc web nào. |
| Vì sao headless không đọc được | `agy --print` không hiển thị được prompt quyền nên **tự chối** mọi công cụ cần duyệt (`read_url`, `read_file`, `command`). Lượt kết thúc RỖNG; adapter đọc stderr và gắn `tool_permission_denied`. |

Đây ĐÚNG chế độ hỏng đã gặp hai lần trước: `command` (2026-09-08, việc ghi
tệp) và `read_file` (2026-09-10, con "git history" của toả). Mẫu sửa đã có:
**Router làm phép đọc an toàn rồi đưa BẰNG CHỨNG cho model** (`nguon_git.
git_nhat_ky_doc`). WebReader là cùng mẫu đó cho web.

## 3. WebReader — `scripts/control_center/web_reader.py`

API: `WebReader.read(url)` · `.metadata(url)` (HEAD) · `.extract_text(url)`,
và điểm vào `doc_web(url)` (ưu tiên adapter GitHub). Trả `KetQuaDoc` — **nguồn
gốc đầy đủ**: `url_goc`, `url_cuoi`, `ts`, `trang_thai`, `content_type`,
`bam_noi_dung` (sha256), `so_byte`, `chuyen_huong`, `nguon`.

Xử lý: chuyển hướng (tối đa 5, **kiểm SSRF LẠI mỗi bước**), timeout 12s, trần
3 MB, charset từ header rồi `<meta>`, HTML → rút text (bỏ script/style, lấy
`<title>`), JSON → in đẹp, `text/*` → nguyên văn. `Accept-Encoding: identity`.
User-Agent trung thực, KHÔNG giả trình duyệt. Không cookie, không header xác
thực, không credential — "đọc web công khai" KHÔNG kéo theo "duyệt web có
đăng nhập".

### 3.1 An toàn SSRF (chặn mặc định, lý do CỤ THỂ)

Chặn: scheme ngoài http/https (`file`, `ftp`, `data`, `javascript`, `gopher`);
`user:pass@`; host nội bộ theo tên (`localhost`, `*.local`, `*.internal`,
`metadata.google.internal`); IP loopback / RFC1918 / link-local / ULA /
multicast / reserved; **metadata đám mây** (`169.254.169.254`,
`fd00:ec2::254`, `100.100.100.200`).

**Phân giải DNS an toàn:** `getaddrinfo` rồi kiểm **MỌI** địa chỉ trả về — một
hostname công khai trỏ về `10.x` bị chặn (bypass tầm thường). Rồi kết nối
**GHIM vào đúng IP đã kiểm** (socket thô + `wrap_socket(server_hostname=host)`
để SNI/chứng chỉ vẫn theo tên) — chống DNS rebinding giữa lúc kiểm và lúc nối.
Tham số truy vấn giống credential được nhận diện (`_QP_NHAY_CAM`) để không log
giá trị.

**Một lỗi THẬT bài kiểm bắt được:** `SSRFLoi` là con của `ValueError`, nên bản
đầu đặt `raise SSRFLoi` *bên trong* `try/except ValueError: pass` (khối thử
phân tích IP) — phép từ chối bị **NUỐT**, hàm rơi xuống nhánh DNS. Đã tách
phép thử-phân-tích khỏi phép kiểm; bài `test_chuyen_huong_ve_ip_rieng_bi_chan`
khoá lại.

### 3.2 Adapter GitHub công khai (không cần token)

`github.com` → REST API công khai (sạch hơn HTML nặng JS):
`/releases/tag/<tag>` → `/repos/{o}/{r}/releases/tags/{tag}`; `/releases` →
`releases/latest`; `/issues|/pull/<n>` → `issues/{n}`; repo/`/tree/...` →
`/repos/{o}/{r}` + `/readme` (giải base64). `raw.githubusercontent.com` đi
đường `read()` thường (đã là text/HTTPS). Không token; giới hạn theo IP là đủ
cho nội dung công khai. Đo thật: trang release 471 KB HTML (đầy nav) so với
72 KB JSON có **đúng** tên release + changelog.

## 4. Hỗ trợ worker headless — Router đọc HỘ (phương án A)

Đề bài cho hai lựa chọn; chọn **A** (Router đưa nội dung), KHÔNG cấp `read_url`:

* **Leader**: `engine._khoi_web(text, project_id)` — câu có URL → Router đọc,
  đính khối `NỘI DUNG WEB` vào nhắc nhở kèm `leader.LUAT_WEB`. Ghi sự kiện
  `WEB_READ` (URL, trạng thái, băm, nguồn) làm nguồn gốc.
* **Worker**: `engine._kem_web_vao_hd(text, hd)` đính bằng chứng web vào
  **mục tiêu hợp đồng** (như `_kem_nhat_ky_git`), cho cả việc thường và việc
  toả (đọc MỘT lần, dùng cho mọi con). Khối nói thẳng: "KHÔNG dùng
  read_url/lệnh — headless bị từ chối quyền; phân tích NGAY trên nội dung này".

Vì sao A: quyền của agent **không đổi một chút nào**, mọi AG01..AG08 giữ đúng
hồ sơ cũ, và bề mặt mạng nằm trong Router (nơi có SSRF guard + bài kiểm) chứ
không nằm trong một CLI của nhà cung cấp.

## 5. Chính sách định tuyến (không tốn worker cho câu hỏi tầm thường)

`LUAT_WEB` (nhét khi có khối WEB): câu ĐƠN GIẢN ("URL này là gì") → trả lời
TRỰC TIẾP, `y_dinh = CHAT`, **không uỷ thác** — Router đã đọc, một AG slot cho
việc đó là lãng phí. Việc NẶNG ("đọc rồi SO SÁNH/ĐỀ XUẤT/VIẾT") → vẫn WORK, và
worker nhận cùng bằng chứng. Khối WEB báo thất bại (vd URL nội bộ bị chặn) →
nói rõ lý do, không dispatch để "thử lại" (headless cũng bị chặn).

## 6. Bộ kiểm — `scripts/tests/test_web_reader_v061.py` (19)

Tất định, không phụ thuộc mạng (monkeypatch `_tai_mot`/`_gh_api`/`getaddrinfo`);
một smoke mạng thật tự bỏ qua khi offline.

**TỪ CHỐI** (mỗi cái kèm lý do cụ thể, không "hỏng" chung): `file://`, `ftp://`,
`gopher://`, `data:`, `javascript:`; `user:pass@`; `localhost`, `*.local`,
`metadata.google.internal`; `127.0.0.1`, `[::1]`, `10.0.0.5`, `172.16.4.4`,
`192.168.1.1`, `169.254.169.254`; hostname công khai phân giải về `10.x`;
**chuyển hướng từ HTTPS công khai về `127.0.0.1`**.
**CHO PHÉP**: host công khai; HTML (rút title+text, bỏ script); JSON (in đẹp);
chuyển hướng giữa hai URL công khai; GitHub release/issue/repo+README đúng
endpoint; nguồn gốc đủ trường; `rut_url` từ câu người dùng.

## 7. Nghiệm thu THẬT — source-mode, `router-cc-desktop.cmd`, gốc dữ liệu thật

`scripts/control_center_v061_ky_uc_web_acceptance.py --chi web`, app source-mode
pid 3552 cổng 59425, dự án `fanfic`, kịch bản NGUYÊN VĂN của người dùng.
**9/9 ĐẠT:**

| Bước | Kết quả |
|---|---|
| Router đọc hộ (sự kiện `WEB_READ`) | ĐẠT — `…/releases/tag/v2.10.0 -> 200 application/json (github api) 72061B` |
| **KHÔNG `tool_permission_denied`** | ĐẠT — 0 sự kiện (trước: FAILED sau 17s) |
| **KHÔNG tốn worker** cho câu đơn giản | ĐẠT — việc mới = 0 |
| Trả lời GROUNDED nội dung thật | ĐẠT — "trang phát hành **v2.10.0** của **World Monitor** (`koala73/worldmonitor`), đăng 08/09/2026, các cập nhật chính…" |
| Nguồn gốc ghi lại | ĐẠT — url + url_cuoi + status 200 + băm `a27b7780…` + nguồn `github` |
| Việc NẶNG → hợp đồng worker mang bằng chứng web | ĐẠT — `fanfic.t6006-1`, mục tiêu 8451 ký tự có khối WEB |
| **Worker headless chạy được** | ĐẠT — `fanfic.t6006-1` **DONE**, AG02, gemini-3.8-flash-medium, 61.3s, `failure_reason` RỖNG; sản phẩm: so sánh đóng gói desktop World Monitor vs Router + 3 điểm tích hợp |
| Không rò bí mật | ĐẠT — 0 chuỗi giống credential trong toàn bộ state dự án |
| Không sửa production | ĐẠT — kho Fanfic không có tệp tracked nào đổi |

## 8. Tương thích Browser Runtime tương lai

WebReader độc lập với mọi thứ "browser": không tiến trình trình duyệt, không
DOM, không phiên. Các lớp sau (session/DOM/click/type/login/screenshot/
localhost) sẽ nằm TRÊN nó và cần chính sách riêng — còn WebReader vẫn là đường
ĐỌC RẺ cho câu hỏi đơn giản, và vẫn là cách duy nhất đưa bằng chứng web cho
worker headless mà không cấp quyền mạng cho agent.

## 9. Trả lời gọn (các trường đề bài)

| Trường | Giá trị |
|---|---|
| Nguyên nhân gốc | `agy --print` (headless) tự chối mọi công cụ cần prompt quyền; `read_url` là một trong số đó. Router không có đường đọc web nào để thay. |
| Nguồn của quyền `read_url` | CLI Antigravity, không phải Router. Router chỉ chọn `--mode accept-edits`/`--add-dir` cho việc ghi; việc đọc không xin cờ nào. |
| WebReader Router-native | **PASS** — `web_reader.py`, chỉ đọc, nguồn gốc đầy đủ |
| Bảo vệ SSRF / mạng riêng | **PASS** — 13 lớp chặn + kiểm mọi IP phân giải + ghim IP; 19 bài kiểm |
| Đọc GitHub release | **PASS** — API công khai, không token, nội dung sạch |
| AG headless đọc web | **PASS** — qua bằng chứng Router đính; `fanfic.t6006-1` DONE 61s |
| AG accounts nhận chính sách | AG01..AG08 — **giống hệt**, không đổi gì (Router đọc hộ) |
| Câu URL đơn giản không tốn worker | **PASS** — 0 việc mới |
| Việc URL sâu qua worker | **PASS** — hợp đồng mang bằng chứng, worker DONE |
| Số lần sửa production | **0** |
