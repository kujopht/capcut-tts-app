# OPERATOR HANDOFF — cập nhật 2026-09-08

> **Trạng thái một dòng:** mã đã xong và đã merge; **farmer CHƯA được cài** lên
> máy AWS. Cần đúng **một** hành động của người vận hành (cần quyền root).

---

## 1. HÀNH ĐỘNG DUY NHẤT CẦN BẠN

```
ssh -i ~/.ssh/fanficappwrrite.pem -t ubuntu@13.212.224.218 'sudo bash -c "set -e; cd /opt/fanfic-audio; echo STEP-1-remote; git ls-remote origin HEAD >/dev/null; echo STEP-2-fetch; git fetch origin; echo STEP-3-merge; git checkout main; git merge --ff-only origin/main; echo STEP-4-bootstrap; exec bash deploy/bootstrap-farmer.sh"'
```

Không hỏi gì cả — khoá Gemini đã bị loại khỏi thiết kế. Lệnh in `STEP-1` …
`STEP-4`; **nếu dừng, dòng `STEP-n` cuối cùng in ra chính là bước hỏng.**

**Vì sao lệnh này khác lệnh trước:** bản trước làm câm phép tiền kiểm bằng
`>/dev/null 2>&1` dưới `set -e`, nên một lần hỏng thoát ra mà **không in gì**
— nhìn y hệt như thành công. Đó là lỗi của bản lệnh, không phải của bạn.

Nghi ngờ hàng đầu: `git ls-remote`/`git fetch` chạy bằng **root**. Đã xác minh
cả hai chạy được bằng `ubuntu`; không kiểm được bằng `root` vì phiên tự động
bị chặn leo thang quyền (và không được nới ra).

---

## 2. TRẠNG THÁI THẬT TRÊN MÁY AWS (kiểm 2026-09-08, chỉ đọc)

| Hạng mục | Trạng thái |
|---|---|
| Unit `fanfic-farmer` | **`not-found`** — chưa cài |
| Dịch vụ farmer | **`inactive`** |
| Số bản farmer đang chạy | **0** |
| `/etc/fanfic-audio/farmer.env` | **không có** |
| `farmer-text-sources.json` | **không có** |
| `/var/lib/fanfic-farmer` | **không có** |
| SHA kho trên máy | **`a755f7f`** (chưa đồng bộ; `main` = `a866d30`) |
| `deploy/bootstrap-farmer.sh` trên máy | **không có** → script chưa từng chạy |

Không một dấu vết nào của bootstrap tồn tại. Bước đồng bộ git hỏng trước tiên,
nên script còn chưa lên tới máy.

---

## 3. SẢN XUẤT KHÔNG BỊ ẢNH HƯỞNG

| Hạng mục | Trạng thái |
|---|---|
| `fanfic-worker-prod` | **active**, không bị đụng |
| `fanfic-translation-worker-prod` | **active**, không bị đụng |
| Appwrite `review_jobs` | Sống, `pending_visible: 0` |
| Appwrite `content_queue` | 60 mục — 12 chờ / 3 xong / 45 hoãn |
| R2 | Đang phục vụ, không đổi |
| Drive `fanfic-gdrive` | Hoạt động; cây `production/` đã tạo; **legacy `archive/` nguyên vẹn** |
| `worker-prod.env` | Không bị đọc, không bị đổi quyền |

Không có trạng thái dở dang nào phải dọn.

---

## 4. ĐÃ XÁC MINH TRÊN HẠ TẦNG THẬT

- **Vòng đánh giá hybrid, đầu-cuối:** farmer xếp việc → laptop giành → chạy
  pool Antigravity thật → `quarantine (35)` → farmer đọc lại và **không sản
  xuất gì**. Đúng hành vi.
- Khử trùng lặp lằn audio: 3/3 nhận đúng mục đã gặt.
- `review_jobs` cấp phát, `status.json` đúng hình dạng, cây Drive chính tắc.

**Chưa chạy thật:** TTS dispatch và cổng ảnh bìa/nền — chưa tác phẩm nào qua
được cổng đánh giá, nên hai bước đó mới chỉ có test đơn vị.

---

## 5. SAU KHI LỆNH CHẠY XONG

Script tự kiểm bốn điều và **chỉ bật dịch vụ nếu cả bốn đạt**: quyền tệp cấu
hình đúng, unit đã cài, hàng đợi đánh giá đọc được, và hai worker production
vẫn `active` với `worker-prod.env` không đổi quyền.

Rồi cần chạy máy đánh giá trên laptop (nếu không, mọi tác phẩm dừng ở
`REVIEW_PENDING` — cố ý):

```
python scripts/router_review_worker.py
```

Và điền nguồn thật vào `/etc/fanfic-audio/farmer-text-sources.json` khi bạn
đã chọn tác phẩm — script chỉ gieo sẵn 3 tác phẩm **phạm vi công cộng** trên
Wikisource (đã kiểm HTTP 200) để mở máy an toàn. Tôi **không** tự chọn tác
phẩm fanfiction: đó là quyết định nội dung của bạn.

---

## 6. HẠN MỨC (bảo thủ, không đổi)

2 tải về đồng thời · 8 đánh giá/vòng · 3 job TTS/vòng · 3 mục/lằn/vòng ·
nghỉ 900 giây · sàn đĩa 5 GiB · **khoá một bản** (hai farmer không thể cùng
chạy).

---

## 7. MÃ

`main` = `a866d30`. PR #165–#169 đã merge, CI xanh cả ba cổng
(backend 4.580 PASS, web build/lint/types, gitleaks). Cây làm việc sạch,
không còn gì chưa commit.

Nhánh `feat/farmer-deploy-ready` trên remote là bản **thừa** (thông điệp commit
bị hỏng do backtick, đã thay bằng `feat/farmer-deploy-v2` và merge). Vô hại,
xoá lúc nào cũng được.
