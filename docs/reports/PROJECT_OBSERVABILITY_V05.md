# V0.5 — QUAN SÁT SỐNG DỰ ÁN + NỀN MÓNG CHO LEADER

Nhánh `feat/v05-live-observability`. **Chưa tag, chưa phát hành.**

---

## 1. Vấn đề

Nguyên văn tình huống đã gặp:

```
Người dùng: "production farmer còn chạy không?"
Leader    : (Router có 0 việc đang chạy) -> "không có gì đang chạy"
Thực tế   : fanfic-farmer trên AWS đang chạy, PID 350714, NRestarts 0,
            khởi động Tue 2026-09-08 15:55:31 UTC
```

**Cái sai không phải con số của Router.** Router thật sự có 0 việc. Cái
sai là dùng con số đó để trả lời một câu hỏi về **một hệ thống khác**:
Router đếm việc do CHÍNH nó điều phối, còn farmer là một systemd service
trên một máy khác, chạy độc lập, không hề đi qua Router. "Router rảnh" và
"production đã dừng" là hai câu khác nhau.

Đây là một lỗi **đúng đắn kiến trúc**, không phải một lỗi nhắc nhở: hệ
thống trước V0.5 **không có** cách nào biết trạng thái sống của bất cứ
thứ gì ngoài sổ của chính nó, nên Leader chỉ có một nguồn để suy.

---

## 2. Bậc thẩm quyền

`observability/tham_quyen.py`, bốn bậc, cao xuống thấp:

| Bậc | Nguồn | Ví dụ |
|---|---|---|
| 1 | **LIVE** — vừa đo từ hệ thống thật | `systemctl is-active` qua SSH |
| 2 | **KHO/BỀN** — kho git + sổ SQLite hiện tại | `git rev-parse`, số việc |
| 3 | **KÝ ỨC** — sự kiện đã ghi, ảnh chụp cũ | `cc_events`, chat cũ |
| 4 | **SUY LUẬN** — model tự đoán | — |

**Luật:** câu hỏi về HIỆN TẠI + có probe LIVE cho thứ được hỏi ⇒ bậc 3 và
4 KHÔNG được dùng để trả lời.

Cái bẫy ở giữa: **bậc 2 không sai**, Router thật sự có 0 việc. Nên bậc
thẩm quyền phải xét theo **từng thứ được hỏi**, không theo độ tin của
nguồn. `xet_cau_hoi()` nhận diện thì/sức khoẻ (`đang`, `còn…chạy`,
`tới đâu`, `xong chưa`, `healthy`, `alive`…) và **không ghim tên dự án
nào** — có bài kiểm quét bộ mẫu để chặn `farmer`/`fanfic`/`aws` lọt vào.

Câu vừa có dấu hiệu hiện tại vừa có mốc quá khứ ("hôm qua farm tới đâu")
thì **quá khứ thắng**: một phép đo BÂY GIỜ không trả lời được câu đó.

---

## 3. Kiến trúc provider

```
ProjectObservabilityProvider   (Protocol)   provider.py
  ├── ProviderCoSo             bọc thu() để KHÔNG provider nào ném
  ├── RouterProvider           nhóm `router`    — việc/agent của Router
  ├── GitProvider              nhóm `kho`       — nhánh/HEAD/sạch-bẩn
  ├── SshServiceProvider       nhóm `dich_vu`   — systemd qua SSH
  └── ProbeChuaCoDuong         nhóm tuỳ khai    — UNAVAILABLE + lý do
```

`DichVuQuanSat` (service.py) dựng provider theo cấu hình, chạy **song
song** (mỗi probe một trần riêng), gộp thành `AnhChupSong`.

**Dự án chung = Router + git, và MỌI dự án đều có.** Dự án khai thêm thì
được **CỘNG** vào, không thay thế — nên Fanfic chỉ là "chung + probe
riêng". Game-X / AlloyAgent / Admissions Scraper thêm adapter riêng mà
không sửa một dòng nào của Leader.

Hợp đồng cứng: `thu()` **không bao giờ ném**. Một endpoint production
chậm hay hỏng chỉ làm khối của nó mang `UNKNOWN` kèm lý do; lượt chat
Router bình thường vẫn chạy.

---

## 4. Lược đồ ảnh chụp

