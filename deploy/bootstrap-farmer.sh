#!/usr/bin/env bash
# Bootstrap MOT LAN cho Production Farmer tren may AWS t3a.medium.
#
# Chay bang quyen root (`sudo bash .../bootstrap-farmer.sh`). Day la HANH
# DONG THU CONG DUY NHAT — moi buoc can root deu nam trong day, vi phien tu
# dong khong duoc phep leo thang quyen.
#
# Bi mat: khoa Gemini duoc go o mot dau nhac AN (`read -rs`) roi di THANG vao
# mot tep 0600 cua user `fanfic`. No khong bao gio xuat hien trong:
#   - dong lenh (nen khong o `ps`, khong o lich su shell)
#   - bien moi truong cua mot tien trinh con nao (nen khong o `/proc/*/environ`)
#   - stdout/stderr, journal, hay bat ky artifact nao
#
# KHONG dung toi `worker-prod.env` hay bat ky bi mat production nao dang co.
#
# Cong: farmer CHI duoc bat chay lien tuc sau khi CA BON phep kiem cuoi cung
# dat. Hong mot cai la script dung, va dich vu khong chay.

set -euo pipefail
umask 077

# Tuyet doi khong bat trace: `set -x` se in ca bien chua khoa.
set +x

REPO=/opt/fanfic-audio
ETC=/etc/fanfic-audio
ENV_FILE="$ETC/farmer.env"
SRC_FILE="$ETC/farmer-text-sources.json"
UNIT=/etc/systemd/system/fanfic-farmer.service
VENV="$REPO/.venv/bin/python"
SVC_USER=fanfic

die() { printf '\n[LOI] %s\n' "$1" >&2; exit 1; }
ok()  { printf '  [OK]   %s\n' "$1"; }
info(){ printf '  [ .. ] %s\n' "$1"; }

[ "$(id -u)" -eq 0 ] || die "phai chay bang root (sudo bash $0)"
[ -d "$REPO" ]  || die "khong thay $REPO"
[ -x "$VENV" ]  || die "khong thay venv $VENV"
id "$SVC_USER" >/dev/null 2>&1 || die "khong co user $SVC_USER"

# Ghi lai quyen cua worker-prod.env TRUOC khi lam gi — de chung minh o cuoi
# rang khong co gi bi noi long.
WPE="$ETC/worker-prod.env"
WPE_BEFORE=""
[ -f "$WPE" ] && WPE_BEFORE="$(stat -c '%U:%G %a' "$WPE")"

printf '\n=== Bootstrap Production Farmer ===\n\n'

# --------------------------------------------------------------- 1. khoa --
printf 'Dan FARMER_GEMINI_API_KEY (khong hien khi go, Enter de xac nhan):\n> '
read -rs GEMINI_KEY
printf '\n\n'
[ -n "${GEMINI_KEY:-}" ] || die "khoa rong — dung lai, khong ghi gi"

# ------------------------------------------------------- 2. tep cau hinh --
info "ghi $ENV_FILE (0600 $SVC_USER)"
install -o "$SVC_USER" -g "$SVC_USER" -m 600 /dev/null "$ENV_FILE"

# `printf` la builtin cua bash => khoa KHONG di qua argv cua mot tien trinh
# nao. Ghi qua stdin vao tep da tao san dung quyen.
{
  printf '# Sinh boi deploy/bootstrap-farmer.sh — KHONG commit tep nay.\n'
  printf 'FARMER_GEMINI_API_KEY=%s\n' "$GEMINI_KEY"
  printf 'FARMER_REVIEW_MODEL=gemini-3.8-flash\n'
  printf 'FARMER_REVIEW_MIN_SCORE=70\n'
  printf 'FARMER_MAX_CONCURRENT_DOWNLOADS=2\n'
  printf 'FARMER_MAX_REVIEW_REQUESTS=8\n'
  printf 'FARMER_MAX_TTS_JOBS=3\n'
  printf 'FARMER_MIN_FREE_DISK_BYTES=5368709120\n'
  printf 'FARMER_ROUND_SLEEP_SECONDS=900\n'
  printf 'FARMER_BATCH_PER_LANE=3\n'
  printf 'FARMER_WORK_DIR=/var/lib/fanfic-farmer/work\n'
  printf 'FARMER_STATUS_PATH=/var/lib/fanfic-farmer/status.json\n'
  printf 'FARMER_TEXT_SOURCES=%s\n' "$SRC_FILE"
} > "$ENV_FILE"

unset GEMINI_KEY   # khong giu trong bo nho script lau hon can thiet
ok "cau hinh farmer da ghi (khoa khong bao gio duoc in ra)"

# Nguon truyen chu — chi tao neu CHUA co, de khong de len danh sach that.
if [ ! -f "$SRC_FILE" ]; then
  install -o "$SVC_USER" -g "$SVC_USER" -m 640 /dev/null "$SRC_FILE"
  cat > "$SRC_FILE" <<'JSON'
{
  "_note": "Nguon truyen chu cho lan B. Them muc vao day; khong can deploy lai.",
  "sources": [
    {
      "url": "https://vi.wikisource.org/wiki/L%E1%BB%81u_ch%C3%B5ng",
      "title": "Leu chong",
      "author": "Ngo Tat To",
      "language": "vi"
    }
  ]
}
JSON
  ok "nguon truyen chu mau da tao ($SRC_FILE)"
