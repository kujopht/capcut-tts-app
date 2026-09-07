# MORNING HANDOFF — đêm 2026-09-07 → 08

## DONE

- **Ranh giới đánh giá chuyển hẳn sang pool Antigravity** qua hàng đợi kéo.
  Không còn khoá Gemini ở bất kỳ đâu trong đường sản xuất. Laptop **không mở
  cổng nào** — nó poll ra ngoài, giành việc, chạy, ghi kết quả.
- **Cấp phát collection `review_jobs`** trên Appwrite production (22 mục tạo
  mới, thuần cộng thêm, các collection khác không bị đụng).
- **Chứng minh vòng lặp hybrid ĐẦY ĐỦ trên hạ tầng thật** — xem TESTS.
- **Cây sản xuất chính tắc trên Drive** đã tạo; cây legacy còn nguyên.
- **Sửa một lỗi thật**: lớp lưu trữ Drive đang ghi vào `FanficWorld/archive`
  (legacy) thay vì `FanficWorld/production`. Đã sửa + test chặn tái diễn.
- **Đính chính một kết luận sai của chính tôi**: báo cáo trước nói venv
  interpreter là `777` world-writable và gọi đó là đường leo thang quyền.
  **Sai** — đó là symlink, và Linux bỏ qua bit quyền của symlink. Interpreter
  thật là `/usr/bin/python3.12` mode `755`, không có gì ghi được.
  `chmod` để "sửa" sẽ **đi theo symlink và đổi python của cả máy**.
- Cổng toàn vẹn interpreter (giải symlink đúng cách), bố cục chính tắc +
  `work_id` tất định, cổng ảnh bìa/nền, lớp gương Drive.

## RUNNING

**Không có tiến trình nào đang chạy.** Farmer chưa được cài lên AWS, và không
có tiến trình nền nào được khởi động trên máy này. Đúng yêu cầu: chỉ khởi động
khi đã xác minh đầy đủ **và** không còn ranh giới cần người — B2 và B6 vẫn còn.

## BLOCKED

| # | Việc | Cần gì |
|---|---|---|
| **B2** | Bootstrap farmer trên AWS | **Quyền quản trị.** Một lệnh trong `docs/PRODUCTION_FARMER.md`. Hook chặn leo thang quyền và tôi không nới ra. |
| **B6** | Nguồn truyện chữ thật | **Quyết định nội dung.** Chưa có nguồn thật; tôi không tự chọn. |

Đã giải quyết trong đêm: **B1** (collection) và **B3** (Drive token tự phục
hồi — **không** cần `rclone config reconnect`).

## TESTS

```
server/tests   4.574 PASS / 0 FAIL (8 skip)
```

Quan trọng hơn con số — **vòng lặp hybrid chạy thật, đầu-cuối, trên hạ tầng
production**:

| Bước | Kết quả thật |
|---|---|
| Farmer xếp việc | `review_pending: 1`, `produced: 0` — fail closed đúng |
| Laptop giành + chạy pool Antigravity | `DONE — quarantine (35)` |
| Farmer đọc bản án vòng sau | `reviewed: 1, rejected: 1, produced: 0` |

Tác phẩm bị `quarantine` nên **không** được sản xuất — đúng hành vi.

## COMMITS

| Commit | Nội dung |
|---|---|
| `36739dc` | main sau khi merge PR #167 (đánh giá hybrid) |
| PR #165 | đồng bộ kho bằng root (mô hình quyền) |
| PR #166 | kho sản xuất chính tắc + cổng toàn vẹn + gương Drive |
| PR #167 | đánh giá hybrid qua hàng đợi + pool Antigravity |

CI xanh cả ba (backend, web build/lint/types, gitleaks).

## PRODUCTION STATE

| Hạng mục | Trạng thái |
|---|---|
| Appwrite `review_jobs` | **Sống**, `pending_visible: 0` |
| Appwrite `content_queue` | 60 mục (15 chạy được, 45 bị hoãn) — không đổi đêm nay |
| R2 | Đang phục vụ, không đổi |
| Drive `fanfic-gdrive` | **Hoạt động**; cây `production/` đã tạo; legacy nguyên vẹn |
| Farmer trên AWS | **Chưa cài, chưa chạy** |
| Hai worker production trên AWS | Không bị đụng tới |
| Máy đánh giá (laptop) | Đã chạy thủ công 1 lượt; **không** chạy nền |

## FARMER METRICS (lượt chạy cuối, từ máy này)

```
audio : discovered 3 · deduped 3 · produced 0
text  : discovered 1 · reviewed 1 · rejected 1 · produced 0 · review_pending 0
archive: fanfic-gdrive → FanficWorld/production · reachable · ARCHIVE_DONE
```

Lằn audio khử trùng lặp đúng 3/3 (các mục TePi đã gặt phiên trước). Lằn text
đi trọn vòng đánh giá và dừng đúng ở `quarantine`.

## EXACT HUMAN ACTIONS NEEDED

**1. Cài farmer lên AWS** (quyền quản trị) — một lệnh:

```
ssh -i ~/.ssh/fanficappwrrite.pem -t ubuntu@13.212.224.218 'sudo bash -c "set -e; cd /opt/fanfic-audio; git ls-remote --exit-code origin HEAD >/dev/null 2>&1; git fetch -q origin; git checkout -q main; git merge --ff-only -q origin/main; exec bash deploy/bootstrap-farmer.sh"'
```

Script **không hỏi khoá Gemini nữa**. Nó kiểm hàng đợi đánh giá, chạy một lô
có kiểm soát, và chỉ bật dịch vụ nếu bốn phép kiểm đạt.

**2. Điền nguồn truyện chữ thật** vào
`/etc/fanfic-audio/farmer-text-sources.json` — nếu không, lằn truyện chữ sẽ
không sản xuất gì.

**3. Chạy máy đánh giá trên laptop** (nền, mỗi 60 giây):

```
python scripts/router_review_worker.py
```

Không có việc này thì mọi tác phẩm dừng ở `REVIEW_PENDING` — cố ý.
