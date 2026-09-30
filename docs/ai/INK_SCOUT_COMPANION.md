# Ink Scout — linh vật đi cùng Trợ lý AI

Linh vật đã duyệt **Concept A — Ink Scout** làm bạn đồng hành hình ảnh của Fanfic AI Assistant. Chỉ là lớp HIỂN THỊ: không đổi backend, provider, định tuyến hay hạn mức AI.

Cờ: `NEXT_PUBLIC_AI_COMPANION_ENABLED` (build-time), **mặc định TẮT**.

| Trợ lý AI | Cờ linh vật | Kết quả |
|---|---|---|
| TẮT | bất kỳ | Không linh vật (`AI_COMPANION_ENABLED = AI_ASSISTANT_ENABLED && …`) |
| BẬT | TẮT | Giao diện AI bình thường; **không một byte** mã/asset linh vật được TẢI (`loader=null`; Turbopack vẫn xuất tệp chunk lười ~3 KB gzip nhưng không bao giờ được yêu cầu) |
| BẬT | BẬT | Linh vật bật |

Nguồn: dự án canonical `C:\Users\nguye\Projects\Fanfic-World-Mascot` (bản GIẢI NÉN, không dùng ZIP 73 MB).

## 1. Kiểm kê bộ asset gốc

| Hạng mục | Giá trị |
|---|---|
| Tổng giải nén (`mascot/`) | 74,3 MB (74 314 576 B), 264 tệp — ZIP 76,5 MB (76 548 467 B) |
| Định dạng | 106 PNG (52,1 MB), 88 WebP (8,9 MB), 66 JSON (11,5 MB, gồm Lottie nhúng PNG), 1 JS runtime |
| Theo thư mục | `sources/` 31,4 MB (sheet sinh ảnh) · `animations/` 13,0 MB · `transitions/` 11,8 MB · `master/` 5,7 MB · `expressions/` 4,2 MB · `stickers/` 4,1 MB · `poses/` 2,2 MB · `runtime/` 13 KB |
| Lớn nhất | `sources/stickers.png` 2,4 MB, `sources/expressions.png` 2,2 MB, `sources/sleepy.png` 2,1 MB … (toàn bộ top-12 là sheet nguồn) |
| Hoạt ảnh | mỗi hoạt ảnh có `sprite.webp` (atlas 320 px), `sprite.png`, `sprite.json`, `poster.png`, `animation.json` (Lottie ảnh), `animated.webp` |
| Trạng thái (10) | idle, hover(wave), listening, thinking, searching, writing(typing), answering(talking), success, error, offline(sleepy) |
| Chuyển động (8) | hop-left, hop-right, walk, jump-onto-panel, sit-down, stand-up, peek-out, return-home |
| Sticker | 12 × 512×512 (WebP 53–69 KB, PNG 253–305 KB) |

## 2. Bộ con WEB (`web/public/mascot/ink-scout/`)

Dựng bằng `python scripts/mascot/build_ink_scout_web.py` (`--check` phát hiện lệch). Chỉ gồm:

* runtime `ink-scout.js` **nguyên từng byte** (sha256 trong `SUBSET.json`; `.gitattributes` `-text` chặn đổi xuống dòng);
* atlas WebP ĐÃ TỐI ƯU của bộ gốc cho 10 trạng thái + 8 chuyển động — chép nguyên, không encode lại/tô lại/lật;
* 9 poster tĩnh WebP (giảm chuyển động) + 2 tư thế (`sitting-edge`, `peeking`) mà runtime hiện sau sit-down/peek-out;
* `manifest.json` rút gọn (chỉ khoá runtime đọc; bỏ PNG/Lottie/animated-WebP; poster hoạt ảnh trỏ về WebP tĩnh).

Tệp TRÙNG từng byte trong bộ gốc chỉ phục vụ MỘT bản: `jump-onto-panel` ≡ `hop-right`, `return-home` ≡ `walk`.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Dung lượng | 74,3 MB (bộ gốc) | **2,22 MB** (2 222 532 B, 3,0%) — 28 tệp + manifest 17,9 KB |
| Ngân sách | — | ≤ 2,7 MB (test + trình dựng cưỡng chế) |

Theo loại: sprite trạng thái 750 KB · sprite chuyển động 870 KB · poster tĩnh 493 KB · tư thế 79 KB · runtime 13 KB.

## 3. Ánh xạ trạng thái (sự kiện THẬT)

`companionState.ts::mapCompanionState` — hàm thuần, ưu tiên từ trên xuống:

| Trạng thái trợ lý (`AiProvider`) | Ink Scout |
|---|---|
| `availability=false` / `!enabled` / mất mạng / lỗi `network_error`,`ai_not_enabled`,`disabled_by_admin`,`ai_no_provider` | offline |
| `streaming` + chưa có token + chế độ Truyện (máy chủ đang truy chương/thư viện) hoặc có tìm web | searching |
| `streaming` + chưa có token | thinking |
| `streaming` + có token + chế độ Viết | writing |
| `streaming` + có token | answering |
| lỗi lượt vừa rồi (panel mở) | error |
| lượt vừa xong `status:"complete"` (sự kiện) | success → phát một lần → listening/idle (`animationcomplete`; giảm chuyển động: 1,5 s) |
| con trỏ trên linh vật ở vị trí nhà | hover (phát một lần) |
| panel mở / đang ở `/assistant` / đang gõ | listening |
| đóng | idle |
| Dừng tạo sinh | listening (không success) |
| Hội thoại mới | listening (không giả thành công) |

