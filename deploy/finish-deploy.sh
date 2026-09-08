#!/usr/bin/env bash
# Hoan tat trien khai farmer: nhan token dich vu, cai, roi XAC MINH.
#
# Chay bang root tren may AWS, SAU khi kho da duoc fast-forward len `main`.
#
# ## Bi mat khong bao gio roi khoi may nay
#
# Token duoc go o mot dau nhac AN ngay tren TTY cua phien SSH. No khong bao
# gio:
#   - nam trong dong lenh (nen khong o `ps`, khong o lich su shell CUA MAY NAO)
#   - di qua argv cua mot tien trinh con (nen khong o `/proc/*/environ`)
#   - ra stdout, journal, hay bat ky artifact nao
#   - duoc commit vao git
#
# Ghi bang `printf` (builtin cua bash) vao mot tep tam CUNG THU MUC, dat
# quyen dung roi `mv` de nguyen — nen khong co khoanh khac nao tep that ton
# tai voi quyen sai.
#
# ## Khong dung toi bi mat nao khac
#
# Chi dong `FAS_HARVESTER_SERVICE_TOKEN` trong `farmer.env` bi thay. Moi dong
# khac trong tep do duoc giu nguyen tung byte, va `worker-prod.env` khong bao
# gio duoc mo.

set -euo pipefail
umask 077
set +x                     # tuyet doi khong trace: se in ca bien chua token

ETC=/etc/fanfic-audio
ENV_FILE="$ETC/farmer.env"
REPO=/opt/fanfic-audio
SVC_USER=fanfic
KEY=FAS_HARVESTER_SERVICE_TOKEN

die() { printf '\n[LOI] %s\n' "$1" >&2; exit 1; }
ok()  { printf '  [OK]   %s\n' "$1"; }
info(){ printf '  [ .. ] %s\n' "$1"; }

[ "$(id -u)" -eq 0 ] || die "phai chay bang root"
[ -f "$ENV_FILE" ] || die "khong thay $ENV_FILE — chay bootstrap-farmer.sh truoc"

# Ghi lai quyen cua bi mat production khac de CHUNG MINH khong dung toi.
WPE="$ETC/worker-prod.env"
WPE_BEFORE=""
[ -f "$WPE" ] && WPE_BEFORE="$(stat -c '%U:%G %a' "$WPE")"

printf '\n=== Hoan tat trien khai farmer ===\n\n'

# --------------------------------------------------------------- 1. token --
# `--skip-token`: token DA duoc ghi boi mot buoc truoc (vd
# `scripts/push_harvester_token.py` day thang tu Windows Credential Manager
# qua stdin). Chi KIEM no co mat, khong hoi lai va khong bao gio in ra.
if [ "${1:-}" = "--skip-token" ]; then
  info "bo qua buoc nhap token (da duoc ghi truoc do) — chi kiem co mat"
  if grep -q "^${KEY}=." "$ENV_FILE"; then
    ok "$KEY co mat trong $ENV_FILE (gia tri khong duoc in)"
  else
    die "$KEY khong co (hoac rong) trong $ENV_FILE — dung lai"
  fi
else
  printf 'Dan %s (khong hien khi go, Enter de xac nhan):\n> ' "$KEY"
  read -rs TOKEN
  printf '\n\n'
  [ -n "${TOKEN:-}" ] || die "token rong — dung lai, khong sua gi"
fi

if [ "${1:-}" != "--skip-token" ]; then

info "ghi $KEY vao $ENV_FILE (chi dong nay bi thay)"
TMP="$ENV_FILE.new.$$"
# Tao tep tam voi quyen DUNG NGAY TU DAU — khong co khoanh khac nao no rong
# quyen roi moi duoc siet lai.
install -o "$SVC_USER" -g "$SVC_USER" -m 600 /dev/null "$TMP"
# Giu nguyen moi dong khac; chi bo dong token cu (neu co).
grep -v "^${KEY}=" "$ENV_FILE" > "$TMP" || true
printf '%s=%s\n' "$KEY" "$TOKEN" >> "$TMP"
unset TOKEN                # khong giu trong bo nho script lau hon can thiet
mv -f "$TMP" "$ENV_FILE"
chown "$SVC_USER:$SVC_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"
ok "da ghi ($(stat -c '%U:%G %a' "$ENV_FILE")) — gia tri khong bao gio duoc in"
fi

