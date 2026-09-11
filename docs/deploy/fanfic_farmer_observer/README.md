# Ảnh chụp quan sát đã lọc cho farmer — KẾ HOẠCH TRIỂN KHAI (chưa chạy)

**Trạng thái: CHỜ NGƯỜI VẬN HÀNH DUYỆT. Chưa có thay đổi nào trên máy
production, và chưa có thay đổi nào trong kho Fanfic.**

Thư mục này chứa mã ĐỀ XUẤT (`observer.py`) + các bước triển khai chính xác.
Router đã sẵn sàng đọc ảnh chụp; tới khi nó được triển khai, probe
`telemetry.snapshot` trả `UNAVAILABLE` kèm lý do, và chẩn đoán Drive vẫn là
`F — chưa đủ bằng chứng`.

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

## 5. Triển khai lên máy production

Đây là **thay đổi trên máy production**, cần người vận hành chạy:

```bash
# 1. cập nhật mã trên host
cd /opt/fanfic-audio && git pull        # hoặc quy trình phát hành đang dùng

# 2. khởi động lại farmer để nạp module mới
systemctl restart fanfic-farmer

# 3. xác nhận ảnh chụp ra đúng chỗ, đúng quyền
stat -c '%n %a %U:%G' /var/lib/fanfic-farmer/observability.json
#   mong đợi: /var/lib/fanfic-farmer/observability.json 644 fanfic:fanfic

# 4. xác nhận KHÔNG có bí mật trong đó
cat /var/lib/fanfic-farmer/observability.json

# 5. xác nhận rclone.conf VẪN riêng tư
stat -c '%n %a %U:%G' /var/lib/fanfic-farmer/rclone.conf
#   mong đợi: 600 fanfic:fanfic  (KHÔNG đổi)
```

Bước 2 khởi động lại một dịch vụ production. Router **không** tự làm, và
cũng không có thao tác nào trong `probe_van_hanh` làm được điều đó — lớp
probe chỉ đọc.

Router phía này **đã sẵn sàng**: chỉ cần thêm `telemetry_file` vào
`scripts/control_center/config/observability.json` (đã thêm sẵn), không cần
đổi mã Router nào nữa.

## 6. Kiểm chứng sau khi triển khai

```bash
python scripts/control_center_v07_probe_acceptance.py --chi kiemtoan
```

Mong đợi: `telemetry.snapshot` chuyển từ `UNAVAILABLE` sang `ACTIVE`, và
phân loại chuyển từ `F` sang một trong `A`–`E` **có bộ đếm chống lưng**.

Hợp đồng hai đầu đã có bài kiểm khoá lại ở
`scripts/tests/test_farmer_observer_contract_v07.py` (13 bài) — chạy được
ngay bây giờ, không cần máy production.
