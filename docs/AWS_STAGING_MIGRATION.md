# Di tru sang AWS staging — kiem ke, sao luu, khoi phuc, rollback

Tai lieu chuan bi cho muc tieu AWS EC2 staging (`ap-southeast-1`,
`t3a.medium`, 2 vCPU / 4 GiB). **Chua cat production khoi GCE.** Khong co
buoc nao trong tai lieu nay tu y doi DNS, dong bang ghi production, hay tat
GCE — nhung viec do thuoc mot nhiem vu cutover rieng, phai duoc xac minh
doc lap.

---

## 0. DIEU CHINH TIEN DE — DOC MUC NAY TRUOC

Nhiem vu goc mo ta "GCE production deployment" gom Appwrite + database +
Docker/Compose + volume + Redis, va coi AWS se nhan "Appwrite/API/control
plane". **Do that thi khong khop.** Da kiem chung truc tiep bang
`gcloud compute instances list` va SSH doc-chi-doc vao may that.

### Production THAT SU dang chay o dau

```
Cloudflare Workers (Free)      frontend Next.js qua OpenNext
  worker `fanfic-web`          domain fanfic.world
        │  HTTPS
        ▼
Render Free Web Service        BACKEND API `fas-prod-api`
        │                      autoDeploy TAT; ngu sau 15 phut khong traffic
        ▼
Appwrite Cloud (SaaS, region sgp)  +  Cloudflare R2 (bucket fanfic-prod)
        ▲
        │ claim job
GCE `fanfic-worker-prod`       asia-southeast1-b, CHI worker
```

| Hang muc | Nhiem vu goc gia dinh | Do that tren may |
|---|---|---|
| Appwrite production | Tu luu tru tren GCE, can di tru | **Appwrite Cloud (SaaS), region `sgp`** — khong nam tren GCE, khong co gi de di tru |
| Database production | Backend/version can kiem ke | **Khong co** — Appwrite Cloud quan ly. Khong co MongoDB/MariaDB/PostgreSQL nao thuoc production |
| Redis production | Can kiem ke | **Khong co tren duong production** |
| Docker/Compose production | Cau hinh can sao chep | **Khong co Docker tren may production** (`which docker` -> absent) |
| Volume production | Can sao luu | **Khong co volume Docker nao** — worker chi co `/var/lib/...` cua systemd |
| API production | GCE | **Render** (`fas-prod-api`), khong phai GCE |
| Trach nhiem GCE production | Appwrite/API/control plane | **Chi 2 worker + 1 timer suc khoe** (chi tiet muc 1) |

### Co HAI may GCE, va chung khac vai tro hoan toan

| May | Zone | Loai | Vai tro | Co phai production? |
|---|---|---|---|---|
| `fanfic-worker-prod` | `asia-southeast1-b` | `e2-medium` (2 vCPU / 4 GiB) | TTS worker + translation worker + health timer | **CO** |
| `fanfic-appwrite-temp` | `us-central1-c` | `c4-standard-2` (2 vCPU / 6.8 GiB) | Appwrite **tu luu tru** 1.9.6 cho **dev/staging** (`appwrite-dev.fanfic.world`) | **KHONG** — `docs/DEV_SELFHOST_APPWRITE.md` ghi ro production dung Cloud that, con may nay la dev/staging; ten may co chu `temp` |

Toan bo danh sach can kiem ke trong nhiem vu goc (phien ban Appwrite, DB
backend, Docker/Compose, volume, Redis, sao luu/khoi phuc) **thuoc
`fanfic-appwrite-temp`** — tuc thuoc dev/staging, khong phai production.

### Vi sao `t3a.medium` cho biet dich den thuc su la worker

`t3a.medium` = 2 vCPU / 4 GiB, **khop chinh xac** `e2-medium` cua
`fanfic-worker-prod` (dang dung 1.8/3.8 GiB). Con
`fanfic-appwrite-temp` dang dung **3.6/6.8 GiB** de chay dong thoi MongoDB +
PostgreSQL + MariaDB + Redis + Traefik + cac worker cua Appwrite.

