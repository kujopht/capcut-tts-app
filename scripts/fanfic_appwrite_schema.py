#!/usr/bin/env python3
"""Đối chiếu schema Appwrite sản xuất với `scripts/setup_appwrite.py`.

VÌ SAO TỒN TẠI: `setup_appwrite.py --dry-run` **không hề gọi Appwrite**
(`_exists` trả `False`, `_call` trả `None`), nên nó in ra kế hoạch như thể
chưa có gì tồn tại. Nó trả lời được "script định làm gì", không trả lời được
"sản xuất đang thiếu gì" — mà đó mới là câu hỏi cần trước một migration, và
cũng là câu hỏi duy nhất khiến cổng "không còn thay đổi nào" có ý nghĩa.

`audit` là phép ĐỌC thuần tuý. Nó không bao giờ POST/PATCH/DELETE.

XỬ LÝ BÍ MẬT: khoá schema đi từ Windows Credential Manager thẳng vào bộ nhớ
tiến trình, rồi vào header `X-Appwrite-Key`. Nó không bao giờ nằm trong argv,
trong stdout/stderr, trong tệp tạm, trong tệp của kho mã, hay trong lịch sử
shell. Toạ độ (endpoint/project/database) không phải bí mật và được đọc tự
động từ Render — người vận hành không phải gõ lại thứ đã cấu hình.

Lệnh:
    audit                 đối chiếu toàn bộ SCHEMA, in khác biệt
    audit --only C        chỉ một collection
    apply --only C        chạy migration đã thu hẹp phạm vi

Mã thoát:
    0  khớp hoàn toàn (với `audit`) / migration xong (với `apply`)
    1  có khác biệt so với SCHEMA
    2  thiếu credential hoặc lỗi cấu hình
    3  Appwrite/Render trả lỗi
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import pathlib
import sys
from typing import Any, Dict, List, Tuple

import httpx

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

TIMEOUT = 30.0

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


_BROKER = None


def _broker():
    """Nạp broker theo đường dẫn — nó là script, không phải package.

    NẠP ĐÚNG MỘT LẦN. Nạp lại tạo ra một đối tượng module KHÁC, và do đó một
    lớp ngoại lệ `BrokerEnvironmentError` khác: `except b.BrokerEnvironmentError`
    khi đó không bắt được ngoại lệ do bản nạp kia ném ra, nên một thông báo
    "thiếu credential" hoàn toàn đọc được lại tuột ra thành traceback kèm mã
    thoát sai. Đã vấp thật khi dựng lối này.
    """
    global _BROKER
    if _BROKER is None:
        path = _ROOT / "scripts" / "fanfic_credential_broker.py"
        spec = importlib.util.spec_from_file_location("_fanfic_broker", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _BROKER = mod
    return _BROKER


#: Kiểu trong SCHEMA -> (type, format) mà Appwrite báo cáo lại.
#:
#: Appwrite KHÔNG có kiểu "enum" hay "email" riêng: cả hai đều là `string` kèm
#: một `format`. So sánh thẳng tên kiểu sẽ báo sai lệch ở mọi cột enum/email
#: trên một schema hoàn toàn đúng.
KIEU_APPWRITE: Dict[str, Tuple[str, str]] = {
    "string": ("string", ""),
    "email": ("string", "email"),
    "enum": ("string", "enum"),
    "integer": ("integer", ""),
    "double": ("double", ""),
    "boolean": ("boolean", ""),
    "datetime": ("datetime", ""),
}


class AuditError(RuntimeError):
    """Appwrite không đọc được — khác hẳn với "đọc được và có khác biệt"."""


class Reader:
    """Chỉ ĐỌC. Lớp này cố tình không có phương thức nào ghi."""

    def __init__(self, env: Dict[str, str]):
        self._endpoint = env["APPWRITE_ENDPOINT"].rstrip("/")
        # Khoa schema di trong header cua CHINH request nay, nen mot endpoint
        # `http://` se gui no di duoi dang ro. Toa do den tu Render chu khong
        # phai dau vao nguoi dung, nhung mot lan sua nham cau hinh khong duoc
        # phep bien thanh mot lan lo khoa. Neu ra qua review bao mat doc lap.
        if not self._endpoint.startswith("https://"):
            raise AuditError(
                "APPWRITE_ENDPOINT phải là https:// — từ chối gửi khoá schema "
                "qua kênh không mã hoá.")
        if self._endpoint.endswith("/v1"):
            self._endpoint = self._endpoint[: -len("/v1")]
        self._project = env["APPWRITE_PROJECT_ID"]
        self._database = env["APPWRITE_DATABASE_ID"]
        self._key = env["APPWRITE_SCHEMA_API_KEY"]

    @property
    def database(self) -> str:
        return self._database

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._project,
            "X-Appwrite-Key": self._key,      # CHỈ ở header, không bao giờ in
        }

    def get(self, path: str) -> Any:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.get(f"{self._endpoint}{path}", headers=self._headers())
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            from server.secret_redaction import thong_diep_loi_an_toan
            try:
                body = r.json()
            except Exception:
                body = None
            # Lọc bí mật theo mẫu trước khi thông điệp ra tới người đọc: thân
            # lỗi 4xx của Appwrite có thể vọng lại chính request bị từ chối.
            raise AuditError(
                f"Appwrite {r.status_code}: "
                f"{thong_diep_loi_an_toan(body, status_code=r.status_code)}")
        return r.json() if r.content else {}


def _khac_biet_collection(cid: str, spec: Dict[str, Any],
                          hien: Any) -> List[str]:
    """Liệt kê những gì SCHEMA yêu cầu mà sản xuất chưa có."""
    if hien is None:
        n_attr = len(spec["attributes"])
        n_idx = len(spec["indexes"])
        return [f"THIẾU CẢ COLLECTION (cần {n_attr} thuộc tính, {n_idx} index)"]

    ra: List[str] = []
    co_attr = {a.get("key"): a for a in hien.get("attributes", [])}
    for key, kind, required, extra in spec["attributes"]:
        thuoc = co_attr.get(key)
        if thuoc is None:
            ra.append(f"thiếu thuộc tính {key} ({kind})")
            continue
        # Một thuộc tính TỒN TẠI vẫn có thể không DÙNG ĐƯỢC — sự cố thật
        # 2026-08-21: job nền của Appwrite đánh dấu "failed" và cột kẹt ở
        # "processing" mãi mãi. Coi "có mặt" là "xong" chính là cái bẫy đó.
        trang_thai = thuoc.get("status")
        if trang_thai and trang_thai != "available":
            ra.append(f"thuộc tính {key}: trạng thái {trang_thai!r}, chưa dùng được")
        mong_type, mong_format = KIEU_APPWRITE.get(kind, (kind, ""))
        if thuoc.get("type") != mong_type:
            ra.append(f"thuộc tính {key}: kiểu {thuoc.get('type')!r}, cần {mong_type!r}")
        if mong_format and thuoc.get("format") != mong_format:
            ra.append(f"thuộc tính {key}: format {thuoc.get('format')!r}, "
                      f"cần {mong_format!r}")
        if bool(thuoc.get("required")) != bool(required):
            ra.append(f"thuộc tính {key}: required={thuoc.get('required')}, "
                      f"cần {required}")
        if kind == "enum":
            thieu_gt = [e for e in (extra or []) if e not in (thuoc.get("elements") or [])]
            if thieu_gt:
                ra.append(f"thuộc tính {key}: enum thiếu giá trị {thieu_gt}")

    co_idx = {i.get("key"): i for i in hien.get("indexes", [])}
    for name, kind, keys in spec["indexes"]:
        idx = co_idx.get(name)
        if idx is None:
            ra.append(f"thiếu index {name} {list(keys)}")
            continue
        trang_thai = idx.get("status")
        if trang_thai and trang_thai != "available":
            ra.append(f"index {name}: trạng thái {trang_thai!r}, chưa dùng được")
        if list(idx.get("attributes") or []) != list(keys):
            ra.append(f"index {name}: cột {idx.get('attributes')}, cần {list(keys)}")
    return ra


@contextlib.contextmanager
def _moi_truong_tam(env: Dict[str, str]):
    """Tiêm biến môi trường CHỈ trong thời gian chạy migration, rồi trả lại.

    `load_settings` đọc `os.environ`, nên khoá phải đi qua đó — không argv,
    không tệp tạm, không tệp kho mã, không lịch sử shell.

    Nhưng `os.environ.update()` trần thì KHÔNG BAO GIỜ được dọn: khoá nằm lại
    trong khối môi trường của tiến trình cho tới lúc thoát, và mọi tiến trình
    con sinh ra sau đó — kể cả gián tiếp — đều thừa hưởng nó. Đó là một bề
    mặt mới, không phải một bước cần thiết. Nêu ra qua review bảo mật độc lập
    (Antigravity Claude Opus, 2026-08-29).

    Khôi phục cả những khoá TRƯỚC ĐÓ KHÔNG TỒN TẠI bằng cách xoá hẳn, chứ
    không đặt lại thành "" — làm thế sẽ để lại một biến rỗng chưa từng có,
    và một biến rỗng không giống một biến vắng mặt với mọi đoạn mã đọc nó.
    """
    truoc = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for k, cu in truoc.items():
            if cu is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = cu


def cmd_audit(args) -> int:
    from scripts.setup_appwrite import SCHEMA

    b = _broker()
    env = b.appwrite_admin_env()
    reader = Reader(env)

    print(f"Endpoint  : {env['APPWRITE_ENDPOINT']}")
    print(f"Project   : {env['APPWRITE_PROJECT_ID']}")
    print(f"Database  : {env['APPWRITE_DATABASE_ID']}")
    print("Khoá schema: đọc từ Windows Credential Manager (không in giá trị)\n")

    if reader.get(f"/v1/databases/{reader.database}") is None:
        print("KHÁC BIỆT: database không tồn tại.")
        return 1

    muc_tieu = [args.only] if args.only else list(SCHEMA)
    if args.only and args.only not in SCHEMA:
        print(f"Không có collection {args.only!r} trong SCHEMA.")
        return 2

    tong = 0
    for cid in muc_tieu:
        hien = reader.get(f"/v1/databases/{reader.database}/collections/{cid}")
        khac = _khac_biet_collection(cid, SCHEMA[cid], hien)
        if not khac:
            n = len(SCHEMA[cid]["attributes"])
            print(f"  OK   {cid:24} ({n} thuộc tính, "
                  f"{len(SCHEMA[cid]['indexes'])} index) — khớp")
            continue
        tong += len(khac)
        print(f"  KHÁC {cid}")
        for dong in khac:
            print(f"         - {dong}")

    print()
    if tong == 0:
        print("Không còn khác biệt nào. Sản xuất khớp SCHEMA.")
        return 0
    print(f"Tổng cộng {tong} khác biệt so với SCHEMA.")
    return 1


def cmd_apply(args) -> int:
    """Chạy migration đã thu hẹp phạm vi, tiêm env trong bộ nhớ.

    `--only` là BẮT BUỘC ở đây (khác với `setup_appwrite` gốc, nơi thiếu cờ
    nghĩa là "tất cả"). Lối vào này chỉ tồn tại cho migration có phạm vi hẹp,
    nên mặc định "chạm mọi collection" không phải thứ đáng để với tới được.
    """
    from scripts.setup_appwrite import SCHEMA, main as setup_main

    if args.only not in SCHEMA:
        print(f"Không có collection {args.only!r} trong SCHEMA.")
        return 2

    b = _broker()
    env = dict(b.appwrite_admin_env())
    # `setup_appwrite` ưu tiên `APPWRITE_SCHEMA_API_KEY`; đặt rỗng khoá runtime
    # để không có đường lui âm thầm sang một khoá chỉ có quyền documents.
    env["APPWRITE_API_KEY"] = ""
    env["FAS_ENV_FILE"] = ""            # không nạp `server/.env` nào cả

    print(f"Áp dụng schema cho {args.only} (chỉ collection này).\n")
    with _moi_truong_tam(env):
        return setup_main(["--only", args.only])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="chỉ đọc; đối chiếu với SCHEMA")
    p_audit.add_argument("--only", default="")
    p_audit.set_defaults(func=cmd_audit)

    p_apply = sub.add_parser("apply", help="chạy migration đã thu hẹp phạm vi")
    p_apply.add_argument("--only", required=True)
    p_apply.set_defaults(func=cmd_apply)

    args = ap.parse_args(argv)
    b = _broker()
    try:
        return args.func(args)
    except b.BrokerEnvironmentError as exc:
        print(f"Thiếu credential: {exc}")
        return 2
    except (AuditError, b.RenderError) as exc:
        print(f"Lỗi dịch vụ: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
