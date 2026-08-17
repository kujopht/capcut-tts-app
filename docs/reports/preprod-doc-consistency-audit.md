# Audit nhất quán tài liệu — Overnight Hardening V1, Phase 16

Phạm vi: `CLAUDE.md` (gốc + `web/CLAUDE.md`), `README.md`, `README_GUI.md`,
`docs/HANDOFF.md`, và toàn bộ `docs/*.md` NGOẠI TRỪ `APPWRITE_V2.md`/
`APPWRITE_SCHEMA.md` (Phase 13 lo phần đó). Đối chiếu với code/cấu trúc thư mục
thật tại `chore/preprod-overnight-hardening-v1` (HEAD lúc audit: sau
`efdaaa2`/`4edf102`).

> **Lưu ý phát hiện muộn — có một phiên/fork KHÁC cũng tự chạy Phase 16 song
> song, độc lập với phiên này.** Trong lúc audit, phát hiện file
> `docs/reports/preprod-documentation-audit.md` (không phải file báo cáo này)
> đã xuất hiện với nội dung/kết luận tương tự, và phiên đó đã tự sửa trực tiếp
> `docs/ADMIN.md`, `docs/WEB_README.md`, `docs/APPWRITE_SCHEMA.md`, và
> `docs/handoffs/admin-trusted-video-v2-handoff.md`. Đã đối chiếu: các sửa đổi
> của phiên kia và của phiên này trên `docs/WEB_README.md` **không đụng độ**
> (Edit theo `old_string` khớp tuần tự, nội dung cuối cùng gộp đúng cả hai).
> Khác biệt đánh giá đáng chú ý: phiên kia xếp `docs/HANDOFF.md` là "khoảng
> trống điều hướng" (không sửa, vì tuyên bố "production chưa deploy" của nó
> không sai so với `CLAUDE.md`), còn phiên này xếp nó là BLOCKER vì khối lượng
> tính năng bị bỏ sót quá lớn (Admin V2, Trusted Video, Image Studio,
> Animation...) khiến file gần như vô dụng làm "nguồn biết mốc nào đã xong".
> Cả hai đánh giá đều đúng ở góc nhìn riêng — người soát xét nên đọc **cả hai**
> báo cáo Phase 16 trước khi quyết định có viết lại `docs/HANDOFF.md` hay
> không. Đã cập nhật checklist Phase 16 trong
> `docs/handoffs/preprod-overnight-hardening-v1.md` bằng kết quả của phiên
> này (viết trước); nếu phiên kia ghi đè sau, cần gộp cả hai khi đọc lại ở
> Phase 17.

## Tóm tắt

| Mức độ | Số lượng |
|---|---|
| Blocker (tài liệu chủ chốt sai lệch nghiêm trọng với thực tế) | 2 |
| Minor | 1 |
| Đã tự sửa tại chỗ | 1 (nhỏ, rõ ràng) |
| Sạch | Phần còn lại (chi tiết bên dưới) |

**Kết quả quan trọng nhất: KHÔNG tìm thấy vi phạm quy tắc bắt buộc nào trong
code.** `server/` không import PySide6/Qt (chỉ có comment tự xác nhận), và mọi
import `desktop_app.*` trong `server/` (ngoài `server/tests`) đúng khớp 4 module
được phép liệt kê trong `CLAUDE.md`: `desktop_app.models`,
`desktop_app.text_chunker`, `desktop_app.providers.*`,
`desktop_app.output_manager`. Không có gì rộng hơn.

## Phát hiện

### 1. [BLOCKER] `docs/HANDOFF.md` cực kỳ lỗi thời — vẫn được `CLAUDE.md` trỏ vào làm nguồn "mốc nào đã xong"

- File dài 1036 dòng, **lần sửa cuối cùng: `181ca68`, 2026-08-08** (`git log -1 --format=%ci -- docs/HANDOFF.md` → `2026-08-08 23:34:42`).
- Nội dung mô tả trạng thái: "PR #1 → `main` CHƯA MERGE", "Production CHƯA
  DEPLOY", kiến trúc "Cloudflare Workers Free → Render Free → Appwrite Cloud".
  Đây là snapshot của nhánh `feature/web-mvp` cách đây hơn một tuần vận hành.
- File này **không hề nhắc tới**: Appwrite tự lưu trữ trên GCE
  (`0b4a0f5`, `dbf1672`, `eb9c220`, `8f20fa6` — đã merge vào
  `integration/pre-prod-v1` qua `11b2068`), Admin Control Center V2 + Trusted
  Video Sources (`3372eeb`…`5fd5ef7`, 7 phase, đã merge), Image Studio V1,
  dịch thuật Cerebras/Groq, Animation, hạng tác giả (`AUTHOR_RANK.md`), hệ
  gamification/social — tất cả đều đã có mặt trong code hiện tại và có tài
  liệu riêng (`docs/ADMIN.md`, `docs/DEV_SELFHOST_APPWRITE.md`,
  `docs/AUTHOR_RANK.md`, `docs/reports/*`).
