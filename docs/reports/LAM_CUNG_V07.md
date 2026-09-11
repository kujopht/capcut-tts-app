# V0.7 — LÀM CỨNG TRƯỚC KHI ĐÓNG BĂNG

Hai khoảng trống đúng đắn còn lại sau khi môi giới probe chạy được
(`PROBE_VAN_HANH_V07.md`): (A) production chưa phơi được số đo an toàn, và
(B) mô hình năng lực runtime chưa tồn tại nên việc bị từ chối thì chết tại
chỗ.

---

## A. Telemetry production ĐÃ LỌC cho Fanfic

### A1. `status.json` có an toàn để phơi không? **KHÔNG CHỨNG MINH ĐƯỢC**

Đọc thẳng mã farmer thật (`server/farmer/`) chứ không đoán. Lược đồ
`FarmerStatus` phần lớn an toàn — số đếm, mốc thời gian, cờ sức khoẻ — nhưng
có **hai đường văn bản tự do của bên thứ ba** chảy thẳng vào tệp:

| Trường | Nguồn thật | Vị trí |
|---|---|---|
| `archive.detail` | `proc.stderr` **THÔ** của `rclone` | `drive_archive.py`, nhánh `else` của `probe()`: `ket_qua["detail"] = err[:300]` |
| `lanes[*].errors[]` | `msg[:300]` của một ngoại lệ bất kỳ | `metrics.py`, `LaneMetrics.note_error` |

`drive_archive.probe()` đã xử lý riêng trường hợp `invalid_grant`/`token`
thành một câu người đọc được — phản xạ đúng — nhưng **nhánh còn lại truyền
nguyên văn stderr**. Một lỗi Google API có thể mang URL ký sẵn, tên tài
khoản, hay mảnh token tuỳ lúc.

Nên câu trả lời là: **không nới quyền `status.json`.** Không phải vì nó chắc
chắn bẩn, mà vì **không chứng minh được là sạch** — và với một tệp có hai ống
dẫn mở, "chưa thấy bẩn lần nào" không phải một lập luận.

> Một chi tiết dễ hiểu nhầm: `status.json` đang là `600` **không phải** do
> một quyết định bảo mật. `MetricsWriter._write_atomic` dùng
> `tempfile.mkstemp` (tạo `600`) rồi `os.replace` (giữ nguyên mode). Chế độ
> `600` là **tác dụng phụ**. Điều đó làm việc nới quyền dễ tới mức nguy hiểm,
> nên lý do KHÔNG nên làm cần được ghi rõ ở đây.

### A2. `rclone.conf` — vẫn RIÊNG TƯ, và nay có HAI lớp chặn

Đo sau khi làm xong: `600 fanfic:fanfic`, **không đổi**.

Thêm một lớp nữa ở phía Router, và lớp này ra đời vì một bài kiểm bắt được lỗ
hổng thật: `read_paths` khai theo **thư mục**, mà `rclone.conf` nằm ngay
trong `/var/lib/fanfic-farmer`. Nghĩa là `filesystem.read_text` **được phép**
`tail` nó. Hôm nay hệ điều hành chặn — nhưng để quyền của máy chủ làm rào
**duy nhất** là sai: một lần đổi quyền trên host sẽ lặng lẽ mở đường.

Nay có `_MAU_TEP_BI_MAT`: một **danh sách CẤM thắng danh sách cho phép**
(`rclone.conf`, `*.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials*.json`,
`token*.json`, `service_account*.json`, `.netrc`, …). Siêu dữ liệu (`stat`)
vẫn lấy được — đó là thứ trả lời "tệp còn được ghi không" và nó không lộ gì.

```
ACTIVE  /var/lib/fanfic-farmer/rclone.conf:size=668:mtime=…:mode=600:owner=fanfic:fanfic
CHẶN ở Router: '…/rclone.conf' thuộc loại tệp BÍ MẬT — lớp probe không bao
               giờ đọc nội dung nó, kể cả khi nó nằm dưới gốc đã khai
```

