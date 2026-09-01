# PARALLEL CONTENT FACTORY — Story + Chinese AI Animation (2026-09-01)

## Tóm tắt

Hai track chạy song song trong cùng phiên. **Cả hai đều đã hoàn thành mọi
việc KHÔNG cần credential production**, và **cả hai đều dừng ở đúng MỘT
điểm chung**: ghi bản nháp thật vào `/api/novels` cần `FAS_HARVESTER_TOKEN`
— một bearer token owner-scoped chưa từng tồn tại ở máy này, đã được yêu
cầu một lần duy nhất (broker đã sẵn sàng nhận), chưa nhận được giá trị tại
thời điểm viết báo cáo này.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Schema `novels` (Appwrite production) | 9 thuộc tính thật sự tồn tại trên server (nhiều trường code đã viết từ mission taxonomy trước nhưng CHƯA migrate) | 23 thuộc tính — migrate bù luôn phần thiếu cũ + 4 trường video mới (`platform`, `rights_mode`, `subtitle_status`, `embed_ref`), thuần cộng thêm, không đổi/xoá trường nào |
| Video draft lưu ở đâu | Chưa có chỗ lưu nào | Tái dùng `Novel`/`METADATA_ONLY` — không tạo collection mới, không route API mới |
| Track A (truyện) — chương đã có sẵn, thật, đã kiểm chứng | 0 | 2 (Re:Zero, ch.1-2, đã tiếng Việt sẵn — dịch từ AO3 có phép tác giả, đăng lại trên docln.net) |
| Track B (video) — ứng viên thật đã xác minh sống | 0 | 10/10 — đủ chỉ tiêu mission |
| `scripts/ship_story_rezero_runner.py` | chưa tồn tại | có, đã compile, đã test đường BLOCKED, sẵn sàng chạy ngay khi có token |
| `scripts/ship_video_drafts_runner.py` | chưa tồn tại | có, đã compile, đã test đường BLOCKED, sẵn sàng chạy ngay khi có token |

## TRACK A — Story Factory

**Nguồn**: docln.net #28046, "Re: Zero - Hai Vì Sao Bị Quên Lãng" — fanfic
Re:Zero dịch từ AO3 **có phép tác giả/hoạ sĩ**, đăng lại trên docln.net
(nguồn Việt hoá sẵn — dịch máy KHÔNG cần chạy cho nguồn này).

**Đã có sẵn, thật, đã kiểm chứng 100% score**: chương 1 (34.100 ký tự),
chương 2 (37.610 ký tự) — đã archive raw + sensitive-scan sạch từ một
phiên trước.

**Chặn thật khi thử lấy thêm chương** (không phải lỗi code): docln.net trả
`HTTP 403` cho MỌI request tới domain này tại thời điểm chạy — kể cả một
URL chương ĐÃ TỪNG tải được thành công trước đó. Đã thử: (1) fetch lại
trang mục lục, (2) fetch lại đúng URL chương 2 đã biết là tốt (để phân biệt
"chặn cả domain" hay "chỉ chặn trang mục lục" — kết quả: chặn CẢ domain),
(3) Wayback Machine (không có snapshot). Dừng theo đúng quy tắc "tối đa
15-20 phút mỗi vấn đề hạ tầng" — không lặp lại mù quáng.

**Provider dịch**: KHÔNG cần — nguồn đã tiếng Việt. Router dịch (Tencent/
free-provider) không được kích hoạt vì không có gì phải dịch.

**Script sẵn sàng**: `scripts/ship_story_rezero_runner.py` — tạo/tái dùng
Novel (idempotent theo `external_source_url`), QA rẻ tiền (trùng đoạn, tên
nhân vật còn nguyên, độ dài hợp lý, không có khối ASCII dài bất thường),
tạo job TTS chương 1 bằng giọng `piper:ngochuyennew` (giọng Ngọc Huyền Mới,
đúng yêu cầu voice production hiện tại), rồi verify thật: job completed,
`duration_seconds > 0`, `size_bytes > 0`, URL phát HTTP 200,
`Content-Type` là `audio/*`.

**Trạng thái**: 2/5 chương tối thiểu đã sẵn sàng ghi (thiếu do chặn nguồn,
không do thiếu code/logic) — 0/2 đã thực sự ghi vào production (thiếu
credential). TTS: 0 job đã chạy (phụ thuộc bước ghi Novel/Chapter trước).

