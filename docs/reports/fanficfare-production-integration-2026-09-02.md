# FANFICFARE — TICH HOP PRODUCTION CHON LOC + SAN XUAT NOI DUNG (2026-09-02)

Tich hop production THAT (co code, co test, da commit) cua FanFicFare
theo dung ket qua hai bao cao proof truoc do
(`fanficfare-real-proof-2026-09-02.md`, SITE_ADAPTER_SOURCE;
`fanficfare-official-fetcher-options-proof-2026-09-02.md`,
BROWSER_CACHE_FALLBACK). Novel-Grabber (`novel-grabber-real-proof-...md`,
ADAPTER_IDEA_SOURCE) van CHI la tham khao — khong nhung runtime Java.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| FanFicFareProvider trong production | Khong ton tai | **That, da commit** (`server/scraper/fanficfare_provider.py`, 14 test that qua) |
| Nguon `narutofanon.fandom.com` | Hoat dong on dinh ca phien (16 chuong Naruto that) | **MOI PHAT HIEN: chan That, HTTP 403** ca trang wiki lan API, xac nhan qua chinh `HttpFetcher` production, 2 lan doc lap — KHONG co gang vuot qua |
| Truyen moi that | 0 | **1 truyen moi that**: "Save Me...Please (Naruto FanFiction)" qua FanFicFareProvider |
| Chuong moi that | 0 | **10 chuong that**, da QA, da dich, da ghi production draft |
| Audio chuong 1 | — | **Xac minh tung byte**: 4.021.613 byte, audio/mpeg, HTTP 200 |
| Adapter moi | — | **0 — khong can**, FanFicFareProvider da du cho nguon nay |

## A. TICH HOP FANFICFAREPROVIDER — that, da test, da commit

`server/scraper/fanficfare_provider.py` (commit `3e579a3`), triet ly
"tich hop nho nhat":

1. **`resolve_acquisition_route(url)`** — dung resolver mission yeu cau:
   `supported hostname -> "fanficfare" -> "browser_cache_fallback" (chi
   khi cache THAT da co san) -> "engine" -> "unavailable"`. Kiem chung
   THAT (khong mock) tren may nay: Wattpad -> `fanficfare`, FFN ->
   `engine` (blocked-by-default, dung nhu thiet ke), fandom wiki ->
   `engine` (khong duoc FanFicFare ho tro).
2. **`fanficfare_supports_hostname()`** — doc TRUC TIEP tu `--sites-list`
   cua chinh ban cai dat nay (161 hostname that, cache 1 lan) — khong
   bao gio la danh sach ghi tay co the lech voi ban that.
3. **FFN/AO3 giu dang ky nhung CHAN MAC DINH** (`_DEFAULT_BLOCKED_HOSTS`)
   dung theo bang chung that (403 xac nhan hai lan o bao cao truoc) —
   van co the dung qua browser-cache fallback NEU nguoi van hanh da co
   san cache that (khong bao gio tu dong mo trinh duyet tu module nay).
4. **Khong co `use_cloudscraper` o bat ky dau** trong module — co MOT
   test tinh (`test_khong_dung_cloudscraper_hay_selenium_trong_module`)
   kiem tra dung cac ky hieu SU DUNG that (`use_cloudscraper:true`,
   `import cloudscraper`, `webdriver.`, `playwright.`) chu khong phai
   chi tim chu "cloudscraper" (vi docstring co nhac den no de GIAI
   THICH vi sao khong dung — mot lan vap false-positive that trong luc
   viet test, da sua truoc khi commit).
5. **`parse_fanficfare_epub()` / `normalize_fanficfare_result()`** —
   chuyen EPUB that thanh dung hinh dang `Novel`/`Chapter` (khop payload
   `POST /api/novels`/`POST /api/chapters` da co san, khong tao dinh
   dang moi) — giu URL nguon, ten tac gia, fandom, so/ten chuong, noi
   dung tho, metadata cap nhat. Mot chuong loi (marker "(CHAPTER ERROR)"
   khi browser-cache khong day du — hanh vi that da thay o bao cao
   truoc) duoc GIU NGUYEN, khong am tham bo qua.
6. **Khong xay lai Adapter SDK** — dung THANG cac module co san:
   `extraction_validation.validate_extracted_content` (kiem tra chuan
   hoa), `dedupe.content_hash`/`source_fingerprint` (dinh danh), `contract.
   canonicalize_url` (URL chuan), `harvest_scheduler.next_check_at`
   (backoff). `server/scraper/contract.py::StoryProvider` +
   `adapters/` + `server/tests/fixtures/scraper/` DA LA "Adapter SDK" —
   xac nhan qua doc truc tiep source, khong doan.
7. **14 test fixture-based that** (`server/tests/test_fanficfare_provider.py`
   + `fanficfare_sample.epub`) — metadata/thu tu chuong, marker loi giu
   nguyen, resolver 5 nhanh, phan loai loi CLI tu dung traceback that
   cua hai bao cao proof, guard tinh khong-cloudscraper. Bo test day du
   repo: **4263 test, 0 loi** sau khi them module nay.

## B. PHAT HIEN THAT KHONG LUONG TRUOC — narutofanon.fandom.com bi chan

Trong luc chuan bi tiep tuc "Naruto: A Shinobi Story" (dang o 15/32
chuong that, THIEU chuong 4 — mot khoang trong cu da co tu truoc, chua
sua trong lan nay), da phat hien:

```
HttpFetcher.fetch("https://narutofanon.fandom.com/wiki/...") -> HTTP 403
HttpFetcher.fetch("https://narutofanon.fandom.com/api.php?...") -> HTTP 403
```