### A3. Thiết kế: ảnh chụp quan sát ĐÃ LỌC

```
trạng thái riêng tư của farmer  ->  ảnh chụp ĐÃ LỌC (644)  ->  Router  ->  Leader/worker
```

Tệp: `/var/lib/fanfic-farmer/observability.json`, `schema_version = 1`, ghi
nguyên tử, mode **`644` tường minh** (`os.chmod` trước `os.replace` — vì
`mkstemp` cho `600`).

**Danh sách CHO PHÉP**, không phải danh sách cấm: `farmer` (mốc + sức khoẻ),
`round`, `lanes[*]` 15 bộ đếm số nguyên + `error_count` + `last_error_class`,
`totals`, `quotas`, `archive` (bí danh remote, đường dẫn chuẩn, enabled,
reachable, status, `last_error_class`, mốc thử/thành công gần nhất, done /
pending / failed), `integrity.ok`.

**Không bao giờ có**: token OAuth, API key, khoá riêng, cookie, nội dung tệp
cấu hình, header `Authorization`, `archive.detail` thô, `lanes[*].errors[]`
thô, đường dẫn trình thông dịch.

Văn bản lỗi bị quy về **một mã trong bộ ĐÓNG** (`auth_invalid_grant`,
`quota_exceeded`, `network`, `not_found`, `permission_denied`, `timeout`,
`rclone_missing`, `disabled`, `unknown`). Có lỗi mà chưa phân loại được thì
là `unknown`, **không** phải rỗng — gộp hai cái đó sẽ giấu mất một sự cố.

Router **lọc lại lần nữa** khi đọc (`loc_telemetry`): khoá lạ bị bỏ, mã lỗi
lạ thành `unknown`. Hai kho là hai nhịp phát hành khác nhau, nên không bên
nào tin tuyệt đối bên kia.

Có ảnh chụp thì `kiem_duong_ong` phân biệt được A–E **bằng bộ đếm thật**
(`_phan_loai_tu_telemetry`): archive tắt hoặc `auth_invalid_grant` → **C**;
`failed > 0` kèm mã lỗi → **C**; không với tới remote → **E**; có tác phẩm mà
`pending > 0` → **B**; không ứng viên nào → **A**; có ứng viên mà không ra
tác phẩm → **D**. Không nhánh nào đoán.

### A4. Đột biến máy chủ: **ĐÃ LÀM, sau khi người dùng duyệt tường minh**

Triển khai lúc `2026-09-11T03:43Z`. Nhật ký đầy đủ + trình tự ở
`docs/deploy/fanfic_farmer_observer/README.md` mục 5–7. Tóm tắt:

| Mục | Trước | Sau |
|---|---|---|
| `ActiveState` / `SubState` | `active` / `running` | `active` / `running` |
| `MainPID` | 350714 | **684324** (đổi vì khởi động lại) |
| `NRestarts` | 0 | **0** — khởi động lại do NGƯỜI, không phải tự phục hồi sau lỗi |
| `metrics.py` | `46a9fbe4…` | `7fab65d5…` (+1173 byte, ĐÚNG một chỗ chèn) |
| `observer.py` | không có | `e13eea6a…`, 644 root:root |
| `observability.json` | không có | **644** fanfic:fanfic, ~2 KB, đang cập nhật |
| `rclone.conf` | 600 fanfic:fanfic | **600 fanfic:fanfic — KHÔNG đổi** |
| `status.json` | 600 fanfic:fanfic | **600 fanfic:fanfic — KHÔNG đổi** |
| `work/` | `farmer.lock` | `farmer.lock` — không đổi |

Sao lưu: `/var/backups/fanfic-farmer-observer-20260911T034128Z/metrics.py`,
sha256 khớp bản gốc.

Ba điều đáng ghi lại vì chúng đổi cách làm lần sau:

* **Bản kế hoạch đầu ghi sai cơ chế.** Nó nói `git pull`, nhưng tiền kiểm
  cho thấy `/opt/fanfic-audio` **không phải kho git**. Triển khai thật dùng
  cài trực tiếp, có sao lưu và đối chiếu sha256 hai đầu. Tiền kiểm tồn tại
  đúng để bắt những chỗ như thế.
