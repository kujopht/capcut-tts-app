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
STAGE_TR="$BASE/env-translation.stage"
AUDIT=/var/log/fanfic-prod-admin.log
APP=/opt/fanfic-audio
ENVD=/etc/fanfic-audio
PY="$APP/.venv/bin/python"
MODELS=/opt/fanfic-models/nghitts/piper-tts
ENV_PROD="$ENVD/worker-prod.env"
ENV_TR="$ENVD/translation-worker-prod.env"

#: DUY NHAT nhung verb nay. Bat ky thu khac -> tu choi.
ALLOW="status install-env install-translation-env preflight stop-staging start stop logs update canary rollback-note"

#: Unit DONG CUNG, khong bao gio nhan tu yeu cau.
UNITS_PROD=(fanfic-worker-prod.service fanfic-translation-worker-prod.service fanfic-worker-prod-health.timer)
UNITS_STAGING=(fanfic-worker.service fanfic-translation-worker.service fanfic-worker-health.timer)

ghi_audit() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$AUDIT" 2>/dev/null || true; }

# --- chay mot cong cu Python voi env production ------------------------------

chay_python() {
  # Truyen DUONG DAN tep env cho Python thay vi `source` no.
  #
  # Day la ranh gioi an toan chinh cua tep nay. `. <(...)` THUC THI noi
  # dung tep; tep do lai den tu `env.stage`, ma ben khong-dac-quyen ghi
  # duoc. Nen mot dong khong co `=` — hoac mot gia tri `$(...)` — se chay
  # bang ROOT. Python chi PHAN TICH tep (`doc_env_text`), khong bao gio
  # chay no.
  #
  # Chi cac bien KHONG bi mat duoc dat o day; bi mat khong bao gio di qua
  # moi truong cua shell nay.
  local vd
  vd="$(systemctl show fanfic-worker-prod.service -p Environment 2>/dev/null \
        | tr ' ' '\n' | sed -n 's/^FAS_VAR_DIR=//p' | tail -1)"
  cd "$APP" || return 1
  PYTHONPATH="$APP" \
  PYTHONUTF8=1 \
  FAS_PIPER_MODELS_DIR="$MODELS" \
  FAS_VAR_DIR="${vd:-/var/lib/fanfic-audio-prod}" \
    "$PY" "$@" --env-file "$ENV_PROD"
}

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

  # KHONG BAO GIO cai tep tho. `--emit` phan tich tep stage roi SINH LAI
  # noi dung tu allowlist, nen chi dung `REQUIRED_ENV_NAMES` song sot.
  #
  # Vi sao khong chi "kiem roi copy": ban dau chinh la nhu vay, va no la
  # mot lo hong LEO THANG QUYEN that. Bo phan tich Python bo qua moi dong
  # khong co `=`, con tep tho thi truoc day duoc `bash` doc bang
  # `. <(...)` — nen mot dong `curl ke-tan-cong/x | sh` di lot qua kiem
  # duyet roi CHAY BANG ROOT. Nguoi khong-dac-quyen chi can ghi duoc
  # `env.stage`, va ho ghi duoc that (0620).
  #
  # Hai thay doi cung luc dong lo hong do: (1) sinh lai thay vi copy, o
  # day; (2) khong con duong `bash source` nao — Python doc thang tep.
  local moi; moi="$(mktemp)"
  chmod 0600 "$moi"
  if ! "$PY" "$APP/scripts/ops/validate_prod_env.py" --emit "$STAGE" > "$moi"; then
    ghi_audit "TU CHOI install-env: khang dinh production that bai"
    rm -f "$moi" "$STAGE"
    return 1
  fi
  # Doc lai ban DA SINH va kiem lan nua — thu ta sap cai phai la thu ta da
  # kiem, khong phai thu ta da doc.
  if ! "$PY" "$APP/scripts/ops/validate_prod_env.py" "$moi"; then
    ghi_audit "TU CHOI install-env: ban sinh lai khong qua khang dinh"
    rm -f "$moi" "$STAGE"
    return 1
  fi

  install -d -m 0755 -o root -g root "$ENVD"
  # 0640 root:fanfic — dung nhu GCE. `fanfic` doc duoc, ai khac thi khong.
  install -m 0640 -o root -g fanfic "$moi" "$ENV_PROD"
  rm -f "$moi"
  : > "$STAGE"   # rong lai, giu nguyen chu so huu/quyen cho lan sau
  ghi_audit "install-env: da ghi $ENV_PROD"
  echo "  $ENV_PROD ($(stat -c '%a %U:%G' "$ENV_PROD"))"
  kiem_env_production
}

vh_install_translation_env() {
  # Tep env RIENG cho worker dich. Hinh dang KHAC worker TTS — khong R2,
  # `STORAGE_BACKEND=local` — khop dung ban tren GCE.
  #
  # Thieu tep nay, `fanfic-translation-worker-prod.service` chet voi
  # "Failed to load environment files: No such file or directory" roi
  # restart vo han. Da xay ra that trong lan canary dau tien.
  [ -f "$STAGE_TR" ] || { echo "TU CHOI: khong co $STAGE_TR"; return 1; }
  local moi; moi="$(mktemp)"
  chmod 0600 "$moi"
  if ! "$PY" "$APP/scripts/ops/validate_prod_env.py" --translation --emit "$STAGE_TR" > "$moi"; then
    ghi_audit "TU CHOI install-translation-env: khang dinh that bai"
    rm -f "$moi" "$STAGE_TR"
    return 1
  fi
  if ! "$PY" "$APP/scripts/ops/validate_prod_env.py" --translation "$moi"; then
    ghi_audit "TU CHOI install-translation-env: ban sinh lai khong qua khang dinh"
    rm -f "$moi" "$STAGE_TR"
    return 1
  fi
  install -d -m 0755 -o root -g root "$ENVD"
  install -m 0640 -o root -g fanfic "$moi" "$ENV_TR"
  rm -f "$moi"
  : > "$STAGE_TR"
  ghi_audit "install-translation-env: da ghi $ENV_TR"
  echo "  $ENV_TR ($(stat -c '%a %U:%G' "$ENV_TR"))"
  "$PY" "$APP/scripts/ops/validate_prod_env.py" --translation "$ENV_TR"
}

