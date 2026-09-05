# Chuyen worker production GCE -> AWS — bao cao thuc thi

Ngay chay: `2026-09-04` (gio UTC trong toan bo tai lieu).
Ket qua cuoi: xem muc 8.

---

## 1. DIEU CHINH TIEN DE — hai thu tai lieu cu ghi SAI

Truoc khi cham vao gi, phep kiem lai Phase 0 lam lo ra hai sai lech quan
trong so voi ban ban giao va so voi `docs/AWS_STAGING_MIGRATION.md`.

| Hang muc | Tai lieu cu ghi | Do that 2026-09-04 |
|---|---|---|
| Appwrite production | Appwrite Cloud (SaaS, region `sgp`) | **`https://appwrite-dev.fanfic.world/v1`** — ban TU LUU TRU tren GCE |
| Vai tro `fanfic-appwrite-temp` | "dev/staging, KHONG phai production" | **ha tang production**, bat ke chu `temp` trong ten |
| SHA worker GCE | ngang `origin/main` | **`5c33306`** (2026-08-21) |
| SHA API production (Render) | — | **`516d83e`** (2026-09-03) |
| Chenh lech worker vs API | — | **248 commit** — worker moi la ban lac hau |

**He qua phai ghi lai:** cuoc chuyen nay **khong** go bo phu thuoc vao
GCE. No chi chuyen *worker*. Appwrite production van chay tren may GCE
`fanfic-appwrite-temp`, va moi canh bao ve may do trong tai lieu cu
(restart policy goc la `no`, chua bao gio reboot thu, `docker-compose.yml`
chi ton tai tren VM) gio la rui ro **production**.

Toa do production duoc doc tu chinh dich vu Render dang phuc vu
(`fas-prod-api`) qua `fanfic_credential_broker.render_non_secret_env` —
allowlist ap o chieu TRA VE, nen mot bien bi doi ten phia Render khong the
noi rong duoc.

---

## 2. VI SAO TRIEN KHAI AWS O `origin/main` CHU KHONG O `5c33306`

Truc giac dau tien la "chi doi may, giu nguyen ma nguon" — mot bien so mot
lan. Do la truc giac **sai** o day: lich su schema Appwrite thuoc ve API
chu khong thuoc ve worker, va API moi hon worker 248 commit.

Doi chieu tung diem bang `git show <sha>:<tep>`:

| Bat bien | `5c33306` | `516d83e` (API) | `9be1d07` | Ket luan |
|---|---|---|---|---|
| Cong thuc `output_key` | `audio/{owner}/{chapter}/{hash}.mp3` | y het | y het | **khong doi** — khong mo coi audio cu |
| Bo thuoc tinh `COL_JOBS` | — | giong `9be1d07` **tung byte** | — | khong ghi thuoc tinh la |
| Bo thuoc tinh `COL_TRACKS` | — | giong `9be1d07` **tung byte** | — | khong ghi thuoc tinh la |
| `bulk_import_service.py` | khong co | **co** | co | collection da ton tai trong Appwrite production |
| `worker.py` goi `drive_chapter_imports` | khong | **co** | co | AWS lam dung viec API mong doi |
| Bien moi truong BAT BUOC moi | — | — | **khong co** | bien moi deu tuy chon |

Them mot lop doc lap: `AppwriteMetadataStore._supported_fields()` **bo**
nhung thuoc tinh Appwrite chua co thay vi that bai.

**Nhung phai noi thang:** cuoc chuyen nay dong thoi la mot buoc **nang ma
nguon worker 313 commit**. No khong phai "doi may, giu nguyen moi thu".

---

## 3. TRANG THAI TRUOC KHI CHAY

```
hang doi production : pending=0  running=0  lease_treo=0
luu luong TTS       : 0 job trong ~29 gio (dong log cuoi 2026-09-03T03:48:28Z)
GCE                 : 3/3 active, uptime 11 ngay 7 gio
```

Su co da co san, **khong** do cuoc chuyen nay gay ra:

* `2026-09-03T02:02` worker GCE thoat bang **core dump** (`status=6/ABRT`)
  sau khi nhan SIGTERM va bo lai **4 job dang chay**. Chung duoc nhan lai
  sau khi lease het han. Day la ly do pha DRAIN **cho hang doi rong
  truoc** thay vi dua vao "dung sach".
* `fanfic-translation-worker-prod` chay voi `storage_backend=local`,
  `r2_configured=false`, mot giong, va
  **`translation_provider_configured: false`** — no dang chay nhung khong
  dich duoc gi. Da nhu vay tu `2026-08-24`. Ban sao tren AWS giu nguyen
  tinh trang do.