* **Lần chạy đầu DỪNG LẠI đúng chỗ nó nên dừng.** Bước kiểm cú pháp trên
  host hỏng vì `ubuntu` không ghi được `__pycache__` trong thư mục root —
  lỗi của PHÉP KIỂM, không phải của mã. Kịch bản dừng, **chưa** khởi động
  lại dịch vụ, nên ma cũ vẫn chạy nguyên. Sửa bằng `PYTHONPYCACHEPREFIX`
  rồi mới đi tiếp.
* **Kiểm rò bí mật chạy NGAY TRÊN HOST trước khi khởi động lại**: nhét một
  token Google giả và một khoá AWS giả vào đúng hai trường văn bản tự do rồi
  chạy `build_snapshot` thật. Kết quả `RO RI: KHONG`, mà mã lớp lỗi vẫn đúng
  (`quota_exceeded`, `auth_invalid_grant`). Chứng minh tại chỗ, không suy từ
  một bài kiểm chạy ở máy khác.

**Trôi mã cần theo dõi:** hai tệp đang nằm trên host **chưa có trong kho
Fanfic** (kho Fanfic không bị sửa, đúng ràng buộc). Một lần phát hành sau có
thể ghi đè mất chúng — xem README mục 6.

### A4b. Thiết kế gốc: đột biến máy chủ **CÓ CẦN**

Mã đề xuất + kế hoạch nằm ở `docs/deploy/fanfic_farmer_observer/`
(`observer.py` + `README.md`). Thay đổi ở kho Fanfic là **hai bước nhỏ**:
thêm `server/farmer/observer.py`, và một dòng `publish(status.as_dict())` ở
cuối `MetricsWriter.write`.

Triển khai cần `git pull` + `systemctl restart fanfic-farmer` trên host —
**đột biến production**, nên Router dừng lại trước đó. Không tệp nào của kho
Fanfic bị sửa, không lệnh nào chạm host.

Hợp đồng hai đầu đã được khoá bằng bài kiểm **chạy được ngay bây giờ**
(`test_farmer_observer_contract_v07.py`, 13 bài): dựng một `status.json`
giống thật *có cả token Google lẫn khoá AWS trong hai trường văn bản tự do*,
rồi khẳng định ảnh chụp không mang chữ nào của chúng, mà vẫn giữ đúng mã lớp
lỗi (`quota_exceeded`, `auth_invalid_grant`).

---

## B. Mô hình năng lực runtime + định tuyến lại

### B1. Nguyên nhân gốc — một từ đơn làm trọng tài bảo mật

`pool/adapters.py` quét danh sách TỪ ĐƠN trên **toàn bộ gói việc đã render**:

```python
_HINH_DANG_BAO_MAT = ("security", "credential", "auth", "permission",
                      "secret", "token", "bảo mật", "xác thực", "quyền")
```

Lời nhắc công cụ **tiêu chuẩn** mà Router gắn vào **mọi** việc có câu:

> "…**quyền** được khớp theo chuỗi chính xác…"

Nên **mọi** việc đều "mang hình dạng bảo mật". Cộng với
`codex_security_shaped_refusal` nằm trong `KHONG_THU_LAI`, kết quả là: mọi
việc xếp vào Codex đều bị từ chối rồi **chết ở `BLOCKED`** — dù chính thông
báo từ chối hứa "định tuyến sang worker khác".

### B2. Sửa ở đúng tầng, không phải bằng cách sửa danh sách từ

**Ba tầng, ba sửa:**

