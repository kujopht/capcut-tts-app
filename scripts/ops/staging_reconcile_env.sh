#!/usr/bin/env bash
# Dong bo CHINH SACH cau hinh giua cac tep env cua worker staging.
#
#     bash staging_reconcile_env.sh [--print-only]
#
# VAN DE DANG SUA (do that tren may AWS staging 2026-09-04):
#
#     ConfigError: STORAGE_BACKEND=r2 nhung thieu cau hinh. Can du bon bien:
#     R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
#         server/main.py:229 -> server/config.py:618
#
# Luc dau tuong la hai tep env lech nhau, vi quan sat thay
# `fanfic-worker.service = active` con translation thi `failed`. Doc log thi
# KHONG PHAI: CA HAI tep deu `STORAGE_BACKEND=r2`, va ca hai worker deu chet
# voi CUNG mot ConfigError. Lan "active" kia chi la mot cua so giua hai lan
# `Restart=always`, truoc khi cham `StartLimitBurst=5` va thanh
# `start-limit-hit`. Mot quan sat dung nhung khong o trang thai on dinh.
#
# GOC RE THAT: `worker_bootstrap.sh` co quy tac "KHONG ghi de neu tep da ton
# tai" — dung cho BI MAT, nhung no da bi ap cho CA TEP, ke ca cac khoa CHINH
# SACH khong-bi-mat. Hai tep duoc sinh luc 00:13 tu ban mau CU (khi mau con
# `STORAGE_BACKEND=r2`); ban mau sau do da doi sang `local`, nhung thay doi
# do KHONG BAO GIO toi duoc may vi tep da ton tai. Cang chay lai bootstrap
# cang tin la da dung.
#
# CACH SUA: tach hai loai khoa.
#
#   BI MAT   (APPWRITE_*, R2_*)  -> KHONG BAO GIO ghi de. Script nay khong
#                                   cham toi, khong doc gia tri, khong in.
#   CHINH SACH (duoi day)        -> LUON dong bo ve gia tri chu dinh, tren
#                                   MOI tep, moi lan chay.
#
# Nho vay hai tep khong the lech nhau mot cach im lang nua.
set -uo pipefail

DICH_DIR="${DICH_DIR:-/etc/fanfic-audio}"
NHOM="${NHOM:-fanfic}"
TEP=(worker.env translation-worker.env)

#: Khoa CHINH SACH — khong phai bi mat, nen in duoc va PHAI dong bo.
#: `STORAGE_BACKEND=local` la chu dinh cua ban nghiem thu AWS staging: no
#: KHONG doi mot bien R2 nao (`server/config.py` chi kiem R2 khi
#: `storage_backend == "r2"`). Doi gia tri o day = doi chinh sach, co y.
declare -A CHINH_SACH=(
  [FAS_ENV]="${FAS_ENV_MONG_MUON:-staging}"
  [DATA_BACKEND]="${DATA_BACKEND_MONG_MUON:-appwrite}"
  [STORAGE_BACKEND]="${STORAGE_BACKEND_MONG_MUON:-local}"
  [FAS_INLINE_WORKER]="${FAS_INLINE_WORKER_MONG_MUON:-false}"
)
KHOA=(FAS_ENV DATA_BACKEND STORAGE_BACKEND FAS_INLINE_WORKER)

chi_in=0
[ "${1:-}" = "--print-only" ] && chi_in=1

