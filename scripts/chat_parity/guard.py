"""
Rao CUNG cho bai kiem tuong duong production (`scripts.chat_parity`). FAIL CLOSED o moi nhanh.

Dich DUY NHAT duoc phep la mot Appwrite 1.9.x DUNG MOT LAN, tu dung tren chinh may chay test:

1. `kiem_dich()` — KHONG goi mang. Host phai la LOOPBACK (`127.0.0.1` / `localhost` / `::1`), project ID
   phai mang tien to `parity-`, va toa do KHONG trung production nao trong nguon su that duy nhat
   `scripts/ops/cutover_target.py` (lop kiem nguoc `khang_dinh_khong_phai_production`).
2. `xac_minh_song()` — CHI DOC: phien ban tra ve phai la 1.9.x (dung dong production dang chay), khoa
   thuoc dung project (`GET /databases` = 200), va MOI tai khoan trong project la tai khoan TONG HOP
   (`@example.test`). Mot project co nguoi dung that thi khong phai may kiem — dung.
3. `moi_truong_con()` — tien trinh con chi nhan `APPWRITE_*` = toa do may kiem, `FAS_ENV_FILE` RONG
   (khong nap `server/.env` nao) va KHONG thua ke bien nao khac cua shell goi.

Khong co duong nao de tro rao nay vao production: production la mot host tu xa, khong bao gio loopback.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote, urlparse

from scripts.ops.cutover_target import CutoverRefused, khang_dinh_khong_phai_production

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
TIEN_TO_DU_AN = "parity-"
DONG_PHIEN_BAN = "1.9."
MIEN_TONG_HOP = "@example.test"
TRAN_KIEM_NGUOI_DUNG = 5000

#: Bien he thong GIU LAI cho tien trinh con (khong phai cau hinh ung dung).
_GIU = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME", "APPDATA",
        "LOCALAPPDATA", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL",
        "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


class DichBiTuChoi(RuntimeError):
    """Rao tu choi. Thong diep KHONG BAO GIO chua bi mat."""


@dataclass(frozen=True)
class CauHinhParity:
    endpoint: str
    project_id: str
    database_id: str
    api_key: str

    @classmethod
    def tu_env(cls, env: Optional[Mapping[str, str]] = None) -> "CauHinhParity":
        env = os.environ if env is None else env
        return cls(endpoint=env.get("APPWRITE_ENDPOINT", ""), project_id=env.get("APPWRITE_PROJECT_ID", ""),
                   database_id=env.get("APPWRITE_DATABASE_ID", ""), api_key=env.get("APPWRITE_API_KEY", ""))

    def an(self, s: str) -> str:
        """Che khoa API trong moi dong log truoc khi in/ghi."""
        return s.replace(self.api_key, "«khoá-api»") if self.api_key else s


def kiem_dich(cfg: CauHinhParity) -> None:
    u = urlparse(cfg.endpoint)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise DichBiTuChoi("APPWRITE_ENDPOINT không hợp lệ.")
    if u.hostname not in LOOPBACK:
        raise DichBiTuChoi(f"Chỉ cho phép Appwrite trên loopback, không phải {u.hostname!r}.")
    if u.path.rstrip("/") != "/v1":
        raise DichBiTuChoi("APPWRITE_ENDPOINT phải kết thúc bằng /v1.")
    if not cfg.project_id.startswith(TIEN_TO_DU_AN):
        raise DichBiTuChoi(f"Project ID phải có tiền tố {TIEN_TO_DU_AN!r} (máy kiểm dùng một lần).")
    if not (cfg.database_id and cfg.api_key):
        raise DichBiTuChoi("Thiếu APPWRITE_DATABASE_ID hoặc APPWRITE_API_KEY.")
    try:
        khang_dinh_khong_phai_production({"APPWRITE_ENDPOINT": cfg.endpoint, "APPWRITE_PROJECT_ID": cfg.project_id,
                                          "APPWRITE_DATABASE_ID": cfg.database_id})
    except CutoverRefused as exc:
        raise DichBiTuChoi(f"Toạ độ trùng production: {exc}") from exc


def _goi(cfg: CauHinhParity, method: str, path: str, *, khoa: bool = True) -> Any:
    import httpx

    hd = {"X-Appwrite-Project": cfg.project_id}
    if khoa:
        hd["X-Appwrite-Key"] = cfg.api_key
    r = httpx.request(method, cfg.endpoint.rstrip("/") + path, timeout=20, headers=hd)
    return r.status_code, (r.json() if r.content else {})


def xac_minh_song(cfg: CauHinhParity) -> Dict[str, Any]:
    kiem_dich(cfg)
    # KHONG kem khoa: tren 1.9.6 `/health/version` kem khoa can scope `public` (khong cap duoc) -> 401.
    st, b = _goi(cfg, "GET", "/health/version", khoa=False)
    ver = str((b or {}).get("version") or "")
    if st != 200 or not ver.startswith(DONG_PHIEN_BAN):
        raise DichBiTuChoi(f"Máy kiểm phải là Appwrite {DONG_PHIEN_BAN}x, nhận {st} {ver!r}.")
    st, _ = _goi(cfg, "GET", "/databases")
    if st != 200:
        raise DichBiTuChoi(f"Khoá không thuộc project máy kiểm (GET /databases = {st}).")
    dem, tong, trang = 0, None, 0
    while tong is None or dem < tong:
        st, b = _goi(cfg, "GET", "/users?queries[]=" + quote(f'{{"method":"limit","values":[100]}}')
                     + "&queries[]=" + quote(f'{{"method":"offset","values":[{dem}]}}'))
        if st != 200:
            raise DichBiTuChoi(f"Không đọc được danh sách tài khoản ({st}).")
        tong = int(b.get("total") or 0)
        if tong > TRAN_KIEM_NGUOI_DUNG:
            raise DichBiTuChoi("Quá nhiều tài khoản cho một máy kiểm dùng một lần.")
        ds = b.get("users") or []
        for u in ds:
            if not str(u.get("email") or "").endswith(MIEN_TONG_HOP):
                raise DichBiTuChoi("Project có tài khoản KHÔNG tổng hợp — không phải máy kiểm.")
        dem += len(ds)
        trang += 1
        if not ds or trang > TRAN_KIEM_NGUOI_DUNG // 100 + 1:
            break
    return {"appwrite_version": ver, "so_tai_khoan": tong or 0}


def moi_truong_con(cfg: CauHinhParity, *, them: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    kiem_dich(cfg)
    env = {k: os.environ[k] for k in _GIU if os.environ.get(k)}
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "FAS_ENV_FILE": "",
        "FAS_ENV": "parity",
        "FAS_INLINE_WORKER": "false",
        "FAS_CORS_ORIGINS": "http://localhost:3000",
        "DATA_BACKEND": "appwrite",
        "STORAGE_BACKEND": "local",
        "APPWRITE_ENDPOINT": cfg.endpoint,
        "APPWRITE_PROJECT_ID": cfg.project_id,
        "APPWRITE_DATABASE_ID": cfg.database_id,
        "APPWRITE_API_KEY": cfg.api_key,
    })
    if them:
        env.update(them)
    try:
        khang_dinh_khong_phai_production(env)
    except CutoverRefused as exc:
        raise DichBiTuChoi(f"Môi trường tiến trình con trỏ vào production: {exc}") from exc
    return env
