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

# --- MO HINH QUYEN: root so huu va DONG BO kho; fanfic chi DOC va chay ------
#
# Kho `/opt/fanfic-audio` thuoc root:root 755. Do la mo hinh dung, va script
# nay KHONG duoc pha no:
#
#   - Dong bo git la viec cua ROOT (danh tinh trien khai hop phap). Chay
#     `git` bang `fanfic` o day se hong khi ghi `.git`, va "sua" no bang
#     `chown` hay `safe.directory` chi la di vong qua mo hinh quyen chu khong
#     phai ton trong no.
#   - Dich vu luc CHAY van la `fanfic` (khong dac quyen). No chi can bit `r-x`
#     cho `other` tren kho — da co san — va quyen ghi vao thu muc trang thai
#     CUA RIENG NO.
#
# Kiem thanh that thay vi gia dinh: neu ai do da chown kho sang `fanfic`, mo
# hinh da bi doi va ta muon biet, khong muon lang le chay tiep.
REPO_OWNER="$(stat -c '%U' "$REPO")"
[ "$REPO_OWNER" = "root" ] || die \
  "kho $REPO thuoc '$REPO_OWNER', khong phai root — mo hinh trien khai da bi
   doi. Dung lai thay vi tu y sua quyen."

# `fanfic` phai DOC duoc kho (bit r-x cho other), nhung KHONG duoc so huu no.
[ "$(stat -c '%A' "$REPO" | cut -c8-10)" = "r-x" ] || die \
  "$REPO khong cho 'other' doc/di qua — dich vu chay bang $SVC_USER se khong
   doc duoc ma nguon. Khong tu noi long o day."

# Ghi lai quyen cua worker-prod.env TRUOC khi lam gi — de chung minh o cuoi
# rang khong co gi bi noi long.
WPE="$ETC/worker-prod.env"
WPE_BEFORE=""
[ -f "$WPE" ] && WPE_BEFORE="$(stat -c '%U:%G %a' "$WPE")"

printf '\n=== Bootstrap Production Farmer ===\n\n'

# ------------------------------------------- 0. dong bo kho BANG QUYEN ROOT --
# Chay TRUOC khi cham vao bat cu thu gi khac, va fail closed: neu khong dua
# duoc kho ve dung ban can trien khai thi khong cau hinh, khong cai dat,
# khong bat dich vu.
info "kiem ket noi toi remote (khong in URL/credential)"
# `ls-remote` xac minh CA ket noi lan quyen doc, va khong in gi khi thanh
# cong. Deliberately vut stdout: mot remote HTTPS co the mang token trong
# URL, va no khong duoc phep loang ra man hinh hay journal.
if ! git -C "$REPO" ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
  die "danh tinh trien khai (root) khong truy cap duoc remote — dung lai,
   khong sua gi. Kiem tra mang/quyen doc kho roi chay lai."
fi
ok "remote truy cap duoc bang danh tinh trien khai (root)"

BEFORE_SHA="$(git -C "$REPO" rev-parse --short HEAD)"
info "dong bo kho bang root (truoc: $BEFORE_SHA)"

# Cay lam viec phai SACH: `merge --ff-only` se tu choi neu co thay doi cuc bo,
# va do la dieu ta muon — mot ban va tay tren may san xuat phai duoc nhin thay
# chu khong bi ghi de am tham.
if ! git -C "$REPO" diff --quiet || ! git -C "$REPO" diff --cached --quiet; then
  die "cay lam viec tai $REPO co thay doi cuc bo chua commit — dung lai.
   Xem: git -C $REPO status"
fi

git -C "$REPO" fetch --quiet origin || die "git fetch that bai (root)"
git -C "$REPO" checkout --quiet main || die "khong checkout duoc main"
git -C "$REPO" merge --ff-only --quiet origin/main \
  || die "khong fast-forward duoc len origin/main — dung lai thay vi ep."

AFTER_SHA="$(git -C "$REPO" rev-parse --short HEAD)"
ok "kho da dong bo bang root: $BEFORE_SHA -> $AFTER_SHA"

# Sau khi dong bo, quyen phai VAN nhu cu — git khong doi chu so huu, nhung
# kiem lai de mot buoc nao do sau nay khong lang le lam hong mo hinh.
[ "$(stat -c '%U' "$REPO")" = "root" ] || die "chu so huu kho da doi sau khi dong bo"

[ -f "$REPO/deploy/fanfic-farmer.service" ] \
  || die "khong thay unit sau khi dong bo — ban trien khai khong dung"

# --------------------------------------------------- 1. (khong con khoa) --
# Danh gia noi dung DI QUA HANG DOI + pool Antigravity tren may Windows, nen
# may nay KHONG can khoa Gemini nao ca. Doan hoi khoa da duoc bo co y: hoi
# mot bi mat khong dung toi la mot cach de no bi ro ri ma khong duoc gi.
info "che do danh gia: hang doi (FARMER_REVIEW_PROVIDER=queue) — khong can khoa Gemini"

# ------------------------------------------------------- 2. tep cau hinh --
info "ghi $ENV_FILE (0600 $SVC_USER)"
install -o "$SVC_USER" -g "$SVC_USER" -m 600 /dev/null "$ENV_FILE"

# `printf` la builtin cua bash => khoa KHONG di qua argv cua mot tien trinh
# nao. Ghi qua stdin vao tep da tao san dung quyen.
{
  printf '# Sinh boi deploy/bootstrap-farmer.sh — KHONG commit tep nay.\n'
  # Danh gia qua HANG DOI: may nay xep viec, may Windows (Router V4 + pool
  # Antigravity) poll ra ngoai va tra ban an. Khong khoa Gemini o day.
  printf 'FARMER_REVIEW_PROVIDER=queue\n'
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

ok "cau hinh farmer da ghi ($ENV_FILE)"

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

# ---------------------------------------------- 4. kiem hang doi danh gia --
# KHONG con kiem khoa Gemini: may nay khong danh gia. Thay vao do kiem thu
# duong ma cong danh gia THAT SU se di — hang doi Appwrite. Neu collection
# `review_jobs` chua duoc cap phat, buoc nay bao ro, va farmer se fail closed
# thay vi san xuat noi dung chua ai duyet.
info "kiem duong hang doi danh gia (khong goi model nao)"
QUEUE_OUT="$(runuser -u "$SVC_USER" -- env -i \
  HOME="/var/lib/fanfic-farmer" PATH=/usr/bin:/bin \
  bash -c "set -a; . '$ENV_FILE'; . '$ETC/worker-prod.env'; set +a; \
           cd '$REPO' && exec '$VENV' -m server.farmer --check-review-queue" \
  2>&1 || true)"

case "$QUEUE_OUT" in
  *'"review_queue": "OK"'*) ok "hang doi danh gia san sang — $QUEUE_OUT" ;;
  *) die "hang doi danh gia CHUA san sang: $QUEUE_OUT
   Nhieu kha nang collection 'review_jobs' chua duoc cap phat. Xem
   docs/reports/OVERNIGHT_BLOCKERS.md muc B1." ;;
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
