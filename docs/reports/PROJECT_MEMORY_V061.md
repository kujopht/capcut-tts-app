# Ký ức dự án V0.6.1 — đề bạt tất định, thay thế, nguồn gốc, nhập lịch sử

Nhánh `feat/v061-memory-provider-vault` · 2026-09-10 · chưa tag/merge · baseline
`dist-v04`/`dist-v05`/`dist-v06` giữ nguyên. Bản đóng gói mới: `dist-v061`.

Báo cáo anh em: `PROVIDER_CREDENTIAL_ARCHITECTURE_V061.md` (Part D/E/F),
`ANTIGRAVITY_POOL_AUDIT_V061.md` (Part C).

## 1. Khuyết tật V0.6 — đo được, không phải suy

Nghiệm thu tay bản EXE V0.6: người dùng gõ

> hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra chỉ được dùng cho
> các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc định cho task thường.

Câu đó **có** vào L0 (lịch sử thô) và **có** tìm lại được sau khi mở lại app.
Nhưng tab Memory hiện `Decisions = 0`, và Leader nói chưa có quyết định `qd_*`
nào. Nguyên nhân ở `memory/ghi_nhan.py` V0.6: tin nhắn người dùng chỉ được ghi
làm sự kiện `chat:user`; con đường L0 → L1 (`_chung_cat`) chỉ biết đến sự kiện
của Router (`TASK_STATE`, `LIVE_PROBE`, …) và kết quả worker. Không có gì đọc
**tuyên bố** của người dùng. Ghi quyết định qua `POST /api/memory/decision`
thì đúng — nhưng người dùng nói bằng ngôn ngữ tự nhiên trong ô chat, và Leader
(vốn có `record_memory`? — không: V0.6 chưa có hành động đó) không có cách nào
ghi.

| Hạng mục | Trước khi sửa (V0.6) | Sau khi sửa (V0.6.1) |
|---|---|---|
| Câu "hãy ghi nhớ đây là một quyết định của project: …" | vào L0, `Decisions = 0` | vào L0 **và** thành `qd_0001` (`authority = user_explicit`, `nguồn = chat_user`, bằng chứng trỏ về đúng dòng L0) — tất định, không LLM, ngay tại cổng vào |
| "thay cho qd_0001, …" | không có khái niệm thay thế qua chat | `qd_0002` hiệu lực; `qd_0001` **SUPERSEDED** nhưng vẫn truy được; liên kết hai chiều |
| "quyết định này ghi khi nào / ai nói / vì sao nhớ?" | chỉ có với quyết định ghi qua API | mọi bản ghi mang `ts_su_kien`, `nguon_loai`, `nguon_id`, `bang_chung → su_kien L0` |
| Leader gặp một tuyên bố | im lặng (không biết có bản ghi) | nhận dòng "VỪA GHI TỰ ĐỘNG TỪ TIN NHẮN NÀY … `qd_xxxx`" trong khối ký ức; hướng dẫn: XÁC NHẬN bằng mã, KHÔNG ghi lại; có `record_memory` cho ký ức nổi lên từ hội thoại (`authority = leader`, thấp hơn) |
| Ràng buộc / yêu cầu / sự thật | không có loại | `LoaiKyUc.CONSTRAINT / REQUIREMENT / FACT` (+ `INCIDENT`, `PROCEDURAL` sẵn có) |
| Quá khứ trước khi ký ức được bật | không có | nhập lịch sử (Part B) |

## 2. Đề bạt tất định — `memory/de_bat.py`

Không LLM. Hai tầng dấu hiệu trên văn bản đã gấp dấu (`gap_dau`):

1. **Dấu hiệu TUYÊN BỐ** (bắt buộc): "ghi nhớ (giúp/rằng)…", "quyết định (của
   project/dự án):", "đây là một quyết định/ràng buộc/yêu cầu/sự cố/quy trình",
   "từ giờ (rule|quy tắc) là", "sự cố:", "SOP/quy trình:", "sự thật/ghi nhận:"…
   **Một câu chỉ có "không được" mà không tuyên bố gì thì KHÔNG được đề bạt** —
   đó là hội thoại, không phải quyết định.
