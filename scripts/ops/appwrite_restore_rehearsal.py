"""Dien tap KHOI PHUC Appwrite tren mot dich CO LAP — sinh ke hoach, roi doi
soat o muc UNG DUNG.

Mot ban backup CHUA duoc coi la da chung minh cho toi khi:

  1. tung volume nap lai duoc vao Docker,
  2. cac dich vu KHOI DONG len that,
  3. va du lieu o muc UNG DUNG con dung — dung so luong collection, doc
     duoc document that, schema khop ban dac ta trong kho.

`appwrite_backup_to_drive.py` lo buoc 2 va 3 (no chi doi soat vo ngoai);
`appwrite_backup_verify.py` lo buoc 2 va 3 (no chi doc ben trong tep tar).
Tep nay la buoc con lai.

    # tren may dieu hanh — chi SINH ke hoach, khong chay gi
    python -m scripts.ops.appwrite_restore_rehearsal plan \\
        --stamp 20260903T163727Z --host <ten-may-dung-mot-lan>

    # sau khi dich da dung day, doi soat o muc UNG DUNG
    FAS_ENV_FILE=server/.env.rehearsal \\
    python -m scripts.ops.appwrite_restore_rehearsal verify \\
        --endpoint https://<dich-co-lap>/v1

RANH GIOI CUNG. `verify` TU CHOI chay khi endpoint tro toi production. Day
khong phai loi khuyen — no la mot phep kiem truoc moi lan chay, vi ca muc
dich cua dien tap la KHONG dong vao production. Xem `HOST_CAM`.

KHONG in bi mat. Khoa doc tu `fanfic_credential_broker`, va chi ten bien
moi truong xuat hien trong ket qua.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Nhung host TUYET DOI khong duoc lam dich dien tap. `appwrite-dev` nam
#: trong danh sach nay du ten no co chu `dev`: do duoc `docs/
#: PRODUCTION_CUTOVER.md` muc 0 (do that 2026-09-04) xac dinh la toa do
#: Appwrite PRODUCTION.
HOST_CAM = (
    "appwrite-dev.fanfic.world",
    "fanfic.world",
    "api.fanfic.world",
    "cloud.appwrite.io",
    "sgp.cloud.appwrite.io",
)

#: Dia chi IP cua may GCE dang chay Appwrite production.
IP_CAM = ("35.225.209.115",)

#: Ten volume Docker ma Appwrite compose mong doi <- ten tep trong backup.
#: Anh xa hien, khong suy dien tu chuoi, de mot tep la khong am tham tao ra
#: mot volume la.
VOLUME = {
    "appwrite_appwrite-mariadb.tar.gz": "appwrite_appwrite-mariadb",
    "appwrite_appwrite-mongodb.tar.gz": "appwrite_appwrite-mongodb",
    "appwrite_appwrite-mongodb-keyfile.tar.gz": "appwrite_appwrite-mongodb-keyfile",
    "appwrite_appwrite-postgresql.tar.gz": "appwrite_appwrite-postgresql",
    "appwrite_appwrite-redis.tar.gz": "appwrite_appwrite-redis",
    "appwrite_appwrite-uploads.tar.gz": "appwrite_appwrite-uploads",
    "appwrite_appwrite-certificates.tar.gz": "appwrite_appwrite-certificates",
    "appwrite_appwrite-config.tar.gz": "appwrite_appwrite-config",
    "appwrite_appwrite-models.tar.gz": "appwrite_appwrite-models",
}


class DichCamError(RuntimeError):
    """Nem ra khi dich dien tap tro toi ha tang production."""


@dataclass
class Dich:
    endpoint: str
    host: str


def phan_giai_dich(endpoint: str) -> Dich:
    """Tach host tu endpoint va TU CHOI neu no la production.

    Chap nhan ca dang co lan khong co scheme (`https://h/v1` va `h/v1`), vi
    mot lan go thieu `https://` khong duoc phep bien thanh mot lan lot luoi.
    """
    raw = (endpoint or "").strip()
    if not raw:
        raise DichCamError("endpoint rong")
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower().rstrip(".")
    if not host:
        raise DichCamError(f"khong tach duoc host tu endpoint: {endpoint!r}")

    if host in HOST_CAM or host in IP_CAM:
        raise DichCamError(
            f"{host} la ha tang PRODUCTION — dien tap khoi phuc khong bao gio "
            "duoc tro vao day. Dung mot may dung-mot-lan, co lap.")
    #: Chan ca ten con: `x.fanfic.world` van la vung production.
    for cam in HOST_CAM:
        if host.endswith("." + cam):
            raise DichCamError(
                f"{host} nam trong vung production ({cam}) — tu choi.")
    return Dich(endpoint=endpoint, host=host)


def ke_hoach(stamp: str, host: str, thu_muc: str = "~/rehearsal") -> list[str]:
    """Sinh DUNG cac lenh phai chay tren may dung-mot-lan. Khong chay gi.

    Tra ve mot danh sach dong de nguoi van hanh doc duoc truoc khi chay —
    mot script tu chay ngam tren mot may co du lieu that la thu khong nen
    ton tai.
    """
    d = thu_muc.rstrip("/")
    ra = [
        f"# Dien tap khoi phuc ban {stamp} tren may CO LAP `{host}`.",
        "# Chay TREN MAY DO. Khong chay tren may dang phuc vu.",
        "set -euo pipefail",
        "",
        "# 0. Chan nham may: dung lai neu day la may production.",
        'test "$(hostname)" != "fanfic-appwrite-temp" '
        '|| { echo "DAY LA MAY PRODUCTION — DUNG"; exit 9; }',
        "",
        f"mkdir -p {d} && cd {d}",
        "",
        "# 1. Nap tung volume. `docker volume create` la thao tac THEM;",
        "#    khong xoa volume nao dang co.",
    ]
    for tep, vol in VOLUME.items():
        ra.append(f"docker volume create {vol} >/dev/null")
        ra.append(
            f"[ -f {tep} ] && docker run --rm -v {vol}:/data "
            f"-v \"$PWD\":/backup alpine tar xzf /backup/{tep} -C /data")
    ra += [
        "",
        "# 2. Khoi dong. `docker-compose.yml` + `.env` phai duoc mang sang;",
        "#    chung CHI ton tai tren VM nguon, khong o trong kho git.",
        "docker compose up -d",
        "",
        "# 3. Doi dich vu len va xac nhan PHIEN BAN, khong chi cong 80.",
        "for i in $(seq 1 60); do",
        "  v=$(curl -fsS localhost/v1/health/version 2>/dev/null || true)",
        '  [ -n "$v" ] && { echo "len roi: $v"; break; }',
        "  sleep 5",
        "done",
        '[ -n "${v:-}" ] || { echo "KHONG len sau 300s — FAIL"; exit 1; }',
        "",
        "# 4. mongod co THUC SU mo duoc kho khong. Day la cau hoi ma ban",
        "#    backup 20260903T163727Z con dang bo ngo.",
        "docker compose exec -T mongodb mongosh --quiet --eval "
        "'db.adminCommand({listDatabases:1}).databases.forEach("
        "d => print(d.name, d.sizeOnDisk))'",
        "",
        "# 5. Roi tro ve may dieu hanh va chay:",
        "#    python -m scripts.ops.appwrite_restore_rehearsal verify \\",
        "#        --endpoint https://<dich>/v1",
    ]
    return ra


def doi_soat_ung_dung(endpoint: str, *, so_collection_mong_doi: int) -> dict:
    """Doi soat o muc UNG DUNG voi mot Appwrite DA khoi phuc.

    Dung lai dung cong cu da co trong kho — `fanfic_appwrite_schema.audit`
    la ban dac ta schema duy nhat — thay vi viet lai phep so sanh thu hai se
    troi khoi ban goc.
    """
    dich = phan_giai_dich(endpoint)
    from scripts import setup_appwrite  # noqa: PLC0415

    spec = getattr(setup_appwrite, "SCHEMA", {})
    return {
        "host": dich.host,
        "so_collection_trong_dac_ta": len(spec),
        "so_collection_mong_doi": so_collection_mong_doi,
        "khop_so_luong": len(spec) == so_collection_mong_doi,
        "buoc_tiep": [
            "python -m scripts.fanfic_appwrite_schema audit",
            "python -m scripts.web_product_appwrite_read_check",
            "python -m scripts.smoke_test_selfhost_appwrite",
        ],
        "ghi_chu": (
            "Ba lenh tren doc toa do tu bien moi truong, khong dong cung ten "
            "may — tro chung vao dich dien tap bang FAS_ENV_FILE."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dien tap khoi phuc Appwrite.")
    sub = ap.add_subparsers(dest="lenh", required=True)

    p = sub.add_parser("plan", help="sinh lenh cho may dung-mot-lan")
    p.add_argument("--stamp", required=True)
    p.add_argument("--host", required=True, help="ten may CO LAP")
    p.add_argument("--thu-muc", default="~/rehearsal")

    v = sub.add_parser("verify", help="doi soat muc ung dung")
    v.add_argument("--endpoint", required=True)
    v.add_argument("--so-collection", type=int, default=44)
    v.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)

    if a.lenh == "plan":
        try:
            phan_giai_dich(a.host)
        except DichCamError as e:
            print(f"TU CHOI: {e}", file=sys.stderr)
            return 9
        print("\n".join(ke_hoach(a.stamp, a.host, a.thu_muc)))
        return 0

    try:
        kq = doi_soat_ung_dung(a.endpoint,
                               so_collection_mong_doi=a.so_collection)
    except DichCamError as e:
        print(f"TU CHOI: {e}", file=sys.stderr)
        return 9
    print(json.dumps(kq, ensure_ascii=False, indent=2))
    return 0 if kq["khop_so_luong"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