doc() {  # doc gia tri mot khoa chinh sach; rong neu khong co
  grep -E "^${2}=" "$1" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

echo "======================================================================"
echo "  TRUOC — chinh sach hien tai tung tep (khoa KHONG bi mat)"
echo "======================================================================"
lech=0
for f in "${TEP[@]}"; do
  p="${DICH_DIR}/${f}"
  if [ ! -f "$p" ]; then echo "  THIEU $p"; lech=1; continue; fi
  echo "  $f"
  for k in "${KHOA[@]}"; do
    printf '    %-20s %s\n' "$k" "$(doc "$p" "$k")"
  done
  # Bi mat: chi bao CO/KHONG, khong bao gio in gia tri.
  for k in APPWRITE_ENDPOINT APPWRITE_PROJECT_ID APPWRITE_DATABASE_ID APPWRITE_API_KEY; do
    if grep -qE "^${k}=..*" "$p"; then s="CO"; else s="THIEU"; fi
    printf '    %-20s %s\n' "$k" "$s"
  done
done

# Chi ro CHO NAO lech — day la cau tra loi cho "STORAGE_BACKEND=r2 vao tu dau".
echo
echo "  --- doi chieu giua hai tep ---"
for k in "${KHOA[@]}"; do
  a="$(doc "${DICH_DIR}/${TEP[0]}" "$k")"
  b="$(doc "${DICH_DIR}/${TEP[1]}" "$k")"
  if [ "$a" != "$b" ]; then
    echo "    LECH  $k: ${TEP[0]}='$a'  vs  ${TEP[1]}='$b'"
    lech=1
  fi
  if [ "$a" != "${CHINH_SACH[$k]}" ] || [ "$b" != "${CHINH_SACH[$k]}" ]; then
    echo "    SAI CHINH SACH $k: mong muon='${CHINH_SACH[$k]}'"
    lech=1
  fi
done
[ "$lech" -eq 0 ] && echo "    (khong lech)"

if [ "$chi_in" -eq 1 ]; then
  echo
  echo "  --print-only: khong sua gi."
  exit $([ "$lech" -eq 0 ] && echo 0 || echo 1)
fi

echo
echo "======================================================================"
echo "  DONG BO — chi khoa CHINH SACH, KHONG cham bi mat"
echo "======================================================================"
for f in "${TEP[@]}"; do
  p="${DICH_DIR}/${f}"
  [ -f "$p" ] || { echo "  bo qua $f (khong co)"; continue; }
  tmp="$(mktemp)"; chmod 600 "$tmp"
  # Bo moi dong chinh sach cu VA dong ghi chu do chinh script nay them o lan
  # truoc, giu NGUYEN VEN moi dong khac (ke ca bi mat). Bo ca dong ghi chu la
  # dieu kien de IDEMPOTENT: neu khong, moi lan chay lai se noi them mot khoi
  # ghi chu nua va tep cu phinh ra mai.
  grep -vE "^($(IFS='|'; echo "${KHOA[*]}"))=|^# --- chinh sach staging, dong bo boi" \
    "$p" > "$tmp"
  # Cat moi dong trong o CUOI tep truoc khi noi them, cung de idempotent.
  printf '%s\n' "$(cat "$tmp")" > "$tmp.trim" && mv -f "$tmp.trim" "$tmp"
  {
    echo ""
    echo "# --- chinh sach staging, dong bo boi staging_reconcile_env.sh ---"
    for k in "${KHOA[@]}"; do echo "${k}=${CHINH_SACH[$k]}"; done
  } >> "$tmp"
  chmod 0640 "$tmp"; chown "root:${NHOM}" "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$p"
  echo "  da dong bo $f"
done

echo
echo "======================================================================"
echo "  SAU — kiem lai"
echo "======================================================================"
sai=0
for f in "${TEP[@]}"; do
  p="${DICH_DIR}/${f}"
  [ -f "$p" ] || { sai=1; continue; }
  echo "  $f"
  for k in "${KHOA[@]}"; do
    v="$(doc "$p" "$k")"
    printf '    %-20s %s' "$k" "$v"
    if [ "$v" = "${CHINH_SACH[$k]}" ]; then echo ""; else echo "   <-- SAI"; sai=1; fi
  done
  # Bi mat phai con nguyen sau khi dong bo.
  for k in APPWRITE_ENDPOINT APPWRITE_PROJECT_ID APPWRITE_DATABASE_ID APPWRITE_API_KEY; do
    grep -qE "^${k}=..*" "$p" || { echo "    MAT $k sau khi dong bo"; sai=1; }
  done
done
echo
if [ "$sai" -eq 0 ]; then
  echo "  PASS: hai tep env dong nhat ve chinh sach, bi mat con nguyen."
  exit 0
fi
echo "  FAIL: van con sai lech."
exit 1
