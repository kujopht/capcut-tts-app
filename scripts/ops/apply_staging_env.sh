#!/usr/bin/env bash
# Nap bon bien Appwrite STAGING vao hai tep env cua worker tren may staging.
#
# Doc tu STDIN, chay bang root TREN CHINH may staging:
#
#     <nguon> | ssh ... "sudo bash /home/ubuntu/apply_staging_env.sh"
#
# KHONG BAO GIO in gia tri. Chi in TEN bien va PASS/FAIL.
#
# VI SAO CO TEP NAY thay vi mot chuoi lenh dai qua ssh: lan truoc chuoi lenh
# do hong theo dung hai cach ma mot tep script khong the hong:
#
#   1. `chmod 640 /etc/fanfic-audio/*.env` — dau `*` duoc SHELL KHONG-DAC-QUYEN
#      tren may dich khai trien TRUOC khi `sudo` chay. User `ubuntu` khong doc
#      duoc thu muc 0750 root:fanfic, nen glob khong no ra, va chmod nhan dung
#      chuoi `*.env` -> "cannot access". Trong tep nay moi glob deu chay SAU
#      khi da vao root.
#   2. Khong co buoc kiem NGUON truoc khi sua DICH. Nguon hong (sai duong dan)
#      van de cac lenh phia sau chay, sua tep dich roi moi bao loi.
#
# Nguyen tac o day: KIEM TRUOC, SUA SAU, ROI KIEM LAI.
set -euo pipefail

DICH_DIR="${DICH_DIR:-/etc/fanfic-audio}"
NHOM="${NHOM:-fanfic}"
BIEN=(APPWRITE_ENDPOINT APPWRITE_PROJECT_ID APPWRITE_DATABASE_ID APPWRITE_API_KEY)
TEP=(worker.env translation-worker.env)

loi() { echo "FAIL: $*"; exit 1; }

# --- 1. DOC va KIEM NGUON — chua cham gi vao tep dich -----------------------
tmp="$(mktemp)"
chmod 600 "$tmp"
trap 'rm -f "$tmp" "$tmp.moi"' EXIT
cat > "$tmp"

for v in "${BIEN[@]}"; do
  # `=..*` doi PHAI CO gia tri: mot dong `APPWRITE_API_KEY=` rong khong tinh.
  grep -qE "^${v}=..*" "$tmp" || loi "nguon thieu ${v} (khong sua gi tren may nay)"
done
thua="$(grep -cvE "^(#|$|APPWRITE_(ENDPOINT|PROJECT_ID|DATABASE_ID|API_KEY)=)" "$tmp" || true)"
[ "$thua" -eq 0 ] || loi "nguon co ${thua} dong ngoai bon bien Appwrite — tu choi"

# --- 2. KIEM DICH ton tai ---------------------------------------------------
[ -d "$DICH_DIR" ] || loi "thieu thu muc ${DICH_DIR}"
for f in "${TEP[@]}"; do
  [ -f "${DICH_DIR}/${f}" ] || loi "thieu ${DICH_DIR}/${f} — chay bootstrap truoc"
done

# --- 3. SUA — nguyen tu tung tep -------------------------------------------
for f in "${TEP[@]}"; do
  p="${DICH_DIR}/${f}"
  # Bo moi dong APPWRITE_* cu (ke ca dong rong mau) roi ghi bon dong moi.
  grep -vE "^APPWRITE_(ENDPOINT|PROJECT_ID|DATABASE_ID|API_KEY)=" "$p" > "$tmp.moi" || true
  cat "$tmp" >> "$tmp.moi"
  chmod 0640 "$tmp.moi"
  chown "root:${NHOM}" "$tmp.moi" 2>/dev/null || true
  mv -f "$tmp.moi" "$p"
done

# --- 4. KIEM LAI — chi TEN bien, khong bao gio gia tri ----------------------
sai=0
for f in "${TEP[@]}"; do
  for v in "${BIEN[@]}"; do
    grep -qE "^${v}=..*" "${DICH_DIR}/${f}" || { echo "  THIEU ${v} trong ${f}"; sai=1; }
  done
  # Chi cuong che quyen KHI dang thuc su chay bang root. Tren may dich that
  # (chay qua `sudo`) dieu kien nay luon dung. Trong bo test chay bang user
  # thuong thi `chown root:fanfic` khong the thanh cong, va bat loi o do chi
  # la bat chinh moi truong test — khong phai bat mot khiem khuyet that.
  if [ "$(id -u)" -eq 0 ]; then
    q="$(stat -c '%a %U:%G' "${DICH_DIR}/${f}")"
    [ "$q" = "640 root:${NHOM}" ] || { echo "  QUYEN SAI ${f}: ${q}"; sai=1; }
  fi
done
[ "$sai" -eq 0 ] || loi "kiem lai khong dat"

echo "PASS: 4/4 bien Appwrite co mat trong ${#TEP[@]} tep, quyen 640 root:${NHOM}"
