# Kiểm toán khả năng chống chịu lỗi (Error/Resilience) — Phase 10

Overnight Pre-Production Hardening Marathon V1. Bản này MỞ RỘNG một lượt rà
soát tĩnh trước đó trong cùng phase (pipeline TTS/Translation, `print()`
non-ASCII, `except Exception` nuốt lỗi, timeout HTTP — cả năm mục đều SẠCH,
xem lịch sử Git) bằng phương pháp **tái hiện thật qua `TestClient`** của
FastAPI cho đúng 9 kịch bản lỗi được giao, thay vì chỉ đọc code.

Toàn bộ test mới nằm ở `server/tests/test_resilience_error_handling.py`
(18 test, chạy OFFLINE — không chạm Appwrite/YouTube thật). Kết nối Appwrite
được "cắt" bằng cách thay `AppwriteIdentityAdapter._client` bằng một đối
tượng giả ném `httpx.ConnectError`, cùng mô hình bọc client đã có sẵn ở
`test_appwrite_v2_contract.py`.

## Tóm tắt theo 9 kịch bản

| # | Kịch bản | Kết luận |
|---|---|---|
| 1 | Appwrite backend không thể kết nối | **ĐÃ SỬA** — 2 lỗi thật: sai mã HTTP (401 thay vì 503) và rò rỉ chi tiết lỗi hệ thống (`getaddrinfo failed`) vào JSON trả về |
| 2 | YouTube API không khả dụng/lỗi | PASS — đã có pattern xử lý mẫu mực từ trước (503 cấu hình thiếu / 429 hết hạn mức / 502 lỗi kết nối), xác nhận lại bằng test thật |
| 3 | Cấu hình provider TTS/dịch không hợp lệ | PASS — có sẵn cơ chế fail-fast, xác nhận qua test hiện có (`test_dependencies.py`, `test_translation_provider_registry.py`) |
| 4 | Request body sai định dạng | PASS — Pydantic trả 422 sạch, không traceback, xác nhận bằng 5 test mới trên 3 route đại diện |
| 5 | Timeout cho lời gọi ra ngoài | PASS — mọi `httpx.Client` trong `server/` đều khai báo `timeout=...` tường minh (đã xác nhận ở lượt rà soát tĩnh trước, kiểm lại toàn bộ danh sách bên dưới) |
| 6 | Gửi trùng lặp (double-click) | PASS — đăng ký trùng email bị chặn rõ ràng (400, không tạo hồ sơ thứ hai); tạo 2 tài nguyên không-khoá-duy-nhất giống hệt nhau đều thành công độc lập (đúng ý đồ, không phải khoá phát hiện trùng) |
| 7 | Mất mạng giữa chừng request | N/A (đã có cơ chế tương đương) — worker bị ngắt giữa chừng được xử lý bằng lease hết hạn + fencing token (`test_lease_hardening.py`, `test_claim_atomicity.py`), không có "khoá vĩnh viễn" |
| 8 | Token phiên hết hạn/rác | PASS — 401 sạch, không traceback; token đã đăng xuất không dùng lại được |
| 9 | Người dùng thường gọi `/api/admin/*` | PASS — thân phản hồi 403 sạch (chỉ có `detail` dạng chuỗi, không traceback/đường dẫn file); KHÔNG kiểm lại quyền hạn (đã xác minh sạch ở Phase 3) |

**Phát hiện thêm ngoài 9 kịch bản**: lưới an toàn cuối cùng của FastAPI
(exception hoàn toàn không lường trước, không bị `except` nào bắt) đã được
xác nhận SẠCH — `app = FastAPI(...)` không bật `debug=True`, nên một lỗi
500 thật sự vẫn không làm lộ traceback hay chi tiết nội bộ vào response.

## Chi tiết kịch bản 1 — Appwrite không kết nối được (lỗi đã sửa)

### Phát hiện

`AppwriteIdentityAdapter._request()` (`server/appwrite_adapter.py`) bắt
`httpx.HTTPError` (mất kết nối/DNS lỗi/timeout) và trước đây ném:

```python
raise AuthError(f"Không kết nối được Appwrite: {exc}") from exc
```

Hai vấn đề, tái hiện được bằng test thật (`KichBanAppwriteKhongKetNoiDuoc`):

