"""Bể worker ấm + cầu nối AG02 — Router V3.2.

Không bài nào gọi `agy` thật: worker ấm được kiểm qua chính sách tái tạo và
máy trạng thái, còn cầu nối chạy thật trên 127.0.0.1 với một hàm chạy giả.

Điều đáng kiểm nhất ở cầu nối không phải "gửi việc có chạy không" mà là những
gì nó TỪ CHỐI: token sai, cổng ra mạng ngoài, bản tin khổng lồ, và — quan
trọng nhất — giao thức không có chỗ nào chứa credential của nhà cung cấp.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.bridge import (LOOPBACK, MAX_MESSAGE_BYTES, BridgeClient,
                                      BridgeConfig, WorkerBridge)
from scripts.router_v3.warm_pool import (RecyclePolicy, SessionStats,
                                         WarmAgyWorker, WarmPool, WarmState)


class ChinhSachTaiTaoTest(unittest.TestCase):
    """Tiến trình ấm ≠ hội thoại vô hạn."""

    def setUp(self):
        self.p = RecyclePolicy(max_turns=5, max_chars=1000,
                               max_age_seconds=60, max_failures=2)

    def test_phien_moi_thi_khong_tai_tao(self):
        self.assertIsNone(self.p.should_recycle(SessionStats(), "toan"))

    def test_doi_HO_VIEC_thi_tai_tao(self):
        """Kéo lê ngữ cảnh của một việc không liên quan vừa tốn token vừa
        làm nhiễu lượt sau."""
        s = SessionStats(turns=2, family="scraper")
        ly_do = self.p.should_recycle(s, "frontend")
        self.assertIsNotNone(ly_do)
        self.assertIn("họ việc", ly_do)

    def test_CUNG_ho_viec_thi_giu_am(self):
        """Đọc module rồi sửa chính module đó — ngữ cảnh cũ là TÀI SẢN."""
        s = SessionStats(turns=3, family="scraper")
        self.assertIsNone(self.p.should_recycle(s, "scraper"))

    def test_qua_nhieu_luot_thi_tai_tao(self):
        ly_do = self.p.should_recycle(SessionStats(turns=5, family="a"), "a")
        self.assertIn("lượt", ly_do)

    def test_ngu_canh_qua_lon_thi_tai_tao(self):
        ly_do = self.p.should_recycle(
            SessionStats(turns=1, chars=2000, family="a"), "a")
        self.assertIn("ký tự", ly_do)

    def test_hong_lien_tiep_thi_tai_tao(self):
        ly_do = self.p.should_recycle(
            SessionStats(turns=1, failures=2, family="a"), "a")
        self.assertIn("hỏng", ly_do)

    def test_phien_gia_thi_tai_tao(self):
        s = SessionStats(turns=1, family="a")
        s.started_at = time.perf_counter() - 120
        self.assertIn("già", self.p.should_recycle(s, "a"))

    def test_ho_viec_rong_khong_ep_tai_tao(self):
        """Không khai họ việc thì không suy đoán — chỉ các ngưỡng khác quyết định."""
        self.assertIsNone(self.p.should_recycle(
            SessionStats(turns=1, family="a"), ""))


class BeWorkerTest(unittest.TestCase):
    def _w(self, wid, state, family="", turns=0):
        w = WarmAgyWorker(wid, model="m")
        w._state = state
        w.stats = SessionStats(turns=turns, family=family)
        return w

    def test_uu_tien_worker_AM_cung_ho_viec(self):
        lanh = self._w("A", WarmState.COLD)
        am_khac = self._w("B", WarmState.WARM_IDLE, family="khac", turns=2)
        am_dung = self._w("C", WarmState.WARM_IDLE, family="toan", turns=2)
        p = WarmPool([lanh, am_khac, am_dung])
        self.assertEqual(p.pick(family="toan").worker_id, "C")

    def test_am_sai_ho_viec_van_hon_worker_lanh(self):
        """Tái tạo tốn ~4s; sinh lạnh cũng vậy — nhưng worker ấm đã sẵn sàng."""
        lanh = self._w("A", WarmState.COLD)
        am = self._w("B", WarmState.WARM_IDLE, family="khac", turns=2)
        self.assertEqual(WarmPool([lanh, am]).pick(family="toan").worker_id, "B")

    def test_worker_BAN_khong_duoc_chon(self):
        ban = self._w("A", WarmState.WARM_BUSY)
        self.assertIsNone(WarmPool([ban]).pick())

    def test_worker_HONG_khong_duoc_chon(self):
        self.assertIsNone(WarmPool([self._w("A", WarmState.FAILED)]).pick())

    def test_snapshot_khong_chua_noi_dung_viec(self):
        w = self._w("A", WarmState.WARM_IDLE, family="toan", turns=3)
        for hang in WarmPool([w]).snapshot():
            self.assertNotIn("prompt", hang)
            self.assertNotIn("response", hang)


class ArgvKhoiDongTest(unittest.TestCase):
    """`start()` phải dựng đúng cờ — bằng chứng thật (2026-08-30): một mô
    hình chọn công cụ lệnh-shell để tạo MỘT tệp, và `accept-edits` không phủ
    trường hợp đó (chỉ ghi tệp), chỉ `--dangerously-skip-permissions` mới."""

    def _argv_da_dung(self, **kw) -> list:
        w = WarmAgyWorker("X", model="m", binary="agy.exe", **kw)
        with mock.patch("scripts.router_v3.warm_pool.subprocess.Popen") as gia:
            gia.return_value.stdout = None
            gia.return_value.stderr = None
            w.start()
        return gia.call_args[0][0]

    def test_mac_dinh_khong_co_co_nao(self):
        argv = self._argv_da_dung()
        self.assertNotIn("--mode", argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_allow_edits_them_mode_accept_edits(self):
        argv = self._argv_da_dung(allow_edits=True)
        self.assertIn("--mode", argv)
        self.assertEqual(argv[argv.index("--mode") + 1], "accept-edits")

    def test_dangerously_skip_permissions_them_dung_co(self):
        argv = self._argv_da_dung(dangerously_skip_permissions=True)
        self.assertIn("--dangerously-skip-permissions", argv)

    def test_ca_hai_dat_duoc_cung_luc(self):
        argv = self._argv_da_dung(allow_edits=True,
                                  dangerously_skip_permissions=True)
        self.assertIn("--mode", argv)
        self.assertIn("--dangerously-skip-permissions", argv)


class _CauNoiThu(unittest.TestCase):
    def setUp(self):
        self.goi = []

        def chay(prompt, family):
            self.goi.append((prompt, family))
            return {"response": f"da xu ly: {prompt[:20]}", "ok": True}

        self.bridge = WorkerBridge(BridgeConfig(worker_id="AG02"), chay)
        self.bridge.start()
        self.client = BridgeClient(self.bridge.port, self.bridge.token,
                                   timeout=10)

    def tearDown(self):
        self.bridge.stop()


class CauNoiTest(_CauNoiThu):
    def test_health_tra_ve_danh_tinh_worker(self):
        r = self.client.health()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["worker_id"], "AG02")
        self.assertTrue(r["healthy"])

    def test_gui_viec_va_nhan_ket_qua(self):
        r = self.client.run("lam viec X", family="toan")
        self.assertEqual(r["status"], "ok")
        self.assertIn("da xu ly", r["response"])
        self.assertEqual(self.goi[0], ("lam viec X", "toan"))

    def test_token_SAI_bi_tu_choi(self):
        xau = BridgeClient(self.bridge.port, "token-bia-dat", timeout=10)
        r = xau.run("lam viec X")
        self.assertEqual(r["status"], "error")
        self.assertIn("token", r["error"])
        self.assertEqual(self.goi, [], "việc KHÔNG được chạy khi token sai")

    def test_token_RONG_bi_tu_choi(self):
        r = BridgeClient(self.bridge.port, "", timeout=10).run("x")
        self.assertEqual(r["status"], "error")

    def test_op_la_bi_tu_choi(self):
        s = socket.create_connection((LOOPBACK, self.bridge.port), timeout=10)
        s.sendall((json.dumps({"op": "xoa_het", "token": self.bridge.token})
                   + "\n").encode())
        d = json.loads(s.recv(4096).decode())
        s.close()
        self.assertEqual(d["status"], "error")

    def test_thieu_prompt_bi_tu_choi(self):
        s = socket.create_connection((LOOPBACK, self.bridge.port), timeout=10)
        s.sendall((json.dumps({"op": "run", "token": self.bridge.token})
                   + "\n").encode())
        d = json.loads(s.recv(4096).decode())
        s.close()
        self.assertEqual(d["status"], "error")
        self.assertEqual(self.goi, [])

    def test_ham_chay_NEM_LOI_khong_lam_sap_cau_noi(self):
        def no(prompt, family):
            raise RuntimeError("worker chet")

        b = WorkerBridge(BridgeConfig(worker_id="AG0X"), no)
        b.start()
        try:
            c = BridgeClient(b.port, b.token, timeout=10)
            r = c.run("x")
            self.assertEqual(r["status"], "error")
            self.assertIn("RuntimeError", r["error"])
            # Cau noi VAN song sau mot lan hong.
            self.assertEqual(c.health()["status"], "ok")
        finally:
            b.stop()


class CauNoiCoStateFnTest(unittest.TestCase):
    """`state_fn` cho Router phân biệt KHOẺ-BẬN với KHOẺ-RẢNH, không chỉ true/false."""

    def setUp(self):
        self.trang_thai = "warm_idle"
        self.bridge = WorkerBridge(
            BridgeConfig(worker_id="AG02"), lambda p, f: {"ok": True},
            health_fn=lambda: self.trang_thai != "failed",
            state_fn=lambda: self.trang_thai)
        self.bridge.start()
        self.client = BridgeClient(self.bridge.port, self.bridge.token, timeout=10)

    def tearDown(self):
        self.bridge.stop()

    def test_health_kem_state_khi_co_state_fn(self):
        r = self.client.health()
        self.assertEqual(r["state"], "warm_idle")
        self.assertTrue(r["healthy"])

    def test_state_doi_theo_thoi_gian_thuc(self):
        self.trang_thai = "warm_busy"
        self.assertEqual(self.client.health()["state"], "warm_busy")

    def test_khong_co_state_fn_thi_khong_co_khoa_state(self):
        b = WorkerBridge(BridgeConfig(worker_id="AG01"), lambda p, f: {"ok": True})
        b.start()
        try:
            r = BridgeClient(b.port, b.token, timeout=10).health()
            self.assertNotIn("state", r)
        finally:
            b.stop()


class RanhGioiBaoMatTest(_CauNoiThu):
    """Những gì cầu nối KHÔNG được làm."""

    def test_CHI_nghe_tren_loopback(self):
        """Bind 0.0.0.0 sẽ mở cầu nối ra cả mạng LAN."""
        self.assertEqual(self.bridge._srv.server_address[0], LOOPBACK)

    def test_token_du_dai_va_ngau_nhien(self):
        a = WorkerBridge(BridgeConfig(), lambda p, f: {})
        b = WorkerBridge(BridgeConfig(), lambda p, f: {})
        try:
            self.assertGreaterEqual(len(a.token), 32)
            self.assertNotEqual(a.token, b.token)
        finally:
            a.stop()
            b.stop()

    def test_giao_thuc_KHONG_co_cho_cho_credential(self):
        """Bản tin chỉ mang việc và kết quả — không có trường nào để nhét
        OAuth token, cookie hay mật khẩu."""
        r = self.client.run("x", family="y")
        for cam in ("oauth", "refresh_token", "cookie", "password",
                    "credential", "keyring"):
            self.assertNotIn(cam, json.dumps(r).lower())

    def test_ban_tin_khong_lo_bi_tu_choi(self):
        """Không có trần thì một client hỏng ép cầu nối cấp phát vô hạn."""
        s = socket.create_connection((LOOPBACK, self.bridge.port), timeout=10)
        try:
            s.sendall(b"x" * (MAX_MESSAGE_BYTES + 10))
            s.shutdown(socket.SHUT_WR)
            s.settimeout(5)
            try:
                tra = s.recv(4096)
            except OSError:
                tra = b""
        finally:
            s.close()
        self.assertEqual(self.goi, [], "việc KHÔNG được chạy")


if __name__ == "__main__":
    unittest.main()


class VongDoiCauNoiTest(unittest.TestCase):
    def test_stop_KHI_CHUA_start_khong_treo(self):
        """`shutdown()` chặn vô hạn nếu `serve_forever()` chưa từng chạy — nó
        đợi một vòng lặp không tồn tại báo đã dừng. Đã vấp thật: bộ test treo
        ở đúng chỗ này."""
        b = WorkerBridge(BridgeConfig(), lambda p, f: {})
        b.stop()          # phai tra ve ngay, khong treo

    def test_start_hai_lan_khong_dung_hai_vong_lap(self):
        b = WorkerBridge(BridgeConfig(), lambda p, f: {})
        b.start()
        b.start()
        try:
            self.assertEqual(BridgeClient(b.port, b.token, timeout=5)
                             .health()["status"], "ok")
        finally:
            b.stop()

    def test_stop_hai_lan_khong_no(self):
        b = WorkerBridge(BridgeConfig(), lambda p, f: {})
        b.start()
        b.stop()
        b.stop()
