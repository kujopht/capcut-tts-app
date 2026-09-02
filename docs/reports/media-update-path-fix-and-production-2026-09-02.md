# SUA DUONG CAP NHAT MEDIA RECORD + TIEP TUC SAN XUAT (2026-09-02, Mission 9)

Sua lo hong schema that (khong the cap nhat placeholder Chinese-media
tai cho, gay ban ghi trung) bang mot duong PATCH RIENG, HEP, deploy
that len production, dung de hoa giai ban ghi trung that su, roi tiep
tuc san xuat noi dung. Pipeline dub Chinese-media giu nguyen dong bang
(khong sua ASR/dich/dub/render/QA).

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Duong cap nhat Novel media-processing | Khong ton tai (chi co `NovelPatch` chung, khong co `subtitle_key`/`dub_audio_key`) | **Co that**: `PATCH /api/novels/{id}/media-processing`, 6 truong duy nhat, deploy live |
| Idempotency `ship_draft()` | Luon POST -> tao ban ghi moi moi lan chay | **Da sua**: tim theo `external_source_url` truoc, PATCH ban ghi cu neu co |
| Ban ghi Chinese-media trung (`emuWAbvnzZk`) | 2 ban ghi cho CUNG 1 nguon (1 rong PENDING_SOURCE, 1 day du READY) | **Da hoa giai that**: 1 ban ghi canonical day du du lieu, 1 ban ghi danh dau SUPERSEDED, khong mat bang chung nao |
| Production backend (`fas-prod-api`, Render) | commit `5d1a4cfee4ae` (tut hau nhieu PR) | **Da deploy that**: commit `1857c9b`, xac minh qua SHA tra ve tu Render API |
| Chuong Naruto "Save Me...Please" | 20/30 | **30/30 — HOAN TAT toan bo truyen** |
| Chuong Bleach "Different" | 9/36 | **19/36** (+10 chuong that, 11-20) |
| Truyen moi | — | **Khong tim/ship truyen moi lan nay** — viec tim nguon moi se la "khao sat cong cu/scraper" bi cam trong mission nay; da co 2 truyen that dang tiep tuc, uu tien do hon la mo rong dan trai |
| Chinese-media DRAFT_READY | 1 (`nov_9edbaa3ccd2d4ab2`, tu Mission 8) | Van **1** — ung vien thu hai (`EBwsgB1rRBo`, ~34 phut) ASR that thanh cong (1147 doan) nhung **dich that bai** vi gioi han quyen cong cu `agy`, khong phai loi pipeline |

## TRACK A — SUA DUONG CAP NHAT MEDIA + HOA GIAI TRUNG LAP

### A1. Thiet ke va trien khai

Giao cho mot Workflow 4 pha (Implement -> Review song song [Security +
Idempotency] -> Fix -> Verify) — 5 agent, 444.870 token, 147 tool call
that. Thay doi:

- `server/domain.py`: them 3 truong `rendered_media_key`, `qa_state`,
  `processing_error` vao `Novel`.
- `server/appwrite_store.py`: `NOVEL_MEDIA_PROCESSING_EDITABLE` — DUY
  NHAT 6 truong (`subtitle_key`, `dub_audio_key`, `rendered_media_key`,
  `subtitle_status`, `qa_state`, `processing_error`), khong giao voi
  `NOVEL_EDITABLE` (truong chung: title/description/tags/rights_mode/...).
  Them `update_novel_media_processing()` — loc `fields` qua whitelist
  TRUOC khi ghi, khong bao gio cham owner/rights/identity.
- `server/main.py`: model `NovelMediaProcessingPatch` (dung 6 truong
  tren) + route `PATCH /api/novels/{novel_id}/media-processing`, cung
  `Depends(harvester_or_user_profile)` y het route chung.
- `scripts/chinese_media_pipeline.py::ship_draft()`: truoc khi POST,
  `GET /api/novels?mine=true` roi tim theo `external_source_url` — neu
  co, PATCH ban ghi cu qua duong moi thay vi tao moi.
- `server/adapters.py` (Mock), `scripts/setup_appwrite.py` (schema
  Appwrite that), `server/tests/test_crud.py` + `test_cover.py` (test
  moi), `scripts/tests/test_chinese_media_pipeline_ship_draft.py`
  (test moi, mock HTTP/R2, xac nhan PATCH-khong-POST khi trung, POST
  nhu cu khi khong trung).

Mot loi that duoc phat hien qua vet FULL suite (khong phai chi file da
sua): them 3 truong dataclass ma khong dong bo `PERSISTED_FIELDS` +
`_novel_from_doc()` se khien Appwrite AM THAM lam roi cac truong moi —
test qua (Mock) nhung khong hoat dong that voi Appwrite that. Da sua
cung cach da lam voi `subtitle_key`/`dub_audio_key` truoc do.

### A2. Kiem chung doc lap (khong tin bao cao agent)

