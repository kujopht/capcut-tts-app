# FANFICFARE — BANG CHUNG TUY CHON FETCHER CHINH THUC (2026-09-02)

Muc tieu: FanFicFare 4.61.0 da cai san (xem bao cao truoc,
`fanficfare-real-proof-2026-09-02.md`) — kiem tra hai tuy chon fetcher
CHINH THUC cua chinh FanFicFare (`use_cloudscraper`, `use_browser_cache`)
co cai thien ty le thanh cong tren cac nguon that da tung bi chan hay
khong. **Khong tich hop production. Khong tim cach vuot qua/giai
CAPTCHA hay trang thach thuc** — neu gap trang thach thuc thi dung lai
ngay, dung theo dung yeu cau.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| `use_cloudscraper` tren FFN | Chua test | **That, van 403 — khong cai thien** |
| `use_browser_cache` tren FFN | Chua test | **That, cai thien ro ret** — metadata + 24/24 chuong duoc liet ke + 1 chuong That day du |
| `use_browser_cache` tren AO3 | Chua test | **That, khong cai thien** — endpoint noi bo `/navigate` khong duoc cache tu mot lan xem trang binh thuong |
| Ket luan | Chua co | **BROWSER_CACHE_FALLBACK** (pham vi hep, xem muc C) |

## TEST A — CLOUDSCRAPER

Xac nhan `use_cloudscraper:true` la tuy chon THAT (co san trong
`defaults.ini` cua ban cai dat, da duoc dung san cho vai site khac nhu
`quotev.com`/`www.alternatehistory.com`, KHONG dung san cho FFN/AO3 —
da kiem tra truc tiep hai section `[www.fanfiction.net]` va
`[archiveofourown.org]` trong `defaults.ini`, khong co dong
`use_cloudscraper` nao trong do).

Tao `personal.ini`:
```ini
[www.fanfiction.net]
use_cloudscraper:true
```

Chay lai DUNG URL da that bai truoc do:
`https://www.fanfiction.net/s/2731239/1/Team-8`

**Ket qua**: van `403 Client Error: Forbidden`. Traceback xac nhan
`CloudScraperFetcher.request()` THAT SU duoc goi (khong bi bo qua am
tham) — cloudscraper co gang giai bot-check cua no, nhung request van bi
tu choi o tang HTTP truoc khi tra ve bat ky trang thach thuc nao de
giai. Day KHONG PHAI mot trang CAPTCHA/thach thuc — chi la 403 thang —
nen dung lai o day dung quy tac "gap trang thach thuc thi dung", khong
di sau hon.

**Phan loai**: THAT BAI, khong cai thien so voi khong dung cloudscraper.

## TEST B — BROWSER CACHE

Xac nhan `use_browser_cache`/`use_browser_cache_only`/
`browser_cache_path`/`browser_cache_age_limit` la tuy chon THAT (doc
truc tiep tu `defaults.ini`, dong 549-601).

