# -*- coding: utf-8 -*-
"""SỰ CỐ BỀN — trạng thái phục hồi sống sót qua khởi động lại (V1.0, B3/§3).

`VongSuCo` trong `su_co.py` là một hàm quyết định THUẦN: cho nó lịch sử hỏng,
nó nói bước tiếp theo. Nó cố ý không biết gì về sổ. Tệp này là nửa còn lại —
nơi lịch sử đó SỐNG, để một lần khởi động lại giữa chừng không xoá mất nó.

VÌ SAO BỀN LÀ BẮT BUỘC, không phải tiện nghi: ngân sách sửa chữa chỉ có
nghĩa khi nó được ĐẾM qua các lần chạy. Một tiến trình Router tắt giữa lúc
sửa rồi bật lại với ngân sách đầy là một vòng lặp vô hạn mọc chân — đúng chế
độ hỏng mà cả `su_co.py` sinh ra để chặn.

LƯU Ở ĐÂU, và vì sao không thêm bảng: bản ghi đi vào SỔ SỰ KIỆN chung
(`ghi_su_kien` kind `INCIDENT_STATE`), và trạng thái hiện tại là bản ghi MỚI
NHẤT của việc đó. Không di trú lược đồ, không kho thứ hai cho cùng một loại
sự thật, và nó tự có sẵn dòng thời gian để đọc lại sau này.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.v10.su_co import (HanhDong, LoaiHong, NganSach,
                                              VongSuCo)

KIND = "INCIDENT_STATE"


@dataclass
class SuCoBen:
    """Hồ sơ một sự cố, đủ để tiếp tục sau khởi động lại."""

    incident_id: str
    project_id: str
    task_id: str
    #: Mục tiêu GỐC của người dùng — thứ không được quên khi worker hỏng.
    muc_tieu: str = ""
    execution_id: str = ""
    loai: str = LoaiHong.UNKNOWN.value
    chu_ky: str = ""
    bang_chung: Tuple[str, ...] = ()
    #: Đếm theo TỪNG loại hành động — chính là `VongSuCo.da_dung`.
    da_dung: Dict[str, int] = field(default_factory=dict)
    #: Đếm theo chữ ký hỏng — chính là `VongSuCo.dem_chu_ky`.
    dem_chu_ky: Dict[str, int] = field(default_factory=dict)
    chien_luoc: str = ""
    cho_chay_truoc: str = ""
    trang_thai: str = "DANG_MO"          # DANG_MO | DA_DONG
    tao_luc: float = field(default_factory=time.time)
    cap_nhat_luc: float = field(default_factory=time.time)

    # -- CHỜ TÀI NGUYÊN (V1.0) ---------------------------------------------
    #
    # Nằm CHUNG hồ sơ sự cố, không tách kho thứ hai: chờ tài nguyên là một
    # nhánh của cùng một sự cố, và nó phải sống sót qua khởi động lại theo
    # đúng cơ chế đã có. Tách ra là dựng nơi thứ hai cho cùng một loại sự
    # thật — chế độ hỏng đã phải sửa nhiều lần trong bản này.
    #
    #: Bể/tài khoản đang chờ (tên bể trong `SoTaiNguyen`).
    be_tai_nguyen: str = ""
    #: Nhà cung cấp + tài khoản, để bảng điều khiển đọc được mà không tra sổ.
    provider: str = ""
    account_id: str = ""
    #: Câu NGUYÊN VĂN nhà cung cấp trả về. Bằng chứng, không phải diễn giải.
    ly_do_tai_nguyen: str = ""
    #: Mốc reset ĐO ĐƯỢC. `None` = KHÔNG ĐO ĐƯỢC, và nó phải ở nguyên `None`.
    reset_luc: Optional[float] = None
    #: Lần chạy tiếp đủ điều kiện sớm nhất. `None` = chưa hẹn được.
    thu_lai_luc: Optional[float] = None
    #: Các bể đã XÉT và vì sao bị loại — `[(tên, lý do)]`.
    ung_vien_da_xet: Tuple[Tuple[str, str], ...] = ()
    #: Số lần đã CHỜ RESET cho sự cố này (trần ở `tai_nguyen.TRAN_CHO_RESET`).
    dem_cho_tai_nguyen: int = 0

    def to_dict(self) -> Dict:
        return {"incident_id": self.incident_id, "project_id": self.project_id,
                "task_id": self.task_id, "muc_tieu": self.muc_tieu[:600],
                "execution_id": self.execution_id, "loai": self.loai,
                "chu_ky": self.chu_ky, "bang_chung": list(self.bang_chung)[:10],
                "da_dung": dict(self.da_dung),
                "dem_chu_ky": dict(self.dem_chu_ky),
                "chien_luoc": self.chien_luoc,
                "cho_chay_truoc": self.cho_chay_truoc,
                "trang_thai": self.trang_thai, "tao_luc": self.tao_luc,
                "cap_nhat_luc": self.cap_nhat_luc,
                "be_tai_nguyen": self.be_tai_nguyen,
                "provider": self.provider, "account_id": self.account_id,
                "ly_do_tai_nguyen": self.ly_do_tai_nguyen[:300],
                "reset_luc": self.reset_luc,
                "thu_lai_luc": self.thu_lai_luc,
                "ung_vien_da_xet": [list(x) for x in
                                    self.ung_vien_da_xet[:12]],
                "dem_cho_tai_nguyen": self.dem_cho_tai_nguyen}

    @classmethod
    def from_dict(cls, d: Dict) -> "SuCoBen":
        return cls(
            incident_id=str(d.get("incident_id") or ""),
            project_id=str(d.get("project_id") or ""),
            task_id=str(d.get("task_id") or ""),
            muc_tieu=str(d.get("muc_tieu") or ""),
            execution_id=str(d.get("execution_id") or ""),
            loai=str(d.get("loai") or LoaiHong.UNKNOWN.value),
            chu_ky=str(d.get("chu_ky") or ""),
            bang_chung=tuple(str(x) for x in (d.get("bang_chung") or ())),
            da_dung={str(k): int(v) for k, v in
                     (d.get("da_dung") or {}).items()},
            dem_chu_ky={str(k): int(v) for k, v in
                        (d.get("dem_chu_ky") or {}).items()},
            chien_luoc=str(d.get("chien_luoc") or ""),
            cho_chay_truoc=str(d.get("cho_chay_truoc") or ""),
            trang_thai=str(d.get("trang_thai") or "DANG_MO"),
            tao_luc=float(d.get("tao_luc") or time.time()),
            cap_nhat_luc=float(d.get("cap_nhat_luc") or time.time()),
            be_tai_nguyen=str(d.get("be_tai_nguyen") or ""),
            provider=str(d.get("provider") or ""),
            account_id=str(d.get("account_id") or ""),
            ly_do_tai_nguyen=str(d.get("ly_do_tai_nguyen") or ""),
            # `or None` LÀ SAI ở đây: `0.0` là một mốc hợp lệ về kiểu, và
            # quan trọng hơn — `None` phải đi ra `None`, không được biến
            # thành một con số. Đọc tường minh.
            reset_luc=(float(d["reset_luc"])
                       if d.get("reset_luc") is not None else None),
            thu_lai_luc=(float(d["thu_lai_luc"])
                         if d.get("thu_lai_luc") is not None else None),
            ung_vien_da_xet=tuple(
                (str(x[0]), str(x[1])) for x in
                (d.get("ung_vien_da_xet") or []) if len(x) >= 2),
            dem_cho_tai_nguyen=int(d.get("dem_cho_tai_nguyen") or 0))


class SoSuCo:
    """Đọc/ghi sự cố bền qua sổ sự kiện chung."""

    def __init__(self, store):
        self.store = store

    def _doc_meta(self, e) -> Dict:
        m = e.get("meta") if isinstance(e, dict) else None
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except (TypeError, ValueError):
                m = None
        return m if isinstance(m, dict) else {}

    def hien_tai(self, task_id: str) -> Optional[SuCoBen]:
        """Bản ghi MỚI NHẤT của việc này, nếu sự cố còn mở.

        `store.su_kien` trả về `ORDER BY id DESC` — **mới nhất TRƯỚC**. Bản
        đầu của hàm này gọi `reversed()` rồi lấy bản đầu tiên, tức là lấy
        đúng bản ghi CŨ NHẤT.

        Hậu quả đo được trên đường thật (2026-09-13): sau hai lần hỏng liên
        tiếp, `da_dung` vẫn là `{'sua_tai_cho': 1}` và `dem_chu_ky` vẫn là 1 —
        mỗi lần hỏng lại nạp ngân sách của lần ĐẦU rồi ghi đè lên. Tức là
        ngân sách không bao giờ cạn, và bộ ngắt mạch không bao giờ nổ: đúng
        cái vòng lặp vô hạn mà cả tầng này sinh ra để chặn.
        """
        try:
            ds = self.store.su_kien(task_id=task_id, limit=200)
        except Exception:                                     # noqa: BLE001
            return None
        for e in ds:                       # đã là mới-nhất-trước
            if str(e.get("kind")) != KIND:
                continue
            sc = SuCoBen.from_dict(self._doc_meta(e))
            return sc if sc.incident_id else None
        return None

    def mo_hoac_lay(self, *, project_id: str, task_id: str, muc_tieu: str,
                    execution_id: str = "") -> SuCoBen:
        """Sự cố đang mở của việc này, hoặc mở một cái mới.

        Không bao giờ mở hai sự cố cho cùng một việc đang chạy: ngân sách
        phải đếm trên MỘT hồ sơ, không thì mỗi lần hỏng lại có ngân sách mới.
        """
        cu = self.hien_tai(task_id)
        if cu is not None and cu.trang_thai == "DANG_MO":
            if muc_tieu and not cu.muc_tieu:
                cu.muc_tieu = muc_tieu
            return cu
        return SuCoBen(
            incident_id=f"sc_{uuid.uuid4().hex[:12]}", project_id=project_id,
            task_id=task_id, muc_tieu=muc_tieu or "",
            execution_id=execution_id)

    def ghi(self, sc: SuCoBen, *, chi_tiet: str = "", level: str = "WARNING"
            ) -> SuCoBen:
        sc.cap_nhat_luc = time.time()
        try:
            self.store.ghi_su_kien(
                KIND, project_id=sc.project_id, task_id=sc.task_id,
                level=level,
                detail=(chi_tiet or f"{sc.loai} · {sc.chien_luoc}")[:400],
                meta=sc.to_dict())
        except Exception:                                     # noqa: BLE001
            # Mot so su co ghi hong KHONG duoc lam chet duong thuc thi.
            pass
        return sc

    def dong(self, sc: SuCoBen, *, ly_do: str = "") -> SuCoBen:
        sc.trang_thai = "DA_DONG"
        return self.ghi(sc, chi_tiet=f"đóng sự cố: {ly_do}"[:400], level="INFO")

    # -- cau noi sang bo quyet dinh THUAN -----------------------------------

    def vong(self, sc: SuCoBen, *, ngan_sach: Optional[NganSach] = None
             ) -> VongSuCo:
        """Dựng lại `VongSuCo` TỪ hồ sơ bền — ngân sách tiếp tục, không reset.

        Đây là chỗ tính bền trở thành hành vi: `da_dung`/`dem_chu_ky` nạp
        ngược vào bộ quyết định, nên một lần khởi động lại giữa chừng không
        cấp thêm lượt sửa nào.
        """
        v = VongSuCo(ngan_sach)
        v.da_dung = dict(sc.da_dung)
        v.dem_chu_ky = dict(sc.dem_chu_ky)
        return v

    def cap_nhat_tu_vong(self, sc: SuCoBen, v: VongSuCo, qd) -> SuCoBen:
        sc.da_dung = dict(v.da_dung)
        sc.dem_chu_ky = dict(v.dem_chu_ky)
        sc.loai = qd.loai.value
        sc.chu_ky = qd.chu_ky
        sc.chien_luoc = qd.hanh_dong.value
        return sc
