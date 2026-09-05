"""Doi soat mot ban backup Appwrite tu-luu-tru CO THUC SU KHOI PHUC DUOC KHONG.

VAN DE DANG SUA. `appwrite_backup_to_drive.py` ket luan PASS khi ban tar tai
lai duoc tu Drive, sha256 khop manifest, va giai nen duoc. Ba dieu do chi
chung minh ban sao KHONG HONG DUONG TRUYEN. Chung KHONG chung minh ben trong
tung volume la mot trang thai co the mo lai.

Truong hop that, do duoc tren ban 20260903T163727Z:

    ./WiredTiger.turtle          mtime 23:36
    ./journal/WiredTigerLog...   mtime 23:37   <-- MOI HON turtle
    ./mongod.lock                2 byte        <-- mongod DANG CHAY

`tar` di qua thu muc du lieu trong nhieu phut. Trong khoang do WiredTiger tu
tao checkpoint moi va GHI DE `WiredTiger.turtle` + `WiredTiger.wt`. Ket qua
la mot ban RACH: tep metadata tro toi mot checkpoint ma cac trang du lieu cua
no da bi chep o trang thai TRUOC do. mongod se tu choi mo, hoac te hon, mo
len voi du lieu thieu.

Moi tep trong ban do deu khop sha256. Ban do van co the KHONG khoi phuc duoc.
Do la ly do tep nay ton tai: doc BEN TRONG tung volume, khong chi doi soat
vo ngoai.

    python -m scripts.ops.appwrite_backup_verify <thu_muc_backup_da_giai_nen>

Chi DOC. Khong giai nen ra dia, khong sua, khong xoa gi. Khong doc
`env.snapshot` va khong bao gio in noi dung tep nao.
"""
from __future__ import annotations

import argparse
import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

#: Muc do nghiem trong. `FAIL` chan PASS; `CANH_BAO` khong chan nhung phai
#: hien ra bao cao; `THONG_TIN` chi de doc hieu.
FAIL = "FAIL"
CANH_BAO = "CANH_BAO"
THONG_TIN = "THONG_TIN"

#: Tep dieu khien cua WiredTiger. `WiredTiger.turtle` la GOC: no ghi
#: checkpoint nao dang co hieu luc. Moi tep du lieu phai duoc chep TRUOC hoac
#: DONG THOI voi no.
WT_TURTLE = "WiredTiger.turtle"
WT_LOCK = "mongod.lock"

#: Thu muc tam / do do cua mongod. Noi dung o day KHONG phai du lieu nguoi
#: dung: `diagnostic.data` la chuoi do dem duoc ghi lien tuc va se LUON moi
#: hon turtle, nen tinh no vao phep so se bao dong gia moi lan.
WT_BO_QUA = ("_tmp/", "diagnostic.data/")


@dataclass
class Phat_hien:
    """Mot ket luan don le, co ma tra cuu duoc."""

    muc: str
    ma: str
    thong_diep: str

    def as_dict(self) -> dict:
        return {"muc": self.muc, "ma": self.ma, "thong_diep": self.thong_diep}


@dataclass
class Volume:
    """Nhung gi doc duoc tu MOT tep <ten_volume>.tar.gz, khong giai nen."""

    ten: str
    so_tep: int = 0
    tong_byte: int = 0
    mtime_max: int | None = None
    ten_tep: list[str] = field(default_factory=list)
    kich_co: dict[str, int] = field(default_factory=dict)
    mtime: dict[str, int] = field(default_factory=dict)

    @property
    def rong(self) -> bool:
        return self.so_tep == 0


def _chuan(ten: str) -> str:
    """Bo tien to `./` cua tar de so sanh ten on dinh."""
    t = ten
    while t.startswith("./"):
        t = t[2:]
    return t


def doc_volume(tar_path: Path) -> Volume:
    """Liet ke thanh vien cua mot tar.gz volume. KHONG ghi gi ra dia."""
    v = Volume(ten=Path(tar_path).name)
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf:
            if not m.isfile():
                continue
            ten = _chuan(m.name)
            v.so_tep += 1
            v.tong_byte += m.size
            v.ten_tep.append(ten)
            v.kich_co[ten] = m.size
            v.mtime[ten] = int(m.mtime)
            if v.mtime_max is None or int(m.mtime) > v.mtime_max:
                v.mtime_max = int(m.mtime)
    return v


def _bo_qua(ten: str) -> bool:
    return any(ten.startswith(p) for p in WT_BO_QUA)


