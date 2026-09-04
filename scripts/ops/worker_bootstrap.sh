#!/usr/bin/env bash
# Dung LAI vai tro worker cua `fanfic-worker-prod` tren mot may Ubuntu 24.04
# bat ky. KHONG phai di tru Appwrite — Appwrite la Appwrite Cloud (SaaS), va
# may nay khong chua database nao.
#
# CO Y KHONG DUNG DICH VU RIENG CUA AWS. Khong CloudFormation, khong SSM,
# khong AMI dung san, khong userdata phu thuoc EC2. Chi apt + venv + systemd,
# nen dung y nguyen duoc tren EC2, GCE, Hetzner, DigitalOcean hay mot VPS
# tran. Day la yeu cau "khong tao lock-in AWS khong can thiet".
#
#     sudo bash worker_bootstrap.sh --role staging
#
# IDEMPOTENT: chay lai nhieu lan an toan, chi bo sung phan con thieu.
#
# KHONG lam (co y): khong ghi mot GIA TRI bi mat nao, khong bat dich vu,
# khong cham gi den GCE. Co tao hai tep env nhung CHI voi TEN bien de trong —
# gia tri do nguoi van hanh nap sau bang `scripts/ops/apply_staging_env.sh`.
set -euo pipefail

ROLE="staging"
REPO_URL="${REPO_URL:-https://github.com/kujopht/capcut-tts-app.git}"
REPO_REF="${REPO_REF:-main}"
APP_DIR="/opt/fanfic-audio"
MODELS_DIR="/opt/fanfic-models/nghitts/piper-tts"
SVC_USER="fanfic"
#: Thu muc da co san 25 `.onnx` + `config.json` (vd da scp truoc vao
#: /home/ubuntu/piper-tts). Co tham so nay thi buoc 7 tu cai model va tu tao
#: lai 25 symlink, nen NGUOI VAN HANH chi phai chay DUNG MOT lenh co quyen.
MODELS_FROM=""

while [ $# -gt 0 ]; do
  case "$1" in
    --role)        ROLE="$2"; shift 2 ;;
    --ref)         REPO_REF="$2"; shift 2 ;;
    --models-from) MODELS_FROM="$2"; shift 2 ;;
    *) echo "tham so la: $1" >&2; exit 2 ;;
  esac
done

if [ "$ROLE" = "production" ]; then
  echo "TU CHOI: script nay chi de dung STAGING. Cutover production la mot" >&2
  echo "nhiem vu rieng, phai duoc nghiem thu doc lap." >&2
  exit 2
fi

echo "=== 0. DOI CHIEU voi ban da do tren fanfic-worker-prod ==="
. /etc/os-release
echo "  OS muc tieu : Ubuntu 24.04 (GCE dang: Ubuntu 24.04.4 LTS)"
echo "  OS may nay  : $PRETTY_NAME"
case "$VERSION_ID" in
  24.04) : ;;
  *) echo "  CANH BAO: khac 24.04 — python3/ffmpeg co the lech phien ban." ;;
esac

echo
echo "=== 1. GOI HE THONG (dung bo da do tren production) ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Danh sach nay lay tu `dpkg-query` tren fanfic-worker-prod, khong phai doan:
#   ffmpeg 7:6.1.1-3ubuntu5   python3 3.12.3   python3-venv 3.12.3
#   python3-pip 24.0          git 2.43.0       curl 8.5.0
#   ca-certificates           tzdata 2026c
apt-get install -y -qq \
  ffmpeg python3 python3-venv python3-pip git curl ca-certificates tzdata
echo "  ffmpeg  : $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
echo "  ffprobe : $(command -v ffprobe || echo THIEU)"
echo "  python3 : $(python3 --version)"

echo
echo "=== 2. SWAP (production dang co 0B — day la CAI THIEN co y) ==="
# fanfic-worker-prod: 3.8GiB RAM, 1.8GiB dung, KHONG co swap. t3a.medium cung
# 4GiB. Them 2GiB swap de mot dot dich/ghep audio khong bi OOM-kill giua job.
if swapon --show=NAME --noheadings | grep -q .; then
  echo "  da co swap: $(swapon --show=SIZE --noheadings | tr '\n' ' ')"
else
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap -q /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "  da them 2GiB swap, ghi ben trong /etc/fstab"
fi

echo
echo "=== 3. USER DICH VU (khong login shell, giong production) ==="
if id "$SVC_USER" >/dev/null 2>&1; then
  echo "  user $SVC_USER da co"
else
  useradd --system --create-home --shell /usr/sbin/nologin "$SVC_USER"
  echo "  da tao user he thong $SVC_USER"
fi

echo
echo "=== 4. MA NGUON tai $APP_DIR ==="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --quiet origin
  git -C "$APP_DIR" checkout --quiet "$REPO_REF"
  git -C "$APP_DIR" reset --quiet --hard "origin/$REPO_REF"
