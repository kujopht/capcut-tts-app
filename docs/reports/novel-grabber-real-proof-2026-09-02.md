# NOVEL-GRABBER — BANG CHUNG THAT (2026-09-02)

Muc tieu: Novel-Grabber co bo sung do phu that su ngoai engine hien tai +
FanFicFare hay khong. **Khong tich hop production.**

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Da cai/build That? | Khong | **Co — build tu source hien tai, JDK+Maven cai moi qua winget/Apache chinh thuc** |
| So site ho tro | Chua biet | **104 site parser That** (dem truc tiep tu thu muc source, khong tinh 2 file khung `Source.java`/`manualSource.java`) |
| Nguon that da thu | 0 | **3 nguon that**: Royal Road (THANH CONG), Syosetu/Re:Zero (LOI that), WuxiaWorld (LOI that) |
| Che do manual/generic | Chua biet | **KHONG the goi qua CLI — gan cung voi Swing GUI trong code hien tai** (bang chung tu source) |
| Ket luan | Chua co | **ADAPTER_IDEA_SOURCE** |

## 1. INSPECT UPSTREAM

Repo that: `github.com/Flameish/Novel-Grabber` (xac minh qua `gh api`, khong
suy doan tu ket qua tim kiem):

| Truong | Gia tri that |
|---|---|
| Tao luc | 2019-02-06 |
| Giay phep | MIT |
| Sao/Fork/Theo doi | 611 / 89 / 34 |
| Commit tren `master` | 795 |
| **Commit THAT gan nhat tren `master`** | **2024-12-30** (`7a29e468`) — ~1 nam 8 thang truoc thoi diem bao cao nay |
| `pushed_at` cua repo (GitHub API) | 2026-08-09 — **GAY NHAM**: da kiem chung day la mot nhanh `dependabot/maven/...` (bot tu dong nang cap phu thuoc `jsoup`), KHONG phai code that cua con nguoi. Nhanh `dev` con cu hon: 2021-10-12 |
| Ban phat hanh (Release) gan nhat | `3.9.2`, xuat ban **2021-04-20** — cu hon 5 nam |
| Phien ban NOI BO trong `pom.xml` hien tai | `3.10.3` — **~40 commit da xay ra SAU ban phat hanh cuoi cung ma khong bao gio duoc dong goi thanh Release moi** |
| Yeu cau Java | 8+ (xac minh `maven.compiler.target=1.8` trong `pom.xml`) — **Java KHONG co san tren may nay**, da cai Microsoft OpenJDK 17 qua winget (chinh thuc, co ky so, co the go bo) de test |
| CLI | That, xac nhan qua `java -jar ... -help`: `-link`, `-wait`, `-headless {chrome/firefox/opera/edge/IE}`, `-chapters`, `-path`, `-login`, `-account`, `-displayTitle`, `-invertOrder`, `-noDesc`, `-getImages` |
| Update/watch | Co class `library/Library.java` va co dieu kien `window.equals("checker")` trong `CLI.java` — **NHUNG khong co CO flag CLI nao kich hoat che do checker/library** trong `-help` — chi thay duoc qua GUI |
| Manual/generic | Co (`manualSource.java`, dung thu vien `Readability4JExtended` — cung ho Readability.js cua Mozilla) — **nhung constructor doc truc tiep tu mot o nhap Swing GUI** (`init.gui.manChapterContainer.getText()`), khong co duong CLI nao goi toi |

**Ket luan trung thuc muc 1**: du an KHONG con duoc phat trien that su (~1
nam 8 thang khong commit nguoi that), moc `pushed_at` "gan day" tren
GitHub la GAY NHAM boi bot dependabot — da kiem tra ky truoc khi ket
luan, khong dung nguyen gia tri be mat.

## 2. THIET LAP WORKSPACE CO LAP

- Cai Microsoft OpenJDK 17 qua `winget` (nguon chinh thuc, co ky so).
- Tai Apache Maven 3.9.16 THANG tu `dlcdn.apache.org` (nguon chinh thuc
  Apache) vao thu muc scratch rieng — KHONG cai dat he thong, chi giai
  nen dung cho phien test nay.