def kiem_wiredtiger(v: Volume) -> list[Phat_hien]:
    """Cong quyet dinh: ban chep WiredTiger nay co the mo lai duoc khong?

    Ba cau hoi, moi cau mot bang chung doc lap:

    1. Co `WiredTiger.turtle` khong? Khong co -> khong phai datadir dung duoc.
    2. `mongod.lock` co rong khong? mongod GHI pid vao do khi chay va cat ve
       0 byte khi tat sach. Khac 0 -> da chep luc mongod DANG CHAY.
    3. Co tep du lieu nao MOI HON turtle khong? Co -> ban chep bi RACH:
       metadata da duoc chep truoc khi du lieu ngung doi.
    """
    ra: list[Phat_hien] = []

    if WT_TURTLE not in v.mtime:
        ra.append(Phat_hien(
            FAIL, "WT_KHONG_CO_TURTLE",
            f"{v.ten}: khong thay {WT_TURTLE} — day khong phai mot thu muc "
            "du lieu WiredTiger mo lai duoc."))
        return ra

    t_turtle = v.mtime[WT_TURTLE]

    if WT_LOCK not in v.kich_co:
        # Khong co bang chung mongod da dung han. `mongod.lock` luon ton tai
        # trong mot datadir that; thieu no nghia la ban chep khong day du
        # hoac da bi loc. Voi mot quyet dinh di tru, "khong chung minh duoc
        # la sach" phai chan, khong duoc mac dinh la sach.
        ra.append(Phat_hien(
            FAIL, "WT_KHONG_CO_LOCK",
            f"{v.ten}: khong thay {WT_LOCK} — khong xac nhan duoc mongod da "
            "dung han luc chep. Khong du can cu de coi ban nay la sach."))
    elif v.kich_co[WT_LOCK] > 0:
        ra.append(Phat_hien(
            FAIL, "WT_MONGOD_DANG_CHAY",
            f"{v.ten}: {WT_LOCK} dai {v.kich_co[WT_LOCK]} byte (khac rong) — "
            "mongod DANG CHAY luc chep. Mot ban tar cua datadir dang song "
            "khong bao dam mo lai duoc; can `mongodump`, `fsyncLock`, hoac "
            "anh chup dia o muc block."))

    xet = [(t, m) for t, m in v.mtime.items()
           if t != WT_TURTLE and not _bo_qua(t)]

    moi_hon = [(t, m) for t, m in xet if m > t_turtle]
    if moi_hon:
        moi_hon.sort(key=lambda x: -x[1])
        vd = ", ".join(f"{t} (+{m - t_turtle}s)" for t, m in moi_hon[:3])
        ra.append(Phat_hien(
            FAIL, "WT_SAO_CHEP_RACH",
            f"{v.ten}: {len(moi_hon)} tep MOI HON {WT_TURTLE} — vi du {vd}. "
            "Metadata checkpoint da bi chep truoc khi du lieu ngung doi, nen "
            "ban nay RACH chu khong chi 'crash-consistent'."))

    # DIEM MU CO THAT, ghi ra thay vi im lang. `tar` chi luu mtime tron
    # GIAY. Mot tep ghi 0,8 giay SAU turtle van mang dung con so giay do,
    # nen phep so `>` o tren khong thay. Ta khong the ket luan RACH tu du
    # lieu nay — nhung cung khong duoc ket luan SACH.
    cung_giay = [t for t, m in xet if m == t_turtle]
    if cung_giay:
        ra.append(Phat_hien(
            CANH_BAO, "WT_CUNG_GIAY",
            f"{v.ten}: {len(cung_giay)} tep co mtime TRUNG giay voi "
            f"{WT_TURTLE} (vi du {', '.join(sorted(cung_giay)[:3])}). `tar` "
            "chi luu do phan giai mot giay, nen khong loai tru duoc kha nang "
            f"chung duoc ghi sau turtle. Chi {WT_LOCK} rong moi la bang "
            "chung mongod da dung."))

    if not any(f.muc == FAIL for f in ra):
        ra.append(Phat_hien(
            THONG_TIN, "WT_ON_DINH",
            f"{v.ten}: {WT_TURTLE} moi bang hoac moi hon moi tep du lieu, va "
            f"{WT_LOCK} rong — ban chep nay nhat quan."))
    return ra


def kiem_mariadb(v: Volume) -> list[Phat_hien]:
    """MariaDB: dang chay luc chep chua, va co chua BANG nao that khong."""
    ra: list[Phat_hien] = []

    pid = sorted(t for t in v.ten_tep if t.endswith(".pid"))
    if pid:
        ra.append(Phat_hien(
            FAIL, "MARIADB_DANG_CHAY",
            f"{v.ten}: con {pid[0]} — mariadbd DANG CHAY luc chep."))

    #: `<db>/db.opt` chi khai bao charset. Bang that la `.ibd`/`.MAD`/`.frm`
    #: BEN TRONG thu muc do. Chi co db.opt = co so du lieu RONG.
    du_lieu = [t for t in v.ten_tep
               if t.startswith("appwrite/") and not t.endswith("db.opt")]
    if not du_lieu:
        ra.append(Phat_hien(
            THONG_TIN, "MARIADB_KHONG_CO_BANG",
            f"{v.ten}: co so du lieu `appwrite` khong chua bang nao — kho nay "
            "KHONG phai noi luu du lieu song."))
    return ra


