# Phase 7 — Audit độ tin cậy YouTube / Trusted Video Sources

Nhánh: `chore/preprod-overnight-hardening-v1`. Phạm vi: `server/trusted_source_service.py`,
`server/trusted_source_store.py`, `server/appwrite_trusted_source_store.py`,
`server/youtube_client.py`, `server/youtube_websub.py`, các route
`/api/admin/animation/sources*` / `mappings*` / `imports*` trong `server/main.py`,
test `server/tests/test_trusted_source_*.py`, frontend
`web/src/app/admin/animation/sources/*`, `web/src/app/admin/animation/import-queue/*`.

Phương pháp: đọc code tĩnh + test hiện có. KHÔNG gọi mạng thật tới YouTube (máy
này không có `YOUTUBE_API_KEY` — đã xác nhận, endpoint sẽ trả 503 đúng ý đồ).

## Tóm tắt

| # | Hạng mục | Kết luận |
|---|---|---|
| 1 | Retry/backoff + phân biệt lỗi tạm thời/vĩnh viễn | PHÁT HIỆN (minor) — không có retry/backoff nào; lỗi quota được phân biệt tốt, nhưng 5xx/timeout và 4xx khác đều gộp chung 502 |
| 2 | Race condition nhập trùng (double-import) | PHÁT HIỆN (minor, đáng ghi nhận) — hàng đợi phát hiện (`create_import_once`) idempotent thật sự; nhưng bước TẠO EPISODE trong `import_video` là check-then-act, không khoá xuyên suốt |
| 3 | Auto flags có bỏ qua ngưỡng `minimum_confidence` không | SẠCH — xác minh code đúng như tài liệu |
| 4 | Preview bắt buộc trước khi tạo nguồn | PHÁT HIỆN (minor) — chỉ ép ở frontend, backend không có gác cổng |
| 5 | Xoá nguồn có làm mồ côi dữ liệu không | SẠCH — có xử lý dọn dẹp/fallback hợp lý |

Không có phát hiện mức BLOCKER. Không sửa code (tất cả phát hiện đều cần
thiết kế lại cơ chế đồng thời/gác cổng, không phải "sửa an toàn nhỏ").

---

## 1. Retry/backoff khi gọi YouTube Data API

**File:** `server/youtube_client.py`, hàm `_goi()` (dòng 188-209).

Xác nhận bằng grep toàn bộ `server/youtube_client.py`, `trusted_source_service.py`,
`youtube_websub.py`: **không có `retry`/`backoff`/`time.sleep`/`tenacity`** ở đâu cả.
Mỗi lệnh gọi (`videos.list`, `channels.list`, `playlists.list`,
`playlistItems.list`) là **một** request `httpx.Client.get()`, không thử lại.

- Lỗi mạng (`httpx.HTTPError` — timeout, connection reset, DNS...) → luôn ném
  `YouTubeApiError("Không kết nối được YouTube Data API.")` ngay từ lần thử đầu
  tiên, không phân biệt "mạng chập chờn 1 lần" với "backend hỏng hẳn".
- Lỗi HTTP ≥ 400: **chỉ** `reason == "quotaExceeded"` được tách riêng
  (dòng 203-205, thông điệp "Đã hết hạn mức gọi YouTube Data API hôm nay."
  → route `main.py::_nguon_tin_cay` dòng 4394-4397 đổi thành HTTP 429 rõ ràng
  cho admin). **Mọi lỗi 4xx/5xx khác** (400 bad request, 403 forbidden không
  phải quota, 500/502/503 tạm thời của YouTube...) đều rơi vào cùng một nhánh
  chung: `f"YouTube Data API từ chối yêu cầu (HTTP {resp.status_code})."`,
  và ở tầng route đều biến thành **HTTP 502** giống hệt nhau (dòng 4394-4397).
  Không có phân biệt "lỗi tạm thời nên thử lại" vs "lỗi cấu hình/vĩnh viễn cần
  sửa" ngoài trường hợp quota.
