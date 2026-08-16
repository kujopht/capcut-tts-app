# Handoff: Admin Control Center V2 + Trusted Video Sources

Đây là nguồn sự thật duy nhất cho một phiên Claude Code MỚI tiếp tục việc này.
Đừng dựa vào trí nhớ hội thoại trước — hãy đọc file này và kiểm tra lại code
thật trước khi sửa bất cứ gì.

Cập nhật lần cuối: 2026-08-16, sau khi Phase 4 được push.

## 0. Bootstrap cho phiên mới

Chạy trước khi làm bất cứ việc gì:

```bash
git status
git branch --show-current
git log --oneline --decorate -15
git stash list
```

Rồi đọc file này (`docs/handoffs/admin-trusted-video-v2-handoff.md`) từ đầu
đến cuối. Sau đó mới đọc code thật của các file liên quan (`server/main.py`
quanh route `/api/admin/*`, `server/config.py`, `web/src/components/AdminShell.tsx`,
`web/src/app/admin/`) trước khi sửa — đừng tin số dòng/tên hàm trong tài liệu
này mù quáng, chúng có thể lệch nếu code đã đổi từ lúc viết handoff.

## 1. Mục tiêu dự án

Ba mảng việc gộp trong một nhánh:

1. **Admin Control Center V2** — dựng lại `/admin` thành trung tâm quản trị
   thật cho Fanfic World: Dashboard, Users, Content, Animation (Series/
   Trusted Sources/Import Queue), Moderation, Analytics, AI/Credits, System,
   Audit Log.
2. **Trusted Video Sources** — mô hình kênh/playlist YouTube "tin cậy", ánh
   xạ sang series, phát hiện tập mới, hàng đợi nhập.
3. **YouTube trusted-channel auto episode sync** — đồng bộ tự động tập mới
   qua WebSub (PubSubHubbub), có cơ chế đối chiếu định kỳ dự phòng.

Đây là **một nhiệm vụ liên tục nhiều phase**, chạy trên MỘT nhánh feature duy
nhất, KHÔNG merge cho tới khi toàn bộ (ít nhất Part A + phần lõi Part B) đã
xong và được người dùng duyệt.

## 2. Trạng thái Git

- Baseline gốc: `integration/pre-prod-v1` @ `8f20fa6` (KHÔNG đổi từ baseline
  tới giờ — không có commit integration mới nào đè lên nhánh này).
- Nhánh làm việc: `feature/admin-trusted-video-v2`.
- Phase 1: commit `3372eeb` — "Admin Control Center V2, Phase 1: mo hinh ba
  muc quan tri + mo rong nhat ky kiem duyet".
- Phase 2: commit `b92583d` — "Admin Control Center V2, Phase 2: giao dien
  shell + bang tong quan".
- Phase 3: commit `b8e1f69` — "Admin Control Center V2, Phase 3: quan ly tai
  khoan day du qua Appwrite Users API".
- Phase 4: commit MỚI NHẤT trên nhánh này (chạy `git log --oneline -5` để
  lấy SHA thật — đừng tin một con số ghi cứng ở đây) — "Admin Control Center
  V2, Phase 4: kiem duyet Animation (series/tap)". Đã push.
- Remote: `origin/feature/admin-trusted-video-v2` phải khớp HEAD cục bộ sau
  khi Phase 4 được push — xác nhận lại bằng `git fetch` + `git rev-parse`
  trước khi tiếp tục Phase 5, đừng tin dòng này nếu đã có thời gian trôi qua.
- `main`: **chưa hề đụng tới** trong toàn bộ việc này. `origin/main` đang ở
  `d483e90` ("deploy: them systemd unit cho translation worker production")
  — hoàn toàn không liên quan, không có commit nào của nhánh này lọt vào.
- **Chưa merge** `feature/admin-trusted-video-v2` vào `integration/pre-prod-v1`
  hay `main`. Không được merge cho tới khi có lệnh rõ ràng.
- Working tree: sạch (không có gì uncommitted) tại thời điểm viết handoff này.

## 3. Đã xong — Phase 1 (commit `3372eeb`)

Mô hình vai trò quản trị BA MỨC, thay cho danh sách admin phẳng cũ:

- `server/config.py`: `Settings.owner_user_ids` / `.admin_user_ids` (đã có
  từ trước) / `.moderator_user_ids` — BA danh sách env var riêng, KHÔNG phải
  cột DB. Method `Settings.admin_role_of(user_id) -> AdminRole` là nguồn sự
  thật duy nhất để tính vai trò (thứ hạng cao nhất thắng nếu trùng nhiều
  danh sách). Env var: `FAS_OWNER_USER_IDS`, `FAS_ADMIN_USER_IDS`,
  `FAS_MODERATOR_USER_IDS` (danh sách user_id, phân cách bằng dấu phẩy).
- `server/domain.py`: enum `AdminRole` (NONE/MODERATOR/ADMIN/OWNER).
  `ModerationEvent` mở rộng thêm `actor_role`, `target_type`, `target_id`,
  `metadata` (không phá cấu trúc cũ, chỉ thêm trường).
- `server/main.py`: ba dependency FastAPI — `admin_profile` (bất kỳ 1 trong
  3 mức, dòng ~3553), `owner_profile` (chỉ OWNER, dòng ~3575),
  `admin_or_owner_profile` (ADMIN hoặc OWNER, dòng ~3588). Đây là điểm chốt
  bảo mật — **backend luôn tự kiểm lại qua các dependency này bất kể frontend
  gửi gì**.
- Nhật ký kiểm duyệt (`moderation_events`, collection Appwrite) mở rộng
  ENUM `action` từ 10 lên 25 giá trị qua `scripts/setup_appwrite.py`'s
  `_ensure_enum()` (cơ chế mở rộng-không-phá-vỡ có sẵn từ trước, KHÔNG viết
  migration mới).
- Đã xác nhận qua smoke test thật trên Appwrite tự lưu trú dev: tạo rồi đọc
  lại một sự kiện audit log thật, không phải chỉ đọc code tĩnh.
- Test: `server/tests/test_admin.py` — class `AdminRoleModelTest` (6 test)
  kiểm mô hình vai trò, cập nhật `test_moi_route_admin_deu_duoc_bao_ve` để
  chấp nhận cả 3 dependency thay vì chỉ `admin_profile`.

## 4. Đã xong — Phase 2 (commit `b92583d`)

**Shell/sidebar** (`web/src/components/AdminShell.tsx`):
- Mảng `NHOM_DIEU_HUONG` — điều hướng gộp NHÓM (Content/Animation/
  Moderation...) thay cho danh sách phẳng cũ.