**Firefox khong duoc cai tren may nay** (da kiem tra
`C:\Program Files\Mozilla Firefox\` va ban (x86) — khong ton tai) — chi
Chrome co san, nen dung Chrome thay vi Firefox nhu tai lieu uu tien.

**Ho so trinh duyet RIENG, tach biet**: tao thu muc profile MOI hoan
toan (`--user-data-dir=<thu muc scratch rieng>`), KHONG dung profile
Chrome that/hang ngay cua nguoi dung — dung dung yeu cau "dedicated
profile, not unrelated user browsing data". Mo THAT hai trang bang
`chrome.exe --user-data-dir=... <url1> <url2>` (tai truc tiep, khong qua
script tu dong hoa nao, giong het viec nguoi dung tu mo hai tab):

1. `https://www.fanfiction.net/s/2731239/1/Team-8`
2. `https://archiveofourown.org/works/45337402`

Xac nhan tai THAT qua tieu de cua so (`tasklist /V`): "Team 8 Chapter 1:
The Power of Observation, a naruto fanfic | FanFiction - Google Chrome"
— trang FFN tai thanh cong binh thuong trong trinh duyet that. Kiem tra
thu muc cache co du lieu that (`Cache_Data/data_0..3`, `f_000001..b`,
`index`) truoc khi dong Chrome.

**Dong Chrome truoc khi doc cache** (theo dung khuyen cao cua
FanFicFare ve xung dot khoa file): dong CHINH XAC 10 tien trinh
`chrome.exe` vua liet ke duoc tu ho so moi nay (khong dung lenh dong
hang loat `/IM chrome.exe`, tranh anh huong cua so Chrome khac cua
nguoi dung neu co) — sau khi dong, `tasklist` xac nhan 0 tien trinh
`chrome.exe` con lai.

`personal.ini`:
```ini
[defaults]
browser_cache_path:...\chrome_profile\Default\Cache\Cache_Data
browser_cache_age_limit:-1

[www.fanfiction.net]
use_browser_cache:true
use_browser_cache_only:true

[archiveofourown.org]
use_browser_cache:true
use_browser_cache_only:true
```

### Ket qua FFN — cai thien That su

```
!!!! 23 chapters errored downloading ... !!!!
```
nghe co ve that bai, nhung file EPUB (44.414 byte) van duoc ghi va chua
bang chung THAT quan trong:

| Muc | Ket qua that |
|---|---|
| Tieu de | "Team 8" — **dung, KHONG phai mirror** |
| Tac gia | "S'TarKan" — **dung tac gia goc**, khac voi lan truoc (Wattpad la ban mirror boi nguoi khac) |
| Danh sach chuong | **24/24 chuong duoc liet ke dung** (FFN nhung ca danh sach chuong vao HTML cua MOI trang, nen chi can cache 1 trang la du de biet toan bo danh sach) |
| Chuong 1 (trang duy nhat DA cache) | **THANH CONG day du**: 58.613 ky tu sach, ten nhan vat dung (Naruto 118, Hinata 44, Kurenai 77, Shino 35), mo dau/ket thuc dung doan van hoan chinh, khong cat cut |
| Chuong 2-24 (chua tung duoc mo trong trinh duyet) | Bi danh dau RO RANG "(CHAPTER ERROR)" / "chapter url removed due to failure" — **that bai TRUNG THUC, khong am tham hong hoac tra rong** |

So sanh voi lan thu truc tiep (khong cloudscraper, khong cache) truoc
do: **0% -> that su co metadata + danh sach chuong + 1 chuong that**.
Day la cai thien that, do luong duoc, khong suy doan.

### Ket qua AO3 — khong cai thien

```
fanficfare.exceptions.HTTPErrorFFF: HTTP Error in FFF 'Page not found
or expired in Browser Cache...'(428)
URL:'https://archiveofourown.org/works/45337402/navigate'
```

Nguyen nhan CO CO CHE, khong phai ngau nhien: adapter AO3 cua FanFicFare
can trang con `/works/45337402/navigate` (danh sach chuong rieng) —
mot URL NOI BO adapter tu goi, KHONG phai trang nguoi dung se tu nhien
ghe tham khi xem mot work binh thuong. Xem trang chinh `/works/45337402`
trong trinh duyet KHONG tu dong cache trang `/navigate` do. Co the ep no
hoat dong bang cach CHU DONG mo them URL `/navigate` that trong trinh
duyet — nhung dieu do bat dau giong "di tim dung URL noi bo ma adapter
can" hon la "duyet web binh thuong", nen KHONG lam them buoc do, dung
tinh than cua yeu cau (khong lach qua trang dang nhap/thach thuc).

**Phan loai**: THAT BAI cho AO3 — co che browser-cache KHONG giup site
nay theo cach dung thong thuong.

## TEST C — SO SANH

| Tieu chi | Truc tiep (khong tuy chon) | Cloudscraper | Browser cache |
|---|---|---|---|
| Metadata FFN thanh cong | Khong (403) | Khong (403, cloudscraper da thu that) | **Co that** |
| Danh sach chuong FFN | Khong | Khong | **Co that, 24/24** |
| >=3 chuong FFN thanh cong | Khong | Khong | **Khong** — chi 1/24 (chi 1 trang duoc cache那 luc test) |
| AO3 (bat ky chi so nao) | Khong (403 tren `/navigate`) | Chua test (mission chi yeu cau FFN cho Test A) | **Khong** — endpoint noi bo khong khop cach cache tu nhien |
| Do sach noi dung khi co | — | — | **Sach hoan toan** (chuong 1 FFN: dung ten nhan vat, dung doan mo/ket, khong loi HTML) |
| Kha nang update tang dan | Da chung minh o bao cao truoc (tren nguon Wattpad thanh cong) | Chua test lai rieng lan nay | Chua test lai rieng lan nay — ve mat co che, van dung CHUNG pipeline ghi/so sanh EPUB nhu moi fetcher khac nen KHONG co ly do ky thuat de khac, nhung chua co bang chung THAT rieng cho ket hop nay |
| Tinh thuc te khi tu dong hoa | Don gian nhung bi chan | Don gian bat, nhung khong giup gi | **Han che**: can NGUOI DUNG (hoac mot phien duyet web THAT) da tung mo TUNG trang chuong truoc do — voi truyen 24 chuong nghia la phai mo ca 24 URL that trong trinh duyet truoc, khong phai mot buoc "bat cong tac roi xong" |

## KET LUAN — mot trong nam lua chon

### **BROWSER_CACHE_FALLBACK**

Ly do:

1. Cloudscraper cho ket qua **0 cai thien that** tren mau test nay — bi
  loai truoc.
2. Browser cache cho ket qua **cai thien that, do luong duoc** (metadata
  + danh sach chuong + 1 chuong day du cho FFN, tu 0% len co du lieu
  su dung duoc) — nhung CHI o pham vi hep: hoat dong tot cho truong hop
  "nguoi dung DA doc chuong nay trong trinh duyet cua chinh ho, muon he
  thong luu lai" — dung boi canh FanFicFare tu mo ta tinh nang nay cho
  ("cach giai quyet cho mot so site chan tai tu dong").
3. KHONG du manh de la nguon chinh (`PRIMARY`) hay ap dung cho ca hai
  fallback (`BOTH_FALLBACKS`, vi cloudscraper khong dong gop gi) — va
  KHONG phai "khong dung" (`NOT_USEFUL`) vi bang chung cai thien FFN la
  that va co the huu ich cho dung mot kich ban hep: nguoi van hanh da
  doc/luot qua mot truyen trong trinh duyet that su.
4. Rui ro/chi phi tu dong hoa: de dung o quy mo lon can mo THAT tung
  trang chuong trong trinh duyet truoc — dieu nay tu no khong con la
  "tu dong hoa" nua ma gan voi "duyet thu cong quy mo lon", nen KHONG
  de xuat lam nen tang cho pipeline thu thap hang loat.

**KHONG tich hop production tu ket luan nay** — dung theo yeu cau cua
mission. Neu sau nay can dung, pham vi hop ly la mot fallback TUY CHON
cho dung truong hop "nguoi dung/nguoi van hanh da xem truoc trong trinh
duyet That", khong phai co che thu thap chinh.

## Don dep

Da dong toan bo 10 tien trinh Chrome cua ho so test rieng (xac nhan qua
`tasklist` — 0 con lai). Khong dong nao trong so nay la cua so Chrome
khac cua nguoi dung. Thu muc profile/cache/personal.ini deu nam trong
`scratchpad`, khong dua vao repo.

## Chi phi

$0 — chi dung cac cong cu/tuy chon co san mien phi (cloudscraper la phu
thuoc da cai san cua FanFicFare, Chrome la trinh duyet co san tren may).

---

**MOBILE HANDOFF MAX 7 LINES**
Status: Ca hai tuy chon fetcher chinh thuc da test that, khong tich hop production
Cloudscraper: That bai — van 403 tren FFN, cloudscraper da thu that nhung khong vuot qua duoc
Browser cache: Cai thien that tren FFN (metadata + 24/24 danh sach chuong + 1 chuong day du sach); AO3 khong cai thien (endpoint /navigate khong duoc cache tu xem trang thuong)
FFN: 403 truc tiep -> 403 cloudscraper -> THANH CONG mot phan qua browser cache
AO3: 403 truc tiep -> browser cache cung that bai (mismatch endpoint noi bo)
Verdict: BROWSER_CACHE_FALLBACK — pham vi hep (nguoi dung da xem truoc), khong phai co che thu thap chinh
SHA: (xem git log sau khi commit)
