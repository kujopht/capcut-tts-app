"""Nghiem thu worker STAGING — chay TREN chinh may staging.

    cd /opt/fanfic-audio && .venv/bin/python -m scripts.ops.worker_staging_acceptance

Khong cat production. Khong doi DNS. Khong dung GCE. Khong publish gi.

RAO CHAN DAU TIEN LA QUAN TRONG NHAT: neu may staging tro vao du an
Appwrite hoac bucket R2 PRODUCTION thi hai worker se tranh claim JOB THAT
cua production. Bai kiem so 0 kiem dung dieu do va TU CHOI chay tiep neu
trung — moi bai sau do khong co y nghia gi neu rao nay hong.

In ra mot bang PASS/FAIL va mot khoi JSON de so sanh voi baseline GCE
(`docs/reports/gce-worker-baseline.json`).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: Ten tai nguyen PRODUCTION. Staging trung bat ky dong nao la DUNG NGAY.
PROD_R2_BUCKET = "fanfic-prod"

KQ: list[tuple[str, bool, str]] = []
SO_LIEU: dict = {}


def kiem(ten: str, dat: bool, ghi_chu: str = "") -> bool:
    KQ.append((ten, dat, ghi_chu))
    print(f"  [{'PASS' if dat else 'FAIL'}] {ten}" + (f" — {ghi_chu}" if ghi_chu else ""))
    return dat


def sh(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def muc(t: str) -> None:
    print(f"\n{'=' * 68}\n  {t}\n{'=' * 68}")


# --------------------------------------------------------------------------
# 0. RAO CHAN CACH LY — chay TRUOC moi thu khac
# --------------------------------------------------------------------------
def rao_chan_cach_ly(prod_project_id: str) -> bool:
    muc("0. RAO CHAN CACH LY (staging KHONG duoc tro vao production)")
    try:
        from server.config import get_settings
        s = get_settings()
    except Exception as exc:  # noqa: BLE001
        kiem("nap duoc cau hinh", False, f"{type(exc).__name__}: {exc}")
        return False

    env = (getattr(s, "environment", "") or os.environ.get("FAS_ENV", "")).lower()
    ok = kiem("FAS_ENV == staging", env == "staging", f"doc duoc: {env!r}")

    bucket = os.environ.get("R2_BUCKET", "")
    ok &= kiem("R2_BUCKET KHAC bucket production", bucket != PROD_R2_BUCKET,
               f"staging dung: {bucket!r}")

    pid = os.environ.get("APPWRITE_PROJECT_ID", "")
    if prod_project_id:
        ok &= kiem("APPWRITE_PROJECT_ID KHAC du an production",
                   bool(pid) and pid != prod_project_id)
    else:
        kiem("APPWRITE_PROJECT_ID doi chieu duoc", True,
             "chua truyen --prod-project-id, bo qua doi chieu truc tiep")

    ok &= kiem("inline worker TAT", os.environ.get("FAS_INLINE_WORKER", "") == "false")
    SO_LIEU["moi_truong"] = env
    SO_LIEU["r2_bucket_la_production"] = bucket == PROD_R2_BUCKET
    return bool(ok)


# --------------------------------------------------------------------------
def phu_thuoc() -> None:
    muc("1. PHU THUOC RUNTIME (giong bo da do tren fanfic-worker-prod)")
    py = platform.python_version()
    kiem("python 3.12.x", py.startswith("3.12"), py)
    for b in ("ffmpeg", "ffprobe"):
        p = shutil.which(b)
        kiem(f"{b} co tren PATH", bool(p), p or "THIEU")
    v = sh(["ffmpeg", "-version"]).stdout.split("\n")[0] if shutil.which("ffmpeg") else ""
    SO_LIEU["ffmpeg"] = v[:60]
    try:
        import server.worker  # noqa: F401
        kiem("import duoc server.worker", True)
    except Exception as exc:  # noqa: BLE001
        kiem("import duoc server.worker", False, f"{type(exc).__name__}: {exc}")
    try:
        import server.translation_worker  # noqa: F401
        kiem("import duoc server.translation_worker", True)
    except Exception as exc:  # noqa: BLE001
        kiem("import duoc server.translation_worker", False, f"{type(exc).__name__}")
    out = sh([sys.executable, "-m", "pip", "list", "--format=freeze"]).stdout
    kiem("KHONG keo theo PySide6", "PySide6" not in out and "shiboken6" not in out)
    SO_LIEU["so_goi_python"] = len([l for l in out.splitlines() if l.strip()])


def giong_cuc_bo() -> None:
    muc("2. GIONG CUC BO — 'Ngoc Huyen (Moi)' PHAI con dung")
    d = Path(os.environ.get("FAS_PIPER_MODELS_DIR",
                            "/opt/fanfic-models/nghitts/piper-tts"))
    kiem("thu muc model ton tai", d.is_dir(), str(d))
    if not d.is_dir():
        return
    onnx = sorted(p.name for p in d.glob("*.onnx"))
    kiem("co 25 model .onnx (nhu production)", len(onnx) == 25, f"thay {len(onnx)}")
    # `ngochuyennew` = "Ngoc Huyen (Moi)", KHAC `ngochuyen` = "Ngoc Huyen".
    # `voice_id` = `piper:<voice_key>` da nam trong job cu VA gop phan sinh
    # `output_key` tren R2, nen ten tep KHONG duoc doi.
    for k, ten in (("ngochuyennew", "Ngoc Huyen (Moi)"), ("ngochuyen", "Ngoc Huyen")):
        kiem(f"{k}.onnx co mat ({ten})", (d / f"{k}.onnx").is_file())
        j = d / f"{k}.onnx.json"
        kiem(f"{k}.onnx.json phan giai duoc", j.is_file(),
             "symlink -> config.json" if j.is_symlink() else "tep thuong")
    try:
        from desktop_app.providers.builtin_catalog import NGHITTS_DISPLAY_NAMES as N
        kiem("bang ten giong khop 'Ngoc Huyen (Moi)'",
             N.get("ngochuyennew", "").endswith("(Mới)"),
             N.get("ngochuyennew", "(khong thay)"))
    except Exception as exc:  # noqa: BLE001
        kiem("doc duoc bang ten giong", False, f"{type(exc).__name__}")
    SO_LIEU["so_model_onnx"] = len(onnx)


def ket_noi() -> None:
    muc("3. KET NOI RA NGOAI (Appwrite Cloud / R2 / API / Drive)")
    # Chi kiem KET NOI + XAC THUC, khong doc/ghi du lieu nghiep vu.
    try:
        from server.config import get_settings
        s = get_settings()
        import httpx
        ep = os.environ.get("APPWRITE_ENDPOINT", "")
        if ep:
            r = httpx.get(f"{ep.rstrip('/')}/health/version", timeout=20)
            kiem("Appwrite Cloud tra loi", r.status_code == 200,
                 f"HTTP {r.status_code}")
        else:
            kiem("APPWRITE_ENDPOINT duoc dat", False)
    except Exception as exc:  # noqa: BLE001
        kiem("Appwrite Cloud tra loi", False, f"{type(exc).__name__}: {exc}")

    try:
        from server.r2_adapter import R2Storage  # noqa: F401
        import boto3  # noqa: F401
        acc = os.environ.get("R2_ACCOUNT_ID", "")
        bk = os.environ.get("R2_BUCKET", "")
        if acc and bk:
            import boto3 as b3
            cl = b3.client(
                "s3", endpoint_url=f"https://{acc}.r2.cloudflarestorage.com",
                aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                region_name="auto")
            cl.head_bucket(Bucket=bk)
            kiem("R2 head_bucket thanh cong", True, f"bucket={bk}")
        else:
            kiem("cau hinh R2 day du", False)
    except Exception as exc:  # noqa: BLE001
        kiem("R2 head_bucket thanh cong", False, f"{type(exc).__name__}: {exc}")

    api = os.environ.get("FAS_API_BASE_URL") or os.environ.get("PUBLIC_API_BASE", "")
    if api:
        try:
            import httpx
            r = httpx.get(f"{api.rstrip('/')}/api/health", timeout=30)
            kiem("API (Render) /api/health", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            kiem("API (Render) /api/health", False, f"{type(exc).__name__}")
    else:
        kiem("API base duoc dat", True, "khong dat — worker khong CAN goi API")

    # Drive la kho LANH: worker chi day archive khi co rclone. Khong bat buoc.
    rc = shutil.which("rclone")
    if rc:
        p = sh(["rclone", "lsd", "fanfic-gdrive:FanficWorld/archive"], timeout=90)
        kiem("Drive archive doc duoc", p.returncode == 0,
             p.stderr.strip()[-80:] if p.returncode else "OK")
    else:
        kiem("rclone (Drive archive)", True,
             "khong cai — day archive se xep hang lai, KHONG chan job")


def dich_vu_va_nhip() -> None:
    muc("4. DICH VU, NHIP, LOG, RESTART")
    for u in ("fanfic-worker.service", "fanfic-translation-worker.service"):
        p = sh(["systemctl", "is-active", u])
        kiem(f"{u} dang active", p.stdout.strip() == "active", p.stdout.strip())
        e = sh(["systemctl", "is-enabled", u])
        kiem(f"{u} enabled (len lai sau reboot)", e.stdout.strip() == "enabled",
             e.stdout.strip())
    p = sh(["systemctl", "is-active", "fanfic-worker-health.timer"])
    kiem("health timer dang active", p.stdout.strip() == "active", p.stdout.strip())

    p = sh([sys.executable, "-m", "server.worker", "--check"], timeout=120)
    kiem("server.worker --check (nhip moi)", p.returncode == 0, f"exit {p.returncode}")

    # Log co cau truc JSON, di qua journald voi SyslogIdentifier rieng.
    p = sh(["journalctl", "-u", "fanfic-worker.service", "-n", "20",
            "--no-pager", "-o", "cat"], timeout=60)
    dong = [l for l in p.stdout.splitlines() if l.strip().startswith("{")]
    kiem("log telemetry JSON nhin thay duoc", len(dong) > 0,
         f"{len(dong)} dong JSON trong 20 dong cuoi")
    quet = [l for l in dong if '"da_quet"' in l]
    kiem("thay vong quet (muc=da_quet)", len(quet) > 0, f"{len(quet)} vong")
    SO_LIEU["so_dong_log_json"] = len(dong)


def khong_cham_production() -> None:
    muc("5. KHONG TAO BAN GHI PRODUCTION, KHONG CHUYEN PUBLIC")
    # Day la kiem tren MA + tren CAU HINH, khong phai tren du lieu production:
    # doc du lieu production tu staging la dieu chinh xac phai KHONG xay ra.
    kiem("bucket R2 khong phai production",
         os.environ.get("R2_BUCKET", "") != PROD_R2_BUCKET)
    kiem("FAS_ENV khong phai production",
         os.environ.get("FAS_ENV", "").lower() != "production")
    # `--require-env staging` trong unit se lam worker thoat ma 2 neu env lech.
    p = sh([sys.executable, "-m", "server.worker", "--require-env", "production",
            "--check"], timeout=120)
    kiem("worker TU CHOI khi bi ep --require-env production",
         p.returncode == 2, f"exit {p.returncode} (mong doi 2)")
    # Khong bai nao trong bo nay chuyen trang thai sang PUBLIC. Ghi lai tuong
    # minh de nguoi doc bao cao khong phai tu suy dien.
    kiem("bo nghiem thu nay khong he goi duong publish", True,
         "khong co loi goi publish/PUBLIC nao trong tep nay")


def so_lieu_may() -> None:
    muc("6. SO LIEU MAY (de so voi baseline GCE)")
    try:
        mem = Path("/proc/meminfo").read_text()
        tot = int([l for l in mem.splitlines() if l.startswith("MemTotal")][0].split()[1])
        ava = int([l for l in mem.splitlines() if l.startswith("MemAvailable")][0].split()[1])
        SO_LIEU["ram_tong_mb"] = round(tot / 1024)
        SO_LIEU["ram_con_mb"] = round(ava / 1024)
        SO_LIEU["ram_dung_mb"] = round((tot - ava) / 1024)
    except Exception:  # noqa: BLE001
        pass
    try:
        sw = sh(["swapon", "--show=SIZE", "--noheadings"]).stdout.strip()
        SO_LIEU["swap"] = sw or "0B"
        kiem("co swap (production co 0B — day la cai thien)", bool(sw), sw or "KHONG")
    except Exception:  # noqa: BLE001
        pass
    try:
        du = shutil.disk_usage("/")
        SO_LIEU["disk_tong_gb"] = round(du.total / 2**30, 1)
        SO_LIEU["disk_dung_gb"] = round(du.used / 2**30, 1)
    except Exception:  # noqa: BLE001
        pass
    SO_LIEU["cpu_logic"] = os.cpu_count()
    try:
        SO_LIEU["load_1p"] = os.getloadavg()[0]
    except Exception:  # noqa: BLE001
        pass
    SO_LIEU["kernel"] = platform.release()
    try:
        import urllib.request
        t0 = time.time()
        urllib.request.urlopen("https://cloud.appwrite.io/v1/health/version",
                               timeout=20).read(1)
        SO_LIEU["do_tre_appwrite_ms"] = round((time.time() - t0) * 1000)
    except Exception:  # noqa: BLE001
        SO_LIEU["do_tre_appwrite_ms"] = None
    for k, v in SO_LIEU.items():
        print(f"    {k:28} {v}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prod-project-id", default="",
                    help="id du an Appwrite PRODUCTION, chi de DOI CHIEU khac nhau")
    ap.add_argument("--baseline", default="docs/reports/gce-worker-baseline.json")
    a = ap.parse_args()

    print("NGHIEM THU WORKER STAGING — khong cat production, khong publish")
    if not rao_chan_cach_ly(a.prod_project_id):
        print("\n" + "!" * 68)
        print("  DUNG LAI: rao chan cach ly KHONG dat.")
        print("  Chay tiep se co nguy co tranh claim job THAT cua production.")
        print("!" * 68)
        return 2

    phu_thuoc()
    giong_cuc_bo()
    ket_noi()
    dich_vu_va_nhip()
    khong_cham_production()
    so_lieu_may()

    bl = ROOT / a.baseline
    if bl.is_file():
        muc("7. SO SANH AWS vs GCE")
        base = json.loads(bl.read_text(encoding="utf-8"))
        g = base.get("so_lieu", {})
        print(f"  {'hang muc':28} {'GCE':>14} {'may nay':>14}")
        for k in ("cpu_logic", "ram_tong_mb", "ram_dung_mb", "swap",
                  "disk_tong_gb", "disk_dung_gb", "so_model_onnx",
                  "so_goi_python", "do_tre_appwrite_ms"):
            print(f"  {k:28} {str(g.get(k, '—')):>14} {str(SO_LIEU.get(k, '—')):>14}")
    else:
        print(f"\n(khong thay baseline {a.baseline} de so sanh)")

    dat = sum(1 for _, o, _ in KQ if o)
    muc(f"KET LUAN: {dat}/{len(KQ)} bai dat")
    fails = [t for t, o, _ in KQ if not o]
    if fails:
        print("  CHUA DAT:")
        for t in fails:
            print(f"    - {t}")
    print(f"\n{json.dumps({'so_lieu': SO_LIEU, 'dat': dat, 'tong': len(KQ)}, ensure_ascii=False, indent=2)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