- `git clone` THAT tu `github.com/Flameish/Novel-Grabber` (commit
  `7a29e468`, 2024-12-30 — code THAT SU moi nhat, khong dung ban release
  cu 2021).
- `mvn package` thanh cong, tao `novel-grabber-3.10.3-jar-with-dependencies.jar`.

Toan bo nam trong `scratchpad`, khong dua vao repo.

## 3. TEST 3 NGUON THAT

| # | Nguon | URL | Ket qua |
|---|---|---|---|
| 1 | Royal Road | `royalroad.com/fiction/43318/the-butcher-of-gadobhra` ("The Butcher of Gadobhra" boi "The Walrus King") | **THANH CONG THAT** |
| 2 | Syosetu (goc tieng Nhat cua Re:Zero) | `ncode.syosetu.com/n2267be/` | **LOI THAT** — crash `IndexOutOfBoundsException` |
| 3 | WuxiaWorld | `wuxiaworld.com/novel/martial-world` ("Martial World") | **LOI THAT** — cung crash, ca voi `-headless chrome` |

### Nguon 1 — Royal Road: THANH CONG day du

```
java -jar novel-grabber.jar -link <url> -chapters 1 3 -path <out> -displayTitle
```
Hoan tat trong **7 giay**, tao EPUB that (82.181 byte).

| Chi so | Ket qua that |
|---|---|
| Metadata | `dc:title`="The Butcher of Gadobhra", `dc:creator`="The Walrus King" — dung, nhung OPF **KHONG co** `dc:source`/URL nguon, **KHONG co** ngay xuat ban — mong hon nhieu so voi FanFicFare |
| Mo ta/tag | CO duoc lay that, nhung dat trong mot trang HTML rieng (`desc_Page.html`), khong nam trong truong OPF chuan — can them ma tu viet de trich xuat lai neu muon dung may |
| Danh sach/thu tu chuong | 3/3 chuong dung thu tu (262, 263, 264 — dung so chuong that cua truyen, thu tu file tuan tu) |
| Do sach noi dung | **Sach hoan toan** — 13.754/12.388/9.568 ky tu, mo dau bang tieu de chuong, ket bang cau van hoan chinh, khong HTML rac |
| Unicode | Khong ap dung ro (truyen tieng Anh) |

### Nguon 2 — Syosetu: THAT BAI, nguyen nhan XAC DINH duoc chinh xac

```
Exception in thread "main" java.lang.IndexOutOfBoundsException:
Index 0 out of bounds for length 0
	at grabber.Novel.downloadChapters(Novel.java:117)
```

Da doc THAT ma nguon adapter (`ncode_syosetu_com.java`): tim chuong bang
`toc.select(".index_box a")`. Da tai THAT trang song hien nay va kiem
tra: class `index_box` **khong con ton tai** — trang That da doi sang
`p-eplist__sublist`. **Ket luan chac chan, khong suy doan**: Syosetu da
lam lai giao dien tu sau lan cap nhat cuoi cua adapter nay, va adapter
chua duoc va cham lai tu do — khop voi phat hien muc 1 (khong commit
that tu 2024-12-30).

### Nguon 3 — WuxiaWorld: THAT BAI, nguyen nhan KHAC — SPA render-phia-client

```
Exception in thread "main" java.lang.IndexOutOfBoundsException:
Index 0 out of bounds for length 0   (giong het loi tren)
```

Adapter tim `#accordion .chapter-item a` trong HTML tinh. Kiem tra THAT
trang da tai: khong co dau vet `chapter-item`/`__typename` nao trong
HTML server tra ve — trang gio la mot ung dung phia client hien dai (dau
hieu Next.js), du lieu chuong duoc JavaScript nap SAU khi trang tai,
khong nam san trong HTML.

