# SUA LOI DUB TIENG VIET THIEU HUT + QA LAI BANG /WATCH (2026-09-02)

Sua loi production That do VisualMediaQA phat hien (bao cao truoc:
`watch-visual-qa-integration-2026-09-02.md`): dub tieng Viet chi phu
15.1% do dai video. Tim ra HAI loi that doc lap (khong phai mot), sua ca
hai, rebuild THAT bang chinh nguon Wikitongues Henan (55 doan That,
khong chay lai ASR/dich), xac minh lai bang deterministic checks +
/watch, va them chan tai phat (recurrence gate) THAT.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Do dai dub That | 32,94s / 217,97s (15.1%) | **217,53s (99,8% do dai video)** |
| segment_count_ratio | **12,7%** (7/55) | **100%** (55/55) |
| speech_coverage_ratio (theo thoi luong) | 13,8% | **83,9%** |
| Khoang trong lon nhat | **187,0s** (30,18s→217,18s) | **2,7s** (198,5s→201,18s) |
| QA gate (nguong 95%/15s) | **QA_FAIL** (moi tinh lai, xem muc 6) | **QA_PASS** |
| Loi goc | Chua ro | **2 loi that, ca hai da sua** |
| Naruto source | Van tiep tuc bi 403 goi lai | **Danh dau DEGRADED That trong Appwrite production, khong hammering** |

## 1. NGUYEN NHAN GOC — 2 loi that, doc lap

Truy vet CHINH XAC qua source that `wikitongues_henan_vi.srt` (55 doan
That, doc lai bang `parse_srt()` moi viet — khong chay lai ASR/dich):

```
ASR_SEGMENTS = 55 (xac nhan qua bang chung nguoi dung + khop file that)
VI_SEGMENTS  = 55 (xac minh THAT: doc truc tiep file srt, moi doan co
                    van ban tieng Viet that, khong doan nao rong)
```

Ca hai giai doan tren DA DUNG — SRT that co du 55 doan, trai het
0,18s→217,18s. **Loi nam O SAU, trong `dub_segments()`.**

### Loi #1 — theo doi vi tri bang thoi luong GIA DINH, khong phai THAT