- Riêng "video/kênh/playlist không tồn tại" (404 nghiệp vụ) KHÔNG đi qua nhánh
  lỗi HTTP này — YouTube Data API trả **200 với `items: []`** cho ID không tồn
  tại, và `get_video`/`get_channel`/`get_playlist` trả `None`, để tầng service
  (`_giai_quyet_preview`, `_lay_ung_vien`) tự ném `TrustedSourceError`/
  `YouTubeApiError` với thông điệp nghiệp vụ rõ ràng ("Không tìm thấy video
  này trên YouTube."). Điểm này ĐÃ phân biệt tốt — không phải phát hiện.

**Ảnh hưởng thực tế:** mọi lệnh gọi trong luồng này đều là hành động ADMIN chủ
động (preview, "Quét video có sẵn") hoặc job đối chiếu định kỳ
(`run_reconciliation`, mỗi nguồn được thử lại tự nhiên ở chu kỳ kế tiếp). Vì
vậy thiếu retry/backoff không gây mất dữ liệu, chỉ là admin phải bấm lại tay
khi gặp lỗi mạng thoáng qua — mức **minor**, không phải blocker.

## 2. Race condition khi 2 admin cùng "Nhập" một video

**File:** `server/trusted_source_service.py::import_video` (dòng 657-716);
`server/animation_store.py::create_episode` (dòng 190-193);
`server/appwrite_animation_store.py::create_episode` (dòng 447-452);
`server/animation_domain.py` dòng 191 (`episode_id: str = field(default_factory=lambda: new_id("anep"))`).

Hai lớp cần phân biệt:

- **Phát hiện video (`scan_source`/WebSub) — THỰC SỰ idempotent.**
  `create_import_once()` (`trusted_source_store.py` dòng 227-243,
  `appwrite_trusted_source_store.py` dòng 494-512) dùng `import_id` **tất
  định** = `video_import_id(youtube_video_id)`, và ở bản Appwrite dựa vào việc
  Appwrite từ chối `POST` trùng `documentId` (409) làm cơ chế "tạo-hoặc-lấy"
  an toàn dưới tải đua nhau — đúng như docstring mô tả, KHÔNG cần transaction
  riêng. SẠCH.

- **Bước "Nhập" thủ công (`import_video`, nút "Nhập"/"Nhập + Xuất bản") —
  CHECK-THEN-ACT, không có khoá xuyên suốt.** Trình tự trong `import_video`:
  1. `get_import(import_id)` — đọc `VideoImport` hiện tại.
  2. `episodes_by_external_ids([video_id])` — kiểm tra đã là tập chưa.
  3. `list_episodes(series_id)` — kiểm tra xung đột số tập.
  4. `create_episode(...)` — **tạo mới, `episode_id` sinh ngẫu nhiên
     (`new_id("anep")`) mỗi lần gọi, không có ràng buộc duy nhất theo
     `external_id` ở tầng lưu trữ** (cả `MockAnimationStore.create_episode`
     lẫn `AppwriteAnimationStore.create_episode` chỉ chèn thẳng, không kiểm
     tra trùng).
  5. `update_import(import_id, {"status": IMPORTED, "created_episode_id": ...})`.

  Nếu route `POST /api/admin/animation/imports/{id}/import` (định nghĩa tại
  `server/main.py` dòng 5127-5134, là `def` đồng bộ nên FastAPI/Starlette
  chạy trong threadpool — hai request đồng thời THỰC SỰ chạy song song ở
  tầng luồng) được gọi hai lần gần như đồng thời cho **cùng một** `import_id`
  (hai admin khác trình duyệt cùng bấm "Nhập"), cả hai request đều có thể đọc
  cùng trạng thái ở bước 1-3 TRƯỚC KHI bước 4 của bên kia hoàn tất → **cả hai
  đều tạo được một `AnimationEpisode`** cho cùng video, cùng series, cùng
  `order_index` — vi phạm đúng bất biến "không trùng số tập" mà bước kiểm tra
  xung đột (bước 3) định bảo vệ. Bản ghi `VideoImport` sau đó chỉ còn trỏ tới
  MỘT `episode_id` (do `update_import` cuối cùng ghi đè), episode còn lại trở
  thành **mồ côi** (tồn tại trong `animation_episodes` nhưng không ai tham
  chiếu, có thể đã publish nếu `publish=true`).

  Phòng vệ hiện có ở frontend (`web/src/app/admin/animation/import-queue/page.tsx`
  dòng 224, 258-274: nút bị `disabled` khi `dangXuLy === im.import_id`) **chỉ
  chặn double-click trong CÙNG một tab trình duyệt**, không chặn được hai
  phiên/hai admin khác nhau — đúng kịch bản nhiệm vụ nêu ra.

  Không tìm thấy test nào phủ kịch bản này (`test_trusted_source_service.py`
  có `test_nhap_thu_cong_thanh_cong` nhưng chỉ gọi tuần tự một lần).

**Mức độ:** minor, không phải blocker — cần hai tài khoản quản trị/kiểm duyệt
bấm cùng lúc trên cùng một hàng trong hàng đợi (kịch bản hiếm với đội ngũ quản
trị nhỏ), hậu quả là một episode trùng lặp có thể dọn tay, không mất dữ liệu
gốc, không lộ thông tin. Không sửa trong phiên này vì cách sửa an toàn (khoá
theo `import_id` xuyên suốt cả chuỗi đọc-kiểm tra-tạo, hoặc đổi `episode_id`
sinh tất định theo `external_id` để tận dụng cơ chế 409-idempotent như
`create_import_once`) đụng vào luồng tạo episode dùng chung với các đường
khác (tạo episode thủ công không qua trusted source) — cần thiết kế + test
riêng, không phải "sửa an toàn nhỏ" trong phạm vi phase này.

## 3. Auto Discover/Auto Import/Auto Publish có bỏ qua ngưỡng `minimum_confidence` không

**File:** `server/trusted_source_service.py::_quyet_dinh_trang_thai`
(dòng 557-611), dùng chung bởi CẢ quét thủ công (`scan_source` →
`_phan_loai_va_ghi_mot_video`) LẪN pipeline WebSub
(`_xu_ly_mot_video_websub` → cùng `_phan_loai_va_ghi_mot_video`) — một đường
quyết định duy nhất, không có nhánh tắt riêng cho WebSub.

Trình tự thực tế trong `_quyet_dinh_trang_thai`:
1. Loại trừ theo từ khoá → `IGNORED` (dòng 565-567), không liên quan cờ tự động.
2. Không khớp series nào → `NEW` (dòng 569-570).
3. **Tính ngưỡng** `nguong` = `mapping.minimum_confidence` nếu mapping có đặt
   riêng, nguược lại `source.minimum_confidence` (dòng 573-575).
4. **`if ket_qua.confidence < nguong: return PENDING`** (dòng 576-578) — kiểm
   tra này xảy ra **TRƯỚC** khi đọc bất kỳ cờ `auto_import`/`auto_publish`
   nào. Không có đường nào trong hàm đọc cờ tự động trước bước này.
5. Chỉ SAU khi vượt ngưỡng, hàm mới đọc `auto_import` (dòng 580-583) rồi
   `auto_publish` (dòng 595-596) để quyết định `PENDING`/`AUTO_IMPORTED`/
   `AUTO_PUBLISHED`.

Xác nhận: **đúng như tài liệu** — "video dưới ngưỡng luôn vào hàng đợi duyệt
tay bất kể cờ tự động" được thực thi đúng ở code, không có đường tắt. Test
`test_quet_du_tin_cay_nhung_khong_bat_auto_import_thi_pending` và
`test_quet_tu_dong_nhap_va_xuat_ban_khi_du_dieu_kien` xác nhận cả hai chiều.
SẠCH.

## 4. Preview bắt buộc trước khi tạo nguồn

**File:** `server/main.py` route `POST /api/admin/animation/sources`
(dòng 4974-4989, model `TrustedSourceCreateIn` dòng ~4890-4906);
`server/trusted_source_service.py::create_source` (dòng 180-215).

Frontend (`web/src/app/admin/animation/sources/new/page.tsx`) ép đúng luồng
hai bước: gọi `previewTrustedSourceUrl` trước, chỉ hiện form "Thêm làm nguồn
tin cậy" sau khi có `xem` (kết quả preview thật), docstring đầu file còn ghi
rõ "KHÔNG có đường tạo thẳng từ URL mà không qua xem trước".

**Nhưng ở backend, `create_source()` KHÔNG gọi lại YouTube Data API để xác
minh** `youtube_channel_id`/`youtube_playlist_id`/`youtube_video_id` là thật.
Nó chỉ: (a) validate `source_type` hợp lệ, (b) chặn `DIRECT_HLS`/`DIRECT_MP4`
chưa triển khai, (c) kiểm tra trùng lặp định danh với nguồn đã có
(`_dinh_danh_da_ton_tai`, dòng 217-228) — hoàn toàn không gọi `self._youtube()`.
Route `POST /api/admin/animation/sources` nhận thẳng `youtube_channel_id`,
`display_name`... từ payload JSON của client, không bắt buộc phải đi kèm một
token/kết quả preview đã ký. Một admin/owner đã đăng nhập (hoặc một request
thủ công/script bỏ qua UI) hoàn toàn có thể `POST` trực tiếp với
`youtube_channel_id="bia-dat"`, `display_name="bat-ky"` mà không bao giờ chạm
YouTube Data API.

**Mức độ:** minor — đây là gác cổng UX/nghiệp vụ (chống nhập nhầm kênh), không
phải kiểm soát bảo mật; người gọi đã phải qua `admin_or_owner_profile` (đã có
quyền quản trị hợp lệ). Hậu quả xấu nhất là tạo một "nguồn tin cậy" với ID sai
— lần "Quét video có sẵn" đầu tiên sẽ gọi YouTube Data API thật và thất bại rõ
ràng (`YouTubeApiError`/kênh không đọc được danh sách video), tự lộ ra ngay,
không âm thầm hỏng dữ liệu. Không sửa vì cần đổi chữ ký API (bắt buộc gửi lại
kết quả preview đã xác thực, hoặc để service tự gọi lại YouTube trước khi tạo)
— không phải một patch nhỏ an toàn trong phạm vi phase.

## 5. Xoá/vô hiệu hoá nguồn có làm mồ côi dữ liệu ngược không

**File:** `server/trusted_source_service.py::remove_source` (dòng 297-319),
`trusted_source_store.py::delete_source` (dòng 70-77),
`appwrite_trusted_source_store.py::delete_source` (dòng 359-363).

- Xoá nguồn: hủy đăng ký WebSub trước (cố gắng hết sức, không chặn xoá nếu
  hub từ chối — dòng 307-314), xoá **cascade** toàn bộ `SeriesMapping` thuộc
  nguồn đó (cả hai bản mock/Appwrite), rồi mới xoá `TrustedSource`. Không có
  mapping mồ côi.
- `VideoImport` (hàng đợi nhập) và `AnimationEpisode` (tập đã nhập) **KHÔNG**
  bị xoá theo — đây là chủ ý đúng: tập animation đã tạo là dữ liệu độc lập,
  không nên biến mất khi nguồn theo dõi bị gỡ. `VideoImport` còn lại vẫn
  tham chiếu `trusted_source_id` đã xoá, nhưng mọi nơi đọc lại tên nguồn đều
  bọc `try/except NotFoundError` và fallback về chuỗi rỗng
  (`admin_list_imports` dòng 624-628, `admin_source_detail` tương tự dòng
  266-273 cho series) — không crash, chỉ hiển thị tên nguồn trống cho các
  bản ghi lịch sử, chấp nhận được.
- `import_video`/`set_import_series`/`reject_import`/`ignore_import` đều
  KHÔNG gọi `self._store.get_source(...)` — không phụ thuộc nguồn còn tồn
  tại hay không, nên các thao tác trên một `VideoImport` mồ côi (nguồn gốc đã
  bị xoá) vẫn hoạt động bình thường, không bị chặn nhầm.

SẠCH — không phát hiện lỗi mồ côi dữ liệu ngược đáng kể.

---

## Kết luận

Không có phát hiện mức BLOCKER trong phạm vi Phase 7. Ba phát hiện mức
**minor** (mục 1, 2, 4) đều là khoảng trống thiết kế đã biết trước (thiếu
retry/backoff phân loại lỗi, thiếu khoá đồng thời cho thao tác nhập thủ công,
thiếu gác cổng backend cho bước preview) — không sửa trong phiên này vì mỗi
mục đều cần thiết kế lại một phần cơ chế (đồng thời, phân loại lỗi HTTP, hoặc
chữ ký API), vượt quá "sửa an toàn nhỏ". Đề xuất theo dõi riêng cho các phase
sau nếu tính năng Trusted Video Sources đi vào production ở quy mô nhiều
admin/nhiều nguồn.

---

## Bổ sung: Fuzz corpus bộ phân tích số tập + kiểm chứng trùng lặp/xung đột/video không khả dụng

(Phần này chạy độc lập, sau phần audit ở trên trong cùng Phase 7 — trọng tâm
khác: mục tiêu, hạng mục 1-5 ở trên là rà soát tĩnh thiết kế đồng thời/lỗi
mạng; phần dưới đây là **fuzz test tất định** cho bộ phân tích số tập/độ tin
cậy, cộng kiểm chứng lại (đọc code + test) hai luồng trùng lặp/xung đột và xử
lý video không còn truy cập được.)

### Tóm tắt

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `parse_episode_number("e12")` (chữ thường) | Trả `None` — SAI, mâu thuẫn với chính cam kết "không phân biệt hoa/thường" ghi ở docstring đầu `server/episode_parser.py` | Trả `12` — khớp `parse_episode_number("E12")` |
| `_BARE_E_RE` (regex "E12" trần) | Không có cờ `re.IGNORECASE` | Có `re.IGNORECASE` |
| Test fuzz cho `episode_parser`/`video_classifier` | Chỉ có test cơ bản (11+9 case) | Thêm 2 lớp `FuzzCorpusPhase7Test` (7 test mới ở `test_episode_parser.py`, 4 test mới ở `test_video_classifier.py`) phủ tiếng Việt có/không dấu, tiếng Anh, "Ep.", combo season+episode, Unicode NFC/NFD, năm phát hành/lượt xem cạnh số tập, toàn bộ `NEGATIVE_KEYWORDS` |
| Test cho "video không còn truy cập" khi quét nguồn kiểu `youtube_video` đơn lẻ | Không có test (hành vi đúng nhưng chưa có test khoá lại) | Thêm `test_quet_nguon_video_don_le_khong_con_truy_cap_bao_loi_ro_rang` |
| Test cho "một video trong playlist/kênh bị gỡ/riêng tư giữa lúc quét" | Không có test | Thêm `test_quet_kenh_bo_qua_video_rieng_tu_trong_playlist_khong_lam_sap_ca_lan_quet` |

### 1. Bug tìm thấy và đã sửa: "e12" (chữ thường) không đọc được số tập

**File:** `server/episode_parser.py`, hằng số `_BARE_E_RE` (dòng ~38).

Fuzz corpus dựng tay theo đúng yêu cầu Phase 7 (tiếng Việt có dấu/không dấu,
tiếng Anh, combo season+episode, Unicode, từ khoá loại trừ, số trong ngữ cảnh
không liên quan) phát hiện: `_KEYWORD_RE` (khớp "tập"/"tap"/"episode"/"ep"/...)
biên dịch với `(?i)` (không phân biệt hoa/thường) như docstring đầu file cam
kết ("Ho tro CA hai each viet tieng Viet... khong phan biet hoa/thuong"), NHƯNG
`_BARE_E_RE` (khớp dạng "E12" trần, dùng khi không có từ khoá đầy đủ) biên dịch
KHÔNG có cờ nào cả:

```python
# Trước khi sửa
_BARE_E_RE = re.compile(r"\bE(\d{1,4})\b")
```

Hệ quả: `parse_episode_number("E12")` → `12` (đúng), nhưng
`parse_episode_number("e12")` → `None` (sai) — cùng một chuỗi, chỉ khác hoa/
thường, ra hai kết quả khác nhau, vi phạm trực tiếp cam kết tất định + không
phân biệt hoa/thường của chính module. Trong thực tế, tiêu đề video tự nộp
thường viết thường toàn bộ (ví dụ kênh tự động hoá dùng template chữ thường),
nên đây không phải một trường hợp biên vô nghĩa.

**Đã sửa** (thêm `re.IGNORECASE`, không đổi ngữ nghĩa/độ đặc hiệu của regex,
không đổi thứ tự ưu tiên với `_KEYWORD_RE`):

```python
_BARE_E_RE = re.compile(r"\bE(\d{1,4})\b", re.IGNORECASE)
```

Xác nhận rủi ro khớp nhầm không tăng: `\b` (ranh giới từ) vẫn đòi hỏi ký tự
ngay trước "E"/"e" không phải ký tự chữ/số — các chuỗi dính liền kiểu
"type12"/"free12"/"anime12" vẫn KHÔNG khớp (không có ranh giới từ ở giữa),
chỉ các trường hợp "E"/"e" đứng như một token riêng (ví dụ "(e12)", "- E12",
"E12" đứng đầu chuỗi) mới khớp — đúng như trước, chỉ thêm biến thể hoa/thường.

Test khoá lại: `test_e_tran_khong_phan_biet_hoa_thuong` trong
`server/tests/test_episode_parser.py`.

### 2. Fuzz corpus — các hạng mục khác (không phát hiện bug)

Chạy `server/tests/test_episode_parser.py::FuzzCorpusPhase7Test` và
`server/tests/test_video_classifier.py::FuzzCorpusPhase7Test` (17+16 test,
toàn bộ PASS sau khi sửa mục 1):

- **Tiếng Việt có dấu/không dấu**: "Tập 1"/"TẬP 1"/"tập 1"/"Tap 1"/"TAP 1",
  "Chương 7"/"CHƯƠNG 7"/"chuong 7", "Phần 3"/"phan 3" — đều đọc đúng.
- **Tiếng Anh**: "Episode 12", "Ep. 12", "Ep.12", "Ep 12", "EP#12", "Ep #12"
  — đều đọc đúng qua `_KEYWORD_RE` (hỗ trợ dấu chấm/khoảng trắng/`#` tuỳ
  chọn giữa từ khoá và số).
- **Combo season+episode ("S01E12"/"S2E12" dính liền)**: KHÔNG đọc được
  (trả `None`) — đây là **hạn chế đã biết, KHÔNG PHẢI bug**: docstring đầu
  `episode_parser.py` chỉ công bố hỗ trợ
  "Tap/Tập/EP/Episode/E12/Chương/Chapter/Phần/Part", không có dạng dính liền
  kiểu fansub S01E12. Dạng có khoảng trắng ("Season 2 Episode 12") vẫn đọc
  đúng 12 vì "Episode 12" tự nó là một khớp từ khoá đầy đủ độc lập. **Không
  sửa** theo FIX POLICY (mở rộng dạng nhận diện là "redesign the parser",
  ngoài phạm vi "sửa bug" — cần thiết kế thêm ưu tiên/độ đặc hiệu cho pattern
  mới, không phải một dòng vá an toàn).
- **Unicode NFC/NFD**: tiêu đề gõ theo tổ hợp dấu tách rời (NFD) và ghép sẵn
  (NFC) đều ra cùng kết quả — `parse_episode_number` tự chuẩn hoá NFC trước
  khi khớp, `video_classifier.chuan_hoa` tự chuẩn hoá NFKD trước khi so
  alias, cả hai đường đều đã đúng.
- **Số trong ngữ cảnh không liên quan** (năm phát hành, lượt xem, độ phân
  giải): "Tiên Nghịch (2024)", "1080p 60fps", "10000000 views", "4K
  Remaster" — đều KHÔNG bị nhận nhầm thành số tập (đúng ý đồ: parser chỉ
  đọc số NGAY SAU một từ khoá tập, không đoán số trần). Khi có từ khoá thật
  cạnh năm phát hành ("Tập 12 (2024)"), vẫn đọc đúng 12 (số đầu tiên có từ
  khoá thắng).