> **CANH BAO KICH CO:** neu y dinh that su la dua **Appwrite tu luu tru** len
> AWS staging, thi `t3a.medium` (4 GiB) **thieu** — muc su dung hien tai da
> 3.6 GiB *truoc khi* tinh dem cho he dieu hanh, va GCE dang co 4 GiB swap
> ho tro. Can `t3a.large` (8 GiB) hoac tuong duong. Neu dich den la **worker**
> (cach doc khop voi kich co da chon), `t3a.medium` la du va la mot doi mot.

Tai lieu nay lam ke hoach cho **ca hai** cach doc, tach ro o muc 4.

---

## 1. KIEM KE CHINH XAC — `fanfic-worker-prod` (production)

Do bang SSH doc-chi-doc ngay `2026-09-03`.

| Hang muc | Gia tri do duoc |
|---|---|
| Zone / loai may | `asia-southeast1-b` / `e2-medium` (2 vCPU, 4 GiB) |
| He dieu hanh | Ubuntu 24.04.4 LTS |
| Ngay tao | `2026-08-08` |
| Uptime luc do | 10 ngay 3 gio |
| RAM | 3.8 GiB tong — **1.8 GiB dung**, 2.0 GiB con dung duoc |
| Swap | **0 B (khong co swap)** |
| Disk | boot 20 GB (`/dev/root` 19G) — **8.4G dung, 46%**; khong co disk du lieu roi |
| Load average | 0.18 / 0.08 / 0.02 (rat nhe) |
| IP | ngoai `34.21.166.133`, trong `10.148.0.2` |
| Network tag | **khong co** -> khong mo cong vao; worker chi goi ra |
| Scheduling | `automaticRestart: true`, `onHostMaintenance: MIGRATE`, khong preemptible |
| Docker | **KHONG cai** |
| Python | `3.12.3` (venv tai `/opt/fanfic-audio/.venv`) |
| ffmpeg / ffprobe | `/usr/bin/ffmpeg`, `/usr/bin/ffprobe` — ffmpeg `6.1.1-3ubuntu5` |

### Dich vu systemd dang chay

| Unit | Trang thai | Viec |
|---|---|---|
| `fanfic-worker-prod.service` | active running | TTS worker — `python -m server.worker --require-env production` |
| `fanfic-translation-worker-prod.service` | active running | translation worker — `python -m server.translation_worker --require-env production` |
| `fanfic-worker-prod-health.timer` | active running | goi health service **moi 2 phut** |
| `fanfic-worker-prod-health.service` | oneshot | chay `server.worker --check`; neu nhip cu thi `systemctl restart fanfic-worker-prod.service` |

Ca hai worker: `User=fanfic`, `Group=fanfic`, `Restart=always`,
`RestartSec=10`, `RestartPreventExitStatus=2`, `StartLimitBurst=5` trong
`StartLimitIntervalSec=300`, `KillSignal=SIGTERM`.

### Duong dan tren may (day la "state" that can mang theo)

| Duong dan | Noi dung | Co phai state ben? |
|---|---|---|
| `/opt/fanfic-audio` | ban checkout ma nguon + `.venv` | **Khong** — tai tao tu git |
| `/opt/fanfic-models` | model Piper — **1.5 GB** | Khong ben, nhung **phai co san** truoc khi worker chay |
| `/etc/fanfic-audio/worker-prod.env` | bien moi truong TTS worker | **CO — bi mat** |
| `/etc/fanfic-audio/translation-worker-prod.env` | bien moi truong translation worker | **CO — bi mat** |
| `/var/lib/fanfic-audio-prod` | `FAS_VAR_DIR` cua TTS worker (nhip, trang thai job) | **CO** |
| `/var/lib/fanfic-audio-translation-prod` | `FAS_VAR_DIR` cua translation worker | **CO** |

`/etc/fanfic-audio/` va hai thu muc `/var/lib/...` **khong doc duoc** bang
tai khoan SSH thong thuong (Permission denied) — dung nhu mong doi ve bao
mat. Kich co that cua hai thu muc state **chua do duoc** (can quyen root):
xem muc 6, GAP-1.

