"""
Giong cuc bo (Piper / NghiTTS): danh sach trang, dinh tuyen, concurrency, cache.

Bo test nay khoa lai mot loai lo hong va vai bay van hanh cu the:

  * `/api/voices` loc giong cuc bo, nhung `POST /api/jobs` KHONG he kiem tra
    `voice_id`. Mot giong bi an van submit job duoc — hai nua he thong dung hai
    dieu kien khac nhau.
  * Mot co boolean bat-tat-tat-ca (`allow_unverified_local_voices`) doi mot
    bien moi truong la mo ca ba giong Piper built-in, ke ca hai giong khong co
    model — sinh ra job khong worker nao chay duoc.
  * Tien trinh API tren Render khong co file `.onnx` nao, nen `installed` o do
    luon false. Giao dien loc theo `installed` thi Ngoc Huyen khong bao gio
    hien ra du da duoc duyet.
  * Piper chay CPU va dung chung mot doi tuong `PiperVoice`. Hai job song song
    la dieu chua ai chung minh la an toan.

Chay hoan toan offline: khong nap model that, khong goi TTS.
"""

from __future__ import annotations

import inspect
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from server import main as server_main
from server import tts_bridge
from server.config import Settings, _local_voices


class CauHinhGia:
    """Chi mang truong ma cac ham loc doc toi."""

    def __init__(self, *voices: str, languages=("vi",)):
        self.local_voices = tuple(voices)
        self.public_voice_languages = tuple(languages)


class VuTruNghiTTS(unittest.TestCase):

    def test_suy_ra_tu_catalog_chu_khong_go_tay(self) -> None:
        from desktop_app.providers.builtin_catalog import piper_builtin_voices

        self.assertEqual(tts_bridge.nghitts_voice_ids(),
                         frozenset(v.id for v in piper_builtin_voices()))

    def test_co_ngochuyen(self) -> None:
        self.assertIn("piper:ngochuyen", tts_bridge.nghitts_voice_ids())

    def test_khong_go_cung_danh_sach_trong_nguon(self) -> None:
        nguon = inspect.getsource(tts_bridge.nghitts_voice_ids)
        self.assertIn("piper_builtin_voices", nguon)


class DanhSachTrang(unittest.TestCase):

    def test_mac_dinh_dung_ngochuyen(self) -> None:
        self.assertEqual(Settings.local_voices, ("piper:ngochuyen",))

    def test_chi_giong_trong_danh_sach_duoc_phuc_vu(self) -> None:
        s = CauHinhGia("piper:ngochuyen")
        self.assertTrue(tts_bridge.voice_is_local_allowed("piper:ngochuyen", s))
        self.assertFalse(tts_bridge.voice_is_local_allowed("piper:calmwoman3688", s))

    def test_giong_ngoai_bo_nghitts_khong_bat_duoc_bang_cau_hinh(self) -> None:
        """
        Vong loc thu hai. Day la thu khien danh sach trang khac mot co bat-tat.

        Nguoi dung tha mot file `.onnx` la vao thu muc models roi khai bao no
        trong `FAS_LOCAL_VOICES` — van KHONG duoc phuc vu. Model la cua nguoi
        dung; thu duoc PHUC VU la quyet dinh cua ma nguon.
        """
        s = CauHinhGia("piper:ngochuyen", "piper:giong-la-nao-do")
        self.assertFalse(tts_bridge.voice_is_local_allowed("piper:giong-la-nao-do", s))
        self.assertEqual(tts_bridge.allowed_local_voice_ids(s),
                         frozenset({"piper:ngochuyen"}))

    def test_tat_het_bang_chuoi_rong(self) -> None:
        self.assertEqual(tts_bridge.allowed_local_voice_ids(CauHinhGia()),
                         frozenset())
        self.assertFalse(tts_bridge.voice_is_local_allowed("piper:ngochuyen",
                                                          CauHinhGia()))

    def test_giong_di_qua_mang_khong_bi_danh_sach_dung_toi(self) -> None:
        s = CauHinhGia()          # khong giong cuc bo nao duoc bat
        self.assertTrue(tts_bridge.voice_is_local_allowed("edge:vi-VN-HoaiMyNeural", s))
        self.assertTrue(tts_bridge.voice_is_local_allowed("capcut:BV075_streaming", s))

    def test_khong_con_co_blanket_nao_quyet_dinh(self) -> None:
        """`allow_unverified_local_voices` khong duoc dieu khien viec loc nua."""
        nguon = inspect.getsource(tts_bridge.list_voices)
        self.assertNotIn("allow_unverified_local_voices", nguon)
        # Loc di qua `voice_is_public`, vốn hoi ca ngon ngu lan danh sach trang.
        self.assertIn("voice_is_public", nguon)
        self.assertIn("allowed_local_voice_ids",
                      inspect.getsource(tts_bridge.voice_is_local_allowed))


