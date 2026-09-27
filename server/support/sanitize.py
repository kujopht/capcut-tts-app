"""
Lam sach + chuan hoa cho Fanfic AI Support.

Moi chuoi den tu trinh duyet (thong bao loi, duong dan, mo ta cua nguoi dung)
deu co the chua thu khong duoc luu: token trong URL, URL ky co `X-Amz-*`,
email, khoa API dan nham. Ham o day chay o MAY CHU — client cung lam sach
truoc khi gui (`web/src/lib/support/sanitize.ts`), nhung may chu khong bao gio
tin client.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

DA_CHE = "[đã che]"

_URL = re.compile(r"(?i)\b(https?://)(?:[^\s/@]+@)?([^\s/?#]+)([^\s?#]*)(?:[?#][^\s]*)?")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]+)?")
_KV = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret(?:[_-]?key)?|access[_-]?token|refresh[_-]?token|token|password|passwd|pwd|"
    r"sig|signature|user[_-]?sig|x-amz-[a-z-]+|authorization|cookie|session(?:[_-]?id)?|credential[s]?)"
    r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)")
_AWS = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_HEX_DAI = re.compile(r"\b[0-9a-fA-F]{32,}\b")
#: Chuoi dai kieu token: PHAI co ca chu hoa, chu thuong va so — slug duong dan
#: ("tinh-ha-van-dam-chuong-13") khong bi che nham; khong co "/" vi cung ly do.
_B64_DAI = re.compile(r"\b(?=[A-Za-z0-9+_-]*\d)(?=[A-Za-z0-9+_-]*[A-Z])(?=[A-Za-z0-9+_-]*[a-z])[A-Za-z0-9+_-]{32,}={0,2}")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DIEU_KHIEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _url_sach(m: re.Match) -> str:
    """Giu scheme + host + duong dan; BO user:pass@, query va fragment."""
    return f"{m.group(1)}{m.group(2)}{m.group(3)}"


def sach_chuoi(s: Optional[str], toi_da: int = 500) -> str:
    """Chuoi an toan de luu/hien/gui cho mo hinh. Thu tu co y: URL truoc (bo
    query chua token), roi cac mau bi mat, roi email/IP, cuoi cung cat do dai."""
    if not s:
        return ""
    # Cat TRUOC khi chay regex: cac mau co lookahead la O(n^2) o truong hop xau;
    # chan dau vao o 2*toi_da (>= 2000) giu moi lan lam sach o muc micro giay.
    t = _DIEU_KHIEN.sub(" ", str(s)[: max(2 * toi_da, 2000)])
    t = _URL.sub(_url_sach, t)
    t = _BEARER.sub(f"Bearer {DA_CHE}", t)
    t = _JWT.sub(DA_CHE, t)
    t = _KV.sub(lambda m: f"{m.group(1)}{m.group(2)}{DA_CHE}", t)
    t = _AWS.sub(DA_CHE, t)
    t = _HEX_DAI.sub(DA_CHE, t)
    t = _B64_DAI.sub(DA_CHE, t)
    t = _EMAIL.sub("[email]", t)
    t = _IP.sub("[ip]", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:toi_da]


# ------------------------------------------------------------------ route
#: Moi trang co tham so cua web (`web/src/app/**/[param]/page.tsx`). Bai test
#: `test_support_sanitize` quet thu muc web va doi chieu — them trang moi ma
#: quen o day thi test do.
MAU_ROUTE = (
    ("/novels/", "/novels/[id]"),
    ("/chapters/", "/chapters/[id]"),
    ("/u/", "/u/[username]"),
    ("/posts/", "/posts/[postId]"),
    ("/animation/watch/", "/animation/watch/[id]"),
    ("/studio/projects/", "/studio/projects/[id]"),
)
#: Route tinh `/animation/new` nam cung tien to voi `/animation/[id]`.
_ROUTE_TINH = {"/animation/new"}
_ID_DOAN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def chuan_hoa_route(duong: Optional[str]) -> str:
    """Duong dan -> MAU route (khong id, khong query). Chuoi la -> "/?"."""
    if not duong:
        return "/?"
    p = str(duong).strip()
    p = re.sub(r"(?i)^https?://[^/]+", "", p)  # bo scheme + host neu client gui ca URL
    p = p.split("?", 1)[0].split("#", 1)[0]
    if not p.startswith("/") or len(p) > 300 or "//" in p or ".." in p:
        return "/?"
    p = re.sub(r"/+$", "", p) or "/"
    if p in _ROUTE_TINH:
        return p
    for tien_to, mau in MAU_ROUTE:
        if p.startswith(tien_to):
            doan = p[len(tien_to):].split("/")
            if doan and _ID_DOAN.match(doan[0] or "-"):
                duoi = "/".join(doan[1:])
                return mau + (f"/{duoi}" if duoi else "")
    if p.startswith("/animation/") and p.count("/") == 2:
        return "/animation/[id]"
    if p.startswith("/admin/"):
        # Trang admin co tham so: giu nhanh, thay doan giong id.
        return "/" + "/".join("[id]" if re.search(r"\d", s) and len(s) > 6 else s for s in p.strip("/").split("/"))
    return p if re.match(r"^[/A-Za-z0-9_\[\]-]+$", p) else "/?"


def lay_id_tu_route(duong: Optional[str], tien_to: str) -> Optional[str]:
    """`/chapters/abc` + `/chapters/` -> `abc` (da kiem mau id), khong thi None."""
    if not duong:
        return None
    p = str(duong).split("?", 1)[0]
    if not p.startswith(tien_to):
        return None
    doan = p[len(tien_to):].split("/")[0]
    return doan if _ID_DOAN.match(doan or "-") else None


# ------------------------------------------------------------------ loi
_SO = re.compile(r"\b\d+(?:\.\d+)?\b")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_ID_TRON = re.compile(r"\b(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{12,}\b")
_NHAY = re.compile(r"(\"[^\"]{0,200}\"|'[^']{0,200}'|`[^`]{0,200}`)")


def chuan_hoa_loi(thong_bao: Optional[str]) -> str:
    """Thong bao loi -> dang chuan de GOM NHOM: bo so, id, chuoi trong ngoac,
    query — hai lan hong giong nhau o hai chuong khac nhau phai ra CUNG mot chuoi."""
    t = sach_chuoi(thong_bao, 400).lower()
    t = _URL.sub(lambda m: f"{m.group(2)}{chuan_hoa_route(m.group(3) or '/')}", t)
    t = _UUID.sub("<id>", t)
    t = _ID_TRON.sub("<id>", t)
    t = _NHAY.sub("<s>", t)
    t = _SO.sub("#", t)
    t = re.sub(r"\s+", " ", t).strip(" .:")
    return t[:160] or "(không có thông báo)"


def dau_van_tay(route_mau: str, loi_chuan: str, he_thong: str) -> str:
    """Dau van tay GOM NHOM su co: cung trang + cung loi chuan + cung phan he.
    Ban build KHONG nam trong dau van tay — cung mot loi qua nhieu lan deploy
    la MOT su co (danh sach build duoc theo doi rieng trong su co)."""
    return hashlib.sha256(f"{route_mau}|{loi_chuan}|{he_thong}".encode("utf-8")).hexdigest()[:16]


def bam_an_danh(gia_tri: str, muoi: str) -> str:
    """Dem "so nguoi bi anh huong" ma khong luu id tho cua khach."""
    return hashlib.sha256(f"{muoi}|{gia_tri}".encode("utf-8")).hexdigest()[:16]


_TRINH_DUYET = ("edge", "chrome", "firefox", "safari", "samsung", "opera", "coc_coc", "other")
_THIET_BI = ("desktop", "tablet", "mobile", "other")


def trinh_duyet(gia_tri: Optional[str]) -> str:
    v = (gia_tri or "").strip().lower()
    return v if v in _TRINH_DUYET else "other"


def thiet_bi(gia_tri: Optional[str]) -> str:
    v = (gia_tri or "").strip().lower()
    return v if v in _THIET_BI else "other"


def ban_build(gia_tri: Optional[str]) -> str:
    v = (gia_tri or "").strip()
    return v if re.match(r"^[A-Za-z0-9._-]{1,40}$", v) else "unknown"


def ma_loi(gia_tri: Optional[str]) -> str:
    """Ma loi do client/may chu dat — CHI chu thuong, so, `_`, `.`, `-`."""
    v = (gia_tri or "").strip().lower()
    return v if re.match(r"^[a-z0-9_.-]{1,48}$", v) else ""
