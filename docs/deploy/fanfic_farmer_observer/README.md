# Ảnh chụp quan sát đã lọc cho farmer — ĐÃ TRIỂN KHAI

**Trạng thái: ĐÃ TRIỂN KHAI 2026-09-11T03:43Z, sau khi người dùng duyệt
tường minh.** Xem mục 7 cho nhật ký lần chạy thật.

Thư mục này chứa mã đã triển khai (`observer.py`) + các bước chính xác.

> **Sửa một chỗ sai trong bản kế hoạch đầu:** bản đầu ghi `git pull` để cập
> nhật mã trên host. **Sai** — tiền kiểm cho thấy `/opt/fanfic-audio`
> **không phải một kho git** (`fatal: not a git repository`). Triển khai
> thật dùng **cài trực tiếp** hai tệp, có sao lưu và đối chiếu sha256; xem
> mục 5.

---

## 1. Vì sao KHÔNG nới quyền `status.json`

`status.json` phần lớn an toàn: số đếm, mốc thời gian, cờ sức khoẻ. Nhưng nó
có **hai đường văn bản tự do của bên thứ ba** chảy thẳng vào:

| Trường | Nguồn | Mã |
|---|---|---|
| `archive.detail` | `proc.stderr` THÔ của `rclone` | `server/farmer/drive_archive.py`, nhánh `else` của `probe()` (`ket_qua["detail"] = err[:300]`) |
| `lanes[*].errors[]` | `msg[:300]` của một ngoại lệ bất kỳ | `server/farmer/metrics.py`, `LaneMetrics.note_error` |

`drive_archive.probe()` đã xử lý riêng trường hợp `invalid_grant`/`token`
thành một câu người đọc được — phản xạ đúng — nhưng **nhánh còn lại truyền
nguyên văn stderr**. Một lỗi của Google API có thể mang URL ký sẵn, tên tài
khoản, hay mảnh token tuỳ lúc.

Nên câu trả lời cho *"status.json có an toàn để phơi không?"* là:
**KHÔNG CHỨNG MINH ĐƯỢC LÀ AN TOÀN**, vì hai trường trên là ống dẫn mở. Không
nới quyền nó.

> Ghi chú kỹ thuật, vì nó dễ gây hiểu nhầm: `status.json` đang là `600`
> **không phải** do một quyết định bảo mật. `MetricsWriter._write_atomic`
> dùng `tempfile.mkstemp` (tạo `600`) rồi `os.replace` (giữ nguyên mode).
> Chế độ `600` là *tác dụng phụ*. Điều đó làm việc nới quyền trở nên dễ —
> và cũng chính vì thế mà phải nói rõ lý do KHÔNG nên làm.

## 2. Vì sao KHÔNG phơi `rclone.conf`

Nó chứa token OAuth của Drive. Ảnh chụp chỉ nêu **bí danh** remote
(`gdrive`) và đường dẫn chuẩn (`gdrive:FanficWorld/production`) — đủ trả lời
"mirror đi đâu" mà không để lộ thứ mở được cửa. `rclone.conf` **giữ nguyên
`600 fanfic:fanfic`**.

## 3. Hợp đồng ảnh chụp

Tệp: `/var/lib/fanfic-farmer/observability.json`, mode **`644`**, ghi nguyên
tử, `schema_version = 1`.

Chỉ những nhóm sau, và đều là **danh sách CHO PHÉP**:

```
schema_version, generated_at
farmer   : started_at, updated_at, healthy, unhealthy_reason (≤200, farmer tự viết)
round    : number, started_at, seconds
lanes[*] : 15 bộ đếm SỐ NGUYÊN + error_count + last_error_class
totals   : bộ đếm số nguyên
quotas   : số nguyên
archive  : remote_alias, root, enabled, rclone_installed, reachable, status,
           last_error_class, last_attempt_at, last_success_at,
           done, pending, failed
integrity: ok
```

**Không bao giờ có:** token OAuth, API key, khoá riêng, cookie, nội dung tệp
cấu hình, header `Authorization`, `archive.detail` thô, `lanes[*].errors[]`
thô, đường dẫn trình thông dịch.