class DocBienMoiTruong(unittest.TestCase):

    def setUp(self) -> None:
        import os

        self._cu = os.environ.get("FAS_LOCAL_VOICES")

    def tearDown(self) -> None:
        import os

        if self._cu is None:
            os.environ.pop("FAS_LOCAL_VOICES", None)
        else:
            os.environ["FAS_LOCAL_VOICES"] = self._cu

    def test_khong_dat_thi_giu_mac_dinh(self) -> None:
        import os

        os.environ.pop("FAS_LOCAL_VOICES", None)
        self.assertEqual(_local_voices(), Settings.local_voices)

    def test_chuoi_rong_KHAC_voi_khong_dat(self) -> None:
        # Phai tat het duoc ma khong phai sua ma nguon.
        import os

        os.environ["FAS_LOCAL_VOICES"] = ""
        self.assertEqual(_local_voices(), ())

    def test_nhieu_id_va_bo_khoang_trang(self) -> None:
        import os

        os.environ["FAS_LOCAL_VOICES"] = " piper:ngochuyen , piper:deepman3909 "
        self.assertEqual(_local_voices(),
                         ("piper:ngochuyen", "piper:deepman3909"))


class MotNguonSuThatDuyNhat(unittest.TestCase):
    """`/api/voices` va duong tao job phai dung CUNG mot dieu kien."""

    def test_ca_hai_deu_goi_cung_mot_ham(self) -> None:
        # `/api/voices` loc bang `voice_is_public`; endpoint tao job cuong che
        # bang `ensure_voice_public`. Ca hai deu di qua CUNG hai vi ngu goc.
        self.assertIn("voice_is_public", inspect.getsource(tts_bridge.list_voices))
        nguon_public = inspect.getsource(tts_bridge.ensure_voice_public)
        self.assertIn("language_in_scope", nguon_public)
        self.assertIn("voice_is_local_allowed", nguon_public)
        self.assertIn("voice_is_local_allowed",
                      inspect.getsource(tts_bridge.ensure_voice_runnable))

    def test_route_tao_job_goi_ensure_voice_allowed(self) -> None:
        # Route la lop vo mong; rao giong nam o chinh than, va chinh than do
        # duoc CA duong don chuong va duong nhap hang loat dung chung.
        self.assertIn("_tao_job_cho_chuong",
                      inspect.getsource(server_main.create_job),
                      "route tạo job phải uỷ quyền cho `_tao_job_cho_chuong`")
        nguon = inspect.getsource(server_main._tao_job_cho_chuong)
        self.assertIn("ensure_voice_public", nguon)
        # Phai chan TRUOC khi ghi job xuong kho, khong phai sau.
        self.assertLess(nguon.index("ensure_voice_public"),
                        nguon.index("store.create_job"))

    def test_worker_cung_kiem_tra_lai(self) -> None:
        # Route co the bi bo qua (job cu, goi truc tiep). Worker la hang rao
        # cuoi cung truoc khi thuc su tong hop.
        self.assertIn("ensure_voice_runnable",
                      inspect.getsource(tts_bridge.synthesize_chapter))

    def test_giong_bi_an_thi_bi_tu_choi(self) -> None:
        with self.assertRaises(tts_bridge.TtsBridgeError):
            tts_bridge.ensure_voice_runnable("piper:calmwoman3688", CauHinhGia())

    def test_giong_duoc_bat_thi_di_qua(self) -> None:
        tts_bridge.ensure_voice_runnable("piper:ngochuyen",
                                        CauHinhGia("piper:ngochuyen"))


class ClientKhongTuChonProviderHayModel(unittest.TestCase):

    def test_payload_tao_job_chi_co_bon_truong(self) -> None:
        truong = set(server_main.JobIn.model_fields)
        self.assertEqual(truong,
                         {"chapter_id", "voice_id", "rate", "chunk_chars"})

    def test_khong_co_truong_provider_hay_duong_dan_model(self) -> None:
        for cam in ("provider", "model_path", "model", "onnx", "engine"):
            self.assertNotIn(cam, server_main.JobIn.model_fields,
                             f"client không được truyền '{cam}'")


