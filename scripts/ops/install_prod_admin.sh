#!/usr/bin/env bash
# Cai cong dieu hanh HEP cho worker PRODUCTION tren AWS. Chay MOT LAN, bang
# root, tren chinh may AWS:
#
#     sudo bash /home/ubuntu/install_prod_admin.sh
#
# Sau lan nay, ca cuoc cutover tu chu duoc: ben khong-dac-quyen chi GHI mot
# dong verb vao hang doi, khong can quyen root nao nua.
#
# CAI GI
#   /usr/local/sbin/fanfic-prod-admin       root:root 0755  (ma dac quyen
#                                           DUY NHAT; khong nhan shell)
#   /var/lib/fanfic-prod-admin/req          root:ubuntu 0730 (ubuntu GHI
#                                           duoc, KHONG liet ke duoc)
#   /var/lib/fanfic-prod-admin/res          root:root 0755  (doc duoc)
#   /var/lib/fanfic-prod-admin/env.stage    root:ubuntu 0620 (ubuntu GHI
#                                           duoc, KHONG doc lai duoc)
#   fanfic-prod-admin.service               oneshot, goi `drain`
#   fanfic-prod-admin.timer                 moi 15s
#   /var/log/fanfic-prod-admin.log          audit, 0640 root:adm
#   4 unit production tu deploy/            (chua enable, chua start)
#   /var/lib/fanfic-audio-prod              FAS_VAR_DIR cua worker TTS
#   /var/lib/fanfic-audio-translation-prod  FAS_VAR_DIR cua worker dich
#
# KHONG cai: khong sudoers, khong NOPASSWD, khong setuid. Ben
# khong-dac-quyen KHONG BAO GIO chay duoc lenh tuy y — no chi chon duoc mot
# trong muoi verb da duyet, va bon verb nguy hiem nhat con phai qua
# `validate_prod_env.py` truoc.
#
# KHONG bat dich vu nao. Cai xong, may van dung yen — `start` la mot buoc
# rieng, co y.
set -euo pipefail

APP=/opt/fanfic-audio
BASE=/var/lib/fanfic-prod-admin
SRC="$APP/scripts/ops/fanfic_prod_admin.sh"
NGUOI="${NGUOI_KHONG_DAC_QUYEN:-ubuntu}"

[ "$(id -u)" -eq 0 ] || { echo "phai chay bang root" >&2; exit 1; }
id -u fanfic >/dev/null 2>&1 || { echo "thieu user 'fanfic' — chay worker_bootstrap.sh truoc" >&2; exit 1; }

# NGUON DUY NHAT la checkout git. KHONG co duong lui sang /home/$NGUOI.
#
# Ban truoc co mot nhanh lui: neu checkout thieu tep thi lay
# `/home/ubuntu/fanfic_prod_admin.sh`. Do la mot lo hong that — thu muc do
# thuoc ben KHONG-DAC-QUYEN, nen mot lan `git fetch` that bai (mat mang,
# DNS hong, kho hong) se lam trinh cai dat MA CUA KE TAN CONG vao
# /usr/local/sbin/fanfic-prod-admin, chay bang root moi 15 giay.
#
# Cung ly le do ap cho chinh trinh cai nay: hay chay no TU CHECKOUT
# (`/opt/fanfic-audio`, thuoc root), dung chay ban trong /home.
echo "=== 0. dua checkout ve origin/main ==="
[ -d "$APP/.git" ] || { echo "THIEU checkout git tai $APP" >&2; exit 2; }
git config --global --add safe.directory "$APP" 2>/dev/null || true
git -C "$APP" fetch origin 2>&1 | sed 's/^/  /' || { echo "fetch that bai" >&2; exit 2; }
git -C "$APP" reset --quiet --hard origin/main 2>&1 | sed 's/^/  /' \
  || { echo "reset that bai" >&2; exit 2; }
echo "  SHA: $(git -C "$APP" rev-parse HEAD 2>/dev/null || echo '?')"

[ -f "$SRC" ] || {
  echo "THIEU ma dac quyen trong checkout: $SRC" >&2
  echo "(khong co duong lui sang /home — day la co y, xem ghi chu o tren)" >&2
  exit 2
}

echo "=== 1. ma dac quyen ==="
install -m 0755 -o root -g root "$SRC" /usr/local/sbin/fanfic-prod-admin
echo "  /usr/local/sbin/fanfic-prod-admin ($(stat -c '%a %U:%G' /usr/local/sbin/fanfic-prod-admin))"