- Root `CLAUDE.md` dòng cuối vẫn ghi: *"Xem `docs/HANDOFF.md` để biết mốc nào
  đã xong và việc tiếp theo."* — trỏ người đọc mới vào một tài liệu sai lệch
  nghiêm trọng so với hiện trạng.
- **Không tự viết lại** theo đúng giới hạn nhiệm vụ (việc lớn, cần quyết định
  nội dung/khung mới). Khuyến nghị cho phase sau hoặc người vận hành: hoặc (a)
  viết một `docs/HANDOFF.md` mới tóm tắt trạng thái hiện tại và archive bản cũ
  sang `docs/handoffs/`, hoặc (b) đổi dòng trỏ trong `CLAUDE.md` sang tài liệu
  còn sống (vd `docs/handoffs/admin-trusted-video-v2-handoff.md` +
  `docs/ADMIN.md` + `docs/DEV_SELFHOST_APPWRITE.md`).

### 2. [BLOCKER] `docs/WEB_README.md` — mục "Giới hạn hiện tại" khẳng định sai về việc đã kiểm chứng Appwrite/R2 thật

- **Lần sửa cuối: `2026-08-07 21:49:03`** (`15cbf71`/gần đó) — trước cả handoff
  MVP web.
- Dòng 249–271 (mục "Giới hạn hiện tại — đọc kỹ") nói: *"Kiểm chứng
  Appwrite/R2 thật: ❌ Chưa"* và liệt kê `AppwriteIdentityAdapter`,
  `AppwriteMetadataStore`, `R2StorageAdapter`, `scripts/setup_appwrite.py` là
  "chưa từng chạy với credential thật".
- Điều này **sai với thực tế đã ghi nhận nhiều lần**: `docs/HANDOFF.md` mục
  "Live smoke test — ĐÃ CHẠY" mô tả chi tiết lần chạy thật trên Appwrite Cloud
  1.9.6 + R2 (bảy lỗi tìm & sửa), và Phase 6 của overnight hardening hiện tại
  vừa chạy smoke test thật lần nữa chống Appwrite tự lưu trữ
  (`appwrite-dev.fanfic.world`, 19/19 đạt cho auth/profile/gamification, thêm
  19/19 cho animation/trusted video, 14/14 cho websub).
- Ai đọc `WEB_README.md` như tài liệu trạng thái hiện hành sẽ hiểu nhầm rằng
  tích hợp Appwrite/R2 chưa từng được xác minh thật — sai lệch nghiêm trọng.
- Đây là việc lớn hơn phạm vi "sửa nhanh" (phải viết lại cả bảng trạng thái và
  đối chiếu với nhiều nguồn khác), nên **chỉ ghi nhận**, không tự viết lại.

### 3. [Đã tự sửa — nhỏ, rõ ràng] `docs/WEB_README.md` — tên trường lỗi thời `commercial_ready`

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `docs/WEB_README.md`, cuối mục "Giới hạn hiện tại" | "Giọng Piper cục bộ bị đánh dấu `commercial_ready: false`." | Ghi rõ trường đã đổi tên thành `public_enabled` từ 2026-08-08, khớp `server/tts_bridge.py` (`"public_enabled": True`); đồng thời bỏ câu "chưa có moderation" đã sai (Admin Control Center V2 đã có moderation: treo tác giả, kiểm duyệt Animation, comment/post, xử lý report) |

Xác minh: `server/tts_bridge.py` dòng 318/321 dùng `public_enabled`, không còn
`commercial_ready` ở bất kỳ đâu trong `server/*.py`.

### 4. [Minor] `docs/ADMIN.md` mục "3. API" liệt kê route cũ, thiếu route mới của V2

- `docs/ADMIN.md` được cập nhật gần nhất `2026-08-16` (SẠCH, phản ánh đúng mô
  hình ba mức OWNER/ADMIN/MODERATOR) nhưng mục "## 3. API" chỉ liệt kê 12 route
  admin đời đầu (`overview`, `author-applications*`, `authors*`, `users*`,
  `novels`, `events`).
- Thực tế `server/main.py` có thêm rất nhiều route `/api/admin/*` mới từ V2
  chưa được liệt vào mục này: `animation/series*`, `animation/sources*`,
  `animation/imports*`, `animation/reconciliation/run`, `image-studio/kill-switch`,
  `image-studio/spending`, `comments*`, `posts*`, `reports*`,
  `social/overview`, `translate/usage`, `users/{id}/suspend`,
  `users/{id}/unsuspend`, `users/{id}/sessions/*`.
