# Handoff: Overnight Pre-Production Hardening Marathon V1

Nguồn sự thật cho phiên này. Nếu ngữ cảnh hội thoại bị nén/mất, đọc file này +
`git log --oneline -30` + `git status` trước khi làm bất cứ gì.

Bắt đầu từ: `integration/pre-prod-v1` @ `a0420e6` (đã qua xét duyệt tích hợp
Admin V2 + Trusted Video Sources, README ready-for-preprod).

Nhánh làm việc: `chore/preprod-overnight-hardening-v1` — KHÔNG merge vào
`integration/pre-prod-v1` trong phiên này, chỉ push/freeze khi xong.

## Ranh giới an toàn (nhắc lại, TUYỆT ĐỐI không phá)

KHÔNG: sửa `main`, deploy production, đụng Appwrite Cloud production, thử lại
Cloud migration, dọn dữ liệu profile production, lộ secret, in API key/token,
commit file `.env`, thực hiện giao dịch AI/ảnh/TTS trả phí thật, trừ Fanfic
Credit thật, kích hoạt shared premium generation thật, xoá dữ liệu người
dùng/nội dung thật, xoá GCE VM, xoá Docker volume, sửa Cloudflare DNS, sửa
GCP firewall/network, chạy migration DB phá huỷ, áp dụng stash
dim/glow/pulse, xoá nhánh feature hiện có.

Việc cần secret/thao tác tay/cloud console/thanh toán/production write/hành
động phá huỷ mơ hồ → ĐÁNH DẤU BLOCKED, ghi lại, đi tiếp phase sau — không
dừng cả phiên.

## Baseline (Phase 0)

- `integration/pre-prod-v1` local == remote == `a0420e6`. Xác nhận.
- `main` local == remote == `d483e909dcd7949b3fae7aaf082aea69c7e274f1`. Chưa đụng.
- Stash: đúng 1 mục, `feature/animation-player-v2-custom-controls` (dim/glow/pulse). Chưa đụng.
- Working tree: sạch lúc bắt đầu.
- Backend test: **2375/2375 pass** (1 skip — thiếu file `.onnx.json` test model cục bộ, không liên quan).
- Frontend test: **635/635 pass**.
- Nhánh overnight tạo tại: `chore/preprod-overnight-hardening-v1` @ `a0420e6` (chưa có commit riêng).

## Tiến độ theo phase

- [x] Phase 0 — Bootstrap + baseline. XONG.
- [x] Phase 1 — Route/feature inventory (`docs/reports/preprod-route-matrix.md`). XONG —
      25 route PUBLIC + 18 route ADMIN (43 route `page.tsx` tổng cộng qua glob).
      Không thấy bug rõ ràng khi đọc; đã ghi nhận 1 điểm cần Phase 3 xác minh
      (route `/admin/animation/series` + `/admin/animation/series/[id]` không có
      `vaiToiThieu` trong `AdminShell.tsx`, khác các route admin khác — chỉ ghi
      nhận, chưa kết luận là bug) và nhiều điểm "cần kiểm tra trực tiếp" (loading/
      mobile) dành cho Phase 2.
- [x] Phase 2 — Browser QA thật (`docs/reports/preprod-browser-qa.md`). XONG —
      quét desktop + mobile (390×844) cho toàn bộ route công khai + đăng ký/
      đăng nhập/write/studio/account/admin (tài khoản thường). Không thấy bug
      console/render. 2 điểm ghi nhận đều là hành vi đúng hoặc artefact môi
      trường QA (lệch cổng CORS do chọn cổng 8010/3010 thay 8000/3000; nav
      mobile cuộn ngang cục bộ có chủ đích). Giới hạn: chưa QA được giao diện
      admin bên trong (không có tài khoản admin/owner sẵn trong mock, không tự
      nâng quyền).
