# Provider ngoài + Kho bí mật — Router Control Center V0.6.1

Nhánh `feat/v061-memory-provider-vault` · 2026-09-10 · Mã: `scripts/control_center/providers/`
· Bài kiểm: `scripts/tests/test_provider_credentials_v061.py` (28), `test_provider_webapi_v061.py` (3).

Mục tiêu của Part D không phải "gọi được Alibaba/Tencent" — đó là bước sau, khi
người vận hành có khoá. Mục tiêu là **nền móng để một khoá API trả tiền đi vào
hệ thống mà không bao giờ xuất hiện ở bất kỳ chỗ nào ngoài kho an toàn**: không
SQLite, không ký ức, không log, không payload việc, không prompt agent, không
Context Pack, không phản hồi API, không `repr()`.

## 1. Năm mảnh

```
kho_bi_mat.py   KhoBiMat ─┬─ KhoBiMatWindows   (Credential Manager, bền)   ← mo_kho_bi_mat()
                          ├─ KhoBiMatTrong     (không sẵn → luu() NÉM)     ← mo_kho_bi_mat() khi không có kho
                          └─ KhoBiMatBoNho     (CHỈ kiểm thử, không bao giờ được mo_kho_bi_mat() chọn)
                BiMat     tay cầm MỜ: .ref · .dung(fn) · repr = "<BiMat ref=…>" · không pickle/json
so.py           SoProvider   providers.db: providers / tai_khoan / models — CHỈ credential_ref
preset.py       Preset       openai_compatible · alibaba_dashscope · tencent_hunyuan (da_do=False)
adapter.py      AdapterOpenAICompat  thu_ket_noi (GET /models, rơi về chat max_tokens=1) · hoi (thủ công)
be.py           BeTaiKhoan   bể tài khoản chung: ít tải nhất, cooldown 3→60/300/900/1800 s, failover
dich_vu.py      DichVuProvider  mặt tiền cho webapi/engine; dang_ky_vao_fabric(dispatchable=False)
```

## 2. Đường đi của một khoá — và mọi chỗ nó KHÔNG đi

| Bước | Ai thấy giá trị | Ai chỉ thấy `credential_ref` |
|---|---|---|
| Người dán khoá vào ô `type=password` của hộp thoại **Providers** | trình duyệt WebView2 cục bộ, xoá khỏi DOM ngay khi gửi | — |
| `POST /api/providers/{id}/accounts` (127.0.0.1, token phiên, một lần) | handler webapi (`gia_tri = payload.pop(...)`, `del` trong `finally`) | — |
| `DichVuProvider.them_tai_khoan` | `kiem_gia_tri` → `KhoBiMat.luu(ref, v)` → `del v` | `TaiKhoan(credential_ref=ref)` → `providers.db`; sự kiện `PROVIDER_ACCOUNT_ADDED` (alias + ref) → `control.db` → ký ức |
| Thử kết nối / hỏi thử | closure `bi_mat.dung(_chay)` của adapter: dựng `Authorization` cho ĐÚNG MỘT request | `KetQuaThu`/`KetQuaHoi` đã qua `_lam_sach()` (thay đúng giá trị nếu nhà cung cấp dội lại, rồi `bi_mat.loc`) |
| Fabric / bộ lập lịch | — | runtime `EXT_<provider>_<alias>` với `auth_profile = credential-ref:<ref>` (nhãn) |
| Ký ức dự án | — | sự kiện đã lọc hai lần (`DichVuProvider._su_kien` → `bi_mat.loc`; cổng vào L0 → `bi_mat.loc`), `PROVIDER_TEST_FAILED` thành INCIDENT có bằng chứng |

Ba rào **bằng mã**, không bằng lời dặn:

1. **`SoProvider._khong_bi_mat()`** — mọi chuỗi ghi vào `providers.db` bị soi bằng
   bộ lọc ký ức + hình dạng khoá (`sk-…`, `AKID…`, `AKIA…`, `AIza…`, `Bearer …`,
   JWT). Khớp → `LoiBiMatLotVao`, không ghi. Bài kiểm đọc **bytes** của
   `providers.db` + WAL sau `wal_checkpoint`.
2. **`BiMat`** — không thuộc tính giá trị, `__reduce__`/`__getstate__` ném,
   `__repr__`/`__str__`/`__format__` chỉ có `ref`. Bài kiểm: `pickle.dumps` và
   `json.dumps` đều `TypeError`.
3. **`KhoBiMatTrong`** — máy không có Credential Manager (CI Linux) thì
   `them_tai_khoan` NÉM `KhoBiMatKhongSan`; không tệp `.json/.env/.txt` nào dưới
   gốc chứa khoá (bài kiểm quét).

## 3. Windows Credential Manager — đo thật

