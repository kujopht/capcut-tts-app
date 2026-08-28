# Story Harvester V3 — cổng production: trạng thái chuẩn bị (2026-08-28)

Ghi lại **trước khi** deploy bất kỳ thứ gì. Không deploy, không scrape, không
chạy Content Factory trong phiên này.

## 1. GitHub Actions environment `production` — ĐÃ TẠO

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Environment `production` | không tồn tại | **đã tạo** (id `20761518915`) |
| Người phê duyệt bắt buộc | không có | **`kujopht`** — mọi job chạm environment này dừng chờ phê duyệt (bấm được từ GitHub mobile) |
| Nhánh được phép deploy | không giới hạn | **chỉ `main`** (deployment branch policy) |
| Variable phạm vi environment | 0 | `PRODUCTION_API_BASE_URL`, `CLOUDFLARE_ACCOUNT_ID` |
| Variable phạm vi repository | 0 | `PRODUCTION_API_BASE_URL`, `CLOUDFLARE_ACCOUNT_ID` |
| Secret phạm vi environment | 0 | **vẫn 0** — xem mục 3 |

`CLOUDFLARE_ACCOUNT_ID` lấy từ phiên OAuth wrangler đang có sẵn
(`npx wrangler whoami`), không phải từ credential nào mới. Nó là **định danh
tài khoản, không phải bí mật** — vô dụng nếu không có token, và workflow dùng
nó qua `vars.` chứ không phải `secrets.`.

**Vì sao đặt variable ở CẢ HAI phạm vi:** job `post_deploy_checks` đọc
`vars.PRODUCTION_API_BASE_URL` nhưng **không khai** `environment: production`
(xem mục 2), nên biến phạm vi environment không tới được nó. Đặt thêm ở phạm vi
repository là cách sửa không phát sinh thêm cổng phê duyệt; bản phạm vi
environment vẫn thắng ở những job có khai environment.

## 2. Lỗi thật tìm được khi rà workflow (chưa sửa mã)

`post_deploy_checks` dùng `vars.PRODUCTION_API_BASE_URL` mà không khai
`environment: production`. Nếu biến chỉ tồn tại ở phạm vi environment thì nó
phân giải thành **rỗng**, và chính guard trong job (`if [ -z "$API_BASE" ]`)
sẽ làm job **thất bại mọi lần chạy** — tức cổng health check sau deploy chưa
bao giờ chạy được. Đã vô hiệu hoá bằng variable phạm vi repository ở mục 1.

Nếu sau này muốn sửa tận gốc bằng cách thêm `environment: production` vào
`post_deploy_checks`, hãy biết đánh đổi: **mỗi** job khai environment có
required reviewer sẽ tạo một cổng phê duyệt riêng, nên một lần chạy đủ
(deploy + post_deploy_checks + phase18 + phase15) sẽ cần **4 lần bấm phê
duyệt** thay vì 3.

Điểm bất tiện nhỏ khác, không phải lỗi: `source_url` khai `required: true`
mà không có default, nên kể cả khi chỉ muốn chạy Phase 18 (`run_canary=false`)
vẫn phải điền một URL.

## 3. Ba secret CHƯA có — và vì sao không thể tự tạo

Đã tìm ở toàn bộ nguồn cấu hình được phép: repo tree, `server/.env*`,
`web/.env*`, `scratchpad/`, `~/.config`, biến môi trường của tiến trình, và
secret/variable phạm vi repository trên GitHub. **Không nơi nào có ba giá trị
này.** Máy này không có `server/.env` thật nào — chỉ `.env.example` và
`.env.selfhost` — đúng với quy tắc "không phục hồi `.env` cũ" sau lần cài lại
Windows 2026-08-22.

| Secret | Nguồn duy nhất | Vì sao tôi không tự làm được |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | dash.cloudflare.com → My Profile → API Tokens → **Create Token**, template *Edit Cloudflare Workers*, giới hạn đúng tài khoản `a0084ee7…` | Phiên wrangler tại máy là **OAuth**, và danh sách scope của nó (`npx wrangler whoami`) **không có** scope quản lý API token — không thể mint token qua API. Dùng chính token OAuth đó làm secret là **sai**: nó rộng hơn hẳn mức tối thiểu (`containers`/`cloudchamber`/`secrets_store` write, `connectivity` admin) và là access token ngắn hạn sẽ hết hạn. Yêu cầu "least privilege, không nới quyền" loại bỏ phương án này. |
| `RENDER_DEPLOY_HOOK_URL` | dashboard Render → service `fas-prod-api` → Settings → **Deploy Hook** → Copy | Không có `render` CLI trên máy, không có `RENDER_API_KEY`, và deploy hook URL không được API Render trả về. Không có đường nào không qua trình duyệt. |
| `FANFIC_ADMIN_CANARY_TOKEN` | Bearer token của **một tài khoản admin đã có**: đăng nhập rồi lấy session token | `scripts/story_harvester_direct_to_web_canary.py` gọi `/api/admin/scraper/*` với `Authorization: Bearer <token>`; server phân giải nó thành `Profile` qua `current_profile`. Mint nó cần **thông tin đăng nhập admin thật** — thứ tôi không có và không được tự tạo. |

Cả ba đều là hành động trên trình duyệt/điện thoại, **không phải việc phải làm
ở máy tính nhà**.

