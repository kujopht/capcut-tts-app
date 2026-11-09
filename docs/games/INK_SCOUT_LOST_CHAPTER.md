# Ink Scout: The Lost Chapter — Chương 0, Kho Lưu Trữ Bị Lãng Quên

Game hành động 2D (pixel-art, kiểu metroidvania) trong vũ trụ gốc của Fanfic World. **Một lát cắt dọc (vertical slice) hoàn chỉnh chơi được từ đầu đến cuối**: 11 phòng nối liền, 4 loại kẻ địch, 1 boss hai giai đoạn, 3 Mảnh Ký Ức, 1 khả năng di chuyển mở ra lối cũ (backtracking), 3 đường kết thúc.

> **Trạng thái:** sau cờ build `NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED` (mặc định **TẮT**). KHÔNG bật ở production khi chưa có chủ phê duyệt. Chưa merge, chưa deploy. Không đụng Appwrite/AI/Gemini/Alibaba/TTS/billing/linh vật Companion.

Game **không sao chép** nhân vật, bản đồ, kẻ địch, vũ khí, UI, âm thanh hay nghệ thuật của bất kỳ game nào; tên, lời thoại, cơ chế đều viết mới. Tài sản duy nhất tái dùng là ảnh linh vật Ink Scout có sẵn của site (`/mascot/ink-scout/master/states/idle.webp`) — làm chân dung HUD và ảnh trang giới thiệu, không sửa gì ở linh vật.

---

## 1. Chạy thử cục bộ (chính xác)

```bash
# 1) build với cờ BẬT (chỉ cho bản preview cục bộ; KHÔNG đặt cờ này trong workflow/wrangler)
set NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED=1
npm --prefix web run build
npm --prefix web run start -- -p 3100
# 2) mở  http://127.0.0.1:3100/entertainment            -> thẻ "Ink Scout: The Lost Chapter" -> Chơi ngay
#        http://127.0.0.1:3100/entertainment/ink-scout  -> trang chi tiết/khởi chạy trực tiếp
```

Bash: `NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED=1 npm --prefix web run build`. Chế độ dev (`npm run dev`) cũng chạy được nhưng số đo hiệu năng phải lấy từ `next start`.

Điều khiển: ← → / A D đi · Space nhảy (giữ lâu cao hơn) · J chém (3 lần liên tiếp = combo) · K Memory Pulse · Shift Margin Step · Esc tạm dừng. Cảm ứng: vùng trái trượt ◀ ▶, các nút ⤒ ⚔ ✦ ⇢.

Không có cờ (build mặc định): thẻ không hiện ở trang Giải trí, `/entertainment/ink-scout` chỉ là thông báo tĩnh "Game này chưa mở", không tải một byte mã game, `noindex`.

## 2. Kiến trúc

```
web/src/game/inkscout/
  core/       LÕI MÔ PHỎNG — TypeScript thuần, tất định, không DOM/Canvas/thời gian thực
    constants.ts  types.ts  rng.ts  tilemap.ts   hằng số cân chỉnh, kiểu, RNG có hạt giống, ô + va chạm AABB quét trục
    player.ts     bộ điều khiển di chuyển + Glyph Blade + Margin Step + Memory Pulse
    enemies.ts    4 máy trạng thái kẻ địch
    boss.ts       THE REDACTOR: lập lịch đòn (túi xáo trộn có hạt giống), giai đoạn, Memory Collapse
    rooms.ts      dữ liệu 11 phòng (ASCII địa hình + mảng thực thể)
    game.ts       vòng mô phỏng: phòng/cửa, chiến đấu, vật thể, chết/hồi sinh, kết thúc → `GameEvent`
    lore.ts       toàn bộ chữ (tiếng Việt)       save.ts   mô hình lưu + sanitize + giao diện SaveStore
  render/     Canvas 2D 384×216, sprite tạm vẽ bằng mã (actors/world/hud/fx/renderer)
  platform/   runtime (vòng lặp 60 Hz cố định + dọn dẹp), input (phím + chạm), audio (Web Audio tổng hợp), storage
  ui/         InkScoutLoader (tải lười) → InkScoutShell (menu → mở đầu → màn chơi) + StageOverlay + TouchControls + inkscout.css
web/src/app/entertainment/ink-scout/page.tsx   route (cờ tắt ⇒ thông báo tĩnh)
```