2. **Phân loại theo ưu tiên**: DECISION > INCIDENT > CONSTRAINT > REQUIREMENT >
   PROCEDURAL > FACT (mặc định khi chỉ có "ghi nhớ").
3. **Dấu hiệu THAY THẾ**: "thay cho/thay thế/ghi đè/cập nhật/thay đổi quyết định
   …", kèm mã `qd_XXXX`/`ku_…` nếu người dùng nêu. Không mã → chọn bản cùng loại
   còn hiệu lực có ≥2 từ đặc trưng chung (`chon_ban_bi_thay_the`); không đủ →
   **không** thay thế (ghi mới, để người quyết).
4. `_CAT_DAU` bỏ phần dẫn ("hãy ghi nhớ đây là một quyết định của project:") để
   nội dung bản ghi là mệnh đề, tiêu đề là câu đầu.

Điểm cắm: `ghi_nhan._chat(role="user")` → `DichVuKyUc.de_bat_tu_chat(project_id,
text, su_kien)` **sau** khi L0 đã ghi (bằng chứng là chính dòng L0 đó). Mọi lỗi
đề bạt bị nuốt — ký ức không được giết Router (bất biến V0.6).

`DichVuKyUc.de_bat()`: mã `qd_*` người dùng nêu được quy về ký ức đứng sau
(`quyet_dinh(ma).ky_uc_ma`) trước khi so khớp — lỗi thật bài kiểm bắt: ứng viên
mang mã `ku_*`, người thì nhớ `qd_*`, nên bản đầu không bao giờ khớp.

## 3. Lược đồ v2 — trạng thái, thay thế, nguồn gốc

`PHIEN_BAN_LUOC_DO = 2`; sáu cột thêm vào `ky_uc` bằng `ALTER TABLE ADD COLUMN`
có `PRAGMA table_info` canh (idempotent, an toàn khi chết giữa chừng): `trang_thai`
(`hieu_luc | thay_the | bo`), `thay_the_cho`, `bi_thay_the`, `ts_sua`, `nguon_loai`,
`nguon_id`. Sổ V0.6 mở bằng V0.6.1 tự nâng; bản ghi cũ đọc được (`keys()` canh).

`KyUc` mang đủ trường Part A đòi: mã ổn định, project (theo sổ), loại, nội dung,
`ts` (created), `ts_sua` (updated), trạng thái, `nguon_loai` (source type),
`nguon_id` (source event id), `bang_chung` (provenance), `tin_cay` (authority),
`thay_the_cho`/`bi_thay_the`.

**Thẩm quyền** (`TinCay`): `USER_EXPLICIT` > `DO_DUOC` > `GHI_NHAN` > `BACKFILL`
> `LEADER` > `SUY_LUAN`. Lịch sử nhập không bao giờ vượt tuyên bố sống.

`thay_the_ky_uc(ma_moi, ma_cu)` — một giao dịch: bản cũ `thay_the` +
`bi_thay_the`, bản mới `thay_the_cho`, bảng `quyet_dinh` đồng bộ, nhật ký sửa.
Bản cũ **không bị xoá** (L0/L1 chỉ-thêm), `liet_ke(chi_hieu_luc=False)` vẫn thấy.

## 4. Nhập lịch sử — `memory/nhap_khau.py` (Part B)

QUÁ KHỨ + HIỆN TẠI + TƯƠNG LAI → KÝ ỨC DỰ ÁN. Bốn adapter, mỗi cái một phạm vi dự
án tường minh, không quét cả máy:

