# Kien truc Character LoRA + Bo cuc 2 nhan vat co kiem soat — 2026-09-01

Quyet dinh cuoi cung tu proof That tren Beam: **IP-Adapter tich hop ky
thuat = PASS. Chat luong san xuat = FAIL** (3 nguoi thay vi 2, danh tinh
Anastasia bi nhan ban, mat nu bi khuat/kem, chi tiet mat Subaru bi meo,
sinh chu/gibberish, bo cuc khong dung duoc). Theo dung chi thi: **DUNG
HAN moi tinh chinh prompt/mask/strength IP-Adapter tiep theo.**

Tai lieu nay ghi lai kien truc MOI duoc thiet ke dem nay — khong GPU
that, khong train LoRA nao, khong tai dataset nao tu dong.

## 1. Track A — Schema CharacterIdentity (da lam, that)

`server/character_identity.py::CharacterVisualIdentity` them 5 truong
tuy chon, hoan toan trung lap provider (khong import beam/torch/
diffusers/PIL — van kiem tra THAT bang AST):

| Truong | Y nghia |
|---|---|
| `lora_asset_id` | Duong dan/dinh danh file LoRA that (R2 key, HF repo id, duong dan cuc bo). Rong = chua co LoRA cho nhan vat nay |
| `lora_trigger_tokens` | Tu/cum tu kich hoat mong doi trong prompt luc train |
| `lora_recommended_strength` | Cuong do `set_adapters()` de xuat (0.6-1.0 dien hinh) |
| `lora_compatible_base_model` | Checkpoint CHINH XAC da train/kiem chung — BAT BUOC khi `lora_asset_id` duoc dien |
| `lora_provenance` | Nguon goc/giay phep file LoRA |

**Ca hai nhan vat hat giong (Subaru, Anastasia) van de TRONG cac truong
nay** — nghien cuu that qua Civitai/HuggingFace (2026-09-01) tim thay
NHIEU LoRA cong dong cho ca hai nhan vat, nhung KHONG co ban nao da xac
minh tuong thich voi `cagliostrolab/animagine-xl-4.0` cu the (cac ban co
san train tren Illustrious, Pony Diffusion, NovelAI, hoac animagine-xl
phien ban CU). Bang chung that quan trong: chinh trang model
`animagine-xl-4.0-zero` xac nhan **"LoRA cua animagineXL V3 khong dung
duoc cho animagineXL V4"** — LoRA KHONG tuong thich cheo checkpoint, y
het lop loi ViT-bigG/ViT-H da gap va sua truoc do trong cung mission
nay. Vi vay: **can train LoRA moi, khong the "muon" mot LoRA cong dong
co san.**

`server/cover_pipeline.py` them `LoraPlan`/`LoraPlanEntry` +
`CoverPromptBuilder.build_lora_plan()` — ke hoach thuan (khong goi
diffusers), ho tro **dung 3 truong hop yeu cau (Requirement 3)**:
- `mode="none"`: khong nhan vat nao co LoRA → duong dan hien co khong doi.
- `mode="single"`: DUNG mot nhan vat co LoRA → diffusers ho tro TRUC
  TIEP (`load_lora_weights` + `set_adapters`), khong can co che vung nao.
- `mode="simultaneous_unsupported"`: >= 2 nhan vat co LoRA cung luc →
  gan co **canh bao ro rang** (xem muc 2 duoi day cho ly do that).

Cung kiem tra: LoRA thieu `lora_compatible_base_model` bi BO QUA (khong
doan tuong thich), va trung `lora_trigger_tokens` giua 2 nhan vat bi canh
bao (rui ro nham dac trung o cap PROMPT, khac voi rui ro o cap TRONG SO
mo hinh).

`beam_apps/cover_illustrious_logic.py` them:
- `assert_lora_compatible_with_base_model()` — so khop CHINH XAC checkpoint,
  raise `LoraCompatibilityError` neu sai (mirror dung mau
  `assert_ip_adapter_encoder_compatible` da dung cho loi ViT-H).