* Render co hai bien moi truong ten **`Key`** va **`Value`** — gan nhu chac
  chan la mot lan dan nham o form. Vo hai, nen don.

---

## 4. BON LOI TIM RA BANG CACH CHAY THAT

Ban ra soat bao mat doc lap tim 10 phat hien bang cach **doc**. Bon loi
duoi day chi lo ra khi **chay** — va ba trong so do nam o dung cho nguy
hiem nhat: duong bao "an toan" va duong khoi phuc. Chi tiet o
`docs/PRODUCTION_CUTOVER.md` muc 6b.

| Ma | Loi | Vi sao dang so |
|---|---|---|
| L1 | `cong()` doc tep ket qua **dang duoc ghi**, khong thay `# exit=`, mac dinh **thanh cong** | cong an toan bao **DAT** trong khi no dang **TU CHOI** |
| L2 | `UnicodeEncodeError` (`→`, console cp1252) lam **do tien trinh giua lan tu dong rollback** | ban ghi noi "dang lui" roi im |
| L3 | Thieu `translation-worker-prod.env` -> worker dich chet, restart vo han | canary FAIL (rao chan lam **dung** viec) |
| L4 | `update` bao thanh cong trong khi **khong dong bo duoc** cong (`ProtectSystem=full` khoa `/usr`) | verb moi merge vao kho khong bao gio toi may |

Ca bon da sua tai goc, moi loi kem bai kiem hoi quy rieng.

---

## 5. CANARY — bang chung so huu cua AWS

```
job     : pending -> running -> completed trong 12.1s
giong   : piper:adam1 (qua CA HAI cong: vat ly + duoc chao ban)
fixture : novel + chuong o DRAFT, DOC LAI de xac nhan, khong bao gio PUBLIC
```

| Bang chung | Gia tri |
|---|---|
| `lease_owner` | `95127-2e6ca8bd` |
| PID `95127` ton tai tren may AWS | **True** |
| Doi tuong R2 (`fanfic-prod`) | `head` HTTP 200, **22.387 byte** |
| Tai lai tu R2 | **22.387 byte**, khop |
| Ban cuc bo tren dia AWS | **False** — khong co ket luan gia "da upload" |
| Don dep | doi tuong R2 + transcript + job + chuong + novel: **da xoa** |
| Doi tuong con sot trong bucket | `_cutover-probe/`: **0** · `audio/canary-prod-`: **0** |

---

## 6. SO SANH AWS vs GCE

| Hang muc | GCE (`e2-medium`) | AWS (`t3a.medium`) |
|---|---|---|
| vCPU | 2 | **2** |
| RAM tong | 3910 MB | 3846 MB |
| RAM con | 2074 MB | **3031 MB** |
| Swap | **0 B** | **2 GB** (cai thien co y) |
| Disk | 19 GB, dung 46% | **48 GB, dung 20%** |
| Python | 3.12.3 | **3.12.3** |
| ffmpeg | 6.1.1-3ubuntu5 | **6.1.1-3ubuntu5** |
| Model `.onnx` | 25 | **25** |
| Goi Python | 49 | 55 (SHA moi hon) |
| Kernel | 6.17.0-1022-gcp | 6.17.0-1017-aws |
| Thoi gian job DRAFT | — | **12.1 s** (staging do truoc: 13.2–13.7 s) |

---

## 7. VE MUC TIEU "10 JOB THAT"

**Khong dat duoc bang luu luong tu nhien.** Production khong co job TTS nao
trong ~29 gio truoc khi do, va nhiem vu cam bia luu luong de dat con so.
**Khong bia.**

Bang chung thay the, va gioi han cua no duoc noi thang:

1. **Canary DRAFT that** — di het chuoi Appwrite claim -> worker AWS ->
   Piper -> upload R2 production -> doi tuong ben -> tai lai duoc, kem hai
   bang chung so huu doc lap.
2. **Cua so quan sat** co lay mau dinh ky (xem muc 8).
3. **So job that den tu nhien trong cua so**: ghi dung con so do duoc.

---

## 8. KET QUA — `PRODUCTION_CUTOVER_PASS`

### Duong di cac pha

| Pha | Ket qua | Moc (UTC) |
|---|---|---|
| PREPARE | **PASS** | 2026-09-04 23:35 |
| DRAIN | **PASS** — 0 job dang chay, GCE dung sach | 23:36 |
| CANARY | **PASS** — 12,1 s | 23:37 |
| OBSERVE | **PASS** — 17 mau / 35 phut | 23:37 → 00:12 |
| COMMIT | **PASS** | 2026-09-05 00:19 |

