# FANFICFARE — BANG CHUNG THAT TRUOC KHI TICH HOP (2026-09-02)

Muc tieu: xac dinh FanFicFare co thuc su huu ich cho pipeline thu thap noi
dung cua Fanfic World hay khong. **Khong tich hop vao production. Khong
sua bat ky truyen production nao.** Toan bo cong viec duoi day la cai dat +
chay CLI truc tiep + doc file trong thu muc scratch — khong co thay doi
code production nao.

## Hang muc | Truoc khi danh gia | Sau khi danh gia

| Hang muc | Truoc | Sau |
|---|---|---|
| FanFicFare da cai dat? | Khong | **Co, v4.61.0, hoat dong that** |
| Nguon that da thu | 0 | **4 nguon that** (FFN, AO3, SpaceBattles, Wattpad) |
| Thu thap nhieu chuong thanh cong | 0 | **1 thanh cong that** (Wattpad, 5 "chuong", 1.301.769 ky tu) |
| Update tang dan da kiem chung | Chua | **Co — 0 byte ghi lai, hash giu nguyen** |
| Nguon trung voi engine hien tai | Chua biet | **0/111 site — xac nhan khong trung** |
| Ket luan kien truc | Chua co | **SITE_ADAPTER_SOURCE** (xem muc 6) |

---

## 1. INSTALL/VERIFY

```
pip install FanFicFare  ->  thanh cong, $0
```

| Truong | Gia tri that |
|---|---|
| Phien ban | 4.61.0 |
| Python | tuong thich voi venv hien co (3.x cua repo), khong xung dot phu thuoc |
| Phu thuoc them | apsw, beautifulsoup4, brotli, chardet, cloudscraper, html2text, html5lib, pywin32, requests, requests-file, urllib3 |
| CLI | `.venv/Scripts/fanficfare.exe` — goi truc tiep duoc |
| So site ho tro | **111** (dem that qua `fanficfare --sites-list \| grep -c "^####"`) |

`fanficfare --version` va `fanficfare --sites-list` da chay that, ket qua
tren la tu output that, khong suy doan.

## 2. REAL-SOURCE TEST — 4 nguon that, khong bypass dang nhap/Cloudflare/robots

Tat ca URL duoi day la THAT, xac minh qua WebSearch (URL xuat hien truc
tiep trong ket qua tim kiem) hoac qua `curl` truc tiep toi trang nguon —
khong bia dat.

