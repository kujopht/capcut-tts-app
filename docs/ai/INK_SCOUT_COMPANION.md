# Ink Scout — linh vật đi cùng Trợ lý AI

Linh vật đã duyệt **Concept A — Ink Scout** làm bạn đồng hành hình ảnh của Fanfic AI Assistant. Chỉ là lớp HIỂN THỊ: không đổi backend, provider, định tuyến, hạn mức hay Appwrite.

Cờ: `NEXT_PUBLIC_AI_COMPANION_ENABLED` (build-time), **mặc định TẮT**. Production: biến repository `PRODUCTION_AI_COMPANION_ENABLED` — hiện `0`, và **chỉ Owner được bật** (§10).

| Trợ lý AI | Cờ linh vật | Kết quả |
|---|---|---|
| TẮT | bất kỳ | Không linh vật (`AI_COMPANION_ENABLED = AI_ASSISTANT_ENABLED && …`) |
| BẬT | TẮT | Giao diện AI bình thường; **không một byte** mã/asset linh vật được TẢI: không chunk, không request `/mascot/`, không khoá `localStorage` (đo trên bản dựng Next thật, §8) |
| BẬT | BẬT | Linh vật bật |

Nguồn: dự án canonical `C:\Users\nguye\Projects\Fanfic-World-Mascot` (bản GIẢI NÉN, v**1.3.0** — không dùng ZIP). Runtime là bản ĐÃ DUYỆT, chép nguyên từng byte; web không sửa, không viết lại engine.

## 1. Bộ con WEB (`web/public/mascot/ink-scout/`, v1.3.0)

Dựng bằng `python scripts/mascot/build_ink_scout_web.py` (`--check` phát hiện lệch; test `ai-companion.test.mjs` cưỡng chế). Gồm: 4 runtime (`ink-scout.js`, `-walk-rig.js`, `-physics.js`, `-presence.js`) **nguyên từng byte** (sha256 trong `SUBSET.json`; `.gitattributes` `-text`); atlas WebP ĐÃ TỐI ƯU của bộ gốc cho 10 trạng thái + 8 chuyển động + 2 sprite đi bộ có hướng (`walk-left`/`walk-right`, hai bản vẽ ĐỘC LẬP — không bao giờ lật); 9 poster tĩnh (giảm chuyển động); 6 tư thế (`sitting-edge`, `peeking`, 4 tư thế vật lý); các mảnh rig đi bộ (PNG — bộ gốc không có WebP cho chúng); `manifest.json` rút gọn. Chép nguyên, không encode lại/tô lại/lật. Tệp trùng từng byte trong bộ gốc chỉ phục vụ MỘT bản (`jump-onto-panel` ≡ `hop-right`, `return-home` ≡ `walk`, `near-boot.png` ≡ `far-boot.png`).

