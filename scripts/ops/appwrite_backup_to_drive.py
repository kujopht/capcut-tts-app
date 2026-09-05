"""Dua ban backup Appwrite tu VM len kho lanh Google Drive, roi THU RESTORE
tu chinh ban tren Drive.

Chay tren may dieu hanh (khong phai tren VM), SAU khi nguoi van hanh da chay
mot lan:

    sudo bash scripts/ops/appwrite_backup_offvm.sh

Vi sao chia hai nua: thu muc Appwrite thuoc user khac va o mode 0750, con
thao tac backup can Docker — hai thu deu doi quyen tren VM. Con `rclone`
thi CHI co (va chi NEN co) tren may dieu hanh: dat credential Drive len mot
VM dang mo 80/443 ra Internet la mo rong be mat tan cong khong can thiet.

    python -m scripts.ops.appwrite_backup_to_drive --stamp 20260903T120000Z

CHI dung `rclone copy` va `rclone check` — dung lai
`scripts/rclone_archive_copy.py`, noi verb `copy` duoc HARDCODE. Khong
sync/move/delete/purge: kho lanh luon la ban sao THEM VAO, khong bao gio la
dong bo hai chieu.

PASS chi khi ban tren DRIVE thuc su giai nen lai duoc — khong phai khi
`rclone copy` tra exit 0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ops.appwrite_backup_verify import (  # noqa: E402
    NGUON_TAR_SONG,
    kiem_backup,
)
from scripts.rclone_archive_copy import rclone_copy, rclone_verify  # noqa: E402

#: Theo dung quy uoc `archive/<nhom>/...` da co tren Drive (animation-worker,
#: experiments, final, scraping). Ha tang di vao nhom rieng `infra`.
DRIVE_INFRA_REMOTE = "fanfic-gdrive:FanficWorld/archive/infra/appwrite-selfhost"

VM_NAME = "fanfic-appwrite-temp"
VM_ZONE = "us-central1-c"
VM_STAGING = "/var/tmp/fanfic-backup-offvm"


def sha256_file(p: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def phan_giai(ten: str) -> str:
    """Duong dan THUC cua mot cong cu CLI.

    Tren Windows `gcloud` la `gcloud.cmd`, va `subprocess.run` KHONG dung
    shell nen no khong tu tim duoi `.cmd`/`.bat` — goi bang ten tran se nem
    `FileNotFoundError: [WinError 2]`. Da do that o lan chay dau. `which`
    xu ly dung PATHEXT nen tra ve dung tep chay duoc.
    """
    p = shutil.which(ten)
    if p:
        return p
    for duoi in (".cmd", ".exe", ".bat"):
        p = shutil.which(ten + duoi)
        if p:
            return p
    return ten  # de subprocess bao loi ro rang thay vi im lang


def run(cmd: list[str], *, timeout: int = 1800) -> subprocess.CompletedProcess:
    cmd = [phan_giai(cmd[0])] + list(cmd[1:])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def buoc(n: str) -> None:
    print(f"\n{'=' * 70}\n  {n}\n{'=' * 70}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stamp", required=True,
                    help="dau thoi gian thu muc staging tren VM (UTC)")
    ap.add_argument("--work-dir", default="",
                    help="thu muc lam viec cuc bo (mac dinh: tam)")
    ap.add_argument("--skip-pull", action="store_true",
                    help="da co ban cuc bo roi, khong keo lai")
    args = ap.parse_args()

    work = Path(args.work_dir) if args.work_dir else Path(
        tempfile.mkdtemp(prefix="appwrite-offvm-"))
    work.mkdir(parents=True, exist_ok=True)
    local = work / args.stamp
    remote = f"{DRIVE_INFRA_REMOTE}/{args.stamp}"
    ket: dict = {"stamp": args.stamp, "remote": remote}

    buoc("BUOC 1 — KEO ban backup tu VM ve may dieu hanh")
    if not args.skip_pull:
        src = f"{VM_NAME}:{VM_STAGING}/{args.stamp}"
        p = run(["gcloud", "compute", "scp", "--recurse", f"--zone={VM_ZONE}",
                 src, str(work)], timeout=3600)
        if p.returncode != 0:
            print(f"LOI keo ve (exit {p.returncode}):\n{p.stderr[-1500:]}")
            print("\nNeu la 'Permission denied': nguoi van hanh chua chay")
            print("  sudo bash scripts/ops/appwrite_backup_offvm.sh")
            return 2
    if not local.is_dir():
        print(f"LOI: khong thay {local}")
        return 2
    tars = sorted(local.glob("*.tar.gz"))
    if not tars:
        print(f"LOI: khong thay .tar.gz nao trong {local}")
        return 2
    tar = tars[0]
    print(f"  tep    : {tar.name}")
    print(f"  size   : {tar.stat().st_size} byte")

    buoc("BUOC 2 — DOI SOAT SHA256 sau khi truyen (toan ven duong truyen)")
    sha_local = sha256_file(tar)
    sums = local / "SHA256SUMS"
    sha_vm = ""
    if sums.is_file():
        sha_vm = sums.read_text(encoding="utf-8").split()[0].strip()
    print(f"  sha256 tren VM   : {sha_vm or '(khong co SHA256SUMS)'}")
    print(f"  sha256 sau truyen: {sha_local}")
    khop = bool(sha_vm) and sha_vm == sha_local
    print(f"  -> {'KHOP' if khop else 'KHONG KHOP / khong doi soat duoc'}")
    if sha_vm and not khop:
        print("DUNG LAI: ban keo ve khac ban tren VM. Khong day len Drive.")
        return 3
    ket["sha256"] = sha_local
    ket["size_bytes"] = tar.stat().st_size

    man = local / "manifest.json"
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf-8"))
        print(f"  manifest: {len(m.get('noi_dung') or [])} tep ben trong")
        ket["so_tep_trong_manifest"] = len(m.get("noi_dung") or [])

    buoc("BUOC 3 — DAY len kho lanh Drive (chi `rclone copy --checksum`)")
    cp = rclone_copy(str(local), remote, rclone_bin=phan_giai("rclone"),
                     timeout=3600)
    print(f"  exit_code: {cp['exit_code']}")
    if cp["stderr_tail"].strip():
        print(f"  stderr   : {cp['stderr_tail'][-400:]}")
    if cp["exit_code"] != 0:
        print("DUNG LAI: day len that bai. Ban local VAN CON, khong xoa gi.")
        return 4

    buoc("BUOC 4 — DOI SOAT DOC LAP doi tuong tren Drive")
    vr = rclone_verify(str(local), remote, rclone_bin=phan_giai("rclone"),
                       timeout=900)
    print(f"  rclone check --one-way exit: {vr['check_exit_code']}")
    if vr["check_stderr_tail"].strip():
        print(f"    {vr['check_stderr_tail'][-300:]}")
    try:
        sz = json.loads(vr["size"] or "{}")
        print(f"  rclone size: {sz.get('count')} tep, {sz.get('bytes')} byte")
        ket["drive_count"] = sz.get("count")
        ket["drive_bytes"] = sz.get("bytes")
    except json.JSONDecodeError:
        pass
    if vr["check_exit_code"] != 0:
        print("DUNG LAI: doi soat Drive that bai.")
        return 5

    buoc("BUOC 5 — THU RESTORE *TU BAN TREN DRIVE* (khong dung ban local)")
    # Day la buoc quyet dinh PASS/FAIL: tai LAI tu Drive vao mot thu muc
    # HOAN TOAN MOI, roi giai nen. Doc lai ban local khong chung minh dieu gi
    # ve ban tren Drive.
    fresh = Path(tempfile.mkdtemp(prefix="restore-tu-drive-"))
    dl = run(["rclone", "copy", f"{remote}/{tar.name}", str(fresh),
              "--checksum"], timeout=3600)
    print(f"  tai ve lai tu Drive exit: {dl.returncode}")
    if dl.returncode != 0:
        print(f"    {dl.stderr[-400:]}")
        return 6
    lai = fresh / tar.name
    if not lai.is_file():
        print("LOI: khong tai lai duoc tep tu Drive")
        return 6
    sha_drive = sha256_file(lai)
    print(f"  sha256 ban tu Drive: {sha_drive}")
    print(f"  -> {'KHOP ban goc' if sha_drive == sha_local else 'KHONG KHOP'}")
    if sha_drive != sha_local:
        return 6

    print("\n  --- giai nen ban tu Drive ---")
    ra = fresh / "giai-nen"
    ra.mkdir()
    try:
        with tarfile.open(lai, "r:gz") as tf:
            ten = tf.getnames()
            tf.extractall(ra, filter="data")
    except Exception as exc:  # noqa: BLE001
        print(f"  LOI giai nen: {type(exc).__name__}: {exc}")
        return 7
    files = [p for p in ra.rglob("*") if p.is_file()]
    tong = sum(p.stat().st_size for p in files)
    print(f"  giai nen OK: {len(ten)} muc, {len(files)} tep, {tong} byte")
    ket["giai_nen_so_tep"] = len(files)
    ket["giai_nen_bytes"] = tong

    print("\n  --- doi soat tung tep voi manifest ---")
    lech: list[str] = []
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf-8"))
        theo_ten = {Path(e["tep"]).name: e for e in (m.get("noi_dung") or [])}
        for p in files:
            e = theo_ten.get(p.name)
            if not e:
                continue
            h = sha256_file(p)
            if h != e["sha256"]:
                lech.append(p.name)
        print(f"  doi soat {len(theo_ten)} muc trong manifest, lech: {len(lech)}")
        if lech:
            for n in lech[:5]:
                print(f"    LECH: {n}")
    else:
        print("  (khong co manifest de doi soat tung tep)")
    ket["so_tep_lech_sha"] = len(lech)

    print("\n  --- nhan dang cau truc da khoi phuc ---")
    nhan = {
        "mongo": any("mongo" in p.name.lower() or "mongo" in str(p.parent).lower()
                     for p in files),
        "mariadb": any("maria" in p.name.lower() or "mysql" in p.name.lower()
                       or "maria" in str(p.parent).lower() for p in files),
        "postgres": any("postgre" in p.name.lower() or "pg" == p.suffix.lstrip(".")
                        or "postgre" in str(p.parent).lower() for p in files),
        "redis": any("redis" in p.name.lower() or "redis" in str(p.parent).lower()
                     or p.name.endswith(".rdb") for p in files),
        "uploads/functions": any(
            k in str(p).lower() for p in files
            for k in ("uploads", "functions", "storage", "config", "cert")),
        "RESTORE.md": any(p.name.upper().startswith("RESTORE") for p in files),
    }
    for k, v in nhan.items():
        print(f"    {'CO   ' if v else 'khong'} {k}")
    ket["nhan_dang"] = nhan

    print("\n  --- doi soat NHAT QUAN ben trong tung volume ---")
    # VI SAO BUOC NAY TON TAI. Moi thu o tren chi chung minh ban sao khong
    # hong DUONG TRUYEN: tai lai duoc, sha256 khop, giai nen duoc. Mot ban
    # tar cua thu muc du lieu MongoDB dang chay khop sha256 hoan hao va van
    # co the khong mo lai duoc — `WiredTiger.turtle` bi ghi de giua chung
    # lan chep. Ban 20260903T163727Z chinh la truong hop do (journal moi hon
    # turtle 44 giay). Neu khong co cong nay, tep nay se bao PASS cho no.
    goc = next((d for d in [ra, *sorted(p for p in ra.iterdir() if p.is_dir())]
                if any(d.glob("*.tar.gz"))), None)
    nhat_quan = None
    if goc is None:
        print("  KHONG thay volume *.tar.gz nao de doi soat.")
        nhat_quan = {"ket_luan": "FAIL", "phat_hien": [], "kho_song": []}
    else:
        # Duong nay LUON la `tar` thu muc volume dang song — do chinh
        # `appwrite_backup_offvm.sh` tao ra. Anh chup khoi di duong khac.
        nhat_quan = kiem_backup(goc, NGUON_TAR_SONG)
        print(f"  kho song: {', '.join(nhat_quan['kho_song']) or '(khong ro)'}")
        for f in nhat_quan["phat_hien"]:
            print(f"    [{f['muc']:9}] {f['ma']}: {f['thong_diep']}")
        print(f"  nhat quan: {nhat_quan['ket_luan']}")
    ket["nhat_quan"] = nhat_quan

    ok = (dl.returncode == 0 and sha_drive == sha_local and not lech
          and len(files) > 0 and nhat_quan["ket_luan"] == "PASS")
    buoc(f"KET LUAN: {'PASS' if ok else 'FAIL'}")
    if ok:
        print("  Ban tren Drive TAI LAI duoc, SHA khop, giai nen duoc, tung")
        print("  tep khop manifest, VA ben trong tung volume nhat quan.")
        print("  Ban local VAN CON — chua xoa gi.")
        print("\n  CHUA chung minh: restore o muc CONTAINER (nap volume vao")
        print("  Appwrite dang chay). Do can Docker + compose tren mot VM")
        print("  dung-mot-lan, la mot nhiem vu rieng — KHONG chay tren VM")
        print("  dang phuc vu.")
    elif nhat_quan["ket_luan"] != "PASS":
        print("  Vo ngoai co the van dung, nhung BEN TRONG volume KHONG nhat")
        print("  quan — xem cac dong FAIL o tren. Ban nay KHONG duoc coi la")
        print("  co the khoi phuc, va KHONG duoc dung lam can cu cutover.")
    print(f"\n{json.dumps(ket, ensure_ascii=False, indent=2)}")
    try:
        shutil.rmtree(fresh, ignore_errors=True)
    except OSError:
        pass
    return 0 if ok else 8


if __name__ == "__main__":
    sys.exit(main())
