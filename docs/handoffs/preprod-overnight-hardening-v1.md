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
- [ ] Phase 1 — Route/feature inventory (`docs/reports/preprod-route-matrix.md`)
- [ ] Phase 2 — Browser QA thật (desktop/laptop/mobile)
- [ ] Phase 3 — Auth/authorization adversarial audit
- [ ] Phase 4 — Appwrite read/write cost audit v2 (`docs/reports/preprod-appwrite-cost-audit.md`)
- [ ] Phase 5 — Performance audit
- [ ] Phase 6 — Self-hosted Appwrite real smoke matrix
- [ ] Phase 7 — YouTube/Trusted Video reliability audit
- [ ] Phase 8 — Image Studio safety/integration audit (KHÔNG chi tiêu thật)
- [ ] Phase 9 — Translation/TTS integration audit (KHÔNG chi tiêu thật)
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
(chưa có)
