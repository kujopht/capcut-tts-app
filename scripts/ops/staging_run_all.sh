#!/usr/bin/env bash
# Chay TOAN BO phan con lai cua nghiem thu AWS staging, bang root, tren chinh
# may staging:
#
#     fanfic-staging-admin run-proof     (cong dieu hanh HEP, khong can sudo
#                                         tu ben khong-dac-quyen)
#
# 1. kiem TEN bien trong hai tep env (khong bao gio in gia tri)
# 2. bat va khoi dong cac unit staging
# 3. bo nghiem thu day du
# 4. mot job DRAFT that, chung minh CHINH MAY NAY nhan
# 5. so lieu de doi chieu AWS vs GCE
#
# KHONG cham production, khong doi DNS, khong publish, khong dung
# fanfic-worker-prod tren GCE, khong dung fanfic-staging-worker tren GCE.
set -uo pipefail

APP=/opt/fanfic-audio
PY="$APP/.venv/bin/python"
ENVD=/etc/fanfic-audio
MODELS=/opt/fanfic-models/nghitts/piper-tts
BIEN=(APPWRITE_ENDPOINT APPWRITE_PROJECT_ID APPWRITE_DATABASE_ID APPWRITE_API_KEY)
loi=0

hr() { printf '\n%s\n  %s\n%s\n' "======================================================================" "$1" "======================================================================"; }

hr "0. DUNG TAM CAC UNIT STAGING CUA MAY NAY (chi may nay)"
# Chi ba unit staging TREN CHINH MAY NAY. KHONG cham GCE: khong
# fanfic-worker-prod, khong fanfic-staging-worker.
for u in fanfic-worker.service fanfic-translation-worker.service fanfic-worker-health.timer; do
  systemctl stop "$u" >/dev/null 2>&1 || true
  # `Restart=always` + `StartLimitBurst` co the da day unit vao
  # `start-limit-hit`; khong reset thi `start` sau nay bi tu choi ngay.
  systemctl reset-failed "$u" >/dev/null 2>&1 || true
  printf '  %-38s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null)"
done

hr "0a. DUA BAN CHECKOUT VE origin/main"
# Phep chung minh phai chay tren dung ma nguon da merge, khong phai tren ban
# bootstrap luc 00:13. `server/` cua tien trinh worker den tu day.
if [ -d "$APP/.git" ]; then
  git config --global --add safe.directory "$APP" 2>/dev/null || true
  git -C "$APP" fetch --quiet origin 2>&1 | sed 's/^/  /' || true
  git -C "$APP" reset --quiet --hard origin/main 2>&1 | sed 's/^/  /' || true
  echo "  SHA: $(git -C "$APP" rev-parse --short HEAD 2>/dev/null)"
else
  echo "  CANH BAO: $APP khong phai git checkout — bo qua"
fi

