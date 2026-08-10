"""
Chinh sach cua TAC GIA: username cong khai, trang thai duyet, hang tac gia, va
quy tac tinh mot lan nghe hop le.

Module nay la Python THUAN — khong FastAPI, khong Appwrite, khong mang, khong
dong ho toan cuc (moi ham nhan `now` de test dieu khien duoc thoi gian). Ly do:
day la nhung quy tac ma sai mot chut la sai ca he thong uy tin, nen chung phai
kiem duoc ma khong can dung ha tang nao.

BA khai niem KHAC NHAU, va viec tach chung ra la co y:

    NGUOI DUNG      ai cung co. Doc, nghe, tao ban nhap.
    TRANG THAI TAC GIA  duoc phep XUAT BAN cong khai hay khong. Day la moderation.
    HANG TAC GIA    uy tin, tinh tu so lan nghe hop le. Day KHONG phai xac minh.

Mot tac giai hang cao van co the bi treo. Mot tac gia moi duoc duyet van o hang
thap nhat. Dung hang de ngu y "da duoc kiem duyet" la sai, va giao dien phai ve
hai thu bang hai ngon ngu thi giac khac nhau.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from server.domain import AuthorStatus

# =============================================================================
# Username cong khai
# =============================================================================
#
# Vi sao khong dung phan truoc dau @ cua email: no la du lieu RIENG TU bi bien
# thanh danh tinh CONG KHAI vinh vien. Nguoi dung dang ky bang
# `ten.thatcuatoi.1998@gmail.com` khong he dong y cho ca the gioi thay chuoi do.
# Nen username la mot buoc nguoi dung TU chon, va cho tra loi thi ho chua co
# trang cong khai — khong phai bi gan mot cai ten ho khong chon.

USERNAME_MIN = 3
USERNAME_MAX = 24

#: Chi chu khong dau, so, gach duoi, gach ngang. KHONG cho dau cach va KHONG cho
#: dau tieng Viet: username di trong URL va bi nguoi ta doc qua dien thoai cho
#: nhau, nen `kedetmong` an hon `kẻ-dệt-mộng`. Ten hien thi moi la cho de dau.
USERNAME_RE = re.compile(r"^[a-z0-9_]+(?:-[a-z0-9_]+)*$")

#: Ten bi GIU LAI. Hai nhom:
#:   1. duong dan that cua site — de `/u/login` khong bao gio dam vao `/login`
#:      neu sau nay co ai doi cach dinh tuyen;
#:   2. cac ten ngu y quyen han — `admin`, `mod`, `support`. Mot nguoi dung ten
#:      `support` co the lua nguoi khac tin ho la nhan vien.
RESERVED_USERNAMES = frozenset({
    "admin", "administrator", "root", "system", "support", "help", "staff",
    "mod", "moderator", "official", "fanfic", "fanficworld", "team",
    "api", "auth", "login", "logout", "register", "signup", "signin",
    "account", "settings", "creator", "studio", "write", "library",
    "explore", "novels", "chapters", "search", "u", "user", "users",
    "me", "you", "null", "undefined", "anonymous", "guest", "deleted",
})


class UsernameError(ValueError):
    """Username khong dung quy tac. Thong bao da o dang doc duoc cho nguoi dung."""


class UsernameTaken(UsernameError):
    """
    Ten hop le nhung da co nguoi khac dung.

    Tach khoi `UsernameError` de tang HTTP tra 409 thay vi 400: "ten nay sai quy
    tac" va "ten nay da co nguoi dung" la hai viec khac nhau voi nguoi dung, va
    tra cung mot ma thi giao dien khong noi dung duoc cau nao.
    """


def normalize_username(raw: str) -> str:
    """
    Dang CHUAN de so khop va de kiem trung.

    Bo dau, ha chu thuong, doi dau cach thanh gach ngang. Nho vay `Kẻ Dệt Mộng`
    va `ke-det-mong` cham vao cung mot o — hai nguoi khong the lay hai username
    ma nguoi doc nhin thay nhu nhau.

    KHONG kiem tra hop le o day: `normalize` va `validate` la hai viec, va gop
    lai thi khong con cho nao goi normalize ma khong muon ngoai le.
    """
    text = unicodedata.normalize("NFKD", (raw or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = text.lower()
    text = re.sub(r"[\s.]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def validate_username(raw: str) -> str:
    """Tra ve dang chuan, hoac nem `UsernameError` voi ly do doc duoc."""
    name = normalize_username(raw)
    if len(name) < USERNAME_MIN:
        raise UsernameError(f"Tên người dùng cần ít nhất {USERNAME_MIN} ký tự.")
    if len(name) > USERNAME_MAX:
        raise UsernameError(f"Tên người dùng dài quá {USERNAME_MAX} ký tự.")
    if not USERNAME_RE.match(name):
        raise UsernameError(
            "Tên người dùng chỉ gồm chữ không dấu, số, gạch dưới và gạch ngang."
        )
    if name in RESERVED_USERNAMES:
        raise UsernameError("Tên người dùng này được hệ thống giữ lại.")
    return name


def suggest_username(display_name: str, email: str, taken: Sequence[str] = ()) -> str:
    """
    Mot GOI Y de dien san vao o nhap — khong phai mot cai ten duoc gan tu dong.

    Uu tien ten hien thi; ten hien thi khong dung duoc thi moi lay phan truoc
    dau @ cua email, va day la GOI Y nen nguoi dung con sua duoc truoc khi no
    thanh cong khai.
    """
    da_co = {normalize_username(t) for t in taken}
    for nguon in (display_name, (email or "").split("@")[0]):
        goc = normalize_username(nguon)
        if len(goc) < USERNAME_MIN or not USERNAME_RE.match(goc):
            continue
        goc = goc[:USERNAME_MAX]
        if goc not in da_co and goc not in RESERVED_USERNAMES:
            return goc
        for i in range(2, 100):
            hau = f"-{i}"
            ung = f"{goc[:USERNAME_MAX - len(hau)]}{hau}"
            if ung not in da_co and ung not in RESERVED_USERNAMES:
                return ung
    return ""


# =============================================================================
# Trang thai tac gia
# =============================================================================

#: Cac buoc chuyen HOP LE. Bang nay la nguon su that duy nhat; khong cho nao
#: khac duoc tu quyet dinh mot buoc chuyen co duoc phep hay khong.
#:
#: Doc bang:
#:   none      -> pending    nguoi dung gui don
#:   pending   -> approved   nguoi duyet dong y
#:   pending   -> rejected   nguoi duyet tu choi
#:   rejected  -> pending    gui lai don
#:   approved  -> suspended  bi treo
#:   suspended -> approved   phuc hoi
#:
#: KHONG co `none -> approved`: moi tac gia deu phai di qua mot ban ghi don, ke
#: ca khi duoc grandfather — migration tao don voi trang thai `approved` kem ghi
#: chu, chu khong nhay buoc. Nho vay lich su luon giai thich duoc.
TRANSITIONS: Dict[AuthorStatus, frozenset] = {
    AuthorStatus.NONE: frozenset({AuthorStatus.PENDING}),
    AuthorStatus.PENDING: frozenset({AuthorStatus.APPROVED, AuthorStatus.REJECTED}),
    AuthorStatus.APPROVED: frozenset({AuthorStatus.SUSPENDED}),
    AuthorStatus.REJECTED: frozenset({AuthorStatus.PENDING}),
    AuthorStatus.SUSPENDED: frozenset({AuthorStatus.APPROVED}),
}

#: Cho nop lai don sau khi bi tu choi. Khong chan vinh vien — nguoi ta co the
#: viet lai gioi thieu cho tu te hon — nhung cung khong de nop lai lien tuc.
RESUBMIT_COOLDOWN = timedelta(days=3)


class AuthorStateError(ValueError):
    """Buoc chuyen trang thai khong hop le. Thong bao doc duoc cho nguoi dung."""


def can_transition(cu: AuthorStatus, moi: AuthorStatus) -> bool:
    return moi in TRANSITIONS.get(cu, frozenset())


def can_publish(status: AuthorStatus) -> bool:
    """CHI tac gia da duyet duoc xuat ban cong khai. Ban nhap thi ai cung viet."""
    return status is AuthorStatus.APPROVED


def can_resubmit(
    status: AuthorStatus,
    decided_at: Optional[str],
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Co duoc nop lai don khong, va neu khong thi vi sao.

    Tra ve `(duoc, ly_do)` chu khong nem ngoai le: giao dien can HIEN ly do
    ngay khi ve trang, truoc khi nguoi dung bam gi.
    """
    if status is AuthorStatus.NONE:
        return True, ""
    if status is AuthorStatus.PENDING:
        return False, "Đơn của bạn đang chờ duyệt."
    if status is AuthorStatus.APPROVED:
        return False, "Bạn đã là tác giả."
    if status is AuthorStatus.SUSPENDED:
        return False, "Quyền xuất bản của bạn đang bị tạm dừng."
    # rejected
    if not decided_at:
        return True, ""
    moc = _parse_iso(decided_at)
    if moc is None:
        return True, ""
    con = (moc + RESUBMIT_COOLDOWN) - (now or datetime.now(timezone.utc))
    if con.total_seconds() > 0:
        ngay = max(1, int(con.total_seconds() // 86400) + 1)
        return False, f"Bạn có thể gửi lại đơn sau {ngay} ngày."
    return True, ""


def _parse_iso(text: str) -> Optional[datetime]:
    try:
        moc = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return moc if moc.tzinfo else moc.replace(tzinfo=timezone.utc)


# =============================================================================
# Hang tac gia
# =============================================================================
#
# MOT cho duy nhat dinh nghia hang. Nguong nam o day, khong nam trong component,
# khong nam trong cau truy van, khong nam trong mot bang o tai lieu roi lech dan
# so voi ma nguon.


@dataclass(frozen=True)
class RankTier:
    #: Khoa on dinh — di vao API va vao class CSS. KHONG bao gio doi, ke ca khi
    #: doi ten hien thi: doi khoa la lam hong moi anh chup, moi test, va huy
    #: hieu cua moi tac gia cung luc.
    key: str
    #: Ten hien thi, tieng Viet.
    title: str
    #: So lan nghe hop le toi thieu.
    min_listens: int
    #: Bac 1..6 — giao dien dung de chon do dam cua huy hieu.
    level: int


#: Nguong o day la nguong CHO PHAT TRIEN: chung du thap de du lieu mock hien
#: duoc ca sau bac, va du cach nhau de thay bac tang co nghia. Truoc khi mo cho
#: nguoi that, xem lai bang nay bang so lieu that.
RANK_TIERS: Tuple[RankTier, ...] = (
    RankTier("tan_but", "Tân Bút", 0, 1),
    RankTier("nguoi_ke_chuyen", "Người Kể Chuyện", 50, 2),
    RankTier("ke_det_mong", "Kẻ Dệt Mộng", 250, 3),
    RankTier("bien_nien_su_gia", "Biên Niên Sử Gia", 1_000, 4),
    RankTier("huyen_thoai_di_gioi", "Huyền Thoại Dị Giới", 5_000, 5),
    RankTier("than_but", "Thần Bút", 20_000, 6),
)


def rank_for(qualified_listens: int) -> RankTier:
    """Hang cao nhat ma so lan nghe nay dat toi."""
    dat = RANK_TIERS[0]
    for tier in RANK_TIERS:
        if qualified_listens >= tier.min_listens:
            dat = tier
        else:
            break
    return dat


def next_rank(qualified_listens: int) -> Optional[RankTier]:
    """Hang ke tiep, hoac `None` khi da o hang cao nhat."""
    for tier in RANK_TIERS:
        if qualified_listens < tier.min_listens:
            return tier
    return None


def rank_progress(qualified_listens: int) -> Dict[str, object]:
    """
    Hang hien tai + chang duong toi hang sau, o dang API dung duoc ngay.

    Tinh o BACKEND chu khong o giao dien: nguong la chinh sach, va mot ban
    frontend cu dang chay trong tab cua ai do khong duoc phep ve mot hang khac
    voi hang ma may chu cong nhan.
    """
    hien = rank_for(qualified_listens)
    sau = next_rank(qualified_listens)
    con = max(0, sau.min_listens - qualified_listens) if sau else 0
    if sau:
        khoang = max(1, sau.min_listens - hien.min_listens)
        phan_tram = int(round(100.0 * (qualified_listens - hien.min_listens) / khoang))
    else:
        phan_tram = 100
    return {
        "key": hien.key,
        "title": hien.title,
        "level": hien.level,
        "qualified_listens": qualified_listens,
        "next_key": sau.key if sau else None,
        "next_title": sau.title if sau else None,
        "next_at": sau.min_listens if sau else None,
        "remaining": con,
        "percent": max(0, min(100, phan_tram)),
    }


# =============================================================================
# Mot lan nghe HOP LE
# =============================================================================
#
# Day la cho de bi lam dung nhat trong ca he thong, nen ban V1 co y THAT CHAT
# va bo qua nhung truong hop khong chac. Bo sot mot lan nghe that thi tac giai
# len hang cham hon mot chut; dem mot lan nghe gia thi ca bang xep hang thanh
# vo nghia.

#: Nghe du lau moi tinh. Bam Phat roi tat ngay khong phai la mot lan nghe.
QUALIFY_SECONDS = 30.0

#: Audio ngan hon `QUALIFY_SECONDS / QUALIFY_RATIO` thi lay theo TI LE. Mot
#: chuong dai 24 giay khong bao gio dat nguong 30 giay, va neu chi dung nguong
#: tuyet doi thi cac chuong ngan vinh vien khong duoc tinh.
QUALIFY_RATIO = 0.75

#: Mot nguoi nghe chi tinh MOT lan cho mot chuong trong 24 gio.
DEDUPE_WINDOW = timedelta(hours=24)


class ListenRejection(str):
    """Ly do khong tinh — dung lam ma tra ve cho API va cho test."""


#: Cac ma ly do. Chuoi on dinh, di vao API.
NOT_AUTHENTICATED = "khong_dang_nhap"
TOO_SHORT = "chua_du_lau"
OWN_CHAPTER = "tu_nghe"
ALREADY_CREDITED = "da_tinh_trong_24h"
CREDITED = "da_tinh"


def required_seconds(duration_seconds: float) -> float:
    """
    Nghe bao lau thi tinh, voi mot ban audio dai `duration_seconds`.

    Chuong dai: 30 giay. Chuong ngan: 75% do dai. Khong biet do dai (0 hoac
    thieu): quay ve 30 giay — tha kho tinh han la tinh sai.
    """
    if duration_seconds and duration_seconds > 0:
        return min(QUALIFY_SECONDS, duration_seconds * QUALIFY_RATIO)
    return QUALIFY_SECONDS


def dedupe_day_bucket(now: Optional[datetime] = None) -> int:
    """
    So thu tu ngay UTC. Dung lam thanh phan cua khoa TAT DINH chong dua.

    Vi sao can no ben canh phep kiem 24 gio truot: phep kiem kia la DOC roi
    GHI, va hai request cung luc deu doc thay "chua co" roi cung ghi. Mot khoa
    tat dinh theo ngay bien buoc ghi thu hai thanh mot xung dot khoa, nen truong
    hop xau nhat cua mot cuoc dua la MOT lan tinh, khong phai hai.
    """
    moment = now or datetime.now(timezone.utc)
    return int(moment.timestamp() // 86400)


def credit_key(listener_id: str, chapter_id: str,
               now: Optional[datetime] = None) -> str:
    """
    Khoa tat dinh cua mot lan tinh. Cung cach lam nhu `job_locks`.

    Bam thay vi noi chuoi: Appwrite gioi han `rowId` 36 ky tu.
    """
    thong = f"{listener_id}\x1f{chapter_id}\x1f{dedupe_day_bucket(now)}".encode()
    return "lst" + hashlib.sha256(thong).hexdigest()[:28]


def evaluate_listen(
    *,
    listener_id: Optional[str],
    author_id: str,
    listened_seconds: float,
    duration_seconds: float,
    last_credit_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Lan nghe nay co tinh vao uy tin cua tac gia hay khong.

    Tra ve `(co_tinh, ma_ly_do)`. Ham THUAN — moi du lieu can thiet duoc truyen
    vao, khong doc kho, khong doc dong ho toan cuc. Nho vay toan bo chinh sach
    kiem duoc bang mot bang truong hop.

    Bon phep kiem, theo dung thu tu tu re den dat:

      1. phai dang nhap — V1 khong dem khach an danh (xem ghi chu duoi);
      2. khong tinh khi tac gia tu nghe chuong cua minh;
      3. phai nghe du lau;
      4. khong tinh lai trong 24 gio cho cung nguoi + cung chuong.

    KHACH AN DANH: co the them sau, nhung se can mot cach nhan dien phien ma
    khong lan dau vao quyen rieng tu. Bo qua han o V1 an han la dem bua roi phai
    di don.
    """
    if not listener_id:
        return False, NOT_AUTHENTICATED
    if listener_id == author_id:
        return False, OWN_CHAPTER
    if listened_seconds < required_seconds(duration_seconds):
        return False, TOO_SHORT
    if last_credit_at:
        moc = _parse_iso(last_credit_at)
        if moc is not None:
            if (now or datetime.now(timezone.utc)) - moc < DEDUPE_WINDOW:
                return False, ALREADY_CREDITED
    return True, CREDITED


# =============================================================================
# Truong CONG KHAI
# =============================================================================


def public_profile(
    profile_dict: Dict[str, object],
    *,
    stats: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """
    Ho so o dang CONG KHAI — danh sach cho phep, khong phai danh sach loai bo.

    Vi sao la danh sach CHO PHEP: mot ngay nao do ai them `phone` vao profile,
    va mot ham "loai bo email" se cho no ra ngoai ma khong ai kip nhan ra. Danh
    sach cho phep thi mac dinh la KIN, va them truong cong khai la mot viec co y.

    KHONG bao gio ra ngoai: email, tier, quota da dung, va trang thai duyet.
    Trang thai duyet la thong tin MODERATION — biet ai dang bi treo hay bi tu
    choi khong phai viec cua nguoi xem trang.
    """
    status = _as_status(profile_dict.get("author_status"))
    ra: Dict[str, object] = {
        "user_id": profile_dict.get("user_id", ""),
        "username": profile_dict.get("username") or "",
        "display_name": profile_dict.get("display_name") or "",
        "bio": profile_dict.get("bio") or "",
        # CHI mot bit lo ra: co phai tac gia da duyet hay khong. `pending`,
        # `rejected`, `suspended` deu ra `false` va khong phan biet duoc.
        "is_author": status is AuthorStatus.APPROVED,
    }
    if ra["is_author"] and stats is not None:
        nghe = int(stats.get("qualified_listens") or 0)
        ra["rank"] = rank_progress(nghe)
        ra["published_novels"] = int(stats.get("published_novels") or 0)
    return ra


def _as_status(value: object) -> AuthorStatus:
    try:
        return AuthorStatus(value)
    except ValueError:
        return AuthorStatus.NONE


def public_author_card(
    profile_dict: Dict[str, object],
    stats: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Ban gon cho ket qua tim kiem — khong kem `bio` dai."""
    the = public_profile(profile_dict, stats=stats)
    the.pop("bio", None)
    return the


def searchable_authors(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Loc cho muc tim kiem "Tac gia": CHI nguoi da duyet.

    Loc o day chu khong o cau truy van cua tung cho goi: mot cho quen dieu kien
    la lo ra danh sach nguoi dang cho duyet, va do la ro ri thong tin moderation.
    """
    return [r for r in rows
            if _as_status(r.get("author_status")) is AuthorStatus.APPROVED]