**Da thu them** `-headless chrome` (tinh nang render-trinh-duyet CHINH
THUC cua Novel-Grabber, khong phai giai phap lach) — **van loi giong
het, hoan tat trong 4 giay** (qua nhanh de la mot phien Chrome that su
khoi dong+render). Ket luan: co `-headless` la mot CO TOAN CUC, nhung
TUNG adapter site phai TU chon co dung no hay khong trong code cua
chinh no — adapter `wuxiaworld_com.java` khong duoc viet de dung duong
headless, nen co toan cuc khong co tac dung o day. Muon sua that su can
SUA CODE adapter, khong phai chi bat mot co dong luc.

## 4. CHE DO MANUAL/GENERIC TREN NGUON FANFICFARE KHONG HO TRO

Nguon du dinh: `narutofanon.fandom.com` (nguon THAT engine hien tai dang
dung, da xac nhan truoc do KHONG nam trong 111 site FanFicFare ho tro).

**Kiem tra truoc**: Novel-Grabber co adapter rieng cho Fandom/Wikia
khong? Da quet toan bo 104 file site那 that — **0 ket qua khop
"fandom"/"wikia"**. Giong het FanFicFare, Novel-Grabber cung khong co
adapter san cho loai site nay.

**Vay chi con duong "manual/generic mode"** — nhung da doc THAT source
`manualSource.java` (muc 1): constructor doc gia tri truc tiep tu MOT O
NHAP CUA GIAO DIEN SWING (`init.gui.manChapterContainer.getText()`),
khong nhan tham so tu CLI, khong doc tu file cau hinh. **Khong co CO
CLI, khong co file settings nao thay the duoc** — da xac nhan lai bang
`-help` (khong co flag `-manual`/`-chapterContainer` nao).

**Ket luan trung thuc**: KHONG THE test duoc muc nay bang tu dong hoa
trong moi truong nay — day la mot GIOI HAN KIEN TRUC that cua chinh
Novel-Grabber (che do manual chi ton tai ben trong ung dung GUI), khong
phai loi cua phep test. Ghi nhan thang than thay vi gia lap hay viet
code rieng de "lach" vao ham GUI-only do (viec do se bien thanh viet
them mot cong cu moi, khong con la test Novel-Grabber nhu no von co).

**Ket qua thuc te tren dung nguon nay**: chi CO DUY NHAT engine hien tai
cua Fanfic World hoat dong (da chung minh nhieu lan truoc do, 16+ chuong
that tu `narutofanon.fandom.com`) — ca FanFicFare (bao cao truoc) lan
Novel-Grabber deu KHONG the cham toi nguon nay bang duong tu dong.

## 5. SO SANH

| Tieu chi | Novel-Grabber | FanFicFare (bao cao truoc) | Engine hien tai |
|---|---|---|---|
| Thanh cong tren nguon that da test | 1/3 (Royal Road) | 1/4 (Wattpad) | 100% tren nguon dang dung (`narutofanon.fandom.com`) |
| Do phu chuong | 3/3 chuong dung thu tu khi thanh cong | 5/5 chuong khi thanh cong | Da chung minh 16+/32 chuong that |
| Do sach noi dung | Sach hoan toan khi thanh cong | Sach hoan toan khi thanh cong | Sach, tru 1 loi nho da biet (dong Category: sot lai) |
| Do phong phu metadata | **Mong** — OPF chi co title/creator/language/UUID, KHONG co URL nguon/ngay thang trong truong may doc duoc | **Phong phu** — Dublin Core day du + tu dong giu link nguon goc | Tu viet, du dung nhung khong chuan hoa |
| Kha nang update tang dan | **Suy ra tu code (khong co CO CLI), khong kiem chung thuc nghiem duoc**: `CLI.downloadNovel()` khong kiem tra EPUB co san/bo qua chuong cu — logic checker/library chi trong GUI | **Da CHUNG MINH THAT** (bao cao truoc): 0 byte ghi lai khi khong co chuong moi | Chua co co che tuong minh (nhung goi API MediaWiki nhe, khong ton kem) |
| Chi phi thoi gian chay | 7 giay/3 chuong (khi thanh cong) | Tuong duong hoac nhanh hon (theo bao cao truoc) | Nhanh (goi API JSON truc tiep) |
| Luong ha tang can de CHAY duoc | **Nang nhat**: can JDK+Maven, build tu source (Java KHONG co san tren may nay, phai cai moi) | Nhe: `pip install`, khong can build | Khong can gi them (da co san trong repo) |
| Tinh thuc te tu dong hoa | Thap: 2/3 site test THAT BAI do adapter cu; manual mode khong the tu dong hoa (GUI-only); dependabot lam moc "hoat dong gan day" gay nham | Trung binh: mot so site lon bi chan nhung co the fallback | Cao — dang chay that, on dinh |