```
AnhChupSong
  project_id, thu_luc, tuoi
  trang_thai_chung        <- CHỈ dịch vụ sống (dich_vu+luu_tru+ung_dung)
  trang_thai_kho          <- kho git, báo RIÊNG
  co_bang_chung_song      <- có ít nhất một DỊCH VỤ đo được?
  router:   {router: KhoiQuanSat}          <- TÁCH RIÊNG
  dich_vu:  {fanfic_farmer: KhoiQuanSat}
  luu_tru:  {r2: …, drive: …}
  ung_dung: {appwrite: …}
  kho:      {git: …}
  nhat_ky_provider: [{provider, nhom, giay, trang_thai, duong, ghi_de}]

KhoiQuanSat: khoa, nhan, trang_thai (xấu nhất trong các quan sát ĐO ĐƯỢC)
QuanSat:     khoa, trang_thai, gia_tri, nguon, do_luc, tuoi,
             han_tuoi, qua_han, ly_do, bang_chung, nhan
```

### Sáu trạng thái, và ba cách "không biết" khác nhau

| | Nghĩa |
|---|---|
| `ACTIVE` | đo được, đang chạy |
| `DEGRADED` | đo được, chạy nhưng có dấu hiệu xấu (restart, đĩa ≥90%) |
| `DOWN` | **ĐO ĐƯỢC**, và nó không chạy — một khẳng định |
| `UNKNOWN` | có probe, lần đo này thất bại (mạng, quá hạn, thiếu khoá) |
| `UNAVAILABLE` | KHÔNG có probe nào cho thứ này |
| `STALE` | có số, nhưng cũ hơn `han_tuoi` |

`DOWN` là **thứ duy nhất** mang nghĩa khẳng định xấu. Cưỡng chế bằng mã,
không bằng lời:

* `QuanSat.__post_init__` **ném** nếu `UNKNOWN`/`UNAVAILABLE` mà không có
  `ly_do`, hoặc mà **có `gia_tri`**. `{"state": "unknown", "count": 0}` là
  một khẳng định về production mà không ai đo — cùng loại lỗi với "Router
  rảnh nên farmer đã dừng".
* `KhoiQuanSat.trang_thai` lấy cái xấu nhất trong **những cái đo được**;
  toàn `UNKNOWN` thì khối là `UNKNOWN`, không phải `DOWN`.
* `AnhChupSong.trang_thai_chung` **bỏ qua nhóm `router`** — Router `DOWN`
  (0 việc) không kéo dự án xuống `DOWN`.

### Một định chính trong chính đợt này: git không phải dịch vụ sống

Bản đầu để `kho` (git) vào phép gộp `trang_thai_chung` và
`co_bang_chung_song`. Lần nghiệm thu đóng gói cho ra hai hệ quả sai:

* một kho **bẩn** (1 tệp chưa commit) làm `trang_thai_chung` thành
  `DEGRADED` trong khi production hoàn toàn khoẻ;
* một lần `git status` **thành công** làm `co_bang_chung_song()` thành
  `True` **dù probe SSH đã thất bại** — nên Leader không còn nhận được
  câu "chưa xác minh được", đúng lúc nó cần nhất.

Kho git là **bậc 2** (trạng thái bền), không phải một dịch vụ đang chạy.
Giờ nó được báo riêng ở `trang_thai_kho`.

---

## 5. Adapter Fanfic

`observability.json` khai bốn probe cho `fanfic`, tất cả **chỉ đọc**:

| Probe | Nhóm | Kết quả đo thật |
|---|---|---|
| `fanfic_farmer` (ssh_service) | `dich_vu` | **ACTIVE** |
| `appwrite` | `ung_dung` | `UNAVAILABLE` + lý do |
| `r2` | `luu_tru` | `UNAVAILABLE` + lý do |
| `drive` | `luu_tru` | `UNAVAILABLE` + lý do |

Đo thật trên `ubuntu@13.212.224.218`, unit `fanfic-farmer`:

```
ssh              ACTIVE   ok
service_state    ACTIVE   active
main_pid         ACTIVE   350714
restarts         ACTIVE   0
started_at       ACTIVE   Tue 2026-09-08 15:55:31 UTC
disk             ACTIVE   21          (% đã dùng)
status_file      UNKNOWN  cat: /var/lib/fanfic-farmer/status.json: Permission denied
healthy          UNKNOWN  (cùng lý do)
round            UNKNOWN  (cùng lý do)
last_update      ACTIVE   1788967800  (từ `stat -c %Y`)
```

