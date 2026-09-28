"""
Cong cu chan doan CHI DOC cho Fanfic AI Support.

BANG CONG CU LA CO DINH (`DiagnosticToolbox.CONG_CU`). Khong co cong cu nao:
  * nhan URL hay ten may — `check_route` chi doi chieu voi bang route NOI BO;
  * goi mang ra ngoai — moi phep kiem chay trong tien trinh qua cac ham ma
    `server/main.py` tiem vao (`SupportDeps`);
  * ghi, xoa, khoi dong lai hay doi cau hinh bat cu thu gi.

QUYEN: cong cu doc truyen/chuong/audio goi DUNG ham kiem quyen doc cua san
pham (`may_read`, `can_read_chapter`) voi DANH TINH nguoi hoi. Chuong nhap cua
nguoi khac tra `not_found` — giong het route doc truyen, khong lo la no ton tai.

Moi ket qua: `{"tool", "status": ok|warn|fail|unknown|denied, "summary", "data"}`
— `data` chi gom truong liet ke san (co/khong, dem, ma trang thai), khong bao
gio co khoa, URL ky, email hay noi dung chuong.
"""
from __future__ import annotations

import concurrent.futures
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from server.support.sanitize import chuan_hoa_route, sach_chuoi

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
THOI_GIAN_TOI_DA_GIAY = 3.0
#: Pool CUA CA tien trinh. Kich thuoc > so luot chan doan dong thoi toi da
#: (`routes._DONG_THOI` = 4) de mot cong cu treo (het 3 giay, luong van chay
#: nen) khong lam cac luot khac het gio oan (review doc lap, 2026-09-28).
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="support-tool")

#: Bang route NOI BO — chi de tra loi "trang nay la gi, can dang nhap khong".
BANG_ROUTE: Dict[str, Dict[str, Any]] = {
    "/": {"area": "home", "login": False},
    "/fanfic": {"area": "reader", "login": False},
    "/library": {"area": "reader", "login": False},
    "/novels/[id]": {"area": "reader", "login": False},
    "/chapters/[id]": {"area": "reader", "login": False},
    "/community": {"area": "community", "login": False},
    "/posts/[postId]": {"area": "community", "login": False},
    "/u/[username]": {"area": "community", "login": False},
    "/authors": {"area": "community", "login": False},
    "/leaderboard": {"area": "community", "login": False},
    "/animation": {"area": "animation", "login": False},
    "/animation/[id]": {"area": "animation", "login": False},
    "/animation/watch/[id]": {"area": "animation", "login": False},
    "/animation/new": {"area": "animation", "login": True},
    "/entertainment": {"area": "entertainment", "login": False},
    "/login": {"area": "auth", "login": False},
    "/auth/callback": {"area": "auth", "login": False},
    "/account": {"area": "account", "login": True},
    "/notifications": {"area": "account", "login": True},
    "/messages": {"area": "chat", "login": True},
    "/support": {"area": "support", "login": False},
    "/creator/apply": {"area": "account", "login": True},
    "/import": {"area": "studio", "login": True},
    "/image-studio/connect/callback": {"area": "studio", "login": True},
    "/studio": {"area": "studio", "login": True},
    "/studio/audio": {"area": "studio", "login": True},
    "/studio/content": {"area": "studio", "login": True},
    "/studio/image": {"area": "studio", "login": True},
    "/studio/library": {"area": "studio", "login": True},
    "/studio/media": {"area": "studio", "login": True},
    "/studio/projects/[id]": {"area": "studio", "login": True},
    "/studio/subtitle": {"area": "studio", "login": True},
    "/studio/translate": {"area": "studio", "login": True},
    "/studio/video": {"area": "studio", "login": True},
    "/studio/write": {"area": "studio", "login": True},
    "/studio/write/import": {"area": "studio", "login": True},
}

#: Tinh nang duoc phep hoi trang thai — ten la ngoai danh sach thi `denied`.
TINH_NANG = ("studio", "audio", "tts_worker", "support_ai", "reader", "community", "login")


@dataclass
class SupportDeps:
    """Moi thu cong cu can tu san pham — `main.py` tiem vao, module nay KHONG
    import `server.main` (tranh vong import, va de test tiem ban gia)."""

    get_novel: Callable[[str], Any]
    get_chapter: Callable[[str], Any]
    list_chapters: Callable[[str], List[Any]]
    track_for_chapter: Callable[[str], Any]
    job_status_for_chapter: Callable[[str], Optional[str]]
    storage_exists: Callable[[str], bool]
    may_read: Callable[[Any, Any], bool]
    can_read_chapter: Callable[[Any, Any, Any], bool]
    health_info: Callable[[], Dict[str, Any]]
    check_metadata: Callable[[], bool]
    check_storage: Callable[[], bool]
    feature_flags: Callable[[], Dict[str, Any]]
    not_found_errors: tuple = (LookupError,)