- Điều hướng mobile: gập/mở THẬT (không còn kiểu cuộn-ngang-luôn-hiện cũ) —
  nút `.admin-nut-mobile`, `aria-expanded={moDieuHuongMobile}`,
  `aria-controls="admin-dieu-huong"`, CSS `.admin-nav` ẩn mặc định dưới
  900px, chỉ hiện khi có class `.admin-nav-mo`.
- Hàm `duVaiTro(cua, toiThieu)` — CHỈ là gợi ý hiển thị UI, KHÔNG phải biên
  bảo mật thật (bảo mật thật luôn ở backend, xem mục 8).
- Huy hiệu vai trò (OWNER/ADMIN/MODERATOR) hiển thị cạnh tiêu đề.
- Component `OSo` (số liệu) mở rộng nhận `so: number | null` — `null` hiện
  "—", KHÔNG BAO GIỜ hiện "0" giả. Component mới `ChuaCauHinh` cho khối
  "chưa cấu hình/chưa xây dựng".

**Dashboard** (`web/src/app/admin/page.tsx`):
- 6 nhóm: Người dùng, Nội dung, Sản phẩm, Trusted Sources, Lưu lượng, Hệ
  thống. Đọc từ `/api/admin/overview` đã mở rộng (xem mục 6 về hiệu năng).
- Chỉ số chưa theo dõi được (verified/unverified/suspended, traffic khi
  chưa có Cloudflare credential, số lượt sinh ảnh) trả `null` thay vì bịa 0.

**Trang mới:**
- `/admin/audit-log` (thay hẳn `/admin/events` — file cũ đã XOÁ) — đọc
  `/api/admin/events` với bộ lọc `action`/`target_type`/`target_user_id` +
  phân trang offset.
- `/admin/ai-credits` — trang THẬT: xem chi tiêu Image Studio + công tắc
  khẩn cấp (kill-switch), nút chỉ bật khi `profile.admin_role === "owner"`.
- `/admin/analytics` — trang THẬT, dùng lại dữ liệu traffic/product từ
  `/api/admin/overview`.
- `/admin/system` — trang THẬT, hiện tình trạng Appwrite/worker/provider
  dịch.
- `/admin/animation`, `/admin/animation/sources`, `/admin/animation/import-queue`
  — trang TĨNH dùng component `AdminSapXayDung` ("Sắp xây dựng"), CHỜ Phần B
  (Phase 5). Các trang này KHÔNG gọi `adminApi` — có test khẳng định điều
  này, nếu sau này thêm dữ liệu thật vào một trong các trang này thì PHẢI
  đổi sang dùng `DanhSachTrangThai` như các trang khác.

**QA trình duyệt thật** (chrome-devtools MCP, đăng nhập OWNER trên Appwrite
tự lưu trú dev):
- Sidebar phân nhóm + huy hiệu vai trò hiển thị đúng trên desktop.
- Dashboard tải xong và hiện số thật: 10 người dùng, nội dung = 0 (trung
  thực — DB dev chưa có truyện/chương nào), 1 dự án dịch.
- Độ trễ tải ban đầu ~13-14 giây được quan sát — xem mục 6, KHÔNG phải vòng
  lặp gọi lại (số lượng network request đứng yên, không tăng thêm mãi).
- **CHƯA xác nhận trực quan** hành vi gập/mở nav ở viewport mobile thật —
  công cụ resize viewport gặp trục trặc kỹ thuật trong phiên đó. Hành vi
  CSS/ARIA đã được test đơn vị khẳng định (xem `web/tests/admin-control-center-v2.test.mjs`),
  nhưng chưa có screenshot mobile thật. Nên làm việc này sớm ở phiên sau nếu
  có sửa gì tới nav.

## 4b. Đã xong — Phase 3 (Full User Management)

**Ý chính: hai khái niệm "tạm dừng" TÁCH BIỆT, đừng nhầm.**
- Treo TÁC GIẢ (đã có từ trước, `/api/admin/authors/{id}/suspend`) — chỉ chặn
  XUẤT BẢN mới. Tác giả vẫn đăng nhập, đọc, nghe bình thường.
- Tạm dừng TÀI KHOẢN (MỚI Phase 3, `/api/admin/users/{id}/suspend`) — khoá
  ĐĂNG NHẬP hoàn toàn (email lẫn OAuth), qua `PATCH /v1/users/{id}/status`
  của Appwrite. Không đụng gì tới `author_status`.

**Backend:**
- `server/domain.py`: hai dataclass mới `AccountStatus` (trạng thái tài
  khoản native: `enabled`/`email_verified`/`phone_verified`/`registered_at`)
  và `AccountSession` (một phiên đăng nhập). KHÔNG lưu vào `profiles` — đọc
  thẳng từ Appwrite Auth mỗi lần hỏi.
- `server/adapters.py` (`IdentityAdapter` Protocol + `MockIdentityAdapter`)
  và `server/appwrite_adapter.py` (`AppwriteIdentityAdapter`, bản THẬT): sáu
  hàm mới — `list_accounts`, `account_status`, `list_sessions`,
  `terminate_session`, `terminate_all_sessions`, `set_account_enabled`,
  `count_accounts`. Bản Appwrite gọi THẲNG REST `/v1/users*` (native Users
  API), KHÔNG qua collection `profiles` — xác nhận qua smoke test thật (mục
  dưới), field `search` là tham số RIÊNG của `/v1/users` (khác `contains`
  bên Databases), `registration`/`$createdAt` trả về ISO string (không phải
  timestamp số như một số tài liệu AI-tóm-tắt ghi sai).
- `server/creator_service.py`: `admin_users`/`admin_user` ĐỔI NGUỒN — giờ
  đọc `list_accounts` (native) trước, làm giàu bằng `profiles_by_ids` theo
  LÔ (không N+1), nên một tài khoản CHƯA chọn username vẫn hiện ra (khác
  hành vi Phase 2 cũ, vốn chỉ thấy người đã có hồ sơ công khai). Bốn hàm
  mới: `admin_set_account_enabled`, `admin_terminate_session`,
  `admin_terminate_all_sessions` — đều ghi `ModerationEvent` qua hạ tầng có
  sẵn từ Phase 1 (`user_suspend`/`user_unsuspend`/`user_session_terminate`,
  BA giá trị này đã có sẵn trong enum Appwrite từ Phase 1, không cần
  migration enum mới).