| Adapter | Nguồn | Mã nguồn mục | Đề bạt |
|---|---|---|---|
| `so_chinh` | `cc_events` + `chat` của đúng dự án trong `control.db` | `cc_events:<id>`, `chat:<id>` | tin `user` → `de_bat.xet` (BACKFILL) |
| `git` | `git log` của `repo_path` (≤3000) | sha | không (commit vào L0 để tìm) |
| `tai_lieu` | `README.md`, `CLAUDE.md`, `HANDOFF*.md`, `docs/**/*.md`, cắt theo `#/##/###` | `<đường>#<slug>#<sha12>` | tiêu đề "sự cố/bẫy/incident" → INCIDENT; "quy trình/runbook/lệnh thường dùng" → PROCEDURAL |
| `phien_claude` | `~/.claude/projects/<slug>/*.jsonl` **chỉ** cho slug của các worktree của kho (`git worktree list`) | `<slug>/<session>:<uuid>` | user → `de_bat.xet`; assistant → INCIDENT khi ≥3 dấu hiệu (≥1 MẠNH) + định danh, hoặc **một tên tệp viết hai cách lệch một ký tự** + dấu hiệu |

Không ChatGPT/cloud: không có nguồn cục bộ nào — không giả vờ đã nhập. Phiên
của dự án khác nằm cạnh **không bao giờ** được đọc (bài kiểm).

**An toàn (B2)**: idempotent (`nhap_khau(nguon, ma_nguon, sha, su_kien_id)`);
chỉ đọc nguồn (bài kiểm so bytes + `HEAD` trước/sau); L0 chỉ-thêm; bí mật lọc ở
cổng vào (inline + blob, `da_loc` cộng dồn); resumable (`TRAN_MOI_LAN=5000`/lượt,
lặp tới hết trong `han_giay=120`, `con_lai` báo phần chưa nhập); `thu_kho=True`
chỉ đếm; `nhap_khau_lan` ghi thống kê mỗi lần.

**Thẩm quyền (điều quan trọng nhất)**: lịch sử **luôn** `tin_cay = backfill`,
không bao giờ `user_explicit`. Lần chạy thật đầu tiên chứng minh vì sao: vai
"user" trong tệp phiên không phải lúc nào cũng là người gõ — bản tóm tắt nén
ngữ cảnh ("This session is being continued…"), thân skill, đầu ra lệnh `/…`,
nhắc nhở hệ thống đều mang vai "user", và một bản tóm tắt nén đã bị đề bạt thành
"quyết định user_explicit". Sửa: `tin_nguoi_go()` loại các dạng đó (`isMeta`,
`isCompactSummary`, `isSidechain`, `<system-reminder>`, `<command-*>`, "# … Skill"),
và mọi thứ còn lại vẫn chỉ là `backfill`.

**Chỉ đề bạt lịch sử trước mốc ký ức** (`ts < moc_ky_uc`, mốc = sự kiện không-backfill
đầu tiên của sổ): một tin nhắn hôm nay kể một sự cố cũ — kể cả đề bài của một task
— không được biến thành bản ghi "lịch sử". **Phiên Claude đang mở** (mtime < 600 s)
bị bỏ qua và nói rõ trong `ghi_chu`: nó là hiện tại, chưa xong, lần sau nhập tiếp.

**Trích đoạn**: sự cố từ tin trợ lý dài lấy đoạn ±700 ký tự QUANH dấu hiệu, cắt ở
ranh câu — kết luận về sự cố thường nằm giữa bài, không phải 1500 ký tự đầu.

### 4.1 Lần chạy thật trên chính kho này (sổ tạm, chỉ đọc nguồn)

| Nguồn | Khám phá | Nhập | Đã lọc bí mật | Đề bạt | Thời gian |
|---|---|---|---|---|---|
| `git` | 664 commit | 664 | 11 | 0 | 4.1 s |
| `tai_lieu` | 1 696 mục | 1 696 | 28 | 66 (sự cố/quy trình từ tiêu đề) | 11.0 s |
| `phien_claude` (8 slug worktree, 85 tệp) | 5 693 tin | 5 000 (+693 lượt sau) | 96 | 31 | 17.3 s |
| tổng | 7 360 sự kiện L0 · 93 ký ức · 0 `user_explicit` · sổ 27 MB | | | | dry-run 6.7 s · nhập 32.5 s |

Trước khi siết (lần 1): 143 ký ức, trong đó **2 "quyết định user_explicit" là bản
tóm tắt nén và thân skill**, 115 "sự cố" phần lớn là báo cáo cuối phiên chỉ có
"fixed"/"failed". Sau siết: 93, không `user_explicit`, sự cố cần dấu hiệu mạnh.