vh_preflight() {
  # Nghiem thu HINH DANG PRODUCTION ma KHONG tieu mot job that nao va
  # KHONG khoi dong worker.
  local loi=0
  echo "=== 1. ENV ==="
  kiem_env_production || loi=1
  echo "=== 1b. ENV WORKER DICH ==="
  if [ -f "$ENV_TR" ]; then
    "$PY" "$APP/scripts/ops/validate_prod_env.py" --translation "$ENV_TR" || loi=1
  else
    echo "  THIEU $ENV_TR — worker dich se chet khi khoi dong"; loi=1
  fi
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
  # KHONG `source` tep env. Xem ghi chu o `vh_install_env`: `bash source`
  # THUC THI tep, va tep do den tu mot cho ma ben khong-dac-quyen ghi
  # duoc. Python nhan duong dan va tu PHAN TICH.
  chay_python "$APP/scripts/ops/prod_preflight.py" 2>&1 | sed 's/^/  /'
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
  # RAO CHAN THU BA — worker NGOAI may nay (vi du GCE) co dang phuc vu
  # hang doi production khong.
  #
  # Rao chan "GCE phai da dung" cua bo dieu phoi song tren may DIEU HANH,
  # ma verb `start` thi den tu mot hang doi ben khong-dac-quyen ghi duoc —
  # nen no co the toi ma khong he di qua bo dieu phoi. Rao chan nay song
  # tren chinh may nay, khong bo qua duoc. Fail closed.
  echo "  kiem worker ngoai dang giu lease:"
  if ! chay_python "$APP/scripts/ops/prod_start_guard.py"; then
    ghi_audit "TU CHOI start: worker ngoai dang phuc vu hang doi production"
    return 1
  fi
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
  # Dong bo ban root cua chinh cong nay voi kho.
  #
  # KHONG nuot loi o day. Ban truoc viet `2>/dev/null || true`, va hau qua
  # that la: `ProtectSystem=full` lam /usr CHI DOC, `install` that bai im
  # lang, cong tren may van chay ban CU trong khi kho da co verb moi — va
  # `update` van bao thanh cong. Mot buoc dong bo that bai am tham con toi
  # hon khong co buoc dong bo nao.
  if install -m 0755 "$APP/scripts/ops/fanfic_prod_admin.sh" \
       /usr/local/sbin/fanfic-prod-admin 2>&1; then
    echo "  da dong bo /usr/local/sbin/fanfic-prod-admin"
  else
    echo "  CANH BAO: KHONG ghi duoc /usr/local/sbin/fanfic-prod-admin"
    echo "            (thieu /usr/local/sbin trong ReadWritePaths cua unit?)"
    echo "            Cong dang chay ban CU — chay lai trinh cai bang root."
    ghi_audit "update: KHONG dong bo duoc ban root cua cong"
    return 1
  fi
  # Bao dam moi tep stage ton tai voi dung quyen.
  #
  # `/var/lib/fanfic-prod-admin` la 0755 root:root, nen ben khong-dac-quyen
  # KHONG tao duoc tep moi trong do — no chi ghi duoc vao tep da co san voi
  # mode 0620 root:ubuntu. Khi mot tep stage MOI duoc them vao kho (vi du
  # `env-translation.stage`), no phai duoc tao o day; neu khong buoc duy
  # nhat con lai la nho nguoi van hanh chay lai trinh cai bang root.
  local nguoi="${NGUOI_KHONG_DAC_QUYEN:-ubuntu}"
  for t in env.stage env-translation.stage; do
    if [ ! -f "$BASE/$t" ]; then
      install -m 0620 -o root -g "$nguoi" /dev/null "$BASE/$t"
      echo "  da tao $BASE/$t ($(stat -c '%a %U:%G' "$BASE/$t"))"
    fi
  done
}

vh_canary() {
  kiem_env_production || return 1
  chay_python "$APP/scripts/ops/prod_canary.py"
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
    install-translation-env) vh_install_translation_env ;;
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
    # Ghi vao tep TAM roi `mv` vao cho — `mv` trong cung mot he tep la
    # NGUYEN TU, nen ben goi khong bao gio nhin thay mot ket qua dang viet
    # do dang.
    #
    # Ban truoc ghi thang vao "$out", va bo dieu phoi thi doc ngay khi tep
    # khac rong. Hau qua that: no doc duoc phan dau cua mot ban preflight
    # CHUA xong, khong thay dong `# exit=`, roi mac dinh coi la thanh cong
    # — bao PREPARE_PASS cho mot preflight that ra da FAIL.
    tam="$RES/.$id.partial"
    {
      echo "# verb=$verb luc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
      chay_verb "$verb"
      echo "# exit=$?"
    } > "$tam" 2>&1
    chmod 0644 "$tam"
    mv -f "$tam" "$out"
  done
}

case "${1:-}" in
  drain) drain ;;
  "")    echo "dung: fanfic-prod-admin <drain|$ALLOW>"; exit 64 ;;
  *)     chay_verb "$1"; exit $? ;;
esac