# ------------------------------------------------------------ 2. bootstrap --
info "chay bootstrap-farmer.sh"
bash "$REPO/deploy/bootstrap-farmer.sh"

# ------------------------------------------------------------ 3. XAC MINH --
printf '\n=== Xac minh (khong co bi mat nao trong phan nay) ===\n'
FAIL=0

info "cho dich vu on dinh (20 giay)"
sleep 20

SHA="$(cat "$REPO/.git/refs/heads/main" 2>/dev/null | cut -c1-7)"
ok "SHA da trien khai: $SHA"

STATE="$(systemctl is-active fanfic-farmer 2>&1 || true)"
MAINPID="$(systemctl show fanfic-farmer -p MainPID --value 2>/dev/null || echo 0)"
RESTARTS="$(systemctl show fanfic-farmer -p NRestarts --value 2>/dev/null || echo 0)"

# `is-active` mot minh KHONG du: mot dich vu dang sap lien tuc van bao
# "active" trong khoang `activating (auto-restart)`. Dau hieu that la
# MainPID > 0.
if [ "$STATE" = "active" ] && [ "${MAINPID:-0}" -gt 0 ]; then
  ok "dich vu chay that: active, MainPID=$MAINPID"
else
  printf '  [FAIL] dich vu KHONG chay that: state=%s MainPID=%s\n' \
    "$STATE" "$MAINPID"; FAIL=1
fi

# Dem lai sau 20 giay nua: neu MainPID doi, no dang sap lien tuc.
sleep 20
MAINPID2="$(systemctl show fanfic-farmer -p MainPID --value 2>/dev/null || echo 0)"
RESTARTS2="$(systemctl show fanfic-farmer -p NRestarts --value 2>/dev/null || echo 0)"
if [ "$MAINPID" = "$MAINPID2" ] && [ "$RESTARTS" = "$RESTARTS2" ]; then
  ok "khong con sap lien tuc (MainPID on dinh, NRestarts=$RESTARTS2)"
else
  printf '  [FAIL] van dang sap lien tuc: PID %s -> %s, NRestarts %s -> %s\n' \
    "$MAINPID" "$MAINPID2" "$RESTARTS" "$RESTARTS2"; FAIL=1
fi

COUNT="$(pgrep -c -f '[s]erver.farmer' 2>/dev/null || echo 0)"
if [ "$COUNT" = "1" ]; then
  ok "DUNG MOT ban farmer dang chay"
else
  printf '  [FAIL] so ban farmer = %s (mong doi 1)\n' "$COUNT"; FAIL=1
fi

for svc in fanfic-worker-prod fanfic-translation-worker-prod; do
  if [ "$(systemctl is-active "$svc" 2>/dev/null)" = "active" ]; then
    ok "worker production con nguyen: $svc"
  else
    printf '  [FAIL] %s khong con active\n' "$svc"; FAIL=1
  fi
done

if [ -n "$WPE_BEFORE" ]; then
  if [ "$WPE_BEFORE" = "$(stat -c '%U:%G %a' "$WPE")" ]; then
    ok "worker-prod.env khong bi dung toi"
  else
    printf '  [FAIL] worker-prod.env bi doi quyen\n'; FAIL=1
  fi
fi

if [ "$FAIL" -ne 0 ]; then
  printf '\n=== CO PHEP KIEM HONG ===\n'
  printf 'Xem: journalctl -u fanfic-farmer -n 40 --no-pager\n\n'
  exit 1
fi

printf '\n=== TAT CA DAT — farmer dang chay ===\n'
printf 'Theo doi:\n'
printf '  journalctl -u fanfic-farmer -f\n'
printf '  cat /var/lib/fanfic-farmer/status.json\n\n'