- `server/main.py`: bốn route mới, đều `Depends(admin_or_owner_profile)` —
  `POST /api/admin/users/{id}/suspend`, `.../unsuspend`,
  `.../sessions/{session_id}/terminate`, `.../sessions/terminate-all`. Hàm
  rào chắn `_kiem_quyen_tac_dong_tai_khoan(admin, target_user_id)` (ngay
  trước `class NoteIn`) chặn HAI rủi ro thật:
  - Tự thao tác lên chính mình (400) — tránh tự khoá mình giữa lúc thao tác.
  - ADMIN thao tác lên tài khoản của một quản trị KHÁC (ADMIN/OWNER) — CHỈ
    OWNER được làm việc này (403 cho ADMIN).
  - **KHÔNG có route "đổi vai trò"**: vai trò là biến môi trường
    (`Settings.admin_role_of`), không phải cột ghi được (xem mục 8) — nên
    rủi ro kinh điển "ADMIN tự nâng mình lên OWNER" trong checklist Phase 3
    gốc KHÔNG áp dụng được ở kiến trúc này, đây là quyết định có chủ đích
    chứ không phải bỏ sót.
  - **KHÔNG có nút xoá tài khoản** — dù Appwrite Users API hỗ trợ
    `DELETE /v1/users/{id}`, handoff gốc yêu cầu cân nhắc kỹ trước khi phơi
    ra UI; quyết định ở phiên này là CHƯA làm, để dành hỏi người dùng nếu
    thật sự cần.
  - `/api/admin/overview`: `users.verified/unverified/suspended` giờ là SỐ
    THẬT (`identity.count_accounts(...)`), không còn `None` — lấp đúng chỗ
    trống Phase 2 để lại.
  - `admin_role` được thêm vào MỌI response `/api/admin/users` và
    `/api/admin/users/{id}` — tính lại ở tầng route (`settings.admin_role_of`),
    không cache trong service.
- Test: `server/tests/test_admin.py`, class `AccountManagementTest` (10 test
  mới) — bao gồm tài khoản chưa có username vẫn hiện, tạm dừng chặn đăng
  nhập KHÔNG đụng `author_status`, rào chắn tự-thao-tác và rào chắn
  cross-rank, chấm dứt một phiên/tất cả phiên, nhật ký ghi đúng hành động.
  Cập nhật `test_truong_chua_theo_doi_tra_None_khong_bia_so_0` (đổi tên ý
  nghĩa: giờ khẳng định số THẬT thay vì `None`).

**Frontend:**
- `web/src/lib/api.ts`: `AdminUser` mở rộng (`email_verified`,
  `account_enabled`, `registered_at`, `admin_role`, `account`, `sessions`),
  hai interface mới `AdminAccountStatus`/`AdminAccountSession`, bốn hàm
  `adminApi.suspendAccount/unsuspendAccount/terminateSession/terminateAllSessions`.
- `web/src/app/admin/users/page.tsx`: danh sách giờ hiện CẢ tài khoản chưa
  có username (`"chưa chọn tên công khai"` thay vì link chết tới `/u/...`),
  thêm cột "Trạng thái tài khoản", mỗi hàng dẫn sang trang chi tiết mới.
- `web/src/app/admin/users/[user_id]/page.tsx` — MỚI. Trang chi tiết MỘT
  tài khoản: trạng thái tác giả và trạng thái tài khoản vẽ ở HAI thẻ riêng
  (rõ ràng đây là hai khái niệm khác nhau), danh sách phiên đăng nhập kèm
  nút chấm dứt từng phiên/tất cả, nút tạm dừng/bỏ tạm dừng tài khoản (đều
  qua `ConfirmDialog` kèm ô ghi chú). Nút thao tác TỰ ẨN khi
  `profile.user_id === userId` (rào chắn thật vẫn ở backend, đây chỉ là UX
  tránh một cú bấm vô ích).
- Test: `web/tests/admin-account-management.test.mjs` (8 test mới).

**Smoke test THẬT trên Appwrite tự lưu trú dev** (không phải chỉ đọc code
tĩnh) — quy trình: khởi động backend tạm ở CỔNG RIÊNG (không phải 8010, vốn
đang bị một tiến trình uvicorn cũ từ phiên trước chiếm giữ — ĐÃ KHÔNG đụng
vào tiến trình đó, không rõ nó có đang được ai dùng hay không), đăng ký hai
tài khoản dùng-một-lần qua `/api/auth/register` (một gán làm OWNER qua
`FAS_OWNER_USER_IDS` khi khởi động lại backend, một làm mục tiêu test),
KHÔNG bao giờ in `user_id`/token ra tài liệu này. Đã xác nhận qua HTTP thật:
- `GET /api/admin/users?q=...` trả về tài khoản CHƯA có username, `search`
  của Appwrite khớp theo TOKEN (không phải substring y hệt) — ghi nhận khác
  biệt so với `contains` của `search_profiles` cũ.
- Tạm dừng tài khoản → đăng nhập trả **401 thật** ngay sau đó; bỏ tạm dừng →
  đăng nhập lại **200**.
- Chấm dứt MỘT phiên và chấm dứt TẤT CẢ phiên đều phản ánh đúng ở
  `GET /v1/users/{id}/sessions` ngay sau đó (số phiên giảm đúng số lượng).
- Rào chắn tự-thao-tác: 400 thật khi OWNER gọi suspend lên chính mình.
- Rào chắn cross-rank: 403 thật khi ADMIN gọi suspend lên tài khoản OWNER.
- `/api/admin/overview`: `verified`/`unverified`/`suspended` phản ánh ĐÚNG
  trạng thái thật trên Appwrite (12 tài khoản thật trên DB dev lúc test, tất
  cả chưa xác minh email — số `unverified` khớp).
- Hai tài khoản dùng-một-lần được GIỮ LẠI trên DB dev sau khi test (không
  xoá) — cùng tiền lệ với tài khoản `smoketest@fanficdev.invalid` đã có sẵn
  từ trước; Appwrite Cloud production KHÔNG bị đụng tới trong toàn bộ quá
  trình này.

## 4c. Đã xong — Phase 4 (Animation Moderation)

**Phát hiện quan trọng NHẤT trước khi viết code**: `AnimationEpisode.state`
(PublishState draft/published) **KHÔNG hề gác hiển thị công khai nào cả** —
`list_episodes()`/`get_animation_episode` trả về MỌI tập bất kể `state`,
hiển thị của một tập phụ thuộc HOÀN TOÀN vào trạng thái SERIES cha. Mọi tập
từng tạo đều có `state=draft` mặc định và KHÔNG có route nào từng đổi nó.
Nếu tái dùng thẳng `state` để "gỡ tập" thì việc THỰC THI gác đó lần đầu tiên
sẽ làm MỌI tập đang có (state=draft) biến mất khỏi công khai — một hồi quy
lớn. Quyết định: thêm TRƯỜNG MỚI, KHÔNG đụng `state`.