- [x] Phase 3 — Auth/authorization adversarial audit. XONG — soi trực tiếp
      `server.main.app.routes`: ~54 route `/api/admin/*`, mỗi route có ĐÚNG MỘT
      trong `admin_profile`/`admin_or_owner_profile`/`owner_profile`, khớp đúng ý
      đồ vai trò cho từng hành động (đọc vs. sửa vs. chỉ-OWNER) — SẠCH, không có
      route thiếu dependency. Giải quyết điểm Phase 1 nêu: `/admin/animation/series`
      không có `vaiToiThieu` trong `AdminShell.tsx` là ĐÚNG Ý ĐỒ, không phải bug —
      route backend `admin_animation_series*` dùng `admin_profile` (MODERATOR trở
      lên), khớp việc kiểm duyệt Animation là việc của MODERATOR. Đã xác nhận lại
      các test tự-kiểm-tra vẫn còn nguyên: `test_moi_route_admin_deu_duoc_bao_ve`,
      `test_khong_the_tu_tam_dung_chinh_minh`,
      `test_khong_the_tu_cham_dut_phien_cua_chinh_minh`,
      `test_admin_khong_duoc_tam_dung_tai_khoan_quan_tri_khac`,
      `test_kiem_duyet_KHONG_duoc_tao_nguon`. Không sửa gì (không có lỗ hổng).
- [x] Phase 4 — Appwrite read/write cost audit v2 (`docs/reports/preprod-appwrite-cost-audit.md`). XONG —
      SẠCH toàn bộ 8 khu vực (dashboard, gamification store, social service,
      creator service, route công khai, health/ready, worker loops, frontend
      useEffect/setInterval). Không sửa gì (không có phát hiện cần sửa). 1 hạn
      chế đã biết ở `admin_authors` (kéo tối đa 500 hồ sơ) — chấp nhận được,
      không sửa.
- [x] Phase 5 — Performance audit (`docs/reports/preprod-performance-audit.md`). XONG —
      SẠCH cả backend (`server/`) lẫn frontend (`web/src`), không có phát
      hiện mức blocker. 5 ghi chú minor (N+1 nhỏ trong xoá cascading/reorder
      admin, `<img>` không khai báo width/height ở ảnh do người dùng tạo,
      không có `dynamic()` code-splitting) — đều là hành động không phải
      đường nóng hoặc quyết định có chủ đích đã ghi chú tại chỗ, không sửa.
      Đo Core Web Vitals thật qua `performance_start_trace` trên 3 route
      (`/`, `/fanfic`, `/animation`): LCP 438-692ms, CLS 0.01 — không có
      vấn đề hiệu năng render.
      BỔ SUNG (đo độ trễ THẬT chống `appwrite-dev.fanfic.world` qua
      `scripts/perf_probe_admin_selfhost.py`, cấp OWNER cục bộ cho tiến
      trình tạm qua `FAS_OWNER_USER_IDS` — biến môi trường, không phải cột
      Appwrite, không cần thao tác Appwrite console): phát hiện
      `GET /api/admin/image-studio/spending` mất **7.8s** do 9 truy vấn
      đếm chạy TUẦN TỰ. ĐÃ SỬA: song song hoá bằng
      `ThreadPoolExecutor(max_workers=4)` (cùng idiom `_admin_dashboard_them`,
      tách `_an_toan` cũ thành `_an_toan_song_song` cấp module để dùng
      chung) → còn **3.1s**. `admin_analytics_detail` (11.4s trước đo) đã
      được song song hoá độc lập (không trùng). Test backend lại
      **2401/2401 pass** sau sửa. Đây cũng GIẢI QUYẾT mục BLOCKED "ADMIN
      qua HTTP+auth thật" ghi ở Phase 6 bên dưới — hoá ra role admin/owner
      là biến môi trường CỤC BỘ (`Settings.admin_role_of`), không phải cột
      Appwrite, nên có thể cấp cho một tiến trình backend tạm mà không cần
      thao tác Appwrite console; đã tận dụng để đo VÀ gọi thật
      `/api/admin/overview`, `/users`, `/animation/series`, `/sources`,
      `/imports`, `/events` qua HTTP+JWT thật — toàn bộ trả 200 đúng như kỳ
      vọng.
