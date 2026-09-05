#!/usr/bin/env bash
# Khoi phuc Appwrite tu ban trich xuat snapshot len mot may DIEN TAP.
#
# Chay TREN MAY DIEN TAP (EC2 dung-mot-lan), bang root:
#
#     sudo bash appwrite_rehearsal_restore.sh /duong/dan/toi/volumes
#
# BA RANH GIOI CUNG, kiem truoc khi lam bat cu viec gi:
#
#   1. TU CHOI chay neu hostname/IP la may production. Mot ban khoi phuc
#      chay nham tren production se ghi de du lieu that.
#   2. TRUNG HOA doi ngoai truoc khi dung stack. Ban khoi phuc la mot ban
#      sao ĐẦY ĐỦ cua production: no co dia chi email that, khoa SMTP that,
#      va se coi minh la `appwrite-dev.fanfic.world`. Neu bat len nguyen xi
#      no CO THE gui email that toi nguoi dung that va xin chung chi cho
#      ten mien that. Ca hai deu la su co san xuat do mot bai dien tap gay
#      ra. Nen: SMTP bi vo hieu, ACME bi tat, domain doi ve chinh may nay.
#   3. KHONG cham DNS, khong cham R2, khong cham production.
#
# VE REPLICA SET — da do that 2026-09-05, KHONG con la gia dinh.
# Thu muc du lieu mang theo `local.system.replset`, nhung thanh vien duoc
# dia chi hoa bang TEN CONTAINER (`appwrite-mongodb:27017`), khong phai ten
# may, nen cau hinh di chuyen duoc nguyen ven: tren EC2 dien tap mongod tu
# len PRIMARY ngay lan dau, khong can sua gi. Van phai KIEM (`isWritable
# Primary`) chu khong duoc tin: mot mongod ket o STARTUP van tra loi
# `listDatabases` binh thuong, nen phep kiem chi-doc se bao "dat" tren mot
# he khong ghi duoc.
set -uo pipefail

VOLDIR="${1:-}"
[ -n "$VOLDIR" ] || { echo "dung: $0 <thu-muc-chua-*.tar.gz>" >&2; exit 2; }
[ -d "$VOLDIR" ] || { echo "khong thay thu muc $VOLDIR" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "phai chay bang root" >&2; exit 2; }

log() { printf '\n=== %s ===\n' "$*"; }

# --- RANH GIOI 1: khong bao gio chay tren production --------------------------
log "BUOC 0 — chan nham may"
HN="$(hostname)"
echo "hostname: $HN"
case "$HN" in
  fanfic-appwrite-temp|fanfic-worker-prod|*appwrite-dev*)
    echo "DAY LA MAY PRODUCTION — DUNG" >&2; exit 9;;
esac
# Neu may nay dang phuc vu ten mien production thi cung dung.
if command -v curl >/dev/null 2>&1; then
  MYIP="$(curl -fsS -m 10 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
  echo "ip cong khai: ${MYIP:-<khong ro>}"
  if [ "$MYIP" = "35.225.209.115" ]; then
    echo "IP NAY LA PRODUCTION GCE — DUNG" >&2; exit 9
  fi
fi

# --- swap 4 GiB ---------------------------------------------------------------
log "BUOC 1 — swap 4 GiB"
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile
  mkswap /swapfile >/dev/null && swapon /swapfile
fi
swapon --show; free -m

# --- docker -------------------------------------------------------------------
log "BUOC 2 — docker"
if ! command -v docker >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq docker.io docker-compose-v2 >/dev/null
fi
docker --version; docker compose version | head -1

# --- nap volume ---------------------------------------------------------------
log "BUOC 3 — nap volume tu ban trich xuat"
shopt -s nullglob
for t in "$VOLDIR"/appwrite_*.tar.gz; do
  n="$(basename "$t" .tar.gz)"
  docker volume create "$n" >/dev/null
  # `_data` la noi docker dat noi dung volume; ban trich xuat da bo lop do.
  docker run --rm -v "$n":/data -v "$VOLDIR":/backup:ro alpine \
    sh -c "tar xzf /backup/$(basename "$t") -C /data" \
    && echo "  nap xong $n"
done
docker volume ls --format '{{.Name}}' | grep appwrite | sort

# --- RANH GIOI 2: trung hoa doi ngoai TRUOC khi dung stack --------------------
log "BUOC 4 — trung hoa doi ngoai (BAT BUOC truoc khi `up`)"
ENVF="$VOLDIR/../.env"
[ -f "$ENVF" ] || ENVF="$VOLDIR/.env"
if [ -f "$ENVF" ]; then
  cp -n "$ENVF" "$ENVF.goc"
  # Khong in gia tri nao ra man hinh — chi bao da doi khoa nao.
  for kv in \
      "_APP_SMTP_HOST=" "_APP_SMTP_PORT=" "_APP_SMTP_USERNAME=" \
      "_APP_SMTP_PASSWORD=" "_APP_SMTP_SECURE=" \
      "_APP_DOMAIN=localhost" "_APP_DOMAIN_TARGET=localhost" \
      "_APP_DOMAIN_FUNCTIONS=localhost" \
      "_APP_OPTIONS_FORCE_HTTPS=disabled" \
      "_APP_OPTIONS_ABUSE=disabled" ; do
    k="${kv%%=*}"
    if grep -q "^${k}=" "$ENVF"; then
      sed -i "s|^${k}=.*|${kv}|" "$ENVF"
    else
      printf '%s\n' "$kv" >> "$ENVF"
    fi
    echo "  da dat $k"
  done