**Kiến trúc kiểm duyệt — hai trục TÁCH BIỆT, xem docstring
`AnimationSeries.moderation_state`/`AnimationEpisode.moderation_state`:**
- `state` (đã có) — trục XUẤT BẢN của CHỦ SỞ HỮU, họ tự đổi qua
  `/api/animation/series/{id}/publish|unpublish`. Quản trị KHÔNG đụng vào.
- `moderation_state` (MỚI, `visible`/`removed`) — trục GỠ XUỐNG của QUẢN
  TRỊ, cùng khái niệm với `ContentState` của Post/Comment. Chủ sở hữu
  KHÔNG đổi được qua bất kỳ route nào của họ — đã xác nhận THẬT: chủ sở
  hữu bấm "Xuất bản" lại sau khi bị gỡ vẫn nhận **200** (route thành công)
  nhưng nội dung VẪN 404 công khai, vì `moderation_state` không đổi.
- Mặc định `VISIBLE` cho MỌI series/tập — migration-an-toàn, không đổi hiện
  trạng công khai của dữ liệu cũ (schema mới KHÔNG bắt buộc, đọc thiếu/NULL
  thành VISIBLE).

**Backend:**
- `server/animation_domain.py`: thêm `moderation_state`/`removed_by`/
  `removed_reason` vào CẢ `AnimationSeries` và `AnimationEpisode`.
- `server/animation_store.py`/`server/appwrite_animation_store.py`: `find_series`
  thêm `state`/`include_removed`/`sort` (mặc định `include_removed=False`
  — ẩn nội dung đã gỡ khỏi MỌI listing công khai, kể cả của chính chủ);
  `list_episodes` thêm `include_removed`; MỚI `episode_counts()` (batch,
  không N+1); MỚI `admin_unpublish_series`/`admin_restore_series`/
  `admin_unpublish_episode`/`admin_restore_episode` — KHÔNG kiểm chủ sở
  hữu (đây là quyền quản trị). Bản Appwrite dùng `q_equal_or_null()` (mới)
  để lọc `moderation_state` an toàn với dữ liệu cũ chưa có thuộc tính này
  (`equal("visible")` không khớp NULL — cùng bài học với `target_kind` cũ
  ở `appwrite_social.py`).
- `server/main.py`: `_may_read_series` + `get_animation_episode` gác THÊM
  `moderation_state`. Sáu route mới dưới `/api/admin/animation/*`, TẤT CẢ
  dùng `Depends(admin_profile)` (≥ MODERATOR — khác Phase 3 vốn cần
  `admin_or_owner_profile`, vì đây là kiểm duyệt nội dung thông thường,
  cùng mức với báo cáo/bài đăng/bình luận). Route unpublish BẮT BUỘC
  `reason` (400 nếu rỗng, xem `SocialService.unpublish_animation_series`).
- `server/social_service.py`: MỚI `admin_animation_series`/
  `admin_animation_series_detail`/`unpublish_animation_series`/
  `restore_animation_series`/`unpublish_animation_episode`/
  `restore_animation_episode` — tái dùng `self._animation_store` đã có sẵn
  (nối từ trước cho bình luận tập), `self._store.novels_by_ids`/
  `self._identity.profiles_by_ids` để làm giàu KHÔNG N+1, và
  `_ghi_nhat_ky` (mở rộng thêm `actor_role`/`target_type`/`target_id`,
  tương thích ngược) để ghi nhật ký — TÁI DÙNG action `content_unpublish`/
  `content_restore` đã có sẵn từ Phase 1 (không cần migration enum mới),
  `target_type="animation_series"` hoặc `"animation_episode"`.
- **Sửa một lỗ hổng kiểm duyệt bình luận đã có từ trước (V6)**: bình luận
  tập Animation (`target_kind="animation_episode"`) đã tồn tại nhưng
  `admin_browse_comments`/`admin_reports` tính `context_url` SAI cho loại
  này (rơi vào nhánh mặc định `/posts/{id}`, trong khi `{id}` là
  `episode_id` chứ không phải `post_id`) — sửa bằng hàm dùng chung
  `_duong_nguon_binh_luan()`, và `admin_browse_comments` nay chấp nhận
  `target_kind=animation_episode` (trước đó bị 400 dù dữ liệu tồn tại).
  Cũng vá `_tap_cong_khai` để gác THÊM `moderation_state` — trước đó một
  series/tập bị gỡ vẫn bình luận được.
- Thêm `target_id` vào `list_events`/`admin_events`/`/api/admin/events`
  (mở rộng thêm, tương thích ngược) — tra được lịch sử của MỘT đối tượng cụ
  thể (một series) trong một truy vấn, tránh N+1 khi ghép lịch sử vào
  trang chi tiết.
- `scripts/setup_appwrite.py`: thêm `moderation_state`/`removed_by`/
  `removed_reason` (không bắt buộc) + index `moderation_idx` vào CẢ
  `animation_series` và `animation_episodes`.
- Test: `server/tests/test_animation_contract.py` (+8, chạy trên CẢ mock
  và Appwrite giả lập), `server/tests/test_animation_domain.py` (mở rộng),
  `server/tests/test_social_service.py::BinhLuanTapAnimationTest` (+5,
  MỚI), `server/tests/test_social_routes.py::KiemDuyetAnimationTest` (+9,
  MỚI, HTTP đầy đủ — bao gồm xác nhận chủ sở hữu KHÔNG hoàn tác được lệnh
  gỡ bằng publish lại, kiểm qua HTTP thật).

**Frontend:**
- `web/src/app/admin/animation/page.tsx` — ĐỔI từ placeholder
  `AdminSapXayDung` sang trang landing THẬT (link tới Series/Trusted
  Sources/Import Queue), không gọi `adminApi` (không cần trạng thái tải).
- `web/src/app/admin/animation/series/page.tsx` — MỚI. Danh sách series
  TOÀN NỀN TẢNG (mọi chủ sở hữu), tìm kiếm debounce, lọc trạng thái xuất
  bản, sắp xếp mới/cũ, phân trang server (offset/limit).
- `web/src/app/admin/animation/series/[id]/page.tsx` — MỚI. Chi tiết MỘT
  series: HAI thẻ trạng thái TÁCH BIỆT (xuất bản của chủ vs kiểm duyệt),
  bảng tập kèm nút gỡ/phục hồi RIÊNG từng tập, lịch sử kiểm duyệt của
  series. Gỡ series/tập đều qua `ConfirmDialog` kèm ô lý do BẮT BUỘC.
- `AdminShell.tsx`: mục nav "Series" đổi href từ `/admin/animation` sang
  `/admin/animation/series` (trỏ thẳng vào danh sách, khớp trang landing
  mới).
