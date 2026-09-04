#!/usr/bin/env bash
# Chay TOAN BO phan con lai cua nghiem thu AWS staging, bang root, tren chinh
# may staging:
#
#     sudo bash /home/ubuntu/staging_run_all.sh
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
set -a
# shellcheck disable=SC1090
. "$ENVD/worker.env"
set +a
export PYTHONPATH="$APP"
export FAS_PIPER_MODELS_DIR="$MODELS"
export PYTHONUTF8=1

hr "3. BO NGHIEM THU DAY DU"
"$PY" /home/ubuntu/worker_staging_acceptance.py \
  --baseline docs/reports/gce-worker-baseline.json 2>&1 | sed 's/^/  /'
ket_nt=${PIPESTATUS[0]}
echo "  -> exit=$ket_nt"

hr "4. MOT JOB DRAFT THAT — chung minh MAY NAY nhan"
cd "$APP" || exit 4
"$PY" /home/ubuntu/staging_draft_job_proof.py 2>&1 | sed 's/^/  /'
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
echo -n "  do tre Appwrite : "
curl -s -o /dev/null -w '%{time_total}s\n' "${APPWRITE_ENDPOINT%/}/health/version" 2>/dev/null || echo "khong do duoc"
echo "  cong lang nghe  :"
ss -tulnp 2>/dev/null | awk '/0.0.0.0|\[::\]/{print "    " $1, $5}' | head -5

hr "KET LUAN"
if [ "$ket_nt" -eq 0 ] && [ "$ket_job" -eq 0 ]; then
  echo "  AWS_STAGING_PASS"
  exit 0
fi
echo "  AWS_STAGING_FAIL  (nghiem thu=$ket_nt, job=$ket_job)"
exit 1
