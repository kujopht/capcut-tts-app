# /WATCH — CAI DAT + VISUAL VIDEO QA CHO CONTENT FACTORY (2026-09-02)

Cai dat skill `/watch` (`bradautomates/claude-video`) That vao Claude
Code, chay QA hinh anh That tren mot rendered artifact That tu lan PASS
truoc, va them mot giai doan `VisualMediaQA` provider-neutral vao pipeline
— khong sua lai kien truc pipeline hien co.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| `/watch` da cai dat? | Khong | **Co, qua duong plugin chinh thuc** (`claude plugin marketplace add` + `claude plugin install`) |
| yt-dlp/ffmpeg/Python | Chi ffmpeg co san | **Ca ba da xac minh hoat dong** (yt-dlp cai moi, Python That, ffmpeg That) |
| Loi tuong thich That phat hien | Chua biet | **Co that**: `-vsync` bi FFmpeg 9.0 tu choi — da xac dinh nguyen nhan, da vá |
| Chay That tren video That | Chua | **Co — 74 frame that, 10 frame da doc, that su xem duoc noi dung** |
| Phat hien That | Chua co | **Loi that: dub audio chi phu 15.1% do dai video** (ffprobe phat hien, /watch xac nhan khong phai loi splice) |
| VisualMediaQA stage | Chua co | **That, co code, co test** (`scripts/visual_media_qa.py`, 24 test PASS) |

## 1. THANH TRA UPSTREAM

Repo That: `github.com/bradautomates/claude-video`. Da doc truc tiep
README.md va `skills/watch/SKILL.md` (khong doan tu tom tat tim kiem):

- **Cai dat**: duong Claude Code chinh thuc (`/plugin marketplace add` +
  `/plugin install watch@claude-video`) — CO tuong duong CLI That
  (`claude plugin marketplace add`/`claude plugin install`), da dung
  duong nay dung theo yeu cau "prefer supported plugin path".
- **CLI**: `python3 scripts/watch.py <source> [--detail
  transcript|efficient|balanced|token-burner] [--start/--end] [--no-whisper]
  [--max-frames] [--resolution] [--fps]`.
- **Frame cap theo detail**: `transcript`=0, `efficient`=50 (keyframe
  nhanh), `balanced`=100 (scene-aware, mac dinh), `token-burner`=khong
  gioi han.
- **Whisper**: TUY CHON, chi fallback khi video khong co caption san —
  co the tat hoan toan bang `--no-whisper`.

## 2. CAI DAT — That, khong mo phong