`status.json` thuộc `root`, nên `cat` bị từ chối với tài khoản `ubuntu`.
Ba trường lấy từ nội dung tệp ở lại `UNKNOWN` **kèm lý do chính xác** —
không bịa, không `DOWN`. Nhưng `stat -c %Y` vẫn chạy được, nên
`last_update` có thật: đó là thứ trả lời "số này còn mới không".

**KHÔNG dùng `sudo`.** Nâng quyền trên một máy production không phải việc
của một lớp quan sát. Cách sửa đúng nằm ở phía máy chủ — xem §11.

### Lệnh được phép gửi qua SSH (allowlist, fail closed)

```
systemctl is-active <unit>
systemctl show <unit> --property=MainPID,NRestarts,ActiveState,SubState,
                                 ExecMainStartTimestamp --no-pager
cat <status_file>
stat -c %Y <status_file>
df -Pk <path> | tail -1
```

Provider **không bao giờ** ghép lệnh từ chuỗi người dùng. Tham số đến từ
cấu hình đã kiểm.

---

## 6. Mô hình an ninh

**Toàn bộ V0.5 là chỉ-đọc, và điều đó được cưỡng chế bằng bài kiểm chứ
không bằng lời hứa.** `provider.KHONG_DUOC_CO` liệt kê ~30 động từ
(`systemctl restart/stop/start`, `rm -rf`, `aws s3 rm/cp/sync`,
`wrangler deploy/delete/secret`, `appwrite databases delete/create/update`,
`files.delete`, `put-object`, `kill`/`taskkill`, `iam `…) và một bài kiểm
quét **cả gói** để chặn chúng. Thêm một provider mang động từ tác động ⇒
bộ kiểm đỏ, chứ không lặng lẽ thành một cái nút "restart service" trong
một công cụ quan sát.

* `/api/live` và `/api/live/capabilities` **chỉ `GET`**; `POST/PUT/DELETE/
  PATCH` trả 404/405 (có bài kiểm). `refresh=1` chỉ bỏ qua bộ đệm.
* Cùng bộ rào V0.2 **không đổi**: token mọi request kể cả `GET`, kiểm
  `Host` **trước** kiểm token, không CORS, bind `127.0.0.1`.
* **Cấu hình không giữ bí mật.** Chỉ `key_path` (đường dẫn tới khoá đã có
  trên máy). `config.kiem_cau_hinh()` **từ chối cả tệp** nếu thấy chữ ký
  khoá riêng / `AKIA…` / `ghp_…` / `sk-…`, và từ chối mọi khoá tên
  `secret`/`password`/`token`/`credential`. Tệp này nằm trong kho git, và
  một khoá riêng lọt vào đây là sự cố không hoàn tác được bằng một commit.
* Khoá riêng không vào dòng lệnh nào đọc lại được: `ssh -i <đường dẫn>`
  mang **đường dẫn**, không mang nội dung. `bang_chung` đi qua
  `packet.redact`, và có bài kiểm đòi payload API không chứa
  `PRIVATE KEY`/tên tệp khoá/`.pem`.
* `BatchMode=yes` + `NumberOfPasswordPrompts=0`: probe **không bao giờ**
  dừng lại hỏi mật khẩu — nó fail closed thành `UNKNOWN`.

**Số lần chạm production: 0.** Không lệnh nào trong đợt này ghi, xoá, hay
deploy bất cứ thứ gì.

---

## 7. Bộ đệm và độ tươi

| Ngưỡng | Giá trị | Hành vi |
|---|---|---|
| `TUOI_TUOI` | 25s | trả bộ đệm ngay |
| `TUOI_CON_DUNG` | 180s | **trả cũ ngay** + làm mới ở luồng nền |
| quá 180s | — | đo đồng bộ |
| `max_age` (mỗi provider) | 120s | quá thì `hieu_luc()` = `STALE` |
| nhịp UI | 90s + `visibilitychange` + nút ↻ | mỗi lần là một phiên SSH thật |
| `refresh=1` | — | bỏ qua bộ đệm (nút tay) |

Leader chat **không** bị treo vì SSH: `chat()` chỉ gọi probe khi
`xet_cau_hoi()` nói câu hỏi đòi trạng thái hiện tại, và probe đi qua bộ
đệm. Câu "viết cho tôi bài kiểm này" không tốn một phiên SSH nào.

Ô UI làm mới **từ bộ đệm** trong vòng vẽ (`veSongTuCache`), và chỉ gọi
mạng ở nhịp 90s / đổi dự án / nút tay — có bài kiểm đòi `veHet()` **không**
gọi `veSong()`, vì vòng vẽ chạy mỗi nhịp WebSocket và một lời gọi ở đó là
một phiên SSH mỗi giây.