### 4.2 B1 — sự cố khoá SSH Fanfic: nguồn nào nói gì

Đề bài mô tả: `fanficappwrrite.pem` (lỗi chính tả) → tên canonical
`fanficappwrite.pem`, tạo bản canonical, sửa ACL, SSH kiểm chứng. Bài **không**
được bịa bản ghi từ đề bài. Soi nguồn được phép (8 slug worktree của kho, tài
liệu) tìm thấy 39 tin/8 mục tài liệu nhắc `fanficappwr?ite.pem`/`icacls`:

* **CÓ bằng chứng**: 2026-09-05 16:38 (phiên `appwrite-aws-migration`): *"`fanficappwrite.pem`
  does not exist. The real file is `fanficappwrrite.pem` — double "r". I'll use that
  automatically…"*; 2026-09-04 06:52 (`claude-lead`): *"The key at that path was gone,
  so I tested the three .pem files in Downloads … `fanficappwrrite.pem` authenticated"*.
  → Đề bạt thành INCIDENT `backfill`, dấu hiệu `ten_hai_cach_viet:fanficappwrite.pem≠fanficappwrrite.pem`
  + `does not exist`, bằng chứng trỏ về đúng dòng L0 (tin đó).
* **KHÔNG có bằng chứng trong nguồn được phép**: việc *tạo bản canonical*, *sửa ACL*
  cho khoá này. Mọi lệnh SSH thật tới 2026-09-08 vẫn dùng `fanficappwrrite.pem`. Nên
  **không** có bản ghi nào nói "đã tạo canonical/đã sửa ACL" — đúng yêu cầu "chỉ tạo
  khi nguồn thật sự có". Nếu việc đó xảy ra ngoài Claude Code (PowerShell tay,
  ChatGPT), nó không có nguồn cục bộ và không được bịa.

Câu "cái vụ SSH key fanficappwrite hôm trước bị gì?" → `tim()` trả sự cố backfill +
sự kiện thô; khối Leader nêu `[ku_… · incident · … · backfill]`.

## 5. Leader

* `khoi_cho_leader` thêm dòng *"VỪA GHI TỰ ĐỘNG TỪ TIN NHẮN NÀY (đã có bản ghi, hãy
  xác nhận bằng mã, KHÔNG ghi lại): qd_xxxx"* khi lượt hiện tại vừa đề bạt.
* `HUONG_DAN`: `record_memory(loai, noi_dung)` là hành động TỰ CHẠY (chỉ ghi vào
  sổ ký ức của chính Control Center — không phá huỷ), `tin_cay = leader`,
  `nguon_loai = leader`; **không dùng** khi tin nhắn người dùng đã là tuyên bố.
* Luật thẩm quyền V0.5/V0.6 nguyên vẹn: LIVE > REPO > MEMORY > INFERENCE.

## 6. Giao diện (Part G/H)

Tab Memory: đếm Sự kiện (+ số nhập lịch sử), Ký ức (+ số `user_explicit`), Quyết
định (hiệu lực / đã thay thế), Sự cố, **Ràng buộc**, **Yêu cầu**, **Quy trình**, Điểm
dừng, Mắt xích bằng chứng, Chỉ mục, Đĩa. Chip mới: Constraints, Requirements,
Procedures, **Historical sources** (bảng nguồn: sẵn/không, đã nhập, lần cuối; nút
Quét lại / Thử khô / Nhập; kết quả 8 ô + ghi chú từng nguồn). Chi tiết bản ghi:
huy hiệu HIỆU LỰC/THAY_THE, ghi/xảy ra/sửa, thẩm quyền, nguồn (`nguon_loai #id`),
"thay thế cho", "bị thay thế bởi" (bấm được).

## 7. API mới

`GET /api/memory/backfill/sources?project=` · `POST /api/memory/backfill {project,
thu_kho, chi}` — cùng rào V0.2; mọi phản hồi qua `_sach`.

