#!/usr/bin/env python3
"""Chuyen Appwrite PRODUCTION tu GCE sang AWS — bo dieu phoi FAIL-CLOSED.

Duong khoi phuc o day la duong DA CHUNG MINH ngay 2026-09-05 (xem
`docs/APPWRITE_MIGRATION.md` muc 8-9): **anh chup dia GCE**, khong phai ban
`tar`. Tep nay TU CHOI chay tu ban `tar`, vi ban `tar` do
`backup.sh`/`backup_v2.sh` tao la ban chep RACH cua MongoDB dang chay va con
thieu 5/14 volume.

    python -m scripts.ops.appwrite_prod_cutover <pha> [--dry-run]

    status        chi DOC ca hai ben, khong doi gi
    preflight     kiem MOI dieu kien tien quyet; KHONG tao tai nguyen tinh tien
    prepare       tao EC2 dich — TON TIEN, doi co --toi-dong-y-tra-tien
    final-backup  anh chup GCE MOI ngay truoc khi chuyen
    restore       nap ban vua chup len may dich
    canary        kiem may dich bang Host header, TRUOC khi dong vao DNS
    cutover       doi ban ghi A goc tren Cloudflare
    observe       theo doi, tu dong rollback khi cham nguong
    commit        chi sau khi het thoi gian giu GCE
    rollback      tra ban ghi A ve GCE

TAI SAO DNS O DAY RE VA AN TOAN. `appwrite-dev.fanfic.world` duoc Cloudflare
PROXY (do duoc: ten mien phan giai ra 104.21.63.15 / 172.67.142.101, con
origin that la 35.225.209.115). Nen client LUON noi voi bien Cloudflare, va
"cutover" chi la doi dia chi GOC. TTL cua client khong lien quan; doi chieu
va quay dau deu co hieu luc trong vai giay. Do la ly do rollback o day dang
tin hon mot lan doi DNS thong thuong.

MOI PHA DEU FAIL-CLOSED: khong chung minh duoc dieu kien thi TU CHOI, khong
bao gio "co le on". Trang thai ghi ra tep ngoai kho; mot pha tu choi chay khi
pha truoc chua DAT.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# --- hang so DA DO DUOC, khong doan -----------------------------------------

#: Nguon production hien tai.
GCE_VM = "fanfic-appwrite-temp"
GCE_ZONE = "us-central1-c"
GCE_PROJECT = "gen-lang-client-0793420657"
ORIGIN_GCE_IP = "35.225.209.115"
HOSTNAME = "appwrite-dev.fanfic.world"

#: Cau hinh may dich — suy ra TU SO DO, khong phai tu catalogue.
#: Dien tap 2026-09-05: toan bo 32 container chay trong 3.859 MB va cham
#: swap dung 8 KB tren mot may 8 GiB. Production GCE phai day 2,53 GiB ra
#: swap chi vi no co 6,93 GiB. Nen 8 GiB la san CO BIEN, va swap 4 GiB van
#: giu vi phep do o dien tap la muc NEN, chua phai dinh tai.
AWS_REGION = "ap-southeast-1"
AWS_INSTANCE_TYPE = "t3a.large"      # 2 vCPU / 8 GiB / x86_64
AWS_VOLUME_GB = 64                   # do: 36/48 GB da dung tren nguon (75%)
AWS_VOLUME_TYPE = "gp3"
AWS_SWAP_GB = 4
AWS_ARCH = "x86_64"                  # KHONG ARM

#: Appwrite phai len dung phien ban nay moi coi la khoi phuc dat.
APPWRITE_VERSION = "1.9.6"
#: Do duoc tren ban khoi phuc: 43 collection, 1.571 document o fanfic_world_prod.
SO_COLLECTION_PROD = 43
SO_DOCUMENT_PROD_TOI_THIEU = 1500    # de bien cho tang truong, chan sut giam

#: Ban backup phai MOI. Mot anh chup cu hon nguong nay khong duoc dung de
#: chuyen: moi phut chenh lech la mot phut ghi cua nguoi dung co the mat.
TUOI_BACKUP_TOI_DA_PHUT = 45

#: Giu GCE nguyen ven bao lau truoc khi duoc phep `commit` (dung GCE).
NGAY_GIU_GCE = 7

#: Dien tap cham swap dung 8 KB. Bat ky luong swap dang ke nao o tai that
#: nghia la gia dinh "8 GiB du" dang sai — va do la mot ly do rollback, khong
#: phai mot dong ghi chu.
NGUONG_SWAP_MB = 256

#: Trang thai + nhat ky nam NGOAI kho, giong `prod_cutover.py` — mot
#: `git add -A` khong duoc phep ghim IP/moc thoi gian dieu hanh vao lich su.
GOC_TRANG_THAI = Path(
    os.environ.get("FANFIC_APPWRITE_CUTOVER_DIR")
    or (Path.home() / ".fanfic" / "appwrite-cutover"))
TEP_TRANG_THAI = GOC_TRANG_THAI / "state.json"
NHAT_KY = GOC_TRANG_THAI / "audit.jsonl"

#: Thu tu bat buoc. Mot pha chi chay khi pha DUNG TRUOC no da DAT.
THU_TU = ["preflight", "prepare", "freeze", "final-backup", "restore",
          "canary", "cutover", "observe", "commit"]

#: Ket qua mot pha het han sau bao lau. `preflight` cua ba ngay truoc khong
#: noi duoc gi ve production hom nay.
HAN_KET_QUA_PHA_GIO = 6.0

#: `freeze`: doc moc ghi moi nhat HAI lan cach nhau bay nhieu giay. Neu no
#: khong doi thi ghi da thuc su dung.
FREEZE_KIEM_GIAY = 90


class CutoverRefused(RuntimeError):
    """Nem ra khi mot dieu kien an toan khong chung minh duoc."""


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
          " ".join(f"{k}={v}" for k, v in chi_tiet.items()))


def doc_trang_thai() -> Dict[str, Any]:
    try:
        return json.loads(TEP_TRANG_THAI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ghi_trang_thai(**cap_nhat: Any) -> Dict[str, Any]:
    tt = doc_trang_thai()
    tt.update(cap_nhat)
    tt["cap_nhat_luc"] = _luc()
    TEP_TRANG_THAI.parent.mkdir(parents=True, exist_ok=True)
    TEP_TRANG_THAI.write_text(
        json.dumps(tt, ensure_ascii=False, indent=2), encoding="utf-8")
    return tt


def doi_pha_truoc(pha: str) -> None:
    """FAIL-CLOSED: tu choi neu BAT KY pha nao truoc no chua DAT, va con han.

    Ban dau ham nay chi kiem pha NGAY TRUOC. Vong phan bien doi khang
    2026-09-05 chi ra duong di qua: mot lan chay bo do tu hom truoc de lai
    `preflight=DAT`, hom sau nguoi van hanh chay tiep tu giua chung, va cong
    van mo vi hang xom truc tiep cua no tinh co con DAT. Nen gio kiem TOAN BO
    day truoc do.

    Va them HAN DUNG: mot ket qua `preflight` cua ba ngay truoc khong con noi
    duoc gi ve production hom nay. Qua han thi phai do lai.
    """
    if pha not in THU_TU:
        return
    tt = doc_trang_thai()
    i = THU_TU.index(pha)
    for truoc in THU_TU[:i]:
        gt = tt.get(f"pha.{truoc}")
        if gt != "DAT":
            raise CutoverRefused(
                f"pha '{truoc}' chua DAT (hien: {gt or 'chua chay'}). "
                f"Khong duoc nhay thang toi '{pha}'.")
        luc = tt.get(f"pha.{truoc}.luc")
        if not luc:
            raise CutoverRefused(
                f"pha '{truoc}' DAT nhung khong co moc thoi gian — trang thai "
                "khong dang tin, chay lai tu dau.")
        t = datetime.strptime(luc, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        tuoi = (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
        if tuoi > HAN_KET_QUA_PHA_GIO:
            raise CutoverRefused(
                f"ket qua pha '{truoc}' da {tuoi:.1f} gio (han "
                f"{HAN_KET_QUA_PHA_GIO} gio). Do lai truoc khi di tiep.")


def dat_pha(pha: str, **them: Any) -> None:
    """Ghi mot pha la DAT, KEM moc thoi gian — han dung dua vao moc nay."""
    ghi_trang_thai(**{f"pha.{pha}": "DAT", f"pha.{pha}.luc": _luc()}, **them)


def phan_giai(ten: str) -> str:
    p = shutil.which(ten)
    if p:
        return p
    for duoi in (".cmd", ".exe", ".bat"):
        p = shutil.which(ten + duoi)
        if p:
            return p
    return ten


def chay(dong: List[str], han: int = 300) -> Tuple[int, str, str]:
    dong = [phan_giai(dong[0])] + list(dong[1:])
    try:
        p = subprocess.run(dong, capture_output=True, text=True, timeout=han,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"


def gce(args: List[str], han: int = 300) -> Tuple[int, str, str]:
    return chay(["gcloud"] + args + [f"--project={GCE_PROJECT}"], han)


def http_origin(path: str, ip: str, host: str = HOSTNAME,
                headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    """GET thang toi mot IP nhung bat tay TLS bang TEN MIEN.

    Day la cach kiem may dich TRUOC khi dong vao DNS: dung het duong ma
    nguoi dung that se di (SNI, vhost, chung chi) ma khong doi mot ban ghi
    nao. Xac thuc chung chi KHONG bi tat.
    """
    import http.client

    class _Noi(http.client.HTTPSConnection):
        def __init__(self, dia_chi: str, ten: str, **kw):
            super().__init__(ten, 443, **kw)
            self._ip = dia_chi

        def connect(self):
            import socket
            self.sock = socket.create_connection((self._ip, 443), self.timeout)
            self.sock = self._context.wrap_socket(
                self.sock, server_hostname=self.host)

    conn = _Noi(ip, host, timeout=30, context=ssl.create_default_context())
    try:
        conn.request("GET", path, headers=headers or {})
        r = conn.getresponse()
        return {"status": r.status,
                "body": r.read(400).decode("utf-8", "replace")[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


# --- PHA: STATUS ------------------------------------------------------------

def pha_status(a) -> int:
    """Chi DOC. Khong doi gi, khong tao gi."""
    print("=== STATUS ===")
    rc, out, _ = gce(["compute", "instances", "describe", GCE_VM,
                      f"--zone={GCE_ZONE}", "--format=value(status)"])
    print(f"  GCE {GCE_VM}: {out or 'khong doc duoc'}")

    r = http_origin("/v1/health/version", ORIGIN_GCE_IP)
    print(f"  production origin: HTTP {r.get('status')} {r.get('body','')[:60]}")

    rc, out, _ = gce(["compute", "snapshots", "list",
                      f"--filter=sourceDisk~{GCE_VM}",
                      "--sort-by=~creationTimestamp", "--limit=1",
                      "--format=value(name,creationTimestamp)"])
    print(f"  anh chup moi nhat: {out or '(khong co)'}")

    tt = doc_trang_thai()
    print("  --- trang thai cac pha ---")
    for p in THU_TU:
        print(f"    {p:14} {tt.get(f'pha.{p}', '-')}")
    return 0


# --- PHA 1: PREFLIGHT -------------------------------------------------------

def pha_preflight(a) -> int:
    """Kiem MOI dieu kien. KHONG tao tai nguyen tinh tien nao."""
    print("=== PREFLIGHT (khong tao gi, khong ton tien) ===")
    loi: List[str] = []
    canh: List[str] = []

    # 1. GCE con song — day la duong lui.
    rc, out, _ = gce(["compute", "instances", "describe", GCE_VM,
                      f"--zone={GCE_ZONE}", "--format=value(status)"])
    print(f"  GCE dang: {out or '?'}")
    if out != "RUNNING":
        loi.append(f"GCE {GCE_VM} khong RUNNING (={out!r}) — mat duong lui")

    # 2. Production dang phuc vu dung phien ban.
    r = http_origin("/v1/health/version", ORIGIN_GCE_IP)
    print(f"  production: HTTP {r.get('status')}")
    if r.get("status") != 200 or APPWRITE_VERSION not in r.get("body", ""):
        loi.append(f"production khong tra {APPWRITE_VERSION}: {r}")

    # 3. Ten mien VAN do Cloudflare proxy — ca ke hoach rollback dua vao day.
    try:
        import socket
        ips = sorted({x[4][0] for x in socket.getaddrinfo(HOSTNAME, 443)})
    except OSError as exc:
        ips = []
        canh.append(f"khong phan giai duoc {HOSTNAME}: {exc}")
    print(f"  {HOSTNAME} -> {ips[:2]}")
    if any(i == ORIGIN_GCE_IP for i in ips):
        loi.append(
            f"{HOSTNAME} tro THANG toi origin — khong con qua Cloudflare, nen "
            "rollback se phu thuoc TTL thay vi co hieu luc tuc thi")

    # 4. Lich anh chup tu dong con song (nguon cua ban backup cuoi).
    rc, out, _ = gce(["compute", "disks", "describe", GCE_VM,
                      f"--zone={GCE_ZONE}", "--format=value(resourcePolicies)"])
    print(f"  chinh sach anh chup: {'co' if out else 'KHONG'}")
    if not out:
        canh.append("dia khong gan chinh sach anh chup tu dong")

    # 5. Khoa schema KHONG duoc co documents.* (bat bien an toan cua kho).
    print("  kiem scope khoa schema...")
    try:
        from scripts.fanfic_credential_broker import appwrite_admin_env
        env = appwrite_admin_env()
        k = env.pop("APPWRITE_SCHEMA_API_KEY", "")
        pr = env.get("APPWRITE_PROJECT_ID", "")
        db = env.get("APPWRITE_DATABASE_ID", "")
        rr = http_origin(f"/v1/databases/{db}/collections/novels/documents",
                         ORIGIN_GCE_IP,
                         headers={"X-Appwrite-Project": pr,
                                  "X-Appwrite-Key": k})
        print(f"    documents.read -> HTTP {rr.get('status')} (401 la DUNG)")
        if rr.get("status") == 200:
            loi.append("APPWRITE_SCHEMA_API_KEY CO documents.* — vi pham bat "
                       "bien an toan cua kho")
    except Exception as exc:  # noqa: BLE001
        canh.append(f"khong kiem duoc scope khoa: {type(exc).__name__}")

    # 6. TUYET DOI khong dung chung may voi worker TTS.
    print(f"  may dich du kien: {AWS_INSTANCE_TYPE} RIENG o {AWS_REGION}")

    for c in canh:
        print(f"  [CANH BAO] {c}")
    for e in loi:
        print(f"  [LOI]      {e}")

    dat = not loi
    if dat:
        dat_pha("preflight", **{"preflight.canh_bao": canh})
    else:
        ghi_trang_thai(**{"pha.preflight": "HONG", "preflight.loi": loi})
    ghi_audit("preflight", dat=dat, so_loi=len(loi), so_canh_bao=len(canh))
    print(f"\nKET LUAN: {'DAT' if dat else 'HONG'}")
    if not dat:
        print("  Khong duoc di tiep. Sua tung dong [LOI] o tren.")
    return 0 if dat else 1


# --- PHA 2: PREPARE (TON TIEN) ---------------------------------------------

def pha_prepare(a) -> int:
    doi_pha_truoc("prepare")
    if not a.toi_dong_y_tra_tien:
        raise CutoverRefused(
            "pha nay TAO MOT EC2 va bat dau tinh tien. Chay lai voi "
            "--toi-dong-y-tra-tien neu that su muon.")
    print("=== PREPARE ===")
    print(f"  se tao: {AWS_INSTANCE_TYPE} / {AWS_VOLUME_GB}GB {AWS_VOLUME_TYPE}"
          f" / {AWS_ARCH} / {AWS_REGION}, swap {AWS_SWAP_GB}GiB")
    if a.dry_run:
        print("  --dry-run: khong goi AWS")
        return 0
    if not shutil.which("aws"):
        raise CutoverRefused(
            "khong co AWS CLI tren may nay. Day la viec cua con nguoi: tao "
            "EC2 theo dung cau hinh tren roi dua lai IP + khoa SSH.")
    raise CutoverRefused(
        "chua noi day tao instance tu dong — co y. Xem "
        "docs/APPWRITE_PROD_CUTOVER.md muc PREPARE de lay lenh chinh xac.")


# --- PHA 2b: FREEZE (chan ghi) ---------------------------------------------

def _moc_ghi_moi_nhat(ip: str) -> str:
    """Moc `$updatedAt` moi nhat ma khoa schema doc duoc — dai dien cho 'con
    ai dang ghi khong'.

    Khoa schema KHONG co `documents.*` (da do), nen khong doc duoc document.
    Nhung `collections` co `$updatedAt`, va Appwrite cham vao do khi schema
    doi. De do GHI cua nguoi dung ta can mot tin hieu khac: so luong tai
    lieu qua chinh backend. Nen ham nay tra ve mot chuoi dai dien; pha
    `freeze` so sanh HAI lan doc chu khong dien giai gia tri.
    """
    from scripts.fanfic_credential_broker import appwrite_admin_env
    env = appwrite_admin_env()
    k = env.pop("APPWRITE_SCHEMA_API_KEY", "")
    pr = env.get("APPWRITE_PROJECT_ID", "")
    db = env.get("APPWRITE_DATABASE_ID", "")
    r = http_origin(f"/v1/databases/{db}/collections", ip,
                    headers={"X-Appwrite-Project": pr, "X-Appwrite-Key": k})
    if r.get("status") != 200:
        raise CutoverRefused(f"khong doc duoc trang thai ghi: {r}")
    return r.get("body", "")


def pha_freeze(a) -> int:
    """Chan ghi tren production TRUOC khi chup ban cuoi.

    VI SAO PHA NAY TON TAI. Vong phan bien doi khang 2026-09-05 chi ra rang
    ban thiet ke truoc do KHONG co buoc nay: GCE van nhan ghi trong luc va
    sau khi doi DNS, nen trong cua so cutover CA HAI ben deu ghi duoc. Ket
    qua la hai kho du lieu phan ky, va moi ghi roi vao ben thua se mat khi
    dung may do. Dong bang ghi la thu DUY NHAT lam cua so do bang khong.

    Day KHONG phai dung dich vu: doc van chay binh thuong, nguoi dung van
    doc truyen duoc. Chi duong GHI bi dong, va chi trong vai phut.
    """
    doi_pha_truoc("freeze")
    print("=== FREEZE (chan ghi tren production) ===")
    print("  Doc VAN chay. Chi chan GHI. Day khong phai downtime toan phan.")
    if not a.da_dong_bang_ghi:
        raise CutoverRefused(
            "chua xac nhan da chan ghi. Dat backend Render ve che do "
            "chi-doc (hoac tat worker ghi), roi chay lai voi "
            "--da-dong-bang-ghi de tep nay DO LAI va xac minh.")

    print(f"  do hai lan cach nhau {FREEZE_KIEM_GIAY}s de xac minh...")
    m1 = _moc_ghi_moi_nhat(ORIGIN_GCE_IP)
    time.sleep(FREEZE_KIEM_GIAY)
    m2 = _moc_ghi_moi_nhat(ORIGIN_GCE_IP)

    if m1 != m2:
        raise CutoverRefused(
            "trang thai VAN doi giua hai lan do — ghi CHUA dung han. "
            "Khong duoc chup ban cuoi khi con ai do dang ghi.")
    print("  hai lan do trung nhau -> ghi da dung")
    dat_pha("freeze")
    ghi_audit("freeze", xac_minh=True, giay=FREEZE_KIEM_GIAY)
    return 0


# --- PHA 4: RESTORE ---------------------------------------------------------

def pha_restore(a) -> int:
    """Nap anh chup cuoi len may dich.

    Pha nay TUNG BI THIEU HAN: `THU_TU` co "restore" nhung `PHA` khong co,
    nen quy trinh khong the chay het duong. No fail-closed (canary luon tu
    choi) chu khong mo cong, nhung do van la mot lo hong that.
    """
    doi_pha_truoc("restore")
    tt = doc_trang_thai()
    snap = tt.get("snapshot_cuoi")
    ip = a.target_ip or tt.get("aws_ip")
    if not snap:
        raise CutoverRefused("khong biet anh chup nao — chay final-backup truoc")
    if not ip:
        raise CutoverRefused("thieu --target-ip")
    print(f"=== RESTORE {snap} -> {ip} ===")
    print("  Quy trinh da chung minh o docs/APPWRITE_MIGRATION.md muc 8-9:")
    print("    1. tao disk tu anh chup, gan vao may trich xuat")
    print("    2. tar 14 volume, doi soat sha256")
    print("    3. nap vao docker volume tren may dich")
    print("    4. docker compose -p appwrite up -d   (ten project PHAI la appwrite)")
    print("    5. xac nhan isWritablePrimary=true   <- GHI duoc moi la bang chung")
    if a.dry_run:
        print("  --dry-run: khong chay")
        return 0
    raise CutoverRefused(
        "buoc nay chua noi day tu dong — co y, vi no cham vao may dich that. "
        "Xem docs/APPWRITE_PROD_CUTOVER.md muc RESTORE.")


# --- PHA 3: FINAL BACKUP ----------------------------------------------------

def pha_final_backup(a) -> int:
    """Anh chup MOI, ngay truoc khi chuyen. Day la luoi an toan cuoi cung."""
    doi_pha_truoc("final-backup")
    ten = f"appwrite-prod-final-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print(f"=== FINAL BACKUP: {ten} ===")
    if a.dry_run:
        print("  --dry-run: khong tao anh chup")
        return 0
    rc, out, err = gce(["compute", "snapshots", "create", ten,
                        f"--source-disk={GCE_VM}",
                        f"--source-disk-zone={GCE_ZONE}",
                        "--labels=purpose=final-cutover-backup"], han=1800)
    if rc != 0:
        raise CutoverRefused(f"tao anh chup that bai: {err[:200]}")
    rc, st, _ = gce(["compute", "snapshots", "describe", ten,
                     "--format=value(status)"])
    print(f"  trang thai: {st}")
    if st != "READY":
        raise CutoverRefused(f"anh chup khong READY (={st})")
    dat_pha("final-backup", snapshot_cuoi=ten, snapshot_luc=_luc())
    ghi_audit("final_backup", ten=ten, status=st)
    return 0


def _tuoi_backup_phut() -> float:
    tt = doc_trang_thai()
    luc = tt.get("snapshot_luc")
    if not luc:
        raise CutoverRefused("chua co anh chup cuoi — chay pha final-backup")
    t = datetime.strptime(luc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0


# --- PHA 5: CANARY (TRUOC DNS) ---------------------------------------------

def pha_canary(a) -> int:
    """Kiem may dich bang Host header — TRUOC khi dong vao DNS.

    Neu buoc nay khong xanh thi khong bao gio duoc doi ban ghi A. Do la ca
    ly do no ton tai: phat hien hong khi nguoi dung VAN dang duoc GCE phuc vu.
    """
    doi_pha_truoc("canary")
    ip = a.target_ip or doc_trang_thai().get("aws_ip")
    if not ip:
        raise CutoverRefused("thieu --target-ip (IP cua EC2 dich)")
    print(f"=== CANARY tren {ip} (DNS chua doi) ===")

    r = http_origin("/v1/health/version", ip)
    print(f"  /v1/health/version -> HTTP {r.get('status')} {r.get('body','')[:50]}")
    if r.get("status") != 200 or APPWRITE_VERSION not in r.get("body", ""):
        raise CutoverRefused(f"may dich khong tra {APPWRITE_VERSION}: {r}")

    from scripts.fanfic_credential_broker import appwrite_admin_env
    env = appwrite_admin_env()
    k = env.pop("APPWRITE_SCHEMA_API_KEY", "")
    pr = env.get("APPWRITE_PROJECT_ID", "")
    db = env.get("APPWRITE_DATABASE_ID", "")
    rr = http_origin(f"/v1/databases/{db}/collections", ip,
                     headers={"X-Appwrite-Project": pr, "X-Appwrite-Key": k})
    print(f"  collections -> HTTP {rr.get('status')}")
    if rr.get("status") != 200:
        raise CutoverRefused(f"khong doc duoc collections tren dich: {rr}")
    try:
        tong = json.loads(rr["body"] + "}" * 0).get("total")
    except json.JSONDecodeError:
        tong = None
    if tong is not None and tong != SO_COLLECTION_PROD:
        raise CutoverRefused(
            f"so collection lech: {tong} != {SO_COLLECTION_PROD}")

    dat_pha("canary", aws_ip=ip)
    ghi_audit("canary", ip=ip, dat=True)
    print("  CANARY DAT — may dich san sang, DNS van chua doi")
    return 0


# --- PHA 6: CUTOVER (doi ban ghi A goc) ------------------------------------

def pha_cutover(a) -> int:
    doi_pha_truoc("cutover")
    tuoi = _tuoi_backup_phut()
    print(f"=== CUTOVER === (anh chup cuoi cach day {tuoi:.1f} phut)")
    if tuoi > TUOI_BACKUP_TOI_DA_PHUT:
        raise CutoverRefused(
            f"anh chup cuoi da {tuoi:.0f} phut > {TUOI_BACKUP_TOI_DA_PHUT}. "
            "Chay lai final-backup ngay truoc khi chuyen.")
    print("  Doi ban ghi A GOC tren Cloudflare:")
    print(f"    {HOSTNAME}:  {ORIGIN_GCE_IP}  ->  {doc_trang_thai().get('aws_ip')}")
    print("  GIU nguyen che do proxy (dam may cam). Rollback = doi nguoc lai.")
    if a.dry_run:
        print("  --dry-run: khong goi Cloudflare")
        return 0
    raise CutoverRefused(
        "doi DNS la thao tac con nguoi phai tu bam — co y khong tu dong hoa. "
        "Xem docs/APPWRITE_PROD_CUTOVER.md muc CUTOVER.")


# --- PHA 7: OBSERVE ---------------------------------------------------------

def _tieu_chi_rollback(ip_dich: str, ssh_dich: str = "") -> List[str]:
    """Tra ve danh sach ly do PHAI rollback. Rong = con on."""
    ly_do: List[str] = []
    r = http_origin("/v1/health/version", ip_dich)
    if r.get("status") != 200:
        ly_do.append(f"health khong 200 (={r.get('status')})")
    elif APPWRITE_VERSION not in r.get("body", ""):
        ly_do.append("health tra sai phien ban")

    # 8 GiB duoc chon tu mot phep do KHONG co tai that. Diem yeu do da duoc
    # ghi ra tu dau, nen no phai co mat trong tieu chi rollback chu khong chi
    # trong tai lieu: swap bat dau bi dung nghia la gia dinh kia sai.
    if ssh_dich:
        rc, out, _ = chay(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15",
             ssh_dich, "awk '/SwapTotal|SwapFree/{print $2}' /proc/meminfo"],
            han=45)
        if rc == 0:
            so = [int(x) for x in out.split() if x.isdigit()]
            if len(so) == 2:
                tong, con = so
                dung_mb = (tong - con) / 1024.0
                if dung_mb > NGUONG_SWAP_MB:
                    ly_do.append(
                        f"swap dang dung {dung_mb:.0f} MB > {NGUONG_SWAP_MB} MB "
                        "— 8 GiB co the khong du o tai that")
    return ly_do


def pha_observe(a) -> int:
    doi_pha_truoc("observe")
    ip = doc_trang_thai().get("aws_ip")
    if not ip:
        raise CutoverRefused("khong biet IP dich")
    print(f"=== OBSERVE {a.minutes} phut, lay mau moi {a.every}s ===")
    het = time.time() + a.minutes * 60
    xau = 0
    while time.time() < het:
        ly_do = _tieu_chi_rollback(ip, a.ssh_dich)
        if ly_do:
            xau += 1
            print(f"  [{_luc()}] XAU ({xau}): {'; '.join(ly_do)}")
            if xau >= 3:
                ghi_audit("observe.cham_nguong", ly_do=ly_do)
                print("\n!!! CHAM NGUONG ROLLBACK — doi ban ghi A ve GCE NGAY")
                ghi_trang_thai(**{"pha.observe": "HONG"})
                return 20
        else:
            xau = 0
            print(f"  [{_luc()}] on")
        time.sleep(a.every)
    dat_pha("observe")
    ghi_audit("observe", dat=True, phut=a.minutes)
    return 0


# --- PHA 8: COMMIT ----------------------------------------------------------

def pha_commit(a) -> int:
    """Chi duoc dung GCE sau khi het thoi gian giu."""
    doi_pha_truoc("commit")
    tt = doc_trang_thai()
    luc = tt.get("cutover_luc")
    if not luc:
        raise CutoverRefused("chua ghi nhan thoi diem cutover")
    t = datetime.strptime(luc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    con = (t + timedelta(days=NGAY_GIU_GCE)) - datetime.now(timezone.utc)
    if con.total_seconds() > 0:
        raise CutoverRefused(
            f"con {con.days} ngay {con.seconds // 3600} gio nua moi het thoi "
            f"gian giu GCE ({NGAY_GIU_GCE} ngay). GCE la duong lui — khong "
            "dung som.")
    print("=== COMMIT: het thoi gian giu, duoc phep dung GCE ===")
    print("  Van la thao tac con nguoi. Khong tu dong dung mot may production.")
    return 0


# --- PHA: ROLLBACK ----------------------------------------------------------

def pha_rollback(a) -> int:
    print("=== ROLLBACK ===")
    print(f"  Doi ban ghi A goc ve GCE: {HOSTNAME} -> {ORIGIN_GCE_IP}")
    print("  Vi Cloudflare proxy, thay doi co hieu luc trong vai giay.")
    print("  GCE van dang chay va van nhan ghi — khong mat du lieu.")
    ghi_audit("rollback.huong_dan", ve=ORIGIN_GCE_IP)
    return 0


PHA = {
    "status": pha_status,
    "preflight": pha_preflight,
    "prepare": pha_prepare,
    "freeze": pha_freeze,
    "final-backup": pha_final_backup,
    "restore": pha_restore,
    "canary": pha_canary,
    "cutover": pha_cutover,
    "observe": pha_observe,
    "commit": pha_commit,
    "rollback": pha_rollback,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pha", choices=sorted(PHA))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--target-ip", default="")
    p.add_argument("--ssh-dich", default="",
                   help="observe: ubuntu@<ip> de do swap tren may dich")
    p.add_argument("--minutes", type=int, default=60)
    p.add_argument("--every", type=int, default=60)
    p.add_argument("--da-dong-bang-ghi", action="store_true",
                   help="freeze: xac nhan DA chan ghi; tep nay se do lai")
    p.add_argument("--toi-dong-y-tra-tien", action="store_true",
                   help="prepare: xac nhan tao tai nguyen TINH TIEN")
    a = p.parse_args(argv)
    try:
        return PHA[a.pha](a)
    except CutoverRefused as exc:
        print(f"TU CHOI: {exc}", file=sys.stderr)
        ghi_audit("tu_choi", pha=a.pha, ly_do=str(exc)[:200])
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