- `assert_lora_plan_executable()` — raise `SimultaneousLoraNotSupportedError`
  neu >= 2 LoRA duoc yeu cau nap cung luc.

## 2. Track B — Co che kiem soat bo cuc (quyet dinh kien truc)

Nghien cuu THAT (khong doan, 2026-09-01):

| Co che | Danh gia that |
|---|---|
| Regional prompting / attention coupling | Chi la "soft nudge" (them bias vao attention logit) — VAN co the bi lan qua duong khac. Do tin cay THAP nhat trong 4 lua chon (xac nhan qua bai viet ky thuat that ve identity bleed). |
| Masked generation (IP-Adapter) | DA THU 3 LAN THAT tren Beam — van that bai bo cuc (mask chong lan → nguoi/artifact ngoai y muon). Khong du rieng le cho bai toan nay. |
| ControlNet/OpenPose | REAL, co san tren HuggingFace cho SDXL (vd `thibaud/controlnet-openpose-sdxl-1.0`), ho tro `MultiControlNet` voi mask KHONG chong lan cho nhieu nguoi — dung CHINH XAC cho "vi tri/khung hinh" nhung KHONG giai quyet van de LoRA identity (day la lop dieu khien TU THE, khac lop dieu khien DANH TINH). Han che biet that: SDXL/ControlNet-da-nguoi de bi dem sai so chi/so tay o canh nguoi. |
| Staged regional inpainting | **KHONG co san trong diffusers mot cach "mien phi"** nhung day la co che DUY NHAT giai quyet dung goc re cua van de LoRA: diffusers KHONG co regional-LoRA-masking (xac nhan qua thao luan GitHub chinh thuc: "supplying a mask for LoRA output is currently not supported by PEFT"). Bang cach nap **TUNG LoRA MOT** trong tung lan goi rieng (inpaint mask rieng, dung `StableDiffusionXLInpaintPipeline` — API co san, chuan), KHONG BAO GIO co 2 LoRA active cung luc → **khong co duong toan hoc nao de lan dac trung**, khac han "attention bias" (van co the bi lan). |

**Quyet dinh: ket hop 2 lop, chon theo do tin cay khong phai do moi la:**

1. **Lop bo cuc/tu the**: ControlNet-OpenPose-SDXL voi 2 khung xuong tu
   the (trai/phai) — quyet dinh TRUC TIEP "chinh xac 2 nguoi, vi tri,
   khung waist-up" thay vi hy vong prompt van ban dat duoc dieu do (day
   la NGUYEN NHAN GOC cua 3 lan that bai bo cuc — chi dua vao van ban).
2. **Lop danh tinh**: staged regional inpainting — sinh bo cuc nen
   (khong danh tinh cu the hoac IP-Adapter nhu hien tai) qua ControlNet,
   sau do 2 lan inpaint RIENG BIET: nap CHI LoRA Subaru → inpaint vung
   trai → go LoRA → nap CHI LoRA Anastasia → inpaint vung phai. Dam bao
   KHONG BAO GIO 2 LoRA active dong thoi.

Day la **co che nho nhat tuong thich** vi hoan toan dung API diffusers
CHINH THUC, co tai lieu day du (`load_lora_weights`/`set_adapters`/
`unload_lora_weights`, `StableDiffusionXLControlNetPipeline`,
`StableDiffusionXLInpaintPipeline`) — khong can viet attention-processor
tuy bien (mot lua chon "moi" hon nhung rui ro ky thuat cao hon nhieu, DA
BI LOAI theo dung chi thi "choose based on reliability, not novelty").

**CHUA duoc xay dung dem nay** — day la mot pipeline MOI hoan toan
(ControlNet + inpaint, khac voi txt2img+IP-Adapter hien co), can mot dot
trien khai rieng sau khi co LoRA that de kiem thu.

## 3. Track C — Chan sinh chu/logic gia (da lam, that)