Văn bản lỗi được quy về **một mã trong bộ ĐÓNG**: `auth_invalid_grant`,
`quota_exceeded`, `network`, `not_found`, `permission_denied`, `timeout`,
`rclone_missing`, `disabled`, `unknown`, hoặc rỗng. Có lỗi mà không phân loại
được thì là `unknown`, **không** phải rỗng — gộp hai cái đó lại sẽ giấu mất
một sự cố thật.

Router **lọc lại lần nữa** khi đọc (`probe_van_hanh.loc_telemetry`): khoá lạ
bị bỏ, `last_error_class` lạ thành `unknown`. Hai kho là hai nhịp phát hành
khác nhau, nên không bên nào tin tuyệt đối bên kia.

## 4. Thay đổi mã (kho Fanfic)

Hai bước, đều nhỏ:

**(a)** Thêm tệp `server/farmer/observer.py` — chép nguyên `observer.py`
trong thư mục này.

**(b)** Gọi nó ở cuối `MetricsWriter.write`, `server/farmer/metrics.py`:

```python
         self._write_atomic(status.as_dict())
+        # Anh chup QUAN SAT da loc cho Router Control Center (mode 644).
+        # Khong bao gio nem: quan sat khong duoc lam chet vong san xuat.
+        from server.farmer.observer import publish
+        publish(status.as_dict())
         return status
```

Không sửa gì khác. `status.json` giữ nguyên nội dung, đường dẫn và **quyền
`600`**.

Tuỳ chọn: truyền `archive_totals={"done":…, "pending":…, "failed":…}` nếu
farmer có sẵn bộ đếm tích luỹ — không có thì ba số đó là `0` và Router vẫn
phân loại được từ `lanes[*]`.

## 5. Triển khai lên máy production — trình tự ĐÃ DÙNG

`/opt/fanfic-audio` không phải kho git, nên cài **trực tiếp** hai tệp. Trình
tự dừng-khi-hỏng, sao lưu trước khi ghi, đối chiếu sha256 hai đầu:

```bash
# 1. tải lên /tmp (ubuntu ghi được) rồi ĐỐI CHIẾU sha256
#    (đưa qua stdin: `base64 -d > /tmp/_deploy_<tên>`)
sha256sum /tmp/_deploy_observer.py /tmp/_deploy_metrics.py

# 2. SAO LƯU tệp sẽ đổi — TRƯỚC mọi lần ghi
sudo install -d -m 700 -o root -g root /var/backups/fanfic-farmer-observer-<MỐC>
sudo cp -a /opt/fanfic-audio/server/farmer/metrics.py \
          /var/backups/fanfic-farmer-observer-<MỐC>/metrics.py

# 3. cài, giữ nguyên 644 root:root như các tệp anh em
sudo install -m 644 -o root -g root /tmp/_deploy_observer.py \
     /opt/fanfic-audio/server/farmer/observer.py
sudo install -m 644 -o root -g root /tmp/_deploy_metrics.py \
     /opt/fanfic-audio/server/farmer/metrics.py

# 4. KIỂM TẠI CHỖ trước khi khởi động lại — cú pháp, import, và một lần
#    `build_snapshot` thật có bí mật giả cài vào để xem có lọt không.
#    `PYTHONPYCACHEPREFIX` là BẮT BUỘC: thư mục là root:root nên `ubuntu`
#    không ghi được `__pycache__`, và đó là lỗi của PHÉP KIỂM chứ không
#    phải của mã — lần đầu đã dừng đúng ở đây.
cd /opt/fanfic-audio && PYTHONPYCACHEPREFIX=/tmp/pyc \
  .venv/bin/python -m py_compile server/farmer/observer.py server/farmer/metrics.py

# 5. chỉ khi 4 sạch mới khởi động lại
sudo systemctl restart fanfic-farmer
```

Khởi động lại một dịch vụ production là **đột biến**. Router **không** tự
làm: không thao tác nào trong `probe_van_hanh` làm được điều đó — lớp probe
chỉ đọc, và `_kiem_chi_doc()` từ chối đúng những động từ này. Lần triển khai
thật đi qua một đường RIÊNG, tường minh, chỉ dùng cho lần đó.

**Khôi phục** (nếu cần): `sudo cp -a <backup>/metrics.py
/opt/fanfic-audio/server/farmer/metrics.py && sudo systemctl restart
fanfic-farmer`. `observer.py` là tệp MỚI, xoá nó là đủ để quay lại hoàn toàn.