Quy tắc phân lớp (có test tĩnh canh): `core/` không import `render/ platform/ ui/`, không `Math.random`/`Date`/hẹn giờ/DOM. Mô phỏng bước **cố định 60 Hz** bằng bộ tích luỹ thời gian; render chạy theo nhịp màn hình (đã đo ở ~120 Hz: vẫn đúng 60 bước/giây). React chỉ nhận `UiSnapshot` rời rạc (đổi chế độ, lời thoại, ký ức...) — **không có cập nhật React theo từng khung**. HUD vẽ trong canvas.

Tải lười hai tầng: trang chủ/Giải trí không chứa mã game; route game chỉ tải vỏ giao diện (menu); runtime (mô phỏng + render + âm thanh) chỉ được `import()` khi bấm **Chơi/Tiếp tục**. `destroy()` gỡ sạch rAF, bộ nghe, AudioContext, canvas.

Tại sao không dùng Phaser: kiểm tra trước khi code — Phaser 3.90.0 `phaser.min.js` là **1.196 MB thô / 315 KB gzip**; toàn bộ game này tải thêm **~39 KB gzip** (xem §7). Mô phỏng thuần (không phụ thuộc engine) cho phép test tất định, bot chơi thử, và bộ giải khả năng tiếp cận — những thứ là trọng tâm của slice này.

## 3. Hệ thống

**Di chuyển** (đơn vị: px nội bộ, khung hình 60 Hz): chạy tối đa 1,65 px/khung; tăng/giảm tốc có hệ số quay đầu; nhảy biến thiên (nhả nút = cắt vận tốc), nhảy đầy cao ≈ 57 px (3,6 ô), xa ≈ 58 px; coyote 6 khung, jump buffer 7 khung, điều khiển trên không; knockback + 60 khung bất tử; hit-stop (3 khung thường / 5 khung đòn nặng, 5 khung khi bị trúng); rung màn hình có 3 mức (Tắt/Nhẹ/Đủ; mặc định Tắt nếu hệ điều hành bật "giảm chuyển động"); tạm dừng; hồi sinh sạch.

**Glyph Blade**: nhát mặt đất 1–2–3 (nhát 3 mạnh, sát thương 2), nhát trên không, nhát lướt (sau khi mở Margin Step). Mỗi mục tiêu trúng cộng **1 Ink** (tối đa 9).

**Memory Pulse** (3 Ink; 2 Ink khi có Ký Ức III): vòng sóng mở rộng — làm kẻ địch trong tầm choáng 120 khung (Broken 60), **lộ bệ glyph ẩn** 480 khung, hé lộ dòng chữ ẩn, xoá đạn của boss, phá mảnh Memory Collapse, ngắt đòn boss đang báo trước (có hồi chiêu 600 khung). Bán kính 56 px (80 px khi có Ký Ức II).

**Margin Step** (nhận ở Đền Lề Trang, giữa chương): lướt ngắn theo hướng đang giữ ≈ 54–66 px, 7 khung bất tử đầu, một lần mỗi cú nhảy trên không. Đây là **khả năng di chuyển duy nhất** (không bám tường/móc/lượn). Số đo thiết kế: nhảy thường vượt khe ≤ 4 ô, KHÔNG vượt khe 5 ô (80 px); nhảy + lướt vượt khe 5 ô — các test lõi canh số này.

**Kẻ địch (đúng 4 loại)** — mỗi loại có silhouette riêng, báo trước ≥ 20 khung, máy trạng thái nhỏ, hộp chạm nhỏ hơn thân (va chạm công bằng), phản ứng khi trúng, dọn tất định:
| Loại | Hành vi |
|---|---|
| **Scribble** (đi bộ) | tuần tra → thấy người chơi → báo trước 24 khung → lao ngắn → hồi phục (bị chém giữa báo trước thì bị ngắt) |
| **Torn Page** (bay) | lơ lửng → báo trước 30 khung (khoá mục tiêu ở 8 khung cuối) → bổ nhào → bay về |
| **Redaction Hound** (nhanh) | tuần tra → cúi 22 khung → lao thẳng tới 70 khung → trượt → hồi; kiểm tra nhảy/lướt |
| **Broken Character** (tinh nhuệ) | hình thể bất ổn, đuổi chậm, giơ tay báo trước 38 khung → đập → hồi; lời thoại khi gặp/nửa máu/chết |

