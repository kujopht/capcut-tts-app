# Fanfic Audio Studio

Kho này chứa **hai sản phẩm** dùng chung một pipeline TTS:

| Phần | Vị trí | Trạng thái |
|---|---|---|
| Ứng dụng desktop Windows (PySide6) | `app.py`, `desktop_app/`, `capcut_tts_api/` | Đang chạy ổn định, đã có installer |
| Nền tảng web (Next.js + FastAPI) | `web/`, `server/` | Production (`fanfic.world`) đã deploy — chưa thương mại nhưng LÀ site thật, không phải mặc định coi "chưa deploy". `staging.fanfic.world` ĐÃ RETIRED (2026-08) — không tự ý dựng lại; xem `docs/DEV_PUBLIC_STAGING.md` |

## Quy tắc bắt buộc

- **Không sửa `capcut_tts_api/`** trước khi chứng minh lỗi nằm ở đó. Đây là bản đã kiểm chứng.
- **Backend web không được import GUI.** `server/` chỉ chạm tới `desktop_app.providers.*`, `desktop_app.text_chunker`, `desktop_app.models`, `desktop_app.output_manager` — đã xác minh không kéo theo PySide6.
- **Mọi bí mật chỉ ở backend.** Trình duyệt chỉ biết `NEXT_PUBLIC_API_BASE`.
- **Không tự đổi sang giọng khác** khi tổng hợp thất bại, ở cả desktop lẫn web.
- **Không commit** model `.onnx`, audio, preview cache, `build/`, `dist/`, `installer_output/`, `node_modules/`, `.env`.
- **Mọi báo cáo viết bằng tiếng Việt**, bảng so sánh dùng cột `Hạng mục | Trước khi sửa | Sau khi sửa`.
- Không push GitHub khi chưa được yêu cầu.
- **Deploy web PHẢI dùng đúng lệnh tường minh** (sau sự cố 2026-08-18: một lần
  deploy staging bị đẩy nhầm thẳng lên production do gọi lệnh mơ hồ):
  - **Staging**: worker `fanfic-web-staging`, domain `staging.fanfic.world`,
    cấu hình `web/wrangler.staging.jsonc`, `npm run cf:deploy:staging`. ĐÃ
    RETIRED (2026-08) — KHÔNG chạy lệnh này để tự ý dựng lại staging; giữ
    nguyên cấu hình ở đây chỉ để biết đích cũ nếu cần tra cứu.
  - **Production**: worker `fanfic-web`, domain `fanfic.world`, cấu hình
    `web/wrangler.jsonc`, `npm run cf:deploy:production`.
  - Không có lệnh `cf:deploy` trần — đã bỏ cố ý. Không tự suy ra API base hay
    đích deploy từ tài liệu cũ; luôn đối chiếu `web/wrangler*.jsonc` và domain
    thật (`npx wrangler deployments list --name <worker>`) trước khi deploy.

## Lệnh thường dùng

### Desktop
```bash
.\.venv\Scripts\python.exe -m compileall -q app.py desktop_app tests
QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe -m unittest discover -s tests -t .
.\run_app.bat            # mở app
.\build_app.bat          # build EXE (onedir)
```
Installer: mở `installer.iss` bằng `C:\Users\robux\AppData\Local\Programs\Inno Setup 6\ISCC.exe`.

### Backend web
```bash
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -t .
```
Phụ thuộc backend ở `server/requirements.txt` (tách khỏi `requirements-gui.txt`,
đã gồm `boto3` cho R2). Không cài gói nào bằng tay.

### Web
```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run typecheck
npm run build
npm test
```

## Kiến trúc TTS

Mọi thứ đi qua `desktop_app/providers/registry.py::ProviderRegistry`:

- `capcut` — bọc `desktop_app/tts_service.py` (không đổi hành vi)
- `edge` — `edge-tts`, có thử lại khi dịch vụ trả rỗng
- `piper` — chạy cục bộ, model `.onnx` + `.onnx.json` ở `%LOCALAPPDATA%\FanficAudioStudio\models\piper`

