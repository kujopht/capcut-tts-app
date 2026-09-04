#!/usr/bin/env bash
# Cong dieu hanh HEP cho AWS staging — chay bang root, KHONG nhan shell tuy y.
#
#     fanfic-staging-admin drain          # xu ly yeu cau dang cho (systemd goi)
#     fanfic-staging-admin <verb>         # goi truc tiep khi da la root
#
# VI SAO CO TEP NAY
# -----------------
# Vong lap go loi AWS staging can lap lai vai thao tac root: dong bo env,
# restart unit, doc log, chay lai ban chung minh. Truoc day moi lan nhu vay la
# mot luot nho nguoi van hanh chay `sudo ...` — khong the tu chu duoc.
#
# Cach giai KHONG dung: NOPASSWD sudo dai tra, hoac tat guard cua kho. Ca hai
# deu bien mot vong go loi thanh mot duong leo thang quyen tuy y.
#
# Cach giai o day: mot HANG DOI YEU CAU.
#   - `ubuntu` chi duoc GHI mot tep vao $REQ, noi dung la DUNG MOT dong verb
#   - root (qua systemd timer) doc verb, doi chieu ALLOWLIST, chay dung ham
#     tuong ung da viet san, roi ghi ket qua ra $RES
#   - verb KHONG BAO GIO duoc dua vao shell; khong co tham so duong dan;
#     khong co `eval`; khong doc gi khac tu tep yeu cau ngoai mot verb
#
# Nho vay ben khong-dac-quyen chi chon duoc MOT TRONG SAU hanh dong da duyet,
# chu khong dien duoc noi dung cua hanh dong nao.
#
# GIOI HAN CUNG
#   - chi ba unit staging cua may nay; TU CHOI bat ky ten unit chua "prod"
#   - chi /etc/fanfic-audio va /opt/fanfic-audio
#   - khong cham GCE, khong cham DNS, khong deploy, khong publish
#   - fail closed: verb khong ro -> tu choi va ghi audit
set -uo pipefail

BASE=/var/lib/fanfic-staging-admin
REQ="$BASE/req"
RES="$BASE/res"
AUDIT=/var/log/fanfic-staging-admin.log
APP=/opt/fanfic-audio
ENVD=/etc/fanfic-audio

#: DUY NHAT nhung verb nay duoc phep. Bat ky thu khac -> tu choi.
#:
#: `reconcile`    -> chinh sach luu tru LOCAL  (mac dinh)
#: `reconcile-r2` -> chinh sach luu tru R2     (chan R2 cua nghiem thu)
#:
#: HAI verb RIENG chu khong mot verb nhan tham so: bien "dung kho nao" thanh
#: mot lua chon TUONG MINH trong allowlist va trong audit log, thay vi mot
#: doi so ma ben goi dien tu do. `reconcile-r2` con TU CHOI neu bon bien R2
#: chua co hoac bucket khong nam trong danh sach staging — fail closed.
ALLOW="status reconcile reconcile-r2 restart logs run-proof update"

#: Bucket R2 duoc phep cho staging. Khop voi `apply_staging_r2.sh` va
#: `worker_staging_acceptance.py` — ba cho phai cung mot y.
BUCKET_STAGING="fanfic-staging fanfic-dev"

#: Unit duoc phep cham. Danh sach DONG CUNG, khong nhan tu yeu cau.
UNITS=(fanfic-worker.service fanfic-translation-worker.service fanfic-worker-health.timer)

ghi_audit() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$AUDIT" 2>/dev/null || true; }

# Chan tuyet doi moi thu mang mui production.
kiem_unit() {
  case "$1" in
    *prod*) ghi_audit "TU CHOI unit production: $1"; echo "TU CHOI: unit production"; return 1 ;;
  esac
  for u in "${UNITS[@]}"; do [ "$u" = "$1" ] && return 0; done
  ghi_audit "TU CHOI unit ngoai danh sach: $1"; echo "TU CHOI: unit ngoai danh sach"; return 1
}

vh_status() {
  echo "=== UNIT ==="
  for u in "${UNITS[@]}"; do
    kiem_unit "$u" || continue
    printf '  %-38s %-10s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null)" \
      "$(systemctl is-enabled "$u" 2>/dev/null)"
  done
  echo "=== CHINH SACH ENV (khong in bi mat) ==="
  for f in worker.env translation-worker.env; do
    p="$ENVD/$f"
    [ -f "$p" ] || { echo "  THIEU $p"; continue; }
    echo "  $f ($(stat -c '%a %U:%G' "$p"))"
    for k in FAS_ENV DATA_BACKEND STORAGE_BACKEND FAS_INLINE_WORKER FAS_LOCAL_VOICES; do
      echo "    $(grep -E "^${k}=" "$p" | tail -1)"
    done
    for k in APPWRITE_ENDPOINT APPWRITE_PROJECT_ID APPWRITE_DATABASE_ID APPWRITE_API_KEY; do
      if grep -qE "^${k}=..*" "$p"; then echo "    $k=<CO>"; else echo "    $k=<THIEU>"; fi
    done
    # R2: bao CO/THIEU cho ba khoa bi mat, nhung IN THANG `R2_BUCKET` —
    # ten bucket KHONG phai bi mat, va no la thu quan trong nhat can doc
    # duoc de biet staging co tro nham vao production hay khong.
    for k in R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
      if grep -qE "^${k}=..*" "$p"; then echo "    $k=<CO>"; else echo "    $k=<THIEU>"; fi
    done
    b="$(grep -E '^R2_BUCKET=' "$p" | tail -1 | cut -d= -f2-)"
    case "$b" in
      fanfic-prod) echo "    R2_BUCKET=$b   <-- PRODUCTION, TUYET DOI SAI" ;;
      "")          echo "    R2_BUCKET=<TRONG>" ;;
      *)           echo "    R2_BUCKET=$b" ;;
    esac
  done
  echo "=== MODEL ==="
  echo "  .onnx: $(find /opt/fanfic-models/nghitts/piper-tts -maxdepth 1 -name '*.onnx' 2>/dev/null | wc -l)"
  echo "  symlink gay: $(find /opt/fanfic-models/nghitts/piper-tts -maxdepth 1 -xtype l 2>/dev/null | wc -l)"
  echo "=== CHECKOUT ==="
  git config --global --add safe.directory "$APP" 2>/dev/null || true
  echo "  SHA: $(git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo '?')"
}