- `web/src/app/admin/comments/page.tsx`: thêm bộ lọc "Bình luận tập
  Animation", nhãn hiển thị đúng ba loại (trước đó bình luận tập Animation
  bị hiển thị nhầm thành "Bài đăng").
- **Sửa một bug UI nghiêm trọng, phát hiện qua QA trình duyệt THẬT (không
  phải qua test tĩnh)**: `ConfirmDialog` (`web/src/components/ui.tsx`) có
  effect bẫy focus/Escape với `onCancel` trong mảng phụ thuộc. MỌI nơi gọi
  `<ConfirmDialog>` đều truyền `onCancel` dạng hàm nền inline
  (`() => setHoi(null)`) — một THAM CHIẾU MỚI mỗi lần cha render lại. Khi
  `body` là một ô nhập có kiểm soát (textarea ghi lý do — CHÍNH XÁC tình
  huống Phase 3 VÀ Phase 4 vừa thêm), MỖI PHÍM GÕ gọi `setState` → cha
  render lại → effect DỌN RỒI CHẠY LẠI → tiêu điểm bị giật khỏi ô nhập về
  nút đã mở hộp thoại. Hậu quả: **không ai gõ được quá MỘT ký tự vào bất
  kỳ ô lý do kiểm duyệt nào trong toàn bộ khu quản trị** (treo tác giả, gỡ
  bài/bình luận, tạm dừng tài khoản Phase 3, gỡ series/tập Phase 4) — một
  hồi quy im lặng đã tồn tại từ Phase 2/3, không bài test tĩnh nào bắt
  được vì các bài đó chỉ đọc mã nguồn bằng regex, không thật sự chạy
  component trong trình duyệt. Sửa: thêm `onCancelRef` (ref giữ `onCancel`
  MỚI NHẤT, cập nhật trong effect không phụ thuộc), effect bẫy focus chỉ
  còn phụ thuộc `[open]`. Xác nhận lại bằng gõ thật qua
  `type_text`/`evaluate_script` trong trình duyệt, không chỉ đọc code.
- Test: `web/tests/admin-animation-moderation.test.mjs` (MỚI, 12 test),
  `web/tests/ui.test.mjs` (+1, khẳng định cấu trúc ref/dependency của fix
  trên để không hồi quy), `web/tests/admin.test.mjs` (nới ngoại lệ "trang
  tĩnh không cần DanhSachTrangThai" từ riêng `AdminSapXayDung` thành MỌI
  trang không gọi `adminApi`), `web/tests/admin-control-center-v2.test.mjs`
  (sửa href nav Series + sửa một chỗ dò `indexOf("  events:")` bị trùng
  với trường `events` mới trong interface Phase 4).

**Smoke test THẬT trên Appwrite tự lưu trú dev** — chạy migration schema
thật (`scripts/setup_appwrite.py --only animation_series` và
`--only animation_episodes`, xác nhận 4 thuộc tính+1 index MỚI mỗi bảng,
15-16 mục còn lại đã có), tạo series+tập dùng-một-lần thật, và xác nhận
qua HTTP thật:
- Danh sách/chi tiết series quản trị đọc đúng, làm giàu đúng (chủ sở hữu,
  số tập) từ dữ liệu thật.
- Gỡ series → công khai 404 NGAY; chủ sở hữu tự `publish` lại → route trả
  200 nhưng **VẪN 404 công khai** (xác nhận đúng thiết kế: quản trị go
  xuống không thể bị chính chủ hoàn tác); phục hồi → 200 trở lại.
- Gỡ MỘT tập không đụng series cha (series vẫn xuất bản, chỉ tập đó biến
  mất khỏi danh sách công khai); phục hồi tập → hiện lại.
- Nhật ký kiểm duyệt ghi đúng `content_unpublish`/`content_restore`,
  `target_type`, `target_id`, `actor_role`, lọc qua `target_id` đúng.
- Ranh giới quyền: 401 ẩn danh thật, 403 người dùng thường thật.

**QA trình duyệt THẬT** (chrome-devtools MCP, đăng nhập OWNER thật qua
`localhost:3000` trỏ về backend dev thật trên cổng riêng): danh sách
series, chi tiết series, gỡ/phục hồi qua UI với ConfirmDialog + ô lý do —
phát hiện VÀ sửa bug ConfirmDialog nói trên ngay tại đây. **Lưu ý môi
trường cho phiên sau**: một tiến trình `next dev` khác đang chạy sẵn trên
cổng 3000 (không phải do phiên này khởi động) đã NGỪNG HOẠT ĐỘNG trong lúc
phiên này thử khởi động một `next dev` thứ hai (Next 16 chặn hai tiến
trình dev cùng thư mục) — tương quan thời điểm rõ, nguyên nhân chính xác
CHƯA chắc chắn. Nếu có ai đó đang dựa vào dev server đó, họ cần tự khởi
động lại (`npm run dev` trong `web/`).

## 5. Trạng thái test/build (đã CHẠY LẠI và xác nhận ngay tại thời điểm viết
handoff này, không phải chỉ nhớ lại)

| Mục | Kết quả |
|---|---|
| Backend (`unittest discover -s server/tests -t .`) | **2189/2189 pass** (1 skipped, không liên quan — thiếu file `.onnx.json` test model cục bộ) — +22 test Phase 4 |
| Frontend (`npm test` = `node --test tests/*.test.mjs`) | **597/597 pass** — +13 test Phase 4 |
| `npm run typecheck` | sạch, 0 lỗi |
| `npm run lint` | 0 lỗi, 2 warning (không liên quan — `<img>` ở `image-studio/page.tsx`, có từ trước) |
| `npm run build` | build production thành công, `/admin/animation/series/[id]` lên đúng route động |
| Secret scan (grep diff cho api_key/secret/token/password/bearer/aws_/private_key + kiểm không có file `.env` nào bị đổi) | sạch |
| Smoke test thật trên Appwrite tự lưu trú dev | ĐÃ CHẠY — xem mục 4b (Phase 3), 4c (Phase 4) |
| QA trình duyệt thật | ĐÃ CHẠY Phase 4 (xem mục 4c) — phát hiện + sửa 1 bug ConfirmDialog thật |

## 6. Quyết định về hiệu năng

- **Không quét toàn bảng, không N+1.** Mọi số đếm mới (users, novels,
  chapters, animation series/episodes, tts jobs, translation projects,
  comments) dùng idiom có sẵn trong codebase: `self._page(COLLECTION,
  [q_limit(1)])[1]` — đọc `total` từ response danh sách của Appwrite mà
  KHÔNG kéo document nào về. Áp dụng nhất quán cho mọi bộ đếm mới trong
  `_admin_dashboard_them()` (`server/main.py`).
