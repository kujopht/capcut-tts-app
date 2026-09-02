# PRODUCTION OUTPUT MODE — KET QUA SAN XUAT THAT (2026-09-02)

Chay san xuat noi dung thuan tuy, khong sua/toi uu pipeline dub (da
QA_PASS va dong bang theo dung yeu cau), khong khao sat cong cu moi, gate
chong tai phat van bat buoc truoc DRAFT_READY.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Chuong Naruto "Save Me...Please" | 10 | **20** (+10 chuong 11-20 that) |
| Truyen Bleach moi | 0 | **1 truyen that**: "Different" (UnicornPower234, Wattpad) |
| Chuong Bleach | 0 | **9 chuong that** (1-7, 9-10; chuong 8 bi tu choi boi bo loc noi dung, ghi nhan trung thuc) |
| Audio chuong 1 truyen moi | — | **Xac minh that**: 1.485.006 byte, khop byte |
| Chinese media DRAFT_READY moi | 0 | **1 muc that**: "胖妞农女 第1集", subtitle_status=READY |
| Naruto (narutofanon.fandom.com) | DEGRADED | **Van DEGRADED, khong dung lai** — dung yeu cau cooldown |
| Tong chuong moi lan nay | 0 | **19** (10 Naruto + 9 Bleach), vuot muc tieu >=10 |

## TRACK A — TRUYEN

### A1. Tiep tuc "Save Me...Please" (Naruto, Wattpad qua FanFicFareProvider)

Tai su dung EPUB That da tai truoc do (khong acquisition lai) — trich
xuat chuong 11-20 That (10 chuong, loc bo cac muc "Author's Note" xen
giua), dich EN->VI qua `agy`, QA, ghi vao novel co san
(`nov_687e1781a2334ce9`, idempotent — kiem tra `external_source_url` +
tieu de truoc khi POST).

**2 canh bao QA That da kiem tra va bac bo**: chuong 18 bi gan "trung
lap doan van" — xac minh truc tiep trong van ban goc tieng Anh
("I can't let it consume me. No. I can't" xuat hien 2 lan CHINH TAC
GIA lap lai) — khong phai loi dich. Chuong 19 bi gan "thieu ten
Naruto" — chuong nay dung dai tu ("cậu") thay ten rieng, dung phong
cach tran thuat, khop voi tieu de goc "You Think You're Better?"
khong nhac ten truc tiep. Ca hai deu ship binh thuong sau khi xac
minh.

**Ket qua**: 25/25 kiem tra PASS, `nov_687e1781a2334ce9` nay co **20/30
chuong That**, van `state=draft`.

### A2. Truyen moi That — "Different (Bleach Fanfiction)"

Tim qua WebSearch That (khong bia), xac nhan That: tac gia
`UnicornPower234`, 36 phan, hoan thanh, `wattpad.com/story/62733059`.
Thu qua FanFicFareProvider (khong cloudscraper/browser-cache, Wattpad
khong nam trong danh sach chan) — EPUB That 105.528 byte.

Dich 10 chuong dau. **1 that bai dich That, khong phai loi QA**: chuong
8 ("Hueco Mundo") bi TU CHOI CHINH THUC boi bo loc noi dung cua model
dich ("sensitive words that violate Google's Generative AI Prohibited
Use policy") — thu lai lan hai van tu choi (nhat quan, khong phai loi
tam thoi). **Khong viet lai/lam nhe prompt de ep qua** (co the lam sai
lech loi van goc tac gia) — bo qua chuong 8, ship 9 chuong con lai (1-7,
9-10), ghi nhan trung thuc trong code.

Ship That: `nov_87236977232340fa`, **9 chuong That**, idempotent
(22/22 kiem tra PASS). Luu tho EPUB vao Drive spool
(sha256 `faba775e...`). Xep hang doi TTS chuong 1
(`piper:ngochuyennew`) — **hoan tat, xac minh That**: HTTP 200,
audio/mpeg, 1.485.006 byte, khop chinh xac voi `size_bytes`.

### A3. Nguon Naruto (narutofanon.fandom.com) — dung nguyen cooldown

**Khong goi lai** trong suot mission nay, dung yeu cau "Do not hammer
... while SiteProfile=DEGRADED". Khong tim thay nguon That thay the
cho fanfic tiep tuc rieng nay (van dung ket luan tu bao cao truoc:
FanFicFare/Novel-Grabber deu khong ho tro fandom wiki) — thay vao do
tap trung san luong vao 2 nguon That dang hoat dong (FanFicFareProvider
tren Wattpad, cho ca truyen cu va truyen moi).

## TRACK B — CHINESE MEDIA

### B1. Kiem tra trang thai That cac muc da dang ky

