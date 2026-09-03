# FINAL MEDIA DURABLE — DRIVE COLD + R2 HOT CHO RENDERED VIDEO (2026-09-02, Mission 10)

Vá lỗ hổng durability cho media cuối (rendered video sau QA_PASS): trước
đây không có đường lưu bền nào cho video đã render — giờ có bản nóng
trên R2, bản lạnh trên Drive, checksum/kích thước ghi vào bản ghi Novel,
idempotent thật (đã kiểm 3 lần chạy, không tạo trùng object nào).

## Hạng mục | Trước | Sau

| Hạng mục | Trước | Sau |
|---|---|---|
| Đường lưu bền rendered video | Không tồn tại — `compose_with_source()` không có caller nào, video render xong chỉ nằm cục bộ | **Có thật**: `archive_final_render()` — sha256, R2 nóng, Drive lạnh, PATCH vào Novel |
| `nov_41c9c967f40845a0` (Wikitongues, QA_PASS thật từ Mission 7) | `rendered_media_key=""`, `qa_state=""` — QA_PASS đã xác nhận nhưng chưa từng ghi lại | **Đã backfill thật**: đủ 4 trường + `qa_state=QA_PASS`, xác minh sống trên R2 và Drive |
| **Lỗi ẩn phát hiện thêm**: schema Appwrite thật thiếu 6 thuộc tính | `rendered_media_key`/`qa_state`/`processing_error` (từ Mission 9) + 3 trường mới đều **CHƯA TỪNG được tạo trên Appwrite production thật** — PATCH trả 200 nhưng ghi bị Appwrite âm thầm bỏ qua | **Đã sửa thật**: chạy `setup_appwrite.py --only novels` — tạo đúng 6 thuộc tính còn thiếu, xác minh lại bằng PATCH+GET thật |
| Idempotency | Chưa có cơ chế nào | **Đã kiểm thật, 3 lần chạy** `archive_final_render()` cùng 1 file → cùng 1 R2 key, cùng 1 Drive file id, cùng 1 sha256 mỗi lần — Drive/R2 cuối cùng chỉ có ĐÚNG 1 object |
| Test suite | — | 4269/4269 `server/tests` PASS, 88/88 test liên quan (bao gồm 12 test mới cho `archive_final_render`, 5 test slug-injection) |

## 1. Vấn đề thật và phát hiện gốc rễ

`compose_with_source()` (tạo rendered video) tồn tại, đã kiểm chứng, nhưng
**không có nơi gọi nào trong sản phẩm** — chỉ có MỘT script rời chạy tay
(Mission 7) từng gọi nó thật, cho đúng MỘT mục: `nov_41c9c967f40845a0`
(Wikitongues Henan Chinese, `rights_mode=REHOST_ALLOWED` — giấy phép CC
BY-SA thật sự cho phép rehost, khác hẳn các mục `EMBED_ONLY` không bao
giờ được render). File render `wikitongues_henan_rendered_FIXED.mkv`
(47.480.344 byte) vẫn còn trên scratchpad, và báo cáo Mission 7
(`dub-coverage-fix-2026-09-02.md:244`) đã xác nhận **QA_PASS thật** —
nhưng bản ghi Novel sống có `rendered_media_key=""` và `qa_state=""`,
xác minh trực tiếp qua API thật trước khi sửa gì.

## 2. Đường durability mới

`archive_final_render(local_render_path, novel_id, slug, token)` thêm vào
`scripts/chinese_media_pipeline.py` (không đụng `transcribe_mandarin()`,
`translate_zh_to_vi()`, `dub_segments()`, `compose_with_source()`,
`ship_draft()` — xác minh qua diff, chỉ có dòng thêm):