### Bien moi truong production can co (CHI TEN — khong bao gio ghi gia tri)

Lay tu `deploy/fanfic-worker.env.example` va `server/config.py`, khong lay
tu may production:

| Bien | Vai tro |
|---|---|
| `FAS_ENV` | chon moi truong (`production`) — `--require-env production` doi khop |
| `FAS_INLINE_WORKER` | phai `false` tren may worker rieng |
| `DATA_BACKEND` | `appwrite` |
| `STORAGE_BACKEND` | `r2` |
| `APPWRITE_ENDPOINT` | endpoint Appwrite Cloud (region `sgp`) |
| `APPWRITE_PROJECT_ID` | id du an production |
| `APPWRITE_DATABASE_ID` | id database production |
| `APPWRITE_API_KEY` | **bi mat** — khoa runtime, quyen toi thieu |
| `R2_ACCOUNT_ID` | tai khoan Cloudflare R2 |
| `R2_BUCKET` | `fanfic-prod` |
| `R2_ACCESS_KEY_ID` | **bi mat** |
| `R2_SECRET_ACCESS_KEY` | **bi mat** |

Bon bien in dam la bi mat. **Khong** co bi mat nao trong git
(`.gitignore` chan `.env.*`). Trong lich su du an da tung co mot su co lo
`APPWRITE_API_KEY` production qua stack trace debug cua Appwrite — khoa da
duoc xoay vong thu cong; xem `docs/reports/appwrite-selfhost-gce-summary.md`
muc dau va muc 13.

---

## 2. KIEM KE — `fanfic-appwrite-temp` (dev/staging, KHONG phai production)

Nguon: `docs/reports/appwrite-selfhost-gce-summary.md` (30 KB, ghi lai phien
dung may nay) + `gcloud compute instances list`.

| Hang muc | Gia tri |
|---|---|
| Zone / loai | `us-central1-c` / `c4-standard-2` (2 vCPU, 6.8 GiB) |
| He dieu hanh | Ubuntu 24.04.4 LTS |
| Disk | 48 G (17.5/48 G dung sau backup) |
| RAM luc do | **3.6 / 6.8 GiB dung** |
| Swap | 4 GB (them tay, ghi trong `/etc/fstab`) |
| IP ngoai | `35.225.209.115` |
| Docker | Engine `29.7.2`, Compose `v5.4.0` (repo APT chinh thuc, dinh dang `.sources` deb822) |
| Appwrite | **1.9.6**, `docker-compose.yml`/`.env` chinh thuc ghim dung tag, kieu "advanced/custom installation" |
| DB adapter chinh | **MongoDB** (`_APP_DB_ADAPTER=mongodb`) |
| Vector DB | **PostgreSQL** |
| MariaDB | Con trong stack nhung **khong** phai adapter mac dinh |
| Redis | **Co** trong stack (cache) |
| Router | Traefik |
| Volume | named volume `appwrite_appwrite-*` (ben) |
| Cong public | **chi 22, 80, 443**. Mongo 27017 / MariaDB 3306 / Redis 6379 / PostgreSQL 5432 **khong** publish ra host (xac nhan bang `ss -tulnp`) |
| DNS | A `appwrite-dev.fanfic.world` -> `35.225.209.115` |
| TLS | Let's Encrypt, cap **thu cong mot lan** bang certbot; **het han `2026-11-14`** va **khong tu renew** (task bao tri chay theo gio co dinh, khong theo han con lai) |
| Restart policy | Cac service loi (`traefik`, `appwrite`, `mariadb`, `postgresql`, `redis`) co policy **`no`** trong compose goc; da them `/etc/systemd/system/appwrite-selfhost.service` (oneshot `docker compose up -d`) va `enable` — **chua kiem chung bang mot lan reboot that** |
| Sao luu | `~/appwrite/backup.sh` — **da chay that**, tao 566 MB tai `~/appwrite/backups/20260816T022120Z`, kem `RESTORE.md` huong dan tung volume. **Chi chay thu cong, khong lich tu dong, khong day ra ngoai VM** |
| Cloud -> self-host migration | **KHONG hoan tat** — dung vi su co lo khoa production |

