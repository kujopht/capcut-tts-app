# Universal Acquisition Engine — bằng chứng thật đa loại nguồn, 2026-08-31

Task #60 (Universal Acquisition Engine Hardening). Bằng chứng THẬT (không
mock, gọi `HttpFetcher`/`AcquisitionRouter` thật, hoặc phiên trình duyệt
thật) qua đúng 6 loại nguồn mission yêu cầu.

## (1) HTML tĩnh — `https://example.com/`

Qua `build_report()` (T0, không cần plugin nào):

```
final_status: AcquisitionStatus.OK
tier_selected: AcquisitionTier.T0_DIRECT
content_hash: ee9e2d05ca9e19c8...
validation_score: 100.0
fallback_reason: T0 (HTTP truc tiep) thanh cong
```

## (2) Trang render JS + (6) một nguồn fanfic/novel

Kết hợp trong MỘT bằng chứng — xem
`docs/reports/t2-browser-rendered-proof-2026-08-31.md` (Task #56):
`docln.net/truyen/14376-thien-su-nha-ben/c109458-...` — T0 lấy được
ciphertext `xor_shuffle`, phiên trình duyệt thật (`mcp__claude-in-
chrome__*`) lấy được toàn bộ ~2.395 từ nội dung chương thật, không có
challenge nào.

## (3) Trang Next.js với `__NEXT_DATA__` — `https://nextjs-commerce.vercel.app/`

Fetch T0 thật (`HttpFetcher`), rồi `extract_embedded_json_blobs()`:

```
LEN raw html: 122269
embedded JSON blobs found: 1
top-level keys: ['props', 'page', 'query', 'buildId', 'runtimeConfig',
                 'nextExport', 'isFallback', 'gsp', 'locale', 'locales',
                 'defaultLocale', 'head']
props keys: ['pageProps', '__N_SSG']
blob size (JSON chars): 56910
```

Đúng hình dạng `__NEXT_DATA__` kinh điển của Next.js Pages Router (không
phải suy đoán — đọc lại chính blob thật lấy được). `find_content_in_json_blob()`
KHÔNG tìm thấy nội dung dài dưới các khoá gợi ý mặc định
(content/body/text/articleBody/html) cho trang thương mại điện tử này —
đây là giới hạn HEURISTIC đã ghi rõ trong docstring của hàm (không phải
lỗi): trang này không đặt nội dung hiển thị dưới các khoá đó.

## (4) Nguồn API công khai/RSS — `https://hnrss.org/frontpage`

Fetch T0 thật, rồi `parse_feed()`:

```
LEN raw xml: 15195
items parsed: 20
first item title: A 12TB Steam "teraleak" spills more than a decade of
                  lost PC gaming history
first item link: https://arstechnica.com/gaming/2026/08/...
first item guid_or_id: https://news.ycombinator.com/item?id=49506182
```

20 mục RSS thật được phân tích đúng, mỗi mục có `title`/`link`/`guid_or_id`
riêng biệt.

## (5) PDF/tài liệu — `https://arxiv.org/pdf/1706.03762`

Fetch T0 thật, rồi `sniff_document_kind()` (từ Task #59):

```
content_type: application/pdf
first bytes: b'%PDF-1.5\n%\xef\xbf\xbd\n137 '
sniff_document_kind -> "pdf"
```

T0 lấy được đúng magic bytes `%PDF-` của một PDF thật (bài báo "Attention
Is All You Need"), `sniff_document_kind` phân loại đúng — hệ thống biết
đây là tài liệu cần T4 (hiện `NotConfiguredDocumentPlugin`, xem Task #59:
honest stub, KHÔNG cố phân tích PDF như thể nó là HTML).

## Tổng kết theo bảng escalation

| Loại nguồn | Tầng dùng thật | Kết quả |
|---|---|---|
| (1) HTML tĩnh | T0 | OK, hash + validation_score thật |
| (2) JS-rendered | T0 thất bại (ciphertext) → T2 | OK qua trình duyệt thật |
| (3) Next.js `__NEXT_DATA__` | T0 + T1 (structured_data) | Blob thật trích xuất đúng cấu trúc |
| (4) RSS/API công khai | T0 + T1 (structured_data) | 20 mục thật phân tích đúng |
| (5) PDF/tài liệu | T0 + sniff (T4 honest stub) | Phân loại đúng, không đoán nội dung |
| (6) Fanfic/novel (docln.net) | T0 thất bại → T2 | Trùng với (2), một dẫn chứng |

Không nguồn nào bị coi là "chặn" chỉ vì T0 thất bại — mỗi trường hợp trên
đều có bằng chứng leo thang thật hoặc phân loại thật (PDF → T4, không cố
dùng T0/T2 sai chỗ).