## 8. Bộ kiểm

| Tệp | Số | Phủ |
|---|---|---|
| `test_project_memory_v061.py` | 18 bài / 18 subtest | phân loại tuyên bố (mọi loại, câu không tuyên bố → None, lead-in bị cắt, mã qd/ku); đề bạt qua `ControlStore` (Decisions 1, `user_explicit`, `chat_user`, bằng chứng L0, idempotent theo sự kiện, thay thế tường minh theo mã + theo nội dung, cả hai truy được); Leader `record_memory` hợp lệ + tự chạy + `HUONG_DAN`; lược đồ v2 (nâng từ v1, cột, đọc bản cũ) |
| `test_memory_backfill_v061.py` | 18 | nguồn không sẵn nói ra; chỉ phiên của worktree kho; idempotent + không ghi đè L0; thử khô không ghi; không sửa tệp nguồn (bytes + HEAD); bí mật lọc inline + blob + mọi bảng; resumable qua trần; nguồn gốc + băm mỗi dòng; lịch sử không bao giờ `user_explicit`; vai user tổng hợp không đề bạt (5 dạng); chỉ trước mốc; "Done. fixed/failed" không thành sự cố; tên hai cách viết; **phiên đang mở bị bỏ qua**; B1 từ phiên + tài liệu có bằng chứng; tìm bằng câu tự nhiên + khối Leader; không bịa khi nguồn không có; dịch vụ + API |
| `test_account_pool_v061.py` | 11 | xem `ANTIGRAVITY_POOL_AUDIT_V061.md` |
| `test_provider_credentials_v061.py` | 28 | xem `PROVIDER_CREDENTIAL_ARCHITECTURE_V061.md` |
| `test_provider_webapi_v061.py` | 3 | token; vòng đời không lộ khoá (kể cả fabric ĐANG SỐNG thấy runtime EXT ngay); 400 không lặp lại giá trị |
| hồi quy | `test_project_memory.py` (V0.6) cập nhật `PHIEN_BAN_LUOC_DO ≥ 2`; `test_project_memory_api_ui.py` allowlist thêm `POST /api/memory/backfill`; toàn bộ `scripts/tests` — xem mục 9 | |

Hai rào V0.6 đã bắt đúng hai chỗ đặt sai của V0.6.1 (và được sửa bằng cách DI
CHUYỂN, không bằng miễn trừ): (1) gói `memory/` không được có `subprocess` —
`git log`/`git worktree list` của nhập lịch sử chuyển ra
`scripts/control_center/nguon_git.py` (ba lệnh đọc, tham số cố định,
`an_cua_so()`); (2) vùng API ký ức trong `webapi.py` không được có
`@app.delete` — các route provider (có DELETE cần `xac_nhan`) nằm sau mục cài đặt
giao diện.

Đối chiếu 11 tình huống nghiệm thu ký ức của đề bài → bài kiểm: (1) tuyên bố →
Decisions 1 + `qd_*`: `test_de_bat_quyet_dinh_user_explicit`; (2) sống qua mở
lại: nghiệm thu EXE bước 10; (3) thay thế: `test_thay_the_theo_ma_tuong_minh`,
`…theo_noi_dung`; (4) "khi nào/ai/vì sao": `ts_su_kien`, `nguon_loai`, `bang_chung`
(bài đề bạt + EXE 2c); (5) Leader xác nhận không ghi lại: `TestLeaderRecordMemory`
+ EXE 2b; (6) thử khô: `test_thu_kho_khong_ghi_gi`; (7) idempotent:
`test_idempotent_va_khong_ghi_de_L0`; (8) B1: `TestPhucHoiSuCoSSH`; (9) không bí
mật: `test_bi_mat_trong_lich_su_bi_loc…` + Part F; (10) phiên lạ không nhập:
`test_chi_doc_phien_cua_worktree_kho_nay`; (11) UI đếm đúng: EXE bước 4/4b.

## 9. Hồi quy

