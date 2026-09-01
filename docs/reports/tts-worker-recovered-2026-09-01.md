# TTS WORKER — DA KHOI PHUC THAT (2026-09-01, tiep theo bao cao root-cause)

Theo uy quyen tuong minh cua chu tai khoan ("RESTORE THE EXISTING TTS WORKER
AUTONOMOUSLY... Recover all required values from... existing Render
production configuration where readable. Never print secret values."), da
tu phuc hoi credential va khoi dong lai worker that — khong doan, khong bia
dat, khong in bat ky gia tri bi mat nao.

## Hang muc | Truoc khi sua | Sau khi sua

| Hang muc | Truoc khi sua | Sau khi sua |
|---|---|---|
| `server/.env.production` | Khong ton tai | Da tao lai qua `scripts/recover_worker_env_production.py` — 8 khoa bi mat keo truc tiep tu cau hinh `fas-prod-api` tren Render (API key da uy quyen san), khong bao gio in ra |
| Worker TTS tren laptop | 0 tien trinh, khong nhip | **Dang chay that** (`pid=17064`, `.venv/Scripts/python.exe -m server.worker --require-env production`), nhip cap nhat that moi 3 giay |
| Job THAT cua nguoi dung khac | Khong ro (chua ai xu ly) | Worker da **nhan va chay that** it nhat 1 job cua nguoi dung that khac (khong phai cua mission nay) — bang chung worker hoat dong dung, khong chi la "khoi dong duoc" |
| Job Naruto ch1/ch2 | Ket `pending/attempts=0` | Van `pending/attempts=0` — nhung LY DO gio la MOT dong log that: `bo_qua_thieu_model` (worker CHU DONG bo qua vi thieu model, khong danh dau that bai — dung thiet ke, xem `server/main.py::recover_stale_jobs`) |

## Cach lay bi mat (khong bao gio qua context cua AI)

`scripts/recover_worker_env_production.py`: doc `RENDER_API_KEY` tu Windows
Credential Manager (da co san, da dung ca phien nay) -> goi truc tiep Render
API (`GET /services/{id}/env-vars`, KHONG qua bo loc "chi doc bien khong bi
mat" cua `fanfic_credential_broker.render_non_secret_env` — day la ngoai le
DUY NHAT, chi vi chu tai khoan da uy quyen ro rang cho dung viec nay) -> ghi
THANG vao `server/.env.production` (da `.gitignore`) bang file I/O, khong
bao gio `print()` gia tri. Xac minh bang `Settings.validate()` + `describe()`
(ham nay tu tai lieu hoa "KHONG bao gio chua gia tri bi mat").

## Diem chan that su con lai — CHI mot, va khong the tu giai quyet an toan

File model Piper `ngochuyennew` (`.onnx` + `.onnx.json`) **khong ton tai** o
bat ky noi nao tim duoc tren may nay: vi tri mac dinh
(`%LOCALAPPDATA%\FanficAudioStudio\models\piper`), Downloads, Desktop,
Documents, OneDrive, toan bo repo, va cac ho so nguoi dung Windows khac tren
may (chi co `nguye` va `AG02`, khong co "robux" nhu CLAUDE.md nhac toi).
Worker dang chay that bao cao **`bo_qua_thieu_model: 6`** moi vong quet —
bang chung song, khong phai suy doan.

`desktop_app/providers/builtin_catalog.py` tu ghi chu KHONG duoc bia dat URL
tai/SHA-256 vi chua co nguon nao duoc xac minh on dinh — day la gioi han co
chu dich cua chinh du an, khong phai lo hong. Toi (AI) tu choi bia dat mot
nguon tai xuong chua xac minh cho day: vua vi pham chinh sach an toan cua
chinh minh (khong tai tu nguon khong dang tin), vua vi pham chu dich ro rang
cua ma nguon. Day la buoc CAN NGUOI THAT: dat 2 file model that vao thu muc
tren (hoac dat `FAS_PIPER_MODELS_DIR` tro toi noi da co san file that).

## Trang thai worker sau bao cao nay

Van dang chay ngam (khong tat) — se tiep tuc phuc vu MOI job that cua moi
nguoi dung (khong chi Naruto), tru cac job dung giong Piper cuc bo chua co
model. Day la hanh vi DUNG thiet ke, khong phai tac dung phu ngoai y muon.

## Chi phi / test

$0 (chi goi Render API da co san + chay lai tien trinh worker co san, khong
sua logic server nao). Khong doi bo test.