- **Toàn bộ `NEGATIVE_KEYWORDS`** (13 từ: trailer/teaser/pv/preview/ost/op/
  ed/opening/ending/short/shorts/highlight/reaction/announcement/livestream)
  — fuzz từng từ một, mỗi từ đều hạ điểm và đánh dấu `excluded=True` đúng ý
  đồ khi xuất hiện như MỘT TỪ RIÊNG. Đồng thời xác nhận các từ này KHÔNG bị
  khớp nhầm khi là một phần của từ khác không liên quan ("PVP Championship",
  "Operation Rescue", "Edit nhanh") — nhờ ranh giới từ `\b` trong `_co_tu`.
- **Tiêu đề mơ hồ**: khớp alias nhưng không đọc được số tập (video tổng
  hợp/AMV) vẫn trả về đúng `series_id`, `episode_number=None` — quản trị tự
  gán số tập bằng tay, không phải lỗi.

### 3. Kiểm chứng trùng lặp (duplicate) và xung đột (conflict) — khớp ý đồ, không sửa

Đọc lại `server/trusted_source_service.py` + test hiện có
(`server/tests/test_trusted_source_service.py`):

- **Video đã là một `AnimationEpisode` thật** (nhập trùng cùng video hai
  lần, hoặc video đã có ở series khác) → `_phan_loai_va_ghi_mot_video` tra
  `episodes_by_external_ids` TRƯỚC khi phân loại, đánh dấu `DUPLICATE` ngay,
  không phân loại lại — test `test_quet_video_da_la_tap_thanh_duplicate`
  xác nhận. Nút "Nhập" thủ công (`import_video`) kiểm tra lại LẦN NỮA ngay
  trước khi tạo episode (không chỉ tin kết quả quét cũ) — đúng docstring
  "KHÔNG BAO GIO ghi de am tham".