`KhoBiMatWindows` gọi `advapi32.CredWriteW/CredReadW/CredDeleteW` qua `ctypes`,
mục `CRED_TYPE_GENERIC`, `Persist=LOCAL_MACHINE`, `UserName="router-cc"`, vùng tên
`RouterCC/provider/<ref>`. Không `CredEnumerate` — mục phiên `agy` của
Antigravity nằm cùng Credential Manager và **không bao giờ bị đọc**. Bài kiểm
`test_windows_credential_manager_vong_tron_that` ghi một mục thử dưới vùng tên,
đọc lại, xoá, khẳng định đã mất (chạy thật trên máy này; `skip` nơi khác).

`ref` = `<provider>.<alias-slug>.<8 hex ngẫu nhiên>` — ổn định để sổ trỏ tới, không
đoán được, và kiểm định dạng chặt (`[A-Za-z0-9][A-Za-z0-9._:-]{2,199}`).

## 4. Preset — khai báo, không giả định

| Preset | base_url mặc định | Model gợi ý | Ghi chú thật |
|---|---|---|---|
| `openai_compatible` | (bắt buộc nhập) | — | lấy model qua `GET /models` |
| `alibaba_dashscope` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | qwen-plus/turbo/max | khoá vùng Trung Quốc đại lục dùng `dashscope.aliyuncs.com` — sửa base_url khi thêm |
| `tencent_hunyuan` | `https://api.hunyuan.cloud.tencent.com/v1` | hunyuan-turbos-latest, hunyuan-lite | khoá API Hunyuan **khác** cặp SecretId/SecretKey của Tencent Cloud API v3 |

Mọi preset `da_do=False`; model gợi ý vào sổ với `nguon="preset"`; danh sách
thật thay bằng `nguon="probed"` sau `thu_ket_noi` thành công. Alibaba và
Tencent **không** được giả định giống nhau: base_url, model, ghi chú riêng; mọi
trường ghi đè được ở tầng provider. `base_url` phải `https://` (chỉ `http://`
cho 127.0.0.1/localhost — máy chủ giả của bài kiểm), không `user:pass@`, không query.

## 5. Thử kết nối chi phí tối thiểu, hỏi thử thủ công

* `GET {base_url}/models` — miễn phí ở mọi API OpenAI-compatible. Endpoint trả
  404/405/501 → `POST /chat/completions` với `max_tokens=1` và model gợi ý.
* Lỗi HTTP không bao giờ kèm header request; thân phản hồi cắt 300 ký tự, thay
  đúng giá trị khoá (nếu nhà cung cấp dội lại), rồi qua bộ lọc. Bài kiểm
  `test_loi_401_doi_khoa_bi_loc`: máy chủ giả trả 401 kèm nguyên khoá → `chi_tiet`
  chứa `401` và `[DA-LOC]`, không chứa khoá.
* `hoi()` = một lượt chat do NGƯỚI bấm ("Hỏi thử" trong UI), ghi sự kiện
  `PROVIDER_MANUAL_CALL`. Đây là "định tuyến thủ công" của Part E.
* HTTP là `urllib` chuẩn; `HttpGia` cho CI — toàn bộ đường chạy được không mạng.

## 6. Bể tài khoản chung

`BeTaiKhoan` — cùng hằng với V4 (`NGUONG_COOLDOWN=3`, `BACKOFF_COOLDOWN=(60,300,900,1800)`),
chọn tài khoản bật, không cooldown, ít `dang_dung` nhất, phá hoà theo alias;
`ket_thuc(ok=False)` ×3 → `cooldown`; thành công xoá chuỗi; `vi_sao_khong_ai()`
giải thích theo nhóm ("đầy chỗ x1; cooldown x2"). Trạng thái bền trong
`providers.db`.

## 7. Định tuyến (Part E — tối thiểu, có chủ ý)

`DichVuProvider.dang_ky_vao_fabric(fabric)` chạy khi engine dựng fabric: mỗi
provider bật → nhóm quota `<provider>_api` + model `<provider>/<model_id>` (năng
lực KHAI BÁO, `premium_tier` theo sổ); mỗi tài khoản → runtime
`EXT_<PROVIDER>_<ALIAS>`, `transport=http-openai`, **`dispatchable=False`**,
IDLE nếu lần thử cuối thành công, OFFLINE kèm lý do nếu chưa. `fabric.validate()`
hỏng → gỡ hết phần vừa thêm (fabric không bao giờ nửa chừng).