| Bộ | Kết quả |
|---|---|
| 5 bộ V0.6.1 (memory_v061, backfill, pool, credentials, provider webapi) | **78 / 78** |
| `test_project_memory.py` + `test_project_memory_api_ui.py` (rào V0.6) | **78 / 78**, 258 subtest — sau hai lần di chuyển mã (mục 8) và một mục allowlist |
| `test_control_center_utf8_locale.py` (AST: `encoding=`, `ensure_ascii`, `text=` + `encoding`) | **42 / 42** — bắt `json.dumps` thiếu `ensure_ascii=False` trong `adapter.py` trước khi chạy, đã sửa |
| Hồi quy có đích (webapi 37, memory V0.6, leader, core, slice, ui, allowlist, attachments, web_deps, repo_ngoai_git, observability ×2, router_v4 scheduler/compat/launcher/premium_astra/profile_crypto) | **641 đạt / 2 hỏng** ở lần chạy đầu — cả hai là rào V0.6 bắt chỗ đặt mã (mục 8), xanh sau khi sửa |
| `python -m unittest discover -s scripts/tests` (lệnh CI) chạy cục bộ | **treo** trong các bài TUI Textual khi chạy song song với build PyInstaller + nghiệm thu EXE + Leader `agy` (CPU đứng 10 phút, `message pump` chờ) — đã dừng. CI Linux chạy lệnh này trên máy rảnh. |
| **Toàn bộ `scripts/tests` bằng pytest, máy rảnh, chia hai nửa** | nửa A (router_v3, beam, chinese media, ops, fanfic, setup, misc): **835 đạt / 4 bỏ qua** (4 phút); nửa B (control_center, router_v4, observability, claude policy, memory, providers): **906 đạt / 1 624 subtest** (22 phút) → **1 741 bài, 0 hỏng** |

## 10. Nghiệm thu bản EXE đóng gói — `dist-v061`

`scripts/control_center_v061_acceptance.py --exe "dist-v061/Router Control Center/Router Control Center.exe"`
— hai phiên, một gốc, Leader THẬT (`agy`), nhập lịch sử THẬT của chính kho này
(chỉ đọc), provider trỏ vào MÁY CHỦ GIẢ trên 127.0.0.1 với KHOÁ GIẢ ngẫu nhiên
(hình dạng `sk-…`, không bao giờ in ra). `dist-v04/05/06` không đổi (sha256 kiểm
lại: `38fcfbd9…`, `d63a6398…`, `6e049cce…`).

Ba lần chạy, mỗi lần dạy một điều:

| Lần | Kết quả | Hỏng vì | Sửa |
|---|---|---|---|
| 1 | 9 bước đầu, chết ở nhập lịch sử | harness đọc `noi_dung` ở cấp sai (`list?loai=decision` lồng trong `ky_uc`); `fetch` nhập 8 000 mục vượt 40 s của một lệnh CDP | harness: đọc đúng cấp; `_api_dai` bắn `fetch` rồi thăm dò |
| 2 | 29/31 | **6f — lỗi SẢN PHẨM**: fabric dựng trước (Leader mở phiên), provider thêm sau → runtime `EXT_*` chỉ hiện sau khởi động lại. **7** — 1 cửa sổ console ở 7.8 s, chủ `WindowsTerminal.exe` (tiến trình phiên-toàn-cục, không quy được bằng phả hệ — cùng hiện tượng V0.6 lần 1), trong lúc bộ kiểm hồi quy của chính đợt này đang chạy nền | `DichVuProvider.sau_khi_doi` → `engine._dong_bo_provider_fabric` đồng bộ fabric đang sống, gỡ `EXT_*` đã xoá (bài kiểm mới); chạy lại trên máy rảnh |
| 3 | 29/31 — **6f ĐẠT** (`EXT_NGHIEMTHU_THU` hiện trên fabric đang sống), **7 ĐẠT** (phiên A: 0 vi phạm / 96 s, app sinh git×24, agy×2, ssh×5) | **5d** — lần nhập hai thấy 2 mục MỚI (8 087 trùng): sự kiện của chính dự án trong `control.db` (`so_chinh`) lớn lên trong lúc app sống → harness đòi "0 mới" là sai; idempotent vẫn đúng. **14** — 1 cửa sổ ở 5.0 s [B: mở lại], chủ `WindowsTerminal.exe`, cùng lúc `agy.EXE`×2 (Leader ấm) xuất hiện; phiên A cùng lần chạy: 0 | harness 5d: đòi git/tài liệu/phiên = 0 mới và mọi mục lần một đều trùng; 14: xem "cửa sổ Windows Terminal" dưới |
| 4 | **31/31** — máy rảnh (không bộ kiểm nào chạy song song) | — | — |