- **Hai video khác nhau cùng nhận diện ra một số tập trong cùng series**
  (conflict) → `_quyet_dinh_trang_thai` tra `episodes_by_series` (danh sách
  `order_index` đã có), nếu số tập trùng với MỘT episode đã tồn tại (từ
  video KHÁC) thì trả `CONFLICT`, KHÔNG tự động ghi đè — test
  `test_quet_trung_so_tap_thanh_conflict` xác nhận. `import_video` thủ công
  cũng kiểm tra lại xung đột ngay trước khi tạo (biến `xung_dot`, dòng
  686-694), khớp nguyên tắc "không ghi đè âm thầm" nêu trong docstring hàm.
- **Idempotent khi quét lại cùng nguồn nhiều lần**: `create_import_once`
  (cả bản Mock lẫn Appwrite) dùng `import_id` tất định =
  `video_import_id(youtube_video_id)`, video đã có bản ghi thì KHÔNG phân
  loại lại (giữ nguyên quyết định quản trị cũ) — khớp ý đồ, đã xác nhận lại
  qua đọc code (không phát hiện thêm gì mới ngoài phát hiện #2 ở phần audit
  chính bên trên).

Không tìm thấy bug ở hai luồng này — hành vi khớp đúng ý đồ tài liệu hoá
trong docstring `ImportStatus.DUPLICATE`/`ImportStatus.CONFLICT`. Không sửa.

