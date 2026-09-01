# Loai bo con nguoi khoi van hanh Beam — 2026-09-01

Muc tieu: operator khong con phai tu tay mo Cloud Shell, chay `beam deploy`,
copy URL, dat lai `BEAM_TOKEN` moi phien, hay doc dashboard bang mat. Bao
cao nay ghi lai NGUYEN NHAN GOC that cua vong lap `waiting_for_provider` vo
han, va toan bo ha tang tu dong hoa da xay dung dem nay.

## 1. Nguyen nhan goc — vong lap `waiting_for_provider` vo han (Muc E)

**That, khong doan**: `ConfiguredProvider.translate_segment()`
(`server/translation_provider_registry.py`) truoc day bat MOI
`TranslationProviderError` (bao gom loi TAM THOI nhu serverless cold-start,
connection refused, HTTP 502/503/504) va gan `_status=UNAVAILABLE`,
`_reset_at=""`. `is_available_now()` coi `UNAVAILABLE` + `reset_at` rong la
"khong dung duoc MAI MAI" trong tien trinh. Khi job duoc requeue (het
`lease_expires_at`), no goi lai `is_available_now()` — VAN False — nen
KHONG BAO GIO thu goi provider THAT LAI, chi lien tuc raise
`AllProvidersUnavailable` va lap lai chu ky cho mac dinh. Ket qua: MOT lan
loi cold-start THOANG QUA dau doc provider VINH VIEN trong bo nho tien
trinh, du Beam da khoe manh tro lai chi vai chuc giay sau.

**Sua tan goc** (`server/translation_providers.py`,
`server/translation_provider_registry.py`, `server/translation_service.py`):

| Hang muc | Truoc khi sua | Sau khi sua |
|---|---|---|
| Phan loai loi | Moi loi tu `DocuTranslateProvider` deu la MOT `TranslationProviderError` chung | 3 lop moi: `TransientProviderError` (timeout/connect/502-504/429/noi dung rong), `PermanentProviderError` (401/403/404/sai dinh dang/thieu cau hinh) |
| Cooldown loi tam thoi | `reset_at=""` — vinh vien | `reset_at` = now + 20s (`DEFAULT_TRANSIENT_COOLDOWN_SECONDS`) — TU phuc hoi |
| Loi vinh vien | Giong het loi tam thoi — van cho `waiting_for_provider` mai mai | `AllProvidersUnavailable.all_permanent=True` khi TOAN BO provider da thu la `PermanentProviderError` — `TranslationService` cho job `failed` NGAY kem loi that |
| Chan doan | Khong co truong nao | `ProviderCatalogEntry.error_class` ("transient"/"permanent"/"rate_limited"/"quota_exhausted"/"unclassified") — dung cho benchmark script in ly do THAT |

**Test moi**: 9 test phan loai loi (`test_translation_providers.py`), 6 test
transient-tu-phuc-hoi/permanent-fail-fast (`test_translation_provider_registry.py`),
1 test job-level fail-fast (`test_translation_editor.py`). Tong +16 test,
server suite 4202 → 4218, tat ca xanh.

## 2. Co che credential (Muc A)

Mo rong `scripts/fanfic_credential_broker.py` (Windows Credential Manager
qua `advapi32`, KHONG file plaintext, KHONG bien moi truong shell profile —
da co san, dung nguyen tac "operator go MOT lan qua stdin" ma mission yeu
cau) — them `"BEAM_TOKEN"` vao `KNOWN_NAMES`, KHONG tao he thong bi mat thu
hai.

`scripts/beam_credential.py::resolve_beam_token()` — diem doc DUY NHAT:
uu tien bien moi truong (hanh vi cu, cho phep ghi de tam thoi), roi moi thu
Credential Manager. Da noi vao CA 5 script `beam_*.py` truoc day tu doc
`os.environ.get("BEAM_TOKEN")` rieng le.

**MOT lenh duy nhat operator can chay (gia tri go qua stdin, khong bao gio
qua Claude)**:
```
python scripts/fanfic_credential_broker.py store --name BEAM_TOKEN
```
Sau lenh nay, MOI thao tac Beam sau do tu dong lay token, khong can
`$env:BEAM_TOKEN` lai moi phien.

## 3. Moi truong chay Beam khong-Cloud-Shell (Muc B)

**That, khong doan**: `pip install --dry-run beam-client` giai quyet SACH,
khong xung dot voi bat ky goi nao da co trong `.venv` nay (fastapi/pydantic/
starlette deu da "already satisfied"). Da cai THAT: `beam-client==0.2.207`
(keo theo `beta9==0.1.265`) — 100% native Windows pip install, KHONG WSL2,
KHONG container, KHONG Cloud Shell. Gia dinh cu trong
`scripts/beam_setup_check.py` ("install inside WSL Ubuntu 22.04") la CHUA
TUNG DUOC KIEM CHUNG — da xoa.

## 4. Loi CLI THAT, dang ton tai (Muc C) — khong phai loi phien ban cu

Doc thang ma nguon `beta9` 0.1.265 da cai (khong doan, khong doc tai lieu):

- `beta9/abstractions/mixins.py`'s generic `deploy()` (dung cho `@endpoint`
  nhu `cover_illustrious_app.py`) nhan `rollout: str = "auto"` nhu MOT
  THAM SO RIENG — khong bi cuon vao `**invocation_details_options`. AN
  TOAN.