Cấu hình có thể **ghi đè theo bản cài**: `<gốc>/.router/observability.json`
thắng bản đóng gói trong `_internal/`. Cần vì cấu hình mặc định đi trong
gói EXE, nên người dùng không thể (và không nên) sửa vào đó — bản cập
nhật sau sẽ ghi đè. Ảnh chụp ghi lại **đường dẫn đã dùng** trong
`nhat_ky_provider`; thiếu dòng đó thì một lần "cấu hình không ăn" không
chẩn đoán được từ ngoài — đã vấp thật ở lần nghiệm thu đầu.

---

## 8. Tích hợp Leader

`engine._khoi_song(project_id, text)`:

1. `xet_cau_hoi(text)` — câu này đòi trạng thái sống không?
2. nếu không → trả `""`, không đo gì.
3. nếu có → `quan_sat.anh_chup(project_id)` (qua bộ đệm), ghi sự kiện
   `LIVE_PROBE`.
4. nếu **không dịch vụ nào đo được** → nối thêm `cau_tu_choi_bia()`.

`leader.LUAT_SONG` được nhét vào nhắc nhở **trước** ảnh chụp tĩnh, với
bốn điều cấm: không suy dịch vụ ngoài từ số việc Router; không đọc
`UNKNOWN`/`UNAVAILABLE`/`STALE` thành `DOWN`; không bịa số cho trường
`UNAVAILABLE`; không trả lời từ ký ức khi khối SỐNG có số.

Rào chính vẫn là **rào cấu trúc** (chỉ đính kèm khối sống khi câu hỏi đòi;
`trang_thai_chung` bỏ qua Router; `co_bang_chung_song` bỏ qua git) — đoạn
nhắc nhở chỉ là lớp thứ hai, vì một rào dựa vào việc model ngoan thì
không phải rào.

Câu Leader **thật sự** trả lời trên bản đóng gói:

> Production farmer (fanfic-farmer trên AWS) hiện đang CHẠY (ACTIVE).
> Thông tin ghi nhận từ live probe qua ssh:13.212.224.218 (7 giây trước)…

với **Router tasks = 0** trong cùng ảnh chụp.

---

## 9. Giao diện

Ô **TRẠNG THÁI SỐNG (DỰ ÁN)** đứng đầu cột phải, trước ô Router; ô Router
được dán nhãn `(ROUTER)` và một dòng "*nội bộ — không nói gì về dịch vụ
ngoài*". Hai thứ trả lời hai câu hỏi khác nhau nên chúng phải **đọc ra là
khác** — gộp chúng về mặt thị giác là mời đúng cái nhầm V0.5 đi sửa.

* chỉ báo độ tươi (`ACTIVE · 12s trước`), **đổi màu vàng** khi >60s;
* nút ↻ đo lại ngay;
* trường không đo được hiện **CHỮ** trạng thái, không bao giờ một con số;
* probe hỏng → ô hiện lý do, phần Router vẫn đọc được.

---

## 10. Bộ kiểm và nghiệm thu

| Bộ | Kết quả |
|---|---|
| `test_observability` (A–G: thẩm quyền, ngữ nghĩa, Router-vs-ngoài, phân tích SSH, chỉ-đọc, generic, Leader) | **46/46** |
| `test_observability_api_ui` | **16/16** |
| `test_observability_live_fanfic` (probe THẬT, tự bỏ qua nếu không nối được) | **6/6** |
| Hồi quy V0.4 (ux_v04, webapi, leader, desktop_shell, allowlist, attachments, quyền, hook) | **251/251** |
| `test_control_center_core` | **80/80** |

Nghiệm thu **bản EXE đóng gói** (`control_center_v05_acceptance.py`,
`ShellExecuteW` + WebView2 thật): **19/19**, chín tình huống của mục 13.

Số đo then chốt trong lần chạy đóng gói:

```
Router tasks=0 · farmer=ACTIVE · tổng thể NGOÀI=ACTIVE
service_state=active; main_pid=350714; restarts=0; disk=21
sự kiện LIVE_PROBE: 0 -> 1
provider hỏng -> UNKNOWN (không thấy tệp khoá) · tổng thể=UNKNOWN
   · bằng chứng sống=False        <- KHÔNG phải DOWN
dự án `router` (không adapter riêng) -> tổng thể=UNAVAILABLE, KHÔNG DOWN
```

