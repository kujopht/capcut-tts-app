# TOMORROW — 2026-08-23

## Đã xong đêm qua

- 5 nhánh phục hồi/tính năng, tất cả xanh, tất cả LOCAL (chưa push)
- Phase D (QA canary) hiện thực xong + test; Phase E xác minh xong + 12 guard biên
- Cổng chất lượng: backend 2653 OK · desktop 372 OK · web 809 (803 pass, 0 fail) · typecheck sạch · eslint 0 error · production build OK
- OmniRoute cài cô lập, native `claude` KHÔNG đổi (đã chứng minh bằng md5 config + version)
- `main` không bị chạm. **Không deploy production.**

## Đã hỏng / không làm được

- **Không push, không mở PR.** Token GitHub được cấp **22:38:39**, nằm TRONG cửa sổ MITM **18:52:46 → 22:47**. Phải coi là đã lộ.
- **OmniRoute: NOT WORTH IT** ở cấu hình miễn phí — 1/3 tác vụ thành công, 92 s cho một câu hỏi nhỏ, fallback tuần tự qua 7 provider, và một crash native libuv trên Windows.

## Cần MỘT hành động người

**Xoay credential từ điện thoại, rồi `gh auth login` lại trên máy này.**
Mọi việc khác đã sẵn sàng và không bị chặn.

(Riêng cho canary thật: một admin cần duyệt đơn của tài khoản fixture, HOẶC xác nhận `FAS_AUTHOR_GATE` đang TẮT trên deployment đích. Mục 9.3 khẳng định đúng hành vi cho CẢ HAI trường hợp, nên canary vẫn an toàn để chạy ngay.)

## Lệnh tiếp theo CHÍNH XÁC

Sau khi `gh auth login` xong, đẩy theo thứ tự rủi ro thấp → cao:

```bash
cd C:\Users\nguye\Documents\CapCut-TTS-App

# 1. docs+test thuần, rủi ro thấp nhất
git push -u origin recovery/oauth-staging-regression
gh pr create --base main --head recovery/oauth-staging-regression \
  --title "test(oauth): restore lost FAS_WEB_BASE_URL callback-origin coverage" \
  --body-file docs/reports/overnight-recovery-2026-08-23.md

# 2. chỉ thêm test
git push -u origin test/bulk-import-boundaries

# 3. QA canary (chỉ script, không chạm runtime)
git push -u origin feature/qa-canary-lifecycle

# 4. frontend
git push -u origin recovery/animation-player-controls

# 5. provider mới (inert theo mặc định) — review kỹ nhất
git push -u origin recovery/pollinations-translation-v2
```

## Việc production-safe tiếp theo

Chạy canary Phase D đầy đủ lên **staging** (KHÔNG production):

```bash
cd C:\Users\nguye\Documents\CapCut-TTS-App
.\.venv\Scripts\python.exe scripts/staging_smoke.py \
  --api https://<staging-api> --web https://staging.fanfic.world \
  --environment staging --job-timeout 600
```

Chờ: 5 lỗi cục bộ đêm qua (`inline_worker`, backend mock/local, URL chưa ký) PHẢI biến mất trên staging thật. Nếu còn, đó là phát hiện thật về staging chứ không phải lỗi canary.

## Việc còn lại đã cố ý chưa làm

- **Chunk-retry + audit-cache** từ commit Pollinations đã phục hồi (~150 dòng trong `translation_service.py` + `test_translation_chunk_resilience.py` 293 dòng). Là tính năng RIÊNG, default-off, xứng đáng một PR riêng. Vẫn nguyên trong bundle và trên `feature/pollinations-translation`.
- Sửa đường cũ `C:\Users\robux\...\ISCC.exe` trong `CLAUDE.md` (profile `robux` là của máy CŨ, không tồn tại trên máy này).