1. **Phân loại** (`router_v3.policy`, MỘT nguồn sự thật duy nhất):
   `la_hinh_dang_bao_mat()` dùng **cụm từ chuyên môn** ("rà soát bảo mật",
   "phân quyền", "api key", "lỗ hổng", "luân chuyển khoá"…) và chỉ áp lên
   **phần văn bản do NGƯỜI VIẾT** — `phan_nguoi_viet()` cắt bỏ từ mốc
   boilerplate đầu tiên (`CÔNG CỤ:`, `PERMISSION_ENVELOPE`, `NHẬT KÝ GIT DO
   ROUTER`, `BẰNG CHỨNG VẬN HÀNH DO ROUTER`…). Danh sách từ đơn cũ được giữ
   lại **chỉ để tương thích ngược**, kèm ghi chú không dùng để phân loại nữa.

2. **Khai báo năng lực** (`control_center/nang_luc.py`): việc đòi gì
   (`nang_luc_viec`, tất định: khai báo tường minh > kiểu việc > cụm từ),
   runtime từ chối gì (`tu_choi_theo_runtime`). Nguồn khai báo là
   **`security.security_refusal_family` vốn đã có sẵn trong `fabric.json`** —
   ở đây chỉ THI HÀNH nó, không phát minh thêm — cộng khoá `refuses` tuỳ
   chọn cho từng runtime. Đổi khai báo thì kết quả đổi theo; có bài kiểm
   khoá lại để không ai hardcode `"codex"` vào mã.

3. **Xếp chỗ là RÀO CỨNG** (`sessions.decide(cam_runtime=…)`): khác hẳn
   `tranh_runtime` (ưu tiên, hết chỗ thì rơi về). Một chỗ đã khai từ chối thì
   **không bao giờ** nhận việc đó; hết chỗ tương thích thì **CHỜ**, vì gửi đi
   một lượt biết chắc bị từ chối là tốn quota để nhận lại một câu từ chối.

### B3. Định tuyến lại — có trần, có nguồn gốc, nhả tài nguyên

`LY_DO_DINH_TUYEN_LAI = {"codex_security_shaped_refusal"}` — **hẹp có chủ
ý**: đây là từ chối vì CHÍNH SÁCH, chỗ chạy còn chưa thử làm việc. Lỗi thật
của việc (`tool_permission_denied`, `security_gate`, `executor_error`,
`test_failed`…) **không** nằm trong đó và **không** được định tuyến lại.

`_dinh_tuyen_lai()`: nhả phiên → xoá `owner_session` → `QUEUED` lại → ghi
`REROUTE_QUEUED`. Trần `MAX_DINH_TUYEN_LAI = 2`; hết trần thì
`REROUTE_EXHAUSTED` và để người xem. Nguồn gốc giữ trong hợp đồng:

```json
"_dinh_tuyen_lai": [{"tu_runtime": "CODEX01",
                     "ly_do": "codex_security_shaped_refusal",
                     "lan": 1, "luc": 1789…}],
"_cam_runtime": ["CODEX01"]
```

`_cam_runtime` được nạp vào rào **cứng** ở lượt xếp chỗ sau: một chỗ đã từ
chối sẽ từ chối y hệt.

---

## C. Bài kiểm

| Tệp | Số bài | Phủ |
|---|---|---|
| `test_probe_van_hanh_v07.py` | 63 | môi giới, ảnh chụp, phân loại A–F, danh sách cấm tệp bí mật |
| `test_nang_luc_reroute_v07.py` | 20 | dương tính giả, loại trừ runtime, định tuyến lại, an toàn |
| `test_farmer_observer_contract_v07.py` | 13 | hợp đồng hai đầu, không rò bí mật |

Ứng với chín yêu cầu:

1. việc tiếng Việt thường có chữ "quyền" **không** thành việc bảo mật — 6
   việc mẫu, mỗi việc khẳng định lời nhắc THẬT SỰ chứa chữ đó trước khi kiểm;
2. runtime không tương thích bị loại — kể cả khi đổi họ từ chối trong cấu
   hình;
3. từ chối vì chính sách → định tuyến lại thành công, có nguồn gốc;
4. có trần, vượt trần thì dừng;
5. lỗi thật **không** bị định tuyến lại;
6. phiên được nhả và việc về `QUEUED`;
7. đầu ra quan sát không mang bí mật;
8. `rclone.conf` vẫn riêng tư — và Router tự chặn thêm một lớp;
9. đột biến production = **0**.