1. sha256 + kích thước (đọc theo khối 1MB, không load hết vào RAM).
2. R2 (nóng): key **content-addressed** —
   `rendered_media/svc_harvester/{slug}-{sha256[:16]}.mkv` — KHÔNG hậu
   tố ngẫu nhiên (khác `ship_draft()`'s subtitle/dub key) — chủ đích để
   idempotent.
3. Drive (lạnh): thư mục con riêng dưới
   `fanfic-gdrive:FanficWorld/archive/final/rendered` — root MỚI, tách
   biệt khỏi kho raw-source cũ (`archive/scraping/raw`) — dùng lại
   `rclone_archive_copy.py` (chỉ `copy`/`check`/`lsjson`/`size`, không
   bao giờ `sync`/`move`/`delete`/`purge`).
4. Lấy **Drive file id thật** từ `lsjson` (không phải chuỗi đường dẫn) —
   xác minh thật: mọi entry trên `fanfic-gdrive:` đều có trường `"ID"`.
5. PATCH `/api/novels/{id}/media-processing` — CHỈ 4 trường
   (`rendered_media_key`/`rendered_archive_file_id`/`rendered_checksum`/
   `rendered_size_bytes`), không bao giờ đụng `qa_state` (quyết định QA
   là của caller, set riêng).

Whitelist `NOVEL_MEDIA_PROCESSING_EDITABLE` mở rộng 6→9 trường, vẫn
KHÔNG giao với `NOVEL_EDITABLE`/`NovelPatch` (đã kiểm thật: `overlap:
set()`).

## 3. Review đối kháng độc lập

Workflow 4 pha (Implement → Review song song [Security + Idempotency] →
Fix → Verify), 5 agent, 538.059 token.

- **Security review**: phát hiện **1 lỗi thật** — tham số `slug` chưa
  được lọc ký tự trước khi ghép vào đường dẫn Drive (rclone coi đó là
  path component thật, khác R2 key chỉ là chuỗi) — rủi ro path
  traversal nếu `slug` đến từ nguồn không tin cậy. Đã sửa: regex
  allowlist `^[a-z0-9]+(?:-[a-z0-9]+)*$`, chặn TRƯỚC mọi I/O, thêm 5
  test (traversal, slash, khoảng trắng/hoa, chuỗi rỗng).
- **Idempotency review**: **0 lỗi** — key/đường dẫn xác nhận thuần hàm
  của (slug, sha256), test gọi hàm 2 lần thật, so `result1 == result2`.

## 4. Lỗi ẩn phát hiện thêm — schema Appwrite thật thiếu thuộc tính

Chạy backfill thật lần đầu: PATCH trả **HTTP 200** nhưng GET ngay sau đó
cho thấy MỌI trường mới đều rỗng — kể cả `qa_state` vừa set. Điều tra
trực tiếp: `scripts/setup_appwrite.py --only novels` (không dry-run, đã
xin phép người dùng trước khi chạm schema production thật) cho thấy
**6 thuộc tính CHƯA TỪNG tồn tại** trên Appwrite thật:
`rendered_media_key`, `qa_state`, `processing_error` (đã thêm code từ
Mission 9 nhưng CHƯA TỪNG áp dụng schema thật) + 3 trường mới của
mission này. Đã tạo thật (`tạo mới 6, bỏ qua 31`) — script tự thiết kế
an toàn để chạy lại (bỏ qua 409 = đã có). **Phạm vi lỗi hẹp**: các trường
`subtitle_key`/`dub_audio_key`/`subtitle_status` mà Mission 9 dùng để
hòa giải bản ghi trùng Chinese-media đã tồn tại từ trước — KHÔNG bị ảnh
hưởng.

## 5. Backfill thật + xác minh trực tiếp

Sau khi sửa schema, chạy lại `archive_final_render()` — 6/6 kiểm tra
PASS. Xác minh ĐỘC LẬP (không tin JSON trả về):

```
R2 (boto3 trực tiếp qua R2StorageAdapter.exists()/size()):
  exists=True, size=47.480.344 byte (khớp chính xác)

Drive (rclone lsjson, đọc thật):
  fanfic-gdrive:FanficWorld/archive/final/rendered/
    wikitongues-henan-chinese-3f837b6060701b4f/
      wikitongues_henan_rendered_FIXED.mkv
      Size=47.480.344, ID=1YFpJKxh2p8KwDefI51lImU6v1Ca34i50
  (khớp CHÍNH XÁC với rendered_archive_file_id trên Novel)
```

## 6. Idempotency — kiểm thật, không suy đoán

Chạy `archive_final_render()` **3 lần tổng cộng** (1 lần trước khi sửa
schema, 2 lần sau) trên cùng 1 file cục bộ:

```
Lần 1: r2_key=...3f837b6060701b4f.mkv, drive_id=1YFpJKxh2p8...
Lần 2: r2_key=...3f837b6060701b4f.mkv, drive_id=1YFpJKxh2p8... (giống hệt)
Lần 3: r2_key=...3f837b6060701b4f.mkv, drive_id=1YFpJKxh2p8... (giống hệt)
```

`rclone lsjson --recursive` sau lần 3: **đúng 1 file** trong thư mục
Drive. `R2StorageAdapter.size()` sau lần 3: **không đổi**. Không có
object trùng nào được tạo ở bất kỳ lần chạy nào.

## 7. Không đụng intermediates dùng-một-lần

Xác nhận qua đọc code + grep: `archive_final_render()` chỉ nhận MỘT
`local_render_path` đã hoàn thiện làm đầu vào — không có đường nào chạm
tới file tạm bên trong `dub_segments()` (`gap_*.wav`, `seg_*.mp3`,
`norm_*.wav`, `concat.txt` — tất cả nằm trong
`tempfile.TemporaryDirectory()`, xóa khi thoát context), không chạm ASR
working file nào. Đúng yêu cầu "không archive disposable intermediates".

## Xác minh test + build

```
server/tests (đầy đủ):        4269/4269 PASS (1 skip)
scripts/tests + server/tests
  (bộ liên quan trực tiếp):    88/88 PASS
  (bao gồm test_cover.py — bắt được 1 lỗi thật do diff này gây ra:
   whitelist "trường mới trên response API" chưa cập nhật 3 trường mới
   — đã tự sửa, không phải false-positive)
```

## Deploy

Đã xin phép người dùng TRƯỚC khi push/deploy (không tự suy diễn từ lần
trước). `git push origin main` (`1857c9b`→`a1fb72e`) → Render deploy
thật (`POST /services/{id}/deploys`) → poll tới `live`, đối chiếu SHA
trả về khớp chính xác `a1fb72e`.

---

**MOBILE HANDOFF MAX 7 LINES**
Status: Durability rendered-video đã vá thật, deploy live, backfill + idempotency đã xác minh trực tiếp, phát hiện thêm 1 lỗi schema Appwrite ẩn từ Mission 9 và đã sửa
Final-video durability: archive_final_render() mới — sha256 + R2 nóng + Drive lạnh + PATCH 4 trường, review bảo mật bắt 1 lỗi thật (slug chưa lọc) đã sửa
Drive: fanfic-gdrive:.../archive/final/rendered/wikitongues-henan-chinese-3f837b6060701b4f/ — xác minh thật qua rclone lsjson, ID=1YFpJKxh2p8KwDefI51lImU6v1Ca34i50
R2: rendered_media/svc_harvester/wikitongues-henan-chinese-3f837b6060701b4f.mkv — 47.480.344 byte, exists=True qua R2StorageAdapter trực tiếp
Backfill: nov_41c9c967f40845a0 (Wikitongues, QA_PASS thật từ Mission 7) — đủ 4 trường + qa_state=QA_PASS, xác minh sống trên production
Idempotency: 3 lần chạy thật, cùng key/id/sha256 mỗi lần, Drive+R2 cuối cùng đúng 1 object — không trùng lặp
SHA: a1fb72e (code, live production) — báo cáo commit riêng sau
