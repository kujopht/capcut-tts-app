#!/usr/bin/env python3
"""Danh sach cho phep (allowlist) va cac phep khang dinh cua cutover
GCE -> AWS. Thuan tuy, khong I/O, khong mang — de test duoc het.

VI SAO TACH RIENG TEP NAY
-------------------------
Toan bo tinh an toan cua cuoc cutover nam o mot cau hoi duy nhat: *cai
worker sap khoi dong co dang tro dung vao production that khong, va co
dang tro NHAM vao staging khong*. Cau hoi do phai tra loi duoc bang mot
ham thuan tuy, chay duoc trong unit test, khong can may that, khong can
credential.

Moi phep kiem o day **fail closed**: thieu du lieu la TU CHOI, khong phai
"cho qua vi khong ro".

KHONG BAO GIO in gia tri bi mat. Cac ham nhan `dict` env va chi tra ve
ten bien + phan loai; gia tri duy nhat duoc phep hien ra la nhung toa do
KHONG bi mat (endpoint, project, database, bucket, backend) — dung cung
mot ly le nhu `fanfic_staging_admin.sh`: ten bucket khong phai bi mat, va
no la thu quan trong nhat can doc duoc de biet co tro nham hay khong.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Tuple

# --------------------------------------------------------------------------
# TOA DO PRODUCTION — nguon su that duy nhat trong ma nguon.
#
# Do that ngay 2026-09-04 tu dich vu Render `fas-prod-api` qua
# `fanfic_credential_broker.render_non_secret_env` (allowlist ap o chieu
# TRA VE, nen mot bien bi doi ten phia Render khong the noi rong duoc).
#
# Luu y kien truc QUAN TRONG: production KHONG dung Appwrite Cloud. No
# dung ban TU LUU TRU o `appwrite-dev.fanfic.world` (may GCE
# `fanfic-appwrite-temp`). `docs/AWS_STAGING_MIGRATION.md` muc 0 noi
# nguoc lai — tai lieu do da CU. Xem `docs/PRODUCTION_CUTOVER.md`.
# --------------------------------------------------------------------------
PROD_APPWRITE_ENDPOINT = "https://appwrite-dev.fanfic.world/v1"
PROD_APPWRITE_PROJECT_ID = "fanfic-world-prod"
PROD_APPWRITE_DATABASE_ID = "fanfic_world_prod"
PROD_R2_BUCKET = "fanfic-prod"

#: Bucket cua staging. Dung de PHAN BIET, khong phai de cho phep: mot tep
#: env production ma tro vao day la sai huong nghiem trong.
STAGING_R2_BUCKETS = ("fanfic-staging", "fanfic-dev")

#: Bien bat buoc phai co gia tri trong tep env cua worker production.
#: Lay tu `server/config.py::Settings.validate()` cho DATA_BACKEND=appwrite
#: + STORAGE_BACKEND=r2. Worker khong phuc vu HTTP nen khong co bien CORS
#: hay auth-token nao trong danh sach nay.
REQUIRED_ENV_NAMES: Tuple[str, ...] = (
    "FAS_ENV",
    "DATA_BACKEND",
    "STORAGE_BACKEND",
    "FAS_INLINE_WORKER",
    "APPWRITE_ENDPOINT",
    "APPWRITE_PROJECT_ID",
    "APPWRITE_DATABASE_ID",
    "APPWRITE_API_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    # CHINH SACH GIONG — bat buoc, khong phai tuy chon.
    #
    # Thieu `FAS_LOCAL_VOICES` thi `voice_is_local_allowed()` tra False cho
    # MOI giong, worker NHAN job roi that bai voi "Giọng '...' hiện không
    # được cung cấp." Job chet chu khong duoc nhuong. Da xay ra that mot lan
    # tren staging (xem `git log` PR #136) va no ton mot vong chung minh.
    "FAS_LOCAL_VOICES",
    "FAS_PUBLIC_VOICE_LANGUAGES",
)

#: Nhung bien mang gia tri BI MAT. Khong bao giờ in gia tri cua chung —
#: chi bao CO/THIEU va do dai.
SECRET_ENV_NAMES: Tuple[str, ...] = (
    "APPWRITE_API_KEY",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ACCOUNT_ID",
)

#: Gia tri co dinh bat buoc. Sai mot trong nhung cai nay la worker se lam
#: sai viec (vi du `FAS_INLINE_WORKER=true` bien tien trinh worker thanh
#: mot tien trinh tu cam chinh minh — loi that da gap, xem
#: `docs/reports/staging/BAO_CAO_STAGING.md` muc 3).
FIXED_ENV_VALUES: Dict[str, str] = {
    "FAS_ENV": "production",
    "DATA_BACKEND": "appwrite",
    "STORAGE_BACKEND": "r2",
    "FAS_INLINE_WORKER": "false",
}

#: Unit systemd cua worker PRODUCTION. Danh sach DONG CUNG.
PROD_UNITS: Tuple[str, ...] = (
    "fanfic-worker-prod.service",
    "fanfic-translation-worker-prod.service",
    "fanfic-worker-prod-health.timer",
)

#: Unit STAGING tren chinh may AWS. Phai TAT truoc khi bat production —
#: mot may chay ca hai la mot may claim job cua ca hai du an.
STAGING_UNITS: Tuple[str, ...] = (
    "fanfic-worker.service",
    "fanfic-translation-worker.service",
    "fanfic-worker-health.timer",
)


class CutoverRefused(Exception):
    """Mot phep khang dinh that bai. Luon fail closed."""


def _sach(v: Optional[str]) -> str:
    """Chuan hoa mot gia tri env: bo khoang trang va \\r cua CRLF.

    Tep env tung mang CRLF that (script scp tu Windows) va hau qua la
    `APPWRITE_ENDPOINT` co \\r o cuoi -> `InvalidURL: ... '\\r' at position
    36`. `systemd` cat \\r khi doc EnvironmentFile nhung `bash .` thi khong,
    nen hai ben tung thay hai gia tri khac nhau tu CUNG mot tep.
    """
    return (v or "").strip().strip("\r")


def phan_loai_bucket(bucket: Optional[str]) -> str:
    """`production` | `staging` | `unknown`. Khong nem loi — de ben goi quyet dinh."""
    b = _sach(bucket)
    if b == PROD_R2_BUCKET:
        return "production"
    if b in STAGING_R2_BUCKETS:
        return "staging"
    return "unknown"


def thieu_bien(env: Mapping[str, str]) -> List[str]:
    """Ten cac bien bat buoc dang thieu hoac rong. Chi TEN, khong gia tri."""
    return [n for n in REQUIRED_ENV_NAMES if not _sach(env.get(n))]


def khang_dinh_production(env: Mapping[str, str]) -> None:
    """Tep env nay CO PHAI production that khong. Nem `CutoverRefused` neu khong.

    Day la cong duy nhat truoc khi bat worker production tren may moi.
    Thu tu kiem duoc chon co y: bien thieu -> gia tri co dinh -> danh tinh
    Appwrite -> bucket R2. Cai cuoi cung la cai nguy hiem nhat nen no duoc
    kiem sau cung, khi moi thu khac da chac chan.
    """
    thieu = thieu_bien(env)
    if thieu:
        raise CutoverRefused(f"thieu bien bat buoc: {', '.join(thieu)}")

    for ten, mong_muon in FIXED_ENV_VALUES.items():
        thuc_te = _sach(env.get(ten)).lower()
        if thuc_te != mong_muon:
            raise CutoverRefused(
                f"{ten} phai la {mong_muon!r}, dang la {thuc_te!r}")

    cap = (
        ("APPWRITE_ENDPOINT", PROD_APPWRITE_ENDPOINT),
        ("APPWRITE_PROJECT_ID", PROD_APPWRITE_PROJECT_ID),
        ("APPWRITE_DATABASE_ID", PROD_APPWRITE_DATABASE_ID),
    )
    for ten, mong_muon in cap:
        thuc_te = _sach(env.get(ten))
        if thuc_te != mong_muon:
            raise CutoverRefused(
                f"{ten} khong khop production: mong doi {mong_muon!r}, "
                f"dang la {thuc_te!r}")

    loai = phan_loai_bucket(env.get("R2_BUCKET"))
    if loai == "staging":
        raise CutoverRefused(
            f"R2_BUCKET={_sach(env.get('R2_BUCKET'))!r} la bucket STAGING — "
            "tep env production khong duoc tro vao day")
    if loai != "production":
        raise CutoverRefused(
            f"R2_BUCKET={_sach(env.get('R2_BUCKET'))!r} khong nam trong "
            f"allowlist (production={PROD_R2_BUCKET!r})")


def khang_dinh_khong_phai_production(env: Mapping[str, str]) -> None:
    """Chieu NGUOC LAI: tep env nay phai KHONG tro vao production.

    Dung cho cac unit staging con lai tren cung may AWS. Neu mot ngay nao
    do env staging bi ghi de bang gia tri production thi hai worker se
    tranh claim job THAT — che do that bai nguy hiem nhat cua ca ke hoach.
    """
    bucket = phan_loai_bucket(env.get("R2_BUCKET"))
    project = _sach(env.get("APPWRITE_PROJECT_ID"))
    if bucket == "production":
        raise CutoverRefused(
            "env nay tro vao bucket PRODUCTION nhung dang duoc dung cho staging")
    if project == PROD_APPWRITE_PROJECT_ID:
        raise CutoverRefused(
            "env nay tro vao du an Appwrite PRODUCTION nhung dang duoc dung "
            "cho staging")


def kiem_unit_production(unit: str) -> None:
    """Chi ba unit production duoc phep. Fail closed."""
    if unit not in PROD_UNITS:
        raise CutoverRefused(f"unit {unit!r} khong nam trong danh sach production")


def kiem_unit_staging(unit: str) -> None:
    if unit not in STAGING_UNITS:
        raise CutoverRefused(f"unit {unit!r} khong nam trong danh sach staging")


def tom_tat_env(env: Mapping[str, str]) -> List[str]:
    """Dong tom tat AN TOAN de in ra log/bao cao.

    Bien bi mat -> `<CO len=N>` hoac `<THIEU>`. Toa do khong bi mat -> in
    thang, vi khong doc duoc chung thi khong biet co tro nham hay khong.
    """
    dong: List[str] = []
    for ten in REQUIRED_ENV_NAMES:
        gt = _sach(env.get(ten))
        if ten in SECRET_ENV_NAMES:
            dong.append(f"{ten}=<CO len={len(gt)}>" if gt else f"{ten}=<THIEU>")
        elif ten == "R2_BUCKET":
            dong.append(f"{ten}={gt or '<TRONG>'}  [{phan_loai_bucket(gt)}]")
        else:
            dong.append(f"{ten}={gt or '<TRONG>'}")
    return dong


def doc_env_text(noi_dung: str) -> Dict[str, str]:
    """Doc dinh dang `KEY=VALUE` cua systemd EnvironmentFile.

    Bo qua dong trong va dong `#`. Chuan hoa CRLF. Dong sau ghi de dong
    truoc — dung nhu `systemd` va nhu `grep ... | tail -1` ma cac script
    ops khac dang dung.
    """
    ra: Dict[str, str] = {}
    for dong in noi_dung.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        d = dong.strip()
        if not d or d.startswith("#") or "=" not in d:
            continue
        k, _, v = d.partition("=")
        ra[k.strip()] = v
    return ra


def render_env_text(env: Mapping[str, str], ten: Iterable[str] = REQUIRED_ENV_NAMES) -> str:
    """Sinh noi dung tep env, LF thuan, ket thuc bang mot dong moi.

    LF thuan la co y: xem `_sach()`. Tep nay se duoc ghi bang root tren may
    dich voi quyen 0640 root:fanfic.
    """
    dong = []
    for k in ten:
        v = _sach(env.get(k))
        if not v:
            raise CutoverRefused(f"khong the sinh env: {k} rong")
        dong.append(f"{k}={v}")
    return "\n".join(dong) + "\n"
