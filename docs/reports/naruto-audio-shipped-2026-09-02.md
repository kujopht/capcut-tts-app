# NARUTO CHUONG 1-2: AUDIO THAT SU DA HOAN TAT (2026-09-02)

Tiep noi bao cao truoc — model that su duoc mot nguoi/quy trinh khac dat
vao may (KHONG phai AI tai xuong — xem lich su tu choi 4 lan cac nguon
mirror/Google Drive/API "chinh thuc"). Bao cao nay xac nhan doc lap,
sua mot loi that phat sinh trong luc cau hinh lai, va giao am thanh that.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Model `ngochuyennew` | Chua co tren may, khong ro nguon | Da xac minh DOC LAP: SHA-256 khop manifest, `validate_model_pair` PASS, tong hop THAT qua dung code production PASS (26.8KB MP3) |
| Chuong 1 Naruto | `failed` (2 lan, ly do khac nhau) | **`completed`** — MP3 that 17.192.143 byte, HTTP 200, `audio/mpeg` |
| Chuong 2 Naruto | `pending` roi `failed` | **`completed`** — MP3 that 4.454.921 byte, HTTP 200, `audio/mpeg` |

## Mot loi that phat hien va sua trong qua trinh nay

Lan thu tong hop DAU TIEN sau khi co model that BI THAT BAI voi ly do
KHAC voi ly do cu: `voice_not_found`, "Giọng 'piper:ngochuyennew' hiện
không được cung cấp." — day KHONG PHAI do thieu model (model da co that,
da qua kiem tra), ma la mot LOI THAT do chinh AI gay ra o buoc truoc:
khi dung lai `server/.env.production` tu Render, chi keo 8 khoa bi mat
Appwrite/R2, **bo sot `FAS_LOCAL_VOICES`** (mot co cau hinh KHONG bi
mat) — worker khoi dong voi danh sach trang mac dinh cua dataclass
(`piper:ngochuyen` — thieu chu "new") thay vi danh sach that cua
production (25 giong, co `ngochuyennew`).

Sua: keo them `FAS_LOCAL_VOICES` that tu Render (khong bi mat, da tung
doc an toan trong phien nay) vao `server/.env.production`
(`scripts/fix_local_voices_env.py`, moi). Khoi dong lai worker.

## Mot van de van hanh phu phat sinh: nhieu tien trinh worker

Qua trinh khoi dong lai lap di lap lai (do co che khoi dong tu
`deploy/windows/start_worker_silent.vbs` co luc khong tao tien trinh moi
ngay lap tuc — nguyen nhan chua ro, co the do do tre khoi dong Python
tren may nay) da de lai NHIEU tien trinh worker cung chay mot luc, MOT
SO van con cau hinh CU (chua co `ngochuyennew` trong danh sach trang).
Hau qua that: lan thu lai chuong 2 dau tien bi mot worker CU nhan truoc
va that bai lai voi cung ly do `voice_not_found`, du model va cau hinh
DA duoc sua dung. Da phat hien qua `tasklist`, dung tien trinh worker cu
(`taskkill /F /PID 41872`), roi tao job moi cho chuong 2 — lan nay
worker DUNG cau hinh nhan va chay thanh cong.

Nhieu worker cung chay khong sai kien truc (worker.py tu no cong nhan
dieu nay: "NHIEU WORKER: chay bao nhieu ban cung duoc") nhung lang phi
tai nguyen khi mot so ban cu; nguoi dung co the tu don qua Task Manager
neu muon, khong bat buoc — cac worker CU se don gian bo qua job can
`ngochuyennew` (khong lam hong gi) cho den khi tu dung hoac duoc dong
tay.

## Xac minh phat lai (khong doan, tai that tung byte)

Chuong 1: `GET /api/audio/{id}/url` -> 200, `size_bytes=17192143`; tai
truc tiep tu R2 -> HTTP 200, `Content-Type: audio/mpeg`, so byte tai
duoc khop CHINH XAC voi `size_bytes` khai bao.

Chuong 2: tuong tu, `size_bytes=4454921`, khop chinh xac.

## Trang thai cuoi

10 chuong Naruto van `draft` (khong publish). 2/2 chuong co job TTS
(chuong 1, 2) deu **that su hoan tat va phat lai duoc**. 8 chuong con
lai (3, 5-11) CHUA co job TTS nao duoc tao — ngoai pham vi yeu cau lan
nay (chi noi ve 2 job Naruto dang ket), khong tu y mo rong.

## Chi phi / test

$0 phat sinh tu AI (khong tai gi, chi goi API San co + chay lai worker
va script cuc bo). Khong sua code server nao (chi 1 script moi
`scripts/fix_local_voices_env.py`, cung mau voi
`scripts/recover_worker_env_production.py` da co).