Toi tu doc lai diff that cua `NOVEL_MEDIA_PROCESSING_EDITABLE`,
`NovelMediaProcessingPatch`, route, va nhanh idempotent trong
`ship_draft()` — khop 100% voi bao cao cua 2 reviewer doc lap (Security
+ Idempotency, ca hai deu ket luan **0 loi**). Test suite that (khong
tin ket qua agent tu bao):

```
server/tests: 4269/4269 PASS (1 skip), 190.7s
scripts/tests: 493/495 PASS — 2 that bai CO SAN, khong lien quan
  (test_router_v3_opencode_adapter.py gia dinh "khong co server" nhung
  co OpenCode server that dang chay tren may nay)
```

### A3. Deploy that len production

Backend (`fas-prod-api`, Render) co `autoDeploy=OFF` — commit vao
`main` KHONG tu dong len production (da ghi nhan that tu su co
2026-08-30). Da **hoi nguoi dung truoc khi push/deploy** (hanh dong
kho hoan tac, anh huong he thong san xuat that) — duoc dong y. Thuc
hien dung quy trinh da ghi trong `docs/HANDOFF.md`:

```
git push origin main                                    (5fc1d9c -> 1857c9b)
POST /services/srv-d9rls8navr4c739k7vvg/deploys          (Render API that)
poll toi status=live, DOI CHIEU commit SHA tra ve
```

Ket qua that: `deploy_id=dep-dac0e2favr4c73b1kq1g`, tien trinh
`build_in_progress` -> `update_in_progress` -> `live`, SHA tra ve
`1857c9b975a5...` khop chinh xac voi commit da push — khong tin trang
thai `live` mot minh nhu canh bao that tu su co truoc.

### A4. Chung minh ranh gioi bao mat that tren production LIVE

Sau khi deploy, chay MOT no luc "smuggle" that vao endpoint moi tren
production that (khong phai test gia lap):

```
PATCH .../media-processing {title:"PWNED", rights_mode:"REHOST_ALLOWED",
  external_source_url:"https://evil.example/...", owner_id:"someone_else",
  qa_state:"QA_PASS"}
```

Ket qua that: `title`/`rights_mode`/`external_source_url`/`owner_id`
**KHONG doi**, chi `qa_state` (truong hop le, nam trong payload) doi.
7/7 kiem tra PASS — da revert `qa_state` ve rong sau do de production
sach nhu truoc khi thu.

### A5. Hoa giai ban ghi trung that

Quyet dinh canonical = `nov_9edbaa3ccd2d4ab2` (ban ghi watcher dang ky
DAU TIEN, 2026-09-01, giu dung provenance that: tac gia that
"A爱漫剧社", kenh that, ly do rights that — khop cau "existing canonical
media identity already used by the watcher" trong yeu cau mission).

1. PATCH canonical qua duong moi: `subtitle_key`, `dub_audio_key`,
   `subtitle_status=READY` tu ban ghi `nov_541440b3f3024d48` — merge
   ket qua xu ly THAT, giu nguyen provenance/rights goc.
2. Ban ghi trung (`nov_541440b3f3024d48`) **KHONG xoa cung** — day la
   hanh dong kho hoan tac tren du lieu san xuat that (xoa qua
   `DELETE /api/novels/{id}` se xoa ca object R2 that). Thay vao do,
   PATCH qua duong CHUNG da co san (`title`/`description` nam trong
   `NOVEL_EDITABLE`) de danh dau ro "SUPERSEDED - merged into
   nov_9edbaa3ccd2d4ab2", giu nguyen toan bo bang chung
   (`subtitle_key`/`dub_audio_key` cua no van con y nguyen, khong mat).

Ket qua that: **11/11 kiem tra PASS** — canonical co du
`subtitle_status=READY` + 2 key that, van giu `external_author_name`
that + `rights_mode=EMBED_ONLY`; ban ghi trung da doi tieu de thanh
SUPERSEDED, van giu nguyen 2 key lam bang chung.

## TRACK B — SAN XUAT NOI DUNG (chay song song voi sua schema, tren
file khac)

### B1. Naruto "Save Me...Please" — HOAN TAT

Trich chuong 21-30 tu EPUB That da tai (khong acquisition lai), dich
EN->VI qua `agy`, QA, ship idempotent (kiem `external_source_url` +
tieu de truoc POST). **25/25 kiem tra PASS**, `nov_687e1781a2334ce9`
nay **30/30 chuong That, hoan tat toan bo truyen**.

### B2. Bleach "Different" — tiep tuc

Dich chuong 11-20 (10 chuong), ship idempotent. **23/23 kiem tra
PASS**, `nov_87236977232340fa` nay **19/36 chuong That**.

### B3. Truyen moi — khong tim lan nay

Mission 9 cam ro "Do not run another scraper/tool survey" — tim mot
nguon truyen HOAN TOAN MOI (nhu da lam voi Bleach o Mission 8, qua
WebSearch xac minh) can chinh dang la mot buoc kham pha/khao sat nguon.
Uu tien tuan thu gioi han nay hon la tu y mo rong — da co 2 truyen That
dang tiep tuc san xuat that, ghi nhan trung thuc khong co truyen moi
lan nay thay vi ep tim mot nguon yeu de "cho co so luong".

