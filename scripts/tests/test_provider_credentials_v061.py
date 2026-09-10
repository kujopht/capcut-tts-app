# -*- coding: utf-8 -*-
"""V0.6.1 — PROVIDER NGOÀI + KHO BÍ MẬT + RANH GIỚI KÝ ỨC (Part D, F, I, K).

Khoá GIẢ trong tệp này có HÌNH DẠNG khoá thật (`sk-…`, `AKID…`) để mọi bộ lọc
bắt được nếu nó lọt — đó chính là điều các bài kiểm đòi: khoá không có mặt
trong `providers.db` (đọc bytes), `control.db` (sự kiện), sổ ký ức (L0 +
blob), phản hồi API, thông điệp lỗi, `repr()` của tay cầm.

Không mạng, không khoá thật, không `agy`. HTTP là `HttpGia`.
"""
from __future__ import annotations

import json
import pickle
import secrets
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center.memory import DichVuKyUc                          # noqa: E402
from scripts.control_center.memory import bi_mat as BM                        # noqa: E402
from scripts.control_center.model import Project                              # noqa: E402
from scripts.control_center.providers import adapter as AD                    # noqa: E402
from scripts.control_center.providers import kho_bi_mat as KB                 # noqa: E402
from scripts.control_center.providers import preset as PS                     # noqa: E402
from scripts.control_center.providers import so as SO                         # noqa: E402
from scripts.control_center.providers.be import BeTaiKhoan                    # noqa: E402
from scripts.control_center.providers.dich_vu import (AUTO_ROUTING,           # noqa: E402
                                                      DichVuProvider,
                                                      LoiDichVuProvider)
from scripts.control_center.store import ControlStore                         # noqa: E402
from scripts.router_v4.runtime import BACKOFF_COOLDOWN, NGUONG_COOLDOWN       # noqa: E402

KHOA = "sk-" + "A1b2C3d4" * 5                # 43 ky tu, hinh dang OpenAI/DashScope
KHOA_TENCENT = "AKID" + "Zx9" * 8
ROOT = Path(__file__).resolve().parents[2]


def _khong_co_khoa(tc: unittest.TestCase, van: str, o_dau: str = ""):
    tc.assertNotIn(KHOA, van, o_dau)
    tc.assertNotIn(KHOA_TENCENT, van, o_dau)


def _http_ok_models(method, url, headers, body):
    if url.endswith("/models"):
        return 200, json.dumps({"data": [{"id": "qwen-plus"}, {"id": "qwen-turbo"}]}).encode()
    return 200, json.dumps({"choices": [{"message": {"content": "pong"}}],
                            "usage": {"total_tokens": 3}}).encode()


def _http_401_doi_khoa(method, url, headers, body):
    # Nha cung cap DOI LAI khoa trong loi — dung cai ta phai loc.
    auth = headers.get("Authorization", "")
    return 401, json.dumps({"error": {"message": f"Incorrect API key provided: "
                                                 f"{auth.replace('Bearer ', '')}"}}).encode()


def _http_khong_models(method, url, headers, body):
    if url.endswith("/models"):
        return 404, b'{"error":"not found"}'
    return 200, json.dumps({"choices": [{"message": {"content": ""}}]}).encode()


# ============================================================ kho bi mat ===