vh_reconcile() { bash "$APP/scripts/ops/staging_reconcile_env.sh"; }

vh_reconcile_r2() {
  # FAIL CLOSED: khong chuyen sang R2 khi chua du dieu kien.
  local p="$ENVD/worker.env"
  [ -f "$p" ] || { echo "TU CHOI: thieu $p"; return 1; }
  for k in R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET; do
    grep -qE "^${k}=..*" "$p" \
      || { echo "TU CHOI: thieu $k — chay apply_staging_r2.sh truoc"; return 1; }
  done
  local b
  b="$(grep -E '^R2_BUCKET=' "$p" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
  if [ "$b" = "fanfic-prod" ]; then
    ghi_audit "TU CHOI reconcile-r2: bucket PRODUCTION"
    echo "TU CHOI: R2_BUCKET la PRODUCTION (fanfic-prod)"; return 1
  fi
  local ok=0
  for x in $BUCKET_STAGING; do [ "$x" = "$b" ] && ok=1; done
  if [ "$ok" -ne 1 ]; then
    ghi_audit "TU CHOI reconcile-r2: bucket ngoai allowlist ($b)"
    echo "TU CHOI: bucket '$b' khong nam trong danh sach staging ($BUCKET_STAGING)"
    return 1
  fi
  echo "  bucket=$b (staging) — chuyen chinh sach sang R2"
  STORAGE_BACKEND_MONG_MUON=r2 bash "$APP/scripts/ops/staging_reconcile_env.sh"
}

vh_restart() {
  for u in "${UNITS[@]}"; do
    kiem_unit "$u" || continue
    systemctl stop "$u" >/dev/null 2>&1 || true
    systemctl reset-failed "$u" >/dev/null 2>&1 || true
  done
  for u in "${UNITS[@]}"; do
    kiem_unit "$u" || continue
    systemctl enable --now "$u" >/dev/null 2>&1 || true
  done
  sleep 6
  for u in "${UNITS[@]}"; do
    printf '  %-38s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null)"
  done
}

vh_logs() {
  for u in fanfic-worker.service fanfic-translation-worker.service; do
    kiem_unit "$u" || continue
    echo "=== $u (60 dong cuoi) ==="
    journalctl -u "$u" -n 60 --no-pager -o cat 2>/dev/null | grep -vE '^\s*$' | tail -40
  done
}

vh_update() {
  git config --global --add safe.directory "$APP" 2>/dev/null || true
  git -C "$APP" fetch --quiet origin && git -C "$APP" reset --quiet --hard origin/main
  echo "  SHA: $(git -C "$APP" rev-parse --short HEAD 2>/dev/null)"
  # Dong bo lai script dieu hanh tu chinh checkout — de ban root luon khop kho.
  install -m 0755 "$APP/scripts/ops/fanfic_staging_admin.sh" \
    /usr/local/sbin/fanfic-staging-admin 2>/dev/null || true
}

vh_run_proof() { bash "$APP/scripts/ops/staging_run_all.sh"; }

chay_verb() {
  local v="$1"
  # Doi chieu ALLOWLIST truoc tien. Fail closed.
  local ok=0
  for a in $ALLOW; do [ "$a" = "$v" ] && ok=1; done
  if [ "$ok" -ne 1 ]; then
    ghi_audit "TU CHOI verb: $v"
    echo "TU CHOI: verb '$v' khong nam trong allowlist ($ALLOW)"
    return 64
  fi
  ghi_audit "CHAY verb: $v"
  case "$v" in
    status)    vh_status ;;
    reconcile) vh_reconcile ;;
    reconcile-r2) vh_reconcile_r2 ;;
    restart)   vh_restart ;;
    logs)      vh_logs ;;
    update)    vh_update ;;
    run-proof) vh_run_proof ;;
  esac
}

# --- che do drain: doc hang doi yeu cau -------------------------------------
drain() {
  install -d -m 0755 "$RES"
  shopt -s nullglob
  for t in "$REQ"/*.req; do
    id="$(basename "$t" .req)"
    # CHI doc dong dau, CHI lay ky tu chu-so-gach — khong bao gio dua vao shell.
    # Loc con [a-z0-9-]: chan moi ky tu shell. Chu SO can co vi mot verb hop
    # le la `reconcile-r2` — loc cu (`a-z-`) cat mat so 2 va bien no thanh
    # `reconcile-r`, roi bi allowlist tu choi mot cach kho hieu.
    verb="$(head -c 64 "$t" 2>/dev/null | head -1 | tr -cd 'a-z0-9-')"
    rm -f "$t"
    out="$RES/$id.out"
    {
      echo "# verb=$verb luc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
      chay_verb "$verb"
      echo "# exit=$?"
    } > "$out" 2>&1
    chmod 0644 "$out"
  done
}

case "${1:-}" in
  drain) drain ;;
  "")    echo "dung: fanfic-staging-admin <drain|$ALLOW>"; exit 64 ;;
  *)     chay_verb "$1"; exit $? ;;
esac
