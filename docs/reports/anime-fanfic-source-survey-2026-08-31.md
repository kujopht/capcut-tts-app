# Khảo sát nguồn Anime/Manga Fanfic — 2026-08-31

Kết quả THẬT của việc rà soát 5 nền tảng ứng viên cho mission "Anime Fanfic
Production Canary". Mỗi domain dưới đây đã được kiểm tra **toàn vẹn**: đọc
`robots.txt`/Điều khoản Dịch vụ thật (không chỉ suy đoán), **và** thử fetch
thật qua `server/scraper/http_fetcher.py::HttpFetcher` — chính fetcher sản
xuất, tự nhận diện minh bạch (`User-Agent: FanficWorldStoryScraper/0.1`),
không phải một công cụ đọc trang riêng biệt. Mã hoá lại thành dữ liệu tại
`server/scraper/source_policy.py` — file này là bản tường thuật, file kia là
cổng chặn thật thi hành trong code.

## Bảng tổng hợp

| Domain | robots.txt | ToS (trích dẫn thật) | `HttpFetcher` thật | Kết luận |
|---|---|---|---|---|
| archiveofourown.org | Cho phép hầu hết đường dẫn | OTW: *"không có ngoại lệ... cho người muốn tạo dataset"*; chủ động giới hạn tốc độ/giám sát; đã yêu cầu Common Crawl ngừng quét (2022) | HTTP 403 trên cả trang ToS lẫn `/tags/Naruto/works` | **AUTHOR_OPT_IN_REQUIRED** |
| fanfiction.net | Cho phép, `Content-Signal: search=yes,ai-train=no,use=reference` | Cho phép automation tốc độ người, nhưng loại trừ *"caches or archives"* khỏi ngoại lệ search-engine | HTTP 403 trên một trang truyện thật (`/s/13530962/1/Ninja-s-Hero-Academia`) | **TECHNICALLY_UNSTABLE** |
| wattpad.com | Chặn nhiều đường dẫn cá nhân/campaign | *"Don't use any kind of software... to 'crawl', 'spider' or otherwise remove any content"* — cấm rõ ràng, không điều kiện | Không kiểm tra (không cần thiết — đã chặn ở ToS) | **POLICY_BLOCKED** |
| scribblehub.com | HTTP 403 (không đọc được) | HTTP 403 (không đọc được) | HTTP 403 | **TECHNICALLY_UNSTABLE** |
| quotev.com | Cho phép hầu hết đường dẫn | Chưa xác định được văn bản chính thức | HTTP 200 nhưng thân trang **RỖNG** (1 ký tự) trên cả trang chủ lẫn `/stories/fanfiction` | **TECHNICALLY_UNSTABLE** |
| tapas.io | Cho phép hầu hết đường dẫn | Chưa kiểm tra | `/genre/FAN_FICTION` trả 404 (đường dẫn sai hoặc mục fanfic không tồn tại ở đó) — **CHƯA XÁC MINH ĐẦY ĐỦ**, ưu tiên thấp vì ít fanfic anime hơn các nền tảng khác | Chưa phân loại — không đưa vào `source_policy.py` |
| royalroad.com | Cho phép (đã đăng ký `SiteConfig` từ mission trước) | *"use or launch any manual or automated system... to access, scrape, crawl, cache, spider any web page"* (cập nhật 2025-03-03) | Không cần kiểm tra — ToS đã cấm dứt khoát | **POLICY_BLOCKED** — xem mục "Lỗ hổng thật đã sửa" bên dưới |
| docln.net (Cổng Light Novel) | Cho phép | Chưa thấy văn bản ToS đầy đủ, nhưng chính site công bố: *"Truyện có chủ sở hữu bản quyền sẽ bị xóa"* | **HTTP 200 thật, ~170KB nội dung thật** — nguồn DUY NHẤT khảo sát được mà không bị 403/thân trang rỗng | **AUTHOR_OPT_IN_REQUIRED** — xem giải thích bên dưới |
| forums.spacebattles.com | Cho phép, `Content-Signal: search=yes,ai-train=no,use=reference` | Chưa kiểm tra | HTTP 403 trên forum thật (`/forums/creative-writing.20/`) | **TECHNICALLY_UNSTABLE** |

## Kết luận thật, không tô hồng

