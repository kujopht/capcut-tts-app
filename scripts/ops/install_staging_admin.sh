#!/usr/bin/env bash
# Cai cong dieu hanh HEP cho AWS staging. Chay MOT LAN, bang root:
#
#     sudo bash /home/ubuntu/install_staging_admin.sh
#
# Sau lan nay, vong go loi staging tu chu duoc: ben khong-dac-quyen chi can
# GHI mot tep verb vao hang doi, khong can quyen root nao nua.
#
# CAI GI
#   /usr/local/sbin/fanfic-staging-admin        root:root 0755  (ma dac quyen
#                                               DUY NHAT; khong nhan shell)
#   /var/lib/fanfic-staging-admin/req           root:ubuntu 0730 (ubuntu GHI
#                                               duoc, KHONG liet ke duoc)
#   /var/lib/fanfic-staging-admin/res           root:root 0755  (doc duoc)
#   fanfic-staging-admin.service                oneshot, goi `drain`
#   fanfic-staging-admin.timer                  moi 15s
#   /var/log/fanfic-staging-admin.log           audit
#
# KHONG cai: khong sudoers, khong NOPASSWD, khong setuid, khong doi guard cua
# kho. Ben khong-dac-quyen KHONG BAO GIO chay duoc lenh tuy y — no chi chon
# duoc mot trong sau verb da duyet.
set -euo pipefail

APP=/opt/fanfic-audio
BASE=/var/lib/fanfic-staging-admin
SRC="$APP/scripts/ops/fanfic_staging_admin.sh"
NGUOI="${NGUOI_KHONG_DAC_QUYEN:-ubuntu}"

[ "$(id -u)" -eq 0 ] || { echo "phai chay bang root" >&2; exit 1; }

# Tim ma dac quyen: uu tien checkout (nguon su that), roi den ban da stage.
# Trinh cai nay duoc chay DUNG MOT LAN boi nguoi van hanh, nen no phai tu lo
# duoc moi truong hop thay vi that bai va doi mot luot nua.
if [ ! -f "$SRC" ] && [ -d "$APP/.git" ]; then
  echo "=== 0. checkout chua co ma dac quyen — dua ve origin/main ==="
  git config --global --add safe.directory "$APP" 2>/dev/null || true
  git -C "$APP" fetch --quiet origin 2>&1 | sed 's/^/  /' || true
  git -C "$APP" reset --quiet --hard origin/main 2>&1 | sed 's/^/  /' || true
  echo "  SHA: $(git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo '?')"
fi
if [ ! -f "$SRC" ] && [ -f /home/"$NGUOI"/fanfic_staging_admin.sh ]; then
  echo "  dung ban da stage o /home/$NGUOI/fanfic_staging_admin.sh"
  SRC=/home/"$NGUOI"/fanfic_staging_admin.sh
fi
if [ ! -f "$SRC" ]; then
  echo "THIEU ma dac quyen o ca hai duong:" >&2
  echo "  $APP/scripts/ops/fanfic_staging_admin.sh" >&2
  echo "  /home/$NGUOI/fanfic_staging_admin.sh" >&2
  exit 2
fi

echo "=== 1. ma dac quyen ==="
install -m 0755 -o root -g root "$SRC" /usr/local/sbin/fanfic-staging-admin
echo "  /usr/local/sbin/fanfic-staging-admin ($(stat -c '%a %U:%G' /usr/local/sbin/fanfic-staging-admin))"

echo "=== 2. hang doi ==="
install -d -m 0755 -o root -g root "$BASE"
# 0730: `ubuntu` TAO duoc tep yeu cau nhung KHONG liet ke duoc thu muc —
# khong doc duoc yeu cau cua phien khac.
install -d -m 0730 -o root -g "$NGUOI" "$BASE/req"
install -d -m 0755 -o root -g root "$BASE/res"
: > /var/log/fanfic-staging-admin.log
chmod 0644 /var/log/fanfic-staging-admin.log
echo "  req: $(stat -c '%a %U:%G' "$BASE/req")   res: $(stat -c '%a %U:%G' "$BASE/res")"

echo "=== 3. unit systemd ==="
cat > /etc/systemd/system/fanfic-staging-admin.service <<'UNIT'
[Unit]
Description=Fanfic AWS staging — cong dieu hanh HEP (drain hang doi yeu cau)
Documentation=file:/opt/fanfic-audio/scripts/ops/fanfic_staging_admin.sh
# KHONG dinh gi den GCE. Chi cham ba unit staging cua chinh may nay.

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/fanfic-staging-admin drain
# Can root that: no goi systemctl va sua /etc/fanfic-audio. Nhung no KHONG
# nhan shell tuy y — chi mot verb trong allowlist dong cung.
User=root
# Bao ve toi thieu con giu duoc chuc nang: khong doi duoc /home, khong leo
# quyen moi.
NoNewPrivileges=true
ProtectHome=true
PrivateTmp=true
UNIT

cat > /etc/systemd/system/fanfic-staging-admin.timer <<'UNIT'
[Unit]
Description=Fanfic AWS staging — quet hang doi dieu hanh moi 15s

[Timer]
OnBootSec=30s
OnUnitActiveSec=15s
AccuracySec=5s
Unit=fanfic-staging-admin.service

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now fanfic-staging-admin.timer >/dev/null 2>&1 || true
echo "  timer: $(systemctl is-active fanfic-staging-admin.timer) / $(systemctl is-enabled fanfic-staging-admin.timer)"

echo
echo "=== 4. thu ngay mot verb ==="
/usr/local/sbin/fanfic-staging-admin status 2>&1 | head -12 | sed 's/^/  /'

echo
echo "==================================================================="
echo "  XONG. Tu day ben khong-dac-quyen dieu hanh bang cach GHI verb:"
echo "      echo status > $BASE/req/\$(date +%s).req"
echo "  roi doc ket qua o $BASE/res/<id>.out"
echo "  Verb duoc phep: status reconcile restart logs run-proof update"
echo "==================================================================="