Backend web bọc thêm một lớp mỏng ở `server/tts_bridge.py` — **không sao chép logic**, chỉ gọi lại chunker và registry.

## Đặc thù môi trường máy này

- Smart App Control **đang bật cưỡng chế** (`VerifiedAndReputablePolicyState=1`,
  policy `{0283ac0f-…}`). Cơ chế đo được 2026-09-10: EXE **không ký** chỉ chạy nếu
  đám mây ISG trả "known good" cho ĐÚNG băm đó; đạt thì Code Integrity ghi EA
  `$KERNEL.PURGE.ESBCACHE` lên tệp và các lần sau không hỏi lại; không đạt thì
  chặn (sự kiện 3033/3077, "we could not verify its publisher") — **mỗi bản
  PyInstaller dựng lại là một băm mới nên là một lần xổ số**: `dist-v0612` chạy,
  `dist-v061` dựng lại 50 phút sau từ CÙNG mã bị chặn vĩnh viễn. Chứng chỉ TỰ KÝ
  không giải quyết được (SAC chỉ tin CA trong Microsoft Trusted Root Program,
  không tra kho gốc cục bộ). Sau khi dựng luôn đọc `KIEM_DONG_GOI.txt`
  (`scripts/kiem_ban_dong_goi.py`); đường chạy chắc chắn không cần ký là
  `pythonw.exe` (PSF ký) chạy `scripts.control_center.desktop` từ mã nguồn.
  Đầy đủ: `docs/reports/SMART_APP_CONTROL_V061.md`. **Không tắt Smart App
  Control**, không sửa chính sách/registry — thao tác này không thể hoàn tác.
- `Documents` bị OneDrive chuyển hướng.
- ffmpeg/ffprobe ở `%LOCALAPPDATA%\Microsoft\WinGet\Links\`.
- Inno Setup nằm ở phạm vi người dùng, không phải `Program Files`.

## AI engineering router (V2)

Chính sách chọn model/effort/subagent/**provider** cho công việc kỹ thuật
trong kho này (Haiku cho tra cứu, Sonnet mặc định, Opus cho việc khó/rủi
ro cao, Fable chỉ dành cho việc CỰC LỚN — cộng thêm từ V2: Google
Antigravity CLI [`agy`, quota Google AI Pro riêng] và Codex CLI làm hai
compute pool ngoài, dùng khi lượng Claude đang căng hoặc cần review độc
lập khác họ model) — xem `docs/AI_ROUTER.md` cho đầy đủ, và
`.claude/agents/` cho các subagent Claude cụ thể (`explorer`,
`test-analyst`, `builder`, `frontend-builder`, `code-reviewer`,
`incident-architect`, `long-horizon-lead`). Không phải một tính năng sản
phẩm. Không lưu credential của Antigravity/Codex trong repo — cả hai đọc
phiên đăng nhập từ nơi lưu trữ riêng của hệ điều hành/CLI.

**Thứ tự ưu tiên (BẮT BUỘC đọc trước khi chọn model):**

```
ACTIVE PROFILE toàn cục (~/.claude/CLAUDE.md)
        >
chuyên biệt hoá của repo (file này, docs/AI_ROUTER.md)
        >
