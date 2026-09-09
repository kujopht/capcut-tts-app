"""Bậc cao cấp (GPT-6 Astra) và rào chống dùng nhầm.

YÊU CẦU VẬN HÀNH, chép nguyên ý: Astra **không bao giờ** được lặng lẽ trở
thành worker mặc định chỉ vì Codex đang đánh dấu nó là mặc định.

Hai rào ĐỘC LẬP, và tệp này kiểm cả hai:

    1. `CodexAdapter` FAIL CLOSED khi chưa ghim model — không rơi về mặc
       định của nhà cung cấp. Rào này chặn cả model cao cấp chưa ai đặt tên.
    2. `premium.GacAstra` — bậc 3 chỉ vào được bằng lý do tường minh.

Bối cảnh đo được (2026-09-09, `codex doctor`, codex-cli 0.153.4): mặc định
trên máy này là `gpt-5.6-sol`, và cùng bản CLI đó phơi ra `gpt-6-astra`.
Nên rào (1) không phải phòng xa — nó chặn một đường đang mở.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.router_v4.premium import (                      # noqa: E402
    BAC_CAO_CAP, CHE_DO_MAC_DINH, MODEL_ASTRA, CheDo, GacAstra, LyDoLeoThang,
    bac_cua, loc_ung_vien)


class TestMacDinh(unittest.TestCase):
    def test_mac_dinh_la_AUTO(self):
        self.assertIs(CHE_DO_MAC_DINH, CheDo.AUTO)

    def test_nhan_dien_astra_theo_ca_TEN_lan_BAC(self):
        self.assertTrue(GacAstra.la_astra(MODEL_ASTRA))
        self.assertTrue(GacAstra.la_astra("GPT-6-ASTRA"))
        # Mot model cao cap MOI, ten khac, van phai bi chan.
        self.assertTrue(GacAstra.la_astra("model-nao-do", premium_tier=3))
        self.assertFalse(GacAstra.la_astra("gpt-5.6-sol"))
        self.assertFalse(GacAstra.la_astra("gemini-3.8-flash-high",
                                           premium_tier=1))

    def test_bac_cua(self):
        self.assertEqual(bac_cua(MODEL_ASTRA), BAC_CAO_CAP)
        self.assertEqual(bac_cua("x", premium_tier=2), 2)


class TestGacAstra(unittest.TestCase):
    def setUp(self):
        self.g = GacAstra()

    def _xin(self, **kw):
        kw.setdefault("task_id", "t1")
        kw.setdefault("che_do", CheDo.AUTO)
        return self.g.xin_phep(**kw)

    # -- tu choi ------------------------------------------------------------

    def test_khong_co_ly_do_thi_TU_CHOI(self):
        ok, vi_sao = self._xin()
        self.assertFalse(ok)
        self.assertIn("mặc định", vi_sao)

    def test_ECO_cam_tuyet_doi_ke_ca_khi_co_ly_do(self):
        ok, vi_sao = self._xin(che_do=CheDo.ECO,
                               ly_do=LyDoLeoThang.NGUOI_YEU_CAU)
        self.assertFalse(ok)
        self.assertIn("ECO", vi_sao)

    def test_ECO_cam_ca_che_do_MAX_cua_nguoi_khac(self):
        ok, _ = self._xin(che_do=CheDo.ECO)
        self.assertFalse(ok)

    def test_viec_TAM_THUONG_bi_tu_choi_du_co_ly_do(self):
        for lv in ("grep", "docs", "formatting", "dependency_update",
                   "git_ops", "summary", "tests"):
            with self.subTest(loai=lv):
                ok, vi_sao = self._xin(ly_do=LyDoLeoThang.NGUOI_YEU_CAU,
                                       loai_viec=lv)
                self.assertFalse(ok, f"{lv} lẽ ra phải bị từ chối")
                self.assertIn("việc thường", vi_sao)

    def test_viec_tam_thuong_bi_tu_choi_ca_o_che_do_MAX(self):
        ok, _ = self._xin(che_do=CheDo.MAX, loai_viec="grep")
        self.assertFalse(ok)

    def test_astra_KHONG_duoc_sinh_ra_astra(self):
        ok, vi_sao = self._xin(che_do=CheDo.MAX, tu_astra=True)
        self.assertFalse(ok)
        self.assertIn("đệ quy", vi_sao)

    def test_tran_song_song_la_MOT(self):
        self.g.mo(session_id="s1", task_id="t1", che_do=CheDo.MAX,
                  ly_do=None, escalated_from="T2")
        self.assertEqual(self.g.dang_chay, 1)
        ok, vi_sao = self._xin(task_id="t2", che_do=CheDo.MAX)
        self.assertFalse(ok)
        self.assertIn("đang chạy", vi_sao)
        self.g.dong("s1")
        ok, _ = self._xin(task_id="t2", che_do=CheDo.MAX)
        self.assertTrue(ok)

    def test_tran_moi_viec(self):
        self.g.mo(session_id="s1", task_id="t1", che_do=CheDo.MAX,
                  ly_do=None, escalated_from="T2")
        self.g.dong("s1")
        ok, vi_sao = self._xin(task_id="t1", che_do=CheDo.MAX)
        self.assertFalse(ok)
        self.assertIn("t1", vi_sao)

    def test_het_ngan_sach_thi_FAIL_CLOSED_chu_khong_ha_cap(self):
        g = GacAstra(ngan_sach=1)
        g.mo(session_id="s1", task_id="t1", che_do=CheDo.MAX, ly_do=None,
             escalated_from="T2")
        g.dong("s1")
        ok, vi_sao = g.xin_phep(task_id="t2", che_do=CheDo.MAX)
        self.assertFalse(ok)
        self.assertIn("cạn", vi_sao)

    def test_mo_khi_khong_duoc_phep_thi_NEM_chu_khong_lang_le(self):
        with self.assertRaises(PermissionError):
            self.g.mo(session_id="s", task_id="t", che_do=CheDo.ECO,
                      ly_do=LyDoLeoThang.NGUOI_YEU_CAU, escalated_from="T2")

    # -- cho phep -----------------------------------------------------------

    def test_AUTO_co_ly_do_leo_thang_thi_duoc(self):
        ok, vi_sao = self._xin(ly_do=LyDoLeoThang.LOI_DONG_THOI_KHO)
        self.assertTrue(ok)
        self.assertIn("leo thang", vi_sao)

    def test_MAX_duoc_ngay_khong_can_ly_do(self):
        ok, vi_sao = self._xin(che_do=CheDo.MAX)
        self.assertTrue(ok)
        self.assertIn("MAX", vi_sao)

    def test_moi_lan_dung_deu_duoc_GHI_du_truong(self):
        bg = self.g.mo(session_id="s1", task_id="t9", che_do=CheDo.AUTO,
                       ly_do=LyDoLeoThang.TRONG_TAI_CUOI,
                       escalated_from="CODEX01/codex-default")
        d = bg.to_dict()
        for k in ("task_id", "provider", "model", "reason", "escalated_from",
                  "timestamp", "turns"):
            self.assertIn(k, d)
        self.assertEqual(d["model"], MODEL_ASTRA)
        self.assertEqual(d["escalated_from"], "CODEX01/codex-default")
        self.assertIsNone(d["turns"], "không đo được thì phải là None, KHÔNG "
                                      "phải 0")
        self.assertEqual(len(self.g.nhat_ky), 1)


class TestLocUngVien(unittest.TestCase):
    class _M:
        def __init__(self, mid, tier=0):
            self.model_id, self.premium_tier = mid, tier

    def test_mac_dinh_bo_model_cao_cap_ra_khoi_ung_vien(self):
        ds = [self._M("gemini-3.8-flash-high"), self._M(MODEL_ASTRA, 3),
              self._M("codex-default", 2)]
        ra = [m.model_id for m in loc_ung_vien(ds, che_do=CheDo.AUTO)]
        self.assertNotIn(MODEL_ASTRA, ra)
        self.assertIn("codex-default", ra)

    def test_duoc_phep_thi_giu_lai(self):
        ds = [self._M(MODEL_ASTRA, 3)]
        ra = loc_ung_vien(ds, che_do=CheDo.MAX, duoc_astra=True)
        self.assertEqual(len(ra), 1)

    def test_ECO_bo_ca_khi_duoc_phep(self):
        ds = [self._M(MODEL_ASTRA, 3)]
        self.assertEqual(loc_ung_vien(ds, che_do=CheDo.ECO, duoc_astra=True),
                         [])


class TestCodexKhongDungMacDinhNhaCungCap(unittest.TestCase):
    """Rào (1) — rào quan trọng hơn, vì nó chặn cả cái chưa có tên."""

    def _packet(self):
        from scripts.router_v3.packet import TaskPacket
        return TaskPacket(task_id="t1", base_sha="x",
                          objective="đọc một tệp", workspace="")

    def test_chua_ghim_model_thi_KHONG_CHAY(self):
        from scripts.router_v3.pool.adapters import CodexAdapter
        a = CodexAdapter("CODEX01")            # khong truyen `model`
        kq = a.send_task(self._packet())
        self.assertEqual(kq.status, "failed")
        self.assertEqual(kq.failure_reason, "no_model_pinned")
        self.assertIn("ghim model", kq.summary)

    def test_lenh_codex_LUON_co_co_m(self):
        """Đọc mã: `-m` phải nằm trong argv, không phải 'thường là có'."""
        import ast
        src = (GOC / "scripts/router_v3/pool/adapters.py").read_text(
            encoding="utf-8")
        cay = ast.parse(src)
        lop = next(n for n in ast.walk(cay)
                   if isinstance(n, ast.ClassDef) and n.name == "CodexAdapter")
        ham = next(n for n in ast.walk(lop)
                   if isinstance(n, ast.FunctionDef) and n.name == "send_task")
        chuoi = [n.value for n in ast.walk(ham)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertIn("-m", chuoi,
                      "`codex exec` thiếu `-m` sẽ chạy model MẶC ĐỊNH của "
                      "CLI — đúng thứ không được phép xảy ra")

    def test_fabric_ghim_model_that_cho_codex(self):
        from scripts.router_v4.fabric_config import nap
        f, _, _ = nap(probe=False)
        m = f.model("codex-default")
        self.assertTrue(m.ten_gui_nha_cung_cap,
                        "model Codex phải ghim `provider_model`")
        self.assertNotEqual(m.ten_gui_nha_cung_cap.lower(), MODEL_ASTRA,
                            "model mặc định của Codex KHÔNG được là Astra")

    def test_astra_co_mat_nhung_CHUA_BAT(self):
        """'Đã chuẩn bị' chứ chưa 'đã bật': không runtime nào đỡ nó."""
        from scripts.router_v4.fabric_config import nap
        f, _, _ = nap(probe=False)
        m = f.model(MODEL_ASTRA)
        self.assertEqual(m.premium_tier, BAC_CAO_CAP)
        do = [r.runtime_id for r in f.runtimes.values()
              if MODEL_ASTRA in (r.supported_models or ())]
        self.assertEqual(do, [], f"Astra đã được bật ở {do} — bộ lập lịch "
                                 f"có thể chọn nó; đó là một quyết định "
                                 f"phải cố ý, không phải vô tình")


class TestBoLapLichLoaiBacCaoCap(unittest.TestCase):
    """Rào THẬT trong bộ lập lịch — không phải một lời hứa trong ghi chú.

    Kịch bản người review dựng ra, và nó đúng: nếu rào duy nhất là "Astra
    vắng mặt trong `supported_models`", thì một người làm ĐÚNG theo hướng
    dẫn ("bật = thêm nó vào `supported_models`") sẽ mở thẳng cửa — Astra
    có `benchmark_profile` 0.9 so với 0.82 của `codex-default`, và
    `expected_cost` nhẹ hơn `benchmark_quality` + `capability_match` cộng
    lại, nên nó THẮNG ĐIỂM một việc `grep` và chạy thật.
    """

    def _fabric_co_astra(self):
        """Fabric có Astra ĐÃ ĐƯỢC BẬT trong `supported_models`."""
        from scripts.router_v4.fabric_config import nap
        f, _, _ = nap(probe=False)
        r = f.runtimes["CODEX01"]
        r.supported_models = tuple(list(r.supported_models) + [MODEL_ASTRA])
        r.needs_provisioning = ""
        r.status = type(r.status).IDLE
        return f

    def _hop_dong(self, **kw):
        from scripts.router_v4.contract import TaskContract
        return TaskContract(task_id="t1", objective="tìm chuỗi trong kho",
                            **kw)

    def test_da_BAT_trong_supported_models_van_KHONG_duoc_chon_tu_dong(self):
        from scripts.router_v4.scheduler import Scheduler
        f = self._fabric_co_astra()
        cho = [p for p in f.placements() if p.model_id == MODEL_ASTRA]
        self.assertTrue(cho, "phải có placement để bài kiểm nói lên điều gì")
        s = Scheduler(f)
        c = self._hop_dong()
        for p in cho:
            ly_do = s._loai_vi(p, c, exclude=set(), now=None)
            self.assertIsNotNone(
                ly_do, f"{p.key} lọt qua phép loại — Astra chọn được TỰ ĐỘNG")
            self.assertIn("CAO CẤP", ly_do)

    def test_ghim_dich_danh_thi_di_qua_duoc(self):
        """Chứng cứ chống rỗng: rào không được chặn cả đường tường minh."""
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.scheduler import Scheduler
        f = self._fabric_co_astra()
        cho = [p for p in f.placements() if p.model_id == MODEL_ASTRA]
        s = Scheduler(f)
        c = self._hop_dong(requirements=Requirements(pin_model=MODEL_ASTRA))
        ly_do = [s._loai_vi(p, c, exclude=set(), now=None) for p in cho]
        self.assertTrue(
            any(l is None or "CAO CẤP" not in l for l in ly_do),
            f"ghim đích danh vẫn bị chặn vì lý do bậc: {ly_do}")

    def test_model_thuong_khong_bi_rao_nay_cham_toi(self):
        from scripts.router_v4.scheduler import Scheduler
        f = self._fabric_co_astra()
        s = Scheduler(f)
        c = self._hop_dong()
        for p in f.placements():
            if p.model_id == MODEL_ASTRA:
                continue
            ly_do = s._loai_vi(p, c, exclude=set(), now=None) or ""
            self.assertNotIn("CAO CẤP", ly_do,
                             f"{p.key} bị chặn nhầm bởi rào bậc cao cấp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
