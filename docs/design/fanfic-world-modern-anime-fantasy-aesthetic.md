# Fanfic World — Aesthetic: Modern Anime Fantasy / Cinematic Storyworld

Trạng thái: nguồn sự thật cho MỌI ảnh minh hoạ được sinh (AI-generated) cho
Fanfic World, bắt đầu từ Phase 3.5 "Cinematic Homepage Polish". File này DÙNG
ĐỊNH DẠNG tham khảo từ `aplaceforallmystuff/claude-art-skill`
(`skills/art/aesthetic.md`, `skills/art/aesthetics/README.md` — đã audit,
không cài đặt skill đó vào máy, chỉ mượn CẤU TRÚC tài liệu). Bộ sinh ảnh THẬT
SỰ dùng là **Pollinations MCP** đã có sẵn trong dự án (không phải
Google/OpenRouter mà skill gốc giả định) — mọi prompt gửi tới Pollinations
phải bắt đầu bằng Base Prompt Prefix ở dưới.

Phái sinh trực tiếp từ `docs/design/FANFIC_WORLD_VISUAL_BIBLE_V1.md` (mục 1,
2, 6, 7, 10, 11 và bản hiệu chỉnh v1.1) — không tự bịa màu/tỷ lệ mới.

---

## Core Concept

> *"Một cổng vào thế giới hư cấu, được vẽ NHƯ một thế giới thật — không phải
> UI đặt trên tường ảnh anime."*

Cán cân đã chốt ở Visual Bible v1.1 (áp dụng cho MỌI ảnh sinh ra ở đây):

| Fantasy | Màu anime | UI hiện đại | Điện ảnh | Glow | Kính | Hoạ tiết | Mật độ |
|---|---|---|---|---|---|---|---|
| 8/10 | 7/10 | 9/10 (không áp dụng trong ảnh, chỉ khi tích hợp CSS) | 8/10 | **1/10** | 3/10 | 3/10 | 5/10 |

## Style Direction

### Nên hướng tới
- Minh hoạ **môi trường/cảnh** (environmental illustration) — có chiều sâu
  lớp (tiền cảnh/trung cảnh/hậu cảnh), không phải một biểu tượng phẳng giữa
  khung.
- Ánh sáng điện ảnh có HƯỚNG rõ ràng, một nguồn sáng ẩn dụ chính mỗi cảnh
  (trăng, đèn lồng, ánh chiếu, ánh trăng qua cửa sổ...) — đúng mục 6 Visual
  Bible.
- Chi tiết "sạch, cao cấp" (clean premium detail) — nét vẽ modern anime,
  không phải vẽ tay thô (sketch) hay pixel.
- Bầu khí huyền bí RẤT tiết chế — năng lượng phép thuật là mạch sáng mảnh,
  không phải khói/hạt phủ đầy khung.

### Nên tránh (áp dụng cứng cho MỌI prompt)
- Giao diện game RPG (thanh HP, khung gỗ, huy hiệu game).
- "Giả trung cổ" tràn lan (giấy da/parchment phủ toàn cảnh) — parchment CHỈ
  là chất liệu của trang Reader, không phải của cả thế giới.
- Cyberpunk, neon gaming, glow bão hoà.
- Chữ/logo/nhãn hiệu bất kỳ trong ảnh (kể cả chữ giả/không đọc được).
- Nhân vật/biểu tượng có bản quyền hoặc gợi nhớ franchise cụ thể.
- Khung UI/menu game vẽ LỒNG bên trong ảnh minh hoạ (ảnh là background/art,
  không tự vẽ nút bấm hay khung viền UI giả).

## Color System

Tất cả hex lấy nguyên từ `web/src/app/globals.css` — KHÔNG bịa giá trị mới,
chỉ mô tả lại vai trò để mô hình sinh ảnh dùng đúng.

### Nền (đêm trăng / mực xanh)
```
--bg     #08090f   (đen-xanh sâu nhất, dùng cho vùng tối nhất của cảnh)
--bg-1   #0f1119
--bg-2   #151824
--bg-3   #1d2130   (xanh navy nhạt nhất — không bao giờ tới mức xám phẳng)
```

### Chữ/đường nét trung tính (không dùng cho art, chỉ tham chiếu khi tích hợp CSS)
```
--text    #eceff7   (ngọc trai gần-trắng)
--text-2  #a9b3c9
--text-3  #7e8aa6
```

### Anime chính — cyan trời quang (MỘT điểm nhấn chính mỗi cảnh)
```
--accent        #22d3ee
--accent-hover  #67e8f9
```

### Anime phụ — tím pháp thuật kiềm chế (tối đa MỘT lúc với cyan)
```
--brand         #8b6cff
--brand-hover   #a78bfa
```

### Cảm xúc / con người thật — chỉ dùng CHỌN LỌC, không phủ diện rộng
```
--vang        #d8b56a   (đèn lồng/hổ phách — ánh sáng ấm, nguồn nhân tạo)
--vang-sang   #e4c982
sakura/coral  #f0a6c8, #fda4af   (điểm nhấn hồng anh đào — cực kỳ chọn lọc)
```

