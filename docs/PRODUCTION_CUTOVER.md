# Chuyen worker PRODUCTION tu GCE sang AWS

Tai lieu dieu hanh cho cuoc chuyen may worker. **Khong** doi DNS, **khong**
dong bang ghi, **khong** terminate VM nao. GCE la duong lui trong suot qua
trinh va con nguyen sau khi chot.

---

## 0. DIEU CHINH TIEN DE — DOC MUC NAY TRUOC

`docs/AWS_STAGING_MIGRATION.md` muc 0 ghi rang production dung **Appwrite
Cloud (SaaS, region `sgp`)** va rang may `fanfic-appwrite-temp` "KHONG phai
production". **Do that khong con dung nua.**

Do that ngay `2026-09-04` tu chinh dich vu Render dang phuc vu production
(`fas-prod-api`, qua `fanfic_credential_broker.render_non_secret_env` —
allowlist ap o chieu TRA VE):

| Toa do production | Gia tri that |
|---|---|
| `APPWRITE_ENDPOINT` | `https://appwrite-dev.fanfic.world/v1` |
| `APPWRITE_PROJECT_ID` | `fanfic-world-prod` |
| `APPWRITE_DATABASE_ID` | `fanfic_world_prod` |
| `R2_BUCKET` | `fanfic-prod` |
| `STORAGE_BACKEND` / `DATA_BACKEND` | `r2` / `appwrite` |

Hai he qua **phai** ghi lai:

1. May GCE ten `fanfic-appwrite-temp` (`us-central1-c`, `35.225.209.115`)
   **dang la ha tang production**, bat ke chu `temp` trong ten. Moi canh
   bao trong `AWS_STAGING_MIGRATION.md` muc 2 ve may nay (restart policy
   goc la `no`, chua bao gio reboot thu, `docker-compose.yml`/`.env` chi
   ton tai tren VM) gio la rui ro **production**, khong phai rui ro dev.
2. Cuoc chuyen nay **khong** go bo su phu thuoc vao GCE. No chi chuyen
   *worker*. Appwrite production van chay tren GCE.

Chung chi TLS o bien: `CN=fanfic.world`, Google Trust Services, het han
`2026-11-07` (Cloudflare Universal SSL, tu gia han). Chung chi **goc** phia
sau Cloudflare la ban Let's Encrypt cap tay, het han `2026-11-14`, **khong
tu gia han** — do van la mot qua bom hen gio, chi khong phai cua nhiem vu
nay.

---

## 1. TRANG THAI DO DUOC (2026-09-04)

### Ba phien ban ma nguon dang chay cung luc

| Thanh phan | SHA | Ngay | Cach xa `origin/main` |
|---|---|---|---|
| Backend API (Render `fas-prod-api`) | `516d83e` | 2026-09-03 | 65 commit |
| **Worker TTS (GCE `fanfic-worker-prod`)** | **`5c33306`** | **2026-08-21** | **313 commit** |
| May AWS (checkout san) | `9be1d07` | 2026-09-04 | 0 |

**Worker GCE la ban lac hau, khong phai API.** Worker dang cham hon API
248 commit. Day la mot su that quan trong ma ban ban giao khong neu.

### Vi sao van trien khai AWS o `origin/main` chu khong o `5c33306`

Truc giac dau tien la "chi doi may, giu nguyen ma nguon" — mot bien so mot
lan. Nhung do la truc giac **sai** o day, vi lich su Appwrite thuoc ve API
chu khong thuoc ve worker: schema production la thu ma `516d83e` can, va
`516d83e` moi hon `5c33306` rat nhieu.

Bang chung da doi chieu tung diem (`git show <sha>:<tep>`):

| Bat bien | `5c33306` | `516d83e` (API) | `9be1d07` | Ket luan |
|---|---|---|---|---|
| Cong thuc `output_key` | `audio/{owner}/{chapter}/{hash}.mp3` | y het | y het | **khong doi** — khong the mo coi audio cu |
| Bo thuoc tinh `COL_JOBS` | — | GIONG `9be1d07` tung byte | — | khong ghi thuoc tinh la |
| Bo thuoc tinh `COL_TRACKS` | — | GIONG `9be1d07` tung byte | — | khong ghi thuoc tinh la |
| `bulk_import_service.py` | khong co | **CO** | co | collection da ton tai trong Appwrite production |
| `worker.py` goi `drive_chapter_imports` | khong | **CO** | co | AWS lam dung viec API mong doi |
| Bien moi truong BAT BUOC moi | — | — | **khong co** | bien moi deu tuy chon |

Them mot lop an toan doc lap: `AppwriteMetadataStore._supported_fields()`
**bo** nhung thuoc tinh Appwrite chua co thay vi that bai — nen ke ca khi
mot migration nao do chua chay, duong tao audio khong vo.

