# Ảnh lượt sửa tính đúng đắn và khả năng mở rộng

Desktop 1440×900, mobile 390×844. Backend chạy chế độ `appwrite` + `r2` thật,
với 16 truyện của một người dùng (12 truyện tạm `[TAM]` đã xoá sau khi đo).

## Số request khi mở trang

Đếm trên Network của Chromium, gộp theo route. `/api/auth/me` xuất hiện hai lần
vì React StrictMode gọi effect hai lần ở chế độ dev.

### `/library` — 16 truyện

| Route | Trước | Sau |
|---|---|---|
| `GET /api/novels?mine=true` | 1 | 1 |
| `GET /api/jobs` | 1 | 1 |
| `GET /api/chapters?mine=true` | — | **1** |
| `GET /api/novels/{id}` | **16** | **0** |
| `GET /api/auth/me` | 2 | 2 |
| **Tổng** | **20** | **5** |

Công thức theo số truyện N: **`N + 4` → `5` (hằng số)**.

### `/studio` — không đổi

| Route | Trước | Sau |
|---|---|---|
| `GET /api/novels?mine=true` | 1 | 1 |
| `GET /api/novels/{id}` | 1 | 1 |
| `GET /api/voices` | 1 | 1 |
| `GET /api/jobs` | 1 | 1 |
| `GET /api/auth/me` | 2 | 2 |
| **Tổng** | **6** | **6** |

`/studio` **không bị N+1**: nó gọi `getNovel` cho đúng một kho chứa của Audio
Studio, không phải cho mỗi truyện. Báo cáo audit trước đây gộp nó chung với
`/library` là không chính xác.

## Ảnh

| Ảnh | Cho thấy điều gì |
|---|---|
| `sau-nplus1-library-desktop.png` | Thư viện sau khi sửa, 3 bản audio, tên chương và truyện đúng |
| `sau-nplus1-library-mobile.png` | Thư viện ở mobile, không tràn ngang |
| `sau-nplus1-studio-desktop.png` | Audio Studio còn nguyên |
| `sau-nplus1-studio-mobile.png` | Audio Studio ở mobile |

Không có ảnh "trước" của Network: bảng số ở trên là phép đo thật, ghi lại từ
Network của trình duyệt trước khi sửa frontend. Cách đo lại:

```js
const calls = [];
page.on("request", (q) => { if (q.url().includes("/api/")) calls.push(q.url()); });
await page.goto("http://localhost:3000/library");
await page.waitForTimeout(9000);
calls.filter((c) => /\/api\/novels\/nov_/.test(c)).length;   // phải là 0
```