`DEFAULT_NEGATIVE_PROMPT` them 17 tag CU THE nham dung dang artifact da
gap that (`title text, book title, gibberish text, random characters,
fake text, illegible text, text overlay, typography, caption, subtitle,
chapter text, japanese/chinese/korean/english text, writing,
calligraphy, stamp, seal`) — tag chung ("text") da co tu truoc nhung
KHONG DU khi model manh co xu huong ve tieu de kieu "bia sach".

Phrasing kenh PROMPT DUONG doi tu `"negative space for title"` (co the
bi hieu la yeu cau MOT vung "negative space" — mo ho) sang
`"blank space reserved for title"` (duong ban compact) va
`"clean blank area for title placement, no artwork detail there"`
(duong ban day du) — **CO CHU DINH tranh tu "text" o kenh DUONG**: CLIP
text encoder khong xu ly PHU DINH tot (mot cau "no text" o prompt DUONG
doi khi phan tac dung), nen mo ta TRANG THAI MONG MUON thay vi phu dinh
truc tiep — phu dinh THAT su nam o kenh negative_prompt rieng (CFG tru
di), da duoc tang cuong day du o tren.

`generated_text_artifact` (mission yeu cau) da TON TAI dung y nghia o
`server/cover_quality_checklist.py::CoverQualityEvaluation.text_artifact_observed`
tu Track E dem qua — KHONG tao truong trung lap.

## 4. Track D — Dinh tuyen (khong doi, da dung tu dem qua)

`server/image_router.py`'s `ImageGenerationCapability.CHARACTER_LORA` da
dung dan raise `NoCapableProviderError` ro rang khi khong provider nao
ho tro (dung the — chua provider nao ho tro CHARACTER_LORA dem nay).
Khong can sua gi them.

## 5. Track E — Uoc tinh chi phi/kha thi (UOC TINH, khong phai do that)

| Hang muc | Uoc tinh | Can cu |
|---|---|---|
| Kich thuoc 1 file LoRA SDXL | ~50-300 MB (safetensors, rank 16-64 dien hinh) | Cac ban LoRA nhan vat cong dong tren Civitai (kich thuoc niem yet cong khai) |
| VRAM tang them / 1-2 LoRA | Rat nho (~vai chuc MB moi LoRA — ma tran phan ra hang thap, KHONG phai trong so day du) | Ban chat toan hoc cua LoRA (low-rank decomposition) |
| Thoi gian nap 1 LoRA | ~1-5 giay tu Beam Volume da cache | So sanh voi thoi gian nap model goc ~40s da do that |
| Luu tru cho 100 nhan vat | ~5-30 GB (100 x 50-300MB) | Tinh tu kich thuoc trung binh o tren |
| Luu tru cho 1.000 nhan vat | ~50-300 GB | Nhu tren, x10 |
| Nap/go LoRA dong khong can rebuild container | **CO — xac nhan that qua tai lieu diffusers**: `load_lora_weights()`/`set_adapters()`/`unload_lora_weights()` la API CHINH THUC hoat dong tren mot pipeline DA nap san trong bo nho, khong can tai lai model goc |

Khuyen nghi kho luu tru: giu MOT Beam Volume "hot cache" cho cac LoRA
dang duoc dung thuong xuyen (giong co che cache trong so model goc da
co), toan bo thu vien day du (100-1.000+ LoRA) nam o R2 — tai VE Volume
lan dau nhan vat do duoc dung trong mot container, sau do dung lai nhu
trong so model goc.

## 6. Track F — Chuan bi LoRA training pipeline + dataset (THIET KE, KHONG thuc thi)

**Chua co LoRA nao ton tai cho Subaru/Anastasia tuong thich
animagine-xl-4.0** (muc 1) — vi vay theo dung chi thi, chuan bi dac ta
huan luyen thay vi mot proof co the chay ngay:

### 6.1 Dac ta dataset (KHONG tai gi tu dong)

- **So luong anh**: 30-60 anh/nhan vat (theo huong dan cong dong that ve
  training LoRA nhan vat tren Animagine — muc thuc te pho bien de dat
  chat luong on dinh ma khong overfit).