## 6. KET LUAN — mot trong bon lua chon

### **ADAPTER_IDEA_SOURCE**

Ly do:

1. **KHONG the la `PRIMARY_PROVIDER`**: du an thuc te khong con duoc bao
  tri (~20 thang khong commit that), 2/3 adapter that da test bi hong do
  cac site nguon da doi giao dien — dua production vao mot cong cu voi
  ty le hong cao va khong ai sua la rui ro khong can thiet.
2. **KHONG phai `SELECTIVE_PROVIDER`**: ngay ca truong hop THANH CONG
  duy nhat (Royal Road) cung khong mang lai loi the ro ret so voi
  FanFicFare/engine hien tai — metadata ngheo hon, khong co update tang
  dan da CHUNG MINH duoc (chi suy tu code), va yeu cau ha tang JDK/Maven
  nang hon han de chi CHAY duoc.
3. **KHONG phai `NOT_WORTH_IT`**: gia tri that su nam o Y TUONG, khong
  phai o phan mem — 104 dinh nghia site (du mot phan da cu) la mot BAN
  DO tot ve "trang nao dung selector CSS gi cho tieu de/danh sach
  chuong/noi dung", va thu vien `Readability4JExtended` (Java port cua
  Mozilla Readability.js) ma `manualSource.java` dung la mot thu vien
  DOC LAP, that, co the tham khao khi thiet ke buoc trich xuat generic
  cho engine hien tai — khong can nhung ca ung dung Java de lay y tuong do.
4. **`ADAPTER_IDEA_SOURCE`** khop nhat: dung cac file `.java` trong
  `src/main/java/grabber/sources/` nhu MOT NGUON THAM KHAO khi can them
  ho tro mot site moi cho engine Python hien tai (vi du: neu can them
  `royalroad.com`, `toc.select("td:not([class]) a")` la mot goi y
  selector THAT, da kiem chung hoat dong, tiet kiem thoi gian do tim
  selector tu dau) — nhung KHONG nhung ca ung dung Java, KHONG phu
  thuoc JDK/Maven trong production, va PHAI tu kiem chung lai tung
  selector truoc khi dung (da chung minh 2/3 co the da loi thoi).

**KHONG tich hop production tu ket luan nay**, dung yeu cau cua mission.

## Chi phi / don dep

$0 — JDK/Maven/source deu tu nguon chinh thuc mien phi. Toan bo cai dat
(JDK) va workspace (Maven, source, jar, output test) nam ngoai repo;
JDK la cai dat he thong DUY NHAT cua mission nay, co the go bo qua
"Add or remove programs" (`Microsoft.OpenJDK.17`, cai qua winget, co ky
so, khong sua registry/service ngoai pham vi trinh cai dat chuan).

---

**MOBILE HANDOFF MAX 7 LINES**
Status: Build that tu source hien tai (JDK+Maven cai moi), test that, khong tich hop production
Version/sites: pom.xml noi bo 3.10.3 (commit that gan nhat 2024-12-30), 104 site parser that
Sources: Royal Road THANH CONG, Syosetu LOI (site doi CSS class), WuxiaWorld LOI (site chuyen SPA, ca -headless cung khong cuu duoc)
Chapters: 3/3 chuong sach tren Royal Road; 0 tren 2 nguon con lai
Vs FanFicFare/current: metadata ngheo hon FanFicFare, update tang dan chi suy tu code chua chung minh duoc; nguon dang dung that (fandom wiki) khong the nao voi toi bang manual mode (GUI-only, khong CLI)
Verdict: ADAPTER_IDEA_SOURCE — tham khao y tuong/selector, khong nhung ca ung dung Java
SHA: (xem git log sau khi commit)