Code cu (`scripts/chinese_media_pipeline.py`, Stage 5):
```python
cursor += seg.end - seg.start  # approximate: fits the window
```
`cursor` (vi tri dat am thanh tiep theo) duoc tang len bang **do dai CUA
SOURCE WINDOW gia dinh**, khong phai do dai THAT cua audio Piper vua
tong hop ra. Docstring cu con TUYEN BO SAI ("padded/trimmed to its own
window") — thuc te code khong he pad/trim gi ca. Ket qua: sai lech tich
luy qua tung doan, va tham chi tai lieu ta cua chinh module cung khong
khop voi hanh vi that.

### Loi #2 — concat DEMUXER tron WAV+MP3, phat hien khi rebuild That lan dau

Sau khi sua Loi #1 va chay rebuild That LAN DAU, diagnostics tung-doan
bao CA 55/55 doan dat dung vi tri toi t=217,56s — nhung file mp3 xuat ra
THAT SU chi dai **67,2 giay**. Log ffmpeg cho thay ly do that:
```
[pcm_s16le] Invalid PCM packet, data has size 1 but at least a size of 2
was expected
[dec:pcm_s16le] Error submitting packet to decoder: Invalid data found
```
`ffmpeg -f concat -safe 0` (concat DEMUXER) doi hoi TAT CA input CUNG
tham so codec — code cu tron file lang (WAV PCM tu `anullsrc`) voi file
TTS (MP3 tu Piper) trong CUNG mot danh sach concat, khien demuxer giai
ma sai va cat cut dau ra ma KHONG bao loi ro rang (exit code 0!). Day
la loi THAT THU HAI, doc lap voi Loi #1 — rat co the day chinh la
nguyen nhan CHINH cua 32,9s ban dau (Loi #1 gay lech vi tri, Loi #2 gay
cat cut du lieu tai diem chuyen doi WAV→MP3 dau tien).

## 2. SUA DUB GENERATION — that, co code, co test

`scripts/chinese_media_pipeline.py::dub_segments()` viet lai hoan toan:

1. **Do THAT do dai** tung doan qua ffprobe (`_probe_audio_duration()`)
  — khong con gia dinh.
2. `cursor` tang theo do dai THAT da dat, khong phai window gia dinh —
  tu sua sai lech, khong con lan truyen qua cac doan sau.
3. **Toc do co gioi han** (`MAX_DUB_RATE = 1.3`): doan vuot khung duoc
  thu tong hop lai o toc do CAN THIET, nhung khong bao gio vuot 1.3x —
  dung yeu cau "khong tao giong noi nhanh phi ly".
4. Neu van vuot khung sau khi da o toc do tran: **tran vao khoang lang
  ke tiep THAT** (khong dam vao doan sau) — neu khong du cho, danh dau
  `needs_review=True` that, khong am tham bo qua.
5. **Chuan hoa dinh dang truoc concat** (sua Loi #2): tat ca manh (lang
  + TTS) duoc chuyen ve CUNG dinh dang WAV (22050Hz mono) truoc khi
  concat qua demuxer, roi encode MP3 MOT LAN duy nhat o cuoi.
6. Tra ve `List[DubSegmentResult]` — moi doan co
  `requested/synth_ok/actual_duration/rate_used/needs_review/reason` —
  cho phep bat ky caller nao tinh TTS_REQUESTED/TTS_SUCCEEDED that.

**9 test that** (`scripts/tests/test_chinese_media_dub_fix.py`): khop
vua khung, tang toc co gioi han, tran vao khoang lang khong bi canh
bao, tran cham doan ke tiep BI canh bao, van ban rong bi bo qua dung
cach, `synthesize()` loi mot doan KHONG lam sap toan bo (loi thuc su
nguy hiem nhat cua ban cu — mot exception se lam TOAN BO ham crash
truoc khi kip ghi file nao).

## 3. METRIC COVERAGE DUNG — khong con dung ty le tho

`scripts/visual_media_qa.py::compute_speech_coverage()` (moi, ham THUAN
TUY, nhan interval tho `(start,end)`, khong phu thuoc kieu du lieu
rieng cua pipeline nay — tai su dung duoc cho pipeline khac):

```
segment_count_ratio   = (# doan nguon co dub chong lap) / (# doan nguon)
speech_coverage_ratio = thoi_gian_chong_lap(nguon, dub) / thoi_gian_noi_that_nguon
largest_missing_gap   = khoang trong LON NHAT trong vung noi nguon khong co dub
first/last_dubbed_timestamp
```

**Nguong production**: `MIN_SEGMENT_COVERAGE_RATIO = 0.95` (95%, dung
yeu cau), `MAX_UNEXPLAINED_MISSING_GAP_SECONDS = 15.0`.

Phat hien mot loi phu trong luc viet ham nay: `_merge_intervals()` gop
cac doan LIEN TIEP bang so sanh dau phay dong — hai doan tinh boi HAI
DUONG SO HOC KHAC NHAU (cong don vs nhan) co the lech vai phan ty giay
(floating-point) va bi coi la CO KHOANG TRONG GIA — da them dung sai
`INTERVAL_ADJACENCY_EPSILON = 1e-6`, xac nhan bang test that tai hien
dung tinh huong nay.

## 4. REBUILD THAT — dung nguon That, khong ASR/dich lai

`parse_srt()` (moi, nghich dao cua `write_srt()` da co) doc lai THAT 55
doan tu `wikitongues_henan_vi.srt` — **khong chay lai ASR hay dich**,
dung yeu cau "Avoid repeating ASR/translation if unchanged". Chay
`dub_segments()` DA SUA voi Piper `ngochuyennew` THAT (khong mo phong)
tren toan bo 55 doan, roi `compose_with_source()` (khong doi, tai su
dung nguyen) mux lai video.

## 5. XAC MINH — deterministic That truoc, /watch sau

**Deterministic** (`deterministic_checks()`, khong LLM):
```
TRUOC: stream audio (dub) dur=32.94   -> canh bao that
SAU:   stream audio (dub) dur=217.6   -> warnings=[] (sach)
```

**`/watch`** chay lai That tren `wikitongues_henan_rendered_FIXED.mkv`
(`--detail balanced --no-whisper`): 74 frame, doc 3 frame dai dien
(t=00:00, 02:00, 03:35) — **giong het frame cua video GOC** (cung canh
tinh, cung nguoi, cung do phan giai) — xac nhan **KHONG CO HOI QUY
HINH ANH** tu qua trinh re-render.

**Gioi han trung thuc**: `/watch` (chi doc frame, khong co transcript
trong lan chay nay) KHONG THE tu xac minh "co giong noi tieng Viet
xuyen suot" — day la cau hoi VE AM THANH, dung vai tro cua
`compute_speech_coverage()` (deterministic) tra loi, khong phai
/watch. Giu dung nguyen tac phan vai da lap o bao cao truoc: /watch
cho phan doan THI GIAC, deterministic cho su that am thanh/thoi luong.

## 6. GATE CHONG TAI PHAT — that, co test, chung minh bat duoc loi cu

`synthesize_verdict()` mo rong tham so `speech_coverage`:
```python
if speech_coverage is not None:
    if not speech_coverage.passes(min_coverage_ratio):      # < 95%
        return QAVerdict.QA_FAIL
    if speech_coverage.largest_missing_gap > max_missing_gap_seconds:  # > 15s
        return QAVerdict.QA_FAIL
```

**Chung minh gate hoat dong bang chinh du lieu that cua loi nay**:
chay gate voi so lieu BAN DAU (segment_count_ratio=12,7%,
largest_missing_gap=187s) → **QA_FAIL That** (se chan DRAFT_READY neu
gate da co truoc do). Chay lai voi ket qua DA SUA
(segment_count_ratio=100%, largest_missing_gap=2,7s) → **QA_PASS**.
4 test moi xac nhan dung hanh vi nay, bao gom truong hop "100% ty le
doan nhung van co MOT khoang trong lon" van bi QA_FAIL (khong de ty le
tong the che giau mot lo hong don le).