#: Thu tu QUAN TRONG: `mongodb-keyfile` phai duoc thu truoc `mongodb`, neu
#: khong tep keyfile se bi nhan nham la kho du lieu MongoDB va bao thieu
#: `WiredTiger.turtle`.
_LOAI = ("mongodb-keyfile", "mongodb", "mariadb", "postgresql", "redis",
         "uploads", "certificates", "config", "models", "functions")


def phan_loai(ten_tep: str) -> str:
    """Tu ten tep volume suy ra loai kho. Khong doan tu duong dan tuyet doi."""
    t = ten_tep.lower()
    for k in _LOAI:
        if k in t:
            return k
    return "khac"


def kiem_backup(thu_muc: Path) -> dict:
    """Doc mot thu muc backup da giai nen, tra ve bao cao co PASS/FAIL."""
    thu_muc = Path(thu_muc)
    tars = sorted(p for p in thu_muc.glob("*.tar.gz") if p.is_file())
    if not tars:
        return {
            "thu_muc": str(thu_muc),
            "kho_song": [],
            "ket_luan": "FAIL",
            "phat_hien": [Phat_hien(
                FAIL, "KHONG_CO_VOLUME",
                f"{thu_muc}: khong thay tep <volume>.tar.gz nao.").as_dict()],
            "volume": {},
        }

    phat_hien: list[Phat_hien] = []
    bao_cao_volume: dict[str, dict] = {}
    kho_song: list[str] = []

    for p in tars:
        loai = phan_loai(p.name)
        v = doc_volume(p)
        bao_cao_volume[p.name] = {
            "loai": loai,
            "so_tep": v.so_tep,
            "tong_byte": v.tong_byte,
            "mtime_max": v.mtime_max,
            "rong": v.rong,
        }

        if v.rong:
            phat_hien.append(Phat_hien(
                CANH_BAO, "VOLUME_RONG",
                f"{p.name}: RONG (khong tep nao). Neu kho nay dang phai giu "
                "du lieu nguoi dung thi day la mat du lieu am tham."))
            continue

        if loai == "mongodb":
            phat_hien.extend(kiem_wiredtiger(v))
            kho_song.append("mongodb")
        elif loai == "mariadb":
            kq = kiem_mariadb(v)
            phat_hien.extend(kq)
            if not any(f.ma == "MARIADB_KHONG_CO_BANG" for f in kq):
                kho_song.append("mariadb")

    if not kho_song:
        phat_hien.append(Phat_hien(
            FAIL, "KHONG_XAC_DINH_DUOC_KHO_SONG",
            "Khong nhan ra kho du lieu nao dang giu du lieu song. Mot ban "
            "backup khong xac dinh duoc kho song thi khong doi soat duoc."))

    co_fail = any(f.muc == FAIL for f in phat_hien)
    return {
        "thu_muc": str(thu_muc),
        "kho_song": sorted(set(kho_song)),
        "ket_luan": "FAIL" if co_fail else "PASS",
        "phat_hien": [f.as_dict() for f in phat_hien],
        "volume": bao_cao_volume,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Doi soat ban backup Appwrite co khoi phuc duoc khong.")
    ap.add_argument("thu_muc", help="thu muc backup DA giai nen (chua *.tar.gz)")
    ap.add_argument("--json", action="store_true", help="chi in JSON")
    a = ap.parse_args(argv)

    kq = kiem_backup(Path(a.thu_muc))
    if a.json:
        print(json.dumps(kq, ensure_ascii=False, indent=2))
        return 0 if kq["ket_luan"] == "PASS" else 1

    print(f"thu muc : {kq['thu_muc']}")
    print(f"kho song: {', '.join(kq.get('kho_song') or []) or '(khong ro)'}")
    print()
    for f in kq["phat_hien"]:
        print(f"  [{f['muc']:9}] {f['ma']}")
        print(f"              {f['thong_diep']}")
    print()
    print(f"KET LUAN: {kq['ket_luan']}")
    if kq["ket_luan"] == "FAIL":
        print("  Ban backup nay CHUA duoc coi la khoi phuc duoc.")
    return 0 if kq["ket_luan"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