**Boss THE REDACTOR** (80 máu): Người Gác cổ bị tha hoá — áo choàng giấy rách, mặt nạ có thanh bôi đen, **Revision Blade**.
- Giai đoạn 1 *Guardian*: Revision Slash (lao chém), Black Line (đường mực ngang → nhảy, hoặc cột dọc → bước ra), Margin Cut (hai sóng sát đất → nhảy), Rewrite (biến mất rồi hiện sau lưng, 24 khung nhìn thấy trước khi chém).
- Giai đoạn 2 *Corrupted Editor* (≤ 55% máu: khựng bất tử → Memory Collapse): thêm Delete (cột xoá cao toàn phòng), Broken Sentence (đạn glyph), Revision Rush (3 cú lao 1-2-3), và **Memory Collapse** hai lần (bốn mảnh ký ức che chắn boss).
- **Lore tương tác với cơ chế**: số Ký Ức đã nhớ làm nứt đúng chừng ấy mảnh (nứt ⇒ vỡ sau 1 nhát), Pulse phá hết mảnh trong tầm và làm boss choáng chịu ×1,5 sát thương, và lời thoại của Redactor đổi theo (≥ 2 ký ức: lộ sự thật).
- Công bằng: mọi đòn nguy hiểm có báo trước ≥ 24 khung (0,4 s); hướng/mục tiêu khoá ở 8 khung cuối; sát thương đến từ vùng nguy hiểm tường minh (không sát thương chạm thân); chống kẹt (Memory Collapse tự tan sau 12 s). Xem §6 cho bằng chứng bot chậm phản ứng.

**Lore & kết thúc**: Ký Ức I *Tác Giả* (Kho sinh ra để giữ truyện dở dang) · II *Sụp Đổ* (bản thảo chồng chất sinh ra nhiễu loạn) · III *Người Gác* (Redactor từng là kẻ khâu lại các trang rách). Mỗi ký ức có thưởng cơ chế: **I: +1 máu tối đa · II: Pulse rộng hơn · III: Pulse rẻ hơn**. Câu hỏi chủ đề: *"một câu chuyện chưa kết thúc có còn đáng được tồn tại?"* Lời thoại ngắn qua Echo, biển ghi chú, chữ ẩn (Pulse), không có tường chữ.
- 0–1 ký ức ⇒ kết thúc **cơ bản** (Kho còn, nhiễu loạn chưa giải) · 2 ký ức ⇒ kết thúc cơ bản + thoại/đoạn sự thật thêm · 3 ký ức ⇒ lựa chọn **XOÁ** (tiêu diệt hẳn tàn dư) hoặc **KHÔI PHỤC** (viết lại thành Người Gác → *The Curator*, móc cho chương sau).

## 4. Bản đồ (11 phòng) và tiến trình

```
Cửa Kho ─ Đại Sảnh ─ Phòng Vọng (Ký Ức I: Pulse lộ bệ glyph theo từng chặng)
             │  ╲_ (gờ cao, khe 5 ô: cần Margin Step) ─ Phòng Ký Ức Bí Mật (Ký Ức III)
             ▼ (hố)
         Dãy Kệ Dưới ─ Đền Lề Trang ★Margin Step ─[khe 5 ô]─ Chồng Phong Ấn (Ký Ức II, tuỳ chọn)
                                                              │
                          Sảnh Bị Biên Tập (thanh Redaction, khe 5 ô) ─ Phòng Dấu Trang ─ Đấu Trường ─ Phòng Kết Thúc
```
- Vòng chơi: khám phá → chiến đấu/nhảy → Ký Ức I (Pulse) → **Margin Step** → qua cổng khe 5 ô → **quay lại** gờ cao Đại Sảnh để vào Phòng Bí Mật → Ký Ức III → boss → kết thúc theo số ký ức.
- Margin Step mở ra ≥ 1 lối trước đó không vào được: `exit:secret` (Đại Sảnh), `exit:sealed`/Ký Ức II (Đền Lề → Chồng Phong Ấn), `exit:bookmark` (Sảnh Bị Biên Tập) — **test chứng minh từng cổng chặn khi thiếu khả năng và mở khi có** (`ink-scout-reach.test.mjs`).
- Dấu Trang (điểm hồi sinh, hồi đầy máu): Đại Sảnh, Đền Lề, Chồng Phong Ấn, Sảnh Bị Biên Tập, Phòng Dấu Trang (ngay trước boss). Cửa đấu trường khoá khi boss thức, mở khi boss ngã.
- Hố gai/rơi khỏi bản đồ: mất 1 máu và về chỗ an toàn gần nhất (không mất phòng, không chết liên tục).