> **CANH BAO:** `docker-compose.yml` va `.env` cua Appwrite **chi ton tai
> tren VM** (`~/appwrite/`), **khong** co trong kho nay. Chung la nguon su
> that duy nhat cho cau hinh Appwrite tu luu tru, va **khong** duoc sao luu
> ra ngoai VM. Xem GAP-2.

### Kien truc luu tru — GIU NGUYEN, khong dua vao EC2

| Tang | He thong | Ghi chu |
|---|---|---|
| Media nong | **Cloudflare R2** (`fanfic-prod`) | **KHONG** di tru vao EC2 |
| Luu tru lanh | **Google Drive** | **KHONG** di tru vao EC2 |
| Control plane / API / dich vu nhe luon-bat | AWS (dich den) | Chi phan nay |

---

## 3. KE HOACH SAO LUU (truoc khi lam bat ky dieu gi)

### 3.1 `fanfic-worker-prod` (production)

Worker **khong giu du lieu nguoi dung**: du lieu that o Appwrite Cloud + R2.
Nhung ba thu sau phai duoc sao luu vi khong tai tao duoc:

| Doi tuong | Cach sao luu | Dich den |
|---|---|---|
| `/etc/fanfic-audio/*.env` (bi mat) | doc bang root, **khong** ghi vao git, **khong** ghi vao kho bi mat cua ben thu ba nao chua duoc chap thuan | kho bi mat cua nguoi van hanh |
| `/var/lib/fanfic-audio-prod`, `/var/lib/fanfic-audio-translation-prod` | `tar` bang root sau khi **dung** worker (tranh doc file dang ghi) | ngoai VM |
| Snapshot toan disk | `gcloud compute disks snapshot` — re, nhanh, la duong lui chac an nhat | GCE snapshot |

Lenh snapshot (an toan, khong sua may dang chay):

```bash
gcloud compute disks snapshot fanfic-worker-prod \
  --zone=asia-southeast1-b \
  --snapshot-names=fanfic-worker-prod-pre-aws-$(date -u +%Y%m%dT%H%M%SZ) \
  --description="Truoc khi chuan bi AWS staging; khong cat production"
```

`/opt/fanfic-models` (1.5 GB) **khong** can sao luu neu tai lai duoc tu
nguon model goc — nhung phai xac nhan nguon con song truoc khi bo qua.

### 3.2 `fanfic-appwrite-temp` (dev/staging)

| Doi tuong | Cach |
|---|---|
| `~/appwrite/docker-compose.yml` + `~/appwrite/.env` | **Uu tien cao nhat** — day la cau hinh khong the tai tao. Copy ra ngoai VM (bo `.env` vao kho bi mat, khong vao git) |
| Volume `appwrite_appwrite-*` | `~/appwrite/backup.sh` (da chung minh chay duoc) + doc `RESTORE.md` di kem |
| Snapshot toan disk | `gcloud compute disks snapshot fanfic-appwrite-temp --zone=us-central1-c ...` |

**Phai sua truoc khi tin:** ban backup 566 MB dang nam **tren chinh VM no
bao ve**. Mot su co disk lam mat ca hai. Buoc dau tien cua bat ky ke hoach
di tru la **day ban backup ra ngoai VM**.

---

## 4. KHOI TAO AWS STAGING (bootstrap)

> **CHUA THUC HIEN DUOC.** Xem muc 5: may nay khong co credential AWS.

### 4.1 Neu dich den la WORKER (khop kich co `t3a.medium` — cach doc duoc de xuat)

Muc tieu: mot EC2 `t3a.medium` o `ap-southeast-1` chay **ban sao staging**
cua hai worker, tro vao **du an Appwrite/bucket R2 staging**, khong bao gio
tro vao production.

