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

# Console Windows mac dinh la cp1252, con `systemd`/`journalctl` tren may
# dich tra ve tieng Viet co dau va cac ky tu nhu `—`, `→`. In thang se nem
# `UnicodeEncodeError`.
#
# Da xay ra THAT, va o dung cho toi te nhat: giua mot lan TU DONG ROLLBACK.
# Lenh bat lai GCE DA chay, nhung tien trinh chet ngay sau do khi in ket
# qua — nen ban ghi noi "dang lui" roi im, va khong ai biet lui xong hay
# chua. Mot loi HIEN THI khong bao gio duoc phep lam do mot duong khoi phuc.
for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def _in(*phan) -> None:
    """In mot dong, khong bao gio nem ngoai le.

    Dung cho MOI thu den tu may tu xa. Duong khoi phuc phai chay duoc ke ca
    khi console khong hien thi noi mot ky tu nao trong do.
    """
    van_ban = " ".join(str(p) for p in phan)
    try:
        print(van_ban)
    except (UnicodeEncodeError, OSError):
        try:
            print(van_ban.encode("ascii", "replace").decode("ascii"))
        except Exception:  # noqa: BLE001 — het cach thi im lang con hon chet
            pass


def _in_khoi(van_ban: str, thut: str = "   ") -> None:
    """In nhieu dong tu xa, an toan tung dong."""
    for d in (van_ban or "").splitlines():
        if d.strip():
            _in(thut + d.rstrip())