=> Dat AWS o `origin/main` dua worker **lai gan** API, khong phai xa ra.

**Nhung phai noi thang:** cuoc chuyen nay dong thoi la mot buoc **nang ma
nguon 313 commit** cho worker. No khong phai "doi may, giu nguyen moi thu".
Cua so quan sat phai duoc doc voi hieu biet do.

### Hang doi production luc do

```
pending = 0   running = 0   lease treo = 0   an_toan_de_ban_giao = true
```

Worker TTS **khong xu ly job nao trong ~29 gio** (dong log cuoi:
`2026-09-03T03:48:28Z`). Luu luong TTS production hien gan nhu bang khong.

Mot muc tieu cua nhiem vu — "it nhat 10 job that hoan tat" — **khong the
dat duoc bang luu luong tu nhien** trong bat ky cua so hop ly nao, va
nhiem vu cam bia luu luong. Xem muc 6.

### Su co da co san, khong do cuoc chuyen nay gay ra

* `2026-09-03T02:02` worker GCE thoat bang **core dump**
  (`status=6/ABRT`, "terminate called without an active exception") sau khi
  nhan SIGTERM va bo lai **4 job dang chay**. Chung duoc nhan lai sau khi
  lease het han, nen khong mat du lieu — nhung do la ly do pha DRAIN cua
  cong cu nay **cho hang doi rong truoc**, khong dua vao "dung sach".
* `fanfic-translation-worker-prod` dang chay voi `storage_backend=local`,
  `r2_configured=false`, va **dung mot giong** (`piper:ngochuyen`). Da nhu
  vay tu `2026-08-24`. Ngoai pham vi nhiem vu nay; ghi lai de khong ai
  tuong cuoc chuyen gay ra.
* Render co hai bien moi truong ten **`Key`** va **`Value`** — gan nhu chac
  chan la mot lan dan nham o form. Vo hai, nen don.

---

## 2. CO CHE

```
scripts/ops/cutover_target.py     allowlist + khang dinh (thuan tuy, 34 bai kiem)
scripts/ops/validate_prod_env.py  chay ban khang dinh do TREN may dich
scripts/ops/prod_probe.py         do hang doi production — CHI DOC
scripts/ops/appwrite_latency.py   do do tre KE CA khi HTTP khong-2xx (16 bai kiem)
scripts/ops/prod_preflight.py     nghiem thu hinh dang production, khong tieu job
scripts/ops/prod_canary.py        mot job DRAFT that, chung minh AWS so huu
scripts/ops/fanfic_prod_admin.sh  cong dieu hanh HEP tren AWS (10 verb)
scripts/ops/install_prod_admin.sh trinh cai mot lan, can root
scripts/ops/prod_cutover.py       dieu phoi 6 pha (23 bai kiem)
```

### Vi sao khong phai mot cau sudo

Mot cau `sudo` tu xa cho moi thao tac se bien vong dieu hanh thanh mot
duong leo thang quyen tuy y. Thay vao do, cung hinh dang da chung minh o
`fanfic_staging_admin.sh`:

* `ubuntu` chi **GHI** duoc mot dong verb vao `/var/lib/fanfic-prod-admin/req`
  (thu muc `0730 root:ubuntu`: tao duoc tep, **khong liet ke duoc**)
* root (qua timer 15 giay) doc verb, **loc con `[a-z0-9-]`**, doi chieu
  ALLOWLIST, roi goi dung ham da viet san
* verb **khong bao gio** di vao shell; khong tham so duong dan; khong `eval`

Bi mat production di duong rieng: Render -> **stdin cua `ssh`** ->
`/var/lib/fanfic-prod-admin/env.stage` (`0620 root:ubuntu` — `ubuntu` GHI
duoc, **KHONG DOC lai duoc**) -> root kiem bang `validate_prod_env.py` ->
`/etc/fanfic-audio/worker-prod.env` (`0640 root:fanfic`). Khong bao gio qua
`argv`, khong bao gio ra stdout, khong bao gio xuong dia may dieu hanh.

### Rao chan quan trong nhat

`fanfic-prod-admin start` **TU CHOI** khi bat ky unit staging nao tren cung
may con `active`. Mot may chay ca hai la mot may claim job cua ca hai du an
— che do that bai nguy hiem nhat cua toan bo ke hoach, va no la bai kiem so
0 o ca ba tang (bash, Python, unit test).

---

## 3. SAU PHA

| Pha | Lam gi | Cham GCE? |
|---|---|---|
| `status` | do ca hai may + hang doi | doc |
| `prepare` | stage ma + dat env + preflight | **khong** |
| `drain` | cho hang doi rong, roi `disable --now` 3 unit GCE | dung dich vu |
| `canary` | tat staging AWS -> bat production AWS -> 1 job DRAFT that | khong |
| `observe` | lay mau dinh ky, tu dong lui khi hoi quy | khong |
| `commit` | chot cau hinh cuoi cung | khong |
| `rollback` | dung AWS, bat lai GCE | bat lai |