| Buoc | Viec | Kiem chung |
|---|---|---|
| 1 | EC2 `t3a.medium`, Ubuntu 24.04 LTS, gp3 20 GB, `ap-southeast-1` | `aws ec2 describe-instances` |
| 2 | Security group: **khong mo cong vao** ngoai SSH tu IP nguoi van hanh. Worker chi goi ra — giong GCE (khong network tag) | `aws ec2 describe-security-groups` |
| 3 | **Them swap 2–4 GB** (GCE dang co 0 B; day la cai thien co y, khong phai sao chep nguyen) | `free -h` thay swap > 0 |
| 4 | `apt install ffmpeg` -> phai co `ffmpeg` + `ffprobe` | `ffmpeg -version` |
| 5 | Python 3.12 + venv tai `/opt/fanfic-audio/.venv`; cai `server/requirements.txt` | `python -m pip check` |
| 6 | Tao user/group `fanfic`, khong login shell | `id fanfic` |
| 7 | Checkout ma nguon vao `/opt/fanfic-audio` o dung SHA dang chay production | `git rev-parse HEAD` khop |
| 8 | Dat model Piper vao `/opt/fanfic-models/nghitts/piper-tts` | worker khoi dong khong bao thieu model |
| 9 | Tao `/etc/fanfic-audio/*.env` voi **gia tri STAGING**, quyen `0640 root:fanfic` | `stat -c '%a %U:%G'` = `640 root:fanfic` |
| 10 | Copy 4 unit file tu `deploy/` (`fanfic-worker-prod.service`, `fanfic-translation-worker-prod.service`, `fanfic-worker-prod-health.service`, `fanfic-worker-prod-health.timer`), **doi ten/Description sang staging** | `systemctl cat` |
| 11 | `systemctl enable --now` | muc 7 (acceptance) |

**Rang buoc bat buoc:** `.env` cua staging **phai** tro vao du an Appwrite
staging va bucket R2 staging. Neu dung gia tri production, hai worker se
tranh claim job that cua production — day la che do that bai nguy hiem nhat
cua ke hoach nay.

### 4.2 Neu dich den la APPWRITE TU LUU TRU

**Khong dung `t3a.medium`.** Toi thieu `t3a.large` (2 vCPU / 8 GiB) de khop
6.8 GiB + 4 GB swap hien tai, hoac phai chap nhan giam tai co do luong.
Ngoai ra:

- Can **volume EBS rieng** cho du lieu Appwrite (GCE dang de tat ca tren boot
  disk 48 G — dung duoc, nhung tren AWS tach volume de snapshot doc lap thi
  tot hon).
- Phai mang theo **dung** `docker-compose.yml` + `.env` phien ban 1.9.6 tu
  `~/appwrite/` (GAP-2), khong tai ban moi tu Internet: MongoDB/PostgreSQL/
  MariaDB/Redis phai khop dung ban dang chay, va hai file
  `mongo-entrypoint.sh` / `mongo-init.js` **phai** tai kem cung tag (thieu
  chung Docker tao thanh thu muc rong va MongoDB do voi exit 126 — loi that
  da gap).
- Mo dung **22/80/443**, tuyet doi khong publish 27017/3306/6379/5432.
- Ke hoach TLS rieng: chung chi hien tai het han `2026-11-14` va **khong tu
  renew**.

---

## 5. TRANG THAI THUC THI — VI SAO CHUA PROVISION

| Dieu kien | Trang thai tren may nay |
|---|---|
| AWS CLI | **Khong cai** (`which aws` -> not found) |
| Credential AWS | **Khong co** (`~/.aws` khong ton tai) |
| gcloud | Co, da dang nhap (`kujopht0101@gmail.com`), project `gen-lang-client-0793420657` |
| SSH vao GCE | Duoc (da dung de kiem ke doc-chi-doc) |

=> **Khong the** khoi tao AWS staging hay khoi phuc mot ban backup that
trong phien nay. Nhiem vu goc dat dieu kien "if credentials/connectivity
permit" — dieu kien **khong** thoa. Khong bia dat trang thai da provision.

Can nguoi van hanh cung cap: AWS CLI + mot IAM principal co quyen
`ec2:*` gioi han trong `ap-southeast-1` (hoac hep hon: tao instance,
security group, EBS, key pair).

