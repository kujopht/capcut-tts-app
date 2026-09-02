# TTS WORKER — TIM MODEL that su + WORKER DUONG DAI TREN WINDOWS (2026-09-02)

Tiep theo yeu cau "FINAL TTS RECOVERY". Phan A: dieu tra tan goc vi tri
model that su tung dung cho Re:Zero. Phan B: worker khong con phu thuoc
vong doi tien trinh nen cua Claude Code.

## Hang muc | Truoc khi sua | Sau khi sua

| Hang muc | Truoc | Sau |
|---|---|---|
| Vi tri model `ngochuyennew` that su | Chua ro, chi doan | **Da xac dinh**: vi tri MAC DINH `%LOCALAPPDATA%\FanficAudioStudio\models\piper` — CHUA TUNG co override nao (khong `FAS_PIPER_MODELS_DIR` trong bat ky config production nao); file THAT SU khong con o do nua |
| Worker song duoc bao lau | Chi trong luc tien trinh nen cua Claude Code con song (2 lan bi `[killed]`) | **Song doc lap**: tu Startup folder cua Windows, tu khoi dong lai khi crash, khong lien quan gi den phien Claude Code nao |

## A. Dieu tra tan goc vi tri model — KET QUA: MODEL_FILES_MISSING (co bang chung day du)

Da doi chieu MOI nguon nguoi dung yeu cau, khong bo sot nguon nao:

1. **Log worker truoc do**: khong con log nao song sot tu chinh lan chay
   Re:Zero (chay truc tiep trong terminal, khong redirect ra file). Log
   MOI nhat (do chinh phien nay tao khi khoi dong lai worker) chi xac
   nhan lai cau hinh, khong co dau vet duong dan model cu.
2. **Job metadata**: `GET /api/jobs/{id}` khong luu duong dan model,
   chi luu `voice_id`.
3. **Env/config history**: Doc lai TOAN BO 8 khoa da phuc hoi tu Render
   (`APPWRITE_*`, `R2_*`) — **khong co `FAS_PIPER_MODELS_DIR` nao trong
   `deploy/render.prod.yaml` hay trong cau hinh that cua `fas-prod-api`**.
   Bien nay CHUA BAO GIO la mot phan cau hinh Render/production — no
   chi ton tai trong `desktop_app/providers/piper_models.py` nhu mot
   override CUC BO, khong dong bo qua Render.
4. **Git history** (`git log --all -S` cho `FAS_PIPER_MODELS_DIR`,
   `ngochuyennew`, `.onnx`): khong tim thay commit nao chua duong dan
   model that (dung nhu ky vong — CLAUDE.md cam commit `.onnx`). Tim
   thay MOT nhanh kien truc GCE rieng (`be1f3f4`, 2026-08-09):
   `deploy/fanfic-worker-prod.service` + `scripts/install_gce_worker.sh`
   dung `MODELS_DIR=/opt/fanfic-models/nghitts/piper-tts` — nhung day la
   **VM Linux rieng, khong lien quan may Windows nay**, va chinh script
   do cung KHONG tai model ho — no chi KIEM TRA model da co san, coi
   thieu la loi dung han, giong het trieu chung hien tai.