### 4. Kiểm chứng "video không khả dụng" (bị gỡ/riêng tư) — khớp ý đồ, đã thêm test khoá lại

Ba đường xử lý video không còn truy cập được qua YouTube Data API, đều đã
xác nhận qua đọc code + test (2 test MỚI thêm trong phiên này, xem mục Tóm
tắt):

1. **Nguồn kiểu `youtube_video` (một video đơn lẻ được tin cậy) mà chính
   video đó bị gỡ/riêng tư trước lúc quét lại**: `_lay_ung_vien` gọi
   `yt.get_video(...)`, nếu trả `None` thì ném `YouTubeApiError` với thông
   điệp rõ ràng ("Không còn truy cập được video này qua YouTube Data API —
   có thể đã bị gỡ hoặc chuyển riêng tư"), `scan_source` bắt lỗi này, ghi
   `last_error_at`/`last_error_message` rồi ném lại (không im lặng, không
   tạo `VideoImport` rác) — xác nhận bằng test MỚI
   `test_quet_nguon_video_don_le_khong_con_truy_cap_bao_loi_ro_rang`.
2. **Một video trong playlist/kênh (nhiều video) bị gỡ/riêng tư giữa lúc
   quét**: `_lay_ung_vien` gọi `get_videos()` theo lô, video nào không có
   trong kết quả trả về thì bị BỎ QUA êm (dòng "video rieng tu/da bi go —
   bo qua, khong bia du lieu"), KHÔNG làm hỏng cả lượt quét — các video còn
   lại vẫn được phát hiện/phân loại bình thường, nguồn vẫn được ghi
   `last_success_at` — xác nhận bằng test MỚI
   `test_quet_kenh_bo_qua_video_rieng_tu_trong_playlist_khong_lam_sap_ca_lan_quet`.
3. **Thông báo WebSub báo video đã bị xoá** (`<at:deleted-entry>`, Phase 6):
   `_danh_dau_video_khong_con_truy_cap` chỉ đổi các bản ghi CÒN chờ quyết
   định (`NEW`/`PENDING`/`CONFLICT`) thành `UNAVAILABLE`, KHÔNG đụng vào bản
   ghi đã là quyết định cuối cùng (`IMPORTED`/`REJECTED`/`IGNORED`/
   `DUPLICATE`) — đã có test từ trước
   (`test_video_bi_xoa_danh_dau_unavailable_neu_dang_cho_duyet` trong
   `test_trusted_source_websub.py`), xác nhận lại vẫn đúng, không sửa.

Cả ba đường đều degrade graceful, không crash, không lộ dữ liệu bịa —
KHÔNG có phát hiện mới ở hạng mục này.

### 5. YOUTUBE_API_KEY — trạng thái cấu hình

`server/.env` (mặc định của máy này) **KHÔNG** có `YOUTUBE_API_KEY` — khớp
xác nhận ở phần audit chính bên trên. Tuy nhiên `server/.env.selfhost` (dùng
để chạy `scripts/smoke_test_selfhost_trusted_sources.py`, đã có kết quả
19/19 rất gần đây theo `docs/handoffs/preprod-overnight-hardening-v1.md`
Phase 6) **CÓ** cấu hình biến này (chỉ xác nhận sự hiện diện, không in giá
trị). Theo phạm vi Phase 7: KHÔNG gọi lại YouTube Data API thật trong phần
bổ sung này (đã có smoke test thật rất gần đây bao phủ đúng luồng
quét/nhập/preview, không lặp lại) — toàn bộ xác minh ở đây là fuzz test
tất định + đọc code, không cần mạng.

### Test mới thêm

- `server/tests/test_episode_parser.py` — lớp `FuzzCorpusPhase7Test` (7 test).
- `server/tests/test_video_classifier.py` — lớp `FuzzCorpusPhase7Test` (4 test).
- `server/tests/test_trusted_source_service.py` — 2 test mới (video đơn lẻ
  không khả dụng; video trong playlist không khả dụng).

Chạy toàn bộ `server/tests` sau khi sửa: **2405/2405 pass (1 skip — thiếu
file `.onnx.json` test model cục bộ, không liên quan)**.
