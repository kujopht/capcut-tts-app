"""
Tong so phan phai duoc bao NGAY, truoc khi tong hop phan dau tien.

LOI DA LEN PRODUCTION: `on_progress` chi duoc goi SAU khi moi phan xong, nen
trong suot phan dau tien `total_parts` van la 0. Giao dien khong co gi de hien
ngoai mot thanh chay vo dinh.

Voi chuong MOT PHAN thi do la TOAN BO thoi gian chay — nguoi dung khong bao gio
thay mot con so nao. Do that: chuong 12.689 ky tu (7 phan, 112 giay) dung im o
"Đang chia chương thành các phần…" suot 112 giay roi nhay thang sang hoan tat.

Bo test cu khong bat duoc vi moi ban gia lap `synthesize_chapter` deu tu goi
`on_progress(1, 1)` mot lan — chung mo phong KET QUA, khong mo phong TRINH TU.
O day dung `synthesize_chapter` THAT voi mot registry gia, va ghi lai day du
chuoi lot goi.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Tuple

from server import tts_bridge


class GiongGia:
    id = "mock:v1"
    provider = "mock"
    language = "vi-VN"
    engine_voice_id = "v1"
    display_name = "Giọng giả"
    installed = True


class RegistryGia:
    """Sinh ra tep mp3 gia cho moi doan. Khong goi provider that."""

    def __init__(self) -> None:
        self.so_lan_tong_hop = 0

    voices: List[Any] = []

    def voice_by_id(self, voice_id: str):
        return GiongGia()

    def synthesize(self, *, text, voice, dest, cancel=None, rate="1.0"):
        self.so_lan_tong_hop += 1
        Path(dest).write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 64)

    def close(self) -> None:
        pass


class Nen(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = RegistryGia()
        with tts_bridge._registry_lock:
            cu = tts_bridge._registry
            tts_bridge._registry = self.registry

        def hoan_nguyen() -> None:
            with tts_bridge._registry_lock:
                tts_bridge._registry = cu

        self.addCleanup(hoan_nguyen)

        # `_concat_mp3` can ffmpeg khi co nhieu hon mot doan. Thay bang mot ban
        # gia: bai test nay noi ve TRINH TU BAO TIEN DO, khong ve viec ghep tep.
        that = tts_bridge._concat_mp3

        def ghep_gia(parts, dest):
            Path(dest).write_bytes(b"".join(Path(p).read_bytes() for p in parts))
            return Path(dest).stat().st_size

        tts_bridge._concat_mp3 = ghep_gia
        self.addCleanup(lambda: setattr(tts_bridge, "_concat_mp3", that))

    def chay(self, text: str, chunk_chars: int = 2000) -> List[Tuple[int, int]]:
        """Chay that va tra ve DAY DU chuoi `(done, total)` da duoc bao."""
        goi: List[Tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "ra.mp3"
            tts_bridge.synthesize_chapter(
                text=text, voice_id="mock:v1", dest=dest, rate="1.0",
                chunk_chars=chunk_chars,
                on_progress=lambda d, t: goi.append((d, t)),
            )
        return goi


class BaoTongTruocKhiTongHop(Nen):

    def test_chuong_MOT_phan_nhan_0_1_roi_1_1(self) -> None:
        """
        Truong hop quan trong nhat: chuong ngan. Truoc ban va, no khong bao gio
        hien duoc phan tram nao ca.
        """
        self.assertEqual(self.chay("Xin chào các bạn."), [(0, 1), (1, 1)])

    def test_lot_goi_DAU_TIEN_da_mang_tong(self) -> None:
        goi = self.chay("Xin chào các bạn.")
        self.assertEqual(goi[0][1], 1, "lượt gọi đầu tiên phải đã biết tổng")
        self.assertEqual(goi[0][0], 0, "chưa phần nào xong thì done phải là 0")

    def test_bao_tong_TRUOC_khi_provider_duoc_goi_lan_nao(self) -> None:
        """
        Kiem TRINH TU that, khong chi kiem gia tri: neu lot bao dau tien nam
        sau lan tong hop dau tien thi con so den muon dung bang mot phan.
        """
        moc: List[str] = []
        that = self.registry.synthesize

        def ghi_lai(**kw):
            moc.append("tong_hop")
            return that(**kw)

        self.registry.synthesize = ghi_lai        # type: ignore[method-assign]

        with tempfile.TemporaryDirectory() as tmp:
            tts_bridge.synthesize_chapter(
                text="Xin chào các bạn.", voice_id="mock:v1",
                dest=Path(tmp) / "ra.mp3", rate="1.0", chunk_chars=2000,
                on_progress=lambda d, t: moc.append(f"bao {d}/{t}"),
            )
        self.assertEqual(moc[0], "bao 0/1",
                         f"lượt báo tổng không đứng đầu: {moc}")

    def test_chuong_NHIEU_phan_dem_len_dan_tu_0(self) -> None:
        goi = self.chay("Câu này dài vừa đủ. " * 60, chunk_chars=200)
        tong = goi[0][1]
        self.assertGreater(tong, 1, "cần nhiều hơn một phần cho bài test này")
        self.assertEqual(goi, [(i, tong) for i in range(tong + 1)])

    def test_tong_KHONG_doi_giua_chung(self) -> None:
        """Tong nhay giua chung se lam thanh tien trinh giat lui."""
        goi = self.chay("Câu này dài vừa đủ. " * 60, chunk_chars=200)
        self.assertEqual(len({t for _, t in goi}), 1)

    def test_lot_cuoi_la_HOAN_TAT(self) -> None:
        goi = self.chay("Câu này dài vừa đủ. " * 60, chunk_chars=200)
        done, tong = goi[-1]
        self.assertEqual(done, tong)

    def test_khong_co_callback_thi_khong_no(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tts_bridge.synthesize_chapter(
                text="Xin chào.", voice_id="mock:v1",
                dest=Path(tmp) / "ra.mp3", rate="1.0", chunk_chars=2000,
                on_progress=None,
            )


class KhongPhaDuongLuuTienDo(Nen):
    """
    Lot bao dau tien di thang vao `_progress_sink`, va no phai LUON duoc luu:
    day chinh la con so lam giao dien chuyen tu thanh vo dinh sang co ty le.
    """

    def test_sink_luu_ngay_lot_bao_dau_tien(self) -> None:
        from server import main as server_main
        from server.adapters import MockMetadataStore
        from server.domain import JobStatus, TtsJob

        store = MockMetadataStore()
        cu = server_main.store
        server_main.store = store
        self.addCleanup(lambda: setattr(server_main, "store", cu))

        job = TtsJob(owner_id="u", chapter_id="c", voice_id="mock:v1",
                     content_hash="h", status=JobStatus.RUNNING, attempts=1,
                     lease_owner=server_main.WORKER_ID,
                     lease_expires_at="2099-01-01T00:00:00+00:00")
        store.save_job(job)

        sink = server_main._progress_sink(job, 1)
        sink(0, 7)              # dung lot bao dau tien cua `synthesize_chapter`

        trong_kho = store.get_job(job.job_id)
        self.assertEqual(trong_kho.total_parts, 7,
                         "tổng phải được lưu ngay ở lượt báo đầu tiên")
        self.assertEqual(trong_kho.done_parts, 0)
        # Va ty le dan xuat van dung: 0/7 = 0%, khong phai "khong biet".
        self.assertEqual(trong_kho.progress_percent, 0)

    def test_lot_dau_tien_KHONG_bi_tiet_che_bo_qua(self) -> None:
        """
        Tiet che duoc phep bo cac lot giua chung, nhung KHONG duoc bo lot dau:
        no la con so duy nhat cho giao dien biet co bao nhieu phan.
        """
        from server import main as server_main
        from server.adapters import MockMetadataStore
        from server.domain import JobStatus, TtsJob

        store = MockMetadataStore()
        so_lan = {"n": 0}
        that = store.save_progress

        def dem(*a, **k):
            so_lan["n"] += 1
            return that(*a, **k)

        store.save_progress = dem               # type: ignore[method-assign]
        cu = server_main.store
        server_main.store = store
        self.addCleanup(lambda: setattr(server_main, "store", cu))

        job = TtsJob(owner_id="u", chapter_id="c", voice_id="mock:v1",
                     content_hash="h", status=JobStatus.RUNNING, attempts=1,
                     lease_owner=server_main.WORKER_ID,
                     lease_expires_at="2099-01-01T00:00:00+00:00")
        store.save_job(job)
        server_main._progress_sink(job, 1)(0, 7)
        self.assertEqual(so_lan["n"], 1)


if __name__ == "__main__":
    unittest.main()