class ApiQuangBaDuocKhiKhongCoModel(unittest.TestCase):
    """Render khong chua model, nhung van phai chao ban giong da duyet."""

    def test_co_runs_on_worker_cho_giong_cuc_bo(self) -> None:
        nguon = inspect.getsource(tts_bridge.list_voices)
        self.assertIn('"runs_on_worker": is_local', nguon)

    def test_public_enabled_thay_cho_commercial_ready(self) -> None:
        nguon = inspect.getsource(tts_bridge.list_voices)
        self.assertIn('"public_enabled"', nguon)
        # So khop KHOA co dau nhay, khong so khop chuoi tran: ghi chu giai
        # thich vi sao ten cu bi bo van duoc nhac toi ten do, va no nen duoc
        # nhac toi.
        self.assertNotIn('"commercial_ready"', nguon,
                         "commercial_ready là phán đoán về giấy phép, không "
                         "phải sự thật kỹ thuật")


class ConcurrencyPiperBangMot(unittest.TestCase):

    def test_co_khoa_rieng_cho_piper(self) -> None:
        self.assertIsInstance(tts_bridge._PIPER_LOCK, type(threading.Lock()))

    def test_chi_mot_job_piper_chay_cung_luc(self) -> None:
        """Do THAT: hai thread cung vao, chi mot thread o trong tai mot thoi diem."""
        dang_trong = 0
        dinh = 0
        canh = threading.Lock()

        def mot_job() -> None:
            nonlocal dang_trong, dinh
            with tts_bridge._PIPER_LOCK:
                with canh:
                    dang_trong += 1
                    dinh = max(dinh, dang_trong)
                time.sleep(0.05)
                with canh:
                    dang_trong -= 1

        ts = [threading.Thread(target=mot_job) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=5)
        self.assertEqual(dinh, 1, "hai job Piper đã chạy chồng nhau")

    def test_giong_qua_mang_khong_bi_xep_hang(self) -> None:
        # Khoa rong phai that su khong khoa gi: hai thread vao duoc cung luc.
        vao = threading.Event()
        xong = threading.Event()

        def a() -> None:
            with tts_bridge._KHONG_KHOA:
                vao.set()
                xong.wait(timeout=2)

        t = threading.Thread(target=a)
        t.start()
        self.assertTrue(vao.wait(timeout=2))
        with tts_bridge._KHONG_KHOA:      # khong duoc chan
            pass
        xong.set()
        t.join(timeout=5)

    def test_khoa_chi_ap_cho_provider_cuc_bo(self) -> None:
        nguon = inspect.getsource(tts_bridge.synthesize_chapter)
        self.assertIn("_PIPER_LOCK if voice.provider == LOCAL_PROVIDER", nguon)

    def test_khoa_bao_ngoai_khong_giu_khi_don_dep(self) -> None:
        # Giu khoa trong luc xoa tep tam la chan job ke tiep vo co. So khop
        # "finally:" co dau hai cham — ghi chu trong ham co nhac "try/finally".
        self.assertNotIn("finally:",
                         inspect.getsource(tts_bridge.synthesize_chapter),
                         "phần dọn dẹp phải nằm ngoài vùng giữ khoá")
        self.assertIn("finally:",
                      inspect.getsource(tts_bridge._tong_hop_cac_doan),
                      "phần dọn dẹp vẫn phải tồn tại, chỉ là ở nơi khác")


class ModelChiNapMotLan(unittest.TestCase):
    """Khong nap model that — chi kiem tra co che cache."""

    def test_provider_cache_theo_duong_dan_onnx(self) -> None:
        from desktop_app.providers.piper_provider import PiperLocalProvider

        nguon = inspect.getsource(PiperLocalProvider._load_voice)
        self.assertIn("self._loaded", nguon)
        self.assertIn("if key in self._loaded", nguon)

    def test_nap_lan_hai_tra_dung_doi_tuong_cu(self) -> None:
        from desktop_app.providers.piper_provider import PiperLocalProvider

        class ModelGia:
            onnx_path = Path("gia.onnx")
            config_path = Path("gia.onnx.json")

        so_lan = {"n": 0}

        class VoiceGia:
            @staticmethod
            def load(onnx, config_path=None):
                so_lan["n"] += 1
                return object()

        class ModuleGia:
            PiperVoice = VoiceGia

        prov = PiperLocalProvider(module=ModuleGia())
        a = prov._load_voice(prov.module, ModelGia())
        b = prov._load_voice(prov.module, ModelGia())
        self.assertIs(a, b)
        self.assertEqual(so_lan["n"], 1, "model bị nạp lại lần thứ hai")

    def test_registry_dung_chung_toan_tien_trinh(self) -> None:
        # Registry la bien toan cuc co khoa -> moi job dung chung mot
        # PiperLocalProvider, tuc la chung mot cache model.
        a = tts_bridge.get_registry()
        b = tts_bridge.get_registry()
        self.assertIs(a, b)


