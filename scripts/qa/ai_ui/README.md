# QA giao diện Trợ lý AI + linh vật Ink Scout bằng Chrome thật (headless)

Ba bộ chạy bằng Chrome headless (CDP), dùng chung `lib.mjs` (máy chủ tĩnh, khởi chạy Chrome với hồ sơ tạm riêng, kết nối CDP) và
`companion_lib.mjs` (đo hình học/va chạm, kéo thả, dòng thời gian trạng thái, CPU/heap):

| Bộ | Dựng gì | Dùng để |
|---|---|---|
| `run.mjs` | `AiProvider` + `AiPanel` + `AiLauncher` + `/assistant` THẬT trong harness esbuild, linh vật tắt | giao diện chat: bố cục 320→1280, gửi/dừng/tạo lại, hạn mức, đổi tài khoản, focus, cuộn, Escape, ô soạn giãn, khối mã |
| `run_companion.mjs` | như trên + mã `AiCompanion` THẬT + asset linh vật thật (`web/public/mascot/`), máy chủ SSE giả có nhịp thời gian | linh vật: trạng thái theo vòng đời thật, va chạm, kéo thả, nhớ vị trí, giảm chuyển động, CPU, rò rỉ, inline `/assistant` |
| `run_real.mjs` | bản dựng **Next THẬT** (`next build` + `next start`), API thay bằng máy chủ giả chèn vào trang | header/footer/định tuyến/chunk lười/CSS thật, byte lúc nghỉ ở từng biến thể cờ, `/assistant` thật |

```bash
node scripts/qa/ai_ui/run.mjs                      # chat UI, toàn bộ (≈ 4 phút)
node scripts/qa/ai_ui/run.mjs --only "^layout"     # một nhóm kịch bản (regex theo id)
node scripts/qa/ai_ui/run_companion.mjs            # linh vật, toàn bộ (≈ 9 phút)
node scripts/qa/ai_ui/run_companion.mjs --only "^(trạng-thái|kéo-thả-chuột)$" --shots <thư mục>
node scripts/qa/ai_ui/run_real.mjs                 # bản dựng Next thật (cần dựng trước — xem đầu tệp run_real.mjs)
# mọi bộ nhận --shots <thư mục> (ảnh chụp từng trạng thái) và --json <tệp> (kết quả máy đọc được)
```

Cần: Node ≥ 22 (WebSocket có sẵn), `web/node_modules` (esbuild, next), và Chrome (`CHROME_PATH` nếu không ở
`C:/Program Files/Google/Chrome/Application/chrome.exe`). Chrome chạy với `--user-data-dir` tạm riêng, mỗi viewport một
browser context — **không đụng** cửa sổ Chrome đang dùng. Mã thoát 1 nếu có kiểm tra FAIL; dòng `info` chỉ báo số đo.

## Kiểm gì — `run.mjs`

| Nhóm | Nội dung |
|---|---|
| `layout`, `layout-states` | 320 / 360 / 390 / 430 / 768 / 1024 / 1280: không tràn ngang, không phần tử nào vượt khung nhìn, ô soạn thấy được, vùng chạm ≥ 24px (báo `info` nếu < 44px), ô nhập ≥ 16px (iOS không tự phóng to), khối mã rào ba dấu huyền cuộn ngang trong chính nó — ở các trạng thái: rỗng, hội thoại dài (từ/URL/mã không có khoảng trắng), hết lượt, lịch sử tiêu đề dài, popover cài đặt, lỗi + "Chưa gửi", chế độ viết |
| `behaviour-send-stop-regenerate` | Enter/Shift+Enter/ô trống, IME đang soạn không gửi, gửi, Tạo lại, Dừng giữa chừng |
| `behaviour-quota-and-errors` | Hết lượt của CHÍNH người dùng (kèm giờ làm mới, không phần trăm toàn site, "Chưa gửi", ô soạn khoá), hết công suất chung, `ai_busy` |
| `behaviour-resilience` | Luồng đóng sạch không có `done`/`error` không kẹt "đang trả lời"; Tạo lại sau khi mở hội thoại cũ từ lịch sử |
| `behaviour-account-switch` | Đăng xuất / đổi tài khoản trong cùng trang: không còn nội dung, hạn mức, cờ phiên của người trước |
| `behaviour-focus`, `behaviour-escape-close` | Desktop: mở panel → focus vào ô soạn; đóng → focus về nút mở; Escape đóng đúng MỘT lớp (popover trước, panel sau), không đóng khi đang gõ IME |
| `behaviour-composer-grow` | Ô soạn giãn theo nội dung tới max-height rồi cuộn trong ô, co lại khi xoá |
| `behaviour-scroll-anchor` | Cuộn lên đọc trong lúc stream thì khung không bị giật xuống đáy |
| `behaviour-reduced-motion` | `prefers-reduced-motion`: không còn hoạt ảnh đáng kể |
| `perf-idle-and-reopen` | Khi đóng chỉ 1 request `/access`; panel mở rỗng không request nền; mở/đóng 40 lần không rò DOM/heap; stream 600 từ không có long task > 200ms |