```bash
python scripts/ops/prod_cutover.py status
python scripts/ops/prod_cutover.py prepare
python scripts/ops/prod_cutover.py drain --dry-run     # do truoc
python scripts/ops/prod_cutover.py drain
python scripts/ops/prod_cutover.py canary
python scripts/ops/prod_cutover.py observe --minutes 30
python scripts/ops/prod_cutover.py commit
python scripts/ops/prod_cutover.py rollback            # bat ky luc nao
```

**`rollback` chay doc lap.** No khong doc tep trang thai nao — no suy ra
viec phai lam tu chinh hai may. Mot pha truoc do that bai giua chung khong
lam mat kha nang lui. Co mot bai kiem doc **ma nguon** cua `pha_rollback`
va that bai neu ai do them `json.load`/`read_text` vao do.

---

## 4. BUOC DUY NHAT CAN NGUOI

Cai cong dieu hanh production, **mot lan**, tren may AWS:

```bash
ssh -i ~/.ssh/<khoa>.pem ubuntu@<ip-aws> 'sudo bash /home/ubuntu/install_prod_admin.sh'
```

`prepare` tu stage hai tep len `/home/ubuntu` truoc, roi in dung dong lenh
nay ra va dung lai voi ma thoat `10`. Trinh cai **khong bat dich vu nao** —
cai xong may van dung yen.

Credential production **khong** can nguoi: chung den tu Render qua
`fanfic_credential_broker` (khoa Render nam trong Windows Credential
Manager cua may dieu hanh). Ranh gioi root-only cua GCE **khong** phai di
qua.

---

## 5. KHOANG TRONG DO TRE APPWRITE — DA DONG

Bo thu thap cu goi `curl ... || echo "khong do duoc"`, nen cot "do tre
Appwrite" trong moi bao cao staging deu trong.

Nguyen nhan goc khong phai "khong do duoc" ma la **tron lan hai cau hoi**:

1. mat bao lau de nhan duoc mot cau tra loi (**luon** do duoc, mien la co
   byte nao quay ve — ke ca 401)
2. cau tra loi do co phai tin hieu khoe manh khong

`scripts/ops/appwrite_latency.py` tach hai cau hoi do. `do_tre_giay` duoc
ghi nhan ngay ca khi `http_status` la 401/404/500; `khoe` chi `True` khi
2xx; `lop_that_bai` phan loai `dns` / `tls` / `ket_noi` / `het_gio` /
`http`.

**Cong khong bi noi long.** `khoe` va `do_tre_giay` la hai truong rieng, va
`dong_tom_tat()` in `KHONG-KHOE(...)` khi trang thai hong du do tre co dep
den may. Co bai kiem cho dung dieu do
(`test_co_do_tre_nhung_khong_khoe_thi_KHONG_hien_thi_nhu_dat`).

Do that tu may dieu hanh: `GET https://appwrite-dev.fanfic.world/v1/health/version`
-> **HTTP 200**, `{"version":"1.9.6"}`, ~0,39 s. Endpoint **production** tra
2xx khong can xac thuc; cai tra khong-2xx la endpoint **staging** (Appwrite
Cloud doi header du an). Nen o production cot nay se co so that.

---

## 6. VE MUC TIEU "10 JOB THAT"

Khong dat duoc bang luu luong tu nhien: production khong co job TTS nao
trong ~29 gio truoc khi do. Nhiem vu cam bia luu luong de dat con so, nen
**khong bia**.

Bang chung thay the, theo thu tu suc manh:

1. **Canary DRAFT that** — di het chuoi Appwrite claim -> worker AWS ->
   Piper -> upload R2 production -> doi tuong ben -> tai lai duoc, kem hai
   bang chung so huu doc lap (`lease_owner` co PID ton tai tren may AWS, va
   khong co ban cuc bo nao de tao ket luan gia).
2. **>= 30 phut chay khoe** co lay mau, khong restart, khong lease treo.
3. **Bat ky job that nao den tu nhien** trong cua so do.

Bao cao cuoi phai noi ro con so job that dat duoc, khong duoc lam tron len.

---

## 7. GIU DUONG LUI

* GCE **khong** bi terminate, khong bi xoa disk, khong bi doi cau hinh.
  Chi ba unit worker bi `disable --now`.
* Giu it nhat **24 gio** sau khi chot, tuy tin dung GCE con lai.
* Muon lui: `python scripts/ops/prod_cutover.py rollback`.
* Nhat ky kiem toan: `docs/reports/cutover-audit.jsonl` (JSONL; chi ten va
  ket qua, khong bao gio gia tri) + `/var/log/fanfic-prod-admin.log` tren
  may AWS.