Router phía này **đã sẵn sàng** từ trước: chỉ cần `telemetry_file` trong
`scripts/control_center/config/observability.json` (đã có), không đổi mã.

## 6. Trôi mã so với kho Fanfic — ĐÃ HOÀ GIẢI

Đã xong ngày 2026-09-11. Hai tệp nay nằm trong kho nguồn trên nhánh
`feat/farmer-sanitized-observability` @ `5baa8c7` (tách từ `main`
`a913fd2`), **chưa merge vào `main`**.

Một chi tiết đáng ghi: **đây không phải hai kho.**
`C:\Users\nguye\Documents\CapCut-TTS-App` và
`C:\FanficWorkers\router-control-center` dùng CHUNG một `.git` (xem
`git worktree list`), và nhánh v0.7 cũng chứa `server/farmer/`. Nên "đưa
vào kho Fanfic" nghĩa là commit lên một nhánh của chính kho này, tách khỏi
nhánh Router — không phải một lần sao chép liên kho.

Hoà giải **có đối chiếu, không chép mù**:

| Kiểm | Kết quả |
|---|---|
| `observer.py` kho ⇄ host | `e13eea6a…c9e434` — **giống hệt** |
| `metrics.py` kho ⇄ host | `7fab65d5…95952a` — **giống hệt** |
| bản gốc trong kho ⇄ bản gốc host | `46a9fbe4…193fbe` — khớp, nên bản vá đặt đúng nền |
| quét bí mật / đường dẫn máy | sạch (không khoá, không IP, không tên máy, không đường Windows) |
| đường dẫn tuyệt đối còn lại | đúng MỘT hằng số sản phẩm, cùng họ `DEFAULT_STATUS_PATH` |

**Cần triển khai lại: KHÔNG** — nguồn và host đã giống hệt nhau.

## 7. Nhật ký lần triển khai thật (2026-09-11T03:43Z)

| Mục | Trước | Sau |
|---|---|---|
| `ActiveState` | `active` | `active` |
| `SubState` | `running` | `running` |
| `MainPID` | 350714 | **684324** (đổi vì khởi động lại) |
| `NRestarts` | 0 | **0** (khởi động lại do người, không phải tự phục hồi) |
| `Result` | `success` | `success` |
| `metrics.py` sha256 | `46a9fbe4…193fbe` | `7fab65d5…95952a` |
| `observer.py` | không có | `e13eea6a…c9e434`, 644 root:root |
| `observability.json` | không có | **644** fanfic:fanfic, ~2 KB |
| `rclone.conf` | 600 fanfic:fanfic | **600 fanfic:fanfic** (không đổi) |
| `status.json` | 600 fanfic:fanfic | **600 fanfic:fanfic** (không đổi) |
| `work/` | `farmer.lock` | `farmer.lock` (không đổi) |

Sao lưu: `/var/backups/fanfic-farmer-observer-20260911T034128Z/metrics.py`
(sha256 `46a9fbe4…193fbe` — khớp bản gốc).

Kiểm rò bí mật **chạy ngay trên host** trước khi khởi động lại: nhét một
token Google giả và một khoá AWS giả vào đúng hai trường văn bản tự do, rồi
khẳng định ảnh chụp không mang chữ nào của chúng — kết quả `RO RI: KHONG`,
mà mã lớp lỗi vẫn đúng (`quota_exceeded`, `auth_invalid_grant`).

**Khoảng trống đã biết:** `archive.last_attempt_at` / `last_success_at` hiện
luôn rỗng — farmer chưa theo dõi hai mốc đó, và `observer.py` cố ý KHÔNG bịa
chúng. Muốn có thì phải thêm ở phía farmer; đó là một thay đổi khác.

## 6. Kiểm chứng sau khi triển khai

```bash
python scripts/control_center_v07_probe_acceptance.py --chi kiemtoan
```

Mong đợi: `telemetry.snapshot` chuyển từ `UNAVAILABLE` sang `ACTIVE`, và
phân loại chuyển từ `F` sang một trong `A`–`E` **có bộ đếm chống lưng**.

Hợp đồng hai đầu đã có bài kiểm khoá lại ở
`scripts/tests/test_farmer_observer_contract_v07.py` (13 bài) — chạy được
ngay bây giờ, không cần máy production.