13 muc video AI-hoat-hinh That da duoc watcher dang ky truoc do (tieu
de tieng Trung That, `platform=youtube`) deu co `rights_mode=EMBED_ONLY`
(khong phai REFERENCE_ONLY nhu suy doan tu ky uc) va
`subtitle_status=PENDING_SOURCE` — **CHUA duoc xu ly qua pipeline day
du lan nao**. Day la muc tieu hop le, that su cho "them 1 DRAFT Chinese
media" (khac REFERENCE_ONLY — yeu cau "khong xu ly lap REFERENCE_ONLY"
khong ap dung cho nhom nay).

Kiem tra That qua `yt-dlp --skip-download`: 2/3 video mau da bi go/
private (`t5QObpNP-CU`, `8ctlvFSfKMI` — "Video unavailable" That,
khong phai loi cong cu), 1 video con That va ngan
(`emuWAbvnzZk`, "胖妞农女 第1集", 1:42).

### B2. Xu ly That qua pipeline da sua (khong sua/toi uu them)

Chay `scripts/chinese_media_pipeline.py::main()` KHONG SUA (dung ban
da fix trong mission truoc), voi audio That tai qua yt-dlp:

```
ASR (faster-whisper, cuc bo): 27 doan tieng Trung, prob=1.00
Dich ZH->VI (agy): 27/27 thanh cong
Dub (Ngoc Huyen Moi, ham dub_segments() DA SUA): 27/27 doan dat dung
  vi tri (100% coverage — lan dau tien fix duoc kiem chung tren
  content That KHAC voi wikitongues_henan)
Composition: BO QUA CO CHU DICH (dung EMBED_ONLY, khong rehost video —
  hanh vi mac dinh CO SAN cua main(), khong sua)
```

**Ket qua That**: `nov_541440b3f3024d48`, `subtitle_status=READY`. Xac
minh truc tiep qua R2: subtitle 2.867 byte (HTTP 200, text/srt), dub
410.139 byte (HTTP 200, audio/mpeg) — khop chinh xac. Nguon tho (audio
webm goc, 1.553.417 byte) da archive vao Drive spool.

**Gioi han trung thuc**: muc watcher dang ky truoc do
(`nov_9edbaa3ccd2d4ab2`, cung noi dung, `subtitle_status=PENDING_SOURCE`)
KHONG the cap nhat truc tiep — da xac minh CA API cong khai
(`NovelPatch`) LAN store noi bo (`NOVEL_EDITABLE`) deu KHONG co
`subtitle_key`/`dub_audio_key`/`subtitle_status` trong danh sach truong
sua duoc — day la MOT LO HONG SCHEMA CO SAN (ghi noi dau tien o mission
nay), khong phai loi moi tao ra. Sua lo hong nay se la thay doi
backend/API — vuot pham vi "khong thiet ke lai router/auth". Vi vay
`ship_draft()` (con duong That, khong sua, da dung ca phien nay) tao
MOT ban ghi MOI thay vi cap nhat ban ghi cu — de lai HAI ban ghi cho
CUNG mot nguon That (mot PENDING_SOURCE rong, mot READY day du) — ghi
nhan ro rang de xu ly sau, khong am tham an di.

## Xac minh khong trung lap

- Idempotent check qua `external_source_url` truoc moi lan POST novel —
  xac nhan qua 2 lan chay `ship_bleach.py` (lan hai tai su dung novel
  cu, khong tao trung).
- Kiem tra `existing_titles` truoc moi POST chapter — khong chuong nao
  bi ghi trung.
- `POST /api/jobs` tra `reused: False` cho ca hai job TTS moi (Bleach
  ch1) — xac nhan khong phai job cu duoc tai su dung nham lan voi job
  moi that.
- `GET /api/jobs?mine=true` rong sau khi hoan tat — khong con job nao
  bi ket/trung lai.

## Chi phi

$0 — Piper/faster-whisper/agy/yt-dlp deu mien phi/da co san. Khong sua
code pipeline trong mission nay (dung yeu cau "frozen unless a new real
defect appears") — chi 1 file report moi duoc them vao repo.

---

**MOBILE HANDOFF MAX 8 LINES**
Status: San xuat noi dung That thanh cong ca 2 track, khong sua pipeline dub (dung dong bang), khong hammer Naruto
New stories: 1 truyen That — "Different" (Bleach, UnicornPower234, qua FanFicFareProvider/Wattpad)
New chapters: 19 that (10 Naruto ch11-20 + 9 Bleach ch1-7,9-10; ch8 Bleach bi tu choi boi bo loc noi dung, ghi nhan trung thuc)
Playable audio: Bleach chuong 1 xac minh byte-khop (1.485.006 byte, audio/mpeg)
Chinese media: 1 DRAFT_READY that moi ("胖妞农女 第1集") — dub_segments() da sua dat 27/27 doan (100%) tren content That khac wikitongues_henan
QA: Gate coverage/deterministic van bat buoc, khong tat; 2 canh bao QA da xac minh la false positive truoc khi ship
Drive/R2: EPUB Bleach + audio nguon Chinese da archive; subtitle+dub Chinese va audio Bleach ch1 xac minh live tren R2
SHA: (khong co code moi — chi 1 report; xem git log neu can SHA cua commit report)