"searching": frontend V1 không gửi `use_web_search` → không có tín hiệu tìm web thật; dùng pha trước token của chế độ Truyện (tín hiệu thật: máy chủ đang dựng ngữ cảnh từ chương). Tham số `webSearch` để sẵn.

## 4. Hành vi

**Desktop ≥1024 px** — host `position:fixed` ngay trái nút mở trợ lý, dịch theo Chat Dock (`useChatDockOffset`), z-index 54 (dưới Chat Dock 55, nút/panel AI 56).

* Panel mở → `jump-onto-panel` lên mép TRÊN panel (ngoài panel — không che chữ, nút Gửi, nút Đóng), phía trái (xa nút Đóng); luôn dưới đáy `.site-header`. Màn thấp → đứng cạnh trái panel; không còn chỗ → ẩn trong lúc panel mở.
* Đang ngồi + chỉ lắng nghe → `sit-down` (giữ tư thế ngồi); làm việc → đứng dậy phát trạng thái; panel đóng → `stand-up` (nếu đang ngồi) + `return-home`.
* Tuyến có điều khiển riêng (`/chapters/*`, `/messages`) → không đứng "nhà" khi panel đóng.
* `CompanionDirector`: trạng thái MỚI NHẤT thắng, không cắt ngang chuyển động (runtime `setState` huỷ motion), mở/đóng dồn dập chỉ đi tới đích cuối.

**`/assistant` (mọi bề rộng)** — linh vật nằm TRONG luồng nội dung giữa đầu trang và hội thoại → không bao giờ đè ô soạn; `visualViewport` thấp (bàn phím ảo) → thu lại. **≤1023 px ngoài `/assistant`: không linh vật nổi.**

**Tiết kiệm** — nạp LƯỜI: cờ tắt 0 byte; cờ bật mà chưa đăng nhập/trợ lý không khả dụng → không tải chunk; đứng "nhà" → tải khi trình duyệt rảnh (`requestIdleCallback`, ≤4 s); panel mở / `/assistant` → tải ngay. Runtime: cache ≤3 ảnh giải mã (giữ nguyên), dừng khi tab ẩn / ngoài màn hình; ẩn bằng CSS → `setPaused(true)`.

**Trợ năng & điều khiển** — `aria-hidden`, không tabindex, không âm thanh, không tự mở trợ lý; `pointer-events` chỉ bật ở vị trí nhà (hover). Popover cài đặt của trợ lý: **Ẩn Ink Scout** / **Giảm chuyển động** (localStorage `fas.aiCompanion.v1`); `prefers-reduced-motion` của hệ điều hành luôn thắng (ảnh tĩnh, dời chỗ tức thì, không tải poster PNG).

**Không lật** — không `scaleX(-1)` ở mã, CSS hay runtime (test cưỡng chế). `hop-left` của bộ gốc KHÔNG phải bản lật (khung 0 trùng `hop-right`, khác dần theo quãng di chuyển; so với bản lật lệch 15,4%).

## 5. Sticker (CHƯA tích hợp)

12 tệp `mascot/stickers/<id>.{png,webp}`, 512×512. Đề xuất gói cho kiến trúc `server/messaging/stickers.py`:

```json
{ "pack_id": "inkscout", "name": "Ink Scout", "unlock": {"kind": "free"},
  "stickers": [
    {"id": "inkscout.hello", "asset_key": "inkscout/hello.webp", "alt": "Xin chào"},
    {"id": "inkscout.lol", "asset_key": "inkscout/lol.webp", "alt": "Cười lớn"},
    {"id": "inkscout.love", "asset_key": "inkscout/love.webp", "alt": "Thương quá"},
    {"id": "inkscout.wow", "asset_key": "inkscout/wow.webp", "alt": "Wow"},
    {"id": "inkscout.thinking", "asset_key": "inkscout/thinking.webp", "alt": "Để nghĩ đã"},
    {"id": "inkscout.angry-cute", "asset_key": "inkscout/angry-cute.webp", "alt": "Dỗi"},
    {"id": "inkscout.sleepy", "asset_key": "inkscout/sleepy.webp", "alt": "Buồn ngủ"},
    {"id": "inkscout.gg", "asset_key": "inkscout/gg.webp", "alt": "GG"},
    {"id": "inkscout.congratulations", "asset_key": "inkscout/congratulations.webp", "alt": "Chúc mừng"},
    {"id": "inkscout.thank-you", "asset_key": "inkscout/thank-you.webp", "alt": "Cảm ơn"},
    {"id": "inkscout.confused", "asset_key": "inkscout/confused.webp", "alt": "Bối rối"},
    {"id": "inkscout.facepalm", "asset_key": "inkscout/facepalm.webp", "alt": "Hết nói nổi"}
  ] }
```

WebP 512 px (~60 KB) đủ cho bong bóng chat; hiển thị 96–128 px CSS (2×–4× mật độ). PNG giữ trong bộ gốc làm bản lưu trữ.

## 6. Điểm không nhất quán thừa hưởng (ảnh raster sinh)

* Bộ gốc tự khai: không có rig vector/Rive; nét và tỉ lệ thay đổi nhẹ giữa các khung/khung nhìn vẽ lại độc lập (`qa/validation.json`, `design-notes.txt`).
* `jump-onto-panel` dùng lại NGUYÊN hoạt ảnh `hop-right` (trùng từng byte) — không có hoạt ảnh "nhảy lên panel" riêng.
* `return-home` dùng lại NGUYÊN `walk`.
* `hover` không có poster tĩnh riêng (manifest trỏ về poster `answering`).
* Atlas `hop-left/right` 16 ô nhưng chỉ 10 khung duy nhất (6 ô trống).