```
claude plugin marketplace add bradautomates/claude-video
claude plugin install watch@claude-video
```
Ca hai lenh That, thanh cong ("Successfully installed plugin:
watch@claude-video (scope: user)"). Skill nam tai
`~/.claude/plugins/marketplaces/claude-video/skills/watch/`.

## 3. XAC MINH — 5 muc, ca 5 That

| Muc | Ket qua That |
|---|---|
| yt-dlp | THIEU luc dau — cai qua `pip install --user yt-dlp` (2026.08.19), xac minh `yt-dlp --version` chay duoc |
| ffmpeg | Co san (winget), xac minh `ffmpeg -version` — **9.0-full_build** |
| Python/runtime | `python3` alias Windows Store KHONG dung duoc — dung truc tiep `C:\Program Files\Python312\python.exe` |
| Goi skill | `python3 scripts/watch.py <file> --detail balanced --no-whisper` chay That, tra ve 74 frame |
| **Tuong thich Windows** | **PHAT HIEN LOI THAT**: `ffmpeg scene extraction failed: Unrecognized option 'vsync'`. FFmpeg 9.0 (rat moi) da bo han co `-vsync` (chi con `-fps_mode`, tuong duong). `frames.py` cua skill dung `-vsync vfr` o HAI noi (dong 256, 615) — CA HAI deu chinh cung nguyen nhan (da xac nhan ca che do `balanced` lan `efficient` deu di qua duong nay). **Da va truc tiep ban cai dat cuc bo**: doi `-vsync`->`-fps_mode` o ca hai dong. Sau khi va, chay lai thanh cong That (74 frame). **Luu y**: ban va nay chi ap dung cho ban cai dat cuc bo tren may nay — mot lan `claude plugin update watch@claude-video` trong tuong lai co the ghi de, can va lai neu upstream chua tu sua. |

Whisper: **KHONG cau hinh key**, dung theo yeu cau "Do not add a paid
Whisper dependency if captions/local ASR already suffice" — chinh skill
tu bao "Without a key, /watch still works but videos without captions
come back frames-only", da xac nhan That qua lan chay thanh cong.

## 4. BANG CHUNG THAT — chay /watch tren rendered artifact That

**Nguon**: `wikitongues_henan_rendered.mkv` (46.699.303 byte) — rendered
artifact That tu lan PASS truoc cua Chinese-media pipeline (xac nhan qua
`verify_real_chinese_draft.py` trong scratch, gan voi Novel production
That `nov_41c9c967f40845a0`, cac truong `subtitle_key`/`dub_audio_key`
kieu video-draft trong `server/domain.py::Novel`).

Chay `--detail balanced --no-whisper` (khong phai token-burner, dung theo
yeu cau): **74 frame** duoc chon (uniform sampling, vi scene-detection
chi tim thay 1 canh — video la MOT canh tinh lien tuc 218 giay).

Da doc **10 frame That** qua Read tool (khong phai toan bo 74 — co y
thuc chi phi): 6 frame trai deu tren toan bo thoi luong + 3 frame tap
trung ngay diem nghi ngo (t=00:25, 00:30, 00:33, gan bien dub-audio) +
1 frame cuoi. Ket qua quan sat That:

- Mot nguoi phu nu noi chuyen truoc camera, canh tinh (talking-head),
  nhac cu (dan tranh) o hau canh — noi dung khop ten file "wikitongues
  henan" (video tu lieu ngon ngu).
- **Khong co phu de burn-in** o BAT KY frame nao da xem (khop voi ffprobe:
  chi co MOT track phu de mem SubRip, khong burn vao pixel).
- **Khong co frame den/hong** trong mau da xem.
- **Ty le khung hinh nhat quan** 1920x1080/16:9 xuyen suot.
- **Chat luong hinh anh on dinh**, khong thay hien tuong render loi.
- **Khong co dut gay hinh anh** dung ngay diem dub audio ket thuc
  (~32.9s) — nguoi vao noi chuyen tu nhien, khong co canh cat/chuyen
  canh tai do.

## 5. SO SANH VOI FFPROBE/DETERMINISTIC — dung vai tro, khong thay the

**ffprobe phat hien TRUOC, chac chan, mien phi** (khong LLM):

```
Video (VP9):  217.937s
Audio dub (MP3, mono, 22050Hz): CHI 32.940s
=> dub audio chi phu 15.1% do dai video
```

Day la mot PHAT HIEN DINH LUONG chac chan — ffprobe khong the sai ve con
so nay. Nhung ffprobe KHONG the tra loi: "video co bi dut/gay hinh anh
tai diem do khong?" — **day la cho /watch dong gop That**: doc frame
That xac nhan KHONG co dut gay hinh anh tai diem dub audio ket thuc,
nghia la day la **loi sinh dub audio khong day du** (dub processing
dung som), KHONG PHAI loi ghep/render video. Hai cong cu bo sung nhau
dung vai tro: ffprobe cho con so chac chan, /watch cho phan doan dinh
tinh (nhin co "on" khong).

**Khong de LLM thay the kiem tra deterministic**: module moi
(`synthesize_verdict()`) duoc thiet ke sao cho canh bao deterministic
(ty le dub thieu) **VAN TON TAI trong ket qua CUOI CUNG** ngay ca khi
visual review hoan toan tich cuc — xac nhan bang test That
(`test_canh_bao_deterministic_song_sot_qua_visual_tot_van_la_qa_review`)
va bang lan chay That (xem muc 6).

## 6. GIAI DOAN VISUALMEDIAQA — provider-neutral, tuy chon, y thuc chi phi

`scripts/visual_media_qa.py` (moi, 24 test qua o
`scripts/tests/test_visual_media_qa.py`):

```
RENDERED
  -> deterministic_checks()      [ffprobe/ffmpeg THUAN, khong LLM]
  -> build_watch_plan()          [quyet dinh CO can xem khong, xem O DAU]
  -> [visual_reviewer(plan)]     [MOI cho callback ngoai — noi DUY NHAT cham LLM]
  -> synthesize_verdict()        [ket hop, deterministic luon thang]
  -> QA_PASS / QA_REVIEW / QA_FAIL
```

**Y thuc chi phi, dung yeu cau**:
- Video ngan (<=600s): `balanced`, toan bo video.
- Video dai, SACH (khong canh bao deterministic): **bo qua mac dinh**,
  khong doc frame nao — chi chay khi goi `force_full_pass=True`.
- Video dai, CO bat thuong: `efficient`, chi tao window quanh dung
  timestamp bat thuong (vd bien dub-audio, doan frame den) — khong quet
  toan bo video dai.
- Xac nhan bang test That: `test_video_dai_sach_bi_bo_qua_mac_dinh`,
  `test_video_dai_co_bat_thuong_chi_zoom_vao_do`.

**Provider-neutral, tai su dung duoc cho Router V3/OpenCode/Codex**:
`WatchPlan.to_cli_invocations()` tra ve list `argv` thuan (chuoi), khong
phu thuoc doi tuong rieng cua Claude Code — bat ky agent nao co the goi
`python3 scripts/watch.py ...` deu dung duoc. `run_qa_gate()` nhan
`visual_reviewer` la MOT HAM BAT KY `(WatchPlan) -> VisualFindings` —
Router V3/OpenCode/Codex tu cung cap ham nay bang model cua ho, module
nay khong bao gio tu goi LLM.

**Khong thay deterministic bang phan doan LLM**: `deterministic_checks()`
la nguon THAT DUY NHAT cho su that cung (thoi luong, stream, codec) —
`synthesize_verdict()` khong bao gio de mot visual review tich cuc ghi
de mot canh bao deterministic that.

**Khong sua lai kien truc pipeline**: `chinese_media_pipeline.py` GIU
NGUYEN khong doi — module moi la mot ham tien ich doc lap
(`run_qa_gate()`), diem tich hop That (ngay sau `compose_with_source()`,
truoc `ship_draft()`) nhung CHUA noi day vao `main()` — vi `main()` hien
tai KHONG goi `compose_with_source()` theo mac dinh (chi chay khi co
video nguon local + rights REHOST_ALLOWED, hien tai khong co duong CLI
nao goi toi), noi them vao se la them mot thay doi hanh vi CLI ngoai
pham vi "khong thiet ke lai pipeline".

## 7. KET QUA CHAY THAT CUOI CUNG (`run_qa_gate`)

```python
run_qa_gate(video, visual_reviewer=<real_findings_from_muc_4>)
```

```
VERDICT: QA_REVIEW
deterministic warnings: ['audio stream #3 covers only 15.1% of video
  duration (32.9s / 217.9s) - likely incomplete narration/dub, not a
  sampling artifact']
plan detail: balanced, windows: 0 (video ngan, xem toan bo)
```

**QA_REVIEW la dung**: visual review hoan toan tich cuc (khong khung
hinh hong, ty le khung hinh dung, chat luong on) NHUNG canh bao
deterministic that (dub thieu 85%) van con — dung nghia la con nguoi
can quyet dinh cuoi, khong duoc tu dong pass.

## Gioi han da biet

- Ban va `-vsync`->`-fps_mode` chi o ban cai dat cuc bo, co the bi ghi
  de boi `claude plugin update`.
- `/watch` khong tu doc track phu de EMBEDDED trong file cuc bo (chi
  nhan dang caption kieu yt-dlp/hosted-video) — mot han che that cua
  chinh skill, khong phai loi tich hop.
- `deterministic_checks()` gia dinh dinh dang `tags.DURATION` kieu
  `HH:MM:SS.ffffff` khi truong `duration` cap stream vang mat (quan sat
  That tren Matroska) — cac dinh dang container khac co the can them
  fallback tuong tu, chua kiem chung ngoai MKV.

## Chi phi

$0 — plugin/yt-dlp/ffmpeg deu mien phi, khong dung Whisper API. 10 frame
That da doc (khong phai 74) — y thuc chi phi dung yeu cau "efficient/
balanced, not token-burner".

---

**MOBILE HANDOFF MAX 7 LINES**
Status: /watch da cai dat That qua Claude Code plugin, da patch 1 loi tuong thich FFmpeg 9.0, VisualMediaQA stage that + 24 test PASS
Watch installed: Co — claude plugin marketplace add + install, xac minh yt-dlp/ffmpeg/Python/Windows That
Real video watched: wikitongues_henan_rendered.mkv (218s, artifact That tu PASS run truoc) — 74 frame, 10 da doc
Visual QA: Canh tinh xuyen suot, khong burn-in sub, khong frame hong, ty le khung hinh dung, khong dut hinh tai bien dub-audio
Issues found: ffprobe phat hien That — dub audio chi phu 15.1% (32.9s/217.9s); /watch xac nhan day la loi sinh dub, khong phai loi splice video
Integration: scripts/visual_media_qa.py — deterministic trươc, /watch tuy chon+y thuc chi phi, provider-neutral cho Router V3/OpenCode/Codex, khong sua pipeline hien co
SHA: (xem git log sau khi commit)