## Kiểm gì — `run_companion.mjs` (id kịch bản)

| Id | Nội dung |
|---|---|
| `cờ-tắt`, `tải-lười` | Cờ build 0: không phần tử/request/`localStorage` của linh vật; cờ 1: không request linh vật TRƯỚC khi trang tải xong, presence/sprite đi bộ chưa tải, ngân sách byte lúc nghỉ |
| `trạng-thái` | thinking→answering→success; Truyện: searching→thinking; Viết: writing; failover im lặng 3s + ping KHÔNG nháy lỗi; Dừng (khi chờ / khi stream); Tạo lại; lỗi cuối (giữ nguyên) và hồi phục; lỗi giữa chừng; 429 quá nhanh; mất mạng→offline; đóng giữa lúc stream; hết lượt→offline |
| `không-lộ-metadata` | Máy chủ giả CỐ TÌNH nhét tên nhà cung cấp/model/khe/vân tay khoá/hạn mức chung vào mọi khung SSE và thông điệp lỗi: DOM, thuộc tính, `localStorage` không được chứa |
| `vị-trí-va-chạm` | 1024 / 1280 / 1920 / 2560: không đè nút mở·Chat Dock·thanh phát·header·điều khiển panel, không che đích chạm (elementFromPoint), nằm trong khung nhìn — ở trạng thái nghỉ/dock/mini/panel mở/đóng |
| `kéo-thả-chuột`, `kéo-thả-chạm`, `đối-chứng-vuốt` | kéo/thả, kẹp biên, thả vào panel/nút mở, nhớ vị trí qua tải lại, đặt lại; chạm kéo không cuộn trang, vuốt nền vẫn cuộn (có phép đối chứng) |
| `đổi-kích-thước`, `xoay-màn-hình` | thu/phóng cửa sổ với vị trí đã nhớ ở rìa; xoay điện thoại ở `/assistant` |
| `giảm-chuyển-động` | ảnh tĩnh, không tải sprite, dời chỗ tức thì, gần như 0 vòng vẽ |
| `hiệu-năng-cpu`, `rò-rỉ`, `nền-trước-sau` | CPU lúc hoạt ảnh / yên lặng / ẩn / stream (trung vị, so với cơ sở cùng trang đóng băng CSS); ~70 chu kỳ mount-unmount/mở-đóng/stream/Dừng: listener, nút DOM, RAF/interval, heap, luồng SSE; tab ẩn dừng vẽ |
| `assistant-inline`, `tuyến-chương`, `công-tắc-tắt` | linh vật inline ở 320→1920 (không đè ô soạn, bàn phím ảo mô phỏng thu lại); `/chapters/*` không đứng nhà; người ngoài khán giả không thấy |

## Giới hạn (nói thẳng)

* Không có Safari/iOS thật và bàn phím ảo chỉ được MÔ PHỎNG (`visualViewport.height` giả): đo bằng Chrome desktop giả lập di động.
* Máy chủ giả nói đúng hợp đồng `/api/ai/*` nhưng không phải Appwrite/Gemini; hành vi phía máy chủ do
  `server/tests/test_ai_e2e_regression.py` kiểm. Failover phía máy chủ chỉ được mô phỏng bằng "im lặng dài + `: ping`" (đúng thứ client thấy).
* CPU đo bằng Chrome phần mềm (`--disable-gpu`): số tuyệt đối chỉ để so sánh tương đối giữa các trạng thái.
* Đây là công cụ QA thủ công, **không chạy trong CI** (CI không có bước dựng Chrome headless cho nó). Phần logic thuần (ánh xạ trạng thái,
  hình học, director, tách markdown, bộ con asset) được `node --test` khoá trong `web/tests/ai-companion.test.mjs` / `ai-markdown-lite.test.mjs`
  và CHẠY trong CI.