class TestKhoBiMat(unittest.TestCase):

    def test_bo_nho_vong_tron_va_tay_cam_mo(self):
        k = KB.KhoBiMatBoNho()
        k.luu("p.alias.abcd1234", KHOA)
        self.assertTrue(k.co("p.alias.abcd1234"))
        bm = k.lay("p.alias.abcd1234")
        self.assertEqual(repr(bm), "<BiMat ref=p.alias.abcd1234>")
        self.assertEqual(str(bm), f"{bm}")
        _khong_co_khoa(self, repr(bm) + str(bm) + f"{bm!r}{bm}")
        self.assertEqual(bm.dung(lambda v: v[-4:]), KHOA[-4:])
        with self.assertRaises(TypeError):
            pickle.dumps(bm)
        with self.assertRaises(TypeError):
            json.dumps(bm)
        self.assertNotIn("_gia_tri", dir(bm))
        self.assertTrue(k.xoa("p.alias.abcd1234"))
        self.assertFalse(k.co("p.alias.abcd1234"))
        with self.assertRaises(KB.KhongCoBiMat):
            k.lay("p.alias.abcd1234")

    def test_ref_va_gia_tri_bi_kiem(self):
        k = KB.KhoBiMatBoNho()
        for xau in ("", "a", "co khoang trang", "../x", "x/y"):
            with self.assertRaises(KB.LoiKhoBiMat):
                k.luu(xau, KHOA)
        for gt in ("", "   ", "co\nxuong dong", "x" * 5000, 123):
            with self.assertRaises(KB.LoiKhoBiMat):
                k.luu("ok.ref.1234", gt)
        # Thong diep loi khong mang gia tri.
        try:
            k.luu("ok.ref.1234", KHOA + "\n")
        except KB.LoiKhoBiMat as exc:
            _khong_co_khoa(self, str(exc))

    def test_kho_trong_khong_roi_ve_tep(self):
        k = KB.KhoBiMatTrong("máy kiểm thử")
        self.assertFalse(k.san()[0])
        with self.assertRaises(KB.KhoBiMatKhongSan):
            k.luu("p.a.12345678", KHOA)
        self.assertFalse(k.co("p.a.12345678"))
        self.assertFalse(k.mo_ta()["san"])

    def test_mo_kho_khong_bao_gio_tra_bo_nho(self):
        k = KB.mo_kho_bi_mat()
        self.assertNotIsInstance(k, KB.KhoBiMatBoNho)
        self.assertIn(k.kieu, ("windows-credential-manager", "khong-san"))

    def test_sinh_ref_on_dinh_khong_doan_duoc(self):
        a, b = KB.sinh_ref("alibaba", "Prod Key"), KB.sinh_ref("alibaba", "Prod Key")
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("alibaba.prod-key."))
        KB.kiem_ref(a)

    @unittest.skipUnless(sys.platform == "win32", "chỉ Windows")
    def test_windows_credential_manager_vong_tron_that(self):
        """Ghi/đọc/xoá MỘT mục thử dưới vùng tên riêng rồi dọn. Không chạm mục khác."""
        k = KB.KhoBiMatWindows()
        ok, ct = k.san()
        self.assertTrue(ok, ct)
        ref = f"kiemthu.probe.{secrets.token_hex(4)}"
        gia_tri = "gia-tri-thu-vo-hai-" + secrets.token_hex(8)
        try:
            k.luu(ref, gia_tri)
            self.assertTrue(k.co(ref))
            self.assertEqual(k.lay(ref).dung(lambda v: v), gia_tri)
        finally:
            k.xoa(ref)
        self.assertFalse(k.co(ref))
        self.assertTrue(k.ben)
        self.assertEqual(KB.KhoBiMatWindows._dich(ref), KB.NAMESPACE + ref)


# ================================================================== so ====