Bản cuối: `dist-v061/Router Control Center/Router Control Center.exe` — 11 629 564
byte, sha256 `bfc25e37dba9abb5f13987ffe2a8e91215b7e7ed7f6a3f3f543cc4d38ab375f8`;
ghi ở `dist-v061/BAN_TOT_v061.txt`.

### Lần 4 — 31 bước

| # | Bước | Kết quả đo |
|---|---|---|
| 1, 1b | mở EXE, chọn dự án; ký ức sẵn, FTS5, lược đồ v2 | ĐẠT |
| 2 | **A1** — gõ đúng câu đã lộ khuyết tật V0.6 vào chat | `quyết định = 1`, `user_explicit = 1`, `tin_cay = user_explicit`, `nguồn = chat_user`; Leader: *"Đã ghi nhận quyết định có mã qd_0001: …"* |
| 2b | Leader không ghi lại | `quyết định = 1` |
| 2c | **A3** — nguồn gốc | `qd_0001` → 1 mắt xích → L0 `chat_user`, có `ts_su_kien` |
| 3 | **A2** — "thay cho qd_0001, …" | `quyết định = 2`; D1 `hieu_luc = False`, `trang_thai = thay_the`; D2 hiệu lực; liên kết hai chiều; Leader: *"Đã ghi nhận quyết định mã qd_0002 (thay thế cho qd_0001)…"* |
| 4, 4b | tab Memory | đếm Quyết định 2 (1 hiệu lực · 1 đã thay thế), Ràng buộc/Yêu cầu/Quy trình, chip Historical sources; danh sách hiện `qd_0001` + `qd_0002` |
| 5 | nguồn lịch sử của chính kho này | 4 adapter sẵn |
| 5b | thử khô | 8 089 khám phá · 103 đề bạt · 10.5 s · sổ chưa đổi |
| 5c | nhập thật | 8 089 nhập · 453 lần lọc bí mật · 103 đề bạt · 55.8 s · **1 phiên đang mở bị bỏ qua** (chính phiên này) |
| 5d | nhập lần hai | 0 mới · 8 089 trùng |
| 5e | **B1** — "vụ SSH key fanficappwrite" | 6 ký ức · 30 sự kiện thô · 72 sự cố `backfill`, authority chỉ `backfill` |
| 6 | kho bí mật | `windows-credential-manager`, sẵn; AUTO routing TẮT; 3 preset |
| 6b | thêm tài khoản (khoá giả) | chỉ `credential_ref`; giá trị **trong Credential Manager** |
| 6c | thử kết nối | `GET /models 200` · máy chủ giả nhận đúng `Bearer` (1 gọi, 1 khớp) · 2 model `probed` |
| 6d | hỏi thử (thủ công) | `pong`, usage 3 token |
| 6e | khoá không có ở | API (`/api/providers`, `/api/usage`, `/api/state`) · `control.db` · `providers.db` · sổ ký ức · log — quét bytes UTF-8 + UTF-16LE |
| 6f | fabric đang sống | `EXT_NGHIEMTHU_THU` có mặt, không nhận dispatch; AG: đăng ký 8, cấp phát 8, Leader chiếm `AG01` |
| 6g | **C** — chỗ Leader | `leader_chiem = ['AG01']` |
| 7 | phiên A: console | 0 vi phạm / 100.6 s (app sinh git×26, agy×2, ssh×5, conhost ẩn ×31) |
| 8 | tắt như người dùng | WM_CLOSE → thoát 15.1 s → điểm dừng "tắt ứng dụng" |
| 9, 10, 10b | mở lại | 2 quyết định (D1 thay thế), 8 089 sự kiện backfill, tài khoản `ok`, `MEMORY_RESUMED` |
| 11 | Leader phiên MỚI | *"Theo quyết định đang có hiệu lực qd_0002 (mã bản ghi ku_af7fc503c36b7373, ghi nhận 1 phút trước, nguồn từ user_explicit do bạn trực tiếp yêu cầu)…"* — 5/5 từ khoá, `MEMORY_CONTEXT 2→3` |
| 11b | không ghi thêm | `quyết định = 2` |
| 12, 12b | xoá | không xác nhận → 400; xác nhận → credential **biến mất** khỏi Credential Manager; xoá provider → sổ sạch |
| 13 | toàn vẹn | `control.db = ok`; 3 sổ ký ức `quick_check = ok` (kho: 8 091 sự kiện) |
| 14 | phiên B: console | 0 vi phạm / 27 s |