- `server/appwrite_store.py::q_greater_equal()` dùng để lọc "mới trong N
  ngày" — **CHÚ Ý**: tên method Appwrite đúng là `"greaterThanEqual"`,
  KHÔNG phải `"greaterEqual"` (bug thật đã gặp và sửa trong phiên này, phát
  hiện qua smoke test thật, không phải qua đọc doc — nếu thấy `"greaterEqual"`
  ở đâu đó khác trong codebase thì đó cũng là bug cùng loại).
- **Quan sát độ trễ CHƯA giải quyết**: `/api/admin/overview` mất khoảng
  13-14 giây để tải xong hoàn toàn khi test qua trình duyệt thật chống lại
  Appwrite tự lưu trú (VM ở xa, không phải localhost). Nguyên nhân nhiều khả
  năng là `_admin_dashboard_them()` gọi TUẦN TỰ ~12-15 truy vấn Appwrite độc
  lập (mỗi truy vấn RIÊNG LẺ đã bị chặn/bounded đúng yêu cầu, nhưng tổng độ
  trễ MẠNG của việc gọi tuần tự cộng dồn lại). Đã xác nhận đây KHÔNG phải
  vòng lặp gọi lại (số lượng network request trong DevTools đứng yên, không
  tăng thêm mãi theo thời gian).
  - **Chưa tối ưu.** Hướng khả dĩ cho phase sau: song song hoá các lệnh gọi
    độc lập trong `_admin_dashboard_them()` (vd `ThreadPoolExecutor` ở phía
    Python, vì các truy vấn không phụ thuộc lẫn nhau), hoặc cache ngắn hạn
    (vài chục giây) cho kết quả tổng quan nếu việc gọi lại liên tục là vấn đề
    thật ở production.
  - Đây KHÔNG chặn Phase 2 được coi là "xanh" — đã được người dùng chấp nhận
    ghi nhận làm việc tiếp theo, không phải lỗi chặn checkpoint.
- Không có lớp cache mới nào được thêm cho dashboard trong Phase 2 — mỗi lần
  tải trang là một lượt gọi thật tới Appwrite (bounded từng truy vấn, nhưng
  không cache tổng thể response).

## 7. Môi trường Appwrite phát triển hiện tại

- Endpoint: `https://appwrite-dev.fanfic.world/v1` (tự lưu trú, VM
  `fanfic-appwrite-temp`, KHÔNG PHẢI Appwrite Cloud production).
- Database ID: `fanfic_world_dev`.
- File cấu hình dev: `server/.env.selfhost` (bị `.gitignore` chặn, không
  bao giờ commit — file này CHỨA giá trị thật của `APPWRITE_PROJECT_ID` và
  API key, **KHÔNG chép giá trị đó vào bất kỳ tài liệu nào**, kể cả handoff
  này).
- Cách chạy backend dev chống lại Appwrite tự lưu trú:
  ```bash
  FAS_ENV_FILE=server/.env.selfhost FAS_INLINE_WORKER=true \
    FAS_OWNER_USER_IDS=<user_id_that_da_dang_ky> \
    .venv/Scripts/python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8010
  ```
  Xác nhận qua `/api/health` → `identity`/`data_backend == "appwrite"`.
- **Appwrite Cloud production TUYỆT ĐỐI không được đụng tới** trong toàn bộ
  công việc này — mọi smoke test thật đều chạy trên endpoint dev ở trên.

## 8. Kiến trúc bảo mật quản trị

- Ba mức: **OWNER > ADMIN > MODERATOR**, đại diện bằng BA danh sách
  user_id trong biến môi trường (`FAS_OWNER_USER_IDS`/`FAS_ADMIN_USER_IDS`/
  `FAS_MODERATOR_USER_IDS`), **KHÔNG BAO GIỜ** là một cột/trường ghi được
  trong DB — đây là triết lý bảo mật đã có từ trước khi bắt đầu việc này
  (xem `docs/ADMIN.md`), lý do: một cột DB ghi được là một đường leo thang
  đặc quyền nếu có bug ở BẤT KỲ luồng ghi nào; danh sách env var thì chỉ
  người có quyền deploy mới đổi được.
- **Backend luôn là nơi quyết định thật.** Route `/api/admin/*` tự kiểm qua
  `admin_profile`/`admin_or_owner_profile`/`owner_profile`
  (`server/main.py`, dòng ~3553-3600) — một người sửa `admin_role` bằng tay
  trong DevTools/localStorage của trình duyệt vẫn bị 403 ở backend.
- **Điều hướng/hiển thị ở frontend KHÔNG PHẢI biên bảo mật** — chỉ là gợi ý
  UX (ẩn mục sidebar không phù hợp vai trò). Đã có test khẳng định điều này
  (`web/tests/admin.test.mjs`: "cong chan hoi MAY CHU, khong doc mot co
  trong trang thai" — cấm mọi biến `is_admin`/`isAdmin` tự quyết định trong
  code frontend).
- Route hiện phân theo mức:
  - `admin_profile` (≥ MODERATOR): reports, posts, comments (moderation-scoped),
    **animation/series (Phase 4 — list/detail/unpublish/restore series+episode)**.
  - `admin_or_owner_profile` (≥ ADMIN): author-applications, authors, users,
    events (audit log), social/overview, translate/usage, image-studio/spending,
    novels, **users/{id}/suspend|unsuspend|sessions/\* (Phase 3)**.
  - `owner_profile` (chỉ OWNER): image-studio kill-switch (POST).

## 9. File/route Admin V2 hiện có