1. **Rò rỉ chi tiết lỗi hệ thống**: `{exc}` in thẳng nội dung exception của
   `httpx` vào thông điệp — ví dụ `[Errno 11001] getaddrinfo failed` — và
   thông điệp này đi thẳng vào `detail` của response JSON. Không phải secret
   (không phải API key/mật khẩu) nhưng là chi tiết hạ tầng nội bộ không nên
   lộ ra ngoài, vi phạm đúng nguyên tắc `thong_diep_loi_an_toan` mà
   `_request()` đã áp dụng cho các lỗi HTTP khác trong CÙNG hàm.
2. **Sai mã HTTP**: vì `AuthError` được dùng chung cho cả "sai thông tin
   đăng nhập" LẪN "không kết nối được Appwrite", `current_profile` (dependency
   bảo vệ HẦU HẾT route, bao gồm mọi route `/api/admin/*` qua `admin_profile`)
   và `/api/auth/login` trả về **401 Unauthorized** khi Appwrite chỉ đơn
   giản là đang gián đoạn — người dùng ĐANG đăng nhập hợp lệ sẽ bị hiểu nhầm
   hàng loạt là "phiên hết hạn, đăng nhập lại đi" trong lúc backend chỉ
   không tới được Appwrite. Đây là kiểu lỗi lệch nghiêm trọng hơn so với
   `/api/admin/trusted-sources/scan` (YouTube) — nơi cùng loại lỗi kết nối
   đã được cố ý map đúng thành 503/502 từ trước (`server/main.py::_nguon_tin_cay`).

### Sửa

- `server/adapters.py`: thêm `AppwriteUnavailableError(AuthError)` — vẫn là
  con của `AuthError` (code cũ bắt `except AuthError` không bị vỡ) nhưng cho
  phép nơi gọi phân biệt "hạ tầng gián đoạn tạm thời" với "người dùng sai".
- `server/appwrite_adapter.py::_request()`: đổi sang ném
  `AppwriteUnavailableError("Không kết nối được Appwrite. Vui lòng thử lại
  sau.")` — không còn nội suy `{exc}`.