**Cửa sổ Windows Terminal** (bước 7/14): ở hai lần chạy, MỘT cửa sổ
`CASCADIA_HOSTING_WINDOW_CLASS` xuất hiện đúng lúc phiên Leader `agy` ấm được sinh
(lần 2: phiên A 7.8 s; lần 3: phiên B 5.0 s), phiên còn lại của cùng lần chạy
sạch. Chủ cửa sổ là `WindowsTerminal.exe` — tiến trình phiên-toàn-cục (Windows
Terminal là "ứng dụng terminal mặc định"), không quy được bằng phả hệ; các
console CÓ quy được về app đều **ẩn** (`console ẩn=3`, tức `an_cua_so()` hoạt
động). V0.6.1 không thêm đường sinh tiến trình nào ở lúc mở app/mở Leader; hiện
tượng này đã được ghi ở V0.6 mục 14 (lần 1: 1 cửa sổ, lần 2: 0). Kết luận thật:
**không vi phạm nào quy được về app**, nhưng bộ đo không thể chứng minh ngược
lại cho cửa sổ của Windows Terminal — để nguyên là HỎNG trong bảng, không đổi
tiêu chí.

Những gì lần 2 đã chứng minh trên bản đóng gói và giữ nguyên ở lần 3: Leader
thật trả lời *"Tôi đã xác nhận và ghi nhận quyết định vào ký ức dự án với mã
qd_0001"* — **xác nhận, không ghi lại** (`quyết định = 1`); câu "thay cho qd_0001…"
→ `qd_0002` hiệu lực, `qd_0001` `thay_the` vẫn truy được, liên kết hai chiều; nhập
lịch sử thật 8 088 mục / 53 s, lần hai 0 mới / 8 088 trùng, 1 phiên đang mở bị bỏ
qua, 453 lần lọc bí mật; "vụ SSH key fanficappwrite" → 7 ký ức + 30 sự kiện thô +
74 sự cố `backfill`; khoá giả nằm trong Credential Manager, **không** ở phản hồi
API/`control.db`/`providers.db`/sổ ký ức/log; xoá tài khoản → biến mất khỏi
Credential Manager; phiên B: Leader mới trả lời *"Theo quyết định đang có hiệu lực
qd_0002 (mã bản ghi ku_…, được ghi nhận 1 phút trước từ nguồn user_explicit do bạn
trực tiếp chỉ định)…"* — khớp 5/5 từ khoá, không ghi thêm.

## 10. Không làm (Part M) và bước tiếp theo

Không xoá L0/L1; không consolidation tự động; không vector memory; không ký ức
xuyên dự án; không đọc phiên của dự án khác; không nhập ChatGPT/cloud (không có
nguồn cục bộ). Bước tiếp theo hợp lý: (a) bật AUTO cho provider ngoài với adapter
thực thi + ngân sách; (b) người vận hành xác nhận/loại các sự cố `backfill` từ
tab Memory (đánh dấu `bo`), vì `backfill` là thẩm quyền thấp nhất trên `leader`;
(c) nhập tiếp 693 tin còn lại của lần chạy đầu bằng nút **Nhập** (resumable).