## 5. Lưu & tích hợp Fanfic

- **Chỉ cục bộ**: một khoá `fanfic.inkscout.lostchapter.v1` trong `localStorage` (checkpoint, Margin Step, ký ức, boss đã hạ, kết thúc, cài đặt, thời gian chơi, số lần ngã, thời gian nhanh nhất). Mọi lần đọc qua `sanitizeSave` (JSON hỏng/độc không làm sập, tiến trình mâu thuẫn bị đưa về điểm hợp lệ). Truy cập `localStorage` bọc try/catch: bị chặn thì game vẫn chơi và báo "không lưu được". Giao diện `SaveStore` bất đồng bộ để sau này thay bằng lưu đám mây mà lõi không đổi. **Không Appwrite, không schema, không mạng.**
- Trang Giải trí: thẻ (chế độ, người chơi, thời lượng, "Không tính XP") chỉ nối vào danh sách khi cờ bật; trang chi tiết có Chơi/Tiếp tục, Chơi lại (có xác nhận), điều khiển, cài đặt, quay về Giải trí; phần mở đầu 3 trang; mở game thì tạm dừng lời đọc truyện đang phát (cùng quy ước với các game 3D).

## 6. Kiểm thử

| Tệp (`web/tests/`) | Số test | Nội dung |
|---|---|---|
| `ink-scout-core.test.mjs` | 29 | gia tốc/giảm tốc, nhảy biến thiên, coyote, jump buffer, knockback + i-frames, Margin Step, số đo thiết kế, combo, Ink, Pulse, FSM 4 kẻ địch, ký ức, lưu/tải, chết/hồi sinh, gai, **tất định từng khung**, tính hợp lệ dữ liệu phòng |
| `ink-scout-boss.test.mjs` | 11 | báo trước ≥ 24 khung, không sát thương lúc báo trước, bộ lập lịch (không lặp, đúng tập, tất định theo hạt giống), giai đoạn, Memory Collapse (nứt theo ký ức, Pulse), chống kẹt, **bot chậm phản ứng 20 khung thắng ở 6 hạt giống** |
| `ink-scout-reach.test.mjs` | 6 | **bộ giải khả năng tiếp cận**: vật thể đạt được, cổng Margin Step/Pulse thật sự chặn, ký ức tuỳ chọn, **không soft-lock (đồ thị trạng thái liên thông mạnh)** |
| `ink-scout-playthrough.test.mjs` | 4 | bot vòng kín qua toàn chương (3 ký ức + KHÔI PHỤC; đường tối thiểu; XOÁ; 2 ký ức; lưu giữa chừng rồi tải) |
| `ink-scout-input.test.mjs` | 9 | phím, chạm đa ngón, chặn cuộn, không kẹt phím, gỡ sạch bộ nghe |
| `ink-scout-runtime.test.mjs` | 9 | vòng đời runtime với window/canvas giả: bước cố định 60 Hz ở 60/120/144 Hz, chống xoáy ốc chết, tự tạm dừng khi tab ẩn/mất tiêu điểm, `destroy()` gỡ sạch rAF + bộ nghe (40 vòng không tích luỹ), UI chỉ cập nhật khi đổi trạng thái, móc QA chỉ khi có cờ |
| `ink-scout-static.test.mjs` | 12 | cờ mặc định tắt + không lọt vào cấu hình triển khai, tải lười, không eval/HTML động/mạng/Appwrite, lõi tất định & phân lớp, `<Link prefetch={false}>`, CSS tiền tố, nút chạm ≥ 56 px, a11y, không dùng tên/tài sản game khác |