- [x] Phase 6 — Self-hosted Appwrite real smoke matrix. XONG (một mục BLOCKED) —
      chạy thật với `FAS_ENV_FILE=server/.env.selfhost` chống `https://appwrite-dev.fanfic.world/v1`:
      - AUTH+PROFILE+GAMIFICATION: mở rộng `scripts/smoke_test_selfhost_appwrite.py`
        thêm đăng nhập riêng/`\/api\/auth\/me`/đăng xuất thật (trước đây chỉ có
        đăng ký) + token đã đăng xuất không dùng được nữa (401) + đăng xuất token
        không hợp lệ vẫn trả 200. Kết quả: **19/19 đạt** (streak/quest/XP/cosmetics/
        leaderboard/Image Studio metadata đều qua). Phát hiện vận hành (không phải
        bug code): tiến trình backend tạm cổng 8010 từ một lần chạy trước đó của
        chính phiên này bị treo lại (không tự tắt sau khi tool timeout), khiến vài
        lần chạy đầu âm thầm test nhầm backend mock cũ — đã `Stop-Process` và chạy
        lại sạch. 2 user dùng thử dùng địa chỉ email `@fanficdev.invalid`, không tự
        xoá (script không có quyền xoá) — dữ liệu rác vô hại, có thể dọn tay qua
        Appwrite console nếu muốn.
      - ANIMATION + TRUSTED VIDEO: đã có kết quả **19/19** rất gần đây từ
        `scripts/smoke_test_selfhost_trusted_sources.py` (tạo AnimationSeries/
        Episode/TrustedSource/quét/nhập thật qua Appwrite adapter) — dùng lại,
        không chạy trùng lặp trong phase này.
      - WEBSUB: đã có kết quả **14/14** rất gần đây từ
        `scripts/smoke_test_selfhost_websub.py` (callback giả lập, trùng lặp,
        chữ ký, reconciliation) — dùng lại, không chạy trùng lặp.
      - ADMIN qua LỚP HTTP+auth thật: **HẾT BLOCKED** (gỡ trong lúc làm Phase 5,
        xem ghi chú "BỔ SUNG" ở Phase 5 phía trên) — hoá ra
        `FAS_ADMIN_USER_IDS`/`FAS_OWNER_USER_IDS` là biến môi trường của TIẾN
        TRÌNH BACKEND, không phải cột dữ liệu trong Appwrite (`Settings.
        admin_role_of`, xem docstring `config.py`), nên KHÔNG cần thao tác tay
        trên Appwrite console để kiểm thật — chỉ cần đăng ký một user smoke-test
        thật rồi khởi một tiến trình backend tạm với `FAS_OWNER_USER_IDS=<id
        vừa tạo>`. Đã gọi thật qua HTTP+JWT: `/api/admin/overview`, `/users`,
        `/animation/series`, `/animation/sources`, `/animation/imports`,
        `/events`, `/image-studio/spending` — toàn bộ trả 200. Chưa test riêng
        suspend/unsuspend (hành động ghi, không cần thiết cho mục tiêu đo hiệu
        năng của Phase 5 — hành vi ghi/quyền hạn của các route đó đã xác nhận
        sạch ở lớp code/dependency tại Phase 3 và ở lớp service thật tại
        `smoke_test_selfhost_trusted_sources.py`).
