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
- [ ] Phase 5 — Performance audit
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
      - ADMIN (user list/detail/suspend/unsuspend/sessions/audit log) qua LỚP
        HTTP+auth thật: **BLOCKED** — `server/.env.selfhost` không có
        `FAS_ADMIN_USER_IDS`/`FAS_OWNER_USER_IDS` nào được cấu hình, tức KHÔNG có
        tài khoản admin/owner thật nào gắn với môi trường dev tự lưu trữ để đăng
        nhập thật rồi gọi các route `/api/admin/*`. Cấp quyền cho một tài khoản
        thật đòi hỏi thao tác tay trên Appwrite console (gán role) — đúng loại
        việc phải ĐÁNH DẤU BLOCKED theo quy tắc an toàn, không tự ý làm thay. Bù
        lại: hành vi các route admin đã được xác nhận sạch ở lớp
        code/dependency (Phase 3) và ở lớp service thật chống Appwrite dev qua
        `smoke_test_selfhost_trusted_sources.py` (admin_source_detail/scan/import
        đều là ghi/đọc THẬT trên Appwrite, chỉ là gọi thẳng service với Profile
        giả lập vai trò thay vì qua HTTP+JWT thật).
- [ ] Phase 7 — YouTube/Trusted Video reliability audit
- [~] Phase 8 — Image Studio safety/integration audit (KHÔNG chi tiêu thật) —
      ĐANG CHẠY nền (fork, `docs/reports/preprod-image-translation-tts-audit.md`)
- [~] Phase 9 — Translation/TTS integration audit (KHÔNG chi tiêu thật) —
      ĐANG CHẠY nền (cùng fork với Phase 8)
- [ ] Phase 10 — Error/resilience testing
- [ ] Phase 11 — Accessibility audit
- [ ] Phase 12 — Security/secret audit (toàn repo + git history)
- [ ] Phase 13 — Data/schema consistency audit
- [ ] Phase 14 — Worker/restart/ops audit
- [ ] Phase 15 — Cross-platform/Windows test robustness
- [ ] Phase 16 — Documentation consistency
- [ ] Phase 17 — Release-candidate report (`docs/reports/preprod-overnight-hardening-v1.md`)
- [ ] Phase 18 — Final verification
- [ ] Phase 19 — Finalize overnight branch (push, freeze, KHÔNG merge, quay về integration/pre-prod-v1 sạch)

## Checkpoint commits

(sẽ ghi SHA + tóm tắt sau mỗi phase xong)

## Phát hiện tổng hợp (sẽ điền dần)

### Bugs tìm thấy
(chưa có)

### Bugs đã sửa
(chưa có)

### Bugs CỐ Ý không sửa (ghi rõ lý do)
(chưa có)

### Blocked (cần thao tác tay/secret/cloud console/thanh toán)
- Phase 6, ADMIN qua HTTP+auth thật trên Appwrite dev tự lưu trữ (suspend/
  unsuspend/sessions/audit log): không có `FAS_ADMIN_USER_IDS`/
  `FAS_OWNER_USER_IDS` cấu hình cho `appwrite-dev.fanfic.world` — cần gán role
  admin/owner cho một tài khoản thật qua Appwrite console (thao tác tay), việc
  ngoài phạm vi tự động của phiên này. Đã bù bằng kiểm chứng lớp code (Phase 3,
  sạch) + lớp service thật (smoke Trusted Sources, 19/19).