class ThieuModelThiBaoRoRang(unittest.TestCase):

    def test_chua_tai_model_thi_loi_phan_loai_dung(self) -> None:
        from desktop_app.models import ErrorKind
        from desktop_app.providers.base import PROVIDER_PIPER, Voice
        from desktop_app.providers.piper_provider import PiperLocalProvider
        from desktop_app.providers.base import ProviderError

        class ModelThieu:
            installed = False
            status_reason = "Chưa có tệp .onnx"
            onnx_path = Path("khong-co.onnx")

        class ManagerGia:
            models_dir = Path("khong-co")

            def find(self, key):
                return ModelThieu()

        prov = PiperLocalProvider(module=object(), manager=ManagerGia())
        voice = Voice(provider=PROVIDER_PIPER, voice_key="ngochuyen",
                      engine_voice_id="ngochuyen", display_name="Ngọc Huyền")
        with self.assertRaises(ProviderError) as ngu_canh:
            prov.synthesize(text="Xin chào.", voice=voice, dest=Path("x.mp3"))
        self.assertIs(ngu_canh.exception.kind, ErrorKind.MODEL_NOT_INSTALLED)

    def test_khong_bao_gio_tu_doi_sang_giong_khac(self) -> None:
        """
        Laptop tat -> job nam `pending`, KHONG duoc am tham doi giong.

        Doc thang tu nguon: khong co duong nao trong `_run_job` hay
        `synthesize_chapter` chon lai giong.
        """
        for ham in (server_main._run_job, tts_bridge.synthesize_chapter):
            nguon = inspect.getsource(ham)
            self.assertNotIn("fallback", nguon.lower())
            self.assertNotIn("configured_fallback", nguon)


class DonDepTepTam(unittest.TestCase):

    def test_provider_xoa_wav_va_thu_muc_tam(self) -> None:
        from desktop_app.providers.piper_provider import PiperLocalProvider

        nguon = inspect.getsource(PiperLocalProvider.synthesize)
        sau_finally = nguon[nguon.index("finally:"):]
        self.assertIn("wav_path.unlink(missing_ok=True)", sau_finally)
        self.assertIn("tmp_dir.rmdir()", sau_finally)

    def test_cau_noi_xoa_cac_part_va_thu_muc_lam_viec(self) -> None:
        nguon = inspect.getsource(tts_bridge._tong_hop_cac_doan)
        sau_finally = nguon[nguon.index("finally:"):]
        # Phai duyet CA thu muc, khong chi cac part da ghi nhan: mot job bi
        # ngat giua chung de lai tep `.part` khong nam trong `part_paths`, va
        # khi ay `rmdir` that bai lang le — ca thu muc o lai vinh vien.
        self.assertIn("work_dir.iterdir()", sau_finally)
        self.assertIn("work_dir.rmdir()", sau_finally)


class GhimPhuThuocWorker(unittest.TestCase):

    GOC = Path(__file__).resolve().parents[2]

    def test_co_tep_requirements_rieng_cho_worker(self) -> None:
        self.assertTrue((self.GOC / "server" / "requirements-worker.txt").is_file())

    def test_ghim_chinh_xac_phien_ban(self) -> None:
        noi_dung = (self.GOC / "server" / "requirements-worker.txt").read_text(
            encoding="utf-8")
        self.assertIn("piper-tts==1.6.0", noi_dung)
        self.assertNotIn("piper-tts>=", noi_dung,
                         "phải ghim chính xác: các bản Piper đổi chữ ký API")

    def test_web_khong_keo_theo_piper(self) -> None:
        # Tien trinh web khong chay job nen khong can onnxruntime. Goi Free chi
        # co 512 MB RAM.
        noi_dung = (self.GOC / "server" / "requirements.txt").read_text(
            encoding="utf-8")
        cac_dong = [d.strip() for d in noi_dung.splitlines()
                    if d.strip() and not d.strip().startswith("#")]
        self.assertNotIn("piper-tts==1.6.0", cac_dong)


if __name__ == "__main__":
    unittest.main()