Lưu ý thiết kế cần cân nhắc sau: `FANFIC_ADMIN_CANARY_TOKEN` là **session
token**, không phải API key dài hạn. Lưu nó thành GitHub secret nghĩa là secret
sẽ **âm thầm hết hạn**, và workflow chỉ báo 401 chứ không nói rõ "token hết
hạn". Cân nhắc chuyển sang một cơ chế khoá dịch vụ có tuổi thọ tường minh.

## 4. Mốc chuẩn 13 truyện thật trên production (chỉ đọc)

Đo lúc chuẩn bị, `GET /api/novels?limit=100`: `count=13`, `total=13`,
`has_more=false`, **13/13 ở trạng thái `published`**.

| # | novel_id | Tiêu đề | Trạng thái | Tạo lúc |
|---|---|---|---|---|
| 1 | `nov_f9f2ce79889d42a3` | TỔNG HỢP Bóng Rổ Fanfic Kích Hoạt Hệ Thống Chó Điên, Phế Vật Lau Ghế Bỗng Hóa Thần Bóng Rổ | published | 2026-08-24 |
| 2 | `nov_6b42f7954f914227` | Conan Fanfic Luật Sư Ác Ma Đối Đầu Nữ Hoàng Phòng Xử Án Kisaki Eri, Ta Thu Những Phu Nhân Cực Phẩm | published | 2026-08-24 |
| 3 | `nov_7a9d668081014c44` | Conan Fanfic Ta Câu Hồn Thu Phục Mọi Linh Hồn Tu Tiên, Cứ Yên Ngươi Phá Án Đi Người Yêu Bạn Để Tôi | published | 2026-08-24 |
| 4 | `nov_7e62ca12f4434713` | Conan Fanfic Ta Sở Hữu Hệ Thống Bồi Dưỡng Để Thu Phục Mọi Mỹ Nhân, Lão Bà Của Ta Là Haibara Ai | published | 2026-08-24 |
| 5 | `nov_f9d6732756d54f52` | Fairy Tail Fanfic Xuyên Không Thành Minato Cầu Hôn Nữ Thần Mirajane, Nỗi Ám Ảnh Của Mọi Ác Quỷ | published | 2026-08-25 |
| 6 | `nov_aecfe32adfa74a72` | TỔNG HỢP Conan Fanfic Gin Và Conan Muốn Trầm Cảm Với Bộ Đôi Xuyên Không Siêu Bá Nhưng Siêu Lầy | published | 2026-08-25 |
| 7 | `nov_30ab18e27aa84f6f` | Naruto Fanfic Nghệ Thuật Dùng Hỏa Chí Thao Túng Quyền Lực, Âm Mưu Thôn Phệ Mọi Sức Mạnh Thành Thần | published | 2026-08-25 |
| 8 | `nov_57b68f0806b24c86` | Naruto Fanfic Tsunade Thua Cược, Bị Thầy Giáo Dụ Dỗ Chơi Đánh Bạc Rượu | published | 2026-08-25 |
| 9 | `nov_af3ae84262264b8c` | Naruto Fanfic Xuyên Thành Naruto Hắc Hóa Ăn Trái Ác Quỷ Mori Mori no Mi, Thống Trị Vạn Thế Giới | published | 2026-08-25 |
| 10 | `nov_4e6e47f7d34e4da6` | Naruto Fanfic Đến Làng Lá Làm Gián Điệp Ta Cưới Luôn Tsunade Và Kaguya, Thống Trị Thế Giới Ninja | published | 2026-08-25 |
| 11 | `nov_178a3ec4c30e43e5` | One Piece Fanfic Ta Có Hệ Thống Thu Phục Mỹ Nữ, Cướp Đoạt Năng Lực Thống Trị Thế Giới | published | 2026-08-25 |
| 12 | `nov_406c272f83b84929` | One Piece Fanfic Xây Dựng Đế Chế Ở Thế Giới Hải Tặc, Ta Dùng Công Nghệ Tương Lai Càn Quét Tất Cả | published | 2026-08-25 |
| 13 | `nov_478b5853894c4f69` | One Piece x Naruto Fanfic Ta Dịch Chuyển Cả Tộc Uchiha Đến Thế Giới Hải Tặc, Thống Trị Cả Thế Giới | published | 2026-08-25 |

Dùng bảng này để đối chiếu sau mỗi lần deploy/canary: `total` phải vẫn là 13 và
13 `novel_id` trên phải còn đủ. Phase 15 canary theo thiết kế là **dùng một lần
rồi bỏ** (tự dọn dữ liệu nó tạo), nên nó không được làm thay đổi bảng này.

## 5. Cổng còn lại

| Cổng | Trạng thái |
|---|---|
| Bộ test (backend 3263 / desktop 372 / web 834) | ✅ xanh tại `bad6832` |
| `production-deploy.yml` / `production-rollback.yml` hợp lệ | ✅ YAML hợp lệ, script tham chiếu đều tồn tại, không còn nội suy `${{ inputs.* }}` trong `run:` |
| Environment `production` + variable | ✅ xong |
| 3 secret | ❌ chờ người — mục 3 |
| Workflow có mặt trên `main` | ❌ **chưa** — `workflow_dispatch` chỉ chạy được khi file workflow đã ở nhánh mặc định. Nhánh `feat/safe-remote-fanfic-ops` (3 commit) **chưa push**: cổng phê duyệt `git push` đã từ chối trong phiên này. |
| Deploy production | ⏸ chặn bởi hai dòng trên |
| Phase 15 canary | ⏸ chặn bởi `FANFIC_ADMIN_CANARY_TOKEN` |
| Phase 18 certification | ⏸ chặn bởi Phase 15 (và cùng secret đó) |
