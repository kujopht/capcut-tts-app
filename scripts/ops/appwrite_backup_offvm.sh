#!/usr/bin/env bash
# Dua ban sao luu Appwrite tu-luu-tru RA KHOI chinh VM no bao ve.
#
# VAN DE DANG SUA: ban backup duy nhat dang nam tren cung mot dia voi thu no
# bao ve (`/home/robux/appwrite/backups/`). Mot su co dia lam mat CA HAI.
#
# VI SAO CAN MOT LENH CO QUYEN: thu muc Appwrite thuoc user `robux` va o mode
# 0750, con thao tac backup phai noi duoc voi Docker. Phien Claude chay bang
# user SSH rieng (`nguye`), KHONG o trong group `docker`, va guard cua kho
# (`.claude/hooks/guard_indirect_exec.py`) chan `sudo` nhu mot ranh gioi cung.
# Nen buoc DUY NHAT can nguoi van hanh la chay chinh tep nay mot lan:
#
#     sudo bash appwrite_backup_offvm.sh
#
# Sau do moi viec con lai (keo ve, day len Drive, doi soat doc lap, thu
# restore) chay tu dong tu may dieu hanh.
#
# VI SAO KHONG DAY TRUC TIEP TU VM LEN DRIVE: `rclone` KHONG duoc cai tren VM
# (da kiem), va cung KHONG NEN cai — lam vay se phai dat credential Drive len
# chinh may dang chay mot dich vu mo cong 80/443 ra Internet. Ban backup di
# VM -> may dieu hanh -> Drive, dung remote `fanfic-gdrive` da xac thuc san,
# theo dung nguyen tac "adapter khong giu credential" cua kho nay.
#
# KHONG XOA GI. Khong `docker compose down`, khong xoa ban backup cu, khong
# xoa ban local sau khi day len. Chi DOC va TAO THEM.
set -euo pipefail

APPWRITE_DIR="${APPWRITE_DIR:-/home/robux/appwrite}"
STAGING="${STAGING:-/var/tmp/fanfic-backup-offvm}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$STAGING/$STAMP"

echo "==================================================================="
echo "  BUOC 1 — KIEM KE ban backup hien co (chi doc)"
echo "==================================================================="
echo "thu muc Appwrite : $APPWRITE_DIR"
if [ ! -d "$APPWRITE_DIR" ]; then
  echo "LOI: khong thay $APPWRITE_DIR — dat APPWRITE_DIR=... roi chay lai." >&2
  exit 2
fi

echo
echo "--- cac ban backup dang co ---"
if [ -d "$APPWRITE_DIR/backups" ]; then
  ls -la "$APPWRITE_DIR/backups/" || true
  echo
  echo "--- kich co tung ban ---"
  du -sh "$APPWRITE_DIR/backups"/*/ 2>/dev/null || echo "  (chua co ban nao)"
  echo
  echo "--- noi dung tung ban ---"
  for d in "$APPWRITE_DIR/backups"/*/; do
    [ -d "$d" ] || continue
    echo "  == $d"
    ls -la "$d" | sed 's/^/     /'
  done
else
  echo "  (chua co thu muc backups/)"
fi

echo
echo "--- co script backup duoc phe chuan khong? ---"
ls -la "$APPWRITE_DIR/backup.sh" 2>/dev/null || echo "  KHONG thay backup.sh"

echo
echo "--- volume Docker cua Appwrite (day la thu THAT SU can bao ve) ---"
docker volume ls --format '{{.Name}}' 2>/dev/null | grep -i appwrite || \
  echo "  (khong liet ke duoc volume)"

echo
echo "--- trang thai container ---"
docker compose -f "$APPWRITE_DIR/docker-compose.yml" ps 2>/dev/null | head -20 || \
  docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null | head -20 || true

echo
echo "==================================================================="
echo "  BUOC 2 — TAO ban backup moi bang dung quy trinh da phe chuan"
echo "==================================================================="
mkdir -p "$OUT"

if [ -x "$APPWRITE_DIR/backup.sh" ]; then
  echo "dung $APPWRITE_DIR/backup.sh (quy trinh da phe chuan, khong viet lai)"
  ( cd "$APPWRITE_DIR" && ./backup.sh ) || {
    echo "LOI: backup.sh that bai — DUNG LAI, khong tu bay ra quy trinh khac." >&2
    exit 3
  }
  MOI="$(ls -1dt "$APPWRITE_DIR/backups"/*/ 2>/dev/null | head -1)"
  echo "ban moi nhat sau khi chay: $MOI"
else
  echo "KHONG co backup.sh. KHONG tu bay ra quy trinh backup moi." >&2
  echo "Bao lai cho nguoi van hanh — day la quyet dinh cua con nguoi," >&2
  echo "khong phai viec de script doan." >&2
  exit 4
fi

echo
echo "==================================================================="
echo "  BUOC 3 — DONG GOI + SHA256 + MANIFEST"
echo "==================================================================="
TAR="$OUT/appwrite-selfhost-$STAMP.tar.gz"
# `-C` de duong dan trong tar la tuong doi, khong nhet ca /home/robux vao.
tar -czf "$TAR" -C "$(dirname "$MOI")" "$(basename "$MOI")"
SIZE="$(stat -c %s "$TAR")"
SHA="$(sha256sum "$TAR" | awk '{print $1}')"

# Manifest liet ke TUNG tep ben trong, kem sha256 rieng — de sau nay doi soat
# duoc tung phan, khong chi mot con so tong.
{
  echo "{"
  echo "  \"tao_luc\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"nguon_vm\": \"$(hostname)\","
  echo "  \"nguon_duong_dan\": \"$MOI\","
  echo "  \"tar\": \"$(basename "$TAR")\","
  echo "  \"tar_sha256\": \"$SHA\","
  echo "  \"tar_size_bytes\": $SIZE,"
  echo "  \"appwrite_version_ghi_nhan\": \"1.9.6\","
  echo "  \"noi_dung\": ["
  first=1
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    h="$(sha256sum "$f" | awk '{print $1}')"
    s="$(stat -c %s "$f")"
    rel="${f#"$MOI"}"
    [ $first -eq 1 ] || echo ","
    first=0
    printf '    {"tep": "%s", "sha256": "%s", "size_bytes": %s}' "$rel" "$h" "$s"
  done < <(find "$MOI" -type f | sort)
  echo
  echo "  ]"
  echo "}"
} > "$OUT/manifest.json"

echo "$SHA  $(basename "$TAR")" > "$OUT/SHA256SUMS"

# De user SSH thuong (`nguye`) keo duoc ve — day la CA muc dich cua staging.
chmod -R a+rX "$STAGING"

echo "tar      : $TAR"
echo "size     : $SIZE byte"
echo "sha256   : $SHA"
echo "manifest : $OUT/manifest.json"
echo
echo "==================================================================="
echo "  XONG PHAN CAN QUYEN. Ban local VAN CON — khong xoa gi."
echo "  Buoc tiep theo chay tu may dieu hanh:"
echo "      python -m scripts.ops.appwrite_backup_to_drive --stamp $STAMP"
echo "==================================================================="
