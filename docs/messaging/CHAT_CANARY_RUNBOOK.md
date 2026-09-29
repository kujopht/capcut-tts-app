# Chat V1 — runbook canary production (CHỦ DỰ ÁN chạy; agent không có khoá/đường vào production)

**Trạng thái lúc soạn (2026-09-29):** `main` = `0ff5d0f` (#229 `eb493b9`, #248 `61cfa18`, #250 `0ff5d0f`). API production đang chạy **`e293a01`** (đọc từ `/api/health`), Appwrite production **1.9.6** (qua Cloudflare). Production **chưa** có bảng chat nào; `FAS_CHAT_V1` và `NEXT_PUBLIC_CHAT_V1_ENABLED` đều TẮT.

Mọi bước dưới đây là **thay đổi production** trừ khi ghi "chỉ đọc". Không bỏ qua cổng.

## Cổng 0 — backup MỚI, khôi phục được (BẮT BUỘC trước mọi lệnh ghi schema)

Host Appwrite: AWS `54.179.200.223` (`i-064abacf35ebe2c8a`), MongoDB `8.2.5` (replica set), MariaDB `10.11`. Từ máy điều hành, cổng 22 và 443 của host **timeout** (đo lại 2026-09-29T04:12:01Z) — agent không tạo được bản backup. Bạn chạy trên chính host qua đường vào bạn có (SSM Session Manager / EC2 Instance Connect / console). Mật khẩu chỉ được tham chiếu bằng TÊN biến **bên trong** container (không lên dòng lệnh host, không vào history). Bản chứng minh gần nhất (`docs/reports/appwrite-backup-proven-2026-09-07.md`) đã 22 ngày — **không dùng thay được**.

```bash
# Xác nhận TÊN container / TÊN biến (không in giá trị):
sudo docker ps --format '{{.Names}}' | grep -E 'mongo|mariadb'
sudo docker exec appwrite-mongodb env | cut -d= -f1 | grep -i mongo
sudo docker exec appwrite sh -c 'echo "DB=$_APP_DB_SCHEMA"'          # ghi lại TÊN database ứng dụng

STAMP=$(date -u +%Y%m%dT%H%M%SZ); D=/root/backups/chat-pre-$STAMP; sudo mkdir -p "$D"; echo "$STAMP"
# 1) MongoDB — dump nhất quán theo thời điểm (--oplog)
sudo docker exec appwrite-mongodb sh -c 'mongodump -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin --oplog --archive --gzip' | sudo tee "$D/mongodb.archive.gz" >/dev/null
# 2) MariaDB (Appwrite vẫn giữ một phần dữ liệu ở đây)
sudo docker exec appwrite-mariadb sh -c 'mariadb-dump --all-databases --single-transaction -uroot -p"$MARIADB_ROOT_PASSWORD"' \
  | gzip | sudo tee "$D/mariadb-all.sql.gz" >/dev/null
# 3) Băm + kích thước
cd "$D" && sudo sha256sum ./* | sudo tee SHA256SUMS.txt && ls -la
```

**Kiểm toàn vẹn (khôi phục thử — container dùng một lần, KHÔNG nối vào mạng Appwrite):**

```bash
sudo docker run -d --name restore-test-mongo --ulimit nofile=64000:64000 \
  -e MONGO_INITDB_ROOT_USERNAME=rt -e MONGO_INITDB_ROOT_PASSWORD="$(openssl rand -hex 16)" mongo:8.2.5
sleep 15
sudo docker exec -i restore-test-mongo sh -c 'mongorestore -u rt -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin \
  --archive --gzip --oplogReplay' < "$D/mongodb.archive.gz"          # dòng cuối phải báo "0 failed"
# Đếm collection + document của DB ứng dụng ở NGUỒN và BẢN KHÔI PHỤC — hai con số phải KHỚP:
DEM='const d=db.getSiblingDB(DB); let n=0; const c=d.getCollectionNames(); c.forEach(x=>n+=d[x].countDocuments()); print(c.length, n)'
sudo docker exec appwrite-mongodb sh -c "mongosh --quiet -u \"\$MONGO_INITDB_ROOT_USERNAME\" -p \"\$MONGO_INITDB_ROOT_PASSWORD\" --authenticationDatabase admin --eval 'const DB=\"<DB>\"; $DEM'"
sudo docker exec restore-test-mongo sh -c "mongosh --quiet -u rt -p \"\$MONGO_INITDB_ROOT_PASSWORD\" --authenticationDatabase admin --eval 'const DB=\"<DB>\"; $DEM'"
sudo docker rm -f restore-test-mongo
```

Ghi vào biên bản: `STAMP`, tên database, `SHA256SUMS.txt`, hai con số đếm khớp nhau, dòng "0 failed". Nên chép thêm một bản ra ngoài host và so băm. **Thiếu bất kỳ mục nào → DỪNG, không tạo schema.**

## Bước 1 — deploy mã `main` với chat vẫn TẮT (production, cần duyệt)

Deploy này đẩy ra **18 commit** kể từ `e293a01`, không chỉ chat: #222 #224 #225 #226 #228 #230 #232 #233 #234 #235 #237 #236 #238 #249 #243 #229 #248 #250. `server/requirements.txt` thêm **Pillow** (bắt buộc lúc khởi động) và **websockets**. Workflow deploy cả API (Render) lẫn web (Cloudflare, **không** có cờ chat).

Trước khi deploy, ghi lại mục tiêu rollback của web: `npx wrangler deployments list --name fanfic-web` (ID version đang chạy).

```bash
gh workflow run production-deploy.yml --ref main -f confirm=DEPLOY_PRODUCTION -f ref=main \
  -f run_certification=true -f run_canary=false -f source_url=<URL mục lục chương công khai> -f chapter_limit=2
gh run watch
```

## Bước 2 — smoke hành vi cũ (chỉ đọc)

```bash
curl -s https://fas-prod-api.onrender.com/api/health
#   commit_sha = 0ff5d0f…; messaging.enabled = false; messaging.audience = "canary"; messaging.canary_users = 0
```

Duyệt nhanh bằng tay: trang chủ, thư viện, một truyện, một chương (đọc + nghe), đăng nhập, cộng đồng. Không có nút Tin nhắn.

## Bước 3 — xem kế hoạch schema (chỉ đọc)

```bash
FAS_ENV_FILE=<tệp env production của bạn> python -m scripts.setup_appwrite --plan \
  --only user_blocks,chat_conversations,chat_members,chat_messages,chat_fanouts
```

`--plan` chỉ phát GET (chặn mọi phương thức khác trước khi gửi), không in khoá. **DỪNG và báo lại** nếu: có bảng `chat_*` nào đã tồn tại; hoặc có dòng `⚠ KHÁC thiết kế`; hoặc database không tìm thấy.

Lưu ý `user_blocks`: đây là bảng MỚI của migration Social Play V1 (#229), mà migration đó chưa được ghi là đã áp lên production. Nếu `--plan` báo `user_blocks … SẼ TẠO` thì nó **phải** được tạo trước khi bật chat — khi `FAS_SOCIAL_V1_SCHEMA` tắt, chat đọc/ghi thẳng bảng này (thiếu bảng = mọi lần gửi tin lỗi). Tạo riêng `user_blocks` là additive, không đụng dữ liệu cũ, không bật Social V1.

## Bước 4 — áp schema (production, CHỈ khi Cổng 0 xanh và Bước 3 sạch)

```bash
FAS_ENV_FILE=<tệp env production> python -m scripts.setup_appwrite --only user_blocks      # "đã có" nếu đã tồn tại
FAS_ENV_FILE=<tệp env production> python -m scripts.setup_appwrite --only chat_conversations
FAS_ENV_FILE=<tệp env production> python -m scripts.setup_appwrite --only chat_members
FAS_ENV_FILE=<tệp env production> python -m scripts.setup_appwrite --only chat_messages
FAS_ENV_FILE=<tệp env production> python -m scripts.setup_appwrite --only chat_fanouts
```

Mỗi lệnh chỉ chạm đúng một collection (`--only`), chỉ TẠO (không sửa/xoá gì có sẵn), idempotent, chờ từng cột/index `available`, tự vượt lỗi bộ đệm index của 1.9.6. Kiểm lại ngay: chạy lại lệnh `--plan` của Bước 3 → mong đợi `5 bảng đã có · SẼ TẠO 0 … · 0 mục KHÁC thiết kế`.

## Bước 5–6 — bật máy chủ cho canary (production)

Env của API production (Render service `fas-prod-api`, nơi các biến `FAS_*` khác đang nằm), rồi deploy/khởi động lại:

```
FAS_CHAT_V1=1
FAS_CHAT_V1_AUDIENCE=canary
FAS_CHAT_V1_CANARY_USERS=<2–5 user ID Appwrite bạn duyệt, cách nhau dấu phẩy>
```

Chỉ user ID (bắt đầu bằng chữ/số, ≤ 36 ký tự) — email/đường dẫn bị bỏ. Không ghi ID vào mã nguồn. Kiểm: `/api/health` → `messaging.enabled = true`, `audience = "canary"`, `canary_users = N` (chỉ số lượng).

## Bước 7–8 — web có cờ (production; cần duyệt một thay đổi workflow)

`production-deploy.yml` hiện chỉ truyền `NEXT_PUBLIC_API_BASE`. Đề xuất (chưa làm) — trong bước "Cloudflare deploy (frontend)":

```yaml
        env:
          ...
          NEXT_PUBLIC_API_BASE: ${{ vars.PRODUCTION_API_BASE_URL }}
          NEXT_PUBLIC_CHAT_V1_ENABLED: ${{ vars.PRODUCTION_CHAT_V1_ENABLED }}
```

rồi `gh variable set PRODUCTION_CHAT_V1_ENABLED --body 1` và chạy lại lệnh deploy ở Bước 1. Cờ web chỉ bật **khung** giao diện: người ngoài canary chỉ gọi `/api/chat/availability` (1 lần/lần tải trang) và không thấy gì.

## Bước 9 — smoke canary (hai tài khoản canary A, B + một tài khoản thường C)

A thấy nút Tin nhắn · B thấy · C **không** thấy (và `/messages` báo "chưa mở") · A ↔ B nhắn tin, B nhận ngay · chưa đọc/đã đọc đúng · dock nổi (≥1024 px) · đổi trang giữ cửa sổ + nháp · tải lại phục hồi · thu nhỏ/khôi phục · nhãn dán · tắt tiếng · chặn/bỏ chặn · mất mạng → có mạng · hai tab · `/messages` trên điện thoại · đăng xuất/đăng nhập (cửa sổ người trước biến mất) · không tin trùng · C gọi thẳng `/api/chat/dm/<A>/messages` → 403.
Đo (DevTools): Enter → tin hiện (mục tiêu < 50 ms); B thấy tin (mục tiêu < 500 ms trung vị); `Server-Timing` `tong` của POST gửi (mục tiêu < 1,5 s; 1.9.6 cùng máy đo 152 ms).

## Rollback

| Mức | Thao tác | Hiệu lực | Dữ liệu |
|---|---|---|---|
| 1 | bỏ ID khỏi `FAS_CHAT_V1_CANARY_USERS`, khởi động lại API | người đó 403 ngay sau khởi động lại | giữ |
| 2 | `FAS_CHAT_V1=0`, khởi động lại API | mọi route chat 503 | giữ |
| 3 | `gh variable set PRODUCTION_CHAT_V1_ENABLED --body ""` + deploy lại, hoặc workflow `production-rollback.yml` (`confirm=ROLLBACK_PRODUCTION`) → Worker về version trước | không còn giao diện chat | giữ |
| 4 (phá huỷ, cuối cùng) | xoá 4 bảng `chat_*` trên Console | — | **mất tin nhắn**; KHÔNG BAO GIỜ xoá `user_blocks` |

**Đã diễn tập trên fanfic-staging (2026-09-29, mã = `main` `0ff5d0f`):** mức 1 — gỡ một ID → 403 `chat_not_enabled` ngay sau khởi động lại (~25 s), người còn trong danh sách vẫn dùng được, `canary_users` giảm, trả lại → tin cũ còn nguyên; mức 2 — `FAS_CHAT_V1=0` → conversations/session/stream/send đều 503 `chat_not_configured`, `messaging.enabled=false`, bật lại → lịch sử còn nguyên (**13/13**); mức 3 — web build không cờ: kể cả tài khoản canary cũng không thấy nút Tin nhắn/dock/nút Nhắn tin, `/messages` báo "chưa mở", **0** request `/api/chat/*` (**5/5**). Mức 4 không diễn tập (phá huỷ).

Mục tiêu rollback mã: API `e293a01` (commit đang chạy trước Bước 1). Render deploy hook không có động từ rollback: dùng Render Dashboard → Deploys → Rollback, hoặc revert trên `main` rồi deploy lại (xem `deploy/RUNBOOK-PRODUCTION-DEPLOY.md`). Web: ID version ghi ở Bước 1.