Hai bài bắt được lỗi thật khi viết:

* `test_probe_KHONG_co_thao_tac_doc_noi_dung_rclone_conf` — phát hiện
  `read_text` **được phép** đọc `rclone.conf` vì nó nằm trong một thư mục đã
  khai. Sinh ra `_MAU_TEP_BI_MAT`.
* `test_hop_dong_bao_mat_thi_TRANH_codex` (bản trước) — bắt `NameError` bị
  `except Exception` nuốt mất.

## D. Chẩn đoán Drive thật — F trước, **A** sau khi có telemetry

Cùng một câu hỏi, hai lần đo, và đó là điểm đáng xem nhất của mục này.

**Trước khi triển khai** — `F, chưa đủ bằng chứng`, 11/13 quan sát đo được.
Không phải một câu trả lời kém: nó là câu trả lời ĐÚNG khi bộ đếm
archive/round nằm sau một tệp `600`.

**Sau khi triển khai** — `A, chưa có việc nào đạt chuẩn production`,
**12/13** quan sát đo được, 0 việc phái đi, 43s:

> *"Không có ứng viên MỚI nào: tìm 2 ứng viên nhưng cả 2 đều trùng hoặc đã
> hoàn thành từ trước, `produced = 0` (bộ đếm tính từ khi tiến trình khởi
> động `2026-09-11T03:43:18 UTC`, vòng 1)."*

Và quan trọng không kém — ảnh chụp cho thấy **đường archive HOÀN TOÀN KHOẺ**:
`enabled=true`, `rclone_installed=true`, `reachable=true`,
`status=ARCHIVE_DONE`, `last_error_class=""`, remote `fanfic-gdrive`, gốc
`fanfic-gdrive:FanficWorld/production`. Đó là bằng chứng **loại trừ** C
(archive hỏng) và E (sai remote/đường dẫn) — thứ trước đây chỉ đoán được.

### Một tinh chỉnh mà chính số đo thật ép ra

Vòng đầu tiên trả `discovered=2, deduped=2, produced=0`. Bản phân loại lúc
đó đọc thành **D** ("có ứng viên mà không ra tác phẩm" → đường ống tắc). Sai.
`deduped` theo chính chú thích của farmer nghĩa là **"đã xong thật sự"** — 2
thứ tìm được đều là bản trùng, nên đây là **A** ("không có việc mới"), không
phải tắc nghẽn. Nay `_phan_loai_tu_telemetry` trừ `deduped` khỏi `discovered`
trước khi phán, và xét `review_pending` TRƯỚC vì "đang chờ đánh giá" là câu
trả lời cụ thể hơn.

### Cửa sổ bộ đếm — nói rõ, không lờ đi

`MetricsWriter._totals` cộng dồn **từ lúc tiến trình khởi động**, không phải
24h. Lần khởi động lại vừa rồi đã **đặt lại** bộ đếm, nên con số hiện tại mô
tả vài phút chứ không mô tả "từ hôm qua tới giờ". Mọi kết luận sinh ra từ ảnh
chụp đều **mang theo cửa sổ đó trong chính câu lý do**, và Leader lặp lại nó
cho người đọc. Muốn trả lời trọn vẹn cho cửa sổ 24h thì phải để farmer chạy
đủ một ngày — hoặc thêm bộ đếm bền ở phía farmer, một thay đổi khác.

Bằng chứng độc lập với bộ đếm vẫn ủng hộ A: 48h nhật ký **không một dòng**
về archive/rclone/drive, và `work/` chỉ có `farmer.lock`.

### Còn lại chưa đo được

`rclone listremotes` vẫn `permission denied` (đúng như thiết kế — không nới
quyền `rclone.conf`); hàng đợi Appwrite và artifact R2 vẫn chưa có adapter.
Cả hai đều được nêu tên trong câu trả lời thay vì bỏ lửng.