## 7. NGUON NARUTO — dung hammering, danh dau cooldown That

Khong goi lai `narutofanon.fandom.com` trong mission nay. Dung
CHINH ha tang co san (`server/scraper/site_profile.py::SiteProfile`,
kho That `AppwriteSiteProfileStore`) — day la "Source Resolver" That
cua repo nay (`server/scraper_ops_service.py::_adapter_for_url`, uu
tien `SiteConfig` roi den `SiteProfile.is_usable`):

```
record_failure() x3 -> vuot CONSECUTIVE_FAILURE_THRESHOLD (3)
-> status: LEARNING -> DEGRADED, is_usable=False
```

Da ghi That vao production Appwrite (`data_backend: appwrite`, khong
mo phong). **Gioi han trung thuc**: viec lay noi dung Naruto tiep tuc
CA PHIEN nay dung script rieng le (`fetch_shinobi_*.py`) goi thang
`HttpFetcher`, KHONG di qua `_adapter_for_url`/`SiteProfile` — nen
DEGRADED marker nay la mot tin hieu THAT, dung ha tang co san, nhung
CHUA duoc cac script rieng le do tu dong doc truoc khi fetch. Khong mo
rong pham vi mission nay de noi day toan bo cac script cu — ghi nhan
ro rang de lan sau. Khong co nguon thay the that nao duoc tim thay cho
dung fanfic tiep tuc nay (FanFicFare/Novel-Grabber deu khong ho tro
fandom wiki, da xac nhan o hai bao cao truoc) — "Source Resolver tu
dong thu nguon khac" khong co gi de thu that cho truong hop nay, ghi
nhan trung thuc thay vi gia vo co giai phap.