- `beta9/abstractions/integrations/vllm.py::VLLM.deploy()` (dung cho
  `translation_hymt2_app.py`) KHONG co tham so `rollout` rieng — no roi
  vao `**invocation_details_options`, duoc forward THANG vao
  `self.print_invocation_snippet(**invocation_details_options)`. Nhung
  `print_invocation_snippet(self, url_type: str = "")` KHONG co tham so
  `rollout`, khong co `**kwargs` — nem `TypeError: print_invocation_snippet()
  got an unexpected keyword argument 'rollout'`. Day la loi THAT trong
  BAN MOI NHAT (0.1.265, khong phai ban cu lac hau) — chi anh huong duong
  `VLLM`, KHONG anh huong duong `@endpoint`.
- Crash xay ra SAU KHI `deploy_stub` RPC da thanh cong (`deploy_response.ok`
  da True, `deployment_id` da duoc gan) va TRUOC KHI `.deploy()` kip
  return — nen `beam deploy ... --format json` qua CLI KHONG BAO GIO kip
  in JSON cho duong VLLM, du deploy that su THANH CONG.

**Fix** (`scripts/beam_operator.py::cmd_deploy_vllm`): goi `.deploy()` qua
SDK Python TRUC TIEP (khong qua subprocess CLI), truyen
`invocation_details_func` — mot hook CHINH THUC, CO SAN cua chinh
`.deploy()` — tro toi mot ham RONG, ngan KHONG cho no tu goi
`print_invocation_snippet(**rollout=...)`. Sau do goi RIENG, AN TOAN
`obj.print_invocation_snippet(url_type="")` (CHI mot tham so dung) de lay
URL that qua `GetUrlResponse.url`. KHONG PATCH site-packages — dung dung
CLAUDE.md's "Do NOT patch random site-packages as the permanent solution."

`scripts/beam_operator.py check-version` ghi lai phien ban DA THU
(`beam-client==0.2.207`) va canh bao (khong chan) neu may that su cai
khac.

## 5. Operator provider-trung-lap (Muc D)

`scripts/beam_operator.py` — moi lenh tra JSON co cau truc, khong can doc
log bang mat:

```
python scripts/beam_operator.py check-version
python scripts/beam_operator.py deploy --kind endpoint --handler beam_apps/cover_illustrious_app.py:generate
python scripts/beam_operator.py deploy --kind vllm --handler beam_apps/translation_hymt2_app.py:hymt2_1_8b
python scripts/beam_operator.py list
python scripts/beam_operator.py wait-ready --url <invoke_url> --kind vllm
```

`wait-ready` kiem tra `/v1/models` (nhe, KHONG sinh token nao) voi backoff
mu CO GIOI HAN (5s → 60s, tran `--max-wait-seconds`) — KHONG poll vo han,
KHONG ton token generation chi de kiem tra san sang.

`CI=1` duoc dat cho MOI subprocess `beam` — tranh crash THAT tren Windows
(`UnicodeEncodeError` khi CLI in banner emoji duoi console cp1252 mac
dinh, tren mot may CHUA co `~/.beam/config.ini` — tai hien duoc truc tiep).
Day la CHI MOT noi dung `os.getenv("CI")` trong toan bo ma nguon beta9
(grep xac nhan) nen khong co tac dung phu nao khac.

**Test**: 12 test cho `beam_operator.py` (parse JSON deploy/list, phan
loai transient/permanent trong `wait-ready`, check-version), 4 test cho
`beam_credential.py`, 3 test cho chan doan an toan trong benchmark script
— tong 19 test moi, scripts suite 416 → 435, tat ca xanh.

## 6. Benchmark UX (Muc F)

`scripts/beam_translation_benchmark.py`: khong con in `status=
waiting_for_provider` tran. Moi lan waiting in kem `elapsed`, `retry_at`,
va `error_class` cua provider (qua `_safe_wait_diagnostic()`, KHONG BAO GIO
in token/header). Voi kien truc da sua o Muc 1, mot loi VINH VIEN gio day
dua job ve `failed` NGAY — script se bao that bai that trong vai giay,
khong con phai cho het `--poll-timeout-seconds` roi moi biet.

## 7. Trang thai Muc G — CHUA THUC HIEN DUOC (thieu credential that)

Da kiem tra: `BEAM_TOKEN` KHONG co trong bien moi truong cua phien lam
viec nay, VA CHUA TUNG duoc luu trong Windows Credential Manager (broker
bao cao `ABSENT`). Day la dung LOAI tinh huong mission tu cho phep hoi:
"unless the only missing input is a credential that has never been stored
locally."

**MOT lenh duy nhat can operator chay THU CONG** (gia tri go qua stdin,
khong bao gio qua Claude/chat):
```
python scripts/fanfic_credential_broker.py store --name BEAM_TOKEN
```
Sau lenh nay, bao operator biet — Claude se tu dong: `check-version` →
`deploy --kind vllm` (Hy-MT2 1.8B, RTX4090) → `wait-ready` → benchmark
cold+warm (dung 2 lan goi generation that, gioi han dung theo mission) →
bao cao ket qua day du (dau ra tieng Viet, wall time, token usage, uoc
tinh chi phi theo rate RTX4090 that $0.000191667/s).

**KHONG co GPU that nao duoc goi, KHONG deploy nao duoc thuc hien de tao
ra bao cao nay.**

## 8. Tong ket test + commit

Full suite (truoc khi commit): server 4218/4218, scripts 435/435,
beam_apps khong doi (khong cham file nao trong `beam_apps/tests`).