---

## 6. GAP — chi biet duoc khi cham vao may that

| Ma | Thieu gi | Vi sao quan trong |
|---|---|---|
| GAP-1 | Kich co that cua `/var/lib/fanfic-audio-prod` va `/var/lib/fanfic-audio-translation-prod` (can root) | Quyet dinh cua so ngung dich vu khi `tar` state |
| GAP-2 | `~/appwrite/docker-compose.yml` + `.env` **khong co trong kho** va khong duoc sao luu ra ngoai VM | Mat VM = mat cau hinh Appwrite tu luu tru, khong tai tao chinh xac duoc |
| GAP-3 | Chua bao gio reboot thu `fanfic-appwrite-temp` de kiem `appwrite-selfhost.service` that su dua container len lai | Restart policy goc la `no`; neu unit sai thi mot lan reboot lam Appwrite dev chet am tham |
| GAP-4 | Khong biet ban backup 566 MB co con khoi phuc duoc khong (chua bao gio thu restore) | Mot ban backup chua tung khoi phuc thu thi chua phai ban backup |
| GAP-5 | Han muc doc Appwrite Cloud production tung bao "Database reads limit for the current billing cycle has been exceeded" | Neu con hieu luc, no chan ca di tru VA hoat dong binh thuong |
| GAP-6 | Ai/cai gi con phu thuoc IP `35.225.209.115` va `34.21.166.133` ngoai DNS da biet | Doi IP co the lam do thu chua ai ghi lai |

---

## 7. TEST CHAP NHAN (acceptance) cho AWS staging

Chay theo dung thu tu. **Khong** buoc nao cham production.

| # | Phep thu | Dat khi |
|---|---|---|
| 1 | `systemctl is-active fanfic-worker-staging.service` | `active` |
| 2 | `systemctl is-active fanfic-translation-worker-staging.service` | `active` |
| 3 | `python -m server.worker --check` | exit 0 (nhip moi) |
| 4 | Kiem **cach ly**: doc `.env` staging, xac nhan `APPWRITE_PROJECT_ID` / `R2_BUCKET` **KHAC** gia tri production | khac tuyet doi |
| 5 | Tao mot job TTS **staging** that va cho hoan tat | job `completed`, audio nam trong bucket **staging** |
| 6 | Tao mot job translation **staging** | job `completed` |
| 7 | Kill worker giua luc dang xu ly, cho health timer | timer khoi dong lai worker trong <= 2 phut, job duoc claim lai (khong mat lease) |
| 8 | `reboot` may staging | ca hai worker + timer tu len lai (day chinh la GAP-3 cua GCE — dung lap lai loi do tren AWS) |
| 9 | `ss -tulnp` | **khong** cong nao lang nghe `0.0.0.0` ngoai SSH |
| 10 | `stat -c '%a %U:%G' /etc/fanfic-audio/*.env` | `640 root:fanfic` |
| 11 | Doi chieu san luong 24 gio staging vs production | khong lech bat thuong |
| 12 | Xac nhan production **khong doi**: `systemctl is-active` tren `fanfic-worker-prod` + uptime khong reset | van `active`, uptime lien tuc |

---

## 8. KE HOACH ROLLBACK

Giai doan nay **khong the** lam hong production, vi khong co buoc nao sua
production. Rollback vi vay rat re:

| Tinh huong | Hanh dong | Anh huong production |
|---|---|---|
| AWS staging sai cau hinh | `systemctl disable --now` hai unit tren EC2; terminate instance | **Khong** |
| Lo `.env` staging tro vao production | **Dung ca hai worker staging NGAY**, xoay vong khoa staging, kiem `store.list_events` xem co job nao bi claim sai | Co the co — phai kiem, xem test #4 la cong chan |
| Snapshot GCE can dung lai | Tao disk moi tu snapshot, tao VM moi; **khong** ghi de VM dang chay | **Khong** |
| Cutover that bai (nhiem vu SAU nay) | Giu `fanfic-worker-prod` chay; chi tro DNS/cau hinh ve lai; **khong** tat GCE cho den khi AWS chay on dinh qua mot chu ky day du | Do la ly do khong tat GCE som |