routing mặc định (bảng tier V1)
```

Bảng tier trong `docs/AI_ROUTER.md` mô tả hồ sơ **BALANCED**. Khi hồ sơ
toàn cục khác BALANCED, hồ sơ đó THẮNG mọi câu "mặc định" trong tài liệu
này. **Phải ĐỌC hồ sơ đang bật, không được đoán và cũng không được chép
giá trị đó vào đây** — nó chỉ tồn tại ở một nơi duy nhất:

```bash
grep -A3 'ACTIVE PROFILE' ~/.claude/CLAUDE.md
```

**Router được THỰC THI bằng mã, không chỉ bằng văn xuôi.** Trước mỗi việc
kỹ thuật đáng kể, chạy quyết định định tuyến (không tốn quota):

```bash
python scripts/ai_router_dispatch.py --task-class <CLASS> --risk <LOW|MEDIUM|HIGH> --dry-run
echo "..." | python scripts/ai_router_dispatch.py --task-class ORDINARY_REVIEW --risk LOW
```

`scripts/ai_router_dispatch.py` giữ bảng định tuyến trong mã, tự tìm
`agy`/`codex`, tự phân giải model đang sống, chặn nội dung giống
credential, và TỰ GHI telemetry — không thể dispatch mà quên ghi.
`SECURITY_REVIEW` không bao giờ đi tới Codex (bằng chứng thật 2026-08-28:
Codex từ chối review bảo mật). Xem `docs/AI_ROUTER.md` mục "Precedence" và
"Enforcement".

**Quan hệ với router toàn cục:** `~/.claude/CLAUDE.md` (tài khoản Windows
này) chứa phần CHUNG của chính sách này (tier model chung, quota-aware
routing, review chéo model, chính sách context/test) — áp dụng cho MỌI
repo trên máy này, không riêng Fanfic. File này + `docs/AI_ROUTER.md` chỉ
còn phần THẬT SỰ đặc thù Fanfic (production/Appwrite/nội dung, quy ước
frontend riêng, các con số benchmark của repo này) — Claude Code tự nối
cả hai (global rồi đến local), không cần lặp lại phần chung ở đây. Đừng
đưa quy tắc riêng của Fanfic ngược lên `~/.claude/` — file đó phải luôn
dùng được cho một repo bất kỳ khác.

## Router Control Center (V0.2)

Phòng điều khiển cho Router V4: mở một dự án, gõ mục tiêu vào ô chat, Router
tự phân rã việc, chọn agent theo năng lực, dựng worktree cô lập, dựng/dùng
lại phiên agent, khoá tài nguyên, chạy, báo cáo — không phải mở tay terminal
Claude/Codex/Antigravity nào.

```bash
.\router-cc-web.cmd         # GIAO DIEN CHINH (V0.2) — bam doi duoc
./router-cc-web             # (ban bash)