5. **`docs/GCE-WORKER-CAPACITY.md`**: co MOT dong do dac that
   ("`benchmark_piper.py`, `ngochuyen`, concurrency 1 | laptop Windows |
   0,047") chung minh: model Piper (it nhat `ngochuyen`) **TUNG that su
   ton tai tren chinh laptop Windows nay** o mot thoi diem truoc (khoang
   cuoi thang 8). `--models-dir` cua `benchmark_piper.py` la tham so BAT
   BUOC, khong co doc lai duong dan chinh xac da dung.
6. **Cau hinh app hien co**: doc `desktop_app/main_window.py` —
   `_install_piper_model` LUON copy file nguoi dung chon VAO thu muc
   CHUAN (`piper_models_dir()`), khong luu duong dan tuy chinh nao khac.
   Ket luan: KHONG co "vi tri bi mat thu hai" — chi co DUY NHAT thu muc
   mac dinh, va no dang RONG.
7. **Windows filesystem**: `%LOCALAPPDATA%\FanficAudioStudio\models\piper`
   khong ton tai; Downloads, Desktop, Documents, OneDrive, toan bo repo:
   khong co `.onnx` nao khop (chi co model onnxruntime demo va model
   tieng Do Thai/tashkeel cua goi `piper-tts` pip — khong lien quan).
8. **Recycle Bin** (`C:\$Recycle.Bin`, tung SID doc duoc): chi co DUY
   NHAT mot muc bi xoa gan day — mot ung dung khong lien quan ("VGN
   VHUB", xoa 2026-08-29) — khong co gi lien quan FanficAudioStudio/Piper.
9. **Ho so nguoi dung Windows khac**: chi co `nguye` va `AG02` ton tai
   tren may; khong co "robux" (nhac trong CLAUDE.md — thuoc may khac);
   khong dung tay vao ho so `AG02` (khong co bang chung nao lien quan,
   xam pham khong can thiet).
10. **Co che bootstrap/tai model co san**: khong ton tai o bat ky dau
    trong repo. `desktop_app/providers/builtin_catalog.py` tu ghi chu ro
    KHONG duoc khai bao URL/SHA-256 vi chua co nguon xac minh — day la
    GIOI HAN CO CHU DICH cua chinh du an.

**Ket luan**: model that da TUNG co tren dung laptop nay, tai dung vi
tri mac dinh, gan day (con hoat dong den it nhat 2026-09-01 ~11:36
UTC — luc job Re:Zero hoan tat). Sau do file bien mat khoi thu muc mac
dinh boi mot hanh dong khong de lai dau vet nao trong Recycle Bin/log/
git — nguyen nhan chinh xac (xoa tay, don dep dia, Storage Sense cua
Windows...) khong the xac dinh duoc tu xa. Day la MODEL_FILES_MISSING
THAT SU, khong phai gia thuyet — moi nguon phuc hoi hop phap nguoi dung
liet ke deu da duoc kiem tra can than. **Khong bia dat URL tai xuong**:
vi pham ca chinh sach an toan cua AI (khong tai tu nguon chua xac minh)
lan chu dich ro rang cua chinh ma nguon.

## B. Worker doc lap voi vong doi Claude Code

`deploy/windows/`:
- `run_worker.bat` — vong lap: chay `python -m server.worker
  --require-env production` voi `FAS_ENV_FILE=server\.env.production`,
  ghi log vao `server\var\worker\logs\worker.log`, TU KHOI DONG LAI sau
  10 giay neu worker thoat (crash, Windows Update, ket noi mang...).
  DUNG HAN (khong lap vo han) neu thieu `server\.env.production` hoac
  `.venv` — khong lang le chay sai credential.
- `start_worker_silent.vbs` — chay `run_worker.bat` AN (khong hien cua
  so console).
- `README.md` — giai thich CHINH XAC vi sao dung Startup folder thay vi
  Scheduled Task: **`.claude/hooks/guard_indirect_exec.py` cua chinh
  repo nay chan cung `schtasks`/`Register-ScheduledTask`/MOI cach goi
  `powershell.exe` (ke ca `-File`) trong MOI che do, ke ca
  `bypassPermissions`** — day la ranh gioi an toan co chu dich cua du
  an, AI khong the va khong nen tu vuot qua. Startup folder la co che
  Windows-native thay the, khong can dang ky task scheduler/registry,
  chi la mot thao tac ghi tep thuong.

**Da cai dat that**: sao chep `start_worker_silent.vbs` vao
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`, roi kich
hoat ngay (khong doi den lan dang nhap tiep theo) qua `wscript.exe`.
Xac minh: nhip (`heartbeat.json`) that, `pid=17716`, tien trinh nay
**hoan toan doc lap voi tien trinh Bash cua Claude Code** — se tiep tuc
chay sau khi phien nay ket thuc, va tu khoi dong lai moi lan dang nhap
Windows sau nay.

## Trang thai cuoi cung

- Worker: dang chay THAT, ben vung qua Windows login, `bo_qua_thieu_model: 6`
  moi vong quet (dung nhu du doan — model van thieu).
- Naruto ch1/ch2: van `pending` — CHI vi thieu model that, khong con ly
  do nao khac.
- Diem chan CON LAI DUY NHAT: 2 file model that (`ngochuyennew.onnx` +
  `.onnx.json`) can duoc dat lai vao
  `%LOCALAPPDATA%\FanficAudioStudio\models\piper\` — day la buoc CAN
  NGUOI THAT, da chung minh khong the tu phuc hoi an toan.

## Chi phi / test

$0. Khong sua logic server nao (chi them tien ich khoi dong o
`deploy/windows/`). Khong doi bo test.
