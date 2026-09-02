# BANG CHUNG PIPELINE CHINESE MEDIA THAT SU + SUA QUYEN DOWNLOAD (2026-09-02)

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Nguon Chinese that co quyen ro rang | Chua co (Track C truoc: 0/31 video co phu de that) | **Co that**: WIKITONGUES Henan Chinese, Wikimedia Commons, CC BY-SA 4.0 |
| Pipeline chay tren du lieu that | Chi test tong hop (edge-tts tu tao) | **Chay dau-cuoi that**: ASR that, dich that, SRT that, dub that, RENDER that |
| Quyen tai file an toan | Bi chan hoan toan (deny toan bo `curl -o`) | Thu hep chinh xac: chi cho phep HTTPS GET, khong credential, ghi trong scratch |

## Phan 1 — Thu hep quyen tai file (uy quyen ro rang truoc khi sua)

`.claude/settings.json` deny TOAN BO `curl -o/-O/--output/--remote-name`
bat ke nguon/dich — mot kiem soat co chu dich, rat co the dat ra chinh vi
chuoi yeu cau tai model Piper truoc do trong phien nay. Da DUNG LAI truoc
khi sua, hoi truc tiep nguoi dung QUA CAU HOI RIENG (khong gop vao mission
list) vi `.claude/settings.json` chinh no nam trong danh sach `ask` cho
Edit — tin hieu ro rang tu chinh cau hinh repo rang sua file nay can xac
nhan that.

Sau khi duoc xac nhan: chuyen bao ve tu deny-toan-bo (settings.json, chi
la glob don gian) sang kiem tra CHINH XAC trong `guard_indirect_exec.py`
(Python, co the bieu dat dieu kien phuc hop): chi cho qua khi DONG THOI
ca bon dieu kien — HTTPS, GET, khong credential/cookie/body, va duong dan
ghi nam trong scratch cua Claude (khong bao gio la repo, khong bao gio
`.claude/`). Thieu MOT trong bon van bi tu choi cung nhu truoc, o MOI che
do ke ca bypassPermissions. 386/386 test qua (366 cu + 20 moi, 0 hong).

## Phan 2 — Pipeline that, dau-cuoi, tren video CC BY-SA 4.0 that

Nguon: `WIKITONGUES- Ying speaking Henan Chinese.webm` — video that, giay
phep **CC BY-SA 4.0** (Wikimedia Commons), 3 phut 38 giay, nguoi noi that
gioi thieu tieng dia phuong Ha Nam. Giay phep nay THAT SU cho phep phan
phoi lai (kem attribution + share-alike) — khac han moi ung vien AI-hoat-
hinh da kiem tra truoc day (khong co quyen phan phoi xac minh duoc).

Ket qua tung buoc:

1. **Phu de goc**: khong co track WebVTT rieng — bo qua, chuyen sang ASR.
2. **faster-whisper (that)**: 55 doan, phat hien dung tieng Trung
   (`prob=1.00`). Vi du: "大家好,我叫琳,很高兴在Wikitongues上面跟大家一起分享..."
3. **Dich ZH->VI (that)**: tu nhien, chinh xac — "Xin chào mọi người, tôi
   tên là Lâm, rất vui được cùng chia sẻ..."
4. **SRT giu dung timestamp (that)**: 55 cue, 6.856 byte.
5. **Dub Ngoc Huyen Moi (that)**: 131.988 byte MP3.
6. **Ghep FFmpeg (that)** — phat hien VA SUA mot loi that: `mov_text` la
   codec phu de rieng cho MP4/MOV, that bai voi Matroska ("Function not
   implemented"). Sua thanh chon codec theo duoi file dau ra. Sau sua: file
   `.mkv` that 46.699.303 byte, xac minh qua `ffprobe` co DU BON track —
   video (vp9), audio goc (opus), phu de tieng Viet (subrip), dub tieng
   Viet (mp3) — dung 217,97 giay khop chinh xac voi nguon.
7. **DRAFT entry that**: `POST /api/novels` -> `nov_41c9c967f40845a0`,
   `state=draft`, `rights_mode=REHOST_ALLOWED`, KHONG xuat hien trong
   danh sach cong khai. `subtitle_key`/`dub_audio_key` tai duoc that qua
   R2 — HTTP 200, `text/srt` / `audio/mpeg`, khop byte chinh xac.

## Phan 3 — Drive archive (xac minh lai, khong doi so voi bao cao truoc)

Da xac nhan trong luot truoc: 10 chuong Naruto + Re:Zero + 1 truyen khac
tung chi nam o scratch cuc bo, chua bao gio len Drive du kien truc da co
san (`fanfic-gdrive:`, `scripts/rclone_archive_copy.py`). Da day len that,
`rclone check` xac nhan 0 khac biet, 31 file khop. Tu dong hoa cho tuong
lai da noi day vao `server/scraper/raw_archive.py` (khong chan, hang doi
thu lai qua `server/worker.py`).

## Phan 4 — Router V3 / OpenCode

Da xac nhan va sua trong luot truoc: `opencode` CLI da cai/dang nhap that
nhung `opencode serve` (server HTTP ma adapter can) chua bao gio duoc
khoi dong. Da them launcher tu khoi dong (cung co che Startup folder voi
worker TTS). `OPENCODE01` gio la `IDLE`.

## Danh gia trung thuc voi cac muc "stretch"

- Dub tieng Viet that: **DAT**.
- Output render phat duoc that: **DAT** (xac minh qua ffprobe, khong doan).
- Retry archive tu dong: **HA TANG DA XONG, chua CHUNG MINH SONG** (chua ep
  mot lan that bai that de xem no tu thu lai — co the lam neu can, khong
  lam trong luot nay vi khong bat buoc).
- Router thay lai OpenCode: **DAT**.

## Dinh chinh mot phat bieu sai truoc do (da noi trong luot truoc, nhac lai
o day cho day du ho so)

Da tung noi sai rang khong co ha tang "Router V3"/"OpenCode" nao trong
repo nay. Sai — `scripts/router_v3/` la he thong that, da commit.

## Chi phi / test

$0 (Wikimedia Commons + faster-whisper + agy + Piper deu mien phi/da co
san; khong goi provider tra phi nao). Bo test guard hook: 386/386 PASS.