### Quy tắc cứng
Một cảnh = nền navy + MỘT accent chính (thường cyan) + tối đa MỘT accent phụ
(tím HOẶC vàng đèn lồng HOẶC sakura — không dùng cả ba cùng lúc). Không
rainbow. Nếu cảnh "cần" nhiều màu hơn để nhìn hấp dẫn, bớt màu chứ không
thêm khung/hoạ tiết bù.

## Composition Rules

1. Bố cục MÔI TRƯỜNG (kiến trúc/thiên nhiên/nội thất huyền ảo), không phải
   một vật thể/nhân vật đơn lẻ giữa nền trơn.
2. Chiều sâu rõ: tiền cảnh mờ nhẹ hoặc tối hơn, trung cảnh là điểm nhìn
   chính, hậu cảnh nhạt/mờ dần vào sương đêm.
3. Đủ không gian âm (negative space) ở MỘT phía để chữ tiêu đề trang web có
   thể đặt đè lên mà không cần khối chữ nhật tối phía sau.
4. KHÔNG vẽ khung/viền trang trí giả UI trong ảnh — khung là việc của CSS
   khi tích hợp, không phải của ảnh.
5. Tỷ lệ khung theo mục đích sử dụng thực tế trên trang (portal card ~4:3
   hoặc 1:1, hero rộng ~21:9 hoặc 16:9) — khai báo tỷ lệ khi gọi Pollinations,
   không crop thô sau khi sinh nếu tránh được.

## Base Prompt Prefix (BẮT BUỘC — chèn vào MỌI lần gọi Pollinations)

```
Modern anime fantasy illustration, cinematic environmental composition with
clear depth (foreground, midground, background). Midnight navy to sky-blue
atmosphere, moonlit or lantern-lit. Restrained arcane violet energy as thin
glowing threads, never overpowering. Selective sakura or coral accent used
sparingly. Selective warm lantern-gold light marking a human presence. Clean
premium anime detail, sophisticated cinematic lighting with one clear light
source, subtle magical atmosphere. No generic fantasy game UI, no HP bars, no
wooden RPG frames. No medieval parchment overload. No cyberpunk, no neon
gaming aesthetic, no glowing borders. No text, no random letters, no logos,
no franchise symbols, no copyrighted characters. Negative space on one side
for headline overlay.
```

### Bảng khoá tham số (Consistency Lock)

| Tham số | Giá trị khoá | Vì sao |
|---|---|---|
| Cân bằng màu | Navy chiếm ưu thế, MỘT accent chính (cyan), tối đa MỘT accent phụ | Tránh "rainbow UI", đúng mục 1 v1.1 |
| Glow | Cực tiểu (1/10) — mạch sáng mảnh, không quầng | Đây là lỗi thị giác đã bị phản hồi nhiều lần ở Nav/Homepage trước đây |
| Chất liệu | Không parchment/giấy da ngoài Reader | Tránh "giả trung cổ" toàn site |
| Nguồn sáng | Đúng MỘT nguồn sáng ẩn dụ mỗi cảnh | Mục 6 Visual Bible — không hai nguồn sáng cạnh tranh |
| Chữ/logo | Tuyệt đối không | Ảnh dùng làm nền/portal — chữ thật do HTML render đè lên |
| Nhân vật bản quyền | Tuyệt đối không | Yêu cầu pháp lý — nguyên tắc dự án |

## AI Generation Signals

**Nên dùng (positive):**
```
"modern anime fantasy illustration"
"cinematic environmental composition"
"moonlit atmosphere"
"restrained arcane violet energy"
"clean premium anime detail"
"one clear light source"
"depth of field, layered composition"
```

**Nên tránh (negative):**
```
"fantasy game UI"
"HP bar, wooden RPG frame"
"parchment texture overlay"
"cyberpunk neon"
"glowing border, bloom, lens flare heavy"
"text, logo, watermark"
"copyrighted character, franchise mascot"
```

---

## Ghi chú vận hành (khác với `claude-art-skill` gốc)

- **Bộ sinh ảnh**: Pollinations MCP (`mcp__pollinations__generateImage*`),
  KHÔNG dùng `tools/generate-image.ts` của skill gốc (script đó gọi Google
  Gemini "Nano Banana" hoặc OpenRouter — không có credential nào cho hai nhà
  cung cấp này trên máy này, đã xác nhận `GOOGLE_API_KEY`/`OPENROUTER_KEY`
  không tồn tại trong shell, `~/.claude/.env`, hay bất kỳ `.env*` nào trong
  repo).
- **An toàn chi phí**: LUÔN sinh preview nhỏ/rẻ trước, tối đa 2 ứng viên mỗi
  khái niệm, xem trước bằng mắt rồi mới quyết định dùng ảnh nào — không sinh
  hàng loạt 4K ngay từ đầu.
- **Không commit ảnh bị loại**: chỉ ảnh ĐÃ CHỌN mới vào `web/public/`; ảnh
  preview/thử nghiệm giữ ngoài cây tài sản production.