Hệ quả có bài kiểm (`test_dang_ky_vao_fabric_khong_nhan_dispatch`): `Scheduler.decide`
với `pin_provider=<provider>` trả `None`, lý do "runtime KHÔNG nhận dispatch";
`explain` thấy nó. Mọi thay đổi sổ (thêm/xoá/bật-tắt/thử kết nối) gọi
`sau_khi_doi` → engine đồng bộ vào fabric **đang sống** (`_dong_bo_provider_fabric`),
gỡ runtime/model `EXT_*` của tài khoản/provider đã xoá, không chạm khe AG — lỗi
thật nghiệm thu EXE lần 3 bắt được: fabric dựng trước (Leader mở phiên), provider
thêm sau, runtime chỉ hiện sau khi khởi động lại. **Không đường tự động nào giao việc cho một API trả tiền** cho
tới khi có adapter thực thi + ngân sách chi tiêu tường minh — đó là "bước tiếp
theo", không phải một cờ ẩn trong V0.6.1 (`AUTO_ROUTING = False` là hằng, không
đọc từ cấu hình/UI).

## 8. Ranh giới ký ức ↔ credential (Part F)

Ký ức được phép nhớ "tài khoản X tồn tại", "AG03 hỏng xác thực lúc 10:32",
"ali/Prod: HTTP 401" — và **không bao giờ** nhớ khoá/cookie/token đã hỏng.
Bộ lọc `memory/bi_mat.py` thêm ở V0.6.1: `sk-…`, `AKID…`, JWT ba đoạn,
`Cookie:`/`Set-Cookie:` (cả dòng), `session[_-]?id / sid / csrf_token / x-api-key /
api-key = …`. Bài kiểm:

* `test_bo_loc_ky_uc_bat_khoa_provider_va_cookie` — câu "AG03 failed authentication
  at 10:32 with key sk-… SecretId AKID… x-api-key … jwt … Cookie: …" → ≥5 lần lọc,
  phần "AG03 failed authentication at 10:32" còn nguyên.
* `test_ky_uc_giu_su_that_khong_giu_bi_mat` — người dùng kể sự cố kèm khoá vào
  chat → L0, blob, INCIDENT đề bạt đều không có khoá; tìm "AG03 hỏng xác thực" ra
  bản ghi; tìm theo khoá ra rỗng.
* `test_thu_ket_noi_that_bai_doi_khoa_khong_lot_vao_ky_uc` — thử kết nối hỏng với
  khoá dội lại → L0 `event:PROVIDER_TEST_FAILED` + INCIDENT có bằng chứng, không khoá
  ở `providers.db`, `control.db`, sổ ký ức (L0 + blob), `trang_thai()`.

## 9. API cục bộ và giao diện

| Đường | Việc |
|---|---|
| `GET /api/providers` | kho bí mật (kiểu/sẵn), preset, provider, tài khoản (chỉ ref), model, bể, chính sách |
| `POST /api/providers` | thêm provider (preset + base_url) |
| `DELETE /api/providers/{id}?xac_nhan=true` | xoá provider + tài khoản + credential (cần xác nhận) |
| `POST /api/providers/{id}/accounts` | alias + `gia_tri` (một lần) → `credential_ref` |
| `DELETE /api/providers/accounts/{acc}?xac_nhan=true` | xoá tài khoản + credential khỏi kho |
| `POST …/toggle` · `…/test` · `…/ask` | bật/tắt · thử kết nối · hỏi thử thủ công |

Mọi route sau rào V0.2 (Host trước token, token mọi request kể cả GET, không
CORS, 127.0.0.1) và mọi phản hồi qua `_sach()` (redact). Bài kiểm webapi: không
token → 401; vòng đời đầy đủ; **không phản hồi nào chứa khoá**, kể cả 400 khi giá
trị hỏng; xoá không xác nhận → 400.

Giao diện: nút **Providers** ở thanh trên → hộp thoại ba phần (kho bí mật · bể
Antigravity từ sổ đăng ký · provider ngoài với thêm/thử/bật-tắt/hỏi thử/xoá).
Ô khoá `type=password`, `autocomplete=off`, xoá khỏi DOM trước khi gửi.

## 10. Chưa cấu hình — và đó là trạng thái đúng

Không có khoá Alibaba/Tencent nào trên máy này được cấu hình bởi đợt V0.6.1:
hai preset ở trạng thái **NOT CONFIGURED**, người vận hành thêm sau qua hộp thoại
Providers (khoá vào Credential Manager, không vào kho git, không vào `.env`).
Nghiệm thu đóng gói dùng máy chủ giả trên 127.0.0.1 với khoá giả — xem
`PROJECT_MEMORY_V061.md` mục nghiệm thu.

## 11. Không làm (Part M)

Không Artifact Vault/Drive, không GitHub Stars Vault, không tự cập nhật, không
vector memory, không di trú/xoá archive production, không chi tiêu tự động trên
API trả tiền, không ký ức toàn cục xuyên dự án.