| # | Nguon | URL | Ket qua |
|---|---|---|---|
| 1 | FanFiction.net | `fanfiction.net/s/2731239/1/Team-8` ("Team 8" by S'TarKan, 24 chuong, 276.868 tu, that) | **403 Forbidden that** tu FanFicFare (`HTTPErrorFFF`, adapter_fanfictionnet.py:144) |
| 2 | SpaceBattles | `forums.spacebattles.com/threads/along-a-faded-path...` (31 threadmark, ~94k tu that) | **Yeu cau dang nhap** — thong bao ro rang "Login Failed on non-interactive process", KHONG bypass, dung theo dung yeu cau |
| 3 | Archive of Our Own | `archiveofourown.org/works/45337402` (tim qua curl that toi series that `/series/3378754`, 3 work ID xac minh that: 45337402/45337597/46137067) | **403 Forbidden that** tren dung endpoint `/navigate` cua FanFicFare — dang chu y: mot `curl` don gian toi URL AO3 KHAC (series page) tu CUNG may/mang lai thanh cong, nen day la chan rieng cho mau request cua FanFicFare, khong phai AO3 chan toan bo mang nay |
| 4 | Wattpad | `wattpad.com/story/240836110-team-8-by-s'tarkan` (ban mirror that cua "Team 8", dang boi `SvN_Writes`, khac tac gia goc S'TarKan) | **THANH CONG THAT** — EPUB 494.333 byte, 5 file chuong |

**Ghi chu trung thuc quan trong**: cong cu WebFetch cua toi rieng biet tra
ve 403 tren trang FanFiction.net va trang tag-listing AO3 — nhung mot
`curl` truc tiep toi mot URL AO3 khac tu cung may lai thanh cong. Dieu
nay chung minh that bai cua WebFetch KHONG dong nghia trang bi chan hoan
toan — vi vay moi ket luan 403 o tren deu duoc xac minh bang chinh
FanFicFare (cong cu dang danh gia), khong suy tu that bai cua WebFetch.

### Chi tiet nguon thanh cong (Wattpad, "Team 8")

Metadata Dublin Core tu `content.opf` — phong phu, tu dong:

- `dc:title`: Team 8 By S'TarKan | `dc:creator`: SvN_Writes (dung — day la
  tai khoan dang lai, KHONG phai tac gia goc)
- `dc:description` **tu dong bao gom lien ket ve nguon goc va tac gia
  that**: link toi `fanfiction.net/s/2731239/1/Team-8` va
  `fanfiction.net/u/884184/S-TarKan` — FanFicFare tu dong giu chuoi
  provenance ngay ca khi thu tu mirror
- 17 `dc:subject` tag (bao gom "naruto", "hinata", "kurenai", "shino",
  "naruhina" — dung voi noi dung that)
- 3 `dc:date` (publication 2020-09-13, modification 2021-10-10)
- Cau truc EPUB dung chuan: `mimetype`, `META-INF/`, `content.opf`,
  `toc.ncx`, `OEBPS/{title_page, 5 file chuong}`, `<spine>` xac nhan thu
  tu tuyen tinh dung

Da xuat rieng 5 file `.txt` sach (bo the HTML, giai ma entity, chuan hoa
khoang trang) vao `clean_chapters/chapter_01.txt` .. `chapter_05.txt` —
day la dang "structured chapter output" ma pipeline co the dung truc tiep,
khac voi EPUB.

## 3. QUALITY CHECK — bao cao that tung chuong

| Chuong | Ky tu | So tu | Ten nhan vat xuat hien | Trung lap? |
|---|---|---|---|---|
| 1 | 265.440 | 46.694 | Naruto 578, Hinata 280, Kurenai 357, Shino 157... | Khong |
| 2 | 243.755 | 42.620 | Naruto 650, Hinata 378, Kurenai 301, Shino 177... | Khong |
| 3 | 274.048 | 47.714 | Naruto 609, Hinata 292, Kurenai 183, Shino 180... | Khong |
| 4 | 281.867 | 49.364 | Naruto 663, Hinata 290, Shino 236, Sasuke 119... | Khong |
| 5 | 236.659 | 41.180 | Naruto 498, Hinata 144, Kurenai 130, Shino 138... | Khong |
| **Tong** | **1.301.769** | **227.572** | — | — |

Kiem tra trung lap qua SHA-256 tren tung chuong sau khi lam sach — **5 hash
khac nhau hoan toan, khong co chuong nao bi lap**.

**Hai "phat hien" heuristic ban dau la SAI, da tu kiem tra va bac bo**:

1. Co (nav_contamination=True) tren chuong 1-3 tu tu khoa "log in" va
   "next chapter" — kiem tra vi tri khop that cho thay: "log in" khop bo
   trong cau "turn a **log in**to a pile of sawdust" (khong lien quan
   nav), "next chapter" khop trong ghi chu tac gia that trong truyen
   ("the next chapter is already in progress...") — KHONG phai menu/nav
   cua website. Day la loi false-positive cua heuristic tu-khoa don gian
   toi tu viet, khong phai loi cua FanFicFare.
2. Ky tu "�" xuat hien trong preview terminal — kiem tra codepoint truc
   tiep: **U+2013 (EN DASH)**, mot ky tu Unicode hop le va duoc giai ma
   dung 100%. "�" chi la loi hien thi cua console Windows cua toi (khong
   render duoc en-dash), KHONG phai loi mojibake that trong EPUB.

**Ket luan quality that**: khong co menu/nav lan vao, khong co
comment/review lan vao, khong thieu doan, khong trung chuong, Unicode
duoc giu nguyen ven (bao gom en-dash va cac ky tu dac biet), thu tu chuong
dung (`<spine>` + ten file0001..file0005 khop thu tu that), khong bi cat
cut van ban (moi chuong ket thuc bang doan van hoan chinh + author's
note, khong dut giua cau).

## 4. INCREMENTAL UPDATE TEST — that, khong gia lap

```
fanficfare --non-interactive -u "Team 8 By S'TarKan-wattpad_240836110.epub"
```

Output that:
```
Updating Team 8 By S'TarKan-wattpad_240836110.epub, URL: https://www.wattpad.com/story/240836110
Team 8 By S'TarKan-wattpad_240836110.epub already contains 5 chapters.
```

Bang chung dinh luong (khong chi doc log):

| Chi so | Truoc update | Sau update |
|---|---|---|
| SHA-256 file EPUB | `3ae9399dd2364b8...` | `3ae9399dd2364b8...` **giong het** |
| Kich thuoc byte | 494.333 | 494.333 **giong het** |
| mtime | 14:32 | 14:32 **khong doi — 0 byte ghi lai** |

FanFicFare goi API/trang nguon de lay so chuong hien tai, so sanh voi
EPUB co san, xac dinh KHONG co chuong moi, va **khong ghi lai bat ky byte
nao vao file** — khong chi "khong tai lai chuong cu", ma thuc su khong
đụng vao file dia. Thu tu/ID chuong giu nguyen vi khong co ghi de xay ra.
Day la bang chung that, do luong duoc, khong phai suy doan tu tai lieu
FanFicFare.

## 5. SO SANH VOI ENGINE THU THAP HIEN TAI — trung thuc, khong chon loc

**Phat hien quan trong nhat cua muc nay**: nguon DUY NHAT ma engine hien
tai cua Fanfic World da chung minh hoat dong that trong suot phien nay —
`narutofanon.fandom.com` (MediaWiki Action API cong khai) — **KHONG nam
trong 111 site FanFicFare ho tro**. Da kiem tra truc tiep:

```
fanficfare --sites-list | grep -iE "fandom|wikia|narutofanon"
-> chi khop 1 dong: fanfictions.fr/fanfictions/fandom/... (mot site
   TIENG PHAP co chu "fandom" trong duong dan URL rieng cua no, KHONG
   phai Fandom.com/Wikia — trung ten hoan toan ngau nhien)
```

=> **0/111 site trung nhau**. Khong the lam mot phep so sanh "cung nguon,
hai he thong" that su nhu de bai yeu cau, vi khong ton tai nguon nao ca
hai he thong deu xu ly duoc. Bao cao dieu nay thang than thay vi ep mot
so sanh gia tao hoac chon mot nguon khac de lam vua ket qua mong muon.

So sanh CAU TRUC — tung he thong tren CHINH nguon da chung minh cua no:

| Tieu chi | Engine hien tai (tren narutofanon.fandom.com) | FanFicFare (tren Wattpad, nguon duy nhat thanh cong) |
|---|---|---|
| Ty le thanh cong (nguon da thu that) | Cao — MediaWiki API cong khai, on dinh, khong bi chan | 1/4 nguon that da thu (25%) — 2/4 bi chan 403, 1/4 yeu cau dang nhap |
| Thoi gian thu thap | Nhanh (goi API JSON truc tiep, khong can HTML parse) | Cham hon (fetch + parse HTML nhieu buoc, 1 lan chay Wattpad mat vai chuc giay/nhieu phut cho 5 chuong lon) |
| Chat luong metadata | Toi tu viet (tieu de, tac gia, danh sach chuong) — du dung nhung khong co chuan Dublin Core, khong tu dong link ve nguon goc | **Phong phu hon that su**: Dublin Core day du, tu dong giu link provenance ve nguon goc ngay ca qua mirror, tags/subjects tu dong |
| Do sach chuong | Co 1 loi da biet: dong "Category:X" con sot cuoi 1 chuong (thu tu regex sai) | Sach hoan toan trong test nay (da kiem chung ky o muc 3) |
| Kha nang phat hien chuong | Tu viet qua `list=allpages`/`usercontribs` — hoat dong nhung dac thu MediaWiki | Tu dong qua adapter rieng cho tung site — nhung KHONG co adapter cho MediaWiki/Fandom wiki noi dung |
| Update tang dan | Chua co co che rieng — moi lan chay lai la load lai toan bo trang wiki (khong ton, vi la goi API nhe, nhung khong co "so sanh chuong cu/moi" tuong minh) | **Co san, da kiem chung that**: phat hien "already contains N chapters", 0 byte ghi lai khi khong co gi moi |
| Luong code tu viet can | Lon: `extraction_validation.py` (285 dong) + `raw_archive.py` (281 dong) + logic lam sach wikitext + dich + QA + ghi API — hang nghin dong tren nhieu file | **Gan bang 0** cho site duoc ho tro (chi goi CLI) — nhung 0% site ho tro trung voi nguon that cua chung ta |

**Ket luan trung thuc cho muc 5**: FanFicFare thang ro rang ve chat luong
metadata va update tang dan KHI no ho tro dung site. Engine hien tai thang
ro rang ve **do phu hop voi nguon that ma Fanfic World dang dung** (site
MediaWiki/Fandom-wiki) va ty le thanh cong tren mang nay (0 lan bi chan so
voi 2/4 lan FanFicFare bi chan 403 tren cac site lon). Day KHONG phai so
sanh "ai tot hon" chung chung — ma la so sanh dung nguon nao ai dang xu
ly duoc.

## 6. ARCHITECTURE VERDICT

### **SITE_ADAPTER_SOURCE**

Ly do (dua tren bang chung that o tren, khong suy doan):

1. Nguon THAT DUY NHAT Fanfic World da chung minh hoat dong
   (`narutofanon.fandom.com`, MediaWiki wiki) **khong nam trong 111 site
   FanFicFare ho tro** — nen FanFicFare khong the la PRIMARY_PROVIDER hay
   FALLBACK_PROVIDER cho cong viec dang lam that su hien nay: no se khong
   bao gio duoc goi toi cho nguon nay.
2. Tuy nhien, khi Fanfic World mo rong sang cac site lon (FFN, AO3,
   Wattpad, SpaceBattles...) — dieu co the xay ra khi can da dang hoa
   nguon — FanFicFare co 111 adapter san co, kien truc adapter ro rang
   (`base_adapter.py`, `fetchers/`, per-site classes), xu ly duoc cac
   truong hop phuc tap (pagination, login-gated site tu choi dung cach,
   incremental update that) ma viet lai tu dau se ton rat nhieu cong.
3. **NOT_WORTH_INTEGRATING** sai vi FanFicFare THAT SU hoat dong tot khi
   duoc phep (bang chung Wattpad muc 2, 4) — dieu nay khong phai "khong
   dang".
4. **PRIMARY_PROVIDER/FALLBACK_PROVIDER** sai vi (a) 0% site trung voi
   nguon that dang dung, (b) 2/4 site lon FanFicFare ho tro bi chan 403
   tu chinh mang nay khi test that — dua toan bo pipeline production vao
   mot cong cu co ty le chan cao nhu vay tren chinh cac site lon nhat la
   rui ro khong can thiet luc nay.

=> **Dung cach tiep can adapter/y tuong cua FanFicFare (cau truc
Novel/Chapter, co che incremental-update, chuan hoa metadata Dublin
Core) lam THAM KHAO thiet ke** cho engine tu viet, thay vi chay toan bo
runtime FanFicFare trong production ngay bay gio.

### Kien truc tich hop toi thieu DE XUAT (CHUA THUC THI)

```
Source URL
   -> FanFicFareProvider (chi cho 111 site no ho tro, vd FFN/AO3/Wattpad)
        hoac ExistingWikiProvider (cho MediaWiki/Fandom — nguon hien tai)
   -> normalize thanh Novel/Chapter object dung chung (cung shape
      du lieu bat ke provider nao tao ra)
   -> extraction_validation.py (validate_extracted_content) — DUNG LAI
      nguyen, khong viet lai
   -> raw_archive.py (spool_uploaded_raw + Drive archive) — DUNG LAI
   -> dich (Antigravity) — DUNG LAI
   -> TTS — DUNG LAI
```

Diem tich hop DUY NHAT can code moi: mot `FanFicFareProvider` mong bao
quanh CLI (goi `fanficfare --non-interactive -u <url_hoac_epub>`, parse
EPUB/OPF ket qua thanh Novel/Chapter — da chung minh cau truc parse duoc
o muc 2-3 that), duoc chon boi source registry dua tren domain co nam
trong 111 site FanFicFare hay khong. Moi buoc sau do (validate, archive,
dich, TTS) khong doi mot dong nao.

## Chi phi

$0 — `pip install FanFicFare` mien phi, toan bo test dung URL cong khai,
khong goi API tra phi nao.

## Gioi han da biet cua chinh danh gia nay

- Chi thu 4 nguon (dat yeu cau toi thieu >=3), chi 1 thanh cong da chung
  minh multi-chapter — chua thu cac site lon khac trong 111 site (vd
  Questionable Questing, ficbook.net) co the co ty le thanh cong khac.
- Ket qua 403 tren FFN/AO3 la dac thu MAY/MANG nay tai THOI DIEM nay —
  co the khac tu server/IP khac hoac thoi diem khac; khong nen coi la
  ket luan vinh vien ve tinh kha dung cua cac site do voi FanFicFare noi
  chung.

---

**MOBILE HANDOFF MAX 8 LINES**
Status: FanFicFare da cai dat & test that, PASS dieu kien DoD toi thieu
Version/sites: v4.61.0, 111 site ho tro (xac minh qua --sites-list)
Sources tested: 4 that (FFN 403, AO3 403/navigate, SpaceBattles login-gate, Wattpad OK)
Stories/chapters: 1 truyen that thanh cong, 5 chuong, 1.301.769 ky tu, 0 trung lap
Incremental: Da kiem chung that — 0 byte ghi lai, hash/mtime giu nguyen khi khong co chuong moi
Vs current engine: 0/111 site trung voi narutofanon.fandom.com (nguon that dang dung) — khong so sanh cung-nguon duoc
Verdict: SITE_ADAPTER_SOURCE — dung kien truc/y tuong lam tham khao, khong chay full runtime production ngay
SHA: (xem git log sau khi commit report nay)