| Hạng mục | Trước khi sửa (v1.0, PR #238) | Sau khi sửa (v1.3.0) |
|---|---|---|
| Bộ gốc | 74,3 MB | 94,7 MB (94 748 902 B) |
| Bộ con web | 2,22 MB — 28 tệp + manifest | **3,70 MB** (3 697 821 B, 3,9% bộ gốc) — 54 tệp + manifest 23,8 KB |
| Ngân sách | ≤ 2,7 MB | ≤ 4,1 MB (test + trình dựng cưỡng chế) |
| Tính năng runtime | 1 runtime, không kéo thả, không đi bộ | + physics (kéo thả, rơi, đáp), đi bộ có hướng, presence (hover/xoa đầu) |

Theo loại: sprite trạng thái 750 KB · sprite chuyển động 870 KB · sprite đi bộ 1 186 KB · poster tĩnh 493 KB · mảnh rig 163 KB · tư thế 175 KB · runtime 38 KB. **Tải lười**: sprite đi bộ/nhảy chỉ được tải khi linh vật thật sự di chuyển; presence chỉ khi con trỏ vào linh vật.

## 2. Ánh xạ trạng thái (sự kiện THẬT)

`companionState.ts::mapCompanionState` — hàm thuần, ưu tiên từ trên xuống:

| Trạng thái trợ lý (`AiProvider`) | Ink Scout |
|---|---|
| `availability=false` / `!enabled` / mất mạng | offline (sleepy) |
| lỗi `network_error`, `ai_not_enabled`, `disabled_by_admin`, `ai_no_provider`, **`ai_budget_exhausted`** | offline (sleepy) |
| `streaming` + chế độ Truyện + **chưa nhận `meta`** (máy chủ đang dựng ngữ cảnh: truy chương/thư viện) hoặc có tìm web | searching |
| `streaming` + chưa có token (sau `meta`: chờ nhà cung cấp, **kể cả failover giữa các slot**) | thinking |
| `streaming` + có token + chế độ Viết | writing |
| `streaming` + có token | answering |
| lỗi lượt vừa rồi (panel mở): `ai_provider_unavailable`, `ai_provider_interrupted`, `ai_rate_limited`, `ai_busy`… | error (giữ nguyên tới lượt sau) |
| lượt vừa xong `status:"complete"` (sự kiện) | success → phát một lần → listening/idle |
| con trỏ trên **chính linh vật** hoặc **nút mở trợ lý** khi đứng nhà | hover (vẫy tay, một lần) |
| panel mở / đang ở `/assistant` | listening |
| đóng | idle |
| Dừng tạo sinh | listening (không success, không error) |

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Hết lượt hôm nay (`ai_budget_exhausted`) | `error` (mặt bối rối với người chỉ vừa chạm hạn mức) | `offline` (sleepy — "AI không sẵn sàng", HANDOFF §6), banner của panel đã nói rõ giờ làm mới; không lộ số liệu chung |
| Hỏi quá nhanh (`ai_rate_limited`) | `error` | `error` (không đổi — lượt bị từ chối do thao tác vừa rồi) |

**Failover phía máy chủ không bao giờ hiện thành lỗi.** Server chuyển slot trước token đầu, nên client chỉ nhận `meta > delta… > usage > done` (có thể có nhịp `: ping`). Linh vật đi `thinking → answering → success`. Chỉ sự kiện `error` cuối cùng (mọi slot đều hỏng, hết hạn mức…) mới hiện `error`. QA trình duyệt thật: khoảng im lặng 3 giây + `: ping` ⇒ `listening>thinking>answering>success>listening`, runtime không bao giờ phát `error`/`offline`.

"searching": frontend V1 không gửi `use_web_search`. Tín hiệu thật là khoảng **trước `meta`** ở chế độ Truyện (`AiProvider.responseStarted` đổi thành `true` khi `meta` về). Tham số `webSearch` để sẵn.

## 3. Hành vi và tương tác

**Desktop ≥1024 px (nổi)** — khung `position:fixed` ngay trái nút mở trợ lý (`right:74px; bottom:88px`), dịch theo Chat Dock (`useChatDockOffset`) và thanh phát (`.mini`), z-index 54 (dưới Chat Dock 55, nút/panel AI 56 ⇒ khi chồng lấn, nút Gửi/Dừng/Đóng/Lịch sử/điều hướng LUÔN thắng).

* Panel mở → `jump-onto-panel` lên mép TRÊN panel (ngoài panel, sát góc trái xa nút Đóng); luôn dưới đáy `.site-header`. Màn thấp → đứng cạnh trái panel; không còn chỗ → ẩn trong lúc panel mở. Đang ngồi + lắng nghe → `sit-down`; làm việc → đứng dậy; đóng → `stand-up` + `return-home`.
* **Kéo thả (chuột + chạm)** bằng physics của bộ gói: cầm → rơi theo trọng lực → đáp. Biên chỉ cho đi sang TRÁI nhà (không bao giờ chui xuống dưới nút mở/Chat Dock) và không lên trên đáy header. Thả vào vùng cấm (panel, nút mở, Chat Dock, thanh phát) → `judgeLanding` đưa về chỗ ngồi/nhà (có test thuần). Cầm không bị giật khỏi tay: `CompanionDirector.hold()` đóng băng mọi lệnh tới runtime tới khi thả, rồi áp lại trạng thái MỚI NHẤT.
* **Nhớ vị trí**: thả hợp lệ trên sàn → `homeX` vào `localStorage` `fas.aiCompanion.v1` (số ≤ 0 đã kẹp, giá trị rác → mặc định). Mỗi lần dùng kẹp lại theo bố cục HIỆN TẠI (thu cửa sổ, đổi bề rộng). **Đặt lại vị trí** trong popover cài đặt. `CompanionDirector.rehome()` khôi phục vị trí đã nhớ kể cả khi director đang bận áp trạng thái đầu tiên (lỗi chạy đua phát hiện bằng QA trình duyệt: trước đây có khi linh vật đứng ở nhà mặc định dù đã nhớ chỗ khác).
* Bấm/chạm nhẹ không kéo → vẫy tay/xoa đầu (presence). Tuyến có điều khiển riêng ở góc dưới (`/chapters/*`, `/messages`) → không đứng nhà khi panel đóng.

**`/assistant` (mọi bề rộng, kể cả điện thoại)** — linh vật INLINE nằm TRONG luồng nội dung giữa đầu trang và hội thoại ⇒ không bao giờ đè ô soạn; kéo thả ngang trong dải của chính nó; `visualViewport` thấp (bàn phím ảo) → thu lại. **≤1023 px ngoài `/assistant`: không linh vật nổi, và không tải chunk của nó** (cổng kiểm media desktop trước khi `import()`).

**Chính sách yên lặng (CPU)** — panel đóng + trạng thái nghỉ + không tương tác 6 giây ⇒ `setPaused(true)`: dừng đồng hồ vẽ của runtime. Mọi thứ đánh thức (mở panel, hover, stream, kéo) vẽ lại ngay. Tab ẩn: runtime tự dừng. Presence (vòng vẽ liên tục) chỉ tải/chạy khi con trỏ ở trên linh vật, tắt sau 3,5 s ân hạn.

**Tiết kiệm** — nạp LƯỜI: cờ tắt 0 byte; đứng "nhà" → tải khi trình duyệt rảnh (`requestIdleCallback` ≤4 s), physics gắn khi rảnh (≤3 s) hoặc ngay trên màn chạm; panel mở / `/assistant` → tải ngay.

**Trợ năng & điều khiển** — `aria-hidden`, host KHÔNG có `tabindex` và KHÔNG có `aria-label` (physics tự đặt `tabindex=0` + `aria-label` ⇒ bị gỡ hẳn; `tabindex=-1` vẫn focus được bằng chuột/chương trình trên một phần tử ẩn khỏi cây trợ năng), không `aria-live`, không âm thanh, không tự mở trợ lý. Popover cài đặt: **Ẩn Ink Scout** / **Giảm chuyển động** / **Đặt lại vị trí**; mã của mục này nạp lười (cờ tắt ⇒ không còn trong JS ban đầu). `prefers-reduced-motion` của hệ điều hành LUÔN thắng (ảnh tĩnh, dời chỗ tức thì, không tải sprite).

**Không lật** — không `scaleX(-1)` ở mã, CSS hay runtime (test cưỡng chế); đi trái/phải dùng hai bản vẽ độc lập của bộ gói.

## 4. Giao diện chatbot (đã rà soát; chỉ sửa chỗ có lỗi/đo được)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Khối mã ``` | Hiện nguyên văn ba dấu huyền giữa đoạn văn; dòng mã dài làm tràn bong bóng | `<pre>` cuộn ngang trong chính nó, `tabIndex=0` (bàn phím cuộn được), vẫn dựng bằng phần tử React (không HTML thô); khối mã ĐANG STREAM (chưa đóng rào) vẫn là khối mã. Logic tách ở `markdownBlocks.ts` (thuần, có test, kể cả đầu vào thù địch) |
| Ô soạn | Cố định 2 dòng (tin dài chỉ thấy 2 dòng) | Tự giãn tới `max-height` (120 px) rồi cuộn trong ô; co lại khi xoá |
| Escape | Không đóng panel nổi | Escape đóng đúng MỘT lớp (popover cài đặt trước, panel sau), trả focus về nút mở; bỏ qua khi đang gõ IME |
| Mở panel | Xuất hiện đột ngột | Mờ dần vào 150 ms, **chỉ `opacity`** (không đổi hộp ⇒ chỗ ngồi của linh vật đo đúng ngay), tắt khi giảm chuyển động |
| Nhấn nút | Chỉ có hover | Có trạng thái `:active` (+ `touch-action: manipulation`); tắt chuyển động khi giảm chuyển động |
| Thanh cuộn danh sách tin | Cột sáng dày mặc định | Mảnh, hoà với kính tối |
| Chữ gợi ý ô soạn | 4,09:1 (< 4,5:1 WCAG 1.4.3) | 5,45:1 (token chữ phụ) |
| `/assistant` desktop (≥1024 px) | Khối `100dvh` nằm dưới header ⇒ ô soạn ở y=860 trong khung nhìn 800 (ngoài màn hình); gõ vào là trang cuộn và header sticky che bộ chọn chế độ | `height: max(480px, 100dvh − 68px)` ⇒ ô soạn nằm gọn trong khung nhìn (đo trên bản dựng Next thật 1280×800 và 1024×768) |
| Nội dung người dùng thường thấy | Không tên provider/model/slot/khoá/hạn mức chung | Không đổi — và nay có QA cố tình nhét `LEAK_*` vào mọi khung SSE/thông điệp lỗi để chứng minh client không vẽ ra |

Đã rà, KHÔNG cần sửa: chọn chế độ, hội thoại mới, lịch sử (tiêu đề dài), hạn mức + giờ làm mới ("Hôm nay còn 3/5 lượt hỏi · làm mới lúc 07:00"), Gửi/Dừng, Tạo lại, "Chưa gửi", trạng thái rỗng, streaming, banner lỗi, URL/từ dài không khoảng trắng, neo cuộn khi stream, focus (mở → ô soạn, đóng → nút mở).
**Giới hạn**: sản phẩm KHÔNG có nút "Tiếp tục" (continue) — đây là tính năng mới, ngoài phạm vi; vùng chạm nút đầu trang trên điện thoại hiệu dụng 40 px (≥ 24 px của WCAG 2.5.8 AA, < 44 px của AAA) vì mở rộng thêm sẽ làm hàng nút tràn ở 320 px.

## 5. Hiệu năng (đo bằng Chrome headless THẬT; chi tiết §8)

Bản dựng Next thật (`next build` + `next start`), tải NGUỘI (không cache), đăng nhập, desktop 1280×800, đo byte trên đường truyền (`encodedDataLength`):

| Hạng mục (JS của trang lúc nghỉ) | Trước khi sửa (`main` c73be8d) | Sau khi sửa |
|---|---|---|
| Mọi cờ tắt (mặc định production) | 242,4 KB (15 tệp) | 242,6 KB (15 tệp) — +0,2 KB: thêm tách khối mã/ô giãn/Escape (+~0,6 KB gz) trừ `companionPrefs` đã gỡ khỏi JS ban đầu (−0,4 KB) |
| Chỉ trợ lý bật, linh vật tắt | 242,4 KB | 242,6 KB (**giống hệt "mọi cờ tắt"**: cờ linh vật tắt không thêm byte nào) |
| Trợ lý + linh vật bật, desktop | 246,3 KB (16 tệp) | 248,6 KB (16 tệp) — chunk lười `AiCompanion` ~5,6 KB gz (kéo thả, director, hình học, bộ nạp) |
| Trợ lý + linh vật bật, điện thoại ngoài `/assistant` | 246,3 KB (16 tệp — vẫn tải chunk linh vật nổi dù không bao giờ hiện) | **242,6 KB (15 tệp)** — cổng kiểm media desktop trước khi `import()` |
| Asset linh vật lúc nghỉ (cờ bật, desktop) | 147,9 KB — 3 tệp (runtime + manifest + sprite idle) | 250,7 KB — 9 tệp: + walk-rig 4 KB, physics 15 KB, 4 tư thế vật lý ~94 KB (nạp khi trình duyệt rảnh ≤3 s, ngoài đường tới hạn) |
| Request `/mascot/` khi cờ tắt | 0 | 0 |
| Request linh vật TRƯỚC khi trang tải xong | 0 | 0 |
| Script đã tải chứa mã linh vật khi cờ tắt | 1 chunk chung (`companionPrefs`) | **0** |

CPU (Chrome phần mềm `--disable-gpu`; trung vị 3 cửa sổ; trang CSS đóng băng để tách riêng phần của linh vật; cơ sở = CÙNG trang với linh vật bị Ẩn):

| Tình huống | Luồng chính trang | Vòng vẽ (RAF/s) |
|---|---|---|
| Cơ sở (linh vật bị Ẩn) | 0,0% | 0 |
| Linh vật đang hoạt ảnh (nghỉ, panel đóng) | 2,8–4,4% | 60 (một vòng duy nhất, đúng tần số màn hình) |
| **Yên lặng** (sau 6 s) | **0,0%** | **0** |
| Panel mở, linh vật ngồi (tư thế tĩnh) | 0,1–0,2% | 0 |
| Đang stream trả lời (gồm cả việc vẽ chữ chạy dần) | 8,7–14,3% | 60 |
| **Người dùng Ẩn linh vật** | **0,1–0,2%** (≈ cơ sở) | **0** |

(Hai lượt đo cách nhau, máy có tải nền khác nhau nên số hơi lệch; khoảng trên là cận của hai lượt.)

Rò rỉ (≈70 chu kỳ: 12 lần đổi tuyến floating↔inline có cả đổi quá nhanh lúc runtime còn đang nạp, 8 lần Ẩn/Hiện, 16 lần mở/đóng panel, 4 stream, 3 Dừng): `jsEventListeners` 195–196 → 200–201 (+5), nút DOM 285 → 338 (+53, đều là tin nhắn thêm), heap 2,07 → 2,91–2,94 MB (+0,84–0,88 MB), RAF đang chờ 1 → 0, interval 0 → 0, luồng SSE mở 0, số document 1.

## 6. Trợ năng (đo bằng CDP)

* Thứ tự Tab: nút mở → (Enter) ô soạn → chọn chế độ → hội thoại mới → lịch sử → cài đặt → đóng → ô soạn …; **linh vật không bao giờ nhận focus**; mọi điều khiển có tên truy cập, vòng focus nhìn thấy và nằm trong khung nhìn. Escape đóng, focus về nút mở.
* Tương phản chữ 28 mục (desktop + 390 px, 8 trạng thái: rỗng, hội thoại, lỗi, đã dừng, hết lượt, lịch sử, cài đặt): thấp nhất 4,63:1; mọi mục ≥ 4,5:1 sau khi sửa chữ gợi ý.
* Linh vật: `aria-hidden="true"`, host không `tabindex`/`aria-label` (bấm vào linh vật không chuyển focus vào nó), không `aria-live`/`role=status|alert` trong khung của nó (hội thoại giữ `aria-live=polite` + `aria-busy` khi stream).
* Giảm chuyển động (hệ điều hành hoặc tuỳ chọn): ảnh tĩnh, không tải sprite hoạt ảnh, ≤ 6 khung vẽ / 1,5 s, dời chỗ tức thì.

## 7. Sticker (CHƯA tích hợp)

12 tệp `mascot/stickers/<id>.{png,webp}`, 512×512; đề xuất gói cho `server/messaging/stickers.py` (`pack_id: "inkscout"`, id `inkscout.hello|lol|love|wow|thinking|angry-cute|sleepy|gg|congratulations|thank-you|confused|facepalm`, `unlock: free`). WebP 512 px (~60 KB) đủ cho bong bóng chat. PR riêng sau khi Chat V1 bật.

## 8. QA

Ba bộ chạy bằng Chrome headless THẬT (CDP) — chi tiết và lệnh ở `scripts/qa/ai_ui/README.md`:

| Bộ | Kết quả (lượt cuối) |
|---|---|
| `run.mjs` — giao diện chat (harness, linh vật tắt) | **813 PASS / 0 FAIL** / 43 INFO (nền trước đợt này: 685) |
| `run_companion.mjs` — linh vật (harness: mã `AiCompanion` + asset thật) | **548 PASS / 0 FAIL** / 38 INFO |
| `run_real.mjs` — bản dựng Next THẬT, ba biến thể cờ | **98 PASS / 0 FAIL** / 11 INFO |
| `node --test` (CI) — ánh xạ, hình học, director, markdown, bộ con, cổng | toàn bộ `npm test`: **1353 pass / 0 fail** / 6 skipped (riêng nhóm AI: 78) |

Viewport: 320 / 360 / 390 / 430 / 768 (điện thoại, máy tính bảng dọc), 1024 (kể cả máy tính bảng ngang cảm ứng) / 1280 / 1920 / 2560 (desktop), xoay dọc↔ngang 844×390, 667×375. Lỗi thật bắt được nhờ QA trình duyệt và đã sửa: (1) vị trí đã nhớ không được áp lúc tải trang khi director đang bận (chạy đua); (2) `/assistant` desktop đẩy ô soạn ra ngoài khung nhìn; (3) chữ gợi ý 4,09:1; (4) JS ban đầu còn chứa `companionPrefs` khi cờ tắt; (5) điện thoại vẫn tải chunk linh vật nổi dù không bao giờ hiện; (6) runtime không tải được lần đầu (mạng chập chờn) thì lần thử lại treo vĩnh viễn trên thẻ `<script>` đã hỏng (tái hiện bằng cách chặn `ink-scout.js` rồi bỏ chặn); (7) `tabindex=-1` trên host vẫn nhận focus khi bấm.

**Review độc lập (Codex, khác họ model với người viết)** trên toàn bộ diff `web/src`: 3 phát hiện. #2 (thẻ script hỏng — MED) và #3 (tabindex — MED) tái hiện được ở trình duyệt thật và đã sửa kèm test; #1 (HIGH: cầm linh vật giữa lúc director đang di chuyển có thể bị giật) KHÔNG tái hiện được — QA thật cầm giữa lúc về nhà: linh vật bám con trỏ ≥ 85% mẫu và đáp đúng chỗ thả, vì physics huỷ chuyển động khi pickup và runtime có token — nên chỉ thêm biện pháp phòng thủ (place = `free` nếu chuyển động kết thúc lúc đang cầm) + test, không đổi hành vi.

**Giới hạn thật**: không có iOS Safari/Android Chrome thật; bàn phím ảo chỉ mô phỏng (`visualViewport.height` giả), Chrome desktop giả lập cảm ứng/di động; failover phía máy chủ chỉ mô phỏng bằng im lặng dài + `: ping` (đúng thứ client thấy — logic máy chủ do `server/tests/` kiểm); CPU đo bằng Chrome phần mềm nên chỉ so sánh tương đối; bộ QA trình duyệt không chạy trong CI (CI không có Chrome headless cho nó).

## 9. Điểm không nhất quán thừa hưởng (ảnh raster sinh)

* Bộ gốc tự khai: không có rig vector/Rive; nét và tỉ lệ thay đổi nhẹ giữa các khung/khung nhìn vẽ lại độc lập (`qa/validation.json`).
* `jump-onto-panel` dùng lại NGUYÊN hoạt ảnh `hop-right`; `return-home` dùng lại `walk`; `hover` không có poster tĩnh riêng.
* Đi trái và đi phải là hai bản vẽ độc lập (đúng yêu cầu không lật), nên nhịp bước hai hướng không đối xứng hoàn hảo.

## 10. Bật trên production — CHỈ khi Owner duyệt rõ ràng

Hiện: `PRODUCTION_AI_ASSISTANT_ENABLED=1` (Trợ lý AI đã mở theo cấu hình ở `AI_PUBLIC_BETA_CHECKLIST.md`), `PRODUCTION_AI_COMPANION_ENABLED=0`. Cờ linh vật là cờ BUILD toàn cục — **không có canary theo người dùng**: bật là mọi người dùng desktop đủ điều kiện thấy Ink Scout (mỗi người tự Ẩn được bằng popover cài đặt).

Điều kiện: PR này đã merge vào `main`, CI xanh, Owner kiểm trên bản local/preview (§8) và nói rõ "bật Ink Scout".

1. Đặt biến repository (cấp repository, KHÔNG bản sao cấp môi trường):
   ```
   gh variable set PRODUCTION_AI_COMPANION_ENABLED --repo kujopht/capcut-tts-app --body 1
   ```
   (pipeline từ chối `COMPANION=1` khi `ASSISTANT≠1`.)
2. Deploy đúng SHA `main` đang chạy bằng lệnh tường minh (không có lệnh `cf:deploy` trần), rồi duyệt môi trường `production`:
   ```
   gh workflow run production-deploy.yml --repo kujopht/capcut-tts-app --ref main -f confirm=DEPLOY_PRODUCTION -f ref=<SHA main> -f run_certification=false -f run_canary=false -f source_url=https://example.com -f chapter_limit=2
   ```
3. Kiểm: Step Summary ghi `AI UI build flags: assistant=1 companion=1`; mở fanfic.world bằng tài khoản đủ điều kiện ở desktop ≥1024 px → Ink Scout đứng cạnh nút mở trợ lý; Network: chỉ SAU khi trang tải xong mới có request `/mascot/ink-scout/`; điện thoại: không có request `/mascot/` ngoài `/assistant`; console không có lỗi `mascoterror`.
4. **Rút lui** (không cần dọn dữ liệu — chỉ `localStorage` `fas.aiCompanion.v1` của từng trình duyệt): `gh variable set PRODUCTION_AI_COMPANION_ENABLED --repo kujopht/capcut-tts-app --body 0` rồi deploy lại cùng cách; nhanh hơn: workflow **Production Rollback** về bản frontend trước. Tắt khẩn cấp của Trợ lý AI (`/admin/ai`) cũng làm linh vật biến mất cùng nút mở.
5. Theo dõi sau khi bật: lỗi `mascoterror` ở console, phản hồi người dùng về vị trí/độ che, CPU trên máy yếu (chính sách yên lặng đã đo ở §5).