### Cửa sổ console — nói thẳng

3/5 lần chạy: **0 vi phạm**. 2/5 lần: **1** cửa sổ, và chùm tiến trình
quanh nó là `bash.exe`×6 + `jq.exe`×2 — **không cái nào** là con của ứng
dụng — tức là phiên Claude Code và hook shell của nó, cùng lúc `rclone.exe`
đang chạy một tác vụ nền trên máy. Cùng chữ ký đã ghi ở
`CONTROL_CENTER_V04_NGHIEM_THU_EXE.md` §3.

`ssh.exe` là đường sinh tiến trình MỚI của V0.5, nên nó được kiểm cô lập
riêng: 3/3 lượt với `an_cua_so()` cho **0 vi phạm**. Trong các lần chạy
đóng gói, app sinh `ssh.exe`×10 + `git.exe`×10 mà không cửa sổ nào đi kèm.

Phép quy trách nhiệm không phân biệt được tuyệt đối khi app sinh 43+ tiến
trình console mỗi lượt — ghi lại như một giới hạn của **phép đo**, không
phải một khẳng định rằng app sạch tuyệt đối.

---

## 11. Giới hạn đã biết

1. **`status.json` không đọc được** với tài khoản `ubuntu` (`root`-only),
   nên `healthy` / `round` ở `UNKNOWN`. Cách sửa nằm ở **phía máy chủ**:
   cho tệp readable theo nhóm, hoặc cho farmer ghi thêm một bản
   world-readable. Không sửa bằng `sudo` từ phía quan sát.
2. **Appwrite / R2 / Drive**: giao diện đã khai, probe báo `UNAVAILABLE`
   kèm lý do chính xác. Đọc thật đòi credential production mà đợt này bị
   cấm đọc/tạo.
3. **Nhận diện câu hỏi bằng mẫu chữ**, không bằng model. Cố tình nghiêng
   về phía đi đo (một probe thừa tốn vài giây; một câu trả lời sai về
   production tốn niềm tin). Câu hỏi lạ có thể lọt.
4. **Ô SỐNG chỉ hiện dự án đang chọn**; không có bảng tổng mọi dự án.
5. **Không có lịch sử trạng thái sống** — mỗi lần là một ảnh chụp. Xu
   hướng ("farmer restart mấy lần tuần này") cần một kho chuỗi thời gian.
6. Phép đo cửa sổ console như §10.

---

## 12. Điểm tích hợp cho việc CHƯA làm (mục 15)

Không cái nào dưới đây được cài trong đợt này; chỉ ghi chỗ cắm.

| Việc sau | Cắm vào đâu |
|---|---|
| TencentDB Agent Memory / Infinite Project Memory | thêm một provider nhóm `ung_dung` cho trạng thái kho ký ức; và một **bậc 3** tường minh trong `tham_quyen.py` để ký ức có nguồn gốc thay vì trộn vào chat |
| Artifact Vault | provider nhóm `luu_tru`, cùng hình dạng `r2`/`drive` |
| GitHub Stars Capability Vault | provider nhóm `ung_dung`, chỉ đọc |
| Router self-updater | đọc `trang_thai_chung` để **từ chối tự cập nhật** khi dịch vụ đang `DEGRADED`/`UNKNOWN` |
| ECO/AUTO/STRONG/MAX selector | `AnhChupSong` đã mang đủ tín hiệu tải để một bộ chọn chế độ đọc |

---

## 13. Bước tiếp theo đề xuất cho V0.6

**Lịch sử trạng thái sống + báo động khi ĐỔI trạng thái.**

Lý do: V0.5 trả lời được "BÂY GIỜ thế nào" nhưng không trả lời được "nó
đã hỏng từ lúc nào" hay "tuần này restart mấy lần" — và chính những câu
đó là thứ người vận hành hỏi sau khi biết có gì sai. Nền móng đã có:
`QuanSat` đã mang `nguon` + `do_luc`, nên chỉ cần một bảng chuỗi thời
gian trong sổ SQLite (`live_history`) ghi lại **mỗi lần trạng thái ĐỔI**
(không ghi mọi lần đo — đó là rác), cộng một sự kiện `LIVE_STATE_CHANGED`
để Leader chủ động nói "farmer vừa chuyển sang DEGRADED 4 phút trước".

Việc đó cũng đóng luôn giới hạn 5, và nó KHÔNG cần credential mới.
