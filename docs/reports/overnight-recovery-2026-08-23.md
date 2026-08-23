# Overnight recovery + Fanfic delivery — 2026-08-23

> Báo cáo tiến trình, cập nhật liên tục trong đêm để sống sót qua sự cố session.
> Tất cả nhánh nằm LOCAL. Không deploy production. Không push (xem Phase 0).

## Phase 0 — Baseline / an toàn

| Hạng mục | Giá trị |
|---|---|
| Repo root | `C:\Users\nguye\Documents\CapCut-TTS-App` |
| User hiện tại | `nguye` (profile cũ `robux` KHÔNG tồn tại trên máy này) |
| `origin/main` | `edb7f0c7b2595042092dbe8d4cc101f85e647fb8` (`edb7f0c`) |
| `main` local | `edb7f0c` — sạch, khớp origin, 0 commit riêng |
| Branch khi bắt đầu | `recovery/oauth-staging-regression` @ `a5cd38f` (ahead 1) |
| Worktrees | 1 (chính) |
| Stashes | 0 |
| Dirty files | 0 |

Toolchain: git 2.55.0.windows.3 · node v24.19.0 · npm 11.17.0 · Python 3.12.10 ·
gh 2.98.0 · Claude Code 2.1.231

### Sự cố malware vẫn đóng (kiểm tra read-only)

| Hạng mục | Trạng thái |
|---|---|
| `WindowsVersionUpdaterLegacy` (thư mục) | absent |
| Scheduled task cùng tên | absent |
| Reset hook `C:\Recovery\OEM` | absent |
| WinINET proxy | `ProxyEnable=0`, ProxyServer rỗng |
| Cổng 64662/64663/64665/53336 | closed |
| Rogue CA `319843F7…9951` | absent |
| hosts | clean |
| ASR rules | 12 còn nguyên |
| Real-time protection / Tamper Protection | True / True |

**SECURITY: PASS.**

### QUYẾT ĐỊNH CHẶN PUSH (quan trọng)

`AppData\Roaming\GitHub CLI\hosts.yml` được ghi lúc **2026-08-22 22:38:39**.
Cửa sổ chặn TLS (MITM) là **18:52:46 → 22:47**.

→ Token GitHub hiện tại được cấp **BÊN TRONG** cửa sổ bị chặn.
→ **KHÔNG push, KHÔNG mở PR tối nay.** Mọi nhánh để sẵn ở local kèm lệnh chính xác
để chạy sau khi re-auth. Xem mục "Lệnh cần chạy sau khi re-auth" ở cuối.

---

## Tiến trình

- [x] Phase 0 — baseline / safety
- [ ] Phase 1 — OAuth/staging recovery branch
- [ ] Phase 2 — Pollinations translation v2
- [ ] Phase 3 — WIP stashes
- [ ] Phase 4 — Phase D canary
- [ ] Phase 5 — Phase E verify
- [ ] Phase 6 — quality gate
- [ ] Phase 7 — OmniRoute
- [ ] Phase 8 — A/B benchmark
- [ ] Phase 9 — state map
- [ ] Phase 10 — cleanup

---

## Phase 1 — `recovery/oauth-staging-regression` — READY (local)

Nhánh `recovery/oauth-staging-regression` @ `a5cd38f`, dựng từ `origin/main`, **+49/−0**.

| Kiểm tra | Kết quả |
|---|---|
| Diff chỉ chạm docs + tests (0 file runtime) | PASS |
| `web_base_url` default localhost là CÓ Ý | PASS — `server/config.py:311` ghi rõ "Mac dinh la dev server; production PHAI dat tuong minh" |
| Staging còn sống (không phải giả định cũ) | PASS — `wrangler.staging.jsonc` → worker `fanfic-web-staging`, custom domain `staging.fanfic.world`, script `cf:deploy:staging` |
| `compileall` file đã sửa | PASS |
| Test OAuth nhắm đúng | 34/34 OK |
| Negative control (chèn regression vào `server/main.py`) | 3 FAILURES → test KHÔNG rỗng nghĩa; đã revert sạch |
| Toàn bộ backend | 2644 OK (3 skipped) |