- Không phải lỗi sai (không route nào trong danh sách là ảo — đã grep xác
  nhận toàn bộ 12 route đang liệt kê đều tồn tại thật), chỉ là **danh sách
  không đầy đủ** dưới một tiêu đề ngụ ý đầy đủ. Không tự sửa vì cần liệt kê lại
  hàng chục route — việc có chủ đích hơn là "sửa nhanh".

## Đã kiểm — SẠCH (không cần sửa)

- **`CLAUDE.md` (gốc)** — mọi lệnh đã thử chạy/xác minh path:
  - `python -m compileall -q app.py desktop_app tests` → chạy OK (exit 0).
  - Mọi path tồn tại thật: `app.py`, `desktop_app/`, `capcut_tts_api/`, `tests/`,
    `run_app.bat`, `build_app.bat`, `installer.iss`, `server/requirements.txt`
    (có `boto3>=1.34,<2.0`), `requirements-gui.txt`, `server/tts_bridge.py`,
    `desktop_app/providers/registry.py`.
  - npm scripts trong `web/package.json` khớp đúng những gì `CLAUDE.md` liệt kê:
    `dev`, `build`, `typecheck` (`tsc --noEmit`), `test` (`node --test`).
  - Kiến trúc provider (`capcut`/`edge`/`piper` qua `ProviderRegistry`,
    `PROVIDER_ORDER`, không tự đổi giọng khi lỗi) khớp chính xác
    `desktop_app/providers/registry.py` hiện tại.
  - `.\.venv\Scripts\python.exe -m unittest discover -s tests -t .` — cú pháp
    đúng, đã khởi chạy thử nhưng bộ test desktop (GUI qua `QT_QPA_PLATFORM=
    offscreen`) chạy lâu hơn khung thời gian audit cho phép; không phát hiện
    dấu hiệu path/lệnh sai, chỉ là bộ test lớn/chậm — không tính là phát hiện
    tài liệu sai.
- **Quy tắc "Backend web không được import GUI"** — grep toàn bộ
  `from desktop_app` / `import desktop_app` trong `server/` (trừ
  `server/tests`) chỉ trả về đúng 4 module được phép:
  `desktop_app.models`, `desktop_app.text_chunker`,
  `desktop_app.providers.*`, `desktop_app.output_manager`. Không có
  `PySide6`/`PyQt`/`Qt` nào bị import — chỉ có comment tự xác nhận trong
  `server/main.py` và `server/tts_bridge.py`.
- **18 biến `FAS_*`** được nhắc trong toàn bộ `docs/*.md` + `CLAUDE.md` đều
  tồn tại thật trong `server/config.py` — không có biến ảo/đã xoá nào.
- **Route API** nhắc trong `docs/ADMIN.md`, `docs/AUTHOR_RANK.md`,
  `docs/WEB_README.md`, `docs/DEV_SELFHOST_APPWRITE.md` (`/api/health`,
  `/api/ready`, `/api/creator/ranks`, 12 route admin cũ) đều tồn tại thật
  trong `server/main.py` — không route ảo nào.
- **`docs/DEV_SELFHOST_APPWRITE.md`** (sửa gần nhất 2026-08-16) — khớp hoàn
  toàn với quy trình `FAS_ENV_FILE=server/.env.selfhost`, script setup/smoke
  hiện có.
- **`web/CLAUDE.md`** chỉ chứa `@AGENTS.md`, trỏ tới file do `next dev` tự sinh
  — không cần audit nội dung, đúng thiết kế.
- **`README.md` (gốc)** — mô tả SDK `capcut_tts_api`, phạm vi tách biệt khỏi
  web/production, không có tuyên bố nào mâu thuẫn với hiện trạng.
- **`README_GUI.md`, `docs/UI_AUDIT.md`, `docs/NPLUS1_MEASUREMENT.md`,
  `docs/OVERNIGHT_REPORT.md`** — các báo cáo tự gắn nhãn commit/ngày cụ thể
  (vd "Chạy trên commit `57e1059`"), đúng bản chất báo cáo tại-một-thời-điểm,
  không phải tài liệu "sống" nên nội dung cũ không tính là sai lệch.
- **`docs/GCE-WORKER-CAPACITY.md`, `docs/AUTHOR_RANK.md`** — nội dung phân
  tích/thiết kế vẫn khớp code và biến môi trường hiện tại, không có route/biến
  ảo.

## Việc đã làm

- Sửa trực tiếp `docs/WEB_README.md` (mục nhỏ, rõ ràng — xem bảng ở phát hiện
  #3).
- Không sửa `docs/HANDOFF.md` hay bảng trạng thái lớn trong `docs/WEB_README.md`
  — vượt phạm vi "sửa nhanh", để lại làm khuyến nghị.
- Không đụng `docs/APPWRITE_V2.md`/`docs/APPWRITE_SCHEMA.md`/
  `scripts/setup_appwrite.py` (thuộc Phase 13).