### Cua so quan sat — 17 mau, khong mot lan hong

```
nrestarts   : 0 (suot 35 phut)
lease treo  : 0
load 1p     : 0.00 – 0.33
RAM con     : 2998 – 3029 MB (chua bao gio duoi 2,9 GB)
swap dung   : 0 MB (co 2 GB, khong cham toi)
disk        : 20%
hang doi    : pending=0 running=0 suot ca cua so
```

### Chot cuoi

| Hang muc | Gia tri |
|---|---|
| Worker production hoat dong | **AWS** `13.212.224.218` |
| SHA trien khai | `34f3953226d2c39036b8b7e4be4396107a6de40b` |
| Unit AWS | 3/3 `active` |
| Unit GCE | 3/3 `inactive` (**doc that duoc**, khong suy dien) |
| VM GCE | **CON NGUYEN** — chi dung dich vu, khong terminate |
| Job `completed` | 218 |
| Cap (chuong, bam) **trung lap** | **0** |
| Object duoi `audio/` | 517 |
| Mau audio lay lai duoc | **5/5** |
| Lease treo | 0 |

### Job that trong cua so quan sat: **0**

Noi thang: khong co job THAT nao den trong 35 phut do, vi production
khong co luu luong TTS (0 job trong ~29 gio truoc do). Muc tieu "10 job
that" **khong dat duoc** va **khong duoc bia**. Bang chung thay the la
canary DRAFT that + 35 phut chay khoe co lay mau.

---

## 9. HAI LOI TIM RA O CHINH PHA COMMIT

### C1 — cong chot fail-open khi khong lien lac duoc GCE

`_units_gce()` tra `?` khi doc that bai, va ca `canary` lan `commit` chi
loc `== "active"` — nen mot may GCE **khong lien lac duoc** di lot qua
cong **y het mot may da dung**. Fail-open o dung cai cong duoc dung de
CHUNG MINH GCE khong con chay.

Lan chay dau cua COMMIT da di qua cong nay voi `gce_units` toan `?`.
Ket luan van dung (kiem tay: GCE that su inactive), nhung **cong da khong
chung minh duoc dieu no phai chung minh**.

### C2 — ma thoat cua `systemctl` LA MOT PHAN CAU TRA LOI

Nguyen nhan goc cua C1. `systemctl is-active` thoat **khac 0** khi unit
KHONG active, va `gcloud compute ssh` truyen ma thoat cua lenh tu xa ra
ngoai. Nen mot may GCE **da dung dung nhu mong doi** lai lam `rc != 0`.

Loi nay chi lo ra **sau khi GCE that su dung** — tuc dung luc no gay hai
nhat.

| Hang muc | Truoc | Sau |
|---|---|---|
| Ket luan "doc duoc" | theo **ma thoat** | theo **so dong + tu khoa hop le** |
| Lenh tu xa | de ma thoat lan ra | ket bang `; exit 0` |
| `?` (khong ro) o `canary`/`commit` | **di lot** | **TU CHOI** (ma 6 / 7) |

Sua xong, COMMIT chay lai va doc duoc `inactive` that su.

---

## 10. DUONG LUI

* `fanfic-worker-prod` (GCE): **VM RUNNING**, ba unit `inactive`+`disabled`,
  tep unit con nguyen, checkout van o `5c33306`, 25 model con du.
* Billing GCE: **dang bat** (`billingEnabled=True`), nen duong lui khong bi
  cat vi het credit.
* Lui bang mot lenh: `python scripts/ops/prod_cutover.py rollback`.
* **Khuyen nghi giu it nhat 24 gio** ke tu `2026-09-05T00:19Z`, tuc toi
  thieu den `2026-09-06T00:19Z`. **KHONG terminate** truoc do.

## 11. VIEC CON LAI (khong chan cutover)

| Viec | Muc | Ghi chu |
|---|---|---|
| `cong()` doi dau `# exit=` phai la dong khong-rong CUOI CUNG | THAP | co y hoan den sau khi chot; xem `PRODUCTION_CUTOVER.md` muc 6b-2 |
| `translation_provider_configured: false` | — | da nhu vay tren GCE tu 2026-08-24; cuoc chuyen khong sua va khong lam te hon |
| Hai bien `Key` / `Value` thua tren Render | THAP | gan nhu chac chan dan nham o form; vo hai |
| Chung chi goc `appwrite-dev.fanfic.world` het han `2026-11-14`, khong tu renew | **CAO** | gio la rui ro PRODUCTION, xem muc 1 |
| Worker AWS chay `origin/main`, API chay `516d83e` | TRUNG BINH | lech 65 commit; theo doi |
