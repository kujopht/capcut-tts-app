#!/usr/bin/env bash
# Cong dieu hanh HEP cho worker PRODUCTION tren AWS — chay bang root,
# KHONG nhan shell tuy y.
#
#     fanfic-prod-admin drain     # xu ly hang doi yeu cau (systemd goi)
#     fanfic-prod-admin <verb>    # goi truc tiep khi da la root
#
# Anh em sinh doi cua `fanfic_staging_admin.sh`, va co y GIONG no ve hinh
# dang: ben khong-dac-quyen chi GHI duoc mot dong verb vao hang doi; root
# doi chieu ALLOWLIST roi chay dung ham da viet san. Verb khong bao gio di
# vao shell, khong co tham so duong dan, khong co `eval`.
#
# KHAC gi ban staging
#   - cham unit `-prod`, nen moi verb NGUY HIEM deu phai qua
#     `validate_prod_env.py` truoc (mot ban chinh sach duy nhat, viet bang
#     Python, co unit test — khong viet lai bang bash o day)
#   - TU CHOI khoi dong production khi unit STAGING tren cung may con song:
#     mot may chay ca hai la mot may claim job cua ca hai du an
#   - `rollback-note` chi ghi lai moc thoi gian; cong nay KHONG BAO GIO
#     cham GCE. Rollback that su la bat lai GCE, va viec do nam o may dieu
#     hanh chu khong o day.
#
# GIOI HAN CUNG
#   - chi ba unit production + ba unit staging cua CHINH may nay
#   - chi /etc/fanfic-audio va /opt/fanfic-audio
#   - khong cham GCE, khong cham DNS, khong deploy web, khong publish
#   - khong xoa du lieu nguoi dung, khong xoa object R2 nao ngoai object
#     thu nghiem co tien to `_cutover-probe/`
#   - fail closed: verb khong ro -> tu choi va ghi audit
set -uo pipefail

BASE=/var/lib/fanfic-prod-admin
REQ="$BASE/req"
RES="$BASE/res"
STAGE="$BASE/env.stage"
AUDIT=/var/log/fanfic-prod-admin.log
APP=/opt/fanfic-audio
ENVD=/etc/fanfic-audio
PY="$APP/.venv/bin/python"
MODELS=/opt/fanfic-models/nghitts/piper-tts
ENV_PROD="$ENVD/worker-prod.env"

#: DUY NHAT nhung verb nay. Bat ky thu khac -> tu choi.
ALLOW="status install-env preflight stop-staging start stop logs update canary rollback-note"

#: Unit DONG CUNG, khong bao gio nhan tu yeu cau.
UNITS_PROD=(fanfic-worker-prod.service fanfic-translation-worker-prod.service fanfic-worker-prod-health.timer)
UNITS_STAGING=(fanfic-worker.service fanfic-translation-worker.service fanfic-worker-health.timer)

ghi_audit() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$AUDIT" 2>/dev/null || true; }

# --- rao chan ---------------------------------------------------------------

kiem_env_production() {
  # Mot ban chinh sach DUY NHAT, bang Python, co unit test.
  [ -f "$ENV_PROD" ] || { echo "TU CHOI: thieu $ENV_PROD"; return 1; }
  "$PY" "$APP/scripts/ops/validate_prod_env.py" "$ENV_PROD"
}

kiem_staging_da_tat() {
  # Che do that bai nguy hiem nhat: AWS chay CA production LAN staging, hai
  # worker claim job cua hai du an tu cung mot may.
  local song=()
  for u in "${UNITS_STAGING[@]}"; do
    [ "$(systemctl is-active "$u" 2>/dev/null)" = "active" ] && song+=("$u")
  done
  if [ "${#song[@]}" -gt 0 ]; then
    ghi_audit "TU CHOI start: unit staging con song: ${song[*]}"
    echo "TU CHOI: unit staging con dang chay: ${song[*]}"
    echo "         chay \`stop-staging\` truoc."
    return 1
  fi
  return 0
}

# --- verb -------------------------------------------------------------------

