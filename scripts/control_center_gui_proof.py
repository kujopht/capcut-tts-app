"""Chứng minh SỐNG mười tiêu chí nghiệm thu của V0.1.1, qua GIAO DIỆN THẬT.

Khác với `tests/test_control_center_gui_*.py` (backend giả, nhanh, offline),
kịch bản này dựng **`ControlCenter` THẬT** trên một thư mục tạm, dựng **cửa
sổ Qt THẬT** (offscreen), rồi bấm đúng những nút mà người dùng bấm. Nếu có
một chỗ nào giao diện chỉ *trông như* nối vào backend, chỗ đó sẽ lộ ra ở
đây chứ không lộ ra trong bộ kiểm.

Mặc định KHÔNG gọi ra provider thật (`--that` để bật). Không có cờ đó, nó
chứng minh được 8/10 tiêu chí; hai tiêu chí còn lại (agent/phiên/worktree
cập nhật sống, nhật ký của một lượt thật) cần một lượt agy thật.

    python scripts/control_center_gui_proof.py           # offline, nhanh
    python scripts/control_center_gui_proof.py --that    # co mot luot agent THAT
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

DAT, HONG = "[ĐẠT ]", "[HỎNG]"


class BangDiem:
    def __init__(self) -> None:
        self.hang: list = []

    def ghi(self, tieu_chi: str, ok: bool, chi_tiet: str = "") -> None:
        self.hang.append((tieu_chi, ok, chi_tiet))
        print(f"  {DAT if ok else HONG} {tieu_chi}"
              + (f"  — {chi_tiet}" if chi_tiet else ""))

    def hong(self) -> int:
        return sum(1 for _, ok, _ in self.hang if not ok)


def kho_git_tam() -> Path:
    """Một kho git thật, tối thiểu — worktree cần một kho thật để nhánh ra."""
    goc = Path(tempfile.mkdtemp(prefix="cc-gui-proof-"))
    (goc / "docs" / "reports").mkdir(parents=True)
    (goc / "docs" / "reports" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "proof@local"],
              ["git", "config", "user.name", "proof"],
              ["git", "add", "-A"],
              ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)
    return goc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--that", action="store_true",
                    help="chạy MỘT lượt agent thật (tốn quota)")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--keep", action="store_true", help="giữ thư mục tạm")
    a = ap.parse_args(argv)

    from PySide6.QtWidgets import QApplication, QPushButton
    from scripts.control_center.engine import ControlCenter
    from scripts.control_center.gui.app import CuaSoChinh
    from scripts.control_center.gui.bridge import Cau
    from scripts.control_center.model import Project

    bd = BangDiem()
    app = QApplication.instance() or QApplication([])
    kho = kho_git_tam()
    print("=" * 74)
    print("CHỨNG MINH GIAO DIỆN V0.1.1 — backend THẬT, cửa sổ Qt THẬT")
    print(f"kho tạm: {kho}")
    print("=" * 74)

    try:
        # -- 1. Khoi dong ----------------------------------------------------
        cc = ControlCenter(root=kho, probe=a.that, max_parallel=2)
        cau = Cau(cc=cc)
        cs = CuaSoChinh(cau=cau)
        cs.show()

        # VONG DIEU PHOI chi bat khi `--that`, va day la lua chon co
        # chu dich, khong phai thieu sot:
        #
        #   * `bat_dau()` goi `cc.start()`, va tu V0.1.1 vong lap do
        #     DO SUC KHOE LUOI ngay khi co viec cho giao — tuc la GOI
        #     RA MANG. Mot bai chung minh "offline" ma lang le goi
        #     provider thi khong con la offline.
        #   * Nguoc lai, tieu chi 5 (agent/phien/worktree cap nhat
        #     song) KHONG THE chung minh ma khong co vong lap. Ban dau
        #     toi quen goi `bat_dau()` o CA HAI che do, nen tieu chi 5
        #     bao HONG voi "trang thai cuoi=QUEUED" — mot loi cua
        #     KICH BAN, khong phai cua san pham. Ghi lai vi no de tai
        #     dien: mot bai chung minh thieu mot cu goi khoi dong se
        #     to cao san pham thay vi to cao chinh no.
        if a.that:
            cs.bat_dau()
        # `or True` DA BI BO. No lam tieu chi nay luon DAT, ke ca khi bo han
        # `cs.show()` — mot dong "bang chung" khong kiem gi thi te hon la
        # khong co dong nao, vi no chiem cho cua mot phep kiem thuc.
        bd.ghi("1. cửa sổ mở được (điểm vào một lệnh)",
               cs.isVisible(), "router-cc-gui.cmd -> QMainWindow")

        # -- 2. Mo du an -----------------------------------------------------
        cc.them_project(Project(project_id="fanfic", name="Fanfic",
                                repo_path=str(kho)))
        cau.chon_project("fanfic")
        app.processEvents()
        bd.ghi("2. mở được dự án Fanfic",
               cs.nhan_project.text() == "Fanfic",
               f"thanh trên hiện {cs.nhan_project.text()!r}")

        # -- 3. Go viec bang CHUOT (o soan + nut Gui) ------------------------
        muc_tieu = ("update docs/reports/seed.md with one line naming the "
                    "Router Control Center GUI")
        kc = cs.khung_chat
        kc.o_soan.setPlainText(muc_tieu)
        kc.nut_gui.click()
        for _ in range(400):
            app.processEvents()
            if cc.store.tasks("fanfic"):
                break
            time.sleep(0.05)
        viec = cc.store.tasks("fanfic")
        bd.ghi("3. gõ việc trong Chat rồi bấm Gửi", bool(viec),
               f"{len(viec)} việc được tạo")

        # -- 4. Router tao/quan ly viec --------------------------------------
        cau.lam_moi()
        app.processEvents()
        bd.ghi("4. Router tạo & quản lý việc",
               cs.khung_viec.bang.rowCount() == len(viec),
               f"bảng Tasks có {cs.khung_viec.bang.rowCount()} hàng")

        # -- 6. Xem chi tiet + nhat ky, khong can terminal -------------------
        cs.khung_viec.bang.selectRow(0)
        app.processEvents()
        co_ct = viec[0].task_id in cs.khung_viec.chi_tiet.o.toPlainText()
        nut = {n.text(): n for n in
               cs.khung_viec.chi_tiet.findChildren(QPushButton)}
        nut["Nhật ký"].click()
        app.processEvents()
        co_log = bool(cs.khung_log.nk.van_ban_dang_hien().strip())
        bd.ghi("6. xem chi tiết + nhật ký bằng chuột", co_ct and co_log,
               f"chi tiết={co_ct} nhật ký={co_log}")

        # -- 7. Copy nhat ky -------------------------------------------------
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText("")
        cs.khung_log.nk.copy_tat_ca()
        app.processEvents()
        cb = QGuiApplication.clipboard().text()
        bd.ghi("7. Copy nhật ký ra clipboard",
               bool(cb.strip()) and viec[0].task_id in cb,
               f"{len(cb)} ký tự vào clipboard")

        # -- 8. Pause / Resume bang NUT --------------------------------------
        tid = viec[0].task_id
        nut["Tạm dừng"].click()
        for _ in range(100):
            app.processEvents()
            if (cc.store.task(tid) or viec[0]).state.value == "PAUSED":
                break
            time.sleep(0.05)
        da_dung = (cc.store.task(tid).state.value == "PAUSED")
        nut["Tiếp tục"].click()
        for _ in range(100):
            app.processEvents()
            if cc.store.task(tid).state.value != "PAUSED":
                break
            time.sleep(0.05)
        da_tiep = (cc.store.task(tid).state.value != "PAUSED")
        bd.ghi("8. Pause/Resume bằng nút", da_dung and da_tiep,
               f"pause={da_dung} resume={da_tiep}")

        # -- 9. Hop thoai dong bang X va Esc ---------------------------------
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from scripts.control_center.gui.views import HopTroGiup
        from scripts.control_center.gui.widgets import HopThoai
        h = HopThoai("Hướng dẫn dùng", cs)
        h.than.addWidget(HopTroGiup())
        h.show()
        co_x = h.nut_x.isVisibleTo(h)
        h.nut_x.click()
        dong_x = not h.isVisible()
        h2 = HopThoai("Hướng dẫn dùng", cs)
        h2.show()
        h2.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape,
                                   Qt.NoModifier))
        dong_esc = not h2.isVisible()
        bd.ghi("9. hộp thoại đóng bằng X và Esc",
               co_x and dong_x and dong_esc,
               f"X hiện={co_x} X đóng={dong_x} Esc đóng={dong_esc}")

        # -- 5. Trang thai SONG (chi khi --that) -----------------------------
        if a.that:
            print(f"\n  … chờ một lượt agent THẬT (tối đa {a.timeout:.0f}s)")
            thay_phien, thay_cay = False, False
            het = time.time() + a.timeout
            while time.time() < het:
                app.processEvents()
                cau.lam_moi()
                app.processEvents()
                if cs.khung_agent.bang.rowCount() > 0:
                    thay_phien = True
                t = cc.store.task(tid)
                if t and t.worktree:
                    thay_cay = True
                if t and t.state.value in ("DONE", "FAILED", "REVIEW"):
                    break
                time.sleep(1.0)
            t = cc.store.task(tid)
            bd.ghi("5. agent/phiên/worktree cập nhật sống",
                   thay_phien and thay_cay,
                   f"phiên hiện ở bảng Agents={thay_phien} "
                   f"worktree={thay_cay} trạng thái cuối={t.state.value}")
        else:
            print("\n  (bỏ qua tiêu chí 5 — cần --that: vòng điều phối phải "
                  "chạy, và nó gọi ra provider thật)")

        # -- 10. Khoi dong lai, trang thai con nguyen ------------------------
        cau.dung()
        app.processEvents()
        cc2 = ControlCenter(root=kho, probe=False, max_parallel=2)
        cau2 = Cau(cc=cc2)
        cs2 = CuaSoChinh(cau=cau2)
        cau2.chon_project("fanfic")
        app.processEvents()
        con = cs2.khung_viec.bang.rowCount()
        co_chat = len(cc2.store.chat("fanfic")) >= 2
        bd.ghi("10. khởi động lại, trạng thái còn nguyên",
               con == len(viec) and co_chat,
               f"{con} việc + {len(cc2.store.chat('fanfic'))} tin chat "
               f"đọc lại từ SQLite")
        cau2.dung()

    finally:
        if not a.keep:
            shutil.rmtree(kho, ignore_errors=True)
        else:
            print(f"\n  (giữ lại {kho})")

    print("\n" + "=" * 74)
    hong = bd.hong()
    print(f"KẾT LUẬN: {len(bd.hang) - hong}/{len(bd.hang)} tiêu chí ĐẠT")
    if not a.that:
        print("  Lưu ý: chưa chạy --that nên tiêu chí 5 chưa được chứng minh.")
    print("=" * 74)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