- **Nguon**: PHAI la anh CO QUYEN su dung hop phap (key visual chinh
  thuc duoc cap phep, frame anime duoc phep trich xuat theo fair-use
  giao duc/nghien cuu tuy khu vuc phap ly, hoac fan art co giay phep ro
  rang) — **operator TU chon va tai xuong, KHONG tu dong hoa buoc nay**
  (dung chi thi "do not download unapproved datasets automatically").
- **Da dang goc/bieu cam**: uu tien anh CHINH DIEN/3-4 (khop voi yeu cau
  bo cuc "facing viewer or 3/4 view" da co trong prompt), da dang bieu
  cam/anh sang de tranh LoRA "dong cung" mot tu the duy nhat.
- **Chu thich (caption)**: theo mau cong dong da xac nhan hieu qua cho
  Animagine — `1boy/1girl, <ten nhan vat>, <ten series>, <mo ta khac tuy
  y>` (xac nhan that qua nghien cuu "SDXL character training" 2026-09-01).
- **Trigger token**: dat ten duy nhat, de phan biet (vd `subaru_natsuki`,
  `anastasia_hoshin`) — khop truc tiep voi
  `CharacterVisualIdentity.lora_trigger_tokens` da co san schema.

### 6.2 Dac ta pipeline huan luyen (KHONG chay GPU)

- **Cong cu**: kohya_ss sd-scripts (chuan cong dong cho SDXL LoRA,
  tuong thich Animagine) — chay tren MOT GPU rieng (Beam hoac may khac),
  KHONG phai container `cover-illustrious` dang phuc vu production.
  Base checkpoint bat buoc: **`cagliostrolab/animagine-xl-4.0`** chinh
  xac (khong duoc dung phien ban khac, xem bang chung khong tuong thich
  cheo o muc 1).
- **Sieu tham so goi y** (tu huong dan cong dong that, CHUA kiem chung
  boi chinh du an nay): rank 16-32, learning rate ~1e-4, ~10-20 epoch
  tren 30-60 anh, resolution 1024.
- **Dau ra**: 1 file `.safetensors`/nhan vat, ghi truc tiep vao
  `CharacterVisualIdentity.lora_asset_id` + `lora_compatible_base_model
  = "cagliostrolab/animagine-xl-4.0"` + `lora_provenance` mo ta day du
  (dataset nguon, ngay train, sieu tham so).
- **Kiem chung TRUOC KHI dung san xuat**: chay MOT anh test rieng le
  (khong phai 2-nhan-vat) de xac nhan LoRA "bat" dung dac trung, TRUOC
  khi thu bo cuc 2 nhan vat.

### 6.3 Trang thai proof "high-fidelity 2 nhan vat" — CHUA THE CHUAN BI DUOC MOT SCRIPT CHAY DUOC

That thoi: proof "Subaru + Anastasia high-fidelity" ma mission yeu cau
CAN CA HAI dieu kien sau, ca hai deu CHUA co dem nay:

1. It nhat 2 file LoRA that (`lora_asset_id`) da train + kiem chung
   tuong thich animagine-xl-4.0 (muc 6.2) — **CHUA train, dung chi thi**.
2. Co che "staged regional inpainting" (ControlNet-pose + inpaint tung
   LoRA rieng, muc 2) — **CHUA duoc xay dung**, la mot pipeline MOI can
   mot dot trien khai rieng.

Vi vay, thay vi mot script GPU "san sang bam nut" (se gay hieu lam ve
muc do san sang that), da chuan bi
`scripts/beam_cover_lora_proof_readiness_check.py` — **mot script CUC
BO, KHONG GPU**, kiem tra chinh xac ca 2 dieu kien tien quyet tren va
bao cao ro cai gi con thieu, thay vi gia vo san sang.

## 7. Nguyen tac production duoc giu nguyen

- Khong GPU that, khong deploy Beam, khong publish noi dung.
- Khong train LoRA nao, khong tai dataset nao tu dong.
- Khong doi kien truc rendering (van SDXL/Animagine tuong thich hien co).
- Duong dan tieu de app-side (SVG overlay) khong doi — KHONG bao gio dua
  vao chu do diffusion sinh ra.