- [x] Phase 7 — YouTube/Trusted Video reliability audit
      (`docs/reports/preprod-youtube-reliability-audit.md`). XONG — không có
      phát hiện mức BLOCKER. 3 phát hiện minor (không sửa, cần thiết kế lại,
      vượt "sửa an toàn nhỏ"): (1) `youtube_client.py::_goi()` không có
      retry/backoff nào cho lỗi mạng/5xx tạm thời — chỉ `quotaExceeded` được
      phân biệt rõ (429), còn lại đều gộp chung 502; (2) `import_video()`
      (nút "Nhập" thủ công) là check-then-act không khoá xuyên suốt — 2 admin
      bấm "Nhập" cùng lúc trên CÙNG một video có thể tạo 2 `AnimationEpisode`
      trùng `order_index` (khác với `scan_source`/`create_import_once`, đã
      xác nhận THỰC SỰ idempotent qua `documentId` tất định); nút bị disable
      ở frontend chỉ chặn double-click cùng tab, không chặn 2 phiên khác
      nhau; (3) preview bắt buộc trước khi tạo nguồn chỉ ép ở frontend,
      backend `create_source()` không gọi lại YouTube Data API để xác minh —
      admin có thể POST thẳng ID bịa đặt. Đã xác minh SẠCH: ngưỡng
      `minimum_confidence` luôn chặn trước khi đọc cờ auto_import/auto_publish
      (một đường quyết định `_quyet_dinh_trang_thai` dùng chung cho quét thủ
      công lẫn WebSub, không có đường tắt); xoá nguồn cascade đúng mapping,
      không làm mồ côi episode/import (có fallback graceful cho tên nguồn đã
      xoá). Không sửa code, không gọi mạng YouTube thật (máy này không có
      `YOUTUBE_API_KEY`).
- [~] Phase 8 — Image Studio safety/integration audit (KHÔNG chi tiêu thật) —
      ĐANG CHẠY nền (fork, `docs/reports/preprod-image-translation-tts-audit.md`)
- [~] Phase 9 — Translation/TTS integration audit (KHÔNG chi tiêu thật) —
      ĐANG CHẠY nền (cùng fork với Phase 8)
- [x] Phase 10 — Error/resilience testing (`docs/reports/preprod-resilience-audit.md`). XONG —
      SẠCH cả 5 mục: (1) TTS job pipeline (`main.py::_run_job`/`recover_stale_jobs`,
      `server/worker.py`) — claim nguyên tử + fencing token + lease/heartbeat +
      `JOB_MAX_ATTEMPTS` có trần, worker restart giữa job được nhận lại đúng; (2)
      Translation job pipeline — cùng khuôn claim/lease/fence, backoff 429/5xx có
      cấu trúc (đọc `Retry-After`, cooldown mặc định 60s khi thiếu header,
      `waiting_for_provider` tách biệt `failed` khi hết hạn mức mọi provider); (3)
      không tìm thêm `print()`/log non-ASCII nào khác có nguy cơ `UnicodeEncodeError`
      ngoài lỗi đã sửa trước đó trong phiên (`admin_overview`, `main.py:3786`) —
      `server/worker.py`/`server/translation_worker.py` đã tự `reconfigure` UTF-8
      trước mọi `print`; (4) không có `except Exception` nào che giấu lỗi thật (mọi
      transition trạng thái thành công đều qua kiểm tra rõ ràng) — chỉ ghi nhận
      MINOR: vài nhánh "việc phụ không được lỗi hỏng request chính" (dọn ảnh cũ,
      thưởng XP, báo người theo dõi) nuốt lỗi mà không log, thiếu quan sát vận hành
      nếu lỗi dai dẳng; (5) toàn bộ HTTP client ra ngoài đều có timeout tường minh
      (Appwrite 15-30s, translation provider 60s, kiểm tra kết nối 15s) — chỉ ghi
      nhận MINOR: R2 (`boto3`) không đặt `connect_timeout`/`read_timeout` tường
      minh trong `Config`, dựa vào mặc định thư viện (không phải treo vô hạn).
      Không sửa gì (không có bug đủ rõ ràng/đủ nhỏ để sửa an toàn).
