"""
Chinh sach thuan cua tang xa hoi: theo doi, bai dang, thich, binh luan, thong
bao, bao cao.

Module nay la Python thuan — khong FastAPI, khong mang, khong kho du lieu. Moi
ham o day nhan vao gia tri va tra ve gia tri, nen chung kiem thu duoc ma khong
can dung mot backend nao.

VI SAO TACH RA: cung ly do voi `server/creator.py`. Quy tac ("bai dang dai bao
nhieu thi qua dai", "mot nguoi duoc dang bao nhieu bai mot gio", "khoa chong
trung cua mot lan thich") la thu se duoc doi, va doi chung KHONG duoc keo theo
viec sua tang kho hay tang route. Khi mot quy tac song trong mot ham thuan, doi
no la doi mot dong; khi no nam rai trong route thi doi no la mot cuoc san lung.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

# -----------------------------------------------------------------------------
# Do dai van ban
# -----------------------------------------------------------------------------

#: Bai dang. Day KHONG phai cho ke chuyen — truyen di duong `novels/chapters`.
#: Mot bai dang la mot loi nhan ngan cua tac gia hoac doc gia, nen tran o day
#: co tinh la mot LOI MOI: viet dai hon thi viet thanh chuong.
POST_MAX_CHARS = 2000
COMMENT_MAX_CHARS = 1000
REPORT_DETAIL_MAX_CHARS = 500
#: Ghi chu cua quan tri khi xu ly bao cao. KHONG BAO GIO ra API cong khai.
MODERATION_NOTE_MAX_CHARS = 1000


#: Cac ky tu DIEU KHIEN HUONG DOC. Chung khong ve ra gi, nhung chung doi thu tu
#: hien thi cua nhung ky tu xung quanh — nen mot chuoi chua chung co the hien ra
#: nguoc han noi dung that.
#:
#: Danh sach nay CO TINH la hep: dung nhom bidi, khong phai ca the loai Unicode
#: `Cf`. `U+200D` (ZWJ) va `U+200C` (ZWNJ) cung o trong `Cf` va deu can thiet —
#: ZWJ ghep emoji gia dinh thanh mot hinh, ZWNJ can cho vai he chu viet.
_BIDI = frozenset(
    "‎‏"                          # LRM, RLM
    "‪‫‬‭‮"        # LRE, RLE, PDF, LRO, RLO
    "⁦⁧⁨⁩"              # LRI, RLI, FSI, PDI
)


class SocialError(ValueError):
    """Vi pham chinh sach xa hoi. Tang route doi thanh 400/422."""


class RateLimited(SocialError):
    """Vuot han muc theo thoi gian. Tang route doi thanh 429."""


class CapabilityDisabled(SocialError):
    """
    Yeu cau dung mot tinh nang Social Play V1 (spoiler/fandom/edited-label/
    user report/blocks/profile banner-accent-fandoms) trong khi may chu chua
    bat `FAS_SOCIAL_V1_SCHEMA` — xem `capabilities_for`. Tang route doi thanh
    409, KHONG PHAI 400: day khong phai loi du lieu nguoi dung nhap, ma la
    "tinh nang nay chua san sang tren may chu nay".

    KHONG BAO GIO am tham bo qua truong nguoi dung da gui — thay vao do nem
    loi nay ro rang. Ghi mot thuoc tinh Appwrite chua duoc cap phat lam HONG
    CA lan ghi do (xem `server/config.py::Settings.social_v1_schema`), nen
    "bo qua truong" that ra la "vo tinh xoa mat" du lieu ma nguoi dung nghi
    la da luu.
    """


# -----------------------------------------------------------------------------
# Social Play V1 — cong nang luc (capability gate)
# -----------------------------------------------------------------------------
#
# Cac thuoc tinh Appwrite moi (spoiler/fandom_id/edited_at/user report/
# user_blocks/banner_key/accent/fandom_ids) CHUA duoc cap phat tren
# production — xem `docs/migrations/SOCIAL_PLAY_V1_SCHEMA.md`. Cho toi khi
# migration chay va co bat, MOI duong ghi cua tang nay phai TU CHOI ro rang
# thay vi am tham bo qua truong, va MOI duong ghi Appwrite phai KHONG BAO
# GIO gui cac thuoc tinh nay.

#: MOT co duy nhat cho CA nhom nang luc nay — khong phai tam bat/tat rieng
#: tung tinh nang. Ly do: chung cung mot dot migration schema, va bat rieng
#: le tung cai chi them to hop trang thai ma khong ai thuc su can.
CAPABILITY_KEYS: Tuple[str, ...] = (
    "post_spoiler", "post_fandom", "edited_label", "user_reports", "blocks",
    "profile_banner", "profile_accent", "profile_fandoms",
)


def capabilities_for(*, data_backend: str, social_v1_schema: bool) -> Dict[str, bool]:
    """
    Nang luc Social Play V1 dang BAT hay TAT, cho `GET /api/limits`.

    Nhan tham so THO (khong nhan `Settings`) de mo-dun nay khong phai import
    `server/config.py` — `config.py` da import NGUOC lai `server/social.py`
    (`_social_limits`), va mot import hai chieu se thanh mot vong lap.

    Kho MOCK (`data_backend == "mock"`) khong co Appwrite that de lam hong,
    nen luon BAT — day la moi truong phat trien/kiem thu cuc bo. Kho
    `appwrite` chi BAT khi operator da tu tay xac nhan migration xong
    (`social_v1_schema=True`).
    """
    bat = data_backend == "mock" or bool(social_v1_schema)
    return {khoa: bat for khoa in CAPABILITY_KEYS}


# -----------------------------------------------------------------------------
# Fandom cong dong — danh sach CO CHON, KHONG phai FandomRegistry
# -----------------------------------------------------------------------------
#
# `server/fandom_registry.py` sinh `fandom_id` NGAU NHIEN moi tien trinh
# (`new_id("fdm")`) — khong on dinh qua lan khoi dong lai, nen KHONG dung
# duoc lam slug ben vung cho mot bai dang. Danh sach duoi day la MOT nguon
# rieng, nho va CO CHU DICH, phan anh `web/src/lib/taxonomy.ts::FANDOM_OPTIONS`
# — doi mot cai thi phai doi ca hai.
COMMUNITY_FANDOMS: Tuple[Tuple[str, str], ...] = (
    ("naruto", "Naruto"),
    ("one-piece", "One Piece"),
    ("conan", "Detective Conan"),
    ("genshin-impact", "Genshin Impact"),
    ("fairy-tail", "Fairy Tail"),
    ("bong-ro", "Bóng rổ"),
)

#: `{slug: nhan}` — tra cuu O(1) o duong doc nhieu (loc bang tin theo fandom).
_COMMUNITY_FANDOM_LABELS: Dict[str, str] = dict(COMMUNITY_FANDOMS)


def community_fandoms_out() -> List[Dict[str, str]]:
    """Hinh dang `/api/limits` tra ve: `[{"id": slug, "label": ten}, ...]`."""
    return [{"id": slug, "label": ten} for slug, ten in COMMUNITY_FANDOMS]


def validate_fandom_id(raw: str, *, bat_buoc: bool = False) -> str:
    """
    Kiem mot slug fandom cong dong. Rong hop le tru khi `bat_buoc=True`.

    KHONG phai kiem cu phap (regex) — day la mot DANH SACH DONG, vi cong dong
    hien chi ho tro vai fandom da chon truoc. Slug khong nam trong danh sach
    thi NEM LOI ro rang (400), khong am tham bo qua hay quy ve rong.
    """
    slug = (raw or "").strip().lower()
    if not slug:
        if bat_buoc:
            raise SocialError("Thiếu fandom.")
        return ""
    if slug not in _COMMUNITY_FANDOM_LABELS:
        raise SocialError(f"Fandom không hợp lệ: {raw!r}.")
    return slug


def community_fandom_label(slug: str) -> Optional[str]:
    """Nhan hien thi cua mot slug, hoac `None` neu khong nam trong danh sach."""
    return _COMMUNITY_FANDOM_LABELS.get((slug or "").strip().lower())


# -----------------------------------------------------------------------------
# Idempotency: bai dang / binh luan
# -----------------------------------------------------------------------------

#: `client_key` cua client — mot chuoi client tu sinh (vd UUID rut gon) de
#: nhan dang LAI CUNG mot lan bam gui, ke ca khi request bi gui trung (mang
#: chap chon, nguoi dung bam nut hai lan). Xem `post_key`/`comment_key`.
CLIENT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def post_key(author_user_id: str, client_key: str) -> str:
    """
    `post_id` TAT DINH tu (tac gia, client_key) — cho tao bai IDEMPOTENT.

    Tac gia nam TRONG hash nen HAI tac gia khac nhau khong bao gio va cham
    du dung chung mot `client_key` (vd hai tab cua hai nguoi cung copy mot
    doan script frontend). Dinh dang `"pst_" + hex[:24]` — CO Y khac quy uoc
    `_khoa()` o duoi (`"pst" + hex[:28]`, khong gach duoi): day la khoa
    NGUOI DUNG CO THE THAY (no chinh la `post_id` hien ra trong URL), trong
    khi `_khoa()` la khoa NOI BO cua cac bang quan he.
    """
    return "pst_" + hashlib.sha256(
        f"{author_user_id}\x1f{client_key}".encode()).hexdigest()[:24]


def comment_key(author_user_id: str, target_id: str, client_key: str) -> str:
    """`comment_id` TAT DINH tu (tac gia, dich, client_key) — xem `post_key`."""
    return "cmt_" + hashlib.sha256(
        f"{author_user_id}\x1f{target_id}\x1f{client_key}".encode()
    ).hexdigest()[:24]


# -----------------------------------------------------------------------------
# Chan / tat tieng nguoi dung
# -----------------------------------------------------------------------------


def block_key(blocker_id: str, blocked_id: str, kind: str) -> str:
    """`block_id` TAT DINH tu (nguoi chan, nguoi bi chan, loai) — xem
    `domain.UserBlock`. Bam theo BA phan de "chặn" va "tắt tiếng" cung mot
    cap nguoi khong va cham thanh mot hang."""
    return "blk_" + hashlib.sha256(
        f"{blocker_id}\x1f{blocked_id}\x1f{kind}".encode()).hexdigest()[:24]


# -----------------------------------------------------------------------------
# Bang tin: cursor va tran do sau
# -----------------------------------------------------------------------------

#: So muc TOI DA duoc xet (kiem tra + loc) cho MOT lan doi bang tin, cho MOI
#: pham vi (scope) va bo loc. Khong phai so muc TRA VE — loc theo chan/tat
#: tieng co the bo di vai muc trong so nay. Vuot tran thi dung lai va bao
#: `depth_capped=True` thay vi quet vo han.
FEED_MAX_DEPTH = 500


def encode_feed_cursor(created_at: str, post_id: str) -> str:
    """Cursor MO — base64url cua `created_at|post_id` cua muc CUOI CUNG da
    xet. Khong ma hoa bi mat gi, chi de tranh nguoi dung chinh tay sua no
    thanh mot chuoi "trong nhu" hop le nhung sai cau truc."""
    raw = f"{created_at}|{post_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_feed_cursor(raw: str) -> Tuple[str, str]:
    """Giai ma cursor. Nem `SocialError` (400) neu khong doc duoc — mot
    cursor hong khong duoc phep am tham roi ve trang dau, vi do se lam
    nguoi dung tuong da xem het ma that ra bi lap lai tu dau."""
    if not raw:
        raise SocialError("Thiếu cursor.")
    try:
        pad = "=" * (-len(raw) % 4)
        text = base64.urlsafe_b64decode((raw + pad).encode("ascii")).decode("utf-8")
        created_at, _, post_id = text.partition("|")
        if not created_at or not post_id:
            raise ValueError("thieu phan")
    except Exception as exc:
        raise SocialError("Cursor không hợp lệ.") from exc
    return created_at, post_id


# -----------------------------------------------------------------------------
# Ho so: preset mau nhan dien
# -----------------------------------------------------------------------------

#: Danh sach mau nhan dien trang ca nhan — CO CHON, khong nhan ma HEX tu do
#: (tranh mot nguoi dat mau khong doc duoc chu tren nen toi/sang cua giao
#: dien). Rong = mac dinh he thong.
ACCENT_PRESETS: Tuple[str, ...] = ("aurora", "ember", "jade", "violet", "gold")

#: So fandom TOI DA mot nguoi dung duoc gan cho trang ca nhan cua minh.
PROFILE_MAX_FANDOMS = 5


def clean_text(raw: str, *, toi_da: int, ten: str, bat_buoc: bool = True) -> str:
    """
    Chuan hoa mot doan van ban nguoi dung go.

    Ba viec, theo dung thu tu nay:

      1. Bo ky tu dieu khien (tru xuong dong va tab) VA nhom dieu khien huong
         doc. Nhom thu hai la thu de bo sot: chung deu >= U+0020 nen mot bo loc
         "bo ky tu duoi 32" khong bat duoc cai nao.

         `U+202E` (dao chieu doc) lam mot chuoi HIEN RA khac han noi dung that
         cua no — mot binh luan co the doc thanh mot cau nguoc lai. Ta bo DUNG
         nhom bidi (`_BIDI`) chu khong bo ca the loai Unicode `Cf`: `U+200D`
         (ZWJ) cung o trong `Cf`, va no la thu ghep emoji gia dinh thanh mot
         hinh. Bo ca nhom thi mot emoji bien thanh ba.
      2. Gom bon dong trong tro len thanh hai. Mot bai dang toan dong trong
         chiem ca man hinh cua nguoi khac trong bang tin, va do la mot dang spam
         khong can mot he thong chong spam nao de chan.
      3. Cat khoang trang hai dau.

    KHONG loc HTML o day: tang hien thi cua React thoat chuoi san, va mot bo loc
    HTML nua o day se lam hong nhung bai viet noi VE ma nguon.
    """
    text = str(raw or "")
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t")
        or (ord(ch) >= 32 and ord(ch) != 127 and ch not in _BIDI)
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if bat_buoc and not text:
        raise SocialError(f"{ten} không được để trống.")
    if len(text) > toi_da:
        raise SocialError(f"{ten} tối đa {toi_da} ký tự (đang {len(text)}).")
    return text


# -----------------------------------------------------------------------------
# Khoa TAT DINH
# -----------------------------------------------------------------------------
#
# Moi bang co the co ban ghi TRUNG deu dung mot khoa tat dinh lam `rowId`. Do la
# cung mot ky thuat da dung cho `job_locks` va `listen_credits`, va no manh hon
# moi phep "doc roi kiem tra" ma ta co the viet:
#
#   doc-roi-kiem-tra   hai request cung luc deu doc thay "chua co" roi cung ghi
#   khoa tat dinh      request thu hai va vao xung dot khoa cua Appwrite
#
# Bam thay vi noi chuoi vi Appwrite gioi han `rowId` o 36 ky tu va cam mot so ky
# tu; `user_id` cua Appwrite da 20-36 ky tu nen noi hai cai lai la chac chan vuot.


def _khoa(tien_to: str, *phan: str) -> str:
    """Khoa tat dinh dai 31 ky tu: 3 tien to + 28 ky tu bam."""
    thong = "\x1f".join(str(p) for p in phan).encode()
    return tien_to + hashlib.sha256(thong).hexdigest()[:28]


def user_follow_key(follower_id: str, target_id: str) -> str:
    """MOT ban ghi cho moi cap (nguoi theo doi, nguoi duoc theo doi)."""
    return _khoa("ufl", follower_id, target_id)


def story_follow_key(follower_id: str, novel_id: str) -> str:
    """MOT ban ghi cho moi cap (nguoi theo doi, truyen)."""
    return _khoa("sfl", follower_id, novel_id)


def post_like_key(user_id: str, post_id: str) -> str:
    """
    MOT luot thich cho moi cap (nguoi, bai).

    Day la cho tinh duy nhat quan trong nhat cua ca tang xa hoi: khong co no,
    hai lan bam nhanh lien tiep tao hai hang va so dem sai vinh vien.
    """
    return _khoa("plk", user_id, post_id)


def comment_like_key(user_id: str, comment_id: str) -> str:
    return _khoa("clk", user_id, comment_id)


def report_key(reporter_id: str, target_kind: str, target_id: str) -> str:
    """
    MOT bao cao cho moi (nguoi bao, loai, doi tuong).

    Nguoi dung bam Bao cao ba lan khong tao ba hang. Doi lai, ho khong bao cao
    lai duoc sau khi quan tri da xu ly — do la chu y: mot noi dung da duoc xem
    va giu lai khong nen quay lai hang doi vi cung mot nguoi bam them lan nua.
    """
    return _khoa("rpt", reporter_id, target_kind, target_id)


# -----------------------------------------------------------------------------
# Thong bao: khoa chong lap
# -----------------------------------------------------------------------------

#: Cua so gom thong bao. Cung mot (nguoi nhan, loai, nguoi gay, doi tuong)
#: trong cung mot NGAY UTC chi sinh MOT thong bao.
#:
#: Vi sao theo ngay chu khong phai "chi mot lan mai mai": bo theo doi roi theo
#: doi lai sau ba thang la mot su kien that, va nguoi nhan nen biet. Nhung mot
#: nguoi bam theo doi/bo theo doi muoi lan trong mot buoi chieu thi khong.
def notification_key(user_id: str, kind: str, actor_id: str,
                     subject_id: str = "",
                     now: Optional[datetime] = None) -> str:
    """
    Khoa tat dinh cua mot thong bao, co GO NGAY.

    Chinh tinh duy nhat cua khoa nay la co che chong spam — khong phai mot bo
    dem, khong phai mot hang doi. Tang kho chi viec "tao neu chua co".
    """
    moment = now or datetime.now(timezone.utc)
    ngay = int(moment.timestamp() // 86400)
    return _khoa("ntf", user_id, kind, actor_id, subject_id, str(ngay))


# -----------------------------------------------------------------------------
# Han muc chong spam
# -----------------------------------------------------------------------------
#
# CO TINH la don gian. Day khong phai mot nen tang tin cay & an toan: no la mot
# cai phanh de mot vong lap hong hoac mot nguoi nghich khong lam ngap bang tin
# cua nguoi khac trong nam phut.
#
# Cua so TRUOT mot gio, dem tren chinh bang du lieu. Khong bo dem trong bo nho:
# backend co the chay nhieu tien trinh (uvicorn + worker), va mot bo dem cuc bo
# se dem rieng o moi tien trinh — tuc la han muc that gap doi mot cach am tham.


@dataclass(frozen=True)
class HanMuc:
    """Bao nhieu lan trong bao nhieu phut."""

    so_lan: int
    phut: int

    @property
    def cua_so(self) -> timedelta:
        return timedelta(minutes=self.phut)

    def moc_bat_dau(self, now: Optional[datetime] = None) -> str:
        """Moc ISO cua dau cua so — dung lam dieu kien truy van."""
        moment = now or datetime.now(timezone.utc)
        return (moment - self.cua_so).isoformat(timespec="seconds")


#: Cac han muc mac dinh. `server/config.py` doc de tu bien moi truong, nen doi
#: chung o staging khong phai sua ma nguon — xem `Settings.social_limits`.
HAN_MUC_MAC_DINH: Dict[str, HanMuc] = {
    #: Dang bai. 10 bai/gio la nhieu hon bat ky nguoi that nao viet.
    "post": HanMuc(so_lan=10, phut=60),
    #: Binh luan. Cao hon dang bai: mot cuoc trao doi that co nhip nhanh hon.
    "comment": HanMuc(so_lan=40, phut=60),
    #: Theo doi. Chan kieu "theo doi mot nghin nguoi de doi duoc theo doi lai".
    "follow": HanMuc(so_lan=100, phut=60),
    #: Bao cao. Chan dung mot nguoi bao cao hang loat de dim mot nguoi khac.
    "report": HanMuc(so_lan=20, phut=60),
}


def kiem_han_muc(ten: str, da_dung: int,
                 han_muc: Optional[HanMuc] = None) -> None:
    """
    Nem `RateLimited` neu da cham tran.

    Nhan vao SO DA DUNG chu khong tu di dem: phep dem thuoc ve tang kho, va giu
    ham nay thuan khien no kiem thu duoc ma khong can mot kho nao.
    """
    muc = han_muc or HAN_MUC_MAC_DINH.get(ten)
    if muc is None:
        return
    if da_dung >= muc.so_lan:
        raise RateLimited(
            f"Bạn đã thao tác quá nhanh (tối đa {muc.so_lan} lần mỗi "
            f"{muc.phut} phút). Vui lòng thử lại sau."
        )


# -----------------------------------------------------------------------------
# Chinh sach media — MOT noi duy nhat
# -----------------------------------------------------------------------------
#
# Yeu cau ro rang: khong rai hang so ra giao dien. Moi tran kich thuoc va moi
# danh sach MIME cho phep deu o day, va ca backend lan frontend deu doc tu day
# (frontend qua `/api/limits`).


@dataclass(frozen=True)
class ChinhSachAnh:
    """Mot loai anh: duoc phep nhung gi, to den dau, nam o dau trong kho."""

    #: Tien to khong gian ten trong R2. Xem `object_key`.
    khong_gian: str
    #: Tran SAU khi xu ly. Frontend nen nen truoc khi gui.
    toi_da_byte: int
    #: Canh dai nhat tinh bang diem anh.
    canh_toi_da: int
    #: MIME duoc nhan. Khong co SVG: SVG la XML va co the chua script.
    mime: Tuple[str, ...] = (
        "image/webp", "image/avif", "image/jpeg", "image/png",
    )
    #: MIME NEN dung sau khi xu ly, theo thu tu uu tien.
    mime_uu_tien: Tuple[str, ...] = ("image/webp", "image/avif")


#: KHONG CO VIDEO o bat ky muc nao. Day la mot quyet dinh, khong phai mot thieu
#: sot: video keo theo transcode, thoi luong, phu de, ban quyen va chi phi bang
#: thong — moi thu do deu la mot du an rieng.
CHINH_SACH_ANH: Dict[str, ChinhSachAnh] = {
    #: Anh dai dien. Nho, vuong, hien o kich thuoc nho khap noi.
    "avatar": ChinhSachAnh(khong_gian="avatars", toi_da_byte=512 * 1024,
                           canh_toi_da=512),
    #: Bia truyen. To hon vi no la thu nguoi ta nhin dau tien o trang truyen.
    "cover": ChinhSachAnh(khong_gian="covers", toi_da_byte=2 * 1024 * 1024,
                          canh_toi_da=1600),
    #: Anh cua bai dang. MOT anh moi bai — xem `POST_MAX_IMAGES`.
    "post": ChinhSachAnh(khong_gian="posts", toi_da_byte=1024 * 1024,
                         canh_toi_da=1600),
}

#: V3: toi da BON anh moi bai, cuong che o tang dich vu.
#:
#: Bon la con so cua mot luoi 2x2 — cai luoi don gian nhat con dep. Nhieu hon
#: thi thanh mot thu vien anh voi trang rieng, thu tu keo tha va man hinh luot,
#: va do la mot tinh nang khac.
POST_MAX_IMAGES = 4

#: Tran TONG dung luong anh cua MOT bai, sau xu ly. Kho R2 dang o goi MVP —
#: xem `docs/HANDOFF.md`. Mot bai bon anh WebP 1600px thuong roi vao khoang
#: 400 KB - 2 MB; tran 3 MB la du rong cho anh that va du chat de mot bai
#: khong ngon mot phan nghin cua kho.
POST_TOTAL_MEDIA_BYTES = 3 * 1024 * 1024


def kiem_bo_anh(loai: str, anh: "Sequence[Dict[str, object]]") -> None:
    """
    Kiem CA BO anh cua mot bai: so luong va TONG dung luong.

    Tung anh mot da qua `kiem_anh`; ham nay giu hai rang buoc chi co nghia o
    muc ca bo. Tach rieng de cho goi nao chi co mot anh khong phai tra tien
    cho logic bo.
    """
    if len(anh) > POST_MAX_IMAGES:
        raise SocialError(f"Tối đa {POST_MAX_IMAGES} ảnh mỗi bài.")
    tong = sum(int(a.get("so_byte") or 0) for a in anh)
    if tong > POST_TOTAL_MEDIA_BYTES:
        mb = POST_TOTAL_MEDIA_BYTES / (1024 * 1024)
        raise SocialError(
            f"Tổng dung lượng ảnh vượt quá {mb:.0f} MB. Hãy bớt hoặc nén ảnh.")


#: Tran hop ly cuoi cung cho moc thoi gian dinh kem (mili giay) khi KHONG kiem
#: duoc thoi luong that: 12 gio. Khong audiobook chuong nao dai hon, va mot moc
#: bia dat se chi tro ve cuoi audio khi bam — kho chiu, khong nguy hiem.
TIMESTAMP_TRAN_MS = 12 * 60 * 60 * 1000


def kiem_timestamp(timestamp_ms: Optional[int],
                   duration_seconds: Optional[float]) -> Optional[int]:
    """
    Kiem moc thoi gian dinh kem mot binh luan chuong.

    `duration_seconds` la thoi luong THAT tu `audio_tracks` neu co. Khi co,
    moc phai nam trong [0, thoi luong + 2s] — hai giay du sai so lam tron cua
    trinh duyet o cuoi audio. Khi KHONG co (chuong chua co audio, hoac track
    thieu thoi luong), lui ve phep kiem hop ly: [0, 12 gio]. Han che nay duoc
    ghi trong bao cao — khong gia vo kiem duoc thu khong kiem duoc.
    """
    if timestamp_ms is None:
        return None
    ts = int(timestamp_ms)
    if ts < 0:
        raise SocialError("Mốc thời gian không hợp lệ.")
    if duration_seconds and duration_seconds > 0:
        if ts > int(duration_seconds * 1000) + 2000:
            raise SocialError("Mốc thời gian vượt quá độ dài audio.")
    elif ts > TIMESTAMP_TRAN_MS:
        raise SocialError("Mốc thời gian không hợp lệ.")
    return ts


def kiem_anh(loai: str, *, mime: str, so_byte: int) -> ChinhSachAnh:
    """
    Kiem mot tep tai len TRUOC khi cham vao kho.

    Tra ve chinh sach da dung de nguoi goi khoi phai tra cuu lai.
    """
    chinh_sach = CHINH_SACH_ANH.get(loai)
    if chinh_sach is None:
        raise SocialError(f"Loại ảnh không hợp lệ: {loai!r}")
    got = (mime or "").split(";")[0].strip().lower()
    if got not in chinh_sach.mime:
        cho_phep = ", ".join(chinh_sach.mime)
        raise SocialError(f"Định dạng ảnh không được hỗ trợ ({got or 'không rõ'}). "
                          f"Chấp nhận: {cho_phep}.")
    if so_byte <= 0:
        raise SocialError("Tệp ảnh rỗng.")
    if so_byte > chinh_sach.toi_da_byte:
        mb = chinh_sach.toi_da_byte / (1024 * 1024)
        raise SocialError(f"Ảnh vượt quá {mb:.1f} MB sau khi xử lý.")
    return chinh_sach


#: Ky tu an toan cho mot doan khoa doi tuong. Moi thu khac bi thay bang `_`.
_KHOA_AN_TOAN = re.compile(r"[^A-Za-z0-9_-]")


def doan_khoa(raw: str) -> str:
    """Mot doan khoa doi tuong an toan: chi chu, so, gach ngang, gach duoi."""
    sach = _KHOA_AN_TOAN.sub("_", str(raw or ""))[:64]
    return sach or "_"


def content_addressed_key(khong_gian: str, *, user_id: str, data: bytes) -> str:
    """
    Khoa doi tuong NOI DUNG-DINH-DIA CHI (Social Play V1): `{khong_gian}/
    {user_id}/{sha256(data)[:16]}.webp` — dung cho avatar/banner ho so SAU
    khi da chuan hoa (`server/image_normalize.py`).

    KHAC `object_key()` o duoi (mot khoa CO DINH `anh.{duoi}` moi khong gian):
    khoa noi dung-dinh-dia-chi tu doi khi ANH doi, nen "xoa anh CU sau khi
    ghi ho so THANH CONG" (xem `SocialService.update_profile`) khong bao gio
    xoa nham khoa MOI vua ghi — hai anh khac nhau chac chan ra hai khoa khac
    nhau, va CUNG mot anh (bam lai upload y het) ra LAI DUNG mot khoa cu.
    """
    return f"{khong_gian}/{doan_khoa(user_id)}/{hashlib.sha256(data).hexdigest()[:16]}.webp"


def object_key(loai: str, *, user_id: str, subject_id: str,
               duoi: str = "webp") -> str:
    """
    Khoa doi tuong trong R2, theo khong gian ten cua tung loai.

        posts/{user_id}/{post_id}/anh.webp
        avatars/{user_id}/anh.webp
        covers/{user_id}/{novel_id}/anh.webp

    KHONG BAO GIO dua dia chi email vao khoa. Ly do khong phai tham my:

      - khoa doi tuong xuat hien trong URL da ky, trong log truy cap, trong
        thong bao loi va trong bang dieu khien cua nha cung cap;
      - mot dia chi email o do la du lieu ca nhan bi ro ri sang moi noi do, va
        khong co cach nao thu hoi mot khoa da phat ra.

    `user_id` cua Appwrite la mot chuoi MO — no khong noi len dieu gi ve nguoi
    do — nen no an toan de dat vao day.
    """
    chinh_sach = CHINH_SACH_ANH.get(loai)
    if chinh_sach is None:
        raise SocialError(f"Loại ảnh không hợp lệ: {loai!r}")
    phan = [chinh_sach.khong_gian, doan_khoa(user_id)]
    if subject_id:
        phan.append(doan_khoa(subject_id))
    phan.append(f"anh.{doan_khoa(duoi)}")
    return "/".join(phan)


def mo_ta_gioi_han() -> Dict[str, object]:
    """
    Hinh dang ma `/api/limits` tra ve cho trinh duyet.

    Frontend doc con so tu day de bao truoc cho nguoi dung, nhung MAY CHU van la
    noi cuong che — xem `web/src/lib/limits.ts`.
    """
    return {
        "post_max_chars": POST_MAX_CHARS,
        "comment_max_chars": COMMENT_MAX_CHARS,
        "report_detail_max_chars": REPORT_DETAIL_MAX_CHARS,
        "post_max_images": POST_MAX_IMAGES,
        "post_total_media_bytes": POST_TOTAL_MEDIA_BYTES,
        "image": {
            loai: {
                "max_bytes": cs.toi_da_byte,
                "max_edge": cs.canh_toi_da,
                "mime": list(cs.mime),
                "preferred_mime": list(cs.mime_uu_tien),
            }
            for loai, cs in CHINH_SACH_ANH.items()
        },
        "rate": {
            ten: {"count": m.so_lan, "minutes": m.phut}
            for ten, m in HAN_MUC_MAC_DINH.items()
        },
        "community_fandoms": community_fandoms_out(),
        "profile_accent_presets": list(ACCENT_PRESETS),
        "profile_max_fandoms": PROFILE_MAX_FANDOMS,
    }


# -----------------------------------------------------------------------------
# Binh luan: DUNG mot cap tra loi
# -----------------------------------------------------------------------------

#: Do sau toi da cua mot nhanh binh luan. `0` la binh luan goc, `1` la tra loi.
#:
#: VI SAO CHAN CUNG o mot cap: mot cay khong gioi han keo theo thut le tang dan
#: (khong doc noi tren dien thoai), mot truy van de quy hoac mot cot `path`, va
#: mot cau hoi khong co cau tra loi dep — "hien bao nhieu cap roi moi thu gon".
#: Mot cap la du de mot cuoc trao doi dien ra, va no giu truy van o dung MOT
#: phep loc theo `parent_id`.
REPLY_MAX_DEPTH = 1


def parent_hop_le(cha_id: str, cha_cua_cha: str) -> None:
    """
    Chi cho tra loi mot binh luan GOC.

    Tra loi mot tra loi thi bi tu choi ngay tai day thay vi am tham gan vao
    dau do — mot cai cay lech la thu rat kho don sau nay.
    """
    if cha_cua_cha:
        raise SocialError(
            "Chỉ trả lời được bình luận gốc. Hãy trả lời bình luận đầu chuỗi."
        )
    if not cha_id:
        raise SocialError("Thiếu bình luận cha.")


# -----------------------------------------------------------------------------
# Bang tin
# -----------------------------------------------------------------------------

#: So bai moi trang bang tin. Du day mot man hinh dien thoai, du nho de mot
#: trang khong keo theo hang tram phep tra cuu ho so.
FEED_PAGE_SIZE = 20

#: Tran tuyet doi cho moi trang, ke ca khi client hoi nhieu hon.
FEED_MAX_PAGE_SIZE = 50

#: Bao nhieu nguoi duoc theo doi thi con dung bang tin "theo doi".
#:
#: Truy van bang tin loc theo `author_user_id IN (...)`. Appwrite gioi han do
#: dai truy van, nen danh sach nay phai co tran. Nguoi theo doi nhieu hon con
#: so nay se thay bang tin cua `NGUOI_THEO_DOI_TOI_DA` nguoi MOI NHAT ho theo
#: doi — va giao dien noi ro dieu do thay vi im lang cat bot.
NGUOI_THEO_DOI_TOI_DA = 100


def kich_thuoc_trang(raw: Optional[int]) -> int:
    """Ep so bai moi trang ve khoang hop le."""
    if not raw or raw <= 0:
        return FEED_PAGE_SIZE
    return min(int(raw), FEED_MAX_PAGE_SIZE)


def tron_bang_tin(theo_doi: Sequence[Dict[str, object]],
                  kham_pha: Sequence[Dict[str, object]],
                  gioi_han: int) -> List[Dict[str, object]]:
    """
    Ghep bai cua nguoi minh theo doi voi bai kham pha, khong trung.

    QUY TAC: bai cua nguoi minh theo doi LUON len truoc, giu nguyen thu tu thoi
    gian cua chung. Bai kham pha chi dung de LAP DAY phan con lai cua trang.

    KHONG co mo hinh xep hang nao o day, va do la mot quyet dinh: mot bo goi y
    hoc may can du lieu hanh vi, mot vong danh gia, va mot cau tra loi cho "vi
    sao toi thay bai nay". Mot bang tin theo thoi gian thi khong can gi ca, va
    nguoi doc luon giai thich duoc no.
    """
    ra: List[Dict[str, object]] = []
    da_co = set()
    for nguon in (theo_doi, kham_pha):
        for bai in nguon:
            khoa = str(bai.get("post_id") or "")
            if not khoa or khoa in da_co:
                continue
            da_co.add(khoa)
            ra.append(bai)
            if len(ra) >= gioi_han:
                return ra
    return ra