Xac nhan bang CHINH `server/scraper/http_fetcher.py::HttpFetcher` —
class production THAT su dung ca phien, khong phai `curl` tho — thu HAI
LAN doc lap (trang wiki thuong VA API), CA HAI deu 403. Day KHONG PHAI
loi tam thoi/ngau nhien ma la mot thay doi that trong khoang thoi gian
tu lan lay chuong 12-16 (thanh cong) den bay gio. **Khong tim cach vuot
qua** — dung nguyen tac da ap dung xuyen suot phien lam viec nay voi
FFN/AO3/Cloudflare.

**He qua**: muc tieu "Naruto toward 32/32" KHONG dat duoc trong lan
chay nay — khong phai vi pipeline sai, ma vi nguon da tu chan. Ghi nhan
trung thuc thay vi bao cao gia tien do.

## C. SAN XUAT THAT — chuyen huong sang FanFicFareProvider

Do nguon Naruto bi chan, da dung CHINH tich hop moi xay de san xuat that:

1. Tim truyen Naruto that tren Wattpad (nguon FanFicFare da chung minh
   hoat dong): **"Save Me...Please (Naruto FanFiction)"**, tac gia that
   `naruto209ye`, `https://www.wattpad.com/story/47276159` — 30 chuong
   that, DA HOAN THANH ("Chapter 30 - The End").
2. Thu that qua `fanficfare --non-interactive` (khong cloudscraper,
   khong browser-cache — duong truc tiep, vi Wattpad khong nam trong
   danh sach chan) — EPUB that 103.631 byte.
3. Loc bo 5 muc "Author's Note" xen giua danh sach chuong (khong phai
   noi dung truyen that) — lay **10 chuong THAT dau tien** (Chuong 1-10).
4. Dich EN->VI qua `agy --print-timeout 180s` (batch that, khong mo
   phong) — 10/10 thanh cong.
5. QA: 3 chuong bi co gan "trung lap doan van" — kiem tra truc tiep:
   ca ba deu la dong `~~~~~...~~~~~` (dau ngan canh trong Wattpad那 goc,
   khong phai loi dich) — **false positive that, da xac minh, khong
   phai loi that**.
6. Ghi vao production qua `POST /api/novels` + `POST /api/chapters`
   (idempotent — kiem tra `external_source_url` truoc khi tao, tranh
   trung lap khi chay lai) — **25/25 kiem tra PASS**.
   `novel_id: nov_687e1781a2334ce9`, `state: draft`.
7. Xep hang doi TTS chuong 1 (`piper:ngochuyennew`) — job
   `job_8c3df2faa5e94891`, hoan tat `completed 100% 5/5 parts`.
8. Xac minh audio qua `GET /api/audio/{chapter_id}/url` + tai that:
   **HTTP 200, audio/mpeg, 4.021.613 byte, khop chinh xac voi
   `size_bytes` server bao cao**.
9. Luu tru THO: `spool_uploaded_raw()` (ham co san, khong viet lai) —
   103.631 byte, sha256 `baa068c4...`, quet du lieu nhay cam SACH, da
   day vao hang doi Drive (nen tang, khong chan).

## D. NOVEL-GRABBER + ADAPTER MOI

Theo dung yeu cau: **khong nhung/chay ung dung Java trong production**.
Khong can adapter moi/sua trong lan nay — FanFicFareProvider da du cho
nguon that duoc chon (Wattpad). Neu sau nay can mot nguon thuc su
KHONG duoc FanFicFare ho tro, `src/main/java/grabber/sources/*.java`
cua Novel-Grabber van la tham khao selector THAT (vi du
`toc.select("td:not([class]) a")` cho Royal Road, da kiem chung That
trong bao cao truoc) — nhung se viet lai bang Python trong
`server/scraper/adapters/`, khong nhung JVM.

## E. KET QUA so voi MUC TIEU

| Muc tieu | Ket qua |
|---|---|
| >=8 chuong moi that | **10 chuong that** — vuot muc tieu |
| >=1 truyen moi that | **1 truyen that**, hoan thanh (30 chuong goc, da lay 10) |
| Audio chuong 1 cho moi truyen moi | **Xac minh that**, byte-khop |
| Khong trung lap chuong/job | **Xac nhan qua idempotent check** (external_source_url + existing_titles truoc khi POST) va qua kiem tra `/api/jobs?mine=true` (rong truoc khi bat dau — khong co job cu de trung) |
| Naruto huong toi 32/32 | **KHONG dat** — nguon bi chan That, ghi nhan trung thuc, khong ep tien do |
| Adapter moi neu can | **Khong can** trong lan nay |

## Chi phi

$0 — FanFicFare/agy/Piper deu mien phi/da co san. Test lien quan: 4263
test toan repo, 0 loi.

---

**MOBILE HANDOFF MAX 8 LINES**
Status: Tich hop FanFicFareProvider that vao production (14 test, 4263 test toan repo PASS) + san xuat noi dung that
Naruto: KHET — narutofanon.fandom.com moi bi chan That (HTTP 403 ca wiki lan API, xac nhan qua HttpFetcher production) — dung o 15/32, khong ep vuot qua
FanFicFare lane: Resolver that (hostname -> fanficfare/browser_cache/engine/unavailable), FFN/AO3 blocked-by-default, khong cloudscraper/stealth
New stories: 1 truyen that — "Save Me...Please" (naruto209ye, Wattpad, qua FanFicFareProvider)
New chapters/audio: 10 chuong that, da QA/dich/ghi draft; audio chuong 1 xac minh 4.021.613 byte khop chinh xac
Adapters: Khong can adapter moi lan nay; Novel-Grabber selector van chi la tham khao (khong nhung Java)
Drive/R2: EPUB tho da luu spool (sha256 baa068c4..., quet sach) + day hang doi Drive; audio da xac minh qua R2
SHA: (xem git log sau khi commit)