## Phase 2 — `recovery/pollinations-translation-v2` — READY (local)

Nhánh mới từ `origin/main`, commit `74b6b54`, **+480/−1** (4 file).

Lý do KHÔNG merge nhánh lịch sử: `79ba675` KHÔNG phải ancestor của `main`
(nó là TIP của `origin/feature/animation-v6`), main đã tiến hoá độc lập
`translation_provider_registry.py` 800→1013 dòng, và cherry-pick commit đầu
tiên xung đột ở `translation_provider_registry.py` + `translation_service.py`.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Pollinations dịch | không có trên main (main chỉ có Pollinations cho ẢNH) | `PollinationsProvider` + 4 model curated |
| Rào chắn tính phí | — | trả phí theo mặc định; chỉ `POLLINATIONS_FREE_TIER=true` mở được |
| `command-a-plus` | có trong bản lịch sử | LOẠI có ý (benchmark: pinyin thay vì Hán Việt) |
| Test | 0 | 21 |
| Backend suite | 2641 (origin/main) | 2662 — đúng +21 |

**Phát hiện khi viết test (không phải suy diễn):** `TRANSLATION_ALLOW_PAID_PROVIDER=true`
MỘT MÌNH không đủ để bật provider trả phí, vì `ProviderRegistry.__init__` lọc
`free_tier` VÔ ĐIỀU KIỆN. Đã ghi lại trong code, `.env.example` và một test.

**CỐ Ý chưa gộp:** phần chunk-retry + audit-cache (~150 dòng trong
`translation_service.py` + `test_translation_chunk_resilience.py` 293 dòng) là
tính năng RIÊNG, default-off. Vẫn được bảo toàn trong bundle và trên nhánh
`feature/pollinations-translation`. Xem mục "Việc còn lại".

## Phase 3 — WIP stashes

### A. `themed-page-hero` → **OBSOLETE / đã trên main** (không áp dụng)

Bằng chứng (không phải phỏng đoán):
- 4/4 Motif component (`MotifCelestialDial`, `MotifCompassArc`,
  `MotifConstellation`, `MotifInkBloom`) đã có trên main qua `ffe77df`.
- 7/8 biến CSS hero đã có trên main.
- Biến thứ 8 (`--hero-highlight`) bị `e01e50d` XOÁ CÓ Ý trên 9 khối theme,
  commit message: "remove dead motif exports and unused CSS custom property".
- `60f4cf1` = "Checkpoint A: Themed Page Hero V1 hoan tat" → việc này đã xong
  và đã commit, rồi được tinh chỉnh tiếp.

→ Áp lại sẽ HỒI SINH CSS đã chết. Giữ nguyên phân loại, không reapply.

### B. `animation-player-v2` → **RECOVERED** → `recovery/animation-player-controls` @ `ecaf71d`

**+127/−3** (4 file). Hành vi: dim-on-pause CHỈ bằng `brightness(85%)` (không
blur, không che nội dung — tôn trọng chính sách YouTube), control bar thành
tâm điểm khi tạm dừng, CHỈ nút Play/Pause đập nhịp.

**Xung đột THẬT (khác kết luận sơ bộ trước đó):** `git apply --check --3way`
báo "applies cleanly" nhưng áp thật thì XUNG ĐỘT ở `globals.css` — stash mang
theo bản cũ của cả khối `.yt-facade`, mà main đã có `.yt-facade`,
`.yt-facade img`, `.yt-facade-play`, `.yt-facade-title`. Lấy nguyên "theirs"
làm `.yt-facade{}` bị NHÂN ĐÔI (2→3). Đã xử lý: khôi phục `globals.css` về
main rồi chèn PHẪU THUẬT chỉ các rule mới, sau đó đối chiếu số lần xuất hiện
từng selector với `origin/main` để chứng minh không nhân bản.

