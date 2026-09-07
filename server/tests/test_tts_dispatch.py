"""
Cong dieu phoi Cloud Tasks phai TRO TIET DOI khi chua bat.

Day la mot ban trien khai TOI (dark deploy): ma nam trong kho, service chay
tren Cloud Run, nhung khong mot byte nao cua luu luong production duoc doi
duong. Test o day khoa lai dung dieu do, vi "co co bat/tat" la mot loi hua de
noi va kho giu — chi can mot import o dau tep hay mot lan goi khong phong ve la
duong tao job da doi hanh vi.

Ba tinh chat can giu:

  1. TAT thi `enqueue()` khong lam gi va khong cham mang.
  2. TAT thi `POST /api/jobs` di dung duong cu — khong them mot lan goi nao.
  3. BAT ma hong thi PHAI NEM (doi 2026-09-07). Nhanh `except` am tham cu la
     thu lam hai su co that tro nen vo hinh: thieu goi `google-cloud-tasks`,
     roi thieu credential GCP tren Render. Ca hai lan `POST /api/jobs` van tra
     201 va hang doi van RONG. Muon job van tao duoc khi Cloud Tasks su co thi
     TAT `FAS_TTS_DISPATCH` — tuong minh, khong am tham.
"""
from __future__ import annotations

import importlib
import os
import unittest
from unittest import mock


def _nap_lai(bien: dict):
    """Nap lai `tts_dispatch` voi bien moi truong da dat — hang so doc luc import."""
    with mock.patch.dict(os.environ, bien, clear=False):
        import server.tts_dispatch as td

        return importlib.reload(td)


class CongTat(unittest.TestCase):

    def tearDown(self):
        # Tra module ve trang thai theo moi truong that, khong de ro ri sang
        # test khac.
        import server.tts_dispatch as td

        importlib.reload(td)

    def test_mac_dinh_la_tat(self):
        td = _nap_lai({"FAS_TTS_DISPATCH": ""})
        self.assertFalse(td.duoc_bat())

    def test_tat_thi_enqueue_khong_cham_mang(self):
        """
        Khong chi 'tra ve None' — phai KHONG import va KHONG goi Cloud Tasks.

        Kiem bang cach chan chinh ham dung de tao client: neu no duoc dung toi
        thi test truot. Mot ban 'tat' ma van dung client la van tra gia ket noi
        tren duong nong.
        """
        td = _nap_lai({"FAS_TTS_DISPATCH": ""})
        with mock.patch.object(td, "cau_hinh_du") as cau_hinh:
            self.assertIsNone(td.enqueue("job_abc"))
            cau_hinh.assert_not_called()

    def test_bat_nhung_thieu_cau_hinh_thi_NEM(self):
        """
        DOI HOP DONG 2026-09-07: truoc day tra None, nay NEM.

        Ly do doi nam o docstring cua `tts_dispatch`: nhanh `except` am tham
        chinh la thu lam hai su co that tro nen vo hinh (thieu goi
        google-cloud-tasks, roi thieu credential GCP tren Render). Ca hai lan
        `POST /api/jobs` van tra 201 va hang doi van rong.
        """
        td = _nap_lai({"FAS_TTS_DISPATCH": "cloudtasks",
                       "FAS_TTS_TASKS_QUEUE": ""})
        self.assertTrue(td.duoc_bat())
        with self.assertRaises(td.DispatchError):
            td.enqueue("job_abc")

    def test_thieu_SA_JSON_thi_NEM_chu_khong_roi_ve_ADC(self):
        """
        Thieu credential PHAI nem, KHONG duoc am tham dung ADC.

        Day la su co that: tren Render khong co ADC nen
        `CloudTasksClient()` nem DefaultCredentialsError, bi nuot, va moi task
        bien mat trong im lang. Neu ai do bo `SA_JSON` di de "don gian hoa",
        bai nay do.
        """
        td = _nap_lai({
            "FAS_TTS_DISPATCH": "cloudtasks",
            "FAS_TTS_TASKS_QUEUE": "q", "FAS_TTS_TASKS_LOCATION": "asia-southeast1",
            "FAS_TTS_TASKS_PROJECT": "p", "FAS_TTS_TASKS_TARGET_URL": "https://x/tasks/tts",
            "FAS_TTS_TASKS_OIDC_SA": "sa@example.invalid",
            "FAS_TTS_TASKS_SA_JSON": "",
        })
        self.assertTrue(td.cau_hinh_du())
        with self.assertRaisesRegex(td.DispatchError, "FAS_TTS_TASKS_SA_JSON"):
            td.enqueue("job_abc")

    def test_SA_JSON_khong_phai_json_thi_NEM(self):
        td = _nap_lai({
            "FAS_TTS_DISPATCH": "cloudtasks",
            "FAS_TTS_TASKS_QUEUE": "q", "FAS_TTS_TASKS_LOCATION": "asia-southeast1",
            "FAS_TTS_TASKS_PROJECT": "p", "FAS_TTS_TASKS_TARGET_URL": "https://x/tasks/tts",
            "FAS_TTS_TASKS_OIDC_SA": "sa@example.invalid",
            "FAS_TTS_TASKS_SA_JSON": "khong-phai-json",
        })
        with self.assertRaises(td.DispatchError):
            td.enqueue("job_abc")