hr "0b. DONG BO CHINH SACH ENV (khong cham bi mat, khong them R2)"
# CHI dung ban trong CHECKOUT. Truoc day uu tien ban stage o /home/ubuntu,
# nhung `fanfic-staging-admin.service` co `ProtectHome=true` (co y, de lam
# hep quyen) nen /home KHONG NHIN THAY duoc tu dich vu — moi lenh tro vao do
# bao "No such file or directory". Da do that: nghiem thu=2, job=2.
#
# Dung checkout con DUNG HON ve ban chat: ban chung minh phai chay tren ma
# nguon DA MERGE, khong phai mot ban chep tay. Verb `update` lo viec dua
# checkout ve origin/main.
REC="$APP/scripts/ops/staging_reconcile_env.sh"
[ -f "$REC" ] || REC=""
if [ -n "$REC" ]; then
  echo "  dung: $REC"
  # GIU NGUYEN kho luu tru dang duoc cau hinh — KHONG ep ve `local`.
  #
  # Ban truoc goi reconcile khong kem tham so, nen no ap chinh sach mac dinh
  # `STORAGE_BACKEND=local`. Hau qua: sau khi `reconcile-r2` da dat r2, mot
  # lan `run-proof` LAT NGUOC no ve local roi chay nghiem thu + job DRAFT o
  # che do local — va bao PASS. Da xay ra that:
  #     STORAGE_BACKEND r2
  #     SAI CHINH SACH STORAGE_BACKEND: mong muon='local'
  #     STORAGE_BACKEND local
  # Do la mot PASS GIA cho chan R2: no chung minh dung cai da chung minh roi.
  #
  # Viec cua reconcile la lam HAI TEP DONG NHAT, khong phai quyet dinh dung
  # kho nao. Lua chon kho thuoc ve `reconcile` / `reconcile-r2`.
  _sb="$(grep -E '^STORAGE_BACKEND=' "$ENVD/worker.env" 2>/dev/null \
          | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
  case "$_sb" in
    local|r2) : ;;
    *) echo "  STORAGE_BACKEND hien tai la '$_sb' — khong hop le, dung 'local'"
       _sb=local ;;
  esac
  echo "  giu nguyen STORAGE_BACKEND=$_sb"
  STORAGE_BACKEND_MONG_MUON="$_sb" bash "$REC" 2>&1 | sed 's/^/  /'
  rc=${PIPESTATUS[0]}
  echo "  -> exit=$rc"
  [ "$rc" -eq 0 ] || { echo; echo "FAIL: dong bo chinh sach that bai."; exit 2; }
else
  echo "  THIEU staging_reconcile_env.sh o ca hai duong"
  exit 2
fi

hr "1. KIEM TEN BIEN (khong in gia tri)"
for f in worker.env translation-worker.env; do
  p="$ENVD/$f"
  if [ ! -f "$p" ]; then echo "  THIEU $p"; loi=1; continue; fi
  echo "  $f  ($(stat -c '%a %U:%G' "$p"))"
  for v in "${BIEN[@]}"; do
    if grep -qE "^${v}=..*" "$p"; then echo "    CO    $v"; else echo "    THIEU $v"; loi=1; fi
  done
  for v in FAS_ENV FAS_INLINE_WORKER DATA_BACKEND STORAGE_BACKEND; do
    # Cac bien nay KHONG bi mat -> in duoc ca gia tri, va can in de doi chieu.
    echo "    $(grep -E "^${v}=" "$p" | head -1)"
  done
done
[ "$loi" -eq 0 ] || { echo; echo "FAIL: thieu bien — dung lai truoc khi bat dich vu."; exit 2; }

hr "2. BAT VA KHOI DONG UNIT STAGING"
systemctl enable --now fanfic-worker.service        >/dev/null 2>&1 || true
systemctl enable --now fanfic-translation-worker.service >/dev/null 2>&1 || true
systemctl enable --now fanfic-worker-health.timer   >/dev/null 2>&1 || true
sleep 6
for u in fanfic-worker.service fanfic-translation-worker.service fanfic-worker-health.timer; do
  a="$(systemctl is-active "$u" 2>/dev/null)"; e="$(systemctl is-enabled "$u" 2>/dev/null)"
  printf '  %-38s %-10s %s\n' "$u" "$a" "$e"
  [ "$a" = "active" ] || { loi=1; echo "    --- 12 dong log cuoi ---"
    journalctl -u "$u" -n 12 --no-pager -o cat 2>/dev/null | sed 's/^/    /'; }
done
[ "$loi" -eq 0 ] || { echo; echo "FAIL: dich vu khong len duoc."; exit 3; }

# Nap env cho cac lenh chay TAY ben duoi (unit tu nap qua EnvironmentFile).
#
# Nap qua mot ban SACH: `systemd` cat bo \r khi doc EnvironmentFile nhung `.`
# cua bash thi KHONG. Tep env tung mang CRLF (script duoc scp tu Windows,
# heredoc sinh ra tep CRLF) va hau qua la `APPWRITE_ENDPOINT` co \r o cuoi ->
# "InvalidURL: ... '\r' at position 36". `staging_reconcile_env.sh` da chuan
# hoa tep, day la lop phong ve thu hai ngay tai cho nap.
_env_sach="$(mktemp)"
tr -d '\r' < "$ENVD/worker.env" > "$_env_sach"
set -a
# shellcheck disable=SC1090
. "$_env_sach"
set +a
rm -f "$_env_sach"