**Nguyen tac:** `fanfic-worker-prod` **van chay** trong suot giai doan
staging. Hai worker cung claim job cua CUNG mot du an Appwrite se tranh
nhau — nen staging **phai** dung du an/bucket rieng (test #4). Do la rang
buoc an toan quan trong nhat cua toan bo ke hoach.

---

## 9. VIEC TIEP THEO (theo thu tu)

1. **Day ban backup Appwrite ra ngoai VM** (GAP-2, GAP-4) — viec cap thiet
   nhat va doc lap voi AWS: hien tai ban backup nam tren chinh may no bao ve.
2. Thu restore ban backup do vao mot VM dung-mot-lan (GAP-4).
3. Xac nhan han muc doc Appwrite Cloud production con bi chan hay khong (GAP-5).
4. Cung cap credential AWS -> chay muc 4.1.
5. Reboot thu `fanfic-appwrite-temp` trong cua so bao tri (GAP-3).
6. Chi khi muc 7 dat **toan bo** 12 phep thu moi mo nhiem vu cutover rieng.

**Khong** lam trong pham vi tai lieu nay: doi DNS, dong bang ghi production,
tat GCE.

---

# GIAI DOAN 2 — CONG CU DA DUNG SAN (2026-09-03)

Bon tep, hai buoc can quyen. Moi thu khac tu dong.

## A. Dua backup Appwrite RA KHOI VM (uu tien 1)

| Tep | Chay o dau | Viec |
|---|---|---|
| `scripts/ops/appwrite_backup_offvm.sh` | **tren VM, mot lan, can quyen root** | kiem ke -> chay `backup.sh` da phe chuan -> tar + SHA256 + manifest tung tep -> de o `/var/tmp/...` cho user SSH doc duoc |
| `scripts/ops/appwrite_backup_to_drive.py` | may dieu hanh, tu dong | keo ve -> doi soat SHA -> `rclone copy` len Drive -> `rclone check` doc lap -> **tai LAI tu Drive** -> giai nen -> doi soat tung tep voi manifest |

Dich tren kho lanh: `fanfic-gdrive:FanficWorld/archive/infra/appwrite-selfhost/<stamp>`
(theo dung quy uoc `archive/<nhom>/...` da co: animation-worker, experiments,
final, scraping).

**Duong ong da duoc CHUNG MINH truoc khi du lieu that di qua no** — chay tren
mot fixture tong hop mo phong dung layout staging:

| Buoc | Ket qua |
|---|---|
| `rclone copy --checksum` | exit 0 |
| `rclone check --one-way` | exit 0, 3 tep / 2539 byte tren Drive |
| tai LAI tu Drive | SHA256 khop ban goc |
| giai nen ban tu Drive | 6 tep / 7283 byte |
| doi soat tung tep voi manifest | 0 lech |
| nhan dang cau truc | mongo / mariadb / postgres / redis / uploads / RESTORE.md |
| **ket luan** | **PASS** |

Drive con **4.78 TiB** trong 5 TiB — du rong cho ban 566 MB.

**KHONG day truc tiep tu VM len Drive** (co y): `rclone` khong co tren VM va
cung khong nen co — dat credential Drive len mot may dang mo 80/443 ra
Internet la mo rong be mat tan cong khong can thiet. Ban backup di
VM -> may dieu hanh -> Drive.

**KHONG xoa ban local.** Ca hai script chi DOC va TAO THEM.

### Vi sao can dung MOT lenh co quyen

| Ro can | Ly do |
|---|---|
| doc `/home/robux/appwrite/backups/` | thuoc user khac, mode 0750 |
| goi Docker de dong bang volume | user SSH cua phien (`nguye`) khong o trong group `docker` |

`groups` cua `nguye` CO `google-sudoers`, nen leo thang quyen se chay duoc —
nhung guard cua kho (`.claude/hooks/guard_indirect_exec.py`) chan viec do nhu
mot ranh gioi cung, va lach mot deny rule khong phai cach lam. Nen buoc do la
cua nguoi van hanh.

## B. Dung lai vai tro worker tren AWS (uu tien 2)

| Tep | Viec |
|---|---|
| `scripts/ops/worker_bootstrap.sh` | idempotent, Ubuntu 24.04 bat ky. apt + venv + systemd. **Khong CloudFormation, khong SSM, khong AMI rieng, khong userdata phu thuoc EC2** — dung y nguyen duoc tren EC2/GCE/Hetzner/VPS tran |
| `deploy/fanfic-translation-worker.service` | **MOI** — `deploy/` chi co ban `-prod` cho worker dich; thieu ban staging thi khong dung lai duoc DAY DU vai tro cua `fanfic-worker-prod` (dang chay CA HAI worker) |
| `scripts/ops/worker_staging_acceptance.py` | nghiem thu, chay tren may staging |
| `docs/reports/gce-worker-baseline.json` | baseline **do that** tren GCE de so AWS vs GCE |

Bootstrap dung **dung quy uoc ten san co** cua `deploy/` (khong hau to =
staging, `-prod` = production) — khong bay ra ten `-staging` moi. Model Piper
duoc them bang **drop-in** systemd (`10-piper-models.conf`) thay vi sua unit
da phe chuan trong kho, nen `deploy/*.service` con doi chieu duoc voi
production khi co su co.

### Rao chan quan trong nhat

`worker_staging_acceptance.py` kiem **truoc moi thu khac** va TU CHOI chay
tiep neu khong dat:

```
FAS_ENV             == staging
R2_BUCKET           != fanfic-prod
APPWRITE_PROJECT_ID != du an production   (khi truyen --prod-project-id)
FAS_INLINE_WORKER   == false
```

Neu staging tro vao du an/bucket production thi hai worker se tranh claim
**job THAT** cua production. Do la che do that bai nguy hiem nhat cua ca ke
hoach, nen no la bai kiem so 0.

Bo nghiem thu con kiem: worker len lai sau reboot (`is-enabled`), phu thuoc
runtime, `ngochuyennew.onnx` (= "Ngoc Huyen (Moi)", **model KHAC**
`ngochuyen.onnx`) con dung, ket noi Appwrite Cloud / R2 / API / Drive, nhip
`--check`, log JSON qua journald, va rang worker **TU CHOI** khi bi ep
`--require-env production` (mong doi exit 2).

### Chi tiet tai san xuat de nham

`.onnx.json` cua ca 25 giong la **SYMLINK** tro vao MOT `config.json` dung
chung. Copy ma deref symlink se phong to vo ich. Va `ngochuyennew` la mot
model KHAC `ngochuyen` — `voice_id` (`piper:<voice_key>`) da nam trong job cu
VA gop phan sinh `output_key` tren R2, nen ten tep KHONG duoc doi.

## C. Chua provision AWS — va viec DUY NHAT can de mo duong

| Dieu kien | Trang thai do that |
|---|---|
| `aws` CLI | **khong cai** |
| `~/.aws` | **khong ton tai** |
| bien moi truong `AWS_*` | **khong co** |
| khoa `.pem` | **khong co** — chi co khoa GCE |
| terraform / pulumi | **khong cai** |

Dieu kien "if credentials permit" cua nhiem vu **khong thoa**. Khong bia
trang thai AWS.

**Mot viec duy nhat can nguoi van hanh** — cap duong vao instance
`t3a.medium` da ton tai o `ap-southeast-1`, bang MOT trong hai:

```
# (1) chi can SSH la DU cho toan bo worker_bootstrap.sh
ssh -i <khoa>.pem ubuntu@<ip-t3a-medium>

# (2) hoac cap mot IAM principal han che trong ap-southeast-1, neu muon
#     tao/sua chinh instance
aws configure --profile fanfic-staging     # sau khi cai AWS CLI
```

`worker_bootstrap.sh` **khong goi mot API AWS nao**, nen chi SSH la du. IAM
chi can neu muon dung/sua vong doi instance.