- [x] Phase 11 — Accessibility audit (`docs/reports/preprod-accessibility-audit.md`). XONG —
      đo Lighthouse Accessibility qua Chrome DevTools MCP trên 6 route
      (`/`, `/fanfic`, `/animation`, `/community`, `/library`, `/login`):
      **100/100 cả 6 route**, không audit accessibility nào fail. Đọc code
      tĩnh SẠCH: skip-nav áp dụng toàn site kể cả admin (`app/layout.tsx`),
      label/aria-label đầy đủ cho input và nút icon-only, `alt` ảnh đúng (kể
      cả xác nhận `alt=""` chủ đích ở `admin/animation/sources/new/page.tsx:139`
      — thông tin đã có ở text kế bên), độ tương phản theme tối đã được rà
      soát từ trước (`globals.css` có ghi chú sửa tỉ lệ tương phản
      `--text-3`). Phát hiện MINOR (không sửa, vượt phạm vi an toàn/nhỏ):
      `ReportDialog.tsx`, `ImageLightbox.tsx`, `SearchOverlay.tsx` không bẫy
      phím Tab trong modal (khác `ConfirmDialog` — duy nhất có bẫy Tab đầy
      đủ) — Tab có thể rơi vào phần tử bị lớp phủ che khuất phía sau. Đã SỬA
      1 lỗi rõ ràng hơn: `translate/ProviderConnectDialog.tsx` (hộp thoại
      BYOK Groq/Cerebras) hoàn toàn thiếu xử lý bàn phím (không tự focus,
      Escape không đóng được, không trả tiêu điểm) — đã thêm để khớp mức tối
      thiểu của `ReportDialog`/`ImageLightbox`; `tsc --noEmit` + `eslint` qua
      sạch sau khi sửa.
      **Vòng 2** (chạy lại độc lập, không hay biết vòng 1 — trùng lặp ngoài ý
      muốn, nhưng tìm thêm được 3 lỗi thật KHÁC còn sót sau vòng 1): (1)
      `globals.css` `.tim-dau` (ô tìm kiếm `SearchOverlay`) có `outline: none`
      không thay thế — đã thêm `.tim-dau:focus-within { box-shadow: var(--ring); }`
      giống mẫu `.site-search:focus-within`; (2) `ReportDialog.tsx` docstring tự
      nhận trả tiêu điểm về nút mở nhưng code không làm — đã thêm bẫy Tab +
      lưu/trả `document.activeElement` giống `ConfirmDialog`; (3) nút chuông
      thông báo `.bell` cỡ cố định 34×34px, thiếu trong khối mobile nâng lên
      44×44 như các nút khác — đã thêm `.bell { min-width: 44px; min-height: 44px; }`
      trong `@media (max-width: 640px)` (dùng min-width/min-height thay vì
      width/height cố định để không phá một test đã khoá quy ước đó).
      `npm run typecheck` sạch, `npm test` **635/635 pass**.
- [~] Phase 12 — Security/secret audit (toàn repo + git history) — ĐANG CHẠY nền
      (fork, `docs/reports/preprod-security-audit.md`)
- [~] Phase 13 — Data/schema consistency audit — ĐANG CHẠY nền (fork,
      `docs/reports/preprod-schema-audit.md`)
- [x] Phase 14 — Worker/restart/ops audit (`docs/reports/preprod-worker-ops-audit.md`). XONG —
      graceful shutdown/stale-job ở `server/worker.py` SẠCH (SIGTERM/SIGINT chờ
      `FAS_WORKER_GRACE_SECONDS` rồi mới thoát, không giả vờ xong nếu còn job,
      lease/claim/fencing đã có sẵn cứu job kẹt `running` khi bị `kill -9`,
      khớp đúng test/tài liệu hiện có). 2 phát hiện vận hành (không phải bug
      code, KHÔNG sửa — vượt ngưỡng "nhỏ/an toàn" của phase này): (1) `/api/health`
      và `/api/ready` của web KHÔNG hề biết trạng thái worker riêng (đúng ý đồ
      kiến trúc tách rời, nhưng nghĩa là không có endpoint HTTP nào báo được
      "worker có sống không" — chỉ `python -m server.worker --check` trên chính
      host worker làm được); (2) production **thiếu hẳn** cặp
      `fanfic-worker-health.{service,timer}` (watchdog tự restart khi worker
      treo) mà bản staging đang có — `fanfic-worker-prod.service` và
      `fanfic-translation-worker-prod.service` chỉ có `Restart=always` (bắt
      crash, không bắt treo), và hệ quả liên quan: khi quên chạy worker riêng ở
      production (`FAS_INLINE_WORKER=false` đúng nhưng không tiến trình nào
      chạy), job kẹt `pending` **im lặng vô thời hạn**, không log/alert nào tự
      kích hoạt. Khuyến nghị ghi lại cho quyết định sau (không thuộc phase
      này): thêm `fanfic-worker-health-prod.*` + mở rộng
      `test_worker_deploy.py` để khoá bất biến cho nhánh production.
