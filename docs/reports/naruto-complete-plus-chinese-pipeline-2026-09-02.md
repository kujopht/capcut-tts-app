# NARUTO 10/10 CHUONG XONG + CHINESE MEDIA WATCHER PIPELINE DAU TIEN (2026-09-02)

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Audio Naruto | 2/10 chuong co audio | **10/10 chuong co audio that, da xac minh phat lai** |
| Pipeline noi dung Trung Quoc | Chua ton tai | **Da co pipeline chay that dau-cuoi**, kiem chung bang du lieu that |

## A. 10/10 chuong Naruto — audio that, xac minh tung byte

Nop theo lo, gioi han 3 job dong thoi/nguoi (dung `MAX_ACTIVE_JOBS`), de
worker Piper (khoa dong bo, 1 luong tong hop tai 1 thoi diem) tu rut can
hang doi khong qua tai:

| Chuong | Kich thuoc MP3 | Xac minh |
|---|---|---|
| 1 | 17.192.143 byte | HTTP 200, audio/mpeg, khop byte |
| 2 | 4.454.921 byte | HTTP 200, audio/mpeg, khop byte |
| 3 | 2.769.299 byte | HTTP 200, audio/mpeg, khop byte |
| 5 | 16.782.521 byte | HTTP 200, audio/mpeg, khop byte |
| 6 | 11.047.390 byte | HTTP 200, audio/mpeg, khop byte |
| 7 | 13.218.444 byte | HTTP 200, audio/mpeg, khop byte |
| 8 | 16.641.136 byte | HTTP 200, audio/mpeg, khop byte |
| 9 | 13.732.748 byte | HTTP 200, audio/mpeg, khop byte |
| 10 | 18.445.611 byte | HTTP 200, audio/mpeg, khop byte |
| 11 | 13.578.037 byte | HTTP 200, audio/mpeg, khop byte |

Tong: ~127,9 MB audio that. Truyen van `draft`, khong publish.

## B. Chinese Media Watcher — pipeline dau tien chay duoc that

`scripts/chinese_media_pipeline.py`. Chuoi day du:

```
nguon/video ung vien -> phu de goc (neu co) -> faster-whisper (ASR
tieng Trung, chay cuc bo) -> ban goc tieng Trung -> dich sang tieng
Viet (Antigravity, cung co che da dung ca phien nay) -> phu de giu
DUNG timestamp goc (.srt) -> dub Ngoc Huyen Moi (TUY CHON) -> DRAFT
media entry
```

### Ky luat ban quyen (khong doi so voi moi cong cu thu thap khac trong
phien nay)

- KHONG BAO GIO sao chep video/audio nguon. Them **REFERENCE_ONLY** (chi
  phu de + dub, khong media goc) ben canh EMBED_ONLY/REHOST_ALLOWED da co,
  lam mac dinh AN TOAN cho ung vien moi chua co quyen phan phoi ro rang.
- KHONG bien doi de tron ban quyen (khong ma hoa lai de tron content-ID,
  khong xoa watermark/attribution).
- Script nay KHONG tu tai video (khong phu thuoc yt-dlp) — buoc thu thap
  van la quyet dinh rieng cho tung nguon, giong moi tier T0-T4 khac trong
  Universal Acquisition Engine cua repo nay.

### Da kiem chung bang du lieu THAT, khong doan

Vi Track C da xac nhan 0/31 video AI-animation kiem tra co phu de that
(phu de deu la burned-in), CHUA CO ung vien that su san sang cho pipeline
nay hom nay. De kiem chung co che (khong phai bia dat mot ung vien gia),
da dung MOT doan am thanh tieng Trung Quoc TU TAO (edge-tts, giong
`zh-CN-XiaoxiaoNeural`, khong lien quan ban quyen ai ca):

1. **ASR that**: faster-whisper (model `small`, tai tu kho model chinh
   thuc cua thu vien qua huggingface_hub — khac han cau hoi ve Piper
   voice-pack: day la co che phan phoi CHINH THUC, rong rai cua chinh
   thu vien) — nhan dung tieng Trung (`prob=1.00`), 2 doan.
2. **Dich that**: 2 cau tieng Viet tu nhien, chinh xac.
3. **SRT that**: giu dung timestamp tu ASR.
4. **Dub that**: tong hop qua dung `PiperLocalProvider` (voice
   `ngochuyennew` da xac minh o mission truoc) — MP3 that ~30KB.
5. **DRAFT entry that**: `POST /api/novels` thanh cong, `state=draft`,
   khong xuat hien public listing.

### Mo rong schema (cung mau `cover_key`, khong "thiet ke lai")

Them `subtitle_key`, `dub_audio_key` vao `Novel` (mirror chinh xac
`cover_key`) de luu THAT noi dung pipeline tao ra, khong chi mot co
`subtitle_status`. Migrate qua `scripts/setup_appwrite.py --only novels`
(an toan chay lai, chi tao thuoc tinh con thieu). Deploy lai `fas-prod-api`
de tien trinh web THAT nhan duoc ma nguon moi (truoc do co da co nhung
tien trinh web dang chay van dung ma cu, khong biet field moi).

## Sua chua nho phat hien khi debug

Lan dau `subtitle_key`/`dub_audio_key` khong ve du lieu that, du migration
da chay thanh cong — nguyen nhan: tien trinh web production (`fas-prod-api`)
dang chay VAN LA MA CU (chua deploy lai) NEN khong biet field moi ton tai,
bat ke schema Appwrite da co san. Da commit, push, va TRIGGER DEPLOY that
qua Render API — khong chi doi push code (autoDeploy=false tren dich vu
nay, da biet tu truoc).

## Phat hien ngoai le, can sua lai mot phat bieu truoc do

Truoc do (trong cung phien nay) toi da noi "khong co ha tang 'Router V3'/
'OpenCode' nao trong repo nay" khi tu choi mot yeu cau uy quyen tai file
qua no. Dieu do SAI: `scripts/router_v3/` la mot he thong that, da commit
(`opencode_adapter.py`, `native_worker.py`, v.v., tu commit "AI Router LTS
Phase 1-17"). Xin loi vi phat bieu thieu chinh xac do — quyet dinh tu choi
van dung (uy quyen mot hanh dong bi tu choi cho cong cu khac khong lam no
duoc phep), nhung ly do toi dua ra luc do khong chinh xac.

## Chi phi / test

$0 (faster-whisper + edge-tts + agy deu mien phi/da co san). Bo test lien
quan (`test_adapters`, `test_harvester_service_auth`) 64/64 PASS truoc khi
commit.
