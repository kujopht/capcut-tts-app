# Đo N+1 trên trang chi tiết truyện

Đo bằng trình duyệt thật (Playwright, Chromium), backend chạy chế độ `appwrite` +
`r2` thật, không phải mock.

**Dữ liệu đo:** truyện `nov_3a9b095ba400407c` — "Truyen do hieu nang", **12 chương**,
trạng thái nháp, chủ sở hữu `audit_5ff2c485@example.com`. Đây là truyện fixture tôi
tạo riêng để đo; xoá bằng nút **Xoá** ở `/write` khi không cần nữa.

## Số request tới backend khi mở `/novels/{id}`

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Tổng request `/api/*` | 16 | 4 |
| `GET /api/chapters/{id}` | **12** (một request mỗi chương) | **0** |
| `GET /api/novels/{id}` | 2 | 2 |
| `GET /api/auth/me` | 2 | 2 |
| Công thức theo số chương N | `N + 4` | `4` (hằng số) |

`GET /api/novels/{id}` và `/api/auth/me` xuất hiện hai lần vì React StrictMode
gọi effect hai lần ở chế độ dev; bản production chỉ gọi một lần. Con số quan
trọng là **12 → 0**: đó là phần tăng tuyến tính theo số chương.

## Số truy vấn lên Appwrite

Mỗi `GET /api/chapters/{id}` tốn 3 lượt gọi Appwrite (`get_chapter`,
`track_for_chapter`, `get_novel`).

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Lượt gọi Appwrite cho 12 chương | 12 × 3 = 36 | 1 |
| Lượt gọi Appwrite cho cả trang | ~38 | 3 |
| Công thức theo số chương N | `3N + 2` | `2 + ceil(N/50)` |

Truy vấn gộp dùng `equal` với mảng giá trị — Appwrite hiểu đó là IN. Chia lô 50
id một lần vì Appwrite giới hạn độ dài truy vấn, và có lật trang vì một chương
có thể có nhiều bản audio.

## Cách đo lại

```js
// Trong Playwright, đếm request /api/* khi mở trang
const calls = [];
page.on("request", r => { if (r.url().includes("/api/")) calls.push(r.url()); });
await page.goto("http://localhost:3000/novels/nov_3a9b095ba400407c");
await page.waitForSelector(".list-item");
calls.filter(c => /\/api\/chapters\/chp_/.test(c)).length;   // phải là 0
```

Regression test khoá lại con số này mà không cần trình duyệt:

- `server/tests/test_chapter_list_batching.py::TestNotLinearInChapters`
  — đếm số lần gọi kho, khẳng định 3 chương và 60 chương tốn **y hệt** nhau.
- `server/tests/test_appwrite_protocol.py::TestBatchedAudioLookup`
  — khẳng định 1, 25 và 50 chương đều tốn đúng 1 request lên Appwrite.
- `web/tests/ui.test.mjs` — khẳng định trang chỉ còn đúng một lời gọi `api.get*`.

## Độ trễ còn lại

Trang mất khoảng 4–5 giây để hiện ở máy này. Đó là độ trễ mạng tới Appwrite
Cloud (~1 giây mỗi lượt × 3–4 lượt tuần tự), không phải N+1. Trước khi sửa thì
36 lượt gọi kia chạy song song từ trình duyệt nên cảm giác không chậm hơn nhiều,
nhưng chúng đập vào quota Appwrite theo cấp số nhân với số chương.

## Ảnh

`docs/screenshots/nplus1/` — trang chi tiết 12 chương (desktop + mobile) và
trang `/write` sau khi sửa.