- [x] Phase 15 — Cross-platform/Windows test robustness
      (`docs/reports/preprod-crossplatform-audit.md`). XONG — không tìm thêm
      lỗi CRLF/LF nào khác ngoài lỗi đã biết và đã sửa trước phiên này
      (`admin-trusted-sources.test.mjs`, commit `a0420e6`): đã rà toàn bộ 31
      file `web/tests/*.test.mjs` đọc source qua `readFileSync`, không có
      khẳng định nào khác dựa vào `\n` trần khi so khớp chuỗi (các so khớp đa
      dòng còn lại đều dùng regex `\s*`/`[\s\S]`, vốn đã bao trọn `\r`).
      `server/tests/*.py` SẠCH về cấu trúc — `Path.read_text()` mặc định dịch
      universal newlines nên miễn nhiễm với dạng lỗi này (khác Node). Không
      tìm thấy Python nào ghép đường dẫn hệ điều hành cục bộ bằng `/` cứng
      thay vì `os.path.join`/`pathlib` (các chỗ dùng `/` tìm được đều là URL,
      khoá lưu trữ S3/R2, khoá `QSettings`, hoặc đường dẫn trong file zip —
      đều ĐÚNG ý đồ). Ghi nhận (không sửa, MINOR, chỉ là tài liệu): 3 lệnh
      dạng `VAR=value lenh` (cú pháp POSIX) trong khối ```bash``` của
      `CLAUDE.md:25`, `docs/DEV_SELFHOST_APPWRITE.md:45`,
      `docs/HANDOFF.md:290` — không chạy trực tiếp được trong PowerShell
      thuần/cmd.exe, chỉ đúng khi qua Git Bash. `compileall` (app.py,
      desktop_app, server, tests) và `web` `npm run typecheck` đều sạch,
      không lỗi. Không sửa code nào (không có bug thật để sửa).
- [x] Phase 16 — Documentation consistency
      (`docs/reports/preprod-doc-consistency-audit.md`). XONG — quan trọng
      nhất: KHÔNG có vi phạm quy tắc `CLAUDE.md` nào trong code (grep toàn bộ
      `server/` xác nhận không import PySide6/Qt nào, và mọi import
      `desktop_app.*` khớp đúng 4 module được phép). 2 phát hiện BLOCKER về
      tài liệu (không sửa, cần quyết định lớn hơn, chỉ ghi lại): (1)
      `docs/HANDOFF.md` (sửa cuối 2026-08-08) cực kỳ lỗi thời — hoàn toàn
      không nhắc Appwrite tự lưu trữ, Admin Control Center V2/Trusted Video
      Sources, Image Studio, Animation... dù `CLAUDE.md` vẫn trỏ người đọc mới
      vào đó; (2) `docs/WEB_README.md` (sửa cuối 2026-08-07) mục "Giới hạn
      hiện tại" khẳng định sai rằng Appwrite/R2 "chưa kiểm chứng thật", trái
      với các lần smoke test thật đã ghi nhận (kể cả Phase 6 phiên này). 1
      phát hiện MINOR: `docs/ADMIN.md` mục "API" thiếu liệt kê nhiều route
      admin mới của V2 (animation/image-studio/comments/reports/sessions) —
      không route nào ảo, chỉ là danh sách chưa đầy đủ. Đã tự sửa 1 lỗi nhỏ rõ
      ràng: `docs/WEB_README.md` còn ghi tên trường cũ `commercial_ready`
      (đã đổi thành `public_enabled` từ 2026-08-08) và câu "chưa có moderation"
      đã sai (Admin V2 đã có moderation). Đã kiểm chứng SẠCH: lệnh/đường dẫn
      trong `CLAUDE.md` gốc (compileall chạy thật, mọi path tồn tại, npm
      scripts khớp `web/package.json`), toàn bộ 18 biến `FAS_*` và mọi route
      API được nhắc trong `docs/*.md` (trừ APPWRITE_V2/SCHEMA) đều tồn tại
      thật trong code — không biến/route ảo nào.