export PYTHONPATH="$APP"
export FAS_PIPER_MODELS_DIR="$MODELS"
export PYTHONUTF8=1

# FAS_VAR_DIR phai KHOP unit cua worker TTS, khong duoc de mac dinh.
#
# `FAS_VAR_DIR` khong nam trong tep env — no la `Environment=` trong unit. Bo
# qua no thi `settings.var_dir` lui ve `server/var` TUONG DOI voi kho, nen ban
# chung minh di tim hien vat o /opt/fanfic-audio/server/var/storage trong khi
# worker da ghi vao /var/lib/fanfic-audio/storage. Da do that: job COMPLETED
# nhung "ton tai=False" -> exit 7.
#
# Lay THANG tu unit de hai ben khong bao gio lech nhau.
_vd="$(systemctl show fanfic-worker.service -p Environment 2>/dev/null \
        | tr ' ' '\n' | sed -n 's/^FAS_VAR_DIR=//p' | tail -1)"
export FAS_VAR_DIR="${_vd:-/var/lib/fanfic-audio}"
echo "  FAS_VAR_DIR (tu unit) = $FAS_VAR_DIR"

hr "3. BO NGHIEM THU DAY DU"
"$PY" "$APP/scripts/ops/worker_staging_acceptance.py" \
  --baseline docs/reports/gce-worker-baseline.json 2>&1 | sed 's/^/  /'
ket_nt=${PIPESTATUS[0]}
echo "  -> exit=$ket_nt"

hr "4. MOT JOB DRAFT THAT — chung minh MAY NAY nhan"
cd "$APP" || exit 4
"$PY" "$APP/scripts/ops/staging_draft_job_proof.py" 2>&1 | sed 's/^/  /'
ket_job=${PIPESTATUS[0]}
echo "  -> exit=$ket_job"

hr "5. SO LIEU MAY (doi chieu AWS vs GCE)"
echo "  vCPU            : $(nproc)"
free -m | awk '/Mem:/{printf "  RAM             : %d MB tong, %d MB dung, %d MB con\n", $2, $2-$7, $7}'
echo "  swap            : $(swapon --show=SIZE --noheadings | tr -d ' ' | head -1)"
df -BG / | awk 'NR==2{printf "  disk            : %s tong, %s dung\n", $2, $3}'
echo "  load 1p         : $(cut -d' ' -f1 /proc/loadavg)"
echo "  kernel          : $(uname -r)"
echo "  python          : $("$PY" --version 2>&1 | cut -d' ' -f2)"
echo "  ffmpeg          : $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
echo "  goi python      : $("$PY" -m pip list --format=freeze 2>/dev/null | wc -l)"
echo "  model .onnx     : $(find "$MODELS" -maxdepth 1 -name '*.onnx' 2>/dev/null | wc -l)"
# Do tre Appwrite: chi la SO LIEU de so voi GCE, khong phai cong. In mot
# dong duy nhat trong moi truong hop — ban truoc in ca "0.000000s" LAN
# "khong do duoc" vi `curl` that bai van in `%{time_total}` roi `||` moi chay.
printf '  do tre Appwrite : '
if [ -n "${APPWRITE_ENDPOINT:-}" ] \
   && t=$(curl -sS -o /dev/null -m 20 -w '%{time_total}' \
          "${APPWRITE_ENDPOINT%/}/health/version" 2>/dev/null); then
  echo "${t}s"
else
  echo "khong do duoc"
fi
echo "  cong lang nghe  :"
ss -tulnp 2>/dev/null | awk '/0.0.0.0|\[::\]/{print "    " $1, $5}' | head -5

hr "KET LUAN"
if [ "$ket_nt" -eq 0 ] && [ "$ket_job" -eq 0 ]; then
  echo "  AWS_STAGING_PASS"
  exit 0
fi
echo "  AWS_STAGING_FAIL  (nghiem thu=$ket_nt, job=$ket_job)"
exit 1