| Kiểm tra | Kết quả |
|---|---|
| Test nhắm đúng | 32/32 (26 cũ + 6 phục hồi) |
| Toàn bộ frontend | 809 test, 803 pass, 0 fail, 6 skipped |
| `tsc --noEmit` | sạch |
| `eslint` | 0 error (2 warning cũ ở `image-studio`, KHÔNG sửa — không liên quan) |
| Nhân bản CSS | không (đối chiếu từng selector với main) |

## Phase 4 — Phase D: hoàn thiện QA canary → `feature/qa-canary-lifecycle` @ `229a0b0`

**+410/−2** trong `scripts/staging_smoke.py`. Thêm mục **9.1–9.8** (dùng số phụ
để 10–13 giữ nguyên số): đơn xin tác giả → ranh giới duyệt → xuất bản → khám
phá → phát lại → sửa → tạo lại bản đọc → thu hồi/xuất bản lại.

Thích ứng cấu hình THẬT: `/api/health` công bố `author_gate_enabled`, nên 9.3
khẳng định 403-khi-chưa-duyệt nếu cổng BẬT, và idempotent nếu cổng TẮT. Không
bước nào nâng quyền — 8 route admin chỉ được gọi để khẳng định bị TỪ CHỐI.

**Hai lỗi tìm ra bằng cách CHẠY THẬT, không phải đọc code:**

| # | Lỗi | Ảnh hưởng |
|---|---|---|
| 1 | `buoc_tts` dùng `r.get("url", "")` — endpoint trả 200 kèm JSON `null` với storage local → `None` → `TypeError` | GIẾT cả lượt chạy tại mục 5. Lỗi CÓ TRƯỚC, không phải do tôi |
| 2 | Bộ đếm track của TÔI parse `/api/audio/{id}` như JSON — đó là đường PHÁT (byte MP3 hoặc 307) | luôn trả 0 → hai khẳng định "không nhân bản" thành VÔ NGHĨA mà vẫn xanh một nửa |

Cùng với 2 lỗi 422 của tôi (`ListenProgressIn` cần `novel_id`, `ListenIn` cần
`listened_seconds`). Đã sửa hết.

**Kết quả chạy trên instance CỤC BỘ** (mock data, local storage, inline worker
— KHÔNG chạm staging/production): **112 khẳng định ĐẠT, 5 HỎNG**, và cả 5 đều
là đặc thù môi trường cục bộ (`inline_worker=True`, backend mock/local, storage
local không cấp URL đã ký — 2 trong 5 là phép kiểm CÓ TRƯỚC của `buoc_tts`).

Bất biến then chốt được chứng minh: dọn dẹp báo `{"chapters": 2, "tracks": 1}`
— chương được tạo lại vẫn ĐÚNG MỘT track, chương đối chứng không bị chạm.

## Phase 5 — Phase E: **VERIFIED COMPLETE** (+ 1 khoảng trống test đã bù)

Không sửa production code. 86 test hiện có ĐẠT. Bao phủ thực tế rất đầy đủ:
parse text/JSON, hạn mức, đối soát hạn mức UI↔máy chủ, dấu vân tay
(idempotency key), hợp đồng schema, thứ tự + tiến độ, idempotent (gửi lại,
giữa lúc chạy, ghi dở), thử lại một mục, huỷ lô, phanh nghỉ (an toàn đa tiến
trình), phân quyền, lô lỗi, KHÔNG tự phục hồi nội dung, 400-không-500, và
KHÔNG bắn 500 thông báo.

Kiến trúc: bulk import KHÔNG đi đường riêng — nó tiêm `tao_job` chính là thân
của route `POST /api/jobs`, nên thừa hưởng idempotency theo dấu vân tay và trần
`MAX_ACTIVE_JOBS`. `MAX_IMPORT_ITEMS=500`, `MAX_IMPORT_TOTAL_CHARS=5.000.000`.

**Khoảng trống THẬT đã tìm ra:** `validate_chapters` dùng `>` (đúng), nhưng
KHÔNG test nào giữ điều đó — `KiemHanMuc` chỉ kiểm phía TỪ CHỐI. Đổi một dấu
thành `>=` sẽ lặng lẽ từ chối lô đúng 500 chương mà cả 86 test vẫn xanh.