else
  git clone --quiet "$REPO_URL" "$APP_DIR"
  git -C "$APP_DIR" checkout --quiet "$REPO_REF"
fi
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
echo "  SHA: $(git -C "$APP_DIR" rev-parse --short HEAD)  ref: $REPO_REF"

echo
echo "=== 5. VENV — CHI tu server/requirements.txt ==="
# Giong dung phep thu ma CI dang cuong che: `server/requirements.txt` phai la
# DU cho backend/worker va khong keo theo PySide6.
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install --quiet -r "$APP_DIR/server/requirements.txt"
# Giong worker production: piper-tts + onnxruntime CO mat de chay giong cuc bo.
"$APP_DIR/.venv/bin/python" -m pip install --quiet "piper-tts>=1.6.0,<2.0"
if "$APP_DIR/.venv/bin/python" -m pip list --format=freeze | grep -Eiq '^(PySide6|shiboken6)'; then
  echo "  LOI: venv da keo theo PySide6 — worker khong duoc phu thuoc GUI." >&2
  exit 3
fi
echo "  so goi: $("$APP_DIR/.venv/bin/python" -m pip list --format=freeze | wc -l) (production: 49)"

echo
echo "=== 6. THU MUC TRANG THAI ==="
# Ten theo dung unit staging san co: `fanfic-audio` / `fanfic-audio-translation`
# (ban production la `-prod`). systemd cung tu tao qua `StateDirectory=`, nhung
# tao san o day de quyen dung ngay tu lan chay dau.
for d in "/var/lib/fanfic-audio" "/var/lib/fanfic-audio-translation"; do
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$d"
  echo "  $d  ($(stat -c '%a %U:%G' "$d"))"
done
install -d -m 0750 /etc/fanfic-audio
chgrp "$SVC_USER" /etc/fanfic-audio

# Viet SAN mau env — chi TEN bien, KHONG mot gia tri nao. Nguoi van hanh chi
# con dien vao cho trong, khong phai tu soan tep. KHONG ghi de neu tep that
# da ton tai: mot lan chay lai bootstrap khong duoc xoa credential.
for m in worker translation-worker; do
  mau="/etc/fanfic-audio/${m}.env"
  if [ -f "$mau" ]; then
    echo "  giu nguyen $mau (da co)"
    continue
  fi
  cat > "$mau" <<'ENVMAU'
# Bien moi truong worker STAGING. Dien gia tri vao sau dau `=`.
#
# TUYET DOI KHONG dung gia tri PRODUCTION o day. `worker_staging_acceptance.py`
# kiem dieu nay TRUOC moi thu khac va se TU CHOI chay tiep neu trung — vi hai
# worker cung claim job cua CUNG mot du an se tranh job THAT cua production.
#
# Tep nay quyen 0640 root:fanfic. Khong bao gio vao git.

FAS_ENV=staging
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite

# `local` la MAC DINH cua server/config.py va la lua chon HOP LE cho staging.
# Chon no thi KHONG can mot bien R2 nao — staging chay duoc ma khong phai
# tao hay di chuyen them credential. Danh doi da biet: khong tap duong DAY
# LEN R2. Doi thanh `r2` va dien bon bien duoi neu muon tap ca duong do.
STORAGE_BACKEND=local

# --- Appwrite (du an STAGING/DEV, KHONG phai production) ---
APPWRITE_ENDPOINT=
APPWRITE_PROJECT_ID=
APPWRITE_DATABASE_ID=
APPWRITE_API_KEY=

# --- Cloudflare R2 — CHI can khi STORAGE_BACKEND=r2 ---
# Bucket phai la STAGING (vd `fanfic-staging`), KHONG bao gio `fanfic-prod`.
R2_ACCOUNT_ID=
R2_BUCKET=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=

# --- Giong cuc bo ---
# De TRONG de tat giong Piper; hoac `piper:ngochuyen` / `piper:ngochuyennew`
# de bat. Model da duoc cai san o /opt/fanfic-models/nghitts/piper-tts.
FAS_LOCAL_VOICES=
ENVMAU
  chmod 0640 "$mau"
  chown root:"$SVC_USER" "$mau"
  # KIEM LAI truoc khi bao. Ban truoc in "da viet mau ..." ngay sau `cat >`
  # ma khong he kiem, nen bao cao co the noi tep da co trong khi no khong co
  # — va nguoi doc khong co cach nao biet. Bao cao phai noi ve thu DA DO.
  if [ ! -s "$mau" ]; then
    echo "  LOI: viet mau $mau that bai (tep khong ton tai hoac rong)" >&2
    exit 6
  fi
  echo "  da viet mau $mau ($(stat -c '%a %U:%G, %s byte' "$mau"))"