def _kq(tool: str, status: str, summary: str, **data: Any) -> Dict[str, Any]:
    return {"tool": tool, "status": status, "summary": summary, "data": data}


class DiagnosticToolbox:
    CONG_CU = ("get_public_system_health", "check_api_health", "check_route", "check_novel",
               "check_chapter", "check_audio_track", "check_audio_range", "check_current_build",
               "check_feature_status", "get_recent_public_incidents", "get_sanitized_client_errors",
               "get_recent_sentry_issues")

    def __init__(self, deps: SupportDeps, store, *, clock=time.monotonic, sentry: Any = None) -> None:
        self.d = deps
        self.store = store
        self._clock = clock
        self._san_sang_cache: Optional[tuple] = None  # (luc, {metadata, storage})
        #: `server.support.sentry_lookup.SentryChiDoc` hoac None (TAT). Token song TRONG doi tuong do.
        self.sentry = sentry

    # ------------------------------------------------------------ chay
    def chay(self, ten: str, args: Dict[str, Any], *, viewer: Any, owner_key: str) -> Dict[str, Any]:
        """Goi MOT cong cu trong bang, co gioi han thoi gian. Ten ngoai bang ->
        `denied` (khong bao gio getattr tuy y)."""
        if ten not in self.CONG_CU:
            return _kq(ten, "denied", "Công cụ không tồn tại.")
        fn = getattr(self, "_" + ten)
        # Pool DUNG CHUNG, khong `with ThreadPoolExecutor(...)`: khoi `with` cho
        # luong chay xong khi thoat, tuc la het thoi gian cung khong tra ve som.
        tuong_lai = _POOL.submit(fn, viewer=viewer, owner_key=owner_key, **args)
        try:
            return tuong_lai.result(timeout=THOI_GIAN_TOI_DA_GIAY)
        except concurrent.futures.TimeoutError:
            return _kq(ten, "unknown", "Kiểm tra quá thời gian — chưa kết luận được.")
        except Exception:  # noqa: BLE001 — cong cu hong khong duoc lam hong ca cau tra loi
            return _kq(ten, "unknown", "Không thực hiện được phép kiểm tra này.")

    # ------------------------------------------------------------ he thong
    def _san_sang(self) -> Dict[str, bool]:
        """Kiem metadata + kho file, NHO 30 giay — mot lan hoi ho tro khong duoc
        bien thanh mot lan danh vao Appwrite/R2 moi luot."""
        bay = self._clock()
        if self._san_sang_cache and bay - self._san_sang_cache[0] < 30:
            return self._san_sang_cache[1]
        kq = {}
        for ten, fn in (("metadata", self.d.check_metadata), ("storage", self.d.check_storage)):
            try:
                kq[ten] = bool(fn())
            except Exception:  # noqa: BLE001
                kq[ten] = False
        self._san_sang_cache = (bay, kq)
        return kq

    def _get_public_system_health(self, *, viewer, owner_key) -> Dict[str, Any]:
        s = self._san_sang()
        ok = all(s.values())
        return _kq("get_public_system_health", "ok" if ok else "fail",
                   "Máy chủ, kho dữ liệu và kho audio đều trả lời." if ok else
                   "Một phần hệ thống đang không trả lời: " + ", ".join(k for k, v in s.items() if not v) + ".",
                   api=True, **s)

    def _check_api_health(self, *, viewer, owner_key) -> Dict[str, Any]:
        info = self.d.health_info()
        s = self._san_sang()
        ok = all(s.values())
        return _kq("check_api_health", "ok" if ok else "fail",
                   "API Fanfic World đang hoạt động." if ok else "API trả lời nhưng một phụ thuộc đang lỗi.",
                   version=sach_chuoi(str(info.get("version", "")), 40),
                   data_backend=info.get("data_backend"), storage_backend=info.get("storage_backend"),
                   metadata=s.get("metadata"), storage=s.get("storage"))

    def _check_current_build(self, *, viewer, owner_key) -> Dict[str, Any]:
        info = self.d.health_info()
        sha = info.get("commit_sha")
        return _kq("check_current_build", "ok", "Đã đọc phiên bản máy chủ.",
                   api_version=sach_chuoi(str(info.get("version", "")), 40),
                   api_commit=(str(sha)[:12] if sha and re.match(r"^[0-9a-f]{7,40}$", str(sha)) else None))

    def _check_feature_status(self, *, viewer, owner_key, feature: str = "") -> Dict[str, Any]:
        f = (feature or "").strip().lower()
        if f not in TINH_NANG:
            return _kq("check_feature_status", "denied", "Tính năng này không nằm trong danh sách được kiểm tra.")
        co = self.d.feature_flags()
        bat = co.get(f)
        if bat is None:
            return _kq("check_feature_status", "unknown", f"Không xác định được trạng thái '{f}'.", feature=f)
        return _kq("check_feature_status", "ok" if bat else "warn",
                   f"Tính năng '{f}' đang {'bật' if bat else 'tắt'}.", feature=f, enabled=bool(bat))

    def _get_recent_public_incidents(self, *, viewer, owner_key) -> Dict[str, Any]:
        ds = self.store.recent_public_incidents()
        return _kq("get_recent_public_incidents", "warn" if ds else "ok",
                   f"Có {len(ds)} sự cố đang mở trong 24 giờ qua." if ds else "Không có sự cố lớn nào đang mở.",
                   incidents=ds)

    def _get_sanitized_client_errors(self, *, viewer, owner_key) -> Dict[str, Any]:
        """CHI loi cua CHINH nguoi hoi (theo `owner_key` may chu tinh) — khong co
        tham so nao chon duoc nguoi khac."""
        ds = self.store.events_for_owner(owner_key)
        return _kq("get_sanitized_client_errors", "warn" if ds else "ok",
                   f"Trình duyệt của bạn đã ghi nhận {len(ds)} lỗi gần đây." if ds else "Chưa ghi nhận lỗi nào từ trình duyệt của bạn.",
                   errors=ds)

    def _get_recent_sentry_issues(self, *, viewer, owner_key, code: str = "", route: str = "",
                                  build: str = "") -> Dict[str, Any]:
        """Doi chieu voi Sentry (CHI DOC, danh sach trang — xem `sentry_lookup.py`). Tu khoa do MAY CHU
        chon tu ma loi/mau route cua ngu canh; nguoi dung va mo hinh chi thay SO DEM + thoi diem +
        co trung ban build khong — khong tieu de loi, khong token."""
        from server.support.sanitize import ban_build, ma_loi

        if self.sentry is None:
            return _kq("get_recent_sentry_issues", "unknown", "Chưa kết nối hệ thống giám sát lỗi — bỏ qua bước đối chiếu.")
        kq = self.sentry.loi_gan_day(ma_loi=ma_loi(code), route_mau=chuan_hoa_route(route), build=ban_build(build))
        if kq.get("trang_thai") == "khong_tra_duoc":
            return _kq("get_recent_sentry_issues", "unknown", "Chưa tra được hệ thống giám sát lỗi lúc này — bỏ qua bước đối chiếu.")
        if kq.get("trang_thai") != "ok":
            return _kq("get_recent_sentry_issues", "unknown", "Không đủ ngữ cảnh để đối chiếu với hệ thống giám sát lỗi.")
        n = kq["so_van_de"]
        if not n:
            return _kq("get_recent_sentry_issues", "ok", "Hệ thống giám sát chưa ghi nhận lỗi tương tự trong 24 giờ qua.",
                       so_van_de=0)
        cung = kq.get("cung_build")
        return _kq("get_recent_sentry_issues", "warn",
                   f"Hệ thống giám sát đã ghi nhận {n} lỗi tương tự ({kq['tong_su_kien']} lần) trong 24 giờ qua"
                   + (", ở đúng bản build bạn đang dùng" if cung else "") + ".",
                   so_van_de=n, tong_su_kien=kq["tong_su_kien"], lan_cuoi=kq["lan_cuoi"], cung_build=cung)

    # ------------------------------------------------------------ trang
    def _check_route(self, *, viewer, owner_key, route: str = "") -> Dict[str, Any]:
        mau = chuan_hoa_route(route)
        info = BANG_ROUTE.get(mau)
        if mau.startswith("/admin"):
            info = {"area": "admin", "login": True, "admin": True}
        if not info:
            return _kq("check_route", "warn", "Không nhận ra trang này trong Fanfic World.", route=mau, known=False)
        can_dn = bool(info.get("login"))
        da_dn = viewer is not None
        if can_dn and not da_dn:
            return _kq("check_route", "warn", "Trang này cần đăng nhập — bạn đang chưa đăng nhập.",
                       route=mau, known=True, area=info["area"], requires_login=True, logged_in=False)
        return _kq("check_route", "ok", "Trang hợp lệ.", route=mau, known=True, area=info["area"],
                   requires_login=can_dn, logged_in=da_dn, admin_only=bool(info.get("admin")))

    # ------------------------------------------------------------ truyen / chuong / audio
    def _check_novel(self, *, viewer, owner_key, novel_id: str = "") -> Dict[str, Any]:
        if not _ID.match(novel_id or ""):
            return _kq("check_novel", "denied", "Mã truyện không hợp lệ.")
        try:
            novel = self.d.get_novel(novel_id)
        except self.d.not_found_errors:
            return _kq("check_novel", "fail", "Không tìm thấy truyện này.", found=False)
        if not self.d.may_read(novel, viewer):
            # Giong route doc truyen: nguoi khong doc duoc khong biet no ton tai.
            return _kq("check_novel", "fail", "Không tìm thấy truyện này.", found=False)
        chuong = self.d.list_chapters(novel_id)
        so = len(chuong)
        return _kq("check_novel", "ok" if so else "warn",
                   f"Truyện có {so} chương." if so else "Truyện chưa có chương nào.",
                   found=True, published=str(getattr(getattr(novel, "state", ""), "value", "")) == "published",
                   chapter_count=so)

    def _chuong(self, chapter_id: str, viewer):
        if not _ID.match(chapter_id or ""):
            return None, None, "denied"
        try:
            ch = self.d.get_chapter(chapter_id)
        except self.d.not_found_errors:
            return None, None, "missing"
        try:
            nv = self.d.get_novel(ch.novel_id)
        except self.d.not_found_errors:
            nv = None
        if not self.d.can_read_chapter(ch, nv, viewer):
            return None, None, "missing"
        return ch, nv, "ok"

    def _check_chapter(self, *, viewer, owner_key, chapter_id: str = "") -> Dict[str, Any]:
        ch, nv, tt = self._chuong(chapter_id, viewer)
        if tt == "denied":
            return _kq("check_chapter", "denied", "Mã chương không hợp lệ.")
        if tt == "missing":
            return _kq("check_chapter", "fail", "Không tìm thấy chương này (hoặc bạn không có quyền đọc).", found=False)
        do_dai = len(getattr(ch, "content", "") or "")
        return _kq("check_chapter", "ok" if do_dai else "warn",
                   "Chương có nội dung." if do_dai else "Chương này chưa có nội dung chữ.",
                   found=True, has_text=do_dai > 0, novel_found=nv is not None)

    def _check_audio_track(self, *, viewer, owner_key, chapter_id: str = "") -> Dict[str, Any]:
        ch, _, tt = self._chuong(chapter_id, viewer)
        if tt == "denied":
            return _kq("check_audio_track", "denied", "Mã chương không hợp lệ.")
        if tt == "missing":
            return _kq("check_audio_track", "fail", "Không tìm thấy chương này.", found=False)
        track = self.d.track_for_chapter(chapter_id)
        if track is None:
            job = self.d.job_status_for_chapter(chapter_id)
            if job in ("pending", "running"):
                return _kq("check_audio_track", "warn", "Audio của chương đang được tạo — thử lại sau ít phút.",
                           has_track=False, job_status=job)
            return _kq("check_audio_track", "warn", "Chương này chưa có audio.", has_track=False, job_status=job)
        con = self.d.storage_exists(track.object_key)
        return _kq("check_audio_track", "ok" if con else "fail",
                   "Chương có audio và tệp audio còn trong kho." if con else "Chương có bản ghi audio nhưng không thấy tệp trong kho.",
                   has_track=True, object_present=bool(con),
                   duration_seconds=round(float(getattr(track, "duration_seconds", 0) or 0), 1))

    def _check_audio_range(self, *, viewer, owner_key, chapter_id: str = "") -> Dict[str, Any]:
        """Tua duoc hay khong phu thuoc KHO: R2 (URL ky) ho tro Range; kho cuc bo
        stream ca tep qua backend (khong Range) — chi la su that cau hinh, khong goi mang."""
        base = self._check_audio_track(viewer=viewer, owner_key=owner_key, chapter_id=chapter_id)
        if base["status"] != "ok":
            return {**base, "tool": "check_audio_range"}
        r2 = self.d.health_info().get("storage_backend") == "r2"
        return _kq("check_audio_range", "ok" if r2 else "warn",
                   "Kho audio hỗ trợ tua (Range)." if r2 else "Kho audio cục bộ không hỗ trợ tua giữa chừng (chỉ ở môi trường thử).",
                   range_supported=r2)
