"""
Studio Project — tang dich vu.

HAI viec kho nam o day, va ca hai deu la ly do tep nay ton tai:

1. **Quyen so huu tren SAU kho khac nhau.** Moi tang co ten truong chu khac
   nhau (`owner_id` o hau het, `owner_user_id` o `SavedImage`), co kho tra
   `None`, co kho NEM khi vang mat. Neu moi duong goi tu xu ly thi se co
   dung mot duong quen — nen o day chi co MOT ham `_cua_toi`.

2. **Tien do phai THAT.** Khong bia mau so. Mot chang chi co ty le khi dem
   duoc ca tu va mau: "8/10 chuong co audio" dem duoc, "80% hoan thanh" thi
   khong. Chang nao khong co mau so that thi tra so luong tran.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from server.adapters import NotFoundError
from server.domain import MediaType, Profile, now_iso
from server.studio_project import (NHAN_CHANG, StudioProject, StudioStage,
                                   TienDoChang)
from server.studio_project_store import MockStudioProjectStore

#: Tran so du an moi nguoi — chot chong vong lap hong, khong phai han muc.
TRAN_DU_AN = 200

#: Chang -> ten truong danh sach trong `StudioProject`.
TRUONG_CUA_CHANG: Dict[StudioStage, str] = {
    StudioStage.DICH: "translation_project_ids",
    StudioStage.HINH_ANH: "image_ids",
    StudioStage.AUDIO: "audio_track_ids",
    StudioStage.PHU_DE: "subtitle_asset_ids",
    StudioStage.VIDEO: "video_project_ids",
}


class StudioProjectError(ValueError):
    """Tham so khong hop le. Thong diep danh cho NGUOI DUNG doc."""


def _ten_tep(khoa: str, tao_luc: str) -> str:
    """Ten doc duoc cho mot tep tai len.

    KHOA DO MAY CHU SINH (xem `upload_session.khoa_moi`), va dung la no nen
    the — mot khoa lay tu than yeu cau la mot khoa ghi de len cua nguoi khac
    duoc. Nhung he qua la phan ten trong khoa luon la mot chuoi hex, va
    `e6e2772c92184aba92804e62f16ef041.srt` thi khong phan biet duoc voi bat
    ky tep nao khac trong danh sach.

    Ten goc cua nguoi dung KHONG duoc luu lai: `MediaAsset` chua co truong
    nao cho no, va them mot truong la mot phep di tru lugc do. Cho den luc
    do, mot cai nhan theo NGAY van phan biet duoc cac tep voi nhau, con mot
    chuoi hex thi khong.
    """
    ten = khoa.rsplit("/", 1)[-1]
    goc = ten.rsplit(".", 1)[0]
    if len(goc) >= 16 and all(c in "0123456789abcdefABCDEF" for c in goc):
        ngay = (tao_luc or "")[:16].replace("T", " ")
        return f"Phụ đề · {ngay}" if ngay else "Phụ đề đã tải lên"
    return ten


class StudioService:
    def __init__(self, store, *, project_store=None, translation_store=None,
                 image_store=None, media_store=None,
                 video_project_store=None) -> None:
        self._store = store                       # novels/chapters/tracks
        self._du_an = project_store or MockStudioProjectStore()
        self._dich = translation_store
        self._anh = image_store
        self._media = media_store
        self._video = video_project_store

    # -- quyen so huu ---------------------------------------------------------

    def _cua_toi(self, actor: Profile, chang: StudioStage, ma: str) -> Any:
        """Ban ghi `ma` NEU no thuoc ve nguoi goi. Nguoc lai: nem.

        MOT cho duy nhat biet tung kho tra ve gi khi vang mat, va mot cho duy
        nhat biet `SavedImage` goi chu la `owner_user_id` con moi thu khac goi
        la `owner_id`.

        Vang mat va khong-phai-cua-ban nem CUNG mot loi: phan biet hai cai do
        la mot kenh do xem id nao ton tai.
        """
        thieu = NotFoundError(f"Không tìm thấy mục {NHAN_CHANG[chang]} này.")
        ban_ghi = None
        try:
            if chang is StudioStage.DICH:
                # `owned_project` tu kiem chu — nhung van de phep kiem chung
                # o duoi chay, de MOT cho duy nhat quyet dinh cau tra loi.
                ban_ghi = (self._dich.get_project(ma) if self._dich else None)
            elif chang is StudioStage.HINH_ANH:
                ban_ghi = self._anh.lay(actor.user_id, ma) if self._anh else None
            elif chang is StudioStage.AUDIO:
                ban_ghi = self._store.track_by_id(ma)
            elif chang is StudioStage.PHU_DE:
                ban_ghi = self._media.get_asset(ma) if self._media else None
            elif chang is StudioStage.VIDEO:
                ban_ghi = self._video.tim(actor.user_id, ma) if self._video else None
        except NotFoundError:
            raise thieu from None
        if ban_ghi is None:
            raise thieu
        chu = getattr(ban_ghi, "owner_id", None) or getattr(
            ban_ghi, "owner_user_id", None)
        if chu != actor.user_id:
            raise thieu
        # Phu de phai DUNG LOAI: mot `MediaAsset` video gan vao o phu de se
        # di thang toi FFmpeg duoi danh nghia mot tep .srt.
        if chang is StudioStage.PHU_DE and \
                getattr(ban_ghi, "media_type", None) is not MediaType.SUBTITLES:
            raise StudioProjectError("Tệp này không phải phụ đề.")
        return ban_ghi

    def _novel_cua_toi(self, actor: Profile, novel_id: str):
        if not novel_id:
            return None
        try:
            n = self._store.get_novel(novel_id)
        except NotFoundError:
            raise NotFoundError("Không tìm thấy truyện này.") from None
        if n.owner_id != actor.user_id:
            raise NotFoundError("Không tìm thấy truyện này.")
        return n

    # -- CRUD -----------------------------------------------------------------

    def tao(self, actor: Profile, *, title: str, description: str = "",
            novel_id: str = "") -> StudioProject:
        t = (title or "").strip()
        if not t:
            raise StudioProjectError("Dự án cần một cái tên.")
        if len(t) > 120:
            raise StudioProjectError("Tên dự án tối đa 120 ký tự.")
        if self._du_an.dem(actor.user_id) >= TRAN_DU_AN:
            raise StudioProjectError(
                f"Đã đạt trần {TRAN_DU_AN} dự án — xoá bớt dự án cũ.")
        if novel_id:
            self._novel_cua_toi(actor, novel_id)
        return self._du_an.luu(StudioProject(
            owner_id=actor.user_id, title=t,
            description=(description or "")[:2000], novel_id=novel_id))

    def danh_sach(self, actor: Profile) -> List[StudioProject]:
        return self._du_an.liet_ke(actor.user_id)

    def lay(self, actor: Profile, project_id: str) -> StudioProject:
        return self._du_an.lay(actor.user_id, project_id)

    def sua(self, actor: Profile, project_id: str, *,
            title: Optional[str] = None, description: Optional[str] = None,
            novel_id: Optional[str] = None) -> StudioProject:
        du_an = self._du_an.lay(actor.user_id, project_id)
        if title is not None:
            t = title.strip()
            if not t:
                raise StudioProjectError("Dự án cần một cái tên.")
            du_an.title = t[:120]
        if description is not None:
            du_an.description = description[:2000]
        if novel_id is not None:
            if novel_id:
                self._novel_cua_toi(actor, novel_id)
            du_an.novel_id = novel_id
        du_an.updated_at = now_iso()
        return self._du_an.luu(du_an)

    def xoa(self, actor: Profile, project_id: str) -> bool:
        return self._du_an.xoa(actor.user_id, project_id)

    # -- gan / go tham chieu --------------------------------------------------

    def gan(self, actor: Profile, project_id: str, chang: StudioStage,
            ma: str) -> StudioProject:
        """Gan mot tai san vao du an — SAU khi da chung minh no la cua minh."""
        du_an = self._du_an.lay(actor.user_id, project_id)
        self._cua_toi(actor, chang, ma)
        try:
            du_an.gan(chang, ma)
        except ValueError as exc:
            raise StudioProjectError(str(exc)) from exc
        du_an.updated_at = now_iso()
        return self._du_an.luu(du_an)

    def go(self, actor: Profile, project_id: str, chang: StudioStage,
           ma: str) -> StudioProject:
        """Go mot tham chieu. KHONG xoa tai san — xem `store.xoa`."""
        du_an = self._du_an.lay(actor.user_id, project_id)
        du_an.go(chang, ma)
        du_an.updated_at = now_iso()
        return self._du_an.luu(du_an)

    # -- tien do --------------------------------------------------------------

    def tien_do(self, actor: Profile, du_an: StudioProject) -> List[TienDoChang]:
        """Tien do THAT cua sau chang. Khong bia mot mau so nao.

        Mau so CHI ton tai o hai cho co that:
          * Audio/Phụ đề — mau so la SO CHUONG cua truyen da gan. Khong gan
            truyen thi khong co mau so, va ta noi vay thay vi doan.
          * Nội dung — 0 hoac 1, chinh la "da gan truyen chua".
        """
        ra: List[TienDoChang] = []

        so_chuong = 0
        if du_an.novel_id:
            try:
                so_chuong = len(self._store.list_chapters(du_an.novel_id))
            except Exception:                                   # noqa: BLE001
                so_chuong = 0
        ra.append(TienDoChang(StudioStage.NOI_DUNG,
                              1 if du_an.novel_id else 0, 1))

        for chang in (StudioStage.DICH, StudioStage.HINH_ANH):
            ra.append(TienDoChang(chang, len(du_an.danh_sach(chang))))
        for chang in (StudioStage.AUDIO, StudioStage.PHU_DE):
            ra.append(TienDoChang(chang, len(du_an.danh_sach(chang)),
                                  so_chuong))
        ra.append(TienDoChang(StudioStage.VIDEO,
                              len(du_an.video_project_ids)))
        return ra

    # -- bo chon tai san ------------------------------------------------------

    @staticmethod
    def _dang_co(du_an: StudioProject, chang: StudioStage) -> set:
        """Nhung ma DA nam trong du an o mot chang.

        Nội dung khong di qua `danh_sach()`: no la MOT truong don
        (`novel_id`), khong phai mot danh sach — xem `StudioProject`.
        """
        if chang is StudioStage.NOI_DUNG:
            return {du_an.novel_id} if du_an.novel_id else set()
        return set(du_an.danh_sach(chang))

    def tai_san_cua_toi(self, actor: Profile, chang: StudioStage, *,
                        project_id: str = "",
                        tran: int = 200) -> List[Dict[str, Any]]:
        """Nguon cua BO CHON TAI SAN dung chung.

        Luon CHI tra tai san cua chinh nguoi goi. `project_id` khong loc bot
        — no chi danh dau muc nao DA nam trong du an, de bo chon hien duoc
        "đã thêm" thay vi de nguoi dung gan trung.

        `tran=0` la KHONG cat. Chi `nhan_tham_chieu` dung duong do: no tra
        nhan cho nhung ma du an DA giu, va mot du an cu tro toi mot tai san
        nam ngoai 200 muc moi nhat thi cat di se lam no trong nhu da mat.
        """
        trong_du_an: set = set()
        if project_id:
            du_an = self._du_an.tim(actor.user_id, project_id)
            if du_an is not None:
                trong_du_an = self._dang_co(du_an, chang)

        ra: List[Dict[str, Any]] = []
        if chang is StudioStage.NOI_DUNG:
            # Truyen CUA CHINH MINH, ke ca ban nhap: du an Studio la cho lam
            # viec, va thu dang lam do dang thi theo dinh nghia chua xuat ban.
            for n in self._store.list_novels(owner_id=actor.user_id):
                try:
                    so = len(self._store.list_chapters(n.novel_id))
                except Exception:                               # noqa: BLE001
                    so = 0
                ra.append({"id": n.novel_id,
                           "label": n.title or "Truyện chưa đặt tên",
                           "detail": f"{so} chương",
                           "created_at": n.created_at})
        elif chang is StudioStage.AUDIO:
            for ch in self._store.chapters_for_owner(actor.user_id):
                for t in self._store.tracks_for_chapter(ch.chapter_id):
                    if t.owner_id != actor.user_id:
                        continue
                    ra.append({"id": t.track_id, "label": ch.title,
                               "detail": f"{t.duration_seconds:.0f}s",
                               "created_at": t.created_at})
        elif chang is StudioStage.HINH_ANH and self._anh is not None:
            for a in self._anh.liet_ke(actor.user_id):
                ra.append({"id": a.image_id,
                           "label": (a.prompt or "Ảnh")[:80],
                           "detail": a.aspect_ratio,
                           "created_at": a.created_at})
        elif chang is StudioStage.PHU_DE and self._media is not None:
            for a in self._media.list_assets(actor.user_id):
                if a.media_type is not MediaType.SUBTITLES:
                    continue
                ra.append({"id": a.asset_id,
                           "label": _ten_tep(a.object_key, a.created_at),
                           "detail": f"{a.size_bytes} B",
                           "created_at": a.created_at})
        elif chang is StudioStage.VIDEO and self._video is not None:
            for v in self._video.liet_ke(actor.user_id):
                ra.append({"id": v.project_id, "label": v.title,
                           "detail": v.render_state.value,
                           "created_at": v.created_at})
        elif chang is StudioStage.DICH and self._dich is not None:
            for p in self._dich.list_projects(actor.user_id):
                ra.append({"id": p.project_id, "label": p.title,
                           "detail": p.target_language,
                           "created_at": p.created_at})

        ra.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        for x in ra:
            x["in_project"] = x["id"] in trong_du_an
        return ra if tran <= 0 else ra[:tran]

    # -- nhan cho tham chieu DA gan -------------------------------------------

    def nhan_tham_chieu(self, actor: Profile,
                        du_an: StudioProject) -> Dict[str, List[Dict[str, Any]]]:
        """Nhan doc duoc cho tung tham chieu du an dang giu.

        Ban ghi chi giu ID, va dung la no nen giu the. Nhung mot khong gian
        lam viec bay ra `trk_9f2a…` thi khong ai biet do la chuong nao — nen
        NHAN duoc tra o day, tu DUNG nguon ma bo chon dung, khong phai tu mot
        bang thu hai.

        Mot ma khong tra loi duoc thi danh dau `missing` chu khong bien mat:
        tai san da bi xoa o cho khac van la mot thu nguoi dung can thay de go
        ra — giau di la de lai mot muc ma khong ai sua duoc.
        """
        ra: Dict[str, List[Dict[str, Any]]] = {}
        for chang in StudioStage:
            ma_da_gan = self._dang_co(du_an, chang)
            if not ma_da_gan:
                ra[chang.value] = []
                continue
            try:
                kho = {x["id"]: x
                       for x in self.tai_san_cua_toi(actor, chang, tran=0)}
            except Exception:                                   # noqa: BLE001
                kho = {}
            thu_tu = ([du_an.novel_id] if chang is StudioStage.NOI_DUNG
                      else du_an.danh_sach(chang))
            ra[chang.value] = [
                {"id": ma,
                 "label": kho.get(ma, {}).get("label", ""),
                 "detail": kho.get(ma, {}).get("detail", ""),
                 "missing": ma not in kho}
                for ma in thu_tu
            ]
        return ra