vh_status() {
  echo "=== UNIT PRODUCTION ==="
  for u in "${UNITS_PROD[@]}"; do
    printf '  %-42s %-10s %s\n' "$u" \
      "$(systemctl is-active "$u" 2>/dev/null)" "$(systemctl is-enabled "$u" 2>/dev/null)"
  done
  echo "=== UNIT STAGING (phai tat khi production chay) ==="
  for u in "${UNITS_STAGING[@]}"; do
    printf '  %-42s %-10s %s\n' "$u" \
      "$(systemctl is-active "$u" 2>/dev/null)" "$(systemctl is-enabled "$u" 2>/dev/null)"
  done
  echo "=== ENV PRODUCTION (khong in bi mat) ==="
  if [ -f "$ENV_PROD" ]; then
    echo "  $ENV_PROD ($(stat -c '%a %U:%G' "$ENV_PROD"))"
    "$PY" "$APP/scripts/ops/validate_prod_env.py" "$ENV_PROD" 2>&1 | sed 's/^/  /'
  else
    echo "  <CHUA CAI>"
  fi
  echo "=== MODEL ==="
  echo "  .onnx        : $(find "$MODELS" -maxdepth 1 -name '*.onnx' 2>/dev/null | wc -l)"
  echo "  .onnx.json   : $(find "$MODELS" -maxdepth 1 -name '*.onnx.json' 2>/dev/null | wc -l)"
  echo "  symlink gay  : $(find "$MODELS" -maxdepth 1 -xtype l 2>/dev/null | wc -l)"
  echo "=== CHECKOUT ==="
  git config --global --add safe.directory "$APP" 2>/dev/null || true
  echo "  SHA: $(git -C "$APP" rev-parse HEAD 2>/dev/null || echo '?')"
  echo "=== MAY ==="
  echo "  vCPU: $(nproc)  load: $(cut -d' ' -f1-3 /proc/loadavg)"
  free -m | awk '/Mem:/{printf "  RAM : %d MB tong, %d MB con\n", $2, $7}'
  echo "  swap: $(swapon --show=SIZE --noheadings 2>/dev/null | tr -d ' ' | head -1)"
  df -BG / | awk 'NR==2{printf "  disk: %s tong, %s dung (%s)\n", $2, $3, $5}'
}

vh_install_env() {
  # Noi dung den tu `$STAGE` — mot tep DU LIEU o duong dan CO DINH ma
  # `ubuntu` ghi duoc. Khong co tham so duong dan nao di qua verb, nen ben
  # khong-dac-quyen khong the tro cong nay vao mot tep bat ky.
  [ -f "$STAGE" ] || { echo "TU CHOI: khong co $STAGE"; return 1; }

  # Kiem TRUOC khi dat vao cho. Mot tep env sai huong khong bao gio duoc
  # cham toi /etc/fanfic-audio.
  if ! "$PY" "$APP/scripts/ops/validate_prod_env.py" "$STAGE"; then
    ghi_audit "TU CHOI install-env: khang dinh production that bai"
    rm -f "$STAGE"
    return 1
  fi

  install -d -m 0755 -o root -g root "$ENVD"
  # 0640 root:fanfic — dung nhu GCE. `fanfic` doc duoc, ai khac thi khong.
  install -m 0640 -o root -g fanfic "$STAGE" "$ENV_PROD"
  rm -f "$STAGE"
  ghi_audit "install-env: da ghi $ENV_PROD"
  echo "  $ENV_PROD ($(stat -c '%a %U:%G' "$ENV_PROD"))"
  kiem_env_production
}

vh_preflight() {
  # Nghiem thu HINH DANG PRODUCTION ma KHONG tieu mot job that nao va
  # KHONG khoi dong worker.
  local loi=0
  echo "=== 1. ENV ==="
  kiem_env_production || loi=1
  echo "=== 2. STAGING DA TAT ==="
  kiem_staging_da_tat && echo "  khong co unit staging nao dang chay" || loi=1
  echo "=== 3. MODEL ==="
  local n; n="$(find "$MODELS" -maxdepth 1 -name '*.onnx' 2>/dev/null | wc -l)"
  echo "  .onnx: $n"
  [ "$n" -ge 25 ] || { echo "  THIEU model (mong doi >= 25)"; loi=1; }
  for g in ngochuyen ngochuyennew; do
    if [ -f "$MODELS/$g.onnx" ] && [ -e "$MODELS/$g.onnx.json" ]; then
      echo "  $g: CO"
    else
      echo "  $g: THIEU"; loi=1
    fi
  done
  echo "=== 4. PHU THUOC + R2 + APPWRITE (chi doc/ghi object thu nghiem) ==="
  ( set -a; . <(tr -d '\r' < "$ENV_PROD"); set +a
    export PYTHONPATH="$APP" FAS_PIPER_MODELS_DIR="$MODELS" PYTHONUTF8=1
    export FAS_VAR_DIR="$(systemctl show fanfic-worker-prod.service -p Environment 2>/dev/null \
        | tr ' ' '\n' | sed -n 's/^FAS_VAR_DIR=//p' | tail -1)"
    export FAS_VAR_DIR="${FAS_VAR_DIR:-/var/lib/fanfic-audio-prod}"
    cd "$APP" && "$PY" "$APP/scripts/ops/prod_preflight.py"
  ) 2>&1 | sed 's/^/  /'
  [ "${PIPESTATUS[0]}" -eq 0 ] || loi=1
  echo "=== KET LUAN PREFLIGHT ==="
  [ "$loi" -eq 0 ] && { echo "  PREFLIGHT_PASS"; return 0; }
  echo "  PREFLIGHT_FAIL"; return 1
}

vh_stop_staging() {
  for u in "${UNITS_STAGING[@]}"; do
    systemctl disable --now "$u" >/dev/null 2>&1 || true
    systemctl reset-failed "$u" >/dev/null 2>&1 || true
    printf '  %-42s %-10s %s\n' "$u" \
      "$(systemctl is-active "$u" 2>/dev/null)" "$(systemctl is-enabled "$u" 2>/dev/null)"
  done
  ghi_audit "stop-staging: da tat ${UNITS_STAGING[*]}"
}