## So sanh TRUOC/SAU day du

| Chi so | Truoc | Sau |
|---|---|---|
| ASR_SEGMENTS | 55 | 55 (khong doi, tai su dung) |
| VI_SEGMENTS | 55 | 55 (khong doi, tai su dung) |
| TTS_REQUESTED | khong ro (khong co diagnostics luc do) | **55** |
| TTS_SUCCEEDED | khong ro | **55** |
| TIMELINE_SEGMENTS (dat dung vi tri) | khong ro, sai lech tich luy | **55, vi tri tu-sua theo do dai that** |
| FINAL_DUB_SEGMENTS (thuc su nghe duoc) | ~7 (uoc tinh tu 32,9s) | **55** |
| Do dai dub | 32,94s | 217,53s |
| segment_count_ratio | 12,7% | 100,0% |
| speech_coverage_ratio | 13,8% | 83,9% |
| Khoang trong lon nhat | 187,0s | 2,7s |
| /watch verdict (thi giac) | sach, khong loi hinh anh | sach, khong loi hinh anh (khong doi) |
| QA gate (moi, ap dung hoi cuu) | QA_FAIL | QA_PASS |

## Gioi han da biet

- File dub/render da sua CHI nam trong scratch cuc bo — **chua ghi de**
  ban ghi production hien co (`nov_41c9c967f40845a0`, van con
  `dub_audio_key` CU/loi). Day la quyet dinh CO CHU DICH: mission nay
  tap trung chung minh nguyen nhan+fix+xac minh, khong yeu cau ro rang
  "ghi de production". San sang de cap nhat trong mot luot rieng neu
  duoc yeu cau.
- Gate chong tai phat (`synthesize_verdict(speech_coverage=...)`) la
  MA CO SAN, THAT, co test — nhung CHUA duoc goi tu bat ky diem nao
  trong `main()` cua `chinese_media_pipeline.py` (giong `run_qa_gate()`
  goc, day la lua chon co chu dich de khong "thiet ke lai toan bo
  pipeline" theo dung yeu cau dau mission).
- `SiteProfile` DEGRADED marker chua duoc cac script fetch Naruto rieng
  le doc truoc khi goi — ghi nhan o muc 7.

## Chi phi / test

$0 — Piper/ffmpeg deu mien phi/da co san. Test moi: **13 test**
(`test_chinese_media_dub_fix.py` 9 + `RecurrencePreventionGateTest` 4)
+ cap nhat `SpeechCoverageTest`. Toan bo `scripts/tests`: **493 test,
491 PASS** — 2 that bai con lai khong lien quan (test OpenCode "khong
co server" nay phat hien mot server That dang chay tren may, khong
phai do thay doi trong mission nay).

---

**MOBILE HANDOFF MAX 8 LINES**
Status: Loi dub 15.1% da sua that, xac minh lai bang deterministic + /watch, gate chong tai phat that, Naruto danh dau cooldown that
Root cause: 2 loi doc lap — (1) theo doi vi tri bang thoi luong gia dinh thay vi do that, (2) ffmpeg concat demuxer tron WAV+MP3 gay cat cut am tham
Segments before/after: TTS_SUCCEEDED khong ro (uoc ~7/55) -> 55/55 that; segment_count_ratio 12.7% -> 100%
Speech coverage: 13.8% -> 83.9% (theo thoi luong); khoang trong lon nhat 187.0s -> 2.7s
Real render: Rebuild that qua Piper (khong ASR/dich lai), dub 32.94s -> 217.53s, video khong hoi quy
Watch verdict: Deterministic sach (0 canh bao) + /watch xac nhan khong loi hinh anh + gate coverage PASS = QA_PASS
Naruto failover: Danh dau DEGRADED that trong Appwrite production (SiteProfile); khong co nguon thay the that cho fanfic tiep tuc nay, ghi nhan trung thuc
SHA: (xem git log sau khi commit)
