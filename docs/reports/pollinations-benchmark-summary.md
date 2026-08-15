# So sánh Pollinations vs Groq — kết quả benchmark thật (2026-08-15)

**Dữ liệu thô đầy đủ** (kèm toàn văn bản dịch): `pollinations-benchmark-raw.json`
(4 model Pollinations + Groq qwen) và `pollinations-benchmark-raw-groq-retry.json`
(deepseek + deepseek-pro + Groq gpt-oss-120b, chạy sau ~10 phút). Console log
gốc: `pollinations-benchmark-console.txt`.

Tài liệu này là bản đọc-hiểu do người viết (không tự động sinh điểm số) —
**không dùng để tự động chọn model**, chỉ tổng hợp lại quan sát từ văn bản
dịch thật để người đọc tự đối chiếu với dữ liệu thô.

## Model thực sự tiếp cận được và dịch thành công

| Model | Trạng thái |
|---|---|
| `pollinations_deepseek` | ✅ Thành công (2 lần chạy) |
| `pollinations_deepseek_pro` | ✅ Thành công |
| `pollinations_kimi` | ✅ Thành công |
| `pollinations_glm` | ✅ Thành công |
| `pollinations_command_a_plus` | ✅ Thành công |
| `groq_qwen` | ❌ 429 rate limit (key dùng chung) |
| `groq_gpt_oss_120b` | ❌ 429 rate limit (key dùng chung) |

**Không lấy được điểm dữ liệu Groq thành công nào** dù đã thử 3 model Groq
khác nhau trên hai lượt chạy cách nhau ~10 phút — khóa `GROQ_API_KEY` dùng
chung hiện đang bị giới hạn tốc độ ở mức tổ chức, không phải lỗi cấu hình.

## Độ trễ — LƯU Ý: dao động RẤT lớn giữa hai lượt chạy

| Model | Lượt 1 (median, 3 đoạn) | Lượt 2 (deepseek/-pro, 3 đoạn) |
|---|---|---|
| `pollinations_deepseek` | 11 453 ms | **672–953 ms** |
| `pollinations_deepseek_pro` | — | 10 454–11 078 ms |
| `pollinations_kimi` | 47 579 ms | — |
| `pollinations_glm` | 22 110 ms | — |
| `pollinations_command_a_plus` | 7 000 ms | — |

`deepseek` chênh lệch **hơn 10 lần** giữa hai lượt (11.4s → ~0.8s) — Pollinations
là một gateway tổng hợp nhiều backend cộng đồng, độ trễ theo model có thể biến
động mạnh theo thời điểm. **Không nên coi con số của MỘT lượt chạy là ổn định**;
cần đo nhiều lượt trải dài thời gian trước khi quyết định dựa trên độ trễ.

Xếp hạng tương đối trong lượt 1 (mẫu nhỏ, chỉ để tham khảo): command-a-plus
nhanh nhất, deepseek trung bình, glm chậm hơn, kimi chậm nhất rõ rệt (~47s/đoạn
— nếu ổn định ở mức này thì không thực tế cho một chương nhiều đoạn).

## Quan sát chất lượng (đọc trực tiếp bản dịch, không chấm điểm tự động)

**Tên riêng/xưng hô — điểm khác biệt RÕ RỆT nhất:**
- `deepseek`, `deepseek_pro`, `kimi`, `glm`: cả bốn đều NHẤT QUÁN dùng phiên âm
  Hán Việt đã thành quy ước của nền tảng này — "Tiêu Viêm" (萧炎), "Dược Lão"
  (药老), "Vân Vận" (云韵) — khớp đúng ví dụ đã có trong test fixture của hệ
  thống (`server/tests/test_translation_provider_registry.py`).
- `command-a-plus`: dùng **pinyin/phiên âm La-tinh thay vì Hán Việt** — "Xiao
  Yan" thay vì "Tiêu Viêm", "Vân Du" (không phải "Vân Vận" — sai cả phiên âm),
  "thành U Tan" thay vì "Ô Thản". Đây là lệch quy ước đặt tên đáng kể so với
  ba model còn lại.

**Xưng hô kính ngữ (thể loại tiên hiệp/huyền huyễn):**
- `deepseek`/`kimi`/`glm`: dịch "师兄" → "Sư huynh" (đúng ngữ cảnh môn phái).
- `command-a-plus`: dịch "师兄" → "Anh trai" (nghĩa gia đình thông thường,
  MẤT sắc thái môn phái/tu luyện đặc trưng thể loại).

**Tự nhiên của hội thoại:** cả bốn đều đọc tự nhiên bằng tiếng Việt;
`command-a-plus` có một vài chỗ diễn đạt hơi gượng ("Là sư phụ đã bôn ba khắp
nơi nhiều năm rồi...") so với các model còn lại.

**Giữ đoạn/thứ tự:** cả bốn model đều giữ đúng cấu trúc 3 dòng thoại, đúng thứ
tự đoạn văn — không phát hiện xáo trộn hay gộp đoạn.

**Kiểm duyệt/lược bỏ nội dung:** không phát hiện model nào lược bớt nội dung
hay từ chối dịch — cả ba đoạn mẫu (kể cả đoạn có xưng hô nhạy cảm "本座"-kiểu)
đều được dịch đầy đủ ở cả bốn model.

## Kết luận — KHÔNG tự động chọn "thắng" từ tên/nhà cung cấp

Bằng chứng thật (không phải suy đoán tên model) cho thấy:
- `deepseek` (model chính hiện tại) dịch chất lượng tốt, đúng quy ước đặt tên,
  độ trễ dao động mạnh nhưng CÓ THỂ rất nhanh (0.7s ở lượt 2).
- `deepseek-pro` chất lượng tương đương `deepseek`, độ trễ ổn định hơn (~10-11s
  cả hai lần đo được) nhưng LUÔN chậm hơn `deepseek` nhiều lần.
- `kimi`/`glm` chất lượng tương đương deepseek/deepseek-pro (cùng quy ước đặt
  tên) — nhưng mẫu quá nhỏ (1 lượt, 3 đoạn) để kết luận chắc chắn về độ trễ.
- `command-a-plus` nhanh nhất trong lượt đo được, NHƯNG có vấn đề chất lượng
  THẬT (lệch quy ước Hán Việt, dịch sai sắc thái kính ngữ môn phái) — tốc độ
  không bù được lỗi nhất quán tên riêng cho một nền tảng đọc fanfic tiên hiệp/
  huyền huyễn.

**Khuyến nghị (dựa trên bằng chứng, không dựa trên tên nhà cung cấp):** giữ
`deepseek` làm model chính, `deepseek-pro` làm model chất lượng/thử lại — đúng
thứ tự đang triển khai. KHÔNG đưa `command-a-plus` lên vị trí ưu tiên cao dù
tốc độ tốt, do lỗi nhất quán tên riêng/kính ngữ vừa quan sát được. `kimi`/`glm`
có thể cân nhắc làm ứng viên dự phòng bổ sung sau Groq, nhưng cần đo thêm
nhiều lượt (đặc biệt độ trễ) trước khi đưa vào production.

**Chưa so sánh được với Groq** — không lấy được điểm dữ liệu Groq thành công
nào trong phiên này (rate limit thật trên key dùng chung). Cần chạy lại
`python scripts/benchmark_pollinations_translation.py` khi `GROQ_API_KEY` hết
bị giới hạn để có so sánh đầy đủ ba bên.