from scripts.ops.cutover_target import (  # noqa: E402
    PROD_UNITS,
    REQUIRED_ENV_NAMES,
    STAGING_UNITS,
    TRANSLATION_REQUIRED_ENV_NAMES,
    CutoverRefused,
    khang_dinh_production,
    khang_dinh_translation_production,
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

#: Nhat ky kiem toan — CO Y nam NGOAI cay lam viec cua git.
#:
#: Ban truoc de o `docs/reports/cutover-audit.jsonl`, tuc mot `git add -A`
#: se commit no. Hom nay no chi chua ten su kien va ma thoat, nhung mot
#: lan goi `ghi_audit` bat can trong tuong lai se ghim thu do vao lich su
#: kho vinh vien. No cung lo IP may, moc thoi gian dieu hanh va trang thai
#: unit cho bat ky ai doc duoc kho.
#:
#: Doi lai: nhat ky khong con di theo kho. Ban BEN nam trong
#: `/var/log/fanfic-prod-admin.log` tren chinh may AWS, do root giu.
NHAT_KY = Path(
    os.environ.get("FANFIC_CUTOVER_AUDIT")
    or (Path.home() / ".fanfic" / "cutover-audit.jsonl"))


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
            # DOI CHO DEN KHI CO DAU KET THUC. Mot ket qua khong co dong
            # `# exit=` la mot ket qua CHUA XONG (hoac bi cat), khong phai
            # mot ket qua thanh cong.
            #
            # Ban truoc tra ve ngay khi tep khac rong VA mac dinh
            # `ma_thoat = 0` khi thieu dau do. Hau qua that: doc trung phan
            # dau cua mot ban preflight dang chay, khong thay `# exit=`,
            # roi bao PREPARE_PASS cho mot preflight da FAIL. Fail-open o
            # dung cho khong duoc phep fail-open.
            dau = [d for d in out.splitlines() if d.startswith("# exit=")]
            if dau:
                try:
                    return int(dau[-1].split("=", 1)[1]), out
                except ValueError:
                    return 1, out
        time.sleep(3)
    # Het gio ma khong thay dau ket thuc -> THAT BAI, khong phai thanh cong.
    return 124, f"het gio cho verb {verb!r} (khong thay dong '# exit=')"


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


def lay_env_translation(env_tts: Dict[str, str]) -> Dict[str, str]:
    """Dung tep env cua WORKER DICH tu bo bien cua worker TTS.

    Khop dung ban dang chay tren GCE, do tu log khoi dong cua
    `fanfic-translation-worker-prod` (2026-08-24):

        storage: local · r2_configured: false · local_voices: ["piper:ngochuyen"]

    Worker dich sinh VAN BAN, khong sinh audio, nen no khong can — va
    khong duoc nhan — credential R2.
    """
    env = {
        "FAS_ENV": "production",
        "DATA_BACKEND": "appwrite",
        "STORAGE_BACKEND": "local",
        "FAS_INLINE_WORKER": "false",
        "FAS_TRANSLATION_INLINE_WORKER": "false",
        "APPWRITE_ENDPOINT": env_tts["APPWRITE_ENDPOINT"],
        "APPWRITE_PROJECT_ID": env_tts["APPWRITE_PROJECT_ID"],
        "APPWRITE_DATABASE_ID": env_tts["APPWRITE_DATABASE_ID"],
        "APPWRITE_API_KEY": env_tts["APPWRITE_API_KEY"],
        "FAS_LOCAL_VOICES": "piper:ngochuyen",
    }
    khang_dinh_translation_production(env)
    return env


# --- do trang thai ----------------------------------------------------------

#: Gia tri bao "khong biet". KHONG BAO GIO duoc coi la "da dung".
KHONG_RO = "?"


def _units_gce(so_lan: int = 3) -> Dict[str, str]:
    """Trang thai ba unit production tren GCE.

    Thu lai vai lan: SSH qua `gcloud` that bai chap chon la chuyen co that
    (da gap mot lan dung giua pha COMMIT). Van khong doc duoc thi tra
    `KHONG_RO` — va ben goi PHAI coi do la mot cau tra loi khong dat, chu
    khong phai "khong active".
    """
    # `; exit 0` KHONG phai de nuot loi — no de tach hai cau hoi khac nhau.
    #
    # `systemctl is-active` thoat KHAC 0 khi unit KHONG active, va `gcloud
    # compute ssh` truyen ma thoat cua lenh tu xa ra ngoai. Nen mot may GCE
    # da dung dung nhu mong doi lai lam `rc != 0`, va ban truoc doc do
    # thanh "khong lien lac duoc".
    #
    # Loi nay chi lo ra SAU khi GCE that su dung — tuc dung luc no gay hai
    # nhat: pha COMMIT tu choi vi tuong mat lien lac, trong khi that ra no
    # vua doc duoc dung cai trang thai no can.
    #
    # Ket luan "doc duoc hay khong" gio dua vao SO DONG dau ra, khong dua
    # vao ma thoat cua mot lenh ma ma thoat la MOT PHAN CAU TRA LOI.
    lenh = ("systemctl is-active " + " ".join(GCE_UNITS) + " 2>&1; "
            "echo '---'; "
            "systemctl is-enabled " + " ".join(GCE_UNITS) + " 2>&1; "
            "exit 0")
    for lan in range(so_lan):
        _rc, out, _err = gce(lenh)
        hoat = [d.strip() for d in out.split("---")[0].strip().splitlines()
                if d.strip()]
        # Chi nhung tu da biet moi duoc coi la mot cau tra loi.
        hop_le = {"active", "inactive", "failed", "activating", "deactivating",
                  "unknown", "reloading"}
        if len(hoat) >= len(GCE_UNITS) and all(
                h in hop_le for h in hoat[:len(GCE_UNITS)]):
            return {u: hoat[i] for i, u in enumerate(GCE_UNITS)}
        if lan < so_lan - 1:
            time.sleep(10)
    return {u: KHONG_RO for u in GCE_UNITS}


def _gce_chua_ro(tt: Dict[str, str]) -> List[str]:
    """Ten cac unit GCE ma ta KHONG doc duoc trang thai.

    Ton tai vi mot loi that: `_units_gce()` tra `?` khi SSH hong, va ca
    `canary` lan `commit` chi loc `== "active"` — nen mot may GCE KHONG
    LIEN LAC DUOC di lot qua cong y het mot may da dung. Do la fail-open o
    dung cai cong duoc dung de chung minh GCE khong con chay.
    """
    return [u for u, v in tt.items() if v == KHONG_RO]


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
        # Lenh nay chay trinh cai TU CHECKOUT (`/opt`, thuoc root), khong
        # tu `/home/ubuntu`. Ban truoc tro vao /home, va do la mot cua so
        # TOCTOU that: giua luc `scp` va luc nguoi van hanh go lenh,
        # `ubuntu` THAY DUOC tep do — nguoi van hanh se chay ma cua ke tan
        # cong bang root.
        print("\n  ===================================================")
        print("  CAN DUNG MOT LENH CO QUYEN — chay tren may nay:")
        print(f"\n    ssh -i {AWS_KEY} {AWS_USER}@{AWS_HOST} \\\n"
              "      'sudo git -C /opt/fanfic-audio fetch origin \\\n"
              "       && sudo git -C /opt/fanfic-audio reset --hard origin/main \\\n"
              "       && sudo bash /opt/fanfic-audio/scripts/ops/install_prod_admin.sh'")
        print("\n  Sau do chay lai: prod_cutover.py prepare")
        print("  ===================================================")
        ghi_audit("prepare.can_nguoi", buoc="install_prod_admin")
        return 10

    # 3. dua checkout ve origin/main — QUA verb `update` (root), vi
    # `/opt/fanfic-audio/.git` thuoc root.
    print("3. dua checkout AWS ve origin/main (verb `update`, chay bang root)")
    ma, out = cong("update", han=420)
    _in_khoi(out)
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
    _in_khoi(out)
    ghi_audit("prepare.install_env", exit=ma)
    if ma != 0:
        return 4

    # 4b. tep env RIENG cho worker dich.
    #
    # Thieu no, `fanfic-translation-worker-prod.service` chet voi "Failed to
    # load environment files" roi restart vo han — da xay ra that trong lan
    # canary dau tien. Hinh dang khac worker TTS: khong R2,
    # `STORAGE_BACKEND=local`, mot giong. Khop dung ban tren GCE.
    print("\n4b. dat tep env cho worker dich")
    env_tr = lay_env_translation(env)
    for d in tom_tat_env(env_tr, TRANSLATION_REQUIRED_ENV_NAMES):
        print(f"   {d}")
    rc, _, err = aws("cat > /var/lib/fanfic-prod-admin/env-translation.stage",
                     nhap=render_env_text(env_tr, TRANSLATION_REQUIRED_ENV_NAMES)
                     .encode("utf-8"))
    if rc != 0:
        print(f"   LOI khi stage env worker dich: {err.strip()[:200]}")
        ghi_audit("prepare.env_tr_stage", rc=rc)
        return 8
    ma, out = cong("install-translation-env")
    _in_khoi(out)
    ghi_audit("prepare.install_translation_env", exit=ma)
    if ma != 0:
        return 9

    # 5. tat unit STAGING cua may nay
    #
    # Phai lam TRUOC preflight: preflight tu choi chay khi con unit staging
    # song (rao chan chong "mot may claim job cua ca hai du an"). Truoc day
    # buoc nay nam trong `canary`, nen `prepare` khong bao gio qua duoc
    # preflight.
    #
    # An toan voi PRODUCTION: cac unit nay tro vao du an/bucket STAGING, nen
    # tat chung khong cham gi den hang doi production. GCE van dang phuc vu.
    print("\n5. tat unit staging cua may AWS (khong cham production)")
    ma, out = cong("stop-staging", han=420)
    _in_khoi(out)
    ghi_audit("prepare.stop_staging", exit=ma)
    if ma != 0:
        return 7

    # 6. preflight
    print("\n6. preflight (khong tieu job that nao)")
    ma, out = cong("preflight", han=900)
    _in_khoi(out)
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

    # DO LAI ngay truoc khi dung. Giua luc `cho_hang_doi_rong` tra ve va
    # luc SIGTERM toi, worker GCE VAN dang nhan job — va no dung `stop`
    # giua mot ban tong hop thi ban do bi bo lai (da xay ra that
    # 2026-09-03: core dump, 4 job bi bo). Phep do lai nay thu hep cua so
    # do xuong con mot lan goi mang; no khong dong duoc hoan toan, va
    # khong gia vo la dong duoc.
    print("\n3. do lai ngay truoc khi dung (thu hep cua so TOCTOU)")
    lai = prod_probe.do_hang_doi()
    print(f"   running={lai['so_luong'].get('running')} "
          f"pending={lai['so_luong'].get('pending')} "
          f"lease_treo={len(lai['lease_treo'])}")
    if lai["so_luong"].get("running", 0) or lai["lease_treo"]:
        print("\nDRAIN_FAIL: job moi xuat hien giua hai lan do. KHONG dung GCE.")
        ghi_audit("drain.toctou", running=lai["so_luong"].get("running"))
        return 5

    print("\n4. dung + disable CHI ba unit worker production tren GCE")
    print("   (VM KHONG bi tat, KHONG bi xoa)")
    lenh = "; ".join(
        f"sudo systemctl disable --now {u}" for u in GCE_UNITS)
    rc, out, err = gce(lenh + " 2>&1; echo '--- sau khi dung ---'; "
                       "systemctl is-active " + " ".join(GCE_UNITS) + " 2>&1", han=420)
    _in_khoi((out + err))
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
    chua_ro = _gce_chua_ro(tt)
    if chua_ro and not a.allow_both:
        print(f"   TU CHOI: KHONG doc duoc trang thai GCE {chua_ro}.")
        print("            Khong lien lac duoc KHONG dong nghia da dung.")
        ghi_audit("canary.tu_choi", ly_do="gce khong ro", units=chua_ro)
        return 6
    con_song = [u for u, v in tt.items() if v == "active"]
    if con_song and not a.allow_both:
        print(f"   TU CHOI: GCE con chay {con_song}. Chay `drain` truoc.")
        ghi_audit("canary.tu_choi", ly_do="gce_con_chay", units=con_song)
        return 2
    print("   GCE: da dung")

    print("\n1. tat unit staging tren AWS")
    ma, out = cong("stop-staging")
    _in_khoi(out)
    ghi_audit("canary.stop_staging", exit=ma)

    print("\n2. bat worker production tren AWS")
    ma, out = cong("start", han=600)
    _in_khoi(out)
    ghi_audit("canary.start", exit=ma)
    if ma != 0:
        print("\nCANARY_FAIL: worker AWS khong len duoc.")
        return _tu_dong_rollback("worker AWS khong khoi dong duoc")

    print("\n3. job DRAFT that (khong bao gio thanh PUBLIC)")
    ma, out = cong("canary", han=900)
    _in_khoi(out)
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

        # GCE co song lai khong? Mot dong doi khoi dong lai no bang tay,
        # mot chinh sach restart cua VM, hay mot lan reboot — bat ky cai
        # nao cung lam HAI worker cung claim mot hang doi, va cua so quan
        # sat mac dinh la 30 phut.
        tt_gce = _units_gce()
        gce_song = [u for u, v in tt_gce.items() if v == "active"]
        m["gce_song"] = gce_song
        if gce_song:
            ghi_audit("observe.hoi_quy", ly_do="GCE song lai", units=gce_song)
            print(f"\nOBSERVE_FAIL: GCE dang chay tro lai {gce_song} — "
                  "hai worker cung claim mot hang doi.")
            print("   Dung quan sat NGAY. Khong tu dong lui: lui la bat GCE, "
                  "ma GCE dang chay san. Can nguoi quyet dinh giu ben nao.")
            return 5

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
    chua_ro = _gce_chua_ro(tt_gce)
    if chua_ro:
        print(f"TU CHOI commit: KHONG doc duoc trang thai GCE {chua_ro}.")
        print("                Khong lien lac duoc KHONG dong nghia da dung —")
        print("                va cong nay ton tai de CHUNG MINH GCE khong chay.")
        ghi_audit("commit.tu_choi", ly_do="gce khong ro", units=chua_ro)
        return 7
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

    # --- job trung lap -----------------------------------------------------
    #
    # Hai worker cung claim mot hang doi se lo ra o day: `output_key` tat
    # dinh theo `content_hash`, nen hai lan chay KHONG tao hai object —
    # nhung chung tao hai JOB cho cung mot (chapter_id, content_hash). Do
    # la dau vet duy nhat con lai, nen day la cho phai nhin.
    from server.domain import JobStatus

    store = prod_probe._store()[0]
    xong = store.list_jobs_by_status(JobStatus.COMPLETED)
    dem: Dict[Tuple[str, str], int] = {}
    for j in xong:
        k = (j.chapter_id, j.content_hash)
        dem[k] = dem.get(k, 0) + 1
    trung = sorted((v, k) for k, v in dem.items() if v > 1)
    print(f"\n  job completed        : {len(xong)}")
    print(f"  cap (chuong, bam) trung: {len(trung)}")
    for v, k in trung[:5]:
        print(f"    {v} job cho chuong {k[0]}")

    # --- audio nguoi dung con lay duoc khong -------------------------------
    #
    # Doi may worker khong duoc dong toi duong DOC. Lay mau vai object that
    # dang phuc vu va xac nhan chung van `head` duoc.
    from server.adapters import build_storage

    kho = build_storage(prod_probe._store()[1])
    mau = 0
    lay_duoc = 0
    tong_obj = 0
    for o in kho.list_objects("audio/"):
        tong_obj += 1
        if mau < 5:
            mau += 1
            key = getattr(o, "key", None) or str(o)
            h = kho.head_probe(key) if hasattr(kho, "head_probe") else {}
            if h.get("tim_thay") and isinstance(h.get("content_length"), int) \
                    and h["content_length"] > 0:
                lay_duoc += 1
    print(f"  object duoi 'audio/' : {tong_obj}")
    print(f"  mau lay lai duoc     : {lay_duoc}/{mau}")

    if trung:
        print("\nTU CHOI commit: co job TRUNG LAP — dau hieu hai worker cung claim.")
        ghi_audit("commit.tu_choi", ly_do="job trung lap", so_cap=len(trung))
        return 5
    if mau and lay_duoc != mau:
        print("\nTU CHOI commit: audio nguoi dung khong lay lai duoc day du.")
        ghi_audit("commit.tu_choi", ly_do="audio khong lay duoc",
                  lay_duoc=lay_duoc, mau=mau)
        return 6

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
        _in_khoi(o)
        ghi_audit("rollback.dung_aws", exit=ma)
        # PHAI kiem: neu AWS khong dung duoc ma ta van bat GCE, hai ben
        # cung claim mot hang doi. Doc lai trang thai THAT thay vi tin ma
        # thoat cua verb.
        tt_aws = _units_aws()
        con_aws = [u for u in PROD_UNITS if tt_aws.get(u) == "active"]
        if con_aws:
            print(f"\nROLLBACK_FAIL: AWS VAN CON chay {con_aws} — "
                  "KHONG bat GCE (se trung lap cong viec).")
            print("   Xu ly AWS truoc, roi chay lai `rollback`.")
            ghi_audit("rollback.dung_aws_that_bai", con_aws=con_aws)
            return 3
        print("   AWS: da dung (da doc lai trang thai that)")
    else:
        # Cong chua cai => worker production chua bao gio duoc bat o day.
        # Van doc lai de chac chan, thay vi suy dien.
        tt_aws = _units_aws()
        con_aws = [u for u in PROD_UNITS if tt_aws.get(u) == "active"]
        if con_aws:
            print(f"\nROLLBACK_FAIL: cong chua cai nhung AWS dang chay {con_aws}.")
            ghi_audit("rollback.aws_chay_khong_cong", con_aws=con_aws)
            return 3
        print("   (cong dieu hanh chua cai; khong unit production nao active)")

    print("\n2. bat lai worker production tren GCE")
    lenh = "; ".join(f"sudo systemctl enable --now {u}" for u in GCE_UNITS)
    rc, out, err = gce(lenh + " 2>&1; echo '--- sau khi bat ---'; "
                       "systemctl is-active " + " ".join(GCE_UNITS) + " 2>&1", han=420)
    _in_khoi((out + err))

    # Doi lau hon MOT lan ngu 15 giay, va doc lai HAI lan cach nhau.
    #
    # Mot worker khoi dong duoc roi chet ngay (khong toi duoc Appwrite,
    # thieu model, env cu) van bao `active` trong vai giay dau. Mot lan
    # doc duy nhat ngay sau khi bat se bao ROLLBACK_PASS cho mot worker
    # sap chet.
    print("\n3. cho GCE khoe lai (doc hai lan, cach nhau)")
    time.sleep(20)
    tt1 = _units_gce()
    time.sleep(25)
    tt2 = _units_gce()
    for u in GCE_UNITS:
        print(f"   {u:44} {tt1.get(u)} -> {tt2.get(u)}")
    chet = [u for u in GCE_UNITS if tt2.get(u) != "active"]
    if chet:
        print(f"\nROLLBACK_FAIL: GCE chua khoe: {chet}")
        ghi_audit("rollback.ket_qua", chet=chet)
        return 2

    # NHIP, khong chi `is-active`. `--check` doc tep nhip ma vong quet ghi
    # moi chu ky; nhip moi la bang chung vong quet DANG QUAY, con
    # `is-active` chi la bang chung tien trinh con song. Da tung co su co
    # that: `active (running)` lien tuc trong khi vong quet dung han.
    rc, out, _ = gce(
        "sudo systemctl start fanfic-worker-prod-health.service 2>/dev/null; "
        "journalctl -u fanfic-worker-prod-health.service -n 5 "
        "--no-pager -o cat 2>/dev/null | tail -5", han=240)
    print("\n4. nhip GCE (bang chung vong quet dang quay):")
    nhip_moi = False
    for d in out.splitlines():
        if d.strip():
            print(f"   {d.strip()}")
        if '"trang_thai": "dang_chay"' in d:
            nhip_moi = True
    ghi_audit("rollback.ket_qua", chet=[], nhip_moi=nhip_moi)
    if not nhip_moi:
        print("\nROLLBACK_FAIL: unit `active` nhung KHONG doc duoc nhip moi.")
        print("   Khong bao cao 'da lui' khi chua chung minh GCE dang phuc vu.")
        return 4

    print("\nROLLBACK_PASS: GCE dang phuc vu tro lai (unit active + nhip moi).")
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