Bộ giải (`tests/helpers/nav.mjs`): dựng nút đứng trên mọi mặt sàn, mô phỏng hàng trăm macro bằng chính `Player`+`TileMap` thật, chỉ giữ cạnh **bền** (đáp xuống cùng chỗ khi lệch xuất phát ±1,5 px và lệch thời điểm lướt ±1 khung). Bot (`tests/helpers/bot.mjs`): đi theo đồ thị đó, đánh bằng chiến thuật người thật (đứng ngoài tầm khi kẻ địch báo trước, nhảy qua cú lao, chém lúc nó hồi phục, Pulse để choáng), đấu boss với **độ trễ phản ứng 15–25 khung** (chỉ thấy trạng thái boss của N khung trước rồi ngoại suy theo lịch báo trước).

QA trình duyệt thật (Chrome qua CDP; bộ script ở `scripts/qa/ink_scout/`, chạy bằng `python scripts/qa/ink_scout/qa_*.py` sau khi build+start như §1): `qa_smoke`, `qa_input` (phím thật), `qa_playthrough` (bot điều khiển vòng lặp rAF + canvas + overlay React thật), `qa_mobile` (chạm thật 320/360/390/430 dọc và ngang), `qa_lifecycle`/`qa_leak2` (vào/ra nhiều lần, rò rỉ, lưu/tải, localStorage hỏng, tab ẩn, Link/Back), `qa_bundle` (kích thước gói theo trang), `qa_flag_off` (build mặc định).

Móc QA: `window.__INK_QA__ = true` đặt **trước khi** tải trang thì runtime phơi `window.__INK_QA_API__` (chính mô phỏng cục bộ + bộ điều khiển đầu vào) cho bot/test. Người chơi thường không có cờ này; nó không phơi API quản trị, khoá hay dữ liệu máy chủ.

**Đánh giá độc lập chéo họ model (Codex, `ORDINARY_REVIEW`)**: 2 vòng trên toàn bộ lõi/runtime/giao diện → 15 phát hiện (chết sau khi chạm mốc kết thúc/Dấu Trang ở khung chí mạng; Memory Collapse lần hai bung không báo trước; Torn Page kẹt trạng thái không lối ra khi bị chém lúc báo trước; Hound lao tiếp với vận tốc hất lùi; cửa đấu trường khoá sớm; Enter/Space bị nuốt khỏi nút hộp thoại; âm thanh cảm ứng không mở khoá; nút đi 2 ngón; hit-stop sót sau chết; lời thoại hết hạn khi tạm dừng; lựa chọn cuối một chạm; khoá cuộn ở trang lỗi; nhạc boss bật lại khi boss đang tan). **14 cái đã sửa và có test hồi quy; 1 cái là hành vi cố ý** (tải một lưu đã hoàn thành cho phép xem lại kết thúc từ Phòng Dấu Trang). Vòng 3 (diff các bản sửa) không dùng được Codex (hết hạn mức tài khoản — không mua thêm) và Antigravity headless bị chặn quyền lệnh, nên được đọc diff thủ công; không tìm thấy hồi quy.

## 7. Hiệu năng & kích thước

Số đo trên bản build production (`next start`), Chrome headless:
| Hạng mục | Kết quả |
|---|---|
| JS trang chủ / Giải trí (gzip) | 248,4 KB / 244,7 KB — **không chunk nào chứa mã game** (cờ bật, đã quét nội dung từng chunk) |
| Route game (menu), thêm | +10,4 KB gzip (28,2 KB thô) vỏ giao diện + ~3 KB CSS |
| Runtime, tải khi bấm Chơi | **28,9 KB gzip (87,7 KB thô)** — mô phỏng + render + âm thanh + input |
| So với Phaser 3.90.0 | 314,9 KB gzip chỉ riêng engine |
| Khởi tạo (bấm Chơi/Xuống Kho → runtime sẵn sàng) | ≈ 52 ms (localhost) |
| Khung hình | trung bình 9,6 ms, p99 9 ms (rAF ≈ 104 Hz headless); mô phỏng đúng 60 bước/s |
| CPU khi chơi / sau khi rời | script ≈ 65 ms/s (6,5%) khi chơi; sau khi rời về menu ≈ cùng mức nền của trang (không còn rAF/hẹn giờ của game) |
| Rò rỉ qua 40 vòng vào/ra | bộ nghe `window/document` hằng số, rAF đang chờ = 0, DOM node không tăng, heap tăng ≈ 0,006 MB/vòng (phẳng dần), `instances` luôn = 1 khi chơi |

