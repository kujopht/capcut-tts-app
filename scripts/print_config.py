"""
In cau hinh dang co hieu luc — de biet tien trinh nay DANG tro vao dau.

    PYTHONPATH=. python scripts/print_config.py

TUYET DOI KHONG in gia tri bi mat. Voi dinh danh (project id, bucket) chi in
TIEN TO va do dai — du de doi chieu "staging hay dev", khong du de dung lai.

Vi sao can: sau khi deploy, cau hoi nguy hiem nhat la "staging co dang go vao
Appwrite cua dev khong". `/api/health` khong tra ve dinh danh (dung vay), nen can
mot cong cu chay tren chinh host do de tra loi.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from server.config import get_settings  # noqa: E402


def dau_van(gia_tri: str, giu: int = 6) -> str:
    """Tien to + do dai. Du de doi chieu, khong du de dung lai."""
    gia_tri = str(gia_tri or "")
    if not gia_tri:
        return "(trong)"
    if len(gia_tri) <= giu:
        return f"{gia_tri!r} ({len(gia_tri)} ky tu)"
    return f"{gia_tri[:giu]}… ({len(gia_tri)} ky tu)"


def co(gia_tri: str) -> str:
    """Voi SECRET: chi noi co hay khong, va dai bao nhieu."""
    return f"da dat ({len(gia_tri)} ky tu)" if gia_tri else "CHUA DAT"


def main() -> int:
    s = get_settings()

    print("=== Moi truong ===")
    print(f"  FAS_ENV              : {s.environment}")
    print(f"  la development       : {s.is_development}")
    print(f"  env file da nap      : {s.env_file_loaded}")
    print(f"  var_dir              : {s.var_dir}")
    print(f"  CORS origins         : {s.cors_origins}")

    print("\n=== Hinh dang tien trinh ===")
    print(f"  FAS_INLINE_WORKER    : {s.inline_worker}")
    if s.inline_worker:
        print("    -> web TU CHAY job. Dung o may lap trinh vien;")
        print("       o staging/production phai dat false va chay server/worker.py.")
    else:
        print("    -> web KHONG chay job. Phai co it nhat mot tien trinh")
        print("       `python -m server.worker`, neu khong job nam `pending` mai.")

    print("\n=== Kho du lieu ===")
    print(f"  DATA_BACKEND         : {s.data_backend}")
    print(f"  STORAGE_BACKEND      : {s.storage_backend}")

    print("\n=== Appwrite (dinh danh: tien to; secret: chi co/khong) ===")
    print(f"  endpoint             : {s.appwrite.api_base or '(trong)'}")
    print(f"  project_id           : {dau_van(s.appwrite.project_id)}")
    print(f"  database_id          : {dau_van(s.appwrite.database_id)}")
    print(f"  api_key              : {co(s.appwrite.api_key)}")
    print(f"  du cau hinh          : {s.appwrite.configured}")

    print("\n=== Cloudflare R2 ===")
    print(f"  account_id           : {dau_van(s.r2.account_id)}")
    print(f"  bucket               : {dau_van(s.r2.bucket)}")
    print(f"  access_key_id        : {co(s.r2.access_key_id)}")
    print(f"  secret_access_key    : {co(s.r2.secret_access_key)}")
    print(f"  du cau hinh          : {s.r2.configured}")

    print("\n=== Kiem tra ===")
    loi = []
    try:
        s.validate()
        print("  Settings.validate()  : DAT")
    except Exception as exc:
        loi.append(str(exc))
        print(f"  Settings.validate()  : HONG — {exc}")

    if s.environment.lower() in ("staging", "production") and s.inline_worker:
        loi.append("FAS_ENV la staging/production ma FAS_INLINE_WORKER van bat")
        print("  CANH BAO             : moi truong that ma web van tu chay job")

    if not s.is_development and s.allow_unverified_local_voices:
        print("  CANH BAO             : dang cho phep giong cuc bo chua xac minh "
              "giay phep o moi truong khong phai development")

    print("\nDoi chieu tien to o tren voi tai nguyen STAGING truoc khi tin. "
          "Trung tien to voi dev nghia la dang tro nham.")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