## TRACK B — Chinese AI Animation Source Factory

**10/10 ứng viên thật, xác minh SỐNG qua `YouTubeAdapter` thật (oEmbed
công khai, không tải video)** — bảng đầy đủ:

| # | video_id | Tiêu đề | Kênh | Rights mode |
|---|---|---|---|---|
| 1 | jBj06aw67f0 | 七十二环书津门卫疆 | 破界动漫局 Anime Club | EMBED_ONLY |
| 2 | f8qAWvpT-LQ | 瘦下来惊艳全校 EP1~38 | 吞噬动漫DevourAnime | EMBED_ONLY |
| 3 | I8pBeykLauA | 天命神算 Ep01-30 | AI动漫频道 | EMBED_ONLY |
| 4 | EBwsgB1rRBo | 侯母换子：真嫡女重生回来了 | TePi动漫推荐 | EMBED_ONLY |
| 5 | RWsrv0pCrVc | China's first AI-generated animated series (tin tức) | ThinkChina Sg | REFERENCE_ONLY |
| 6 | iRpBgUekOdI | 2026 24 must-watch AI animation hits (tổng hợp trailer) | YOUKU English Animation | REFERENCE_ONLY |
| 7 | emuWAbvnzZk | 胖妞农女 第1集 | (kênh AI漫剧) | EMBED_ONLY |
| 8 | K4w5dFVJjvU | 妈妈的人情账（50） | KK爱看 | EMBED_ONLY |
| 9 | 8ctlvFSfKMI | 第一门客 | KK爱看 | EMBED_ONLY |
| 10 | rGCI6Uj1Wew | 好女婿，先下手为强 第1~63集 | KK爱看 | EMBED_ONLY |

Ghi chú cột `Rights mode`: #5/#6 là clip tin tức/trailer tổng hợp CỦA BÊN
THỨ BA nói VỀ nội dung AI-animation (không phải chính tập phim) —
`REFERENCE_ONLY` (chỉ dùng để tham chiếu/nghiên cứu định dạng, KHÔNG tạo
draft xem trực tiếp từ đây). 8 mục còn lại là nội dung AI-animation THẬT
(EMBED_ONLY — không kênh nào có quyền phân phối lại xác minh được).

**Phụ đề gốc — kiểm tra thật, không đoán**: tất cả 10/10 video đều trả về
**danh sách caption-track RỖNG** qua API `timedtext?type=list` công khai
của YouTube (không cần đăng nhập, không tải video). Nhãn "MULTI SUB" trên
tiêu đề của các kênh này là phụ đề **BURN-IN vào hình ảnh video**, không
phải track văn bản thật lấy được. `subtitle_status = PENDING_SOURCE` cho
tất cả 10.

**Bilibili**: `BilibiliAdapter` thật đã thử — bị chính `robots.txt` của
`api.bilibili.com` từ chối user-agent hiện tại. Đây là giới hạn tôn trọng
robots.txt CÓ CHỦ Ý của adapter (không bypass anti-bot) — Bilibili KHÔNG
khả dụng qua kênh này ở phiên này, không phải lỗi.

**3 video được chọn làm DRAFT thật** (script
`scripts/ship_video_drafts_runner.py`, đã sẵn sàng, chờ credential):
#1, #2, #3 ở bảng trên — 3 kênh AI-animation THẬT SỰ (không phải
tin tức/trailer), đa dạng thể loại. `rights_mode=EMBED_ONLY`,
`subtitle_status=PENDING_SOURCE`, KHÔNG sao chép byte media nào.

## Track B — Quan sát định dạng (cho animation generator tương lai)

Từ 10 ứng viên đã xử lý (chỉ quan sát được qua tiêu đề/kênh/metadata công
khai — KHÔNG tải video nên không đo được số liệu khung hình/cảnh thật;
không "nghiên cứu quá mức" thêm ngoài dữ liệu đã có sẵn từ bước cataloging
này):

- **Nhịp phát hành**: hầu hết là series NHIỀU tập gộp thành 1 video dài
  (vd EP1~38, Ep01-30, "1~63 集") — khác hẳn kiểu "1 video = 1 tập" của
  anime truyền thống; phù hợp mô hình "toàn bộ mùa/truyện trong một lần
  xem liên tục" của khán giả short-drama.