**Backend routes** (`server/main.py`, tất cả dưới `/api/admin/`):
```
GET  /api/admin/overview
GET  /api/admin/author-applications
GET  /api/admin/author-applications/{user_id}
POST /api/admin/author-applications/{user_id}/approve
POST /api/admin/author-applications/{user_id}/reject
GET  /api/admin/authors
POST /api/admin/authors/{user_id}/suspend
POST /api/admin/authors/{user_id}/restore
GET  /api/admin/users
GET  /api/admin/users/{user_id}
GET  /api/admin/novels
GET  /api/admin/events
GET  /api/admin/social/overview
GET  /api/admin/reports
POST /api/admin/reports/{report_id}/resolve
GET  /api/admin/posts
POST /api/admin/posts/{post_id}/remove
POST /api/admin/posts/{post_id}/restore
GET  /api/admin/comments
GET  /api/admin/posts/{post_id}/comments
POST /api/admin/comments/{comment_id}/remove
POST /api/admin/comments/{comment_id}/restore
GET  /api/admin/translate/usage
GET  /api/admin/image-studio/spending
POST /api/admin/image-studio/kill-switch
POST /api/admin/users/{user_id}/suspend                          — MỚI Phase 3
POST /api/admin/users/{user_id}/unsuspend                        — MỚI Phase 3
POST /api/admin/users/{user_id}/sessions/{session_id}/terminate  — MỚI Phase 3
POST /api/admin/users/{user_id}/sessions/terminate-all           — MỚI Phase 3
GET  /api/admin/animation/series                                — MỚI Phase 4
GET  /api/admin/animation/series/{series_id}                    — MỚI Phase 4
POST /api/admin/animation/series/{series_id}/unpublish           — MỚI Phase 4
POST /api/admin/animation/series/{series_id}/restore             — MỚI Phase 4
POST /api/admin/animation/episodes/{episode_id}/unpublish        — MỚI Phase 4
POST /api/admin/animation/episodes/{episode_id}/restore          — MỚI Phase 4
```
Lưu ý: `GET /api/admin/users` và `GET /api/admin/users/{user_id}` (Phase 3)
giờ đọc THẲNG Appwrite Users API (native) làm nguồn chính, làm giàu bằng
`profiles` — xem mục 4b. Bốn route quản lý tài khoản đều gọi qua
`_kiem_quyen_tac_dong_tai_khoan()` (rào chắn tự-thao-tác + cross-rank).
Sáu route Animation (Phase 4) đều `admin_profile` (≥ MODERATOR) và gọi qua
`SocialService` (`social.admin_animation_series*`/`unpublish_animation_*`/
`restore_animation_*`) — xem mục 4c.

**Frontend** (`web/src/app/admin/`):
```
layout.tsx              — bọc <AdminShell> quanh mọi trang con
page.tsx                — Dashboard
users/                  — danh sách tài khoản (ĐỔI NGUỒN ở Phase 3, xem mục 4b)
users/[user_id]/        — MỚI Phase 3: chi tiết một tài khoản, tạm dừng/
                          phiên đăng nhập
authors/                — đơn tác giả + danh sách tác giả (đã có từ trước)
stories/                — duyệt truyện (đã có từ trước, KHÔNG có nút xoá — có chủ đích)
posts/, comments/, reports/  — moderation xã hội (đã có từ trước)
audit-log/              — MỚI Phase 2, thay /admin/events (đã xoá)
analytics/               — MỚI Phase 2
ai-credits/              — MỚI Phase 2
system/                  — MỚI Phase 2
animation/               — ĐỔI Phase 4: tu placeholder sang trang landing THẬT
animation/series/       — MỚI Phase 4: danh sách series TOÀN NỀN TẢNG
animation/series/[id]/  — MỚI Phase 4: chi tiết series + kiểm duyệt tập
animation/sources/       — CÒN placeholder Phase 2, CHỜ Phase 5
animation/import-queue/  — CÒN placeholder Phase 2, CHỜ Phase 5
```
Component chính: `web/src/components/AdminShell.tsx` (shell/nav/OSo/
ChuaCauHinh/duVaiTro — Phase 4 đổi href nav "Series" sang
`/admin/animation/series`), `web/src/components/AdminSapXayDung.tsx`
(placeholder tái dùng được, còn dùng cho sources/import-queue),
`web/src/components/ui.tsx::ConfirmDialog` (Phase 4 sửa bug focus, xem mục
4c), `web/src/lib/api.ts` (mọi type + hàm gọi `adminApi.*`).

Test: `server/tests/test_admin.py` (class `AccountManagementTest` Phase 3),
`server/tests/test_animation_contract.py`/`test_animation_domain.py`
(Phase 4), `server/tests/test_social_service.py::BinhLuanTapAnimationTest`
(Phase 4), `server/tests/test_social_routes.py::KiemDuyetAnimationTest`
(Phase 4), `web/tests/admin.test.mjs`,
`web/tests/admin-control-center-v2.test.mjs`,
`web/tests/admin-account-management.test.mjs` (Phase 3),
`web/tests/admin-animation-moderation.test.mjs` (MỚI Phase 4),
`web/tests/ui.test.mjs` (Phase 4, +1 khẳng định fix ConfirmDialog).

## 10. Các phase còn lại (ĐÚNG THỨ TỰ)

- ~~**PHASE 3** — User Management đầy đủ~~ — **XONG**, xem mục 4b.
- ~~**PHASE 4** — Animation Moderation~~ — **XONG**, xem mục 4c.
- **PHASE 5** — Trusted Video Sources backend + UI: mô hình kênh/video/
  playlist YouTube tin cậy, ánh xạ series, bộ phân loại/phát hiện tập mới,
  hàng đợi nhập, nhập lại lịch sử (backfill).
- **PHASE 6** — YouTube WebSub + pipeline tập mới tự động: WebSub là kênh
  CHÍNH, có đối chiếu định kỳ tần suất thấp làm dự phòng, nhập tự động phải
  idempotent, tuỳ chọn tự động xuất bản. Test callback thật từ YouTube bị
  CHẶN cho tới khi có backend công khai qua HTTPS thật (xem mục 12).
- **PHASE 7** — Hoàn thiện các chỉ số analytics/product còn thiếu + hoàn
  thiện tích hợp tổng thể.

## 11. Cấu hình YouTube

- Biến môi trường: `YOUTUBE_API_KEY` — đã có DÒNG PLACEHOLDER (comment,
  KHÔNG có giá trị) trong `server/.env.example`. **KHÔNG được ghi giá trị
  thật của key này vào bất kỳ file tài liệu/handoff nào, kể cả file này.**
  Nếu key thật đã được cấu hình riêng trong `server/.env.selfhost` hoặc môi
  trường thật, đó là việc của người vận hành, không phải của agent — agent
  KHÔNG được đọc/in giá trị đó ra bất cứ đâu.
- YouTube Data API v3 cần được BẬT trên Google Cloud project tương ứng
  trước khi Phase 5/6 có thể gọi thật — xác nhận việc này đã làm hay chưa
  TRỰC TIẾP với người dùng ở đầu Phase 5, đừng giả định.

## 12. Quyết định kiến trúc WebSub

- **Bắt buộc dùng WebSub (PubSubHubbub) chính thức** cho đồng bộ tập mới —
  KHÔNG được hạ cấp xuống chỉ polling. Polling định kỳ tần suất THẤP chỉ
  đóng vai trò đối chiếu/dự phòng (reconciliation), không phải cơ chế chính.
- Test webhook cục bộ/giả lập (gửi payload WebSub giả tới endpoint callback
  nội bộ) ĐƯỢC PHÉP và nên làm trong Phase 6.
