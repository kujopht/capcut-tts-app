# Đối soát audio mồ côi theo lịch — staging

## Nguyên tắc

**Chỉ đọc. Không bao giờ tự động xoá.**

`scripts/reconcile_audio.py` mặc định là dry-run. Muốn xoá phải truyền **hai**
cờ: `--delete --yes-really-delete`. Lịch chạy tự động **chỉ** được dùng dạng
mặc định.

Lý do không bật xoá tự động: object "mồ côi" có thể chỉ là một job đang chạy mà
lần quét bắt gặp giữa chừng. Thời gian ân hạn 24 giờ che được trường hợp đó,
nhưng một lỗi trong logic phân loại cộng với chế độ xoá tự động là **mất dữ liệu
người dùng không hoàn tác được**. Đọc báo cáo vài tuần rồi mới cân nhắc.

Bộ quét job (`_sweep_forever`) **không bao giờ** gọi công cụ này. Hai việc tách
rời hoàn toàn: bộ quét chỉ đổi trạng thái job, đối soát mới chạm vào file.

## Render Cron Job

```yaml
  - type: cron
    name: fas-staging-reconcile
    runtime: python
    plan: starter
    region: singapore
    branch: feature/web-mvp
    schedule: "17 3 * * *"        # 03:17 UTC hằng ngày, giờ thấp điểm
    buildCommand: pip install -r server/requirements.txt
    startCommand: >
      python scripts/reconcile_audio.py
      --json /tmp/doi-soat-$(date -u +%Y%m%d).json
    envVars:
      - key: FAS_ENV
        value: staging
      - key: DATA_BACKEND
        value: appwrite
      - key: STORAGE_BACKEND
        value: r2
      - key: APPWRITE_ENDPOINT
        sync: false
      - key: APPWRITE_PROJECT_ID
        sync: false
      - key: APPWRITE_DATABASE_ID
        sync: false
      - key: APPWRITE_API_KEY
        sync: false
      - key: R2_ACCOUNT_ID
        sync: false
      - key: R2_BUCKET
        sync: false
      - key: R2_ACCESS_KEY_ID
        sync: false
      - key: R2_SECRET_ACCESS_KEY
        sync: false
```

Không có `--delete` trong `startCommand`. Đó là chủ ý.

## Nếu nền tảng không có cron

`cron` trên một máy bất kỳ có quyền truy cập cùng credential:

```cron
17 3 * * * cd /srv/fas && python scripts/reconcile_audio.py --json /var/log/fas/doi-soat-$(date -u +\%Y\%m\%d).json >> /var/log/fas/reconcile.log 2>&1
```

## Báo cáo có gì

JSON gồm: tổng số object, số đã được tham chiếu / đang xử lý / còn trong ân hạn /
mồ côi, danh sách bản ghi trỏ tới object không tồn tại, và số lỗi.

**Đã khử dữ liệu nhạy cảm:** báo cáo chứa **khoá object**, không chứa presigned
URL, token hay credential. Đã quét bốn báo cáo trong lượt E2E: không có dấu hiệu
secret nào. Khoá object có dạng `audio/{owner_id}/{chapter_id}/{hash}.mp3` — nó
lộ `owner_id`, nên báo cáo phải được coi là **nội bộ**, đừng đưa vào ticket công
khai.

## Cần chú ý điều gì trong báo cáo

| Dấu hiệu | Ý nghĩa | Hành động |
|---|---|---|
| `mo_coi` tăng đều mỗi ngày | có đường sinh rác chưa biết | điều tra trước khi nghĩ tới xoá |
| `ban_ghi_thieu_file` > 0 | **mất dữ liệu** — bản ghi trỏ tới object không còn | điều tra ngay; công cụ không bao giờ tự xoá bản ghi |
| `dang_xu_ly` cao kéo dài | job kẹt, hoặc worker chết | xem runbook, mục "kiểm tra job stale" |
| `loi` > 0 | không đọc được vài object | kiểm tra credential và quyền |

## Khi thực sự cần xoá

Chạy **thủ công**, sau khi đọc báo cáo dry-run và hiểu từng mục:

```bash
# 1. Xem trước — bắt buộc
python scripts/reconcile_audio.py --json truoc-khi-xoa.json

# 2. Chỉ khi đã hiểu từng object trong danh sách mồ côi
python scripts/reconcile_audio.py --delete --yes-really-delete --json sau-khi-xoa.json
```

Công cụ kiểm tra lại tham chiếu **ngay trước** khi xoá từng object, nên một job
kết thúc giữa lần quét và lần xoá vẫn an toàn.
