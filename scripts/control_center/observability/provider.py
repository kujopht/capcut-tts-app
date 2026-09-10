"""Giao diện provider + luật CHỈ-ĐỌC cưỡng chế bằng mã.

Một provider là một cách QUAN SÁT một dự án. Nó không bao giờ là một cách
TÁC ĐỘNG lên dự án đó. Luật này không nằm trong tài liệu mà nằm trong
`_KHONG_DUOC_CO` bên dưới cùng một bài kiểm quét cả gói: một provider mới
mang theo một động từ đổi trạng thái sẽ làm bộ kiểm đỏ, chứ không lặng lẽ
thành một cái nút "restart service" trong một công cụ quan sát.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Protocol, Sequence

from scripts.control_center.observability.model import (AnhChupSong,
                                                        KhoiQuanSat,
                                                        QuanSat, TrangThai)

#: Dong tu KHONG BAO GIO duoc xuat hien trong mot provider. Danh sach nay
#: la ban dich cua muc 10 trong yeu cau V0.5 sang mot thu kiem duoc.
#:
#: Doc thi duoc: `systemctl is-active`, `systemctl show`, `cat status.json`.
#: Con `restart`/`stop`/`rm`/`put`/`deploy` thi khong — mot lop QUAN SAT
#: khong duoc mang duong tac dong, vi luc do no thanh mot API dieu khien
#: production nam sau mot cai ten vo hai.
KHONG_DUOC_CO: Sequence[str] = (
    "systemctl restart", "systemctl stop", "systemctl start",
    "systemctl reload", "systemctl enable", "systemctl disable",
    "service restart", "service stop", "shutdown", "reboot",
    "rm -rf", "rm -f", "unlink", "truncate",
    "aws s3 rm", "aws s3 rb", "aws s3 cp", "aws s3 sync",
    "r2 delete", "r2 put", "bucket delete",
    "wrangler deploy", "wrangler delete", "wrangler secret",
    "appwrite databases delete", "appwrite databases create",
    "appwrite databases update", "drive.files.delete", "files.delete",
    "iam ", "put-object", "delete-object", "kill ", "pkill", "taskkill",
)


class ProjectObservabilityProvider(Protocol):
    """Một cách quan sát. `thu(...)` phải KHÔNG BAO GIỜ ném.

    Provider nào cũng chạy trên đường của một tin nhắn chat, nên một lỗi
    mạng ở một probe không được phép làm cả lượt hội thoại vỡ. Hợp đồng:
    trả về `KhoiQuanSat` mang `UNKNOWN`/`UNAVAILABLE` kèm lý do, không
    ném lên.
    """

    ma: str
    nhan: str
    nhom: str          # "router" | "dich_vu" | "luu_tru" | "ung_dung" | "kho"

    def kha_nang(self) -> Sequence[str]:
        """Những khoá quan sát provider này CÓ THỂ cho ra."""

    def thu(self, ctx) -> KhoiQuanSat:
        """Đo một lần. Không ném. Không tác động."""


class ProviderCoSo:
    """Phần chung: bọc `thu()` để không provider nào ném ra ngoài."""

    ma = "co-so"
    nhan = "Cơ sở"
    nhom = "dich_vu"
    #: Tran thoi gian cho MOT lan do. Bat buoc: mot probe SSH cham khong
    #: duoc keo ca luot chat theo.
    han = 8.0

    def kha_nang(self) -> Sequence[str]:
        return ()

    def _do(self, ctx) -> KhoiQuanSat:                  # pragma: no cover
        raise NotImplementedError

    def thu(self, ctx) -> KhoiQuanSat:
        t0 = time.perf_counter()
        try:
            k = self._do(ctx)
        except Exception as exc:                        # noqa: BLE001
            # KHONG de lot ngoai le. Va KHONG bien loi thanh `DOWN`: mot
            # probe hong khong noi gi ve he thong duoc quan sat.
            k = KhoiQuanSat(khoa=self.ma, nhan=self.nhan)
            k.them(QuanSat(
                khoa="probe", trang_thai=TrangThai.UNKNOWN,
                nguon=self.ma,
                ly_do=f"probe lỗi: {type(exc).__name__}: {exc}"[:200]))
        k.mat_giay = round(time.perf_counter() - t0, 3)  # type: ignore
        return k


def gop(project_id: str, khoi: Sequence[KhoiQuanSat],
        nhom_cua: Dict[str, str],
        nhat_ky: Optional[List[Dict]] = None) -> AnhChupSong:
    """Ghép các khối rời thành một `AnhChupSong`."""
    a = AnhChupSong(project_id=project_id)
    for k in khoi:
        nhom = nhom_cua.get(k.khoa, "dich_vu")
        getattr(a, nhom)[k.khoa] = k
    a.nhat_ky_provider = list(nhat_ky or [])
    return a