→ `test/bulk-import-boundaries` @ `5730672`: **+12 test**, bulk suite 86→98.
Negative control: chèn `>` → `>=` ở cả 3 chỗ khiến 12 test mới báo **5 lỗi**,
còn `KiemHanMuc` cũ chạy 4 test và báo **OK** — hoàn toàn mù. Đã revert.

## Phase 6 — Cổng chất lượng

| Lệnh | Kết quả |
|---|---|
| `python -m unittest discover -s server/tests -t .` | **2653 OK** (3 skipped) — origin/main là 2641 |
| `python -m compileall app.py desktop_app tests` | OK |
| `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t .` | **372 OK** |
| `npm test` (web) | **809 test, 803 pass, 0 fail, 6 skipped** |
| `npm run typecheck` (`tsc --noEmit`) | sạch |
| `npm run lint` (eslint) | **0 error**, 2 warning CÓ TRƯỚC ở `image-studio/page.tsx` (KHÔNG sửa — không liên quan) |
| `npm run build` (production build) | **thành công** |

Lưu ý: repo dùng `unittest` + `compileall`, KHÔNG có pytest/ruff/mypy trong venv.

## Phase 7 — OmniRoute: **CÀI ĐẶT AN TOÀN, TÙY CHỌN, CÔ LẬP**

Provenance đã đối chiếu trước khi cài: `repository.url` =
`git+https://github.com/diegosouzapw/OmniRoute.git` (khớp nguồn chính thức),
maintainer `diegosouza.pw` khớp chủ GitHub `diegosouzapw`, **không có**
`preinstall`/`install`/`postinstall` (chỉ `prepare: husky`, npm không chạy cho
người dùng cài từ registry). Ghim đúng **3.8.49**, sha512 integrity có sẵn.

Cài vào prefix CÔ LẬP `C:\Users\nguye\Documents\Projects\omniroute-sandbox`
với `--ignore-scripts`. **KHÔNG global, KHÔNG trên PATH.**

CỐ Ý KHÔNG chạy: `setup-claude` (ghi `~/.claude/profiles/`) và `launch` (trỏ
Claude Code sang OmniRoute) — đúng luật "không sửa config Claude toàn cục".

| Kiểm tra | Trước | Sau khi cài + chạy + dừng |
|---|---|---|
| `which claude` | `.../WinGet/Links/claude` | **giống hệt** |
| `claude --version` | 2.1.231 | **2.1.231** |
| `~/.claude.json` md5 | `666369…a245b` | **`666369…a245b` không đổi** |
| `~/.claude/profiles` | không có | **vẫn không có** |
| omniroute trên PATH | — | **0** |
| omniroute global npm | — | **0** |

Dữ liệu riêng của nó ở `C:\Users\nguye\.omniroute` (ngoài config Claude).
Khởi động với **0 credential**: mọi route `auto/*` báo *"matched no connected
models; returning an empty pool"* và nó KHÔNG tự mở rộng pool (cần
`OMNIROUTE_AUTO_FREE_FALLBACK_TO_FULL_POOL=true`). Không key trả phí nào.

## Phase 8 — A/B benchmark (không phá hoại)

Có một pool provider MIỄN PHÍ / KHÔNG-KEY dùng được (`opencode`, `felo-web`),
nên đo được thật mà không tốn phí.

| Tác vụ | OmniRoute | Đúng/Sai |
|---|---|---|
| 1. Kiến trúc bulk import (phase order + có tự tạo job?) | **13.6 s**, `big-pickle`, 1020 tok | **ĐÚNG** (C→A→B, uỷ quyền `tao_job`) |
| 2. Bất biến OAuth callback | **92.5 s** | **KHÔNG có output dùng được** |
| 3. Đề xuất 3 test cho một dataclass | **429 sau 7 provider**, + crash libuv | **HỎNG** |

Tác vụ 3 trả lời trực tiếp câu hỏi "routing có lãng phí thời gian thử tuần tự
không?" — **CÓ**: `attemptOrder` đi qua 7 provider
(`oc/big-pickle` → `oc/north-mini-code-free` → `felo/felo-chat` →
`felo-search` → `felo-scholar` → `felo-social` → `felo-document`) rồi mới bỏ,
kèm `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)` — crash native
libuv trên Windows.