.\router-cc-gui.cmd         # Qt desktop — duong GO LOI / du phong
./router-cc                 # TUI Textual — duong GO LOI / du phong
./router-cc --headless      # anh chup JSON, khong can TTY
./router-cc --chat "..."    # gui mot cau vao o chat roi thoat
```

**Từ V0.2, giao diện web cục bộ là đường chính.** `router-cc-web.cmd` tự
sinh token phiên, xin một cổng rỗng trên `127.0.0.1`, mở trình duyệt, rồi
chạy server — không PowerShell, không Node, không tự khởi động backend.
Qt và TUI ở lại làm đường gỡ lỗi. **Cả ba dùng chung một sổ SQLite**, nên
mở cạnh nhau vẫn thấy cùng dự án/việc/phiên.

Ba điều không được phá ở tầng API cục bộ (`webapi.py`), mỗi điều có bài
kiểm ở `scripts/tests/test_control_center_webapi.py` nên **CI cưỡng chế**:

1. **Token mọi request, kể cả `GET`.** Trình duyệt cho phép request
   cross-origin (nó chỉ ngăn *đọc* phản hồi), nên không có token thì một
   trang web bất kỳ đang mở có thể `POST /api/chat`.
2. **Kiểm `Host` TRƯỚC kiểm token** — chặn DNS rebinding.
3. **Không CORS, bind `127.0.0.1`, không bao giờ `0.0.0.0`.**

Bốn bất biến của tầng đính kèm (`attachments.py`) — xem
`docs/CONTROL_CENTER.md` mục 12: nhị phân không vào SQLite; đường dẫn lưu
trữ do backend sinh từ băm nội dung; đọc chỉ qua `attachment_id` và kiểm
containment sau `resolve()`; agent chỉ nhận đính kèm của đúng việc của nó.

Ba luật của tầng Qt, và cả ba đều có bài kiểm khoá lại
(`tests/test_control_center_gui_*.py`, 95 bài):

1. **Không giành Ctrl+C/V/X/A.** Không một `QShortcut`/`QAction` nào — ở
   BẤT KỲ phạm vi nào, kể cả `WindowShortcut` mặc định — được đăng ký các
   tổ hợp đó. Giành một cái là lấy mất clipboard của mọi ô chỉ-đọc.
2. **Ô chỉ-đọc dùng `setReadOnly(True)`, không bao giờ `setEnabled(False)`**
   — cách thứ hai làm mất luôn khả năng chọn.
3. **Vẽ lại không được giết vùng đang bôi đen.** Mọi chỗ ghi văn bản theo
   nhịp phải đi qua `dat_van_ban_giu_chon()`. Ghi thô bằng
   `setPlainText()` mỗi giây là một **lỗi clipboard**, dù trông như lỗi
   hiệu năng.

Mã ở `scripts/control_center/`; đầy đủ ở `docs/CONTROL_CENTER.md`; bằng
chứng chạy thật ở `docs/reports/CONTROL_CENTER_V01_PROOF.md`.

**V0.3** thêm Project Leader (ô chat quyết CHAT/STATUS/CONTROL/WORK, kết
quả phải chảy về chat) — `docs/reports/CONTROL_CENTER_V03_LEADER.md`.
**V0.4** làm lại UX: không cửa sổ console nào được nhấp lên, một màn hình
thấy hết, ô soạn tự trống + giữ focus, chủ đề tối, ảnh nền —
`docs/reports/CONTROL_CENTER_V04_UX.md`, và luật ở
`docs/CONTROL_CENTER.md` §14b/§14c. Luật quan trọng nhất của V0.4: **mọi
`subprocess.run`/`Popen` trên đường của ứng dụng phải mang
`**an_cua_so()`** — có bài kiểm AST trên cả bao đóng khởi động cưỡng chế.

**V0.5** thêm quan sát SỐNG: bậc thẩm quyền LIVE > kho/bền > ký ức > suy
luận, sáu trạng thái mà chỉ `DOWN` là khẳng định xấu —
`docs/reports/PROJECT_OBSERVABILITY_V05.md`.
**V0.6** thêm KÝ ỨC DỰ ÁN vô hạn + ảo hoá ngữ cảnh: lịch sử thô chỉ-thêm
(L0) trên đĩa cục bộ, ký ức có cấu trúc trỏ về bằng chứng (L1), viên nang
(L2), điểm dừng để phiên sau tiếp tục không cần dán handoff (L3); Leader
nhận một GÓI NGỮ CẢNH có trần token ĐỘC LẬP với kích thước lịch sử, kèm
`leader.LUAT_KY_UC` ở mọi lượt có khối — ký ức KHÔNG BAO GIỜ trả lời câu
hỏi hiện tại khi có probe sống. Sổ ở `<gốc>/.router/memory/<ns>/` (cạnh
`control.db`, KHÔNG trong cây git của dự án), mỗi dự án một sổ. Không xoá
gì ở V0.6. `docs/reports/PROJECT_MEMORY_V06.md`, mã ở
`scripts/control_center/memory/`.
**V0.6.1** sửa khuyết tật V0.6 (tuyên bố tường minh của người dùng nằm ở L0
mà `Decisions = 0`): ĐỀ BẠT TẤT ĐỊNH (không LLM) tuyên bố → quyết định /
ràng buộc / yêu cầu / sự cố / quy trình / sự thật, `authority =
user_explicit`, thay thế kiểu ADR hai chiều, nguồn gốc trỏ về L0; NHẬP LỊCH
SỬ (backfill) từ sổ Router, git, tài liệu, phiên Claude CỦA ĐÚNG KHO (theo
`git worktree list`) — idempotent, chỉ đọc, lịch sử luôn `backfill` không
bao giờ `user_explicit`; KIỂM TOÁN bể Antigravity (8 khe chứng minh từ sổ
đăng ký, Leader ghim AG01 nay HIỆN RA với bộ lập lịch); PROVIDER NGOÀI + KHO
BÍ MẬT (Windows Credential Manager, `credential_ref` trong sổ, giá trị
không bao giờ vào SQLite/ký ức/log/prompt; provider vào fabric ở trạng thái
KHÔNG nhận dispatch). Nút **Providers** ở thanh trên. TOẢ ĐA AGENT: "gọi N
agent…"/"mỗi agent một…" (đọc từ câu người dùng, tất định — `toa.py`) → 1
việc cha + N việc con độc lập có ràng buộc không trùng, sức chứa đo từ
fabric (trừ chỗ Leader chiếm), con tránh runtime anh em, gộp kết quả có
nguồn gốc; `--max-parallel 0` = trần tự theo bể (3..12); khoá tài nguyên có
CHẾ ĐỘ READ/WRITE (đọc song song, ghi độc quyền, chuỗi cũ = WRITE), tài
nguyên theo TỪNG con, việc đọc git nhận nhật ký do Router đọc (agent headless
không chạy được shell — quyền của nó KHÔNG được nới);
`docs/reports/MULTI_AGENT_FANOUT_V061.md`.

**LUẬT CHUNG đã trả giá BỐN lần — `agy --print` (headless) TỰ CHỐI mọi công cụ
cần prompt quyền** (`command`, `read_file`, `read_url`) — **kể cả khi chính
LEADER gọi chúng** (lượt trả về rỗng → `LeaderLoi` → rơi về bộ phân rã → tạo
việc, đúng thứ ta muốn tránh). Đừng cấp quyền rộng, đừng
`--dangerously-skip-permissions`: **Router làm phép đọc an toàn rồi đính BẰNG
CHỨNG vào hợp đồng/nhắc nhở**, và `HUONG_DAN` nói thẳng với Leader rằng nó
KHÔNG CÓ CÔNG CỤ NÀO. Ba hiện thực cùng mẫu: `nguon_git.git_nhat_ky_doc` (lịch
sử git), `web_reader.doc_web` (web công khai, an toàn SSRF,
`docs/reports/WEB_READER_V061.md`), và ký ức dự án (`memory/`). Câu hỏi LỊCH
SỬ/KIẾN THỨC DỰ ÁN và câu hỏi có URL đơn giản **không được** tốn một AG slot —
xem `leader.LUAT_LICH_SU` / `leader.LUAT_WEB`;
`docs/reports/PROJECT_MEMORY_RECALL_V061.md`.

**GỐC DỮ LIỆU CHÍNH TẮC — `scripts/control_center/duong_du_lieu.py` là NƠI DUY
NHẤT định nghĩa nó.** Dữ liệu bền nằm ở `%LOCALAPPDATA%\RouterControlCenter`
(+`.router/`), **không** cạnh EXE, **không** `parents[2]`, **không** `cwd`.
Trước 2026-09-10 gốc neo vào vị trí mã nên cùng `project_id` ra nhiều quyển sổ
độc lập — đúng lý do tuyên bố "GPT-6 Astra…" gõ ở `dist-v06` không hiện ra ở
bản source-mode. Thứ tự: `--root` (bài kiểm) → `$ROUTER_CC_DATA_ROOT` → chính
tắc. Thêm: `kho.json` giữ **phiên bản KHO tách khỏi phiên bản ứng dụng** (sổ
mới hơn mã thì DỪNG), `KhoaKho` cho **một người ghi** (bản thứ hai nhận câu
"Kho dữ liệu Router đang được dùng"), và `di_tru.py` +
`scripts/router_cc_di_tru.py` để gộp sổ cũ (xem trước → sao lưu → khử trùng →
idempotent → không xoá gì). Đầy đủ:
`docs/reports/GOC_DU_LIEU_CHINH_TAC_V061.md`.

Báo cáo:
`docs/reports/PROJECT_MEMORY_V061.md`,
`docs/reports/PROVIDER_CREDENTIAL_ARCHITECTURE_V061.md`,
`docs/reports/ANTIGRAVITY_POOL_AUDIT_V061.md`; mã ở
`scripts/control_center/memory/{de_bat,nhap_khau}.py` và
`scripts/control_center/providers/`.

**V0.7 Phase 1** (nhánh `feat/v07-fanfic-adoption`, chưa merge/tag) thêm
NHẬN DỰ ÁN CÓ SẴN + VIÊN NANG DỰ ÁN: `nhan_du_an()` nhận một kho THẬT
**chỉ đọc** (không sao chép/dời/khởi tạo lại/ghi gì vào kho; danh tính suy
từ gốc worktree + commit gốc, KHÔNG từ nhánh); `vien_nang_du_an.py` dựng 19
mục có `{gia_tri, trang_thai, nguon, bang_chung}` với UNKNOWN là giá trị
hợp lệ và giá trị SỐNG không bị đóng băng; `kiem_lien_tuc.py` kiểm toán 13
hạng mục. Luật quan trọng nhất của V0.7: **bản gọn nạp cho Leader chọn mục
THEO CÂU HỎI**, và **dòng báo cắt phải NÊU TÊN mục chưa nạp** — bảng ưu
tiên cố định + dòng chỉ-đếm là lý do đo được khiến Leader BỊA ("5
Antigravity account" trong khi sổ ghi 8). Xem
`docs/reports/NHAN_DU_AN_VIEN_NANG_V07.md` và `docs/CONTROL_CENTER.md` §18
(luật 13–17).

**V0.7 — PROBE VẬN HÀNH** (`scripts/control_center/probe_van_hanh.py`): câu
hỏi về PRODUCTION (systemd/rclone/Drive/R2) không được biến thành việc phân
tích KHO — đo được ở `fanfic.t2efd-1`: worker phải gọi công cụ `command` và
`agy --print` tự chối (`tool_permission_denied`). Router đo hộ bằng MÔI GIỚI
CÓ KIỂU: 9 thao tác chỉ đọc, API **không nhận chuỗi lệnh**, tham số kiểm theo
cấu hình dự án, lưới thứ hai chặn động từ đột biến, **không nâng quyền**. Ai
thiếu bằng chứng thì phân loại **F** kèm danh sách thiếu gì, không đoán
nguyên nhân. Việc mang "hình dạng bảo mật" nay tránh Codex NGAY LÚC XẾP CHỖ
(trước đây chết ở `BLOCKED`, và lời nhắc công cụ tiêu chuẩn của mọi việc đều
chứa chữ "quyền" nên gần như mọi việc xếp vào Codex đều chết).
`docs/reports/PROBE_VAN_HANH_V07.md`, `docs/CONTROL_CENTER.md` §19 (luật
18–21).

**V0.7 — LÀM CỨNG**: (a) KHÔNG nới quyền `status.json` của farmer — nó có
hai ống dẫn văn bản tự do (`archive.detail` ← `stderr` thô của `rclone`,
`lanes[*].errors[]` ← ngoại lệ bất kỳ) nên không chứng minh được là sạch;
đường đúng là ẢNH CHỤP ĐÃ LỌC riêng (`observability.json`, `644`, danh sách
CHO PHÉP, lỗi quy về mã trong bộ ĐÓNG) — mã đề xuất + kế hoạch triển khai ở
`docs/deploy/fanfic_farmer_observer/`, **chưa triển khai, cần người vận hành
duyệt**. `rclone.conf` giữ `600`, và Router tự chặn thêm một lớp
(`la_tep_bi_mat` — danh sách CẤM thắng danh sách cho phép). (b) Một TỪ ĐƠN
không được làm trọng tài phân loại bảo mật: chữ "quyền" trong lời nhắc công
cụ tiêu chuẩn từng làm MỌI việc xếp vào Codex bị từ chối rồi chết ở
`BLOCKED`. Nay phân loại bằng CỤM TỪ chuyên môn, chỉ trên phần NGƯỜI VIẾT, ở
một nguồn duy nhất (`router_v3.policy`); runtime khai báo thứ nó từ chối;
xếp chỗ là RÀO CỨNG (`cam_runtime`); từ chối vì CHÍNH SÁCH thì định tuyến
lại có trần + nguồn gốc. `docs/reports/LAM_CUNG_V07.md`,
`docs/CONTROL_CENTER.md` §20 (luật 22–24).

**Nó KHÔNG thay Router V4** — nó gọi `Scheduler`/`Executor` của V4 nguyên
vẹn và chỉ thêm thứ V4 cố ý không có: trạng thái sống lâu hơn một mission
(dự án, phiên dùng lại được, khoá tài nguyên, phong bì quyền AUTO/GATED,
bền qua khởi động lại). Thay đổi duy nhất chạm V4 là một tham số tuỳ chọn
`Executor(worktree_provider=...)`, mặc định `None` = hành vi cũ.

Ba luật không được phá khi sửa gói này:
1. **Không nới rào an toàn.** Không `--dangerously-skip-permissions`, không
   `bypassPermissions`, `destructive_actions_allowed` luôn `False`, việc
   chạm lớp GATED thì DỪNG chờ người.
2. **Không bịa số usage.** Không đo được thì `UNAVAILABLE` + `None`, không
   phải `0`.
3. **Không tự xoá worktree.** Chỉ đánh dấu.

## Tìm/đọc trong kho: dùng `scripts/tim.py`, không dùng `cd && grep`

```bash
python scripts/tim.py "TrangThai"                      # tìm
python scripts/tim.py "def thu" scripts/control_center # giới hạn phạm vi
python scripts/tim.py --doc scripts/store.py --tu 1 --den 60   # đọc
python scripts/tim.py --kiem                           # chính sách loại trừ
git grep -n "TrangThai" -- scripts/                    # cửa thứ hai
```

**Đây không phải một quy ước cho ngoan — nó là cách duy nhất phạm vi đọc
tự chứng minh được.** Claude Code phân giải những đường dẫn mà một lệnh
Bash NHẮC TÊN rồi đối chiếu với các luật `Read(...)` deny. Sau một `cd`,
thư mục hiệu lực không suy ra được TĨNH, nên nó không thể chứng minh phép
tìm không chạm `.env` — và phải hỏi người. `tim.py` suy gốc kho từ **vị
trí của chính tệp đó**, nên `cd` trở thành vô nghĩa thay vì bị cấm.

Hai điều nữa đã đo được, và cả hai đổi cách làm việc:

* **Thư mục CHƯA ĐƯỢC TIN làm hồ sơ quyền của kho biến mất** — cả 241
  luật `allow` lẫn hook `PreToolUse` đều bị bỏ qua, và mỗi worktree Router
  vừa dựng là một thư mục như thế. Sửa:
  `python scripts/kiem_quyen.py --tin-cay <đường>`.
* **Tầng an toàn sống ở `~/.claude/settings.json`**, không ở hồ sơ kho —
  vì chỉ tầng đó luôn có hiệu lực. `python scripts/kiem_quyen.py --kiem`
  kiểm cả hai tầng và in ma trận AN TOÀN / NGUY HIỂM.

Đầy đủ, kèm số đo: `docs/reports/QUYEN_CLAUDE_TIN_CAY.md`.

## Trạng thái

Xem `docs/HANDOFF.md` để biết mốc nào đã xong và việc tiếp theo.
