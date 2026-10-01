# QA giao diện Trợ lý AI bằng Chrome thật (headless)

Dựng **đúng** `AiProvider` + `AiPanel` + `AiLauncher` + trang `/assistant` của `web/` (không sao chép mã), thay phần mạng bằng
một máy chủ giả chạy trong trang, rồi dùng Chrome headless (CDP) để **đo** bố cục và chạy các luồng người dùng.

```bash
node scripts/qa/ai_ui/run.mjs                      # toàn bộ (≈ 3–4 phút)
node scripts/qa/ai_ui/run.mjs --only "^layout"     # một nhóm kịch bản (regex theo id)
node scripts/qa/ai_ui/run.mjs --shots <thư mục>    # lưu ảnh chụp từng trạng thái
node scripts/qa/ai_ui/run.mjs --json kq.json       # kết quả máy đọc được
```

Cần: Node ≥ 22 (WebSocket có sẵn), `web/node_modules` (esbuild), và Chrome (`CHROME_PATH` nếu không ở
`C:/Program Files/Google/Chrome/Application/chrome.exe`). Chrome chạy với `--user-data-dir` tạm riêng, mỗi viewport một
browser context — **không đụng** cửa sổ Chrome đang dùng. Mã thoát 1 nếu có kiểm tra FAIL; dòng `info` chỉ báo số đo.

## Kiểm gì

| Nhóm | Nội dung |
|---|---|
| `layout`, `layout-states` | 320 / 360 / 390 / 430 / 768 / 1024 / 1280: không tràn ngang, không phần tử nào vượt khung nhìn, ô soạn thấy được, vùng chạm ≥ 24px (báo `info` nếu < 44px), ô nhập ≥ 16px (iOS không tự phóng to) — ở các trạng thái: rỗng, hội thoại dài (từ/URL/mã không có khoảng trắng), hết lượt, lịch sử tiêu đề dài, popover cài đặt, lỗi + "Chưa gửi", chế độ viết |
| `behaviour-send-stop-regenerate` | Enter/Shift+Enter/ô trống, IME đang soạn không gửi, gửi, Tạo lại, Dừng giữa chừng |
| `behaviour-quota-and-errors` | Hết lượt của CHÍNH người dùng (kèm giờ làm mới, không phần trăm toàn site, "Chưa gửi", ô soạn khoá), hết công suất chung, `ai_busy` |
| `behaviour-resilience` | Luồng đóng sạch không có `done`/`error` không kẹt "đang trả lời"; Tạo lại sau khi mở hội thoại cũ từ lịch sử |
| `behaviour-account-switch` | Đăng xuất / đổi tài khoản trong cùng trang: không còn nội dung, hạn mức, cờ phiên của người trước |
| `behaviour-focus` | Desktop: mở panel → focus vào ô soạn; đóng → focus về nút mở |
| `behaviour-scroll-anchor` | Cuộn lên đọc trong lúc stream thì khung không bị giật xuống đáy |
| `behaviour-reduced-motion` | `prefers-reduced-motion`: không còn hoạt ảnh đáng kể |
| `perf-idle-and-reopen` | Khi đóng chỉ 1 request `/access`; panel mở rỗng không request nền; mở/đóng 40 lần không rò DOM/heap; stream 600 từ không có long task > 200ms |

## Giới hạn (nói thẳng)

* Không có Safari/iOS thật và không mô phỏng bàn phím ảo: kiểm "an toàn bàn phím" chỉ ở mức đọc mã (xem `docs/ai/`).
* Máy chủ giả nói đúng hợp đồng `/api/ai/*` nhưng không phải Appwrite/Gemini; hành vi phía máy chủ do
  `server/tests/test_ai_e2e_regression.py` kiểm.
* Đây là công cụ QA thủ công, **không chạy trong CI** (CI không có bước dựng Chrome headless cho nó).
