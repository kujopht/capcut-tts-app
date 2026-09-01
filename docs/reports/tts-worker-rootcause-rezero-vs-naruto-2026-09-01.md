# TTS WORKER — SO SANH BANG CHUNG Re:Zero (thanh cong) vs Naruto (ket) (2026-09-01)

Phan hoi truoc day da ket luan dung KIEN TRUC (worker chay tren LAPTOP, khong
phai Render) nhung bi hieu nham la de xuat dung Render worker moi. Bao cao nay
lam lai theo dung 8 buoc yeu cau: so sanh THAT bang chung, khong doan.

## Hang muc | Truoc khi sua | Sau khi sua

| Hang muc | Truoc khi sua | Sau khi sua |
|---|---|---|
| Gia thuyet "job harvester bi routing khac job web" | Chua kiem chung, chi suy luan | **Loai bo hoan toan** — bang chung ca o code lan o du lieu |
| Nguyen nhan that | Nghi ngo chung "worker khong chay" | **Xac nhan chinh xac**: worker dung giua 11:36 va 16:13 UTC ngay 2026-09-01, `server/.env.production` da mat |

## 1. So sanh truc tiep 3 job record qua API (khong doan)

`GET /api/jobs/{id}` cho ca 3 job, cung token harvester:

| Field | Re:Zero (THANH CONG) | Naruto ch1 (KET) | Naruto ch2 (KET) |
|---|---|---|---|
| owner_id | svc_harvester | svc_harvester | svc_harvester |
| voice_id | piper:ngochuyennew | piper:ngochuyennew | piper:ngochuyennew |
| rate / chunk_chars | 1.0 / 2000 | 1.0 / 2000 | 1.0 / 2000 |
| created_at (UTC) | 2026-09-01 11:31:33 | 2026-09-01 16:13:26 | 2026-09-01 16:35:33 |
| started_at | 11:31:37 (4s sau) | null | null |
| status | completed | pending | pending |
| attempts | 1 | 0 | 0 |

**Moi field cau truc (owner_id, voice_id, rate, chunk_chars) GIONG HET NHAU.**
Khac biet duy nhat la thoi diem tao va trang thai thuc thi — dung nhu du doan
neu day la van de "khong co worker nao dang chay", khong phai loi payload.

## 2. Doc code claim/routing (khong doan)

Grep toan bo `server/main.py` cho `harvester_owner_user_id` chi ra ĐÚNG 3 cho
dung no: tao `Profile` cho request tu token harvester, va MOT route hoan toan
khac (`admin_scraper_publish_run`, gan owner mac dinh cho noi dung tu scraper) —
**khong co dong nao trong `recover_stale_jobs`, `_claim_stale_job`,
`_start_job_thread`, hay `_run_job` nhac den `harvester_owner_user_id`**.

Doc truc tiep `recover_stale_jobs` (dong 2546-2621): no quet TOAN BO job
`pending`/`running` **khong loc theo owner_id o bat ky buoc nao** — chi loc
theo: `_CAN_RUN_JOBS` (co toan cuc), `lease_is_live()`, co dang chay o thread
noi bo hay khong, va `voice_runnable_on_this_machine(voice_id)` (chi ap dung
khi khong phai inline_worker). **Ket luan: khong co va khong the co "loi
routing/payload rieng cho job tao boi harvester"** — code khong he phan biet.

## 3. Worker that su dung o dau

- `tasklist` toan bo tien trinh may nay: **0 tien trinh python.exe** dang
  chay.
- `python -m server.worker --check`: `FileNotFoundError` — khong doc duoc
  file nhip tim (heartbeat.json).
- `server/var/worker/` (thu muc ma vong lap `chay()` cua worker tu ghi nhip
  moi chu ky) **khong ton tai** — worker chua bao gio chay vong lap chinh voi
  var_dir mac dinh tren checkout nay (thu muc `server/var/storage/...` co rat
  nhieu file audio la do CHAY BO TEST, khong phai do worker that).
- `server/.env.production` (file credential Appwrite/R2 that, da dung THANH
  CONG cho chinh job Re:Zero — theo `mission_g_rezero_tts_runner.py` tu ghi
  lai lenh khoi phuc) **khong con ton tai** tren may nay.

## 4. Vi sao Re:Zero tung chay Piper that ma gio khong tim thay model

`desktop_app/providers/piper_models.py` co bien moi truong
`FAS_PIPER_MODELS_DIR` cho phep tro thu muc model Piper ra ngoai vi tri mac
dinh (`%LOCALAPPDATA%\FanficAudioStudio\models\piper`). Vi tri mac dinh HIEN
KHONG TON TAI tren may nay — nhieu kha nang bien nay (cung nhu credential
Appwrite/R2) tung duoc dat trong `server/.env.production` da mat, tro toi noi
model that duoc dat. Khong tim thay ho so nguoi dung Windows nao khac
("robux" nhac trong CLAUDE.md khong ton tai tren may nay) giu ban sao do.

## Ket luan cuoi cung (co bang chung, khong doan)

**KHONG PHAI loi routing/payload cua job tao boi harvester.** Nguyen nhan
duy nhat: khong co tien trinh `python -m server.worker` nao dang chay tren
may nay ke tu sau khi job Re:Zero hoan tat (~11:36 UTC), va file credential
`server/.env.production` da mat cung voi no. Kien truc "worker tren LAPTOP"
la DUNG THIET KE (theo dung `deploy/render.prod.yaml`) — khong can, va
khong nen, dung Render worker moi.

## Diem chan that su con lai (can nguoi that, khong the tu lam an toan)

1. **Credential Appwrite/R2 that** de tao lai `server/.env.production` —
   day la bi mat production, chu dong tu Render API pull ve file ma khong
   hoi truoc di nguoc lai ky luat xu ly bi mat da thiet lap xuyen suot phien
   nay (vd: toan bo kien truc harvester-token moi duoc xay rieng chi de
   TRANH dung lai bi mat rong hon). Se hoi truoc khi lam neu duoc yeu cau.
2. **File model Piper that** (`.onnx` + `.onnx.json` cho `ngochuyennew`)
   hoac gia tri that cua `FAS_PIPER_MODELS_DIR` — khong the tu suy doan
   nguon tai an toan (chinh code da ghi chu khong duoc bia dat nguon).

## Chi phi / test

$0 phat sinh (chi doc API + grep code, khong goi provider tra phi). Khong
sua code server nao trong bao cao nay (thuan chuan doan). Bo test khong
doi.