echo "=== 2. hang doi + cho dat env ==="
install -d -m 0755 -o root -g root "$BASE"
# 0730: `ubuntu` TAO duoc tep yeu cau nhung KHONG liet ke duoc thu muc.
install -d -m 0730 -o root -g "$NGUOI" "$BASE/req"
install -d -m 0755 -o root -g root "$BASE/res"
# env.stage: `ubuntu` GHI duoc (0620) nhung KHONG DOC lai duoc. Tep nay
# mang bi mat production trong vai giay; khong ai ngoai root doc lai no.
install -m 0620 -o root -g "$NGUOI" /dev/null "$BASE/env.stage"
# Tep stage THU HAI cho worker dich — hinh dang env khac han (khong R2,
# STORAGE_BACKEND=local), nen no co duong rieng thay vi dung chung.
install -m 0620 -o root -g "$NGUOI" /dev/null "$BASE/env-translation.stage"
for p in "$BASE" "$BASE/req" "$BASE/res" "$BASE/env.stage" "$BASE/env-translation.stage"; do
  echo "  $p ($(stat -c '%a %U:%G' "$p"))"
done

echo "=== 3. audit log ==="
install -m 0640 -o root -g adm /dev/null /var/log/fanfic-prod-admin.log
echo "  /var/log/fanfic-prod-admin.log ($(stat -c '%a %U:%G' /var/log/fanfic-prod-admin.log))"

echo "=== 4. FAS_VAR_DIR cua hai worker ==="
for d in /var/lib/fanfic-audio-prod /var/lib/fanfic-audio-translation-prod; do
  install -d -m 0750 -o fanfic -g fanfic "$d"
  echo "  $d ($(stat -c '%a %U:%G' "$d"))"
done

echo "=== 5. unit production (cai, KHONG enable, KHONG start) ==="
for u in fanfic-worker-prod.service fanfic-translation-worker-prod.service \
         fanfic-worker-prod-health.service fanfic-worker-prod-health.timer; do
  if [ -f "$APP/deploy/$u" ]; then
    install -m 0644 -o root -g root "$APP/deploy/$u" "/etc/systemd/system/$u"
    echo "  $u"
  else
    echo "  THIEU $APP/deploy/$u" >&2; exit 3
  fi
done

# Khong can drop-in cho duong model: `deploy/fanfic-worker-prod.service` da
# co san `Environment=FAS_PIPER_MODELS_DIR=/opt/fanfic-models/nghitts/piper-tts`.
# Them mot drop-in trung gia tri chi tao ra nguon su that thu hai.

echo "=== 6. dich vu drain ==="
cat > /etc/systemd/system/fanfic-prod-admin.service <<'EOF'
[Unit]
Description=Fanfic AWS production — cong dieu hanh HEP (drain hang doi yeu cau)

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/fanfic-prod-admin drain
# Hep quyen y het ban staging. ProtectHome=true nghia la cong nay KHONG
# NHIN THAY /home — moi duong dan no dung deu phai nam trong /opt, /etc,
# /var. Da tung mat mot vong go loi vi quen dieu do.
#
# `/usr/local/sbin` nam trong ReadWritePaths vi mot ly do cu the: verb
# `update` dong bo ban root cua chinh cong nay tu checkout. `ProtectSystem=full`
# lam /usr CHI DOC, nen khong co dong do thi `update` khong bao gio thay
# duoc ma cua cong — va vi loi bi nuot (`2>/dev/null || true`) nen no bao
# thanh cong. Da xay ra that: mot verb moi duoc merge vao kho nhung cong
# tren may van chay ban cu, im lang.
#
# Rui ro chap nhan duoc: nguon cua ban copy la `/opt/fanfic-audio` — thuoc
# `root:root` hoan toan tren may nay (da kiem), nen khong co nguoi dung
# khong-dac-quyen nao chen duoc ma vao do.
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=/etc/fanfic-audio /var/lib/fanfic-prod-admin /var/log/fanfic-prod-admin.log /var/lib/fanfic-audio-prod /var/lib/fanfic-audio-translation-prod /usr/local/sbin
EOF
cat > /etc/systemd/system/fanfic-prod-admin.timer <<'EOF'
[Unit]
Description=Fanfic AWS production — quet hang doi yeu cau moi 15s

[Timer]
OnBootSec=30
OnUnitActiveSec=15
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now fanfic-prod-admin.timer >/dev/null 2>&1
echo "  fanfic-prod-admin.timer: $(systemctl is-active fanfic-prod-admin.timer)"

echo
echo "=== XONG ==="
echo "KHONG dich vu worker nao duoc bat. Buoc tiep theo chay tu may dieu hanh:"
echo "    python scripts/ops/prod_cutover.py prepare"
/usr/local/sbin/fanfic-prod-admin status || true