vh_start() {
  kiem_env_production || { ghi_audit "TU CHOI start: env khong phai production"; return 1; }
  kiem_staging_da_tat || return 1
  for u in "${UNITS_PROD[@]}"; do
    systemctl reset-failed "$u" >/dev/null 2>&1 || true
    systemctl enable --now "$u" >/dev/null 2>&1 || true
  done
  sleep 8
  local loi=0
  for u in "${UNITS_PROD[@]}"; do
    local a; a="$(systemctl is-active "$u" 2>/dev/null)"
    printf '  %-42s %-10s %s\n' "$u" "$a" "$(systemctl is-enabled "$u" 2>/dev/null)"
    if [ "$a" != "active" ]; then
      loi=1
      echo "    --- 15 dong log cuoi ---"
      journalctl -u "$u" -n 15 --no-pager -o cat 2>/dev/null | sed 's/^/    /'
    fi
  done
  ghi_audit "start: exit=$loi"
  return "$loi"
}

vh_stop() {
  # `stop` KHONG giet job dang tong hop: unit co TimeoutStopSec va worker
  # tu cho toi `an_han_dung_giay`. Cong nay chi gui SIGTERM.
  for u in "${UNITS_PROD[@]}"; do
    systemctl disable --now "$u" >/dev/null 2>&1 || true
    printf '  %-42s %-10s %s\n' "$u" \
      "$(systemctl is-active "$u" 2>/dev/null)" "$(systemctl is-enabled "$u" 2>/dev/null)"
  done
  ghi_audit "stop: da dung ${UNITS_PROD[*]}"
}

vh_logs() {
  for u in fanfic-worker-prod.service fanfic-translation-worker-prod.service; do
    echo "=== $u (40 dong cuoi) ==="
    journalctl -u "$u" -n 40 --no-pager -o cat 2>/dev/null | grep -vE '^\s*$' | tail -30
  done
  echo "=== fanfic-worker-prod-health.service (8 dong cuoi) ==="
  journalctl -u fanfic-worker-prod-health.service -n 8 --no-pager -o cat 2>/dev/null | tail -8
}

vh_update() {
  git config --global --add safe.directory "$APP" 2>/dev/null || true
  git -C "$APP" fetch --quiet origin && git -C "$APP" reset --quiet --hard origin/main
  echo "  SHA: $(git -C "$APP" rev-parse HEAD 2>/dev/null)"
  # Dong bo ban root voi kho, y het ban staging.
  install -m 0755 "$APP/scripts/ops/fanfic_prod_admin.sh" \
    /usr/local/sbin/fanfic-prod-admin 2>/dev/null || true
}

vh_canary() {
  kiem_env_production || return 1
  ( set -a; . <(tr -d '\r' < "$ENV_PROD"); set +a
    export PYTHONPATH="$APP" FAS_PIPER_MODELS_DIR="$MODELS" PYTHONUTF8=1
    export FAS_VAR_DIR="$(systemctl show fanfic-worker-prod.service -p Environment 2>/dev/null \
        | tr ' ' '\n' | sed -n 's/^FAS_VAR_DIR=//p' | tail -1)"
    export FAS_VAR_DIR="${FAS_VAR_DIR:-/var/lib/fanfic-audio-prod}"
    cd "$APP" && "$PY" "$APP/scripts/ops/prod_canary.py"
  )
  local rc=$?
  ghi_audit "canary: exit=$rc"
  return "$rc"
}

vh_rollback_note() {
  # KHONG cham GCE. Chi ghi moc de hai ben doi chieu duoc.
  ghi_audit "rollback-note: production units dung tren may nay luc $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  vh_stop
  echo "  da ghi moc rollback vao $AUDIT"
  echo "  BAT LAI GCE la viec cua may dieu hanh — cong nay khong cham GCE."
}

# --- dieu phoi --------------------------------------------------------------

chay_verb() {
  local v="$1" ok=0
  for a in $ALLOW; do [ "$a" = "$v" ] && ok=1; done
  if [ "$ok" -ne 1 ]; then
    ghi_audit "TU CHOI verb: $v"
    echo "TU CHOI: verb '$v' khong nam trong allowlist ($ALLOW)"
    return 64
  fi
  ghi_audit "CHAY verb: $v"
  case "$v" in
    status)        vh_status ;;
    install-env)   vh_install_env ;;
    preflight)     vh_preflight ;;
    stop-staging)  vh_stop_staging ;;
    start)         vh_start ;;
    stop)          vh_stop ;;
    logs)          vh_logs ;;
    update)        vh_update ;;
    canary)        vh_canary ;;
    rollback-note) vh_rollback_note ;;
  esac
}

drain() {
  install -d -m 0755 "$RES"
  shopt -s nullglob
  for t in "$REQ"/*.req; do
    id="$(basename "$t" .req)"
    # CHI dong dau, CHI [a-z0-9-]: chan moi ky tu shell. Co so vi
    # `rollback-note` va cac verb tuong lai co the mang so.
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
  "")    echo "dung: fanfic-prod-admin <drain|$ALLOW>"; exit 64 ;;
  *)     chay_verb "$1"; exit $? ;;
esac