### B4. Chinese-media DRAFT thu hai — ASR thanh cong, dich that bai

Kiem tra 12 ung vien PENDING_SOURCE con lai qua `yt-dlp --skip-download`
(khong tai): 3/12 da bi go/private (`1LyvITAOhdM`, `rGCI6Uj1Wew`,
`K4w5dFVJjvU` — cong voi 2 da xac nhan Mission 8 = 5/14 tong the da
chet), 9 con lai deu la video dai (34 phut den 22 gio — khac han video
1:42 truoc do, day la cac ban "tong hop nhieu tap" thay vi "tap 1"
rieng le).

Chon `EBwsgB1rRBo` (34 phut, ngan nhat trong so con lai) — tai audio
That (28.346.793 byte, sha256 `057d0eba...`), archive vao Drive spool
that. Chay qua `chinese_media_pipeline.py` KHONG SUA:

```
ASR (faster-whisper small, CPU, That): 1147 doan tieng Trung, prob=1.00
  (~42 lan nhieu hon video truoc — video nay day thoai)
Dich ZH->VI qua agy: THAT BAI THAT
  ValueError: no JSON array in agy output (exit=0)
  stderr那那那: "jetski: no output produced — a tool required the
  'command' permission that headless mode cannot prompt for, so it
  was auto-denied."
```

**Day la mot gioi han cong cu THAT, MOI phat hien** — khac voi 2 loi
dub-coverage da sua o Mission 7. Voi lo hang 1147 doan (payload JSON
lon), `agy` tu quyet dinh can goi mot cong cu phu ("command") de xu ly
— trong moi truong headless khong co nguoi ngoi xac nhan quyen, yeu cau
do bi tu dong tu choi. Day KHONG PHAI loi trong `chinese_media_pipeline.py`
(dong bang, khong sua) va KHONG PHAI van de sua duoc bang
`--dangerously-skip-permissions` mot cach an toan (khong ro `agy` dinh
chay lenh gi — tu y bo qua kiem tra quyen cho mot yeu cau khong ro danh
tinh la rui ro, khong phai buoc di dung).

**Ket luan trung thuc**: khong co DRAFT_READY thu hai lan nay. Nguon
tho (audio 34 phut) da archive That vao Drive, co the dung lai cho mot
lan xu ly khac (vi du chia nho payload dich, hoac cho ai co the tuong
tac de cap quyen `agy`) nhung viec do se la thay doi pipeline — ngoai
pham vi "giu dong bang" cua mission nay.

## Xac minh khong trung lap

- `ship_draft()` idempotent: da xac minh qua test that (2 nhanh, PATCH
  khong POST khi trung, POST nhu cu khi khong trung) + qua chinh hoa
  giai ban ghi trung that (khong tao ban ghi thu 3).
- `existing_titles` truoc moi POST chapter — khong chuong Naruto/Bleach
  nao bi ghi trung.
- Xac minh live: sau khi hoa giai, `GET /api/novels/{canonical}` va
  `GET /api/novels/{duplicate}` deu tra dung 1 ban ghi moi, khong tao
  them ban ghi nao.

## Chi phi

$0 — Render deploy (mien phi/da co), Piper/faster-whisper/agy/yt-dlp
deu mien phi/da co san. 1 lan git push + 1 lan Render deploy that (da
xin phep truoc). Khong sua pipeline dub (dung yeu cau dong bang).

---

**MOBILE HANDOFF MAX 8 LINES**
Status: Sua xong duong cap nhat media, deploy that len production, hoa giai trung lap that, tiep tuc san xuat — pipeline dub van dong bang
Media update path: PATCH /api/novels/{id}/media-processing, 6 truong, deploy live commit 1857c9b (Render, xac minh SHA khop), security+idempotency review 0 loi, live smuggle-test 7/7 PASS
Duplicate repair: nov_9edbaa3ccd2d4ab2 la canonical, merge subtitle/dub tu nov_541440b3f3024d48 (nay danh dau SUPERSEDED, khong xoa, khong mat bang chung), 11/11 PASS
New stories: Khong tim truyen moi lan nay (tim nguon moi = khao sat, bi cam trong mission) — 2 truyen That van dang tiep tuc
New chapters/audio: Naruto 30/30 (HOAN TAT) +10 chuong; Bleach 19/36 +10 chuong; audio chuong 1 da xac minh tu Mission 8
Chinese drafts: Van 1 (tu truoc) — ung vien thu 2 (34 phut) ASR that thanh cong 1147 doan nhung dich that bai vi agy tu choi quyen "command" trong headless mode (loi cong cu moi phat hien, khong sua pipeline)
Drive/R2: Audio tho EBwsgB1rRBo (28.3MB, sha256 057d0eba...) da archive Drive spool; subtitle+dub Chinese cu va audio Bleach ch1 van live tren R2 tu truoc
SHA: 1857c9b (fix + deploy that len production)