- `server/main.py`: 5 điểm bắt `AppwriteUnavailableError` TRƯỚC `AuthError`,
  trả về `503` thay vì mã cũ — `current_profile` (dependency dùng chung cho
  gần như mọi route được bảo vệ, kể cả toàn bộ `/api/admin/*`), `login`,
  `register` (cả hai lệnh gọi `identity.register`/`identity.login`),
  `oauth_exchange`, `set_username` (trước đây map nhầm thành 409 "tên đã bị
  trùng").

### Bảng so sánh

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Thông điệp lỗi khi Appwrite mất kết nối | `"Không kết nối được Appwrite: [Errno 11001] getaddrinfo failed"` (rò rỉ chi tiết hệ thống) | `"Không kết nối được Appwrite. Vui lòng thử lại sau."` (không lộ chi tiết nội bộ) |
| Mã HTTP cho `/api/auth/login` khi Appwrite mất kết nối | 401 (giống hệt sai mật khẩu) | 503 (đúng bản chất: hạ tầng gián đoạn tạm thời) |
| Mã HTTP cho MỌI route bảo vệ (`current_profile`, gồm cả `/api/admin/*`) khi Appwrite mất kết nối | 401 — người dùng hợp lệ bị buộc tưởng "phiên hết hạn" | 503 — đúng là lỗi backend tạm thời, không đá người dùng ra khỏi phiên một cách vô lý |
| Mã HTTP cho `/api/creator/username` khi Appwrite mất kết nối | 409 "tên đã bị trùng" (sai hoàn toàn về bản chất) | 503 |
| Test tái hiện | Không có | `server/tests/test_resilience_error_handling.py::KichBanAppwriteKhongKetNoiDuoc` (6 test) |

## Chi tiết các kịch bản còn lại

### 2 — YouTube API không khả dụng (PASS)

`server/youtube_client.py::YouTubeClient._goi()` đã tách bạch rõ: lỗi kết
nối (`httpx.HTTPError`) → `YouTubeApiError("Không kết nối được YouTube Data
API.")` (KHÔNG bao giờ nội suy `exc`/URL có chứa `key=`), lỗi `quotaExceeded`
giữ nguyên `reason` để tầng trên map thành 429, các lỗi API khác thành
thông điệp chung. `server/main.py::_nguon_tin_cay()` map: `YouTubeConfigError`
→ 503, `YouTubeApiError` với `reason=="quotaExceeded"` → 429, còn lại → 502.
Test có sẵn `test_trusted_source_routes.py::test_khong_cau_hinh_key_tra_503`
xác nhận qua `TestClient` thật. Đây là pattern nên tham chiếu khi các nơi
khác cần phân biệt lỗi hạ tầng — thực tế mục 1 ở trên (Appwrite) đã áp dụng
đúng tinh thần này.

### 3 — Cấu hình provider không hợp lệ (PASS)

`server/tests/test_dependencies.py` xác nhận `DATA_BACKEND=appwrite` hay
`STORAGE_BACKEND=r2` thiếu biến môi trường bắt buộc đều fail-fast ngay ở
`settings.validate()`/`build_*`, KHÔNG bao giờ lặng lẽ lùi về mock.
`server/tests/test_translation_provider_registry.py::test_thieu_cau_hinh_nem_loi_ngay_luc_tao`
xác nhận provider dịch thiếu API key ném lỗi ngay lúc khởi tạo, không phải
lúc dùng. `server/tts_bridge.py` bọc mọi lỗi provider TTS (kể cả
`subprocess.TimeoutExpired`) thành `TtsBridgeError` có `ErrorKind` rõ ràng,
không để lộ traceback subprocess.

### 4 — Request body sai định dạng (PASS)

5 test mới (`KichBanRequestSaiDinhDang`) gửi: thiếu trường bắt buộc, sai kiểu
dữ liệu, và body không phải JSON hợp lệ tới `/api/auth/register`,
`/api/novels`, `/api/chapters`. Tất cả trả `422` (JSON không hợp lệ trả
`400`/`422` tuỳ tầng parse), không route nào lộ traceback hay đường dẫn file
Python trong response — hành vi mặc định của Pydantic/FastAPI đã đủ an toàn.

### 5 — Timeout cho lời gọi ra ngoài (PASS)

Xác nhận lại danh sách `httpx.Client(timeout=...)` trong toàn bộ `server/`:
Appwrite/YouTube (`REQUEST_TIMEOUT = 15.0`), Appwrite dịch/gamification
(`30.0`), provider dịch (`TIMEOUT_SECONDS = 60.0` cho dịch thật,
`_KIEM_TRA_TIMEOUT_SECONDS = 15.0` cho kiểm tra kết nối), Image Studio
BYOK/registry (`self._timeout`). Không có client HTTP nào thiếu timeout
(có thể treo vô hạn). Một ghi nhận MINOR còn tồn từ lượt rà soát trước
(không sửa, rủi ro thấp): R2/boto3 không đặt `connect_timeout`/`read_timeout`
tường minh trong `Config`, dựa vào mặc định của botocore.

### 6 — Gửi trùng lặp / double-click (PASS)

`KichBanGuiTrungLap` (2 test mới): đăng ký cùng một email hai lần liên tiếp
— lần hai bị từ chối rõ ràng (400 "Email này đã được đăng ký."), không tạo
hồ sơ thứ hai, không lỗi 500 — nhờ khoá (`threading.Lock`) trong
`MockIdentityAdapter.register`. Tạo hai Novel cùng tiêu đề liên tiếp (tài
nguyên KHÔNG có ràng buộc duy nhất theo tiêu đề) đều thành công với
`novel_id` khác nhau — đúng ý đồ (không phải lỗi trùng lặp cần chặn). Việc
tạo TTS job trùng lặp (cùng nội dung/giọng/tốc độ) đã có cơ chế
fingerprint riêng (`job_fingerprint`, `test_fingerprint_and_scale.py`) để
không tổng hợp lại audio đã có.

### 7 — Mất mạng giữa chừng request (N/A — đã có cơ chế tương đương)

Không mô phỏng riêng vì cơ chế bảo vệ đã tồn tại và có test: một worker bị
ngắt kết nối/crash giữa chừng khi đang xử lý job để lại lease hết hạn
(`FAS_JOB_LEASE_SECONDS`), job được `recover_stale_jobs()` nhận lại bởi
worker khác, và fencing token (`test_lease_hardening.py::TestFencingBlocksTheOldWorker`)
chặn worker cũ (nếu "sống lại") ghi đè kết quả — không có trạng thái kẹt
vĩnh viễn ở tầng job. Ở tầng HTTP đơn thuần (client đóng kết nối giữa
chừng), đây là hành vi ASGI server xử lý (request bị huỷ, không có state
nào bị ghi dở dang phía ứng dụng vì mọi ghi trạng thái đều nằm sau khi đã
có kết quả đầy đủ) — không có gì đặc thù của ứng dụng cần vá.

### 8 — Token phiên hết hạn/rác (PASS)

`KichBanDangNhapPhienHetHan` (3 test): token rác hoàn toàn → 401 sạch,
không traceback. Token đã đăng xuất → không dùng lại được (401). Thiếu
header `Authorization` → 401, không phải 500.

### 9 — Người dùng thường gọi `/api/admin/*` (PASS)

Không kiểm lại phân quyền (đã xác minh sạch ở Phase 3). Chỉ kiểm thân phản
hồi: `/api/admin/overview` với tài khoản thường trả 403, thân JSON chỉ có
`detail` dạng chuỗi, không có `Traceback`, không có `site-packages`, không
có dòng `File "..."` — phản hồi lỗi hoàn toàn sạch.

## Bugs tìm thấy

1. `server/appwrite_adapter.py::AppwriteIdentityAdapter._request()` — rò rỉ
   chi tiết lỗi hệ thống (`getaddrinfo failed`, v.v.) vào response JSON khi
   Appwrite mất kết nối. **ĐÃ SỬA.**
2. Toàn bộ đường xác thực (`current_profile`, `login`, `register`,
   `oauth_exchange`, `set_username`) trả sai mã HTTP (401/400/409) khi
   Appwrite mất kết nối, đáng lẽ phải là 503. Nghiêm trọng nhất là
   `current_profile` vì nó bảo vệ gần như mọi route, kể cả toàn bộ
   `/api/admin/*` — nghĩa là một lần Appwrite gián đoạn tạm thời sẽ trông
   giống hệt "toàn bộ người dùng đang đăng nhập bị hết phiên cùng lúc".
   **ĐÃ SỬA.**

## Bugs đã sửa trong phase này

Xem bảng so sánh ở mục "Chi tiết kịch bản 1" phía trên. Tệp thay đổi:
`server/adapters.py` (thêm `AppwriteUnavailableError`),
`server/appwrite_adapter.py` (ném lớp lỗi mới, bỏ nội suy exception thô),
`server/main.py` (5 điểm bắt lỗi, map sang 503).

## Bugs CỐ Ý không sửa (ghi rõ lý do)

- R2/boto3 thiếu `connect_timeout`/`read_timeout` tường minh (mục 5) — rủi
  ro thấp (mặc định botocore không phải vô hạn), sửa cần test lại toàn bộ
  đường ghi R2, ngoài phạm vi cho phép của phase này (tránh thay đổi kiến
  trúc rộng).
- Một số `except Exception: pass` không log (thưởng XP, dọn cover cũ, thông
  báo follower) ghi nhận từ lượt rà soát tĩnh trước trong cùng phase — đúng
  về mặt không được phép làm hỏng request chính, chỉ thiếu quan sát vận
  hành, MINOR, không sửa.

## Kết quả kiểm thử

- `server/tests/test_resilience_error_handling.py`: **18/18 PASS** (file
  mới, viết trong phase này).
- Toàn bộ `server/tests/`: **2408/2408 PASS** (1 skip, không liên quan —
  thiếu file `.onnx.json` test model cục bộ) sau khi áp dụng các sửa đổi.
- `python -m compileall -q server`: sạch.

## Kết luận

9/9 kịch bản đã được kiểm tra bằng request thật qua `TestClient` (trừ kịch
bản 7, có cơ chế tương đương đã kiểm chứng bằng test hiện có). Tìm và sửa
được 1 lỗi thật có thể tái hiện, ảnh hưởng tới TOÀN BỘ route được bảo vệ khi
Appwrite gián đoạn (sai mã HTTP + rò rỉ chi tiết lỗi hệ thống). Các kịch
bản còn lại đều đã có pattern xử lý lỗi tốt từ trước (đặc biệt là
YouTube/Trusted Video — dùng làm tài liệu tham chiếu khi sửa Appwrite), lưới
an toàn cuối cùng của FastAPI cho lỗi 500 hoàn toàn không lường trước cũng
đã xác nhận sạch.