else
  echo "  CANH BAO: khong thay .env — stack co the khong dung duoc" >&2
fi

# --- RANH GIOI 3 / sua replica set --------------------------------------------
log "BUOC 5 — go cau hinh replica set cu (mongod standalone)"
# Chay mongod KHONG co --replSet tren chinh volume da khoi phuc, xoa cau hinh
# replset cu, roi tat. Sau buoc nay node moi tu bau duoc thanh primary.
MONGO_IMG="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -i '^mongo' | head -1)"
[ -n "$MONGO_IMG" ] || MONGO_IMG="mongo:8"
echo "dung image: $MONGO_IMG"

docker run --rm -d --name mongo-fix \
  -v appwrite_appwrite-mongodb:/data/db "$MONGO_IMG" \
  mongod --dbpath /data/db --bind_ip 127.0.0.1 >/dev/null

for i in $(seq 1 60); do
  if docker exec mongo-fix mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' 2>/dev/null | grep -q 1; then
    break
  fi
  sleep 3
done

echo "--- co so du lieu doc duoc (bang chung journal replay thanh cong) ---"
docker exec mongo-fix mongosh --quiet --eval \
  'db.adminCommand({listDatabases:1}).databases.forEach(d => print(d.name, d.sizeOnDisk))' \
  || echo "  KHONG mo duoc kho — ban khoi phuc HONG"

# GHI LAI cau hinh cu TRUOC khi doi. Thanh vien replset o day rat co the la
# `mongodb:27017` — ten DICH VU trong docker-compose, khong phai ten may —
# nen no von da di chuyen duoc. In ra de biet chac thay vi doan.
echo "--- cau hinh replset dang co trong ban khoi phuc ---"
docker exec mongo-fix mongosh --quiet --eval \
  'const c = db.getSiblingDB("local").system.replset.findOne();
   if (!c) { print("(khong co cau hinh replset)"); }
   else { print("_id:", c._id);
          c.members.forEach(m => print("  member", m._id, m.host)); }' || true

docker stop mongo-fix >/dev/null 2>&1 || true

# DIEN TAP THAT 2026-09-05 DA BAC BO buoc "xoa cau hinh replset" o day.
#
# Ban truoc cua tep nay xoa `local.system.replset` roi khoi tao lai. Chay
# that cho thay dieu do vua THUA vua NGUY HIEM: thanh vien duoc dia chi hoa
# la `appwrite-mongodb:27017` — TEN CONTAINER trong docker-compose, khong
# phai ten may — nen cau hinh von da di chuyen duoc nguyen ven sang may
# khac. Do duoc tren EC2 dien tap:
#
#     isWritablePrimary = true  ngay o lan thu DAU TIEN
#     rs.status()       -> set: rs0, myState: 1, appwrite-mongodb:27017 PRIMARY
#
# Xoa cau hinh se vut di oplog config ma khong duoc gi, va neu quen
# `rs.initiate()` thi mongod ket o STARTUP: doc van duoc, GHI thi khong,
# trong khi moi phep kiem chi-doc van xanh.
#
# Nen: KIEM TRUOC. Chi can can thiep khi thanh vien duoc dia chi hoa bang
# ten may hoac IP cu the.

log "BUOC 5b — chi khoi tao lai replica set NEU can"
cat <<'HD'
Sau `docker compose up -d`, XAC NHAN truoc khi lam gi them:

    docker compose exec -T mongodb mongosh --quiet --eval       'print(db.hello().isWritablePrimary)'

  true  -> XONG. Cau hinh replset di chuyen duoc, khong dung toi gi nua.
  false -> chi khi do moi khoi tao lai, voi dung ten dich vu trong compose:

    docker compose exec -T mongodb mongosh --quiet --eval       'rs.initiate({_id:"rs0", members:[{_id:0, host:"appwrite-mongodb:27017"}]})'

GHI duoc moi la bang chung, khong phai doc duoc. Mot mongod ket o STARTUP
van tra loi `listDatabases` binh thuong.

HD

log "BUOC 6 — dung stack"
echo "Chay tu thu muc co docker-compose.yml:"
echo "    docker compose up -d"
echo
echo "Roi doi PHIEN BAN (khong phai chi doi cong 80):"
echo '    for i in $(seq 1 60); do curl -fsS localhost/v1/health/version && break; sleep 5; done'
echo
echo "Sau do doi soat muc UNG DUNG tu may dieu hanh:"
echo "    python -m scripts.ops.appwrite_restore_rehearsal verify --endpoint http://<ip>/v1"