**KHUYẾN NGHỊ: NOT WORTH IT cho luồng Fanfic** (ở cấu hình miễn phí):
1/3 tác vụ thành công; 92 s cho một câu hỏi 50 từ; fallback tuần tự đốt
wall-clock; có crash native. Và về bản chất nó là **model gateway không có
quyền đọc repo hay dùng tool** — không làm được việc agentic trên repo, tức
đúng phần việc thật.

Để lại: đã cài nhưng **CÔ LẬP và KHÔNG dùng**. Xoá bằng
`rm -rf C:\Users\nguye\Documents\Projects\omniroute-sandbox` và
`C:\Users\nguye\.omniroute`. Chỉ nên xem lại nếu sau này nối một provider
subscription/trả phí thật — ngoài phạm vi tối nay.

## Phase 9 — Bản đồ trạng thái Fanfic

| Hạng mục | Trạng thái |
|---|---|
| `origin/main` | `edb7f0c` — KHÔNG bị chạm suốt đêm, sạch, 0 commit riêng |
| `recovery/oauth-staging-regression` | `a5cd38f` — +49/−0, READY (local) |
| `recovery/pollinations-translation-v2` | `74b6b54` — +480/−1, READY (local) |
| `recovery/animation-player-controls` | `ecaf71d` — +127/−3, READY (local) |
| `feature/qa-canary-lifecycle` | `229a0b0` — +410/−2, READY (local) |
| `test/bulk-import-boundaries` | `5730672` — +12 test, READY (local) |
| `feature/pollinations-translation` | `2ed65fe` — nhánh LỊCH SỬ đã phục hồi từ bundle, GIỮ LẠI làm nguồn tham chiếu, KHÔNG mở PR |
| PR đã mở | **KHÔNG CÓ** — xem lý do chặn push ở Phase 0 |
| Phase D | ĐÃ HIỆN THỰC + ĐÃ TEST, sẵn sàng cho canary thật (cần 1 hành động người) |
| Phase E | **VERIFIED COMPLETE** + 12 guard biên mới |
| Pollinations | viết lại native cho main, trả phí-theo-mặc-định, inert khi chưa bật |
| Stash themed-page-hero | OBSOLETE, đã chứng minh, không áp |
| Stash animation-player-v2 | ĐÃ PHỤC HỒI thành nhánh riêng |
| Cloudflare Free frontend | KHÔNG chạm. `wrangler.staging.jsonc` → `fanfic-web-staging` / `staging.fanfic.world`; `wrangler.jsonc` → `fanfic-web`. Test `KHONG khai them tai nguyen Cloudflare phai tra tien` vẫn ĐẠT |
| Google Drive Desktop | Stream files BẬT, mount **G:**, `PreResetBackup-2026-08-22` thấy được, cache cục bộ ~3.9 GB / 34 GB (không tải toàn bộ) |
| Production deploy | **KHÔNG. Không lệnh deploy nào được chạy.** |

### Xoay credential còn lại (làm từ điện thoại / máy khác)

1. **Google** `hainam10102000@gmail.com` — đổi mật khẩu + đăng xuất mọi phiên
2. **GitHub** `kujopht` — thu hồi PAT + phiên (token hiện tại cấp lúc 22:38:39, TRONG cửa sổ bị chặn)
3. **Microsoft** `nguyencongson160870@gmail.com`
4. **Anthropic / Claude Code**
5. **OpenAI / Codex**
6. **Cloudflare Wrangler token** — xoay ở dashboard rồi `wrangler login` mới; KHÔNG phục hồi cache cũ
7. **rclone** — thu hồi quyền ở Google Account (Drive Desktop đã ổn định, không cần rclone)

Không có SSH key, không có `.env` chứa secret, không có credential AWS/kube/docker
trên máy này → hạ tầng production Fanfic có vẻ KHÔNG bị lộ từ host này.

## Phase 10 — Dọn dẹp và kiểm tra toàn vẹn cuối

