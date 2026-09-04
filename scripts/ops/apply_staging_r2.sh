#!/usr/bin/env bash
# Nap bon bien R2 STAGING vao hai tep env cua worker tren may staging.
#
# Doc tu STDIN, chay bang root TREN CHINH may staging:
#
#     <nguon> | ssh ... "sudo bash /home/ubuntu/apply_staging_r2.sh"
#
# Cung ky luat voi `apply_staging_env.sh`: KIEM TRUOC, SUA SAU, ROI KIEM LAI.
# KHONG BAO GIO in gia tri. Chi in TEN bien, ten BUCKET, va PASS/FAIL.
#
# KHAC MOT DIEM QUAN TRONG so voi ban Appwrite: o day co mot rao chan TEN
# BUCKET, va no la ALLOWLIST chu khong phai denylist.
#
#   R2_BUCKET phai nam trong BUCKET_STAGING.
#
# "Khong phai fanfic-prod nen coi la an toan" la SAI: mot bucket production
# KHAC, hoac mot lan go sai ten, van phai bi tu choi. Rao chan nay dat ngay
# tai BIEN GIOI CHUYEN GIAO — truoc khi mot byte nao duoc ghi vao tep env —
# nen mot lan go sai khong bao gio ket thuc bang viec worker staging ghi vao
# kho production.
set -euo pipefail

DICH_DIR="${DICH_DIR:-/etc/fanfic-audio}"
NHOM="${NHOM:-fanfic}"
BIEN=(R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET)
TEP=(worker.env translation-worker.env)

#: Bucket duoc phep cho staging. Khop voi `R2_BUCKET_STAGING` trong
#: `scripts/ops/worker_staging_acceptance.py` — hai cho phai cung mot y.
BUCKET_STAGING="fanfic-staging fanfic-dev"
#: Ten production, chan tuong minh de thong bao loi noi ro no la production.
BUCKET_PRODUCTION="fanfic-prod"

loi() { echo "FAIL: $*"; exit 1; }

tmp="$(mktemp)"
chmod 600 "$tmp"
trap 'rm -f "$tmp" "$tmp.moi"' EXIT
cat > "$tmp"

# --- 1. KIEM NGUON — chua cham gi vao tep dich -----------------------------
for v in "${BIEN[@]}"; do
  grep -qE "^${v}=..*" "$tmp" || loi "nguon thieu ${v} (khong sua gi tren may nay)"
done
thua="$(grep -cvE "^(#|$|R2_(ACCOUNT_ID|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)=)" "$tmp" || true)"
[ "$thua" -eq 0 ] || loi "nguon co ${thua} dong ngoai bon bien R2 — tu choi"

# --- 2. RAO CHAN BUCKET — truoc khi ghi bat ky thu gi ----------------------
bucket="$(grep -E '^R2_BUCKET=' "$tmp" | tail -1 | cut -d= -f2- | tr -d '\r' | tr -d '[:space:]')"
echo "  R2_BUCKET nhan duoc : ${bucket}"
[ "$bucket" != "$BUCKET_PRODUCTION" ] \
  || loi "bucket la PRODUCTION (${BUCKET_PRODUCTION}) — tu choi tuyet doi"
ok_bucket=0
for b in $BUCKET_STAGING; do [ "$b" = "$bucket" ] && ok_bucket=1; done
[ "$ok_bucket" -eq 1 ] \
  || loi "bucket '${bucket}' khong nam trong danh sach staging (${BUCKET_STAGING})"
echo "  -> bucket nam trong danh sach staging: DAT"

# --- 3. KIEM DICH ----------------------------------------------------------
[ -d "$DICH_DIR" ] || loi "thieu thu muc ${DICH_DIR}"
for f in "${TEP[@]}"; do
  [ -f "${DICH_DIR}/${f}" ] || loi "thieu ${DICH_DIR}/${f} — chay bootstrap truoc"
done

# --- 4. SUA — nguyen tu tung tep, va CHUAN HOA ve LF ----------------------
for f in "${TEP[@]}"; do
  p="${DICH_DIR}/${f}"
  grep -vE "^R2_(ACCOUNT_ID|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)=" "$p" \
    | tr -d '\r' > "$tmp.moi" || true
  tr -d '\r' < "$tmp" >> "$tmp.moi"
  chmod 0640 "$tmp.moi"
  chown "root:${NHOM}" "$tmp.moi" 2>/dev/null || true
  mv -f "$tmp.moi" "$p"
done

# --- 5. KIEM LAI — chi TEN bien (va ten bucket, khong phai bi mat) --------
sai=0
for f in "${TEP[@]}"; do
  for v in "${BIEN[@]}"; do
    grep -qE "^${v}=..*" "${DICH_DIR}/${f}" || { echo "  THIEU ${v} trong ${f}"; sai=1; }
  done
  b2="$(grep -E '^R2_BUCKET=' "${DICH_DIR}/${f}" | tail -1 | cut -d= -f2-)"
  [ "$b2" = "$bucket" ] || { echo "  ${f}: bucket sau khi ghi la '${b2}'"; sai=1; }
  grep -q $'\r' "${DICH_DIR}/${f}" && { echo "  ${f}: con CRLF"; sai=1; }
done
[ "$sai" -eq 0 ] || loi "kiem lai khong dat"

echo "PASS: 4/4 bien R2 co mat trong ${#TEP[@]} tep; bucket=${bucket} (staging)"