- Test đầu-cuối THẬT từ YouTube → callback thật của mình **bị chặn cho tới
  khi có một backend công khai qua HTTPS thật** (YouTube's hub yêu cầu một
  callback URL truy cập được từ internet để xác thực subscribe) — đừng cố
  giả lập việc này bằng cách nào khác, chỉ ghi nhận là blocker và tiếp tục
  phần còn lại của pipeline (parse/lưu/idempotency) bằng test giả lập.

## 13. Việc KHÔNG liên quan đang được stash — ĐỪNG ĐỘNG VÀO

```
stash@{0}: On feature/animation-player-v2-custom-controls: animation-player-v2 dim/glow/pulse WIP - not yet committed, awaiting user review
```

- Đây là công việc UX cho trình phát Animation (hiệu ứng mờ/phát sáng/nhấp
  nháy khi tạm dừng) từ một nhánh KHÁC (`feature/animation-player-v2-custom-controls`),
  đã được stash TRƯỚC KHI bắt đầu việc Admin/Trusted Video này, để giữ
  nguyên trạng chờ người dùng duyệt riêng.
- **KHÔNG liên quan gì tới Admin Control Center V2 / Trusted Video Sources.**
- **KHÔNG `git stash pop` / `git stash apply` / `git stash drop` cái này**
  trong lúc làm việc trên `feature/admin-trusted-video-v2`, dù vô tình hay
  cố ý — nó thuộc về một nhánh khác và một luồng công việc khác đang chờ
  người dùng xem lại.
- Nếu `git stash list` ở phiên mới cho thấy NHIỀU hơn 1 mục, hoặc mục
  `stash@{0}` không còn khớp mô tả trên, hãy DỪNG LẠI và hỏi người dùng
  trước khi làm bất cứ thao tác stash nào — đừng tự đoán.

## 14. Quy tắc an toàn Git (bắt buộc, xuyên suốt mọi phase còn lại)

- **Không sửa `main`.**
- **Không merge** `feature/admin-trusted-video-v2` vào `integration/pre-prod-v1`
  hay `main` cho tới khi có lệnh rõ ràng.
- **Không deploy production.**
- **Không đụng tới Appwrite Cloud production** — mọi thao tác/schema/dữ
  liệu thật chỉ chạy trên Appwrite tự lưu trú dev (mục 7).
- Dùng Appwrite tự lưu trú dev cho MỌI smoke test thật.
- **Không bao giờ commit file `.env*`** hay in giá trị secret/API key ra
  bất cứ đâu (log, doc, commit message, báo cáo cho người dùng).
- Mỗi checkpoint (mỗi phase xong) là MỘT commit riêng, push lên
  `feature/admin-trusted-video-v2`, KHÔNG amend commit cũ trừ khi được yêu
  cầu rõ.

## 15. HÀNH ĐỘNG TIẾP THEO CHÍNH XÁC — PHASE 5

Phase 3 (Full User Management) và Phase 4 (Animation Moderation) **ĐÃ
XONG** — xem mục 4b/4c để biết chi tiết đầy đủ, quyết định kiến trúc, và
kết quả smoke test/QA trình duyệt thật. ĐỪNG làm lại hai phase này.

**PHASE 5 — TRUSTED VIDEO SOURCES**: mô hình kênh/playlist YouTube "tin
cậy", ánh xạ sang series, phát hiện tập mới, hàng đợi nhập, nhập lại lịch
sử (backfill) — xem mục 1 (mục tiêu dự án, Phần B) và mục 11 (cấu hình
YouTube, CHƯA xác nhận `YOUTUBE_API_KEY`/YouTube Data API v3 đã bật hay
chưa — hỏi người dùng TRỰC TIẾP ở đầu phase này, đừng giả định). Trước khi
viết code:
- Đọc lại mục 11 VÀ hỏi người dùng xác nhận: (a) `YOUTUBE_API_KEY` đã có
  trong `server/.env.selfhost` thật chưa, (b) YouTube Data API v3 đã bật
  trên Google Cloud project tương ứng chưa. KHÔNG viết code gọi YouTube
  Data API thật trước khi có câu trả lời rõ ràng.
- Đây là PHẦN B của dự án (mô hình mới hoàn toàn: `trusted_sources`,
  `youtube_mappings` hoặc tên tương đương) — KHÁC Phase 4 (kiểm duyệt
  series/tập ĐÃ CÓ). Cần thiết kế schema Appwrite mới (thêm collection
  trong `scripts/setup_appwrite.py`, cùng mẫu additive/optional-field như
  Phase 4 đã làm cho `moderation_state`).
- Dashboard hiện có `trusted_sources: {"configured": false}` (Phase 2,
  `server/main.py::_admin_dashboard_them`) — Phase 5 là lúc thay `false`
  bằng dữ liệu thật, xem mục 6 (quyết định hiệu năng) để giữ đúng idiom
  bounded-count (`limit(1)` + đọc `total`, không quét toàn bảng).
  `web/src/app/admin/animation/sources`/`import-queue` hiện vẫn là
  placeholder `AdminSapXayDung` (Phase 2), chờ thay bằng trang thật ở đây.
- Tái sử dụng hạ tầng `ModerationEvent` với action `trusted_source_add`/
  `trusted_source_disable`/`trusted_source_enable`/`youtube_mapping_create`/
  `youtube_mapping_update` — ĐÃ CÓ SẴN trong enum Appwrite từ Phase 1
  (không cần migration enum mới, cùng mẫu Phase 3/4 đã tái dùng
  `user_suspend`/`content_unpublish` có sẵn).
- Giữ nguyên phân biệt vai trò đã thiết lập (mục 8) — quyết định mức
  (`admin_profile` hay `admin_or_owner_profile`) cho route Trusted Sources
  TRƯỚC khi viết route, dựa theo mức độ nhạy cảm (thêm/tắt một nguồn tin
  cậy có lẽ nên là `admin_or_owner_profile`, tương tự author-applications/
  users, vì đây là cấu hình ảnh hưởng rộng chứ không phải kiểm duyệt từng
  mục nội dung).

## 16. Ghi chú cho agent đọc file này

Sau khi hoàn thành BẤT KỲ phase nào, cách làm chuẩn (đã dùng ở Phase 1/2):
chạy đủ test/typecheck/lint/build/secret-scan → commit RIÊNG cho phase đó →
push lên `feature/admin-trusted-video-v2` → báo SHA cho người dùng → dừng
nếu người dùng yêu cầu dừng để soát xét. Cập nhật LẠI file handoff này (mục
2-5, 9, 10) sau mỗi phase quan trọng, không chỉ viết một lần rồi bỏ quên.