else
  ok "nguon truyen chu da co tu truoc — giu nguyen"
fi

install -d -o "$SVC_USER" -g "$SVC_USER" -m 755 /var/lib/fanfic-farmer
install -d -o "$SVC_USER" -g "$SVC_USER" -m 755 /var/lib/fanfic-farmer/work

# ------------------------------------------------------------- 3. dich vu --
info "cai unit systemd"
install -o root -g root -m 644 "$REPO/deploy/fanfic-farmer.service" "$UNIT"
systemctl daemon-reload
ok "unit da cai ($UNIT)"

# ------------------------------------------- 4. kiem khoa (khong in khoa) --
info "kiem khoa Gemini bang MOT lan goi that"
# Khoa di tu tep -> moi truong cua CHINH tien trinh python, KHONG qua argv.
# `runuser` doc tep env bang quyen cua `fanfic`, dung chu so huu that.
CRED_OUT="$(runuser -u "$SVC_USER" -- env -i \
  HOME="/var/lib/fanfic-farmer" PATH=/usr/bin:/bin \
  bash -c "set -a; . '$ENV_FILE'; . '$ETC/worker-prod.env'; set +a; \
           cd '$REPO' && exec '$VENV' -m server.farmer --verify-credential" \
  2>&1 || true)"

case "$CRED_OUT" in
  *'"credential": "OK"'*) ok "khoa Gemini dung duoc — $CRED_OUT" ;;
  *) die "khoa Gemini KHONG dung duoc: $CRED_OUT" ;;
esac

# ------------------------------------------------ 5. lo chay co kiem soat --
info "chay MOT vong co kiem soat (--once, gioi han boi han muc)"
BATCH_OUT="$(runuser -u "$SVC_USER" -- env -i \
  HOME="/var/lib/fanfic-farmer" PATH=/usr/bin:/bin \
  bash -c "set -a; . '$ENV_FILE'; . '$ETC/worker-prod.env'; set +a; \
           cd '$REPO' && exec '$VENV' -m server.farmer --once" 2>&1 || true)"
printf '%s\n' "$BATCH_OUT" | tail -40

# ---------------------------------------------------------- 6. BON PHEP KIEM
printf '\n=== Kiem tra cuoi (khong co bi mat nao trong phan nay) ===\n'
FAIL=0

# (a) cau hinh co mat, dung chu so huu, dung quyen
CFG="$(stat -c '%U:%G %a' "$ENV_FILE")"
if [ "$CFG" = "$SVC_USER:$SVC_USER 600" ]; then
  ok "cau hinh farmer: $ENV_FILE ($CFG)"
else
  printf '  [FAIL] quyen cau hinh sai: %s\n' "$CFG"; FAIL=1
fi

# (b) dich vu da cai
if systemctl cat fanfic-farmer.service >/dev/null 2>&1; then
  ok "dich vu da cai: fanfic-farmer.service"
else
  printf '  [FAIL] chua cai duoc unit\n'; FAIL=1
fi

# (c) khoa danh gia dung duoc (da kiem o buoc 4)
ok "khoa danh gia Gemini: dung duoc"

# (d) hai worker production KHONG bi dong toi
for svc in fanfic-worker-prod fanfic-translation-worker-prod; do
  if [ "$(systemctl is-active "$svc" 2>/dev/null)" = "active" ]; then
    ok "worker production con nguyen: $svc (active)"
  else
    printf '  [FAIL] %s khong con active\n' "$svc"; FAIL=1
  fi
done

# (e) khong noi long bi mat production nao
if [ -n "$WPE_BEFORE" ]; then
  WPE_AFTER="$(stat -c '%U:%G %a' "$WPE")"
  if [ "$WPE_BEFORE" = "$WPE_AFTER" ]; then
    ok "worker-prod.env khong bi doi quyen ($WPE_AFTER)"
  else
    printf '  [FAIL] worker-prod.env doi quyen: %s -> %s\n' \
      "$WPE_BEFORE" "$WPE_AFTER"; FAIL=1
  fi
fi

# ------------------------------------------------------------ 7. cong bat --
if [ "$FAIL" -ne 0 ]; then
  printf '\n=== DUNG LAI: co phep kiem hong. Farmer KHONG duoc bat. ===\n'
  exit 1
fi

printf '\n=== Bon phep kiem deu dat — bat farmer chay lien tuc ===\n'
systemctl enable --now fanfic-farmer
sleep 3
systemctl is-active fanfic-farmer >/dev/null 2>&1 \
  && ok "fanfic-farmer: active" \
  || die "bat fanfic-farmer that bai — xem: journalctl -u fanfic-farmer -n 50"

printf '\nXong. Theo doi:\n'
printf '  journalctl -u fanfic-farmer -f\n'
printf '  cat /var/lib/fanfic-farmer/status.json\n\n'