## 8. Bảo mật

Không `eval`/`new Function`/HTML động/`innerHTML`/mạng/WebSocket/worker; không khoá, token, API quản trị hay Appwrite; dữ liệu duy nhất ra vào là `localStorage` (qua `sanitizeSave`). Test tĩnh (`ink-scout-static.test.mjs`) canh các điều này.

**Lưu ý cho tương lai — game do người dùng tạo (UGC):** slice này chạy mã của chính Fanfic World trên origin của site. Nếu sau này cho phép game/mod do người dùng viết (script, asset tuỳ ý), **bắt buộc** chạy chúng trong sandbox riêng: iframe `sandbox` không `allow-same-origin`, **origin khác** (không chung cookie/localStorage/token với site), CSP chặt, giao tiếp chỉ qua `postMessage` có lược đồ, không đưa khoá/API quản trị/Appwrite vào đó. Không bao giờ nạp mã người dùng vào cùng origin hoặc `eval`.

## 9. Tài sản: tạm thời vs sẵn sàng sản xuất

| Thành phần | Trạng thái |
|---|---|
| Sprite nhân vật/kẻ địch/boss/địa hình/nền/HUD | **TẠM** — vẽ bằng mã (nguyên bản, nhất quán bảng màu); thay bằng sprite sheet thật mà không đổi lõi |
| Chân dung HUD + ảnh trang giới thiệu | Tái dùng ảnh Ink Scout sản xuất có sẵn của site |
| Âm thanh | **TẠM** — tổng hợp Web Audio (không tệp, không bản quyền); tắt tiếng chơi như bình thường; mở AudioContext chỉ sau cử chỉ người dùng |
| Lõi mô phỏng, dữ liệu phòng, boss, lore, lưu, giao diện, nút chạm | Sẵn sàng cho slice; lore là bản nháp tiếng Việt cần biên tập |

## 10. Giới hạn đã biết

- Đồ hoạ/âm thanh còn là bản tạm; chưa có nhạc nền thật; chưa có bản đồ nhỏ (minimap).
- Thời lượng: bot "speedrun" qua toàn chương ≈ 3,0–3,3 phút (đường tối thiểu ≈ 1,7 phút). **Ước lượng** lần chơi đầu của người thật ≈ 15–25 phút (khám phá, đọc, quay lại lấy ký ức, 2–4 lần thử boss) — đây là ước lượng từ mô hình, chưa đo trên người thật; nằm ở cận dưới của mục tiêu 20–35 phút.
- Độ khó boss được cân bằng bằng bot chậm phản ứng (thắng 6/6 hạt giống, 0–1 lần ngã) — bot là đường cận trên của kỹ năng; người thật chậm hơn và sẽ ngã nhiều hơn. Cần playtest người thật.
- Không có gamepad; không có chọn phím tuỳ ý; chưa có bảng xếp hạng/XP/lưu đám mây (cố ý ngoài phạm vi).
- Trong lúc tạm dừng, đồng hồ thời gian chơi dừng; đọc hộp ký ức không tính vào thời gian.

## 11. Bước tiếp theo (đề xuất)

1. Chủ xem bản preview (§1), chơi thử thật trên máy + điện thoại, cho phản hồi độ khó/nhịp.
2. Thay sprite tạm bằng sprite sheet thật; thêm nhạc/SFX thật có giấy phép; biên tập lại lời thoại.
3. Sau khi chủ duyệt: thêm biến môi trường cờ vào quy trình deploy **như một bước riêng có chủ đích** (hiện CỐ Ý không có trong workflow/wrangler), kèm kiểm tra rollback giống linh vật Companion.
4. Chương 1 chỉ làm sau khi slice này được duyệt (lưu đám mây, bản đồ nhỏ, gamepad nếu muốn).