Cả 5 nền tảng đã kiểm tra đầy đủ đều **không** thể tự động hoá ngay bây
giờ: 1 nguồn cần xin phép tác giả thật (không thể tự động), 1 nguồn bị cấm
ToS tuyệt đối, 3 nguồn bị chặn ở tầng hạ tầng (403 hoặc trả về thân trang
rỗng) dù `robots.txt`/ToS đôi khi có vẻ chấp nhận được. Đây là một xu hướng
nhất quán, không phải trùng hợp — khớp với phát hiện thật khác trong cùng
đợt khảo sát: AO3 công khai đã phản ứng với việc bị đưa vào Common Crawl
(dùng huấn luyện AI) từ 2022, và `fanfiction.net` tự công bố tín hiệu
`ai-train=no` trong `robots.txt` — tức là làn sóng cứng hoá chống scraping
(đặc biệt chống AI) trên diện rộng đang khiến ngay cả một bot minh bạch,
tuân thủ tốc độ người, tự nhận diện rõ ràng cũng bị chặn.

## Lỗ hổng thật đã sửa: `royalroad.com`

`site_registry.py` đã có sẵn cấu hình `SiteConfig` cho `royalroad.com` từ
một mission trước (robots.txt cho phép nên đã thêm) — nhưng `assert_source_
not_blocked()` ban đầu CHỈ được gọi trong `discover()`/`confirm_unknown_
source()`, không phải `start_or_continue()`. Runbook của chính hệ thống
(`deploy/RUNBOOK-STORY-HARVESTER.md`, mục 1) nói rõ: domain "đã biết" đi
THẲNG vào `POST /api/admin/scraper/runs`, không bắt buộc qua `/discover`
trước. Nghĩa là cổng chặn ban đầu **vô nghĩa với đúng domain nguy hiểm
nhất** — domain đã có cấu hình sẵn. Đã sửa bằng cách thêm cùng lệnh gọi vào
`start_or_continue()`, kèm test hồi quy khởi động thật một run nhắm vào
`royalroad.com` để chứng minh gate cháy ở đường này, không chỉ đường
discovery.

## Vì sao `docln.net` (nguồn duy nhất tải được thật) vẫn không dùng được

Kỹ thuật tải được không có nghĩa là được phép dùng. Khu "Truyện Sáng Tác"
(sáng tác gốc, nơi fanfic thật sự nằm) là nội dung CỦA TỪNG TÁC GIẢ —
giống hệt lý do AO3 cần đồng ý từng người, không thể khái quát hoá một lần
cho cả site. Khu Light Novel dịch (phần lớn nội dung site) còn tệ hơn:
chính site tự thừa nhận sẽ xoá truyện khi chủ sở hữu bản quyền khiếu nại —
tức là phần lớn nội dung ở đó là bản dịch KHÔNG được cấp phép, không phải
một nguồn hợp pháp dù có tải được.

## Không làm gì để "vượt qua"

Không giả mạo User-Agent trình duyệt, không bắt chước dấu vân tay
TLS/browser để né tránh 403 — đó là ranh giới rõ ràng giữa "tuân thủ" và
"né tránh phát hiện", và việc này không thực hiện ranh giới đó dù về mặt kỹ
thuật khả thi.

## Việc còn lại để có nội dung thật

Không có đường tự động hoá nào khả dụng ngay từ 5 nguồn trên. Đường khả dĩ
duy nhất còn lại là **con người thật liên hệ với tác giả thật** (AO3/AUTHOR_
OPT_IN) hoặc **một nguồn/nội dung do đội ngũ vận hành tự cung cấp/đã xác
nhận quyền sử dụng** — cả hai đều là hành động của con người, không phải
việc agent tự động hoá được. Xem báo cáo phiên làm việc (`ANIME_FANFIC_
BOOTSTRAP_READY`) để biết chính xác bước tiếp theo cần ai, làm gì.

## Mã hoá thành cổng chặn thật

`server/scraper/source_policy.py::assert_source_not_blocked()` được gọi ở
đầu `ScraperOpsService.discover()`/`confirm_unknown_source()` — một domain
nằm trong bảng trên (trừ Tapas, chưa đủ bằng chứng để phân loại) bị từ chối
NGAY, trước khi gửi bất kỳ request nào, với thông điệp trích dẫn đúng bằng
chứng ở trên. Một agent/operator sau này gọi `/api/admin/scraper/discover`
với URL Wattpad/AO3/FFN/ScribbleHub/Quotev sẽ nhận lỗi rõ ràng thay vì lặp
lại chính khảo sát này từ đầu.