class TestSoProvider(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-pv-"))
        self.so = SO.SoProvider(root=self.tmp)

    def tearDown(self):
        self.so.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tu_choi_chuoi_giong_bi_mat(self):
        self.so.luu_provider(SO.Provider(provider_id="ali", preset="alibaba_dashscope",
                                         base_url="https://x.example/v1"))
        for xau in (KHOA, KHOA_TENCENT, "Bearer " + "q" * 30, "API_KEY=" + "z" * 20):
            with self.assertRaises(SO.LoiBiMatLotVao):
                self.so.luu_tai_khoan(SO.TaiKhoan(account_id="ali:a", provider_id="ali",
                                                  alias="a", credential_ref="ali.a.1234abcd",
                                                  meta={"ghi_chu": xau}))
            with self.assertRaises(SO.LoiBiMatLotVao):
                self.so.luu_provider(SO.Provider(provider_id="ali2", preset="openai_compatible",
                                                 base_url="https://x.example/v1", ten=xau))
        self.assertEqual(self.so.tai_khoan_tat_ca(), [])

    def test_ma_provider_va_alias_bi_kiem(self):
        with self.assertRaises(SO.LoiSoProvider):
            self.so.luu_provider(SO.Provider(provider_id="Ali Baba", preset="x"))
        self.so.luu_provider(SO.Provider(provider_id="ali", preset="x"))
        with self.assertRaises(SO.LoiSoProvider):
            self.so.luu_tai_khoan(SO.TaiKhoan(account_id="ali:x", provider_id="ali",
                                              alias="", credential_ref="ali.x.1234abcd"))

    def test_bytes_tep_db_khong_co_khoa(self):
        self.so.luu_provider(SO.Provider(provider_id="ali", preset="alibaba_dashscope",
                                         base_url="https://x.example/v1"))
        self.so.luu_tai_khoan(SO.TaiKhoan(account_id="ali:a", provider_id="ali", alias="a",
                                          credential_ref="ali.a.1234abcd"))
        self.so._c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for f in self.tmp.rglob("providers.db*"):
            _khong_co_khoa(self, f.read_bytes().decode("latin-1"), str(f))
        self.assertIn("ali.a.1234abcd", " ".join(self.so.moi_chuoi()))


# ============================================================= adapter ====

class TestAdapter(unittest.TestCase):

    def _ad(self, http, preset_ma="alibaba_dashscope", base_url="https://api.example/v1"):
        p = SO.Provider(provider_id="ali", preset=preset_ma, base_url=base_url)
        return AD.AdapterOpenAICompat(p, PS.preset(preset_ma), http=http)

    def _bm(self):
        k = KB.KhoBiMatBoNho()
        k.luu("ali.a.1234abcd", KHOA)
        return k.lay("ali.a.1234abcd")

    def test_thu_ket_noi_qua_models_chi_phi_toi_thieu(self):
        http = AD.HttpGia(_http_ok_models)
        kq = self._ad(http).thu_ket_noi(self._bm())
        self.assertTrue(kq.ok, kq.to_dict())
        self.assertEqual(kq.cach, "models")
        self.assertEqual(kq.models, ["qwen-plus", "qwen-turbo"])
        self.assertEqual(len(http.goi_lai), 1)
        self.assertEqual(http.goi_lai[0]["method"], "GET")
        self.assertTrue(http.goi_lai[0]["co_xac_thuc"])
        self.assertIsNone(http.goi_lai[0]["body"])
        _khong_co_khoa(self, json.dumps(kq.to_dict()) + json.dumps(http.goi_lai))

    def test_khong_co_models_thi_chat_toi_thieu(self):
        http = AD.HttpGia(_http_khong_models)
        kq = self._ad(http).thu_ket_noi(self._bm())
        self.assertTrue(kq.ok, kq.to_dict())
        self.assertEqual(kq.cach, "chat_toi_thieu")
        body = json.loads(http.goi_lai[1]["body"])
        self.assertEqual(body["max_tokens"], 1)
        self.assertEqual(body["model"], "qwen-plus")

    def test_loi_401_doi_khoa_bi_loc(self):
        kq = self._ad(AD.HttpGia(_http_401_doi_khoa)).thu_ket_noi(self._bm())
        self.assertFalse(kq.ok)
        self.assertEqual(kq.ma_http, 401)
        self.assertIn("401", kq.chi_tiet)
        self.assertIn("[DA-LOC]", kq.chi_tiet)
        _khong_co_khoa(self, kq.chi_tiet)

    def test_ngoai_le_mang_khong_lo_khoa(self):
        def _no(method, url, headers, body):
            raise OSError(f"connection refused while sending {headers['Authorization']}")
        kq = self._ad(AD.HttpGia(_no)).thu_ket_noi(self._bm())
        self.assertFalse(kq.ok)
        self.assertIn("OSError", kq.chi_tiet)
        _khong_co_khoa(self, kq.chi_tiet)

    def test_hoi_thu_tra_noi_dung_va_usage(self):
        kq = self._ad(AD.HttpGia(_http_ok_models)).hoi(self._bm(), model="qwen-plus", cau="hi")
        self.assertTrue(kq.ok)
        self.assertEqual(kq.noi_dung, "pong")
        self.assertEqual(kq.usage, {"total_tokens": 3})

    def test_preset_khai_bao_khong_duoc_coi_la_da_do(self):
        for p in PS.PRESETS.values():
            self.assertFalse(p.da_do, p.ma)
        self.assertNotEqual(PS.preset("alibaba_dashscope").base_url_mac_dinh,
                            PS.preset("tencent_hunyuan").base_url_mac_dinh)
        self.assertTrue(PS.preset("openai_compatible").yeu_cau_base_url)


# ================================================================== be ====

class TestBeTaiKhoan(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-pv-"))
        self.so = SO.SoProvider(root=self.tmp)
        self.so.luu_provider(SO.Provider(provider_id="ali", preset="alibaba_dashscope",
                                         base_url="https://x.example/v1"))
        for a in ("a", "b", "c"):
            self.so.luu_tai_khoan(SO.TaiKhoan(account_id=f"ali:{a}", provider_id="ali", alias=a,
                                              credential_ref=f"ali.{a}.1234abcd"))
        self.be = BeTaiKhoan(self.so, "ali")

    def tearDown(self):
        self.so.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chon_it_tai_nhat_va_failover(self):
        self.assertEqual(self.be.chon(now=0).alias, "a")
        self.be.bat_dau("ali:a")
        self.assertEqual(self.be.chon(now=0).alias, "b")
        self.assertEqual(self.be.chon(now=0, loai_tru=("ali:b",)).alias, "c")
        self.assertIsNone(self.be.chon(now=0, loai_tru=("ali:b", "ali:c")))
        self.assertIn("đầy chỗ x1", self.be.vi_sao_khong_ai(now=0, loai_tru=("ali:b", "ali:c")))

    def test_cooldown_co_bac_cung_hang_voi_V4(self):
        for _ in range(NGUONG_COOLDOWN):
            self.be.bat_dau("ali:a")
            t = self.be.ket_thuc("ali:a", ok=False, now=1000.0, chi_tiet="HTTP 500")
        self.assertEqual(t.trang_thai, "cooldown")
        self.assertAlmostEqual(t.cooldown_den, 1000.0 + BACKOFF_COOLDOWN[0])
        self.assertNotEqual(self.be.chon(now=1000.0).alias, "a")
        self.assertEqual(self.be.chon(now=1000.0 + BACKOFF_COOLDOWN[0] + 1,
                                      loai_tru=("ali:b", "ali:c")).alias, "a")
        self.be.bat_dau("ali:a")
        t = self.be.ket_thuc("ali:a", ok=True, now=2000.0)
        self.assertEqual((t.hong_lien_tiep, t.trang_thai), (0, "ok"))
        tt = self.be.tom_tat(now=2000.0)
        self.assertEqual((tt["dang_ky"], tt["khoe"], tt["ho_so_rieng"]), (3, 1, 3))


# ============================================================== dich vu ===

class TestDichVuProvider(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-pv-"))
        self.st = ControlStore(root=self.tmp)
        self.ky_uc = DichVuKyUc(self.st, self.tmp)          # cam nguoi ghi vao store
        self.st.luu_project(Project(project_id="p1", name="P1", repo_path=str(self.tmp)))
        self.kho = KB.KhoBiMatBoNho()
        self.dv = DichVuProvider(self.st, self.tmp, kho_bi_mat=self.kho,
                                 http=AD.HttpGia(_http_ok_models))
        self.dv.them_provider("ali", "alibaba_dashscope")

    def tearDown(self):
        self.dv.close()
        self.ky_uc.close()
        self.st.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _moi_noi(self) -> str:
        """Mọi nơi một khoá có thể lọt: providers.db, control.db, ký ức L0+blob."""
        phan = [" ".join(self.dv.so.moi_chuoi()), json.dumps(self.dv.trang_thai(), default=str)]
        for e in self.st.su_kien(limit=500):
            phan.append(json.dumps(e, default=str))
        p = self.ky_uc.provider("p1")
        for sk in p.su_kien(limit=500):
            phan.append(sk.tom_tat + json.dumps(sk.meta, default=str))
            if sk.blob_sha:
                phan.append(p.doc_blob(sk.blob_sha) or "")
        for k in p.liet_ke(limit=200):
            phan.append(k.noi_dung + k.tieu_de)
        return "\n".join(phan)

    def test_them_tai_khoan_chi_tra_ref_khong_tra_gia_tri(self):
        t = self.dv.them_tai_khoan("ali", "Prod", KHOA, project_id="p1")
        self.assertTrue(t["credential_ref"].startswith("ali.prod."))
        self.assertNotIn("gia_tri", t)
        _khong_co_khoa(self, json.dumps(t))
        self.assertTrue(self.kho.co(t["credential_ref"]))
        _khong_co_khoa(self, self._moi_noi(), "khoá lọt vào một sổ")
        self.assertTrue(any(e["kind"] == "PROVIDER_ACCOUNT_ADDED"
                            for e in self.st.su_kien(project_id="p1", limit=50)))

    def test_thu_ket_noi_that_bai_doi_khoa_khong_lot_vao_ky_uc(self):
        self.dv.http = AD.HttpGia(_http_401_doi_khoa)
        t = self.dv.them_tai_khoan("ali", "Prod", KHOA, project_id="p1")
        kq = self.dv.thu_ket_noi(t["account_id"], project_id="p1")
        self.assertFalse(kq["ket_qua"]["ok"])
        self.assertEqual(kq["tai_khoan"]["trang_thai"], "hong")
        self.assertIn("401", kq["tai_khoan"]["lan_thu_chi_tiet"])
        van = self._moi_noi()
        _khong_co_khoa(self, van, "khoá dội lại từ 401 lọt vào sổ/ký ức")
        # Nhung SU THAT "tai khoan hong luc nao" thi CO trong ky uc: L0 (su
        # kien) VA L1 (INCIDENT co bang chung) — chi khong co khoa.
        p = self.ky_uc.provider("p1")
        l0 = [sk for sk in p.su_kien(limit=200) if sk.loai == "event:PROVIDER_TEST_FAILED"]
        self.assertEqual(len(l0), 1)
        self.assertIn("401", l0[0].tom_tat)
        inc = [k for k in p.liet_ke(limit=50) if k.loai.value == "incident"]
        self.assertTrue(inc)
        self.assertIn("PROVIDER_TEST_FAILED", inc[0].noi_dung)
        self.assertIn("ali/Prod", inc[0].noi_dung)
        self.assertEqual(inc[0].bang_chung[0].su_kien_id, l0[0].id)

    def test_thu_ket_noi_thanh_cong_nap_model_probed(self):
        t = self.dv.them_tai_khoan("ali", "Prod", KHOA)
        kq = self.dv.thu_ket_noi(t["account_id"])
        self.assertTrue(kq["ket_qua"]["ok"])
        ms = self.dv.so.models_cua("ali")
        self.assertEqual({m.model_id for m in ms if m.nguon == "probed"}, {"qwen-plus", "qwen-turbo"})
        self.assertTrue(any(m.nguon == "preset" for m in ms))
        self.assertEqual(kq["tai_khoan"]["trang_thai"], "ok")

    def test_hoi_thu_la_duong_thu_cong_co_su_kien(self):
        t = self.dv.them_tai_khoan("ali", "Prod", KHOA, project_id="p1")
        kq = self.dv.hoi_thu(t["account_id"], model="qwen-plus", cau="ping", project_id="p1")
        self.assertTrue(kq["ok"])
        self.assertEqual(kq["noi_dung"], "pong")
        self.assertTrue(any(e["kind"] == "PROVIDER_MANUAL_CALL"
                            for e in self.st.su_kien(project_id="p1", limit=50)))
        _khong_co_khoa(self, self._moi_noi())

    def test_kho_khong_san_thi_khong_them_duoc_va_khong_roi_ve_tep(self):
        dv = DichVuProvider(self.st, self.tmp, kho_bi_mat=KB.KhoBiMatTrong("CI"),
                            so=self.dv.so)
        with self.assertRaises(KB.KhoBiMatKhongSan):
            dv.them_tai_khoan("ali", "x", KHOA)
        self.assertEqual(self.dv.so.tai_khoan_tat_ca(), [])
        for f in self.tmp.rglob("*"):
            if f.is_file() and f.suffix in (".json", ".env", ".txt", ".ini", ".cfg"):
                _khong_co_khoa(self, f.read_text(encoding="utf-8", errors="replace"), str(f))

    def test_xoa_can_xac_nhan_va_xoa_ca_credential(self):
        t = self.dv.them_tai_khoan("ali", "Prod", KHOA)
        with self.assertRaises(LoiDichVuProvider):
            self.dv.xoa_tai_khoan(t["account_id"])
        kq = self.dv.xoa_tai_khoan(t["account_id"], xac_nhan=True)
        self.assertTrue(kq["credential_da_xoa"])
        self.assertFalse(self.kho.co(t["credential_ref"]))
        with self.assertRaises(LoiDichVuProvider):
            self.dv.xoa_provider("ali")
        self.dv.xoa_provider("ali", xac_nhan=True)
        self.assertEqual(self.dv.so.providers(), [])

    def test_base_url_bi_kiem(self):
        for u in ("http://api.example/v1", "https://u:p@api.example/v1", "ftp://x", "https://x/?a=1"):
            with self.assertRaises(LoiDichVuProvider):
                self.dv.them_provider("k2", "openai_compatible", base_url=u)
        with self.assertRaises(LoiDichVuProvider):
            self.dv.them_provider("k3", "openai_compatible")          # can base_url
        self.dv.them_provider("k4", "openai_compatible", base_url="http://127.0.0.1:9/v1/")
        self.assertEqual(self.dv.so.provider("k4").base_url, "http://127.0.0.1:9/v1")

    def test_dang_ky_vao_fabric_khong_nhan_dispatch(self):
        from scripts.router_v4 import fabric_config as FC
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import TaskContract
        from scripts.router_v4.scheduler import Scheduler
        self.assertFalse(AUTO_ROUTING)
        t = self.dv.them_tai_khoan("ali", "Prod", KHOA)
        self.dv.thu_ket_noi(t["account_id"])
        with mock.patch("scripts.router_v4.antigravity_launcher.profile_ton_tai", lambda a: True):
            f = FC.dung_fabric(FC.doc_cau_hinh(root=ROOT))
        kq = self.dv.dang_ky_vao_fabric(f)
        self.assertEqual(kq["loi"], "", kq)
        self.assertEqual(kq["runtimes"], ["EXT_ALI_PROD"])
        r = f.runtime("EXT_ALI_PROD")
        self.assertFalse(r.dispatchable)
        self.assertEqual(r.auth_profile, f"credential-ref:{t['credential_ref']}")
        self.assertIn("ali/qwen-plus", f.models)
        f.validate()
        c = TaskContract(task_id="x", objective="o",
                         requirements=Requirements(coding=True, repo_read=True, pin_provider="ali"))
        c.validate()
        d = Scheduler(f).decide(c, now=time.time())
        self.assertIsNone(d.selected)
        self.assertIn("KHÔNG nhận dispatch", d.reason)
        # Idempotent: dang ky lai khong nhan doi.
        kq2 = self.dv.dang_ky_vao_fabric(f)
        self.assertEqual((kq2["runtimes"], kq2["models"], kq2["loi"]), ([], [], ""))
        _khong_co_khoa(self, json.dumps([x.to_dict() for x in f.runtimes.values()], default=str))
        # Xoa tai khoan -> runtime EXT bi go khoi fabric; khe AG khong bi cham.
        so_ag = sum(1 for r in f.runtimes.values() if r.provider == "antigravity")
        self.dv.xoa_tai_khoan(t["account_id"], xac_nhan=True)
        kq3 = self.dv.dang_ky_vao_fabric(f)
        self.assertIn("EXT_ALI_PROD", kq3["da_go"])
        self.assertNotIn("EXT_ALI_PROD", f.runtimes)
        self.assertEqual(sum(1 for r in f.runtimes.values() if r.provider == "antigravity"), so_ag)
        f.validate()
        # Xoa provider -> model EXT cung bi go.
        self.dv.xoa_provider("ali", xac_nhan=True)
        kq4 = self.dv.dang_ky_vao_fabric(f)
        self.assertIn("ali/qwen-plus", kq4["da_go"])
        self.assertNotIn("ali/qwen-plus", f.models)
        f.validate()

    def test_sau_khi_doi_duoc_goi_de_dong_bo_fabric_song(self):
        """Lỗi thật ở nghiệm thu EXE: fabric dựng TRƯỚC (Leader mở phiên), provider
        thêm SAU → không có runtime EXT tới khi khởi động lại. Nay mọi thay đổi sổ
        gọi `sau_khi_doi`, engine đồng bộ vào fabric đang sống."""
        goi = []
        dv = DichVuProvider(self.st, self.tmp, kho_bi_mat=self.kho, so=self.dv.so,
                            http=AD.HttpGia(_http_ok_models), sau_khi_doi=lambda: goi.append(1))
        t = dv.them_tai_khoan("ali", "Prod", KHOA)
        dv.thu_ket_noi(t["account_id"])
        dv.bat_tat_tai_khoan(t["account_id"], False)
        dv.xoa_tai_khoan(t["account_id"], xac_nhan=True)
        dv.them_provider("k9", "openai_compatible", base_url="https://k9.example/v1")
        dv.xoa_provider("k9", xac_nhan=True)
        self.assertEqual(len(goi), 6)
        # Callback nem khong lam hong nghiep vu.
        dv.sau_khi_doi = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        self.assertTrue(dv.them_tai_khoan("ali", "Prod2", KHOA)["credential_ref"])


# ===================================================== ranh gioi ky uc (F) ==

class TestRanhGioiKyUcCredential(unittest.TestCase):

    def test_bo_loc_ky_uc_bat_khoa_provider_va_cookie(self):
        # Cookie de CUOI: mau `Cookie:` nuot het phan con lai cua dong (dung —
        # mot header cookie la mot khoi), nen dat truoc se che cac mau sau.
        van = (f"AG03 failed authentication at 10:32 with key {KHOA} and SecretId {KHOA_TENCENT}; "
               f"x-api-key: zzzzzzzzzzzz9999; "
               f"jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwx\n"
               f"Cookie: session=abcdefghijklmnop1234; theme=dark")
        ra, n = BM.loc(van)
        self.assertGreaterEqual(n, 5, ra)
        _khong_co_khoa(self, ra)
        self.assertNotIn("abcdefghijklmnop1234", ra)
        self.assertNotIn("zzzzzzzzzzzz9999", ra)
        self.assertNotIn("eyJzdWIiOiIxMjM0NTY3ODkwIn0", ra)
        # Su that van con: ai, luc nao.
        self.assertIn("AG03 failed authentication at 10:32", ra)

    def test_ky_uc_giu_su_that_khong_giu_bi_mat(self):
        tmp = Path(tempfile.mkdtemp(prefix="cc-pv-"))
        try:
            st = ControlStore(root=tmp)
            dv = DichVuKyUc(st, tmp)
            st.luu_project(Project(project_id="p1", name="P1", repo_path=str(tmp)))
            # Nguoi dung ke lai su co, dan ca khoa vao chat.
            st.them_chat("p1", "user", f"AG03 failed authentication at 10:32, key was {KHOA} "
                                       f"— ghi nhớ đây là một sự cố của project: AG03 hỏng xác "
                                       f"thực lúc 10:32.")
            p = dv.provider("p1")
            for sk in p.su_kien(limit=50):
                _khong_co_khoa(self, sk.tom_tat + json.dumps(sk.meta, default=str))
                if sk.blob_sha:
                    _khong_co_khoa(self, p.doc_blob(sk.blob_sha) or "")
            inc = p.liet_ke(limit=20)
            self.assertTrue(inc, "sự cố phải được ghi nhớ")
            for k in inc:
                _khong_co_khoa(self, k.noi_dung + k.tieu_de)
                self.assertIn("AG03", k.noi_dung)
            self.assertTrue(p.tim("AG03 hỏng xác thực"))
            self.assertFalse(p.tim_su_kien(KHOA))
            dv.close(); st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