- **Phụ đề**: 100% burn-in, không track riêng — animation generator tương
  lai của ta PHẢI tự tạo track WebVTT/SRT riêng ngay từ đầu (không thể lấy
  lại từ nguồn tham khảo dạng này).
- **Thể loại lặp lại**: xuyên không/trọng sinh (穿越/重生), báo thù/lật
  ngược thế cục (逆袭), gia đình/đạo đức (家庭/伦理), tiên hiệp/huyền huyễn
  (仙/玄幻) — khớp với thể loại fanfic anime ta đã có trong taxonomy
  (`characters`/`pairings`/`status`).
- **Kênh chuyên biệt hoá**: một kênh (KK爱看) sản xuất ĐỀU ĐẶN nhiều series
  hoàn chỉnh — mô hình "một xưởng, nhiều IP ngắn" hơn là một studio làm
  một bộ dài.
- Không đo được: thời lượng cảnh, mật độ thoại, tỷ lệ hoạt hình/tĩnh, tần
  suất pan/zoom, animation miệng, kiểu chuyển cảnh, tái sử dụng nền, nhạc/
  SFX — TẤT CẢ đều cần phân tích khung hình thật (yêu cầu tải video), nằm
  ngoài phạm vi EMBED_ONLY của phiên này. Ghi rõ đây là khoảng trống dữ
  liệu THẬT, không giả định số liệu.

## PHASE C — Kế hoạch tích hợp lấy cảm hứng từ Huobao (KHÔNG triển khai)

`chatfire-AI/huobao-drama` — không phải deliverable của mission này. Kế
hoạch NGẮN GỌN để tái dùng Ý TƯỞNG workflow/UI/orchestration (không phụ
thuộc chặt vào repo đó):

```
Truyện Fanfic World (đã dịch, đã QA)
  -> Cắt kịch bản theo cảnh (phân đoạn theo lời thoại/tường thuật, tái
     dùng logic chunking đã có ở text_chunker.py)
  -> Storyboard (mô tả cảnh + nhân vật xuất hiện, JSON có cấu trúc — không
     phải ảnh, chỉ đặc tả)
  -> Trạng thái cảnh/nhân vật (character sheet đã có ở CharacterIdentity/
     LoRA foundation — TÁI DÙNG, không xây lại)
  -> Sinh ảnh (image router đã có — ưu tiên self-host/free-quota trước
     API trả phí, đúng nguyên tắc router hiện hành)
  -> Hoạt hình ảnh/video (bước MỚI DUY NHẤT thật sự cần — khảo sát công
     cụ self-host/free trước khi xem xét bất kỳ API trả phí nào)
  -> Giọng/TTS (đã có, tái dùng nguyên vẹn — không đổi)
  -> Phụ đề (WebVTT/SRT, không burn-in — bài học rút ra trực tiếp từ khảo
     sát Track B ở trên)
  -> Ghép FFmpeg (đã có ffmpeg/ffprobe trong môi trường này)
  -> Tập hoàn chỉnh
```

Nguyên tắc bắt buộc: **provider-neutral** (khớp router hiện hành), ưu tiên
Tencent free quota / Beam free compute / Vast trả phí sau này / model
self-host trước bất kỳ API ngoài trả phí nào, và **không khoá cứng** vào
kiến trúc Huobao — chỉ mượn Ý TƯỞNG pipeline.

## Test & Bảo mật

`server/tests` đầy đủ: 4218/4218 pass (đã sửa 1 test bị ảnh hưởng bởi 4
trường Novel mới — `test_cover.py::test_only_cover_url_was_added`, theo
đúng cơ chế xác nhận-tường-minh sẵn có của chính test đó). Secret-scan
sạch trên mọi diff. Migration schema Appwrite: dry-run trước, rồi apply
thật, xác nhận "an toàn chạy lại bất cứ lúc nào" bởi chính tool.

## Chặn còn lại (một lần, không lặp lại)

`FAS_HARVESTER_TOKEN` — đã yêu cầu một lần, broker đã sẵn sàng nhận
(`python scripts/fanfic_credential_broker.py store --name FAS_HARVESTER_TOKEN`),
chưa nhận được giá trị. Đây là điểm chặn DUY NHẤT còn lại cho cả hai track
— mọi việc khác (code, script, catalog, schema, test) đã xong và chờ chạy
ngay khi có token, không cần thêm bất kỳ quyết định hay thao tác nào khác
từ người vận hành.