done

# Kiem lai LAN CUOI ca hai tep, va in dung nhung gi do duoc.
for m in worker translation-worker; do
  mau="/etc/fanfic-audio/${m}.env"
  [ -f "$mau" ] || { echo "  LOI: thieu $mau sau khi tao" >&2; exit 6; }
done
echo "  da kiem lai: 2/2 tep env co that tren dia"

echo
echo "=== 7. MODEL PIPER ==="
install -d -m 0755 "$MODELS_DIR"

if [ -n "$MODELS_FROM" ]; then
  if [ ! -d "$MODELS_FROM" ]; then
    echo "  LOI: --models-from '$MODELS_FROM' khong phai thu muc" >&2
    exit 5
  fi
  echo "  cai model tu $MODELS_FROM"
  # `cp` chu khong `mv`: giu nguyen ban da scp de chay lai duoc, va de
  # nguoi van hanh tu xoa khi da hai long.
  cp -f "$MODELS_FROM"/*.onnx "$MODELS_DIR"/ 2>/dev/null || true
  cp -f "$MODELS_FROM"/config.json "$MODELS_DIR"/ 2>/dev/null || true
  # TAO LAI 25 symlink. Kho lanh/scp deref symlink nen ban chuyen den chi co
  # 25 `.onnx` + MOT `config.json`; thieu buoc nay thi `PiperModelManager`
  # khong tim thay cau hinh cho tung giong.
  if [ -f "$MODELS_DIR/config.json" ]; then
    n=0
    for f in "$MODELS_DIR"/*.onnx; do
      [ -e "$f" ] || continue
      ln -sfn config.json "${f}.json"
      n=$((n + 1))
    done
    echo "  da tao lai $n symlink <voice_key>.onnx.json -> config.json"
  else
    echo "  CANH BAO: thieu config.json — khong tao duoc symlink nao" >&2
  fi
  chown -R root:root "$MODELS_DIR" 2>/dev/null || true
  chmod -R a+rX "/opt/fanfic-models"
fi

SO_ONNX="$(find "$MODELS_DIR" -maxdepth 1 -name '*.onnx' 2>/dev/null | wc -l)"
SO_LINK="$(find "$MODELS_DIR" -maxdepth 1 -name '*.onnx.json' 2>/dev/null | wc -l)"
echo "  model dang co: $SO_ONNX / 25 (production co 25, moi ban ~63.5MB, tong ~1.5GB)"
echo "  cau hinh giong: $SO_LINK / 25 (<voice_key>.onnx.json)"
for k in ngochuyen ngochuyennew; do
  if [ -f "$MODELS_DIR/$k.onnx" ]; then
    echo "  CO    $k.onnx"
  else
    echo "  THIEU $k.onnx"
  fi
done
if [ "$SO_ONNX" -lt 25 ]; then
  cat <<'MODELNOTE'
  CHUA DU MODEL. KHONG tai tu Internet o day: cac tep .onnx nay la tai san
  cua du an, khong phai goi cong khai, nen script se KHONG doan mot URL.

  Da co ban tren kho lanh Drive tu 2026-09-04 (28 tep, 1.587.941.103 byte,
  `rclone check --one-way` exit 0). Truoc do bo model TON TAI DUY NHAT tren
  dia boot cua fanfic-worker-prod — xem scripts/ops/piper_models_to_drive.py.

  Cach dua model len — chay TU MAY DIEU HANH (noi da co remote
  `fanfic-gdrive` xac thuc san), KHONG cai rclone tren may staging:

    # 1. tai tu kho lanh ve may dieu hanh
    rclone copy fanfic-gdrive:FanficWorld/archive/infra/piper-models \
        ./piper-tts --checksum

    # 2. day len may staging
    scp -i <khoa>.pem -r ./piper-tts/* \
        ubuntu@<host>:/opt/fanfic-models/nghitts/piper-tts/

    # 3. TREN may staging — dung lai 25 symlink
    bash /opt/fanfic-models/nghitts/piper-tts/TAO_LAI_SYMLINK.sh \
        /opt/fanfic-models/nghitts/piper-tts

  Buoc 3 la BAT BUOC. Cau truc that tren production la:
    - 25 tep <voice_key>.onnx (moi ban ~63.516.050 byte)
    - MOT tep config.json dung chung
    - 25 SYMLINK <voice_key>.onnx.json -> config.json
  Kho lanh CO Y khong luu 25 symlink (scp/rclone deref chung thanh 25 ban
  sao giong nhau cua cung mot tep), nen phai tao lai o dau ben nay.

  Giong "Ngoc Huyen (Moi)" = `ngochuyennew.onnx` (KHAC `ngochuyen.onnx`).
  Ca hai da duoc kiem co mat trong ban tren Drive.
  `voice_id` (`piper:<voice_key>`) da nam trong job cu VA gop phan sinh
  `output_key` tren R2, nen ten tep KHONG duoc doi.
MODELNOTE
fi

echo
echo "=== 8. UNIT SYSTEMD ==="
# Dung DUNG quy uoc san co cua `deploy/`: khong hau to = staging,
# `-prod` = production. KHONG bay ra ten `-staging` moi.
#   fanfic-worker.service         <-> fanfic-worker-prod.service
#   fanfic-worker-health.service  <-> fanfic-worker-prod-health.service
#   fanfic-worker-health.timer    <-> fanfic-worker-prod-health.timer
#   fanfic-translation-worker.service  (them moi: chi co ban -prod)
for u in fanfic-worker.service fanfic-translation-worker.service \
         fanfic-worker-health.service fanfic-worker-health.timer; do
  src="$APP_DIR/deploy/$u"
  if [ -f "$src" ]; then
    install -m 0644 "$src" "/etc/systemd/system/$u"
    echo "  da dat $u"
  else
    echo "  THIEU $src — chua the bat $u"
  fi
done

# Unit staging CO Y khong dat `FAS_PIPER_MODELS_DIR` (xem bang trong
# fanfic-worker-prod.service). Nhung staging tren AWS PHAI kiem duoc giong
# cuc bo — "Ngoc Huyen (Moi)" = `ngochuyennew` — nen bo sung bang DROP-IN
# thay vi sua unit da duoc phe chuan trong kho. Drop-in la cach systemd
# dung de chinh mot unit tai cho, va no giu `deploy/*.service` nguyen ban
# nen con doi chieu duoc voi production khi co su co.
install -d -m 0755 /etc/systemd/system/fanfic-worker.service.d
cat > /etc/systemd/system/fanfic-worker.service.d/10-piper-models.conf <<DROPIN
# Sinh boi scripts/ops/worker_bootstrap.sh — KHONG sua tay.
# Model chi DOC: khong them vao ReadWritePaths, dung ly le nhu ban production
# (mot tien trinh bi chiem khong duoc sua duoc model).
[Service]
Environment=FAS_PIPER_MODELS_DIR=$MODELS_DIR
DROPIN
echo "  da dat drop-in 10-piper-models.conf (FAS_PIPER_MODELS_DIR)"

systemctl daemon-reload

echo
echo "=== 9. TUONG LUA / MANG ==="
# fanfic-worker-prod KHONG co network tag nao -> KHONG mo cong vao. Worker chi
# GOI RA: Appwrite Cloud (443), R2 (443), Render API (443), Drive (443).
# Tren AWS: security group chi can cho SSH tu IP nguoi van hanh, ngoai ra
# khong mo gi. Khong Elastic IP, khong load balancer, khong cong 80/443 vao.
echo "  cong dang lang nghe (mong doi: chi SSH):"
ss -tulnp 2>/dev/null | awk 'NR==1 || /0.0.0.0|\[::\]/' | head -8 || true

echo
echo "==================================================================="
echo "  BOOTSTRAP XONG — DICH VU CHUA DUOC BAT (co y)"
echo "==================================================================="
cat <<'CUOI'
Hai tep env DA duoc tao san (chi TEN bien, khong mot gia tri nao):

  /etc/fanfic-audio/worker.env
  /etc/fanfic-audio/translation-worker.env              (mode 0640 root:fanfic)

Con thieu DUNG BON gia tri, va chung la bi mat nen phai do nguoi van hanh nap:

  APPWRITE_ENDPOINT       endpoint Appwrite staging/dev
  APPWRITE_PROJECT_ID     *** DU AN STAGING — KHONG duoc la du an production
  APPWRITE_DATABASE_ID    database staging
  APPWRITE_API_KEY        khoa runtime, quyen toi thieu

Bon bien R2 KHONG can khi `STORAGE_BACKEND=local` (mac dinh trong mau) —
`server/config.py` chi kiem R2 khi `storage_backend == "r2"`.

Cach nap, KHONG in gia tri va KHONG sua gi neu nguon thieu:
  <nguon> | ssh ... "sudo bash /home/ubuntu/apply_staging_env.sh"

Dong co dau *** la rao chan quan trong nhat cua ca ke hoach: neu staging tro
vao du an PRODUCTION thi hai worker se tranh claim JOB THAT cua production.
`worker_staging_acceptance.py` kiem dung dieu do truoc moi thu khac va se TU
CHOI chay tiep neu trung.

Bat dich vu:
  systemctl enable --now fanfic-worker.service
  systemctl enable --now fanfic-translation-worker.service
  systemctl enable --now fanfic-worker-health.timer

Roi nghiem thu (chay TREN may staging):
  cd /opt/fanfic-audio && .venv/bin/python -m scripts.ops.worker_staging_acceptance
CUOI
