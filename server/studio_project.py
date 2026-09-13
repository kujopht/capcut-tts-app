"""
Studio Project — SOI DAY noi cac cong cu Studio lai voi nhau.

NGUYEN TAC DUY NHAT cua tep nay: du an chi giu THAM CHIEU, khong giu du
lieu. Khong mot byte noi dung, mot ban dich, mot tam anh hay mot doan audio
nao duoc sao vao day.

Vi sao quan trong den the: moi tang da co kho rieng, vong doi rieng, va
duong don rac rieng (`TranslationProject`, `SavedImage`, `AudioTrack`,
`MediaAsset`, `VideoProject`). Sao du lieu sang mot bang thu hai la tao ra
hai nguon su that cho cung mot thu, va ke tu do moi lan sua o mot ben la
mot lan lech o ben kia. Mot danh sach id thi khong the lech.

He qua co chu dich: xoa mot du an KHONG xoa tai san cua no. Du an la mot
CACH NHIN, khong phai mot cai thung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from server.domain import new_id, now_iso


class StudioStage(str, Enum):
    """Sau chang cua quy trinh Studio, DUNG THU TU nay.

    Thu tu la quy trinh chu khong phai thu tu cai dat: chu -> dich -> anh ->
    audio -> phu de -> video. Video dung cuoi vi no la cho moi thu phia
    truoc gop lai.
    """

    NOI_DUNG = "noi_dung"
    DICH = "dich"
    HINH_ANH = "hinh_anh"
    AUDIO = "audio"
    PHU_DE = "phu_de"
    VIDEO = "video"


#: Nhan tieng Viet cua tung chang — MOT nguon, de giao dien khong tu dat lai
#: va lech voi backend.
NHAN_CHANG: Dict[StudioStage, str] = {
    StudioStage.NOI_DUNG: "Nội dung",
    StudioStage.DICH: "Dịch",
    StudioStage.HINH_ANH: "Hình ảnh",
    StudioStage.AUDIO: "Audio",
    StudioStage.PHU_DE: "Phụ đề",
    StudioStage.VIDEO: "Video",
}

#: Tran so tham chieu moi loai, moi du an. Khong phai gioi han thuong mai —
#: chi la chot chong mot vong lap hong nhoi mot trieu id vao mot ban ghi.
TRAN_THAM_CHIEU = 500


@dataclass
class StudioProject:
    """Mot du an Studio: mot cai ten + sau danh sach tham chieu."""

    owner_id: str
    title: str
    description: str = ""

    #: Nội dung — `Novel.novel_id`. MOT truyen cho moi du an: du an la "tac
    #: pham nay", va cho hai truyen vao mot du an thi moi cau hoi ve sau
    #: ("dich chuong nao?", "audio cua truyen nao?") deu mat mot cau tra loi.
    novel_id: str = ""

    #: Cac danh sach con lai la NHIEU-nhieu: mot ban dich co the phuc vu
    #: nhieu du an, mot tam anh co the dung lai.
    translation_project_ids: List[str] = field(default_factory=list)
    image_ids: List[str] = field(default_factory=list)
    audio_track_ids: List[str] = field(default_factory=list)
    subtitle_asset_ids: List[str] = field(default_factory=list)
    video_project_ids: List[str] = field(default_factory=list)

    project_id: str = field(default_factory=lambda: new_id("spr"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    # -- tham chieu ----------------------------------------------------------

    def danh_sach(self, chang: StudioStage) -> List[str]:
        """Danh sach tham chieu cua MOT chang. Nội dung khong dung duong nay."""
        return {
            StudioStage.DICH: self.translation_project_ids,
            StudioStage.HINH_ANH: self.image_ids,
            StudioStage.AUDIO: self.audio_track_ids,
            StudioStage.PHU_DE: self.subtitle_asset_ids,
            StudioStage.VIDEO: self.video_project_ids,
        }[chang]

    def gan(self, chang: StudioStage, ma: str) -> bool:
        """Them mot tham chieu. `False` neu da co — gan hai lan la vo hai."""
        ds = self.danh_sach(chang)
        if ma in ds:
            return False
        if len(ds) >= TRAN_THAM_CHIEU:
            raise ValueError(
                f"Dự án đã đạt trần {TRAN_THAM_CHIEU} mục cho {NHAN_CHANG[chang]}.")
        ds.append(ma)
        return True

    def go(self, chang: StudioStage, ma: str) -> bool:
        ds = self.danh_sach(chang)
        if ma not in ds:
            return False
        ds.remove(ma)
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "description": self.description,
            "novel_id": self.novel_id,
            "translation_project_ids": list(self.translation_project_ids),
            "image_ids": list(self.image_ids),
            "audio_track_ids": list(self.audio_track_ids),
            "subtitle_asset_ids": list(self.subtitle_asset_ids),
            "video_project_ids": list(self.video_project_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TienDoChang:
    """Tien do MOT chang — cho the du an o trang Tổng quan.

    `tong` la 0 khi khong co mau so THAT. Do la ly do lop nay ton tai thay
    vi mot con so phan tram: "8/10 chương có audio" la mot su that dem duoc,
    con "80% hoan thanh" thi khong — va bia mot mau so ra de ve cho dep la
    dung thu de bai cam.
    """

    chang: StudioStage
    so: int
    tong: int = 0

    @property
    def co_mau_so(self) -> bool:
        return self.tong > 0

    @property
    def xong(self) -> bool:
        """Chi tra `True` khi CO mau so that va da day."""
        return self.co_mau_so and self.so >= self.tong

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.chang.value,
            "label": NHAN_CHANG[self.chang],
            "count": self.so,
            # `None` chu khong phai 0: giao dien phai phan biet duoc "khong co
            # mau so" voi "mau so bang khong".
            "total": self.tong if self.tong > 0 else None,
            "done": self.xong,
        }
