"""
Sentry cho backend FastAPI (project Sentry `python-fastapi`) — TAT MAC DINH.

Khong co `FAS_SENTRY_DSN` thi `khoi_tao_sentry()` khong import `sentry_sdk`, khong gui gi. Bat
thi MOI su kien di qua `lam_sach_su_kien()` truoc khi roi tien trinh — KHONG BAO GIO gui:
  * cookie (request + header `Cookie`/`Set-Cookie`), header `Authorization`/`X-Appwrite-*`
    (chi giu mot danh sach header CHO PHEP), than request (`max_request_body_size="never"`);
  * token Bearer / JWT / khoa Appwrite (`standard_…`) / Tencent UserSig / khoa kieu `key=value`;
  * query string cua MOI URL (URL ky cua R2: `X-Amz-Signature`, `X-Amz-Credential`, …);
  * bien cuc bo cua stack frame (`include_local_variables=False`, va xoa `vars` neu con);
  * email, IP (`send_default_pii=False`, va xoa `user.email`/`user.ip_address`).

It on: chi loi 5xx / ngoai le chua bat (mac dinh cua tich hop FastAPI); log `logging` chi la
breadcrumb, KHONG thanh su kien; tracing TAT (`FAS_SENTRY_TRACES_SAMPLE_RATE`, mac dinh 0).

Moi truong: `development` / `staging` / `production` lay tu `FAS_ENV`. Release: SHA build
(`FAS_BUILD_SHA` hoac `RENDER_GIT_COMMIT` do Render tu dat) — `fanfic-api@<sha12>`.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from server.secret_redaction import SECRET_KEY_NAMES, loc_bo_theo_gia_tri

BIEN_DSN = "FAS_SENTRY_DSN"
BIEN_TRACES = "FAS_SENTRY_TRACES_SAMPLE_RATE"
DICH_VU = "fanfic-api"
AN = "<redacted>"

MOI_TRUONG = {"development": "development", "dev": "development", "local": "development",
              "staging": "staging", "production": "production", "prod": "production"}

#: Ten truong (so khop CHINH XAC sau khi ha chu) luon bi thay bang AN — bo sung cho
#: `SECRET_KEY_NAMES` nhung thu chi Sentry moi gap (header, UserSig Tencent, ...).
TEN_NHAY_CAM = SECRET_KEY_NAMES | frozenset({
    "set-cookie", "x-appwrite-key", "x-appwrite-session", "x-appwrite-jwt", "x-support-session",
    "x-api-key", "api-key", "proxy-authorization", "usersig", "user_sig", "sdksecretkey", "secret_key",
    "token", "session", "session_id", "jwt", "dsn", "signature", "x-amz-signature", "x-amz-credential",
    "x-amz-security-token", "password_hash",
})

#: CHI nhung header nay duoc giu lai trong `request.headers` cua su kien.
HEADER_CHO_PHEP = frozenset({"user-agent", "content-type", "content-length", "accept", "accept-language",
                             "host", "x-request-id", "cf-ray"})

_MAU = [
    # Query string cua moi URL (URL ky R2/S3, token tren link, ...): giu scheme+host+path.
    (re.compile(r"(https?://[^\s?#\"'<>]+)\?[^\s#\"'<>]*"), r"\1?" + AN),
    # Tham so ky AWS/R2 lot ra ngoai URL.
    (re.compile(r"(?i)\b(X-Amz-(?:Signature|Credential|Security-Token))=[^\s&\"'<>]+"), r"\1=" + AN),
    # Tencent UserSig (zlib+base64 bat dau `eJw`/`eJy`) va dang `usersig=...`.
    (re.compile(r"\beJ[wyz][A-Za-z0-9*_\-=+/]{20,}"), AN),
    (re.compile(r"(?i)\b(user_?sig)\s*[=:]\s*[^\s&\"',;]+"), r"\1=" + AN),
    # Cap `ten=gia_tri` bi mat (api_key=..., secret: ..., token=...).
    (re.compile(r"(?i)\b((?:[a-z_]*_)?(?:api[_-]?key|secret|token|password|passwd|signature|credential))"
                r"(\s*[=:]\s*)[^\s&\"',;]{4,}"), r"\1\2" + AN),
    # Email.
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
]


def loc_chuoi(s: str) -> str:
    """Che bi mat trong MOT chuoi tu do (thong diep loi, breadcrumb, gia tri extra)."""
    ra = loc_bo_theo_gia_tri(str(s))  # khoa Appwrite, Bearer, JWT — mau dung chung cua kho
    for mau, thay in _MAU:
        ra = mau.sub(thay, ra)
    return ra


def loc_url(u: Optional[str]) -> Optional[str]:
    if not u or not isinstance(u, str):
        return u
    try:
        p = urlsplit(u)
        return urlunsplit((p.scheme, p.netloc.rsplit("@", 1)[-1], p.path, "", ""))
    except ValueError:
        return loc_chuoi(u)


def loc_de_qui(du_lieu: Any, sau: int = 10) -> Any:
    if sau <= 0:
        return AN
    if isinstance(du_lieu, dict):
        return {k: (AN if isinstance(k, str) and k.strip().lower() in TEN_NHAY_CAM else loc_de_qui(v, sau - 1))
                for k, v in du_lieu.items()}
    if isinstance(du_lieu, (list, tuple)):
        return [loc_de_qui(v, sau - 1) for v in du_lieu]
    if isinstance(du_lieu, str):
        return loc_chuoi(du_lieu)
    return du_lieu


def _lam_sach_frame(fr: Dict[str, Any]) -> None:
    """Bo bien cuc bo; che luon cac dong NGU CANH MA NGUON (Sentry gui kem vai dong code quanh
    moi frame) — ma nguon khong chua gia tri luc chay, nhung mot literal hinh dang bi mat trong
    code (vd fixture) van khong duoc roi tien trinh. Do that bang bai end-to-end."""
    fr.pop("vars", None)
    if isinstance(fr.get("context_line"), str):
        fr["context_line"] = loc_chuoi(fr["context_line"])
    for k in ("pre_context", "post_context"):
        if isinstance(fr.get(k), list):
            fr[k] = [loc_chuoi(d) if isinstance(d, str) else d for d in fr[k]]


def _an_danh(uid: Any) -> str:
    return "u_" + hashlib.sha256(str(uid).encode("utf-8")).hexdigest()[:16]


def lam_sach_su_kien(event: Dict[str, Any], hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """`before_send` / `before_send_transaction`. KHONG nem loi: loi o day = mat su kien, nen moi
    buoc deu phong thu; neu chinh viec lam sach hong thi BO su kien (tra None) thay vi gui tho."""
    try:
        req = event.get("request")
        if isinstance(req, dict):
            for k in ("cookies", "data", "env"):
                req.pop(k, None)
            if req.get("query_string"):
                req["query_string"] = AN
            if "url" in req:
                req["url"] = loc_url(req.get("url"))
            hs = req.get("headers")
            if isinstance(hs, dict):
                req["headers"] = {k: loc_chuoi(v) for k, v in hs.items()
                                  if isinstance(k, str) and k.lower() in HEADER_CHO_PHEP}
        user = event.get("user")
        if isinstance(user, dict):
            event["user"] = {"id": _an_danh(user["id"])} if user.get("id") else {}
        for ex in ((event.get("exception") or {}).get("values") or []):
            if isinstance(ex.get("value"), str):
                ex["value"] = loc_chuoi(ex["value"])
            for fr in ((ex.get("stacktrace") or {}).get("frames") or []):
                _lam_sach_frame(fr)
        for th in ((event.get("threads") or {}).get("values") or []):
            for fr in ((th.get("stacktrace") or {}).get("frames") or []):
                _lam_sach_frame(fr)
        le = event.get("logentry")
        if isinstance(le, dict):
            if isinstance(le.get("message"), str):
                le["message"] = loc_chuoi(le["message"])
            if le.get("params"):
                le["params"] = loc_de_qui(le["params"])
            if isinstance(le.get("formatted"), str):
                le["formatted"] = loc_chuoi(le["formatted"])
        if isinstance(event.get("message"), str):
            event["message"] = loc_chuoi(event["message"])
        bc = event.get("breadcrumbs")
        vals = bc.get("values") if isinstance(bc, dict) else bc
        if isinstance(vals, list):
            sach = [lam_sach_breadcrumb(b) for b in vals]
            sach = [b for b in sach if b]
            if isinstance(bc, dict):
                bc["values"] = sach
            else:
                event["breadcrumbs"] = sach
        for khoa in ("extra", "contexts", "tags"):
            if event.get(khoa):
                event[khoa] = loc_de_qui(event[khoa])
        if isinstance(event.get("transaction"), str):
            event["transaction"] = loc_url(event["transaction"]) if "://" in event["transaction"] \
                else loc_chuoi(event["transaction"])
        return event
    except Exception:  # noqa: BLE001 — lam sach hong thi KHONG gui ban tho
        return None


def lam_sach_breadcrumb(crumb: Dict[str, Any], hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    try:
        if not isinstance(crumb, dict):
            return None
        if isinstance(crumb.get("message"), str):
            crumb["message"] = loc_chuoi(crumb["message"])
        data = crumb.get("data")
        if isinstance(data, dict):
            data = loc_de_qui(data)
            for k in ("url", "http.url", "to", "from"):
                if isinstance(data.get(k), str):
                    data[k] = loc_url(data[k])
            data.pop("http.query", None)
            data.pop("http.fragment", None)
            crumb["data"] = data
        return crumb
    except Exception:  # noqa: BLE001
        return None


def moi_truong(environment: str) -> str:
    return MOI_TRUONG.get((environment or "").strip().lower(), "development")


def ban_phat_hanh(env: Mapping[str, str]) -> Optional[str]:
    sha = (env.get("FAS_BUILD_SHA") or env.get("RENDER_GIT_COMMIT") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
        return None
    return f"{DICH_VU}@{sha[:12].lower()}"


def tuy_chon_sentry(settings: Any, env: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    """Tham so cho `sentry_sdk.init`, hoac None khi TAT. Tach rieng de test kiem ma khong gui gi."""
    dsn = (env.get(BIEN_DSN) or "").strip()
    if not dsn:
        return None
    try:
        traces = float(env.get(BIEN_TRACES) or 0.0)
    except ValueError:
        traces = 0.0
    return {
        "dsn": dsn,
        "environment": moi_truong(getattr(settings, "environment", "")),
        "release": ban_phat_hanh(env),
        "sample_rate": 1.0,
        "traces_sample_rate": max(0.0, min(traces, 0.2)),
        "send_default_pii": False,
        "include_local_variables": False,
        "max_request_body_size": "never",
        "max_breadcrumbs": 30,
        "attach_stacktrace": False,
        "before_send": lam_sach_su_kien,
        "before_send_transaction": lam_sach_su_kien,
        "before_breadcrumb": lam_sach_breadcrumb,
    }


def khoi_tao_sentry(settings: Any, env: Optional[Mapping[str, str]] = None, **them: Any) -> bool:
    """Goi MOT lan truoc khi tao app. TAT (khong DSN) -> False, khong import `sentry_sdk`."""
    env = os.environ if env is None else env
    tuy = tuy_chon_sentry(settings, env)
    if tuy is None:
        return False
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    tuy["integrations"] = [
        StarletteIntegration(transaction_style="endpoint"),
        FastApiIntegration(transaction_style="endpoint"),
        # Log chi la breadcrumb (INFO+); KHONG bien dong log nao thanh su kien — it on.
        LoggingIntegration(level=logging.INFO, event_level=None),
    ]
    tuy.update(them)
    sentry_sdk.init(**tuy)
    sentry_sdk.set_tag("service", DICH_VU)
    if tuy.get("release"):
        sentry_sdk.set_tag("build", tuy["release"].split("@", 1)[1])
    return True
