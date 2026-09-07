"""Bài kiểm giao diện Control Center — chạy KHÔNG CẦN màn hình thật.

Textual có chế độ chạy ngầm (`App.run_test()`), nên giao diện kiểm được như
mọi mã khác. Đó là lý do V0.1 dựng trên Textual thay vì kéo thêm một stack
mới vào kho: một giao diện không kiểm được sẽ hỏng lặng lẽ và chỉ lộ ra khi
người dùng mở nó.

BÀI KIỂM Ở ĐÂY KIỂM HÀNH VI, KHÔNG KIỂM MÀU SẮC. Cái đáng khoá lại là: bảy
màn hình có dựng được không, ô chat có thật sự tạo việc không, các phím vận
hành có gọi đúng bộ máy không, và một thao tác phá được có hỏi lại không.
"""
from __future__ import annotations

import unittest

try:
    from textual.widgets import TabbedContent
    CO_TEXTUAL = True
except ImportError:                                       # pragma: no cover
    CO_TEXTUAL = False

from scripts.control_center.model import TaskState
from scripts.tests.test_control_center_slice import (FakeExecutor, _cc, _xong,
                                                     kho_git_tam)


@unittest.skipUnless(CO_TEXTUAL, "chưa cài textual (requirements-control-room)")
class TestControlCenterUI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.repo = kho_git_tam()
        self.cc = _cc(self.repo, ex=FakeExecutor())

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                 # noqa: BLE001
            pass

    def _app(self):
        from scripts.control_center.ui.app import ControlCenterApp
        # Nhip ve cham trong bai kiem: vong lap ve KHONG phai thu dang duoc
        # kiem o day, va mot nhip 1s se chen vao giua cac buoc cua Pilot.
        # `autostart=False`: bai kiem tu dap nhip. Voi vong lap nen bat,
        # moi phep kiem trang thai thanh mot cuoc dua — `stop_engine()` sau
        # khi mount van de lot mot nhip, va viec chay xong truoc khi bai
        # kiem kip bam `p`. Da hong ngau nhien that.
        return ControlCenterApp(self.cc, refresh_interval=60.0,
                                autostart=False)

    async def _mo(self, pilot) -> None:
        """Mở app với vòng lặp điều phối TẮT (`autostart=False`).

        Vòng lặp nền biến mọi phép kiểm trạng thái thành một cuộc đua với bộ
        điều phối. Ở đây nhịp là tường minh; việc vòng lặp có chạy thật hay
        không đã được `test_control_center_slice` kiểm riêng.
        """
        await pilot.pause()
        await pilot.pause()

    async def test_bay_man_hinh_deu_dung_duoc(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            self.assertTrue(app.query("#projects"))       # 1 Projects
            self.assertTrue(app.query("#chat"))           # 2 Chat
            self.assertTrue(app.query("#tasks"))          # 3 Tasks
            self.assertTrue(app.query("#agents"))         # 4 Agents
            self.assertTrue(app.query("#events"))         # 6 Logs
            self.assertTrue(app.query("#usage"))          # 7 Usage
            tabs = app.query_one("#tabs", TabbedContent)
            self.assertEqual(len(tabs.query("TabPane")), 5)

    async def test_o_chat_tao_viec_that(self):
        """Gõ vào ô chat -> việc xuất hiện trong sổ THẬT, không phải mẫu."""
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.query_one("#chat").post_message(
                app.query_one("#chat").Submitted("fix the styling in web/admin"))
            await pilot.pause()
            ts = self.cc.store.tasks("demo")
            self.assertEqual(len(ts), 1)
            self.assertEqual(app.query_one("#tasks").row_count, 1)

    async def test_bang_viec_ve_dung_so_dong(self):
        self.cc.chat("demo", "fix web/admin and investigate the slow build")
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            self.assertEqual(app.query_one("#tasks").row_count,
                             len(self.cc.store.tasks("demo")))

    async def test_thanh_trang_thai_dem_viec_CAN_NGUOI(self):
        self.cc.chat("demo", "deploy the web to production")
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            self.assertEqual(
                sum(1 for t in app.snap["tasks"] if t["state"] == "BLOCKED"), 1)

    async def test_dung_han_HOI_LAI_truoc_khi_giet_tien_trinh(self):
        """Thao tác phá được phải xác nhận — không dừng ngay khi bấm phím."""
        from scripts.control_center.ui.app import XacNhan
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            app.query_one("#tasks").move_cursor(row=0)
            await pilot.press("s")
            await pilot.pause()
            self.assertIsInstance(app.screen, XacNhan,
                                  "phải hiện hộp xác nhận")
            self.assertIsNot(self.cc.store.task(tid).state, TaskState.FAILED,
                             "chưa xác nhận thì KHÔNG được dừng")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsNot(self.cc.store.task(tid).state, TaskState.FAILED)

    async def test_duyet_cong_HOI_LAI(self):
        from scripts.control_center.ui.app import XacNhan
        self.cc.chat("demo", "deploy the web to production")
        tid = self.cc.store.tasks("demo")[0].task_id
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            app.query_one("#tasks").move_cursor(row=0)
            await pilot.press("g")
            await pilot.pause()
            self.assertIsInstance(app.screen, XacNhan)
            self.assertIs(self.cc.store.task(tid).state, TaskState.BLOCKED,
                          "chưa xác nhận thì cổng vẫn đóng")

    async def test_tam_dung_KHONG_hoi_lai_vi_hoan_tac_duoc(self):
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            app.query_one("#tasks").move_cursor(row=0)
            await pilot.press("p")
            await pilot.pause()
            self.assertIs(self.cc.store.task(tid).state, TaskState.PAUSED)

    async def test_chi_tiet_viec_mo_duoc(self):
        from scripts.control_center.ui.app import TaskDetail
        self.cc.chat("demo", "fix web/admin")
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            app.query_one("#tasks").move_cursor(row=0)
            app.action_chi_tiet()
            await pilot.pause()
            self.assertIsInstance(app.screen, TaskDetail)

    async def test_vong_lap_ve_KHONG_goi_CLI_nha_cung_cap(self):
        """Vẽ giao diện không được phép gọi `agy`/`codex`.

        Mỗi lệnh đó mất vài giây và tốn một lượt quota; một vòng lặp vẽ 1
        giây sẽ biến bảng điều khiển thành một bộ phát lệnh CLI.
        """
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            app.lam_moi()
            await pilot.pause()
            self.assertFalse(app._usage.get("provider_probe_ran"))
            self.assertEqual(app._usage.get("providers"), [])

    async def test_bang_usage_KHONG_hien_so_khong_cho_thu_khong_do_duoc(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)
            app.project_id = "demo"
            app.lam_moi()
            await pilot.pause()
            for u in app._usage.get("pools", []):
                for m in u["metrics"]:
                    if m["confidence"] == "UNAVAILABLE":
                        self.assertIsNone(m["value"])

    async def test_loi_doc_trang_thai_HIEN_RA_chu_khong_im_lang(self):
        """Đọc hỏng -> thanh trạng thái nói "KHÔNG ĐỌC ĐƯỢC".

        Lỗi thật đã xảy ra ở `control_room/app.py`: một `except: pass` khiến
        bảng vẽ lại số liệu chết trông hệt số liệu sống, và người vận hành
        ra quyết định trên đó.
        """
        app = self._app()
        async with app.run_test() as pilot:
            await self._mo(pilot)

            def _no(*a, **k):
                raise RuntimeError("sổ hỏng")
            app.cc.snapshot = _no
            app.lam_moi()
            await pilot.pause()
            self.assertGreaterEqual(app._doc_hong, 1)
            self.assertIn("sổ hỏng", app._loi_cuoi)


if __name__ == "__main__":
    unittest.main()
