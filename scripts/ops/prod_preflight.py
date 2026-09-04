#!/usr/bin/env python3
"""Nghiem thu HINH DANG PRODUCTION tren may AWS — KHONG tieu mot job that
nao va KHONG doi hoi worker dang chay.

Chay qua cong dieu hanh hep:  `fanfic-prod-admin preflight`

Cai duy nhat script nay GHI ra ngoai la mot doi tuong R2 thu nghiem mang
tien to `_cutover-probe/`. Tien to do khong nam tren bat ky duong doc nao
cua san pham (`output_key` luon bat dau bang `audio/`), nen no khong the
tro thanh noi dung nguoi dung nhin thay. Doi tuong bi xoa ngay trong cung
mot lan chay, ke ca khi mot buoc phia sau that bai.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))

from scripts.ops.appwrite_latency import do_tre, dong_tom_tat  # noqa: E402
from scripts.ops.cutover_target import (  # noqa: E402
    PROD_R2_BUCKET,
    CutoverRefused,
    khang_dinh_production,
    nap_env_tu_tep,
)

#: Tien to CO Y nam ngoai `audio/` — khong duong doc nao cua san pham cham toi.
TIEN_TO_PROBE = "_cutover-probe/"


def _in(nhan: str, gt) -> None:
    print(f"  {nhan:22}: {gt}")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default="",
                    help="tep env production. Duoc PHAN TICH, khong bao gio "
                         "duoc chay — xem `chay_python` trong fanfic_prod_admin.sh")
    a = ap.parse_args()
    loi = 0

    # --- 1. env cua chinh tien trinh nay phai la production ---------------
    print("=== A. KHANG DINH MOI TRUONG ===")
    try:
        if a.env_file:
            for k, v in nap_env_tu_tep(a.env_file).items():
                os.environ[k] = v
        khang_dinh_production(os.environ)
        _in("khang dinh env", "DAT")
    except CutoverRefused as exc:
        print(f"  TU CHOI: {exc}")
        return 2
    except OSError as exc:
        print(f"  TU CHOI: khong doc duoc tep env: {exc.strerror}")
        return 2

    from server.config import get_settings

    s = get_settings()
    s.validate()
    _in("environment", s.environment)
    _in("data_backend", s.data_backend)
    _in("storage_backend", s.storage_backend)
    _in("inline_worker", s.inline_worker)
    _in("var_dir", s.var_dir)
    if (s.environment or "").lower() != "production":
        print("  DUNG LAI: settings.environment khong phai production")
        return 2
    if s.inline_worker:
        print("  DUNG LAI: inline_worker phai la false tren may worker rieng")
        return 2
    if (s.storage_backend or "").lower() != "r2":
        print("  DUNG LAI: storage_backend phai la r2")
        return 2
    if s.r2.bucket != PROD_R2_BUCKET:
        print(f"  DUNG LAI: bucket {s.r2.bucket!r} khong phai {PROD_R2_BUCKET!r}")
        return 2

    # --- 2. do tre + suc khoe Appwrite ------------------------------------
    print("\n=== B. APPWRITE ===")
    kq = do_tre(os.environ["APPWRITE_ENDPOINT"],
                project_id=os.environ.get("APPWRITE_PROJECT_ID"))
    _in("health/version", dong_tom_tat(kq))
    _in("phien ban", (kq.get("than") or {}).get("version"))
    # Do tre duoc GIU lai ke ca khi khong khoe — nhung mot trang thai hong
    # KHONG BAO GIO duoc dien giai thanh mot cong da dat.
    if not kq["khoe"]:
        print(f"  KHONG DAT: health khong-2xx (lop={kq['lop_that_bai']})")
        loi = 1

    # Ket noi THAT o tang du lieu, khong chi tang HTTP.
    from server.domain import JobStatus
    from server.adapters import build_metadata_store

    t0 = time.perf_counter()
    store = build_metadata_store(s)
    dang_chay = store.list_jobs_by_status(JobStatus.RUNNING)
    cho = store.list_jobs_by_status(JobStatus.PENDING)
    _in("truy van du lieu", f"{time.perf_counter() - t0:.3f}s")
    _in("job running", len(dang_chay))
    _in("job pending", len(cho))

    # --- 3. R2 ghi / doc / xoa tren doi tuong thu nghiem -------------------
    print("\n=== C. R2 (ghi -> doc -> xoa, doi tuong thu nghiem) ===")
    from server.adapters import build_storage

    kho = build_storage(s)
    key = f"{TIEN_TO_PROBE}{uuid.uuid4().hex}.bin"
    than = b"fanfic-cutover-preflight-" + uuid.uuid4().hex.encode()
    _in("bucket", s.r2.bucket)
    _in("key", key)
    if not key.startswith(TIEN_TO_PROBE):
        print("  DUNG LAI: key thu nghiem sai tien to")
        return 2

    da_ghi = False
    try:
        kho.put(key, than, content_type="application/octet-stream")
        da_ghi = True
        _in("put", f"{len(than)} byte")

        head = kho.head_probe(key) if hasattr(kho, "head_probe") else {}
        _in("head", f"tim_thay={head.get('tim_thay')} "
                    f"http={head.get('http_status')} "
                    f"len={head.get('content_length')}")
        if not head.get("tim_thay") or head.get("content_length") != len(than):
            print("  KHONG DAT: head khong khop")
            loi = 1

        doc = kho.get(key)
        _in("get", f"{len(doc)} byte, khop={doc == than}")
        if doc != than:
            print("  KHONG DAT: noi dung doc lai khong khop")
            loi = 1
    except Exception as exc:  # noqa: BLE001
        print(f"  KHONG DAT: R2 that bai: {type(exc).__name__}")
        loi = 1
    finally:
        if da_ghi:
            try:
                # Chi xoa dung key da tao, va chi khi no mang tien to probe.
                assert key.startswith(TIEN_TO_PROBE)
                _in("delete", kho.delete(key))
                _in("con ton tai", kho.exists(key))
            except Exception as exc:  # noqa: BLE001
                print(f"  CANH BAO: chua xoa duoc doi tuong thu nghiem: "
                      f"{type(exc).__name__}")
                loi = 1

    # --- 4. giong + model --------------------------------------------------
    print("\n=== D. GIONG CUC BO ===")
    from server import tts_bridge

    ds = list(s.local_voices or ())
    _in("so giong chao ban", len(ds))
    qua_ca_hai = []
    for v in ds:
        vat_ly = tts_bridge.voice_runnable_on_this_machine(v)
        san_pham = tts_bridge.voice_is_local_allowed(v, s)
        if vat_ly and san_pham:
            qua_ca_hai.append(v)
        elif not vat_ly:
            print(f"    THIEU MODEL: {v}")
            loi = 1
    _in("qua CA HAI cong", f"{len(qua_ca_hai)}/{len(ds)}")
    if not qua_ca_hai:
        print("  KHONG DAT: khong giong nao dung duoc -> moi job se that bai")
        loi = 1

    # --- 5. ffmpeg ---------------------------------------------------------
    print("\n=== E. FFMPEG ===")
    import shutil

    for c in ("ffmpeg", "ffprobe"):
        d = shutil.which(c)
        _in(c, d or "THIEU")
        if not d:
            # Chuong nhieu doan duoc ghep bang ffmpeg. Chuong mot doan chi
            # doi ten tep — nen mot bai smoke ngan VAN XANH tren may thieu
            # ffmpeg. Do la ly do phai kiem tuong minh o day.
            print("  KHONG DAT: chuong nhieu doan se khong ghep duoc")
            loi = 1

    print("\n=== KET LUAN ===")
    print("  PREFLIGHT_PASS" if loi == 0 else "  PREFLIGHT_FAIL")
    return loi


if __name__ == "__main__":
    raise SystemExit(main())