class PhuThuocPhaiDuocKhaiBao(unittest.TestCase):

    def test_thu_vien_cloud_tasks_phai_duoc_khai_bao(self):
        """
        `google-cloud-tasks` PHAI nam trong `server/requirements.txt`.

        VI SAO CAN MOT BAI TEST CHO MOT DONG REQUIREMENTS. Khi bai nay duoc
        viet, `enqueue()` con bat MOI exception va tra `None`, nen THIEU GOI im
        lang y het mot su co tam thoi: bat `FAS_TTS_DISPATCH=cloudtasks` ma
        khong task nao duoc day va khong gi keu len. `enqueue()` nay da nem,
        nhung dong requirements van phai duoc khoa — mot `DispatchError` luc
        chay that van la su co production, con bai test nay chan no tu truoc.

        Da MAC dung loi nay: commit d8e3062 duoc deploy len production voi
        `tts_dispatch.py` day du nhung KHONG co `google-cloud-tasks` trong
        requirements — va bo test cu van xanh, vi no chi kiem nhanh "thieu goi
        thi khong nem".

        Kiem VAN BAN requirements, khong phai `import`: import thanh cong o may
        lap trinh vien khong noi gi ve moi truong production.
        """
        from pathlib import Path

        req = (Path(__file__).resolve().parents[1] / "requirements.txt")
        dong_hieu_luc = [
            d.strip() for d in req.read_text(encoding="utf-8").splitlines()
            if d.strip() and not d.strip().startswith("#")
        ]
        self.assertTrue(
            any(d.lower().startswith("google-cloud-tasks") for d in dong_hieu_luc),
            "server/requirements.txt phai khai bao google-cloud-tasks — tien "
            "trinh WEB la noi goi enqueue, nen no thuoc tep nay chu khong phai "
            "requirements-worker.txt.",
        )


class DuongTaoJobKhongDoi(unittest.TestCase):

    def test_main_goi_enqueue_dung_mot_lan_va_sau_khi_ghi_ben_vung(self):
        """
        Doc THANG ma nguon cua `_tao_job_cho_chuong`.

        Vi sao doc ma nguon chu khong chay: chay duoc no doi mot kho Appwrite
        gia lap day du. Dieu can khoa o day la VI TRI cua lan goi — sau
        `create_job_once` va sau `_start_job_thread` — vi day som len truoc khi
        job nam ben vung la day mot job co the chua ton tai.
        """
        import inspect

        from server import main as api

        src = inspect.getsource(api._tao_job_cho_chuong)
        self.assertEqual(
            src.count("tts_dispatch.enqueue("), 1,
            "phai co DUNG mot lan goi enqueue trong duong tao job",
        )
        vi_tri_ghi = src.index("create_job_once")
        vi_tri_thread = src.index("_start_job_thread")
        vi_tri_day = src.index("tts_dispatch.enqueue(")
        self.assertLess(vi_tri_ghi, vi_tri_day,
                        "enqueue phai nam SAU khi job da duoc ghi ben vung")
        self.assertLess(vi_tri_thread, vi_tri_day,
                        "enqueue phai nam SAU _start_job_thread")

    def test_enqueue_khong_nam_trong_nhanh_reused(self):
        """Job da co san thi khong day them task — tranh nhan doi vo ich."""
        import inspect

        from server import main as api

        src = inspect.getsource(api._tao_job_cho_chuong)
        truoc_reused = src.index('"reused": True')
        self.assertLess(
            truoc_reused, src.index("tts_dispatch.enqueue("),
            "nhanh tra ve job da co (`reused`) phai thoat TRUOC lan goi enqueue",
        )


if __name__ == "__main__":
    unittest.main()