| Kiểm tra | Kết quả |
|---|---|
| Việc hợp lệ nằm CHỈ trong file untracked | KHÔNG (0 file untracked) |
| 8 nhánh đều có working tree sạch | ĐẠT |
| Bằng chứng phục hồi còn nguyên (bundle + 2 patch + audit-docs) | ĐẠT, bundle vẫn `verify` OK |
| Bằng chứng sự cố malware còn nguyên | ĐẠT |
| `PreResetBackup-2026-08-22` trên Drive | KHÔNG chạm |
| Tiến trình build/test/git còn ghi dữ liệu | KHÔNG |
| Drive đang upload file mới quan trọng | KHÔNG (`content_cache` delta 0 MB / 6 s; không file nào được ghi lên Drive tối nay) |

**Một phát hiện ở phút cuối, đã xử lý:** sau khi `omniroute stop` báo
"Server stopped" và cổng 20128 đã đóng, cổng **mở lại**. Nguyên nhân: một tiến
trình con `dist/server-ws.mjs` (WebSocket daemon) được spawn detached và `stop`
không reap. Đã kiểm tra kỹ: **KHÔNG có scheduled task, KHÔNG Run key, KHÔNG
startup folder, KHÔNG autostart** nào của OmniRoute — nên đây là tiến trình sót
lại, KHÔNG phải persistence, và nó sẽ không quay lại sau khi tắt máy. Đã kill
5 tiến trình theo đường dẫn sandbox; cổng 20128 đóng; `claude` vẫn 2.1.231 với
md5 config không đổi.

Đây chính là loại lỗi mà bước "kiểm tra toàn vẹn phút cuối" tồn tại để bắt —
nếu bỏ qua, một service lạ sẽ được để lại đang chạy sau khi tôi báo "đã xong".

## Cập nhật — sáng 2026-08-23: đã push và mở PR

`gh auth status` xác nhận phiên MỚI (`hosts.yml` ghi lúc 07:35:47, sau cửa sổ
chặn 18:52:46→22:47 tối qua). Đã push cả 5 nhánh phục hồi + nhánh docs + nhánh
lịch sử `feature/pollinations-translation` (chỉ để tham chiếu, KHÔNG mở PR).

| PR | Nhánh | CI |
|---|---|---|
| [#32](https://github.com/kujopht/capcut-tts-app/pull/32) | `recovery/oauth-staging-regression` | ĐẠT (3/3) |
| [#33](https://github.com/kujopht/capcut-tts-app/pull/33) | `test/bulk-import-boundaries` | fail lần 1 (không liên quan) → rerun |
| [#34](https://github.com/kujopht/capcut-tts-app/pull/34) | `feature/qa-canary-lifecycle` | ĐẠT (3/3) |
| [#35](https://github.com/kujopht/capcut-tts-app/pull/35) | `recovery/animation-player-controls` | ĐẠT (3/3) |
| [#36](https://github.com/kujopht/capcut-tts-app/pull/36) | `recovery/pollinations-translation-v2` | ĐẠT (3/3) |

**PR #33 lần chạy đầu tiên fail**, nhưng KHÔNG do thay đổi của PR: test hỏng là
`test_translation_job_recovery.KhoiPhucJobSauKhiWorkerChetTest...`, một kịch
bản đua (race) mô phỏng worker chết giữa chừng — file này KHÔNG nằm trong diff
của PR (`git diff --stat main..test/bulk-import-boundaries` chỉ đổi
`server/tests/test_bulk_chapter_import.py`). Chạy lại 5 lần trên `main` sạch,
cục bộ: **5/5 OK** — kết luận đây là flaky test có trước, nhạy cảm thời gian,
không phải hồi quy do PR. Đã trigger `gh run rerun --failed`.

**Rerun confirmed green** — all 3 checks pass on `test/bulk-import-boundaries`
after `gh run rerun --failed`. Triage stands: pre-existing flaky worker-death
race test, unrelated to this PR's diff.

**All 5 PRs are open, CI-green, and ready for human review/merge:**
#32, #33, #34, #35, #36. None merged automatically, per instructions.
