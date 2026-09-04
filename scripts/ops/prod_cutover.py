#!/usr/bin/env python3
"""Dieu phoi cuoc chuyen worker PRODUCTION tu GCE sang AWS.

    python scripts/ops/prod_cutover.py <pha> [tuy chon]

PHA
    status      chi doc: do ca hai may + hang doi production
    prepare     stage ma dieu hanh + tep env len AWS (KHONG bat gi)
    drain       cho GCE xong job dang chay roi DUNG worker GCE
    canary      bat worker AWS + chay mot job DRAFT that
    observe     theo doi AWS trong mot cua so thoi gian
    commit      chot: ghi lai cau hinh cuoi cung
    rollback    bat lai GCE. CHAY DUOC DOC LAP, khong can pha nao truoc do.

NGUYEN TAC
  * `rollback` khong doc tep trang thai nao de biet phai lam gi — no suy ra
    tu chinh hai may. Mot pha truoc that bai giua chung khong lam mat kha
    nang lui.
  * Khong pha nao XOA gi cua GCE. `drain` chi `systemctl disable --now`.
    VM GCE khong bao gio bi terminate boi cong cu nay.
  * Bi mat production di tu Render -> stdin cua ssh -> tep stage 0620 tren
    may dich -> root doc, kiem, dat vao /etc. Khong bao gio qua argv, khong
    bao gio ra stdout, khong bao gio xuong dia may dieu hanh.
  * Nhat ky kiem toan: JSONL, chi ten va ket qua, khong bao gio gia tri.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))
sys.path.insert(0, str(GOC / "scripts"))

from scripts.ops.cutover_target import (  # noqa: E402
    PROD_UNITS,
    REQUIRED_ENV_NAMES,
    STAGING_UNITS,
    CutoverRefused,
    khang_dinh_production,
    render_env_text,
    tom_tat_env,
)

# --- toa do may -------------------------------------------------------------
AWS_HOST = os.environ.get("FANFIC_AWS_HOST", "13.212.224.218")
AWS_USER = os.environ.get("FANFIC_AWS_USER", "ubuntu")
AWS_KEY = os.environ.get("FANFIC_AWS_KEY",
                         str(Path.home() / ".ssh" / "fanficappwrrite.pem"))
GCE_TEN = "fanfic-worker-prod"
GCE_ZONE = "asia-southeast1-b"

#: Unit production TREN GCE. Trung ten voi `PROD_UNITS` — day la chu y:
#: cung mot vai tro, hai may. Chi mot trong hai duoc chay.
GCE_UNITS = PROD_UNITS

NHAT_KY = GOC / "docs" / "reports" / "cutover-audit.jsonl"


def _luc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ghi_audit(su_kien: str, **chi_tiet: Any) -> None:
    """JSONL, chi ten + ket qua. KHONG BAO GIO gia tri bi mat."""
    ban_ghi = {"luc": _luc(), "su_kien": su_kien}
    ban_ghi.update(chi_tiet)
    try:
        NHAT_KY.parent.mkdir(parents=True, exist_ok=True)
        with NHAT_KY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ban_ghi, ensure_ascii=False) + "\n")
    except OSError:
        pass
    print(f"  [audit] {su_kien} " +
          " ".join(f"{k}={v}" for k, v in chi_tiet.items() if k != "luc"))


# --- chay lenh tu xa --------------------------------------------------------

def phan_giai(ten: str) -> str:
    """Duong dan THAT cua mot CLI, giai truoc khi goi.

    Tren Windows `gcloud` la `gcloud.cmd`, va `subprocess.run` khong dung
    shell nen khong tu do duoi theo `PATHEXT` -> `FileNotFoundError:
    [WinError 2]`. Da mac dung loi nay mot lan trong duong ong sao luu
    Appwrite (xem `docs/AWS_STAGING_MIGRATION.md`, muc "Loi da sua trong
    chinh duong ong"); day la cung mot bay.
    """
    import shutil

    return shutil.which(ten) or ten


def _chay(dong: List[str], nhap: Optional[bytes] = None,
          han: int = 300) -> Tuple[int, str, str]:
    dong = [phan_giai(dong[0])] + list(dong[1:])
    p = subprocess.run(dong, input=nhap, capture_output=True, timeout=han)
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def aws(lenh: str, nhap: Optional[bytes] = None, han: int = 300) -> Tuple[int, str, str]:
    """Chay mot lenh tren may AWS bang SSH khoa rieng."""
    return _chay(["ssh", "-i", AWS_KEY, "-o", "BatchMode=yes",
                  "-o", "ConnectTimeout=15",
                  "-o", "StrictHostKeyChecking=accept-new",
                  f"{AWS_USER}@{AWS_HOST}", lenh], nhap=nhap, han=han)


def gce(lenh: str, han: int = 300) -> Tuple[int, str, str]:
    """Chay mot lenh tren may GCE production."""
    return _chay(["gcloud", "compute", "ssh", GCE_TEN, f"--zone={GCE_ZONE}",
                  f"--command={lenh}"], han=han)


def cong(verb: str, han: int = 900) -> Tuple[int, str]:
    """Goi cong dieu hanh HEP tren AWS qua hang doi yeu cau.

    Ben khong-dac-quyen chi GHI mot dong verb; root doc, doi chieu
    allowlist, chay ham da viet san. Khong co shell tuy y o day.
    """
    ma = f"{int(time.time() * 1000)}-{os.getpid()}"
    rc, _, err = aws(f"printf %s {shlex.quote(verb)} "
                     f"> /var/lib/fanfic-prod-admin/req/{ma}.req")
    if rc != 0:
        return rc, f"khong ghi duoc yeu cau: {err.strip()}"
    het = time.time() + han
    while time.time() < het:
        rc, out, _ = aws(f"cat /var/lib/fanfic-prod-admin/res/{ma}.out 2>/dev/null")
        if rc == 0 and out.strip():
            ma_thoat = 0
            for d in out.splitlines():
                if d.startswith("# exit="):
                    try:
                        ma_thoat = int(d.split("=", 1)[1])
                    except ValueError:
                        ma_thoat = 1
            return ma_thoat, out
        time.sleep(3)
    return 124, f"het gio cho verb {verb!r}"


# --- credential -------------------------------------------------------------

def lay_env_production() -> Dict[str, str]:
    """Keo bo bien worker production tu Render. Khong in, khong ghi dia."""
    import fanfic_credential_broker as broker
    import recover_worker_env_production as rec

    key = broker.fetch("RENDER_API_KEY")
    if not key:
        raise CutoverRefused(
            "RENDER_API_KEY khong co trong Windows Credential Manager")
    svc = broker.render_resolve_service(key)
    sid = svc.get("id") or (svc.get("service") or {}).get("id")
    if not sid:
        raise CutoverRefused("khong phan giai duoc service id cua fas-prod-api")
    tat_ca = rec.fetch_all_env(key, sid)
    env = {k: tat_ca.get(k, "") for k in REQUIRED_ENV_NAMES}
    khang_dinh_production(env)          # fail closed truoc khi di dau ca
    return env


# --- do trang thai ----------------------------------------------------------

def _units_gce() -> Dict[str, str]:
    rc, out, _ = gce("systemctl is-active " + " ".join(GCE_UNITS) + " 2>&1; "
                     "echo '---'; systemctl is-enabled " + " ".join(GCE_UNITS) + " 2>&1")
    if rc != 0:
        return {u: "?" for u in GCE_UNITS}
    phan = out.split("---")
    hoat = [d.strip() for d in phan[0].strip().splitlines() if d.strip()]
    return {u: (hoat[i] if i < len(hoat) else "?") for i, u in enumerate(GCE_UNITS)}


def _units_aws() -> Dict[str, str]:
    tat = list(PROD_UNITS) + list(STAGING_UNITS)
    rc, out, _ = aws("for u in " + " ".join(tat) +
                     "; do printf '%s %s\\n' \"$u\" \"$(systemctl is-active $u 2>/dev/null)\"; done")
    ra: Dict[str, str] = {}
    for d in out.splitlines():
        p = d.split()
        if len(p) == 2:
            ra[p[0]] = p[1]
    return ra


def pha_status(a) -> int:
    print("=== GCE (production hien tai) ===")
    for u, tt in _units_gce().items():
        print(f"  {u:44} {tt}")
    rc, out, _ = gce("uptime -p; git -C /opt/fanfic-audio rev-parse --short HEAD 2>/dev/null")
    print("  " + " | ".join(d.strip() for d in out.splitlines() if d.strip()))

    print("\n=== AWS (dich den) ===")
    for u, tt in _units_aws().items():
        nhan = "PROD " if u in PROD_UNITS else "stg  "
        print(f"  {nhan}{u:44} {tt}")
    rc, out, _ = aws("uptime -p; git -C /opt/fanfic-audio rev-parse --short HEAD 2>/dev/null")
    print("  " + " | ".join(d.strip() for d in out.splitlines() if d.strip()))

    print("\n=== HANG DOI PRODUCTION (chi doc) ===")
    from scripts.ops import prod_probe
    prod_probe.nap_env_production()
    ban_do = prod_probe.do_hang_doi()
    print(f"  pending={ban_do['so_luong'].get('pending')}  "
          f"running={ban_do['so_luong'].get('running')}  "
          f"lease_treo={len(ban_do['lease_treo'])}  "
          f"an_toan_ban_giao={ban_do['an_toan_de_ban_giao']}")
    return 0


# --- PHA 1: PREPARE ---------------------------------------------------------

def pha_prepare(a) -> int:
    print("=== PREPARE ===")
    print("Khong bat dich vu nao trong pha nay. GCE khong bi cham.\n")

    # 1. stage ma dieu hanh (khong dac quyen, chi la tep trong /home)
    #
    # PHAI di TRUOC moi thu: trinh cai lay ma dac quyen tu day khi checkout
    # chua co no. Va checkout KHONG the duoc cap nhat tu ben khong-dac-quyen
    # — `/opt/fanfic-audio/.git` thuoc root (dung nhu vay), nen mot
    # `git fetch` chay bang `ubuntu` chi tra ve
    # `cannot open '.git/FETCH_HEAD': Permission denied`. Viec cap nhat
    # checkout thuoc verb `update`, chay bang root.
    print("1. stage ma dieu hanh len /home/ubuntu")
    for ten in ("fanfic_prod_admin.sh", "install_prod_admin.sh"):
        p = GOC / "scripts" / "ops" / ten
        rc, _, err = _chay(["scp", "-i", AWS_KEY, "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new",
                            str(p), f"{AWS_USER}@{AWS_HOST}:/home/{AWS_USER}/{ten}"])
        print(f"   {ten}: {'OK' if rc == 0 else 'LOI ' + err.strip()[:80]}")
        ghi_audit("prepare.stage", tep=ten, rc=rc)
        if rc != 0:
            return 2

    # 2. da co cong dieu hanh chua?
    rc, out, _ = aws("test -x /usr/local/sbin/fanfic-prod-admin && echo CO || echo CHUA")
    da_cai = "CO" in out
    print(f"2. cong dieu hanh production: {'DA CAI' if da_cai else 'CHUA CAI'}")
    if not da_cai:
        print("\n  ===================================================")
        print("  CAN DUNG MOT LENH CO QUYEN — chay tren may nay:")
        print(f"\n    ssh -i {AWS_KEY} {AWS_USER}@{AWS_HOST} "
              f"'sudo bash /home/{AWS_USER}/install_prod_admin.sh'")
        print("\n  Sau do chay lai: prod_cutover.py prepare")
        print("  ===================================================")
        ghi_audit("prepare.can_nguoi", buoc="install_prod_admin")
        return 10

    # 3. dua checkout ve origin/main — QUA verb `update` (root), vi
    # `/opt/fanfic-audio/.git` thuoc root.
    print("3. dua checkout AWS ve origin/main (verb `update`, chay bang root)")
    ma, out = cong("update", han=420)
    print("\n".join("   " + d for d in out.splitlines() if d.strip()))
    ghi_audit("prepare.update", exit=ma)
    if ma != 0:
        return 6
    rc, sha, _ = aws("git -C /opt/fanfic-audio rev-parse HEAD 2>/dev/null")
    print(f"   SHA hien tai = {sha.strip()}")
    ghi_audit("prepare.sha", sha=sha.strip()[:12])

    # 4. dat tep env production
    print("4. dat tep env production (bi mat khong qua argv, khong xuong dia)")
    env = lay_env_production()
    for d in tom_tat_env(env):
        print(f"   {d}")
    noi_dung = render_env_text(env).encode("utf-8")
    # stdin cua ssh -> tep stage 0620 (ubuntu ghi duoc, KHONG doc lai duoc).
    rc, _, err = aws("cat > /var/lib/fanfic-prod-admin/env.stage", nhap=noi_dung)
    if rc != 0:
        print(f"   LOI khi stage env: {err.strip()[:200]}")
        ghi_audit("prepare.env_stage", rc=rc)
        return 3
    ghi_audit("prepare.env_stage", rc=0, so_bien=len(env))

    ma, out = cong("install-env")
    print("\n".join("   " + d for d in out.splitlines()))
    ghi_audit("prepare.install_env", exit=ma)
    if ma != 0:
        return 4

    # 5. preflight
    print("\n5. preflight (khong tieu job that nao)")
    ma, out = cong("preflight", han=900)
    print("\n".join("   " + d for d in out.splitlines()))
    ghi_audit("prepare.preflight", exit=ma)
    if ma != 0:
        print("\nPREPARE_FAIL: preflight khong dat. GCE VAN DANG CHAY.")
        return 5

    print("\nPREPARE_PASS. GCE van dang chay; chua co gi chuyen giao.")
    return 0


# --- PHA 2: DRAIN -----------------------------------------------------------

def pha_drain(a) -> int:
    print("=== DRAIN GCE ===")
    from scripts.ops import prod_probe
    prod_probe.nap_env_production()

    print(f"1. cho hang doi rong (toi da {a.wait}s). KHONG giet job nao.")
    ban_do = prod_probe.cho_hang_doi_rong(a.wait)
    print(json.dumps({k: ban_do[k] for k in
                      ("so_luong", "lease_treo", "dat", "so_lan_do")},
                     ensure_ascii=False, indent=2))
    ghi_audit("drain.hang_doi", dat=ban_do.get("dat"),
              running=ban_do["so_luong"].get("running"),
              lease_treo=len(ban_do["lease_treo"]))
    if not ban_do.get("dat"):
        print("\nDRAIN_FAIL: van con job `running`. KHONG dung GCE.")
        return 2
    if ban_do["lease_treo"]:
        print("\nDRAIN_FAIL: co lease treo — xu ly truoc khi ban giao.")
        return 3

    # Moc ban giao: ghi TRUOC khi dung, de neu buoc sau hong van truy duoc.
    rc, out, _ = gce("date -u +%FT%TZ; uptime -p; "
                     "systemctl show fanfic-worker-prod.service -p ActiveEnterTimestamp")
    print("\n2. moc GCE cuoi cung truoc khi dung:")
    for d in out.splitlines():
        if d.strip():
            print(f"   {d.strip()}")
    ghi_audit("drain.moc_gce", moc=out.strip().replace("\n", " | ")[:300])

    if a.dry_run:
        print("\n--dry-run: KHONG dung GCE.")
        return 0

    print("\n3. dung + disable CHI ba unit worker production tren GCE")
    print("   (VM KHONG bi tat, KHONG bi xoa)")
    lenh = "; ".join(
        f"sudo systemctl disable --now {u}" for u in GCE_UNITS)
    rc, out, err = gce(lenh + " 2>&1; echo '--- sau khi dung ---'; "
                       "systemctl is-active " + " ".join(GCE_UNITS) + " 2>&1", han=420)
    print("\n".join("   " + d for d in (out + err).splitlines() if d.strip()))
    tt = _units_gce()
    con_song = [u for u, v in tt.items() if v == "active"]
    ghi_audit("drain.dung_gce", con_song=con_song)
    if con_song:
        print(f"\nDRAIN_FAIL: van con unit GCE dang chay: {con_song}")
        return 4
    print("\nDRAIN_PASS: GCE da ngung nhan job. VM van con nguyen.")
    return 0


# --- PHA 3: CANARY ----------------------------------------------------------

def pha_canary(a) -> int:
    print("=== CANARY AWS ===")

    print("0. rao chan: GCE phai da dung (khong hai worker cung claim)")
    tt = _units_gce()
    con_song = [u for u, v in tt.items() if v == "active"]
    if con_song and not a.allow_both:
        print(f"   TU CHOI: GCE con chay {con_song}. Chay `drain` truoc.")
        ghi_audit("canary.tu_choi", ly_do="gce_con_chay", units=con_song)
        return 2
    print("   GCE: da dung")

    print("\n1. tat unit staging tren AWS")
    ma, out = cong("stop-staging")
    print("\n".join("   " + d for d in out.splitlines()))
    ghi_audit("canary.stop_staging", exit=ma)

    print("\n2. bat worker production tren AWS")
    ma, out = cong("start", han=600)
    print("\n".join("   " + d for d in out.splitlines()))
    ghi_audit("canary.start", exit=ma)
    if ma != 0:
        print("\nCANARY_FAIL: worker AWS khong len duoc.")
        return _tu_dong_rollback("worker AWS khong khoi dong duoc")

    print("\n3. job DRAFT that (khong bao gio thanh PUBLIC)")
    ma, out = cong("canary", han=900)
    print("\n".join("   " + d for d in out.splitlines()))
    ghi_audit("canary.job", exit=ma)
    if ma != 0:
        print("\nCANARY_FAIL: job canary khong dat.")
        return _tu_dong_rollback("job canary that bai")

    print("\nCANARY_PASS")
    return 0


def _tu_dong_rollback(ly_do: str) -> int:
    print(f"\n!!! TU DONG ROLLBACK: {ly_do}")
    ghi_audit("rollback.tu_dong", ly_do=ly_do)
    ma = pha_rollback(argparse.Namespace(wait=0))
    return 20 if ma == 0 else 21


# --- PHA 4: OBSERVE ---------------------------------------------------------

def pha_observe(a) -> int:
    print(f"=== OBSERVE ({a.minutes} phut) ===")
    from scripts.ops import prod_probe
    prod_probe.nap_env_production()

    het = time.time() + a.minutes * 60
    mau: List[Dict[str, Any]] = []
    khoi_dong_lai_dau = None
    while time.time() < het:
        rc, out, _ = aws(
            "for u in " + " ".join(PROD_UNITS) + "; do "
            "printf '%s=%s ' \"$u\" \"$(systemctl is-active $u 2>/dev/null)\"; done; echo; "
            "systemctl show fanfic-worker-prod.service -p NRestarts --value; "
            "cat /proc/loadavg | cut -d' ' -f1; "
            "free -m | awk '/Mem:/{print $7}'; "
            "free -m | awk '/Swap:/{print $3}'; "
            "df -BG / | awk 'NR==2{print $5}'")
        d = [x.strip() for x in out.splitlines() if x.strip()]
        ban_do = prod_probe.do_hang_doi()
        m = {
            "luc": _luc(),
            "units": d[0] if d else "?",
            "nrestarts": d[1] if len(d) > 1 else "?",
            "load1": d[2] if len(d) > 2 else "?",
            "ram_con_mb": d[3] if len(d) > 3 else "?",
            "swap_dung_mb": d[4] if len(d) > 4 else "?",
            "disk": d[5] if len(d) > 5 else "?",
            "pending": ban_do["so_luong"].get("pending"),
            "running": ban_do["so_luong"].get("running"),
            "lease_treo": len(ban_do["lease_treo"]),
        }
        if khoi_dong_lai_dau is None:
            khoi_dong_lai_dau = m["nrestarts"]
        mau.append(m)
        print(f"  [{m['luc']}] {m['units']} nrestarts={m['nrestarts']} "
              f"load={m['load1']} ram_con={m['ram_con_mb']}MB "
              f"swap={m['swap_dung_mb']}MB disk={m['disk']} "
              f"pending={m['pending']} running={m['running']} "
              f"lease_treo={m['lease_treo']}")

        # Hoi quy nghiem trong -> rollback.
        if "fanfic-worker-prod.service=active" not in m["units"]:
            ghi_audit("observe.hoi_quy", ly_do="worker khong active", mau=m)
            print("\nOBSERVE_FAIL: worker AWS khong con active.")
            return _tu_dong_rollback("worker AWS ngung active trong cua so quan sat")
        if m["lease_treo"]:
            ghi_audit("observe.hoi_quy", ly_do="lease treo", mau=m)
            print("\nOBSERVE_FAIL: co lease treo.")
            return _tu_dong_rollback("lease treo trong cua so quan sat")
        if (khoi_dong_lai_dau or "0").isdigit() and str(m["nrestarts"]).isdigit():
            if int(m["nrestarts"]) > int(khoi_dong_lai_dau):
                ghi_audit("observe.hoi_quy", ly_do="worker restart", mau=m)
                print("\nOBSERVE_FAIL: worker da restart trong cua so quan sat.")
                return _tu_dong_rollback("worker AWS restart trong cua so quan sat")
        time.sleep(a.every)

    ghi_audit("observe.xong", so_mau=len(mau), phut=a.minutes)
    print(f"\nOBSERVE_PASS: {len(mau)} mau qua {a.minutes} phut, khong hoi quy.")
    return 0


# --- PHA 5: COMMIT ----------------------------------------------------------

def pha_commit(a) -> int:
    print("=== COMMIT ===")
    tt_gce = _units_gce()
    tt_aws = _units_aws()
    con_gce = [u for u, v in tt_gce.items() if v == "active"]
    if con_gce:
        print(f"TU CHOI commit: GCE con chay {con_gce} — se trung lap cong viec.")
        return 2
    thieu_aws = [u for u in PROD_UNITS if tt_aws.get(u) != "active"]
    if thieu_aws:
        print(f"TU CHOI commit: AWS thieu unit active: {thieu_aws}")
        return 3
    stg = [u for u in STAGING_UNITS if tt_aws.get(u) == "active"]
    if stg:
        print(f"TU CHOI commit: unit staging tren AWS con chay: {stg}")
        return 4

    rc, sha, _ = aws("git -C /opt/fanfic-audio rev-parse HEAD")
    from scripts.ops import prod_probe
    prod_probe.nap_env_production()
    ban_do = prod_probe.do_hang_doi()

    chot = {
        "luc": _luc(),
        "worker_hoat_dong": "AWS",
        "aws_host": AWS_HOST,
        "aws_sha": sha.strip(),
        "aws_units": {u: tt_aws.get(u) for u in PROD_UNITS},
        "gce_units": tt_gce,
        "gce_vm": "CON NGUYEN (chi dung dich vu)",
        "hang_doi": ban_do["so_luong"],
        "lease_treo": len(ban_do["lease_treo"]),
    }
    print(json.dumps(chot, ensure_ascii=False, indent=2))
    ghi_audit("commit", **{k: v for k, v in chot.items() if k != "luc"})
    print("\nCOMMIT_PASS. GCE giu nguyen lam duong lui — KHONG terminate.")
    return 0


# --- ROLLBACK (doc lap) -----------------------------------------------------

def pha_rollback(a) -> int:
    """Bat lai GCE. KHONG doc tep trang thai nao — suy ra tu chinh hai may."""
    print("=== ROLLBACK ===")
    ghi_audit("rollback.bat_dau")

    print("1. dung worker production tren AWS (neu dang chay)")
    rc, out, _ = aws("test -x /usr/local/sbin/fanfic-prod-admin && echo CO || echo CHUA")
    if "CO" in out:
        ma, o = cong("stop", han=600)
        print("\n".join("   " + d for d in o.splitlines()))
        ghi_audit("rollback.dung_aws", exit=ma)
    else:
        print("   (cong dieu hanh chua cai — bo qua)")

    print("\n2. bat lai worker production tren GCE")
    lenh = "; ".join(f"sudo systemctl enable --now {u}" for u in GCE_UNITS)
    rc, out, err = gce(lenh + " 2>&1; echo '--- sau khi bat ---'; "
                       "systemctl is-active " + " ".join(GCE_UNITS) + " 2>&1", han=420)
    print("\n".join("   " + d for d in (out + err).splitlines() if d.strip()))

    print("\n3. cho GCE khoe lai")
    time.sleep(15)
    tt = _units_gce()
    for u, v in tt.items():
        print(f"   {u:44} {v}")
    chet = [u for u, v in tt.items() if v != "active"]
    ghi_audit("rollback.ket_qua", chet=chet)
    if chet:
        print(f"\nROLLBACK_FAIL: GCE chua khoe: {chet}")
        return 2

    rc, out, _ = gce("journalctl -u fanfic-worker-prod-health.service -n 3 "
                     "--no-pager -o cat 2>/dev/null | tail -3")
    print("\n4. nhip GCE:")
    for d in out.splitlines():
        if d.strip():
            print(f"   {d.strip()}")

    print("\nROLLBACK_PASS: GCE dang phuc vu tro lai.")
    return 0


PHA = {
    "status": pha_status,
    "prepare": pha_prepare,
    "drain": pha_drain,
    "canary": pha_canary,
    "observe": pha_observe,
    "commit": pha_commit,
    "rollback": pha_rollback,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pha", choices=sorted(PHA))
    p.add_argument("--wait", type=int, default=900,
                   help="drain: giay toi da cho job dang chay xong")
    p.add_argument("--minutes", type=int, default=30, help="observe: so phut")
    p.add_argument("--every", type=int, default=60, help="observe: nhip lay mau (giay)")
    p.add_argument("--dry-run", action="store_true",
                   help="drain: do nhung KHONG dung GCE")
    p.add_argument("--allow-both", action="store_true",
                   help="canary: bo qua rao chan 'GCE phai da dung' (NGUY HIEM)")
    a = p.parse_args(argv)
    try:
        return PHA[a.pha](a)
    except CutoverRefused as exc:
        print(f"TU CHOI: {exc}", file=sys.stderr)
        ghi_audit("tu_choi", pha=a.pha, ly_do=str(exc)[:200])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