- [ ] Phase 17 — Release-candidate report (`docs/reports/preprod-overnight-hardening-v1.md`)
- [ ] Phase 18 — Final verification
- [ ] Phase 19 — Finalize overnight branch (push, freeze, KHÔNG merge, quay về integration/pre-prod-v1 sạch)

## Checkpoint commits

(sẽ ghi SHA + tóm tắt sau mỗi phase xong)

## Phát hiện tổng hợp

(Chi tiết đầy đủ nằm trong ghi chú từng phase ở trên và các file
`docs/reports/preprod-*.md` tương ứng — mục này chỉ tóm tắt để Phase 17 dễ
tổng hợp.)

### Bugs tìm thấy và đã sửa
- Phase 5: `admin_image_studio_spending` (`server/main.py`) — 9 truy vấn đếm
  Appwrite chạy tuần tự, đo thật 7.8s. Sửa: song song hoá
  (`ThreadPoolExecutor(max_workers=4)` + `_an_toan_song_song`) → 3.1s.
- Phase 11 (vòng 1): `translate/ProviderConnectDialog.tsx` hộp thoại BYOK
  hoàn toàn thiếu xử lý bàn phím (focus/Escape) — đã thêm.
- Phase 11 (vòng 2, độc lập): `.tim-dau` (`globals.css`) thiếu focus style
  thay thế cho `outline: none`; `ReportDialog.tsx` không trả tiêu điểm về
  nút mở như docstring tự nhận; `.bell` thiếu kích thước chạm tối thiểu
  44×44 trên mobile — cả 3 đã sửa.
- Phase 16: `docs/WEB_README.md` còn nhắc tên trường cũ `commercial_ready`
  (đã đổi `public_enabled`) và câu "chưa có moderation" đã lỗi thời — đã sửa.

### Bugs CỐ Ý không sửa (ghi rõ lý do)
Xem ghi chú "minor" tại từng phase (5, 7, 10, 11, 14, 15, 16) — mỗi mục đều
ghi rõ lý do chấp nhận được (hành động ADMIN không phải đường nóng, quyết
định có chủ đích đã có comment tại chỗ, hoặc vượt phạm vi "sửa nhỏ/an
toàn" của FIX POLICY overnight này).

### Blocked (cần thao tác tay/secret/cloud console/thanh toán)
(Không còn mục nào — mục Phase 6 "ADMIN qua HTTP+auth thật" ĐÃ GỠ BLOCKED
trong lúc làm Phase 5: hoá ra vai trò admin/owner là biến môi trường của
tiến trình backend, không phải cột Appwrite, nên không cần thao tác
Appwrite console. Xem ghi chú "BỔ SUNG" ở Phase 5 và "HẾT BLOCKED" ở
Phase 6 phía trên.)

Blocked thật sự còn lại (không liên quan Phase 6, xem Phase 17 mục "known
blockers"): (A) YouTube WebSub E2E ngoài — cần callback HTTPS công khai;
(B) Ví Fanfic Credit theo người dùng — kiến trúc Appwrite hoá đã hoãn có
chủ đích sang việc khác, ngoài phạm vi phiên này; (C) Kiểm tra/dọn dữ liệu
datetime profile production lịch sử — hoãn tới khi có lại quyền truy cập
Appwrite Cloud.
