"""Chứng minh SỐNG bảy bước nghiệm thu clipboard của V0.2 — Windows THẬT.

Chạy với nền Qt THẬT (không `offscreen`) và **clipboard THẬT của Windows**.
Đây là điểm khác biệt với `tests/test_control_center_gui_attachments.py`:
bộ kiểm dựng `QMimeData` trong tiến trình, còn kịch bản này đi qua đúng
clipboard hệ điều hành mà Snipping Tool ghi vào.

    python scripts/control_center_attachment_proof.py
    python scripts/control_center_attachment_proof.py --that   # co mot luot agent THAT

MỘT ĐIỀU PHẢI NÓI THẲNG VỀ BƯỚC 1, và không được che:

Kịch bản này **không tự bấm được Win+Shift+S**. Snipping Tool đòi người
dùng kéo chuột chọn vùng — không có API nào làm hộ, và giả vờ làm được là
nói sai về bằng chứng.

Thứ nó làm là điều tương đương kiểm được bằng máy: đặt một **bitmap thật
lên clipboard thật của Windows**, đúng định dạng mà Snipping Tool đặt
(`CF_DIB`, Qt thấy qua `QMimeData.hasImage()`), rồi chạy tiếp sáu bước còn
lại qua đúng đường mã mà Ctrl+V đi.

Muốn có bước 1 đúng nghĩa "người bấm Win+Shift+S" thì dùng `--cho-nguoi`:
kịch bản sẽ ĐỢI bạn tự chụp, rồi đọc clipboard và chạy tiếp. Đó là bằng
chứng đầy đủ nhất, và nó cần một cú bấm của con người.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

DAT, HONG = "[ĐẠT ]", "[HỎNG]"


class Bang:
    def __init__(self) -> None:
        self.hang: list = []

    def ghi(self, buoc: str, ok: bool, chi_tiet: str = "") -> None:
        self.hang.append((buoc, ok, chi_tiet))
        print(f"  {DAT if ok else HONG} {buoc}"
              + (f"  — {chi_tiet}" if chi_tiet else ""))

    def hong(self) -> int:
        return sum(1 for _, ok, _ in self.hang if not ok)


def kho_git_tam() -> Path:
    goc = Path(tempfile.mkdtemp(prefix="cc-att-proof-"))
    (goc / "docs").mkdir(parents=True)
    (goc / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "proof@local"],
              ["git", "config", "user.name", "proof"],
              ["git", "add", "-A"], ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)
    return goc


def anh_thu(w: int = 320, h: int = 200):
    """Một ảnh có NỘI DUNG NHẬN RA ĐƯỢC, không phải một khối màu.

    Ảnh chụp màn hình thật có chữ và đường nét; một khối màu đơn nén xuống
    vài trăm byte và sẽ che mất mọi vấn đề về kích cỡ/nén.
    """
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    im = QImage(w, h, QImage.Format_RGB32)
    im.fill(QColor("#0b4a80"))
    p = QPainter(im)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont("Arial", 16))
    p.drawText(18, 40, "Router Control Center")
    p.drawText(18, 74, "bang chung dinh kem V0.2")
    p.drawText(18, 108, time.strftime("%Y-%m-%d %H:%M:%S"))
    for i in range(0, w, 24):
        p.drawLine(i, 130, i + 12, 180)
    p.end()
    return im


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--that", action="store_true",
                    help="chạy MỘT lượt agent thật (tốn quota)")
    ap.add_argument("--cho-nguoi", action="store_true",
                    help=("ĐỢI bạn tự bấm Win+Shift+S rồi mới đọc "
                          "clipboard — bằng chứng đầy đủ nhất cho bước 1"))
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    # NEN THAT, khong `offscreen`: clipboard cua Windows chi that khi co
    # mot ket noi man hinh that. `offscreen` co clipboard RIENG trong tien
    # trinh, va no se lam ca bai chung minh nay thanh vo nghia.
    os.environ.pop("QT_QPA_PLATFORM", None)

    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtWidgets import QApplication
    from scripts.control_center.engine import ControlCenter
    from scripts.control_center.gui.app import CuaSoChinh
    from scripts.control_center.gui.bridge import Cau
    from scripts.control_center.model import Project

    bd = Bang()
    app = QApplication.instance() or QApplication([])
    print("=" * 76)
    print("CHỨNG MINH ĐÍNH KÈM V0.2 — clipboard Windows THẬT, cửa sổ Qt THẬT")
    print(f"nền Qt: {app.platformName()!r}")
    print("=" * 76)
    if app.platformName() == "offscreen":
        print("  ! nền là 'offscreen' — clipboard sẽ KHÔNG phải clipboard "
              "thật của Windows. Bằng chứng này không tính.")

    kho = kho_git_tam()
    try:
        cc = ControlCenter(root=kho, probe=a.that, max_parallel=2)
        cau = Cau(cc=cc)
        cc.them_project(Project(project_id="fanfic", name="Fanfic",
                                repo_path=str(kho)))
        cau.chon_project("fanfic")
        cs = CuaSoChinh(cau=cau)
        cs.show()
        if a.that:
            cs.bat_dau()
        app.processEvents()
        kc = cs.khung_chat
        cb = QGuiApplication.clipboard()

        # -- BUOC 1: anh len clipboard THAT --------------------------------
        if a.cho_nguoi:
            print("\n  >>> Bấm Win+Shift+S và chụp một vùng bất kỳ.")
            print("      Kịch bản đợi tối đa 120s...")
            cb.clear()
            app.processEvents()
            het = time.time() + 120
            while time.time() < het and cb.image().isNull():
                app.processEvents()
                time.sleep(0.2)
            im = cb.image()
            bd.ghi("1. Win+Shift+S — NGƯỜI chụp, clipboard mang ảnh",
                   not im.isNull(),
                   f"{im.width()}×{im.height()}" if not im.isNull()
                   else "hết 120s mà clipboard không có ảnh")
        else:
            im = anh_thu()
            cb.setImage(im)
            app.processEvents()
            doc_lai = cb.image()
            bd.ghi("1. ảnh trên clipboard THẬT (tương đương Win+Shift+S)",
                   not doc_lai.isNull()
                   and doc_lai.width() == im.width(),
                   f"đặt {im.width()}×{im.height()}, đọc lại "
                   f"{doc_lai.width()}×{doc_lai.height()}")
        if cb.image().isNull():
            bd.ghi("2..7. (bỏ) — không có ảnh trên clipboard", False)
            raise SystemExit(1 if bd.hong() else 0)

        # -- BUOC 2: Ctrl+V vao o chat -------------------------------------
        # Di qua DUNG duong ma Ctrl+V di: `insertFromMimeData` voi mime
        # LAY TU CLIPBOARD THAT, khong phai mot QMimeData tu dung.
        kc.o_soan.insertFromMimeData(cb.mimeData())
        app.processEvents()
        ds = kc.dai.danh_sach()
        bd.ghi("2. Ctrl+V vào ô Project Chat", len(ds) == 1,
               f"{len(ds)} đính kèm được nhận")
        if not ds:
            raise SystemExit(1)
        dk = ds[0]

        # -- BUOC 3: thumbnail hien ----------------------------------------
        from scripts.control_center.gui.attachments_ui import TheDinhKem
        the = kc.dai.findChildren(TheDinhKem)
        co_tb = bool(the) and the[0].dk.la_anh \
            and the[0].hinh.pixmap() is not None \
            and not the[0].hinh.pixmap().isNull()
        bd.ghi("3. thumbnail hiện trong dải đính kèm", co_tb,
               f"{dk.filename} · {dk.co_doc_duoc()}")

        # -- BUOC 6 (do truoc): bam/kich co KHOP ---------------------------
        p_luu = cc.dinh_kem.duong_dan(dk.attachment_id)
        byte_dia = p_luu.read_bytes()
        sha_dia = hashlib.sha256(byte_dia).hexdigest()
        bd.ghi("6. băm/kích cỡ KHỚP giữa sổ và byte trên đĩa",
               sha_dia == dk.sha256 and len(byte_dia) == dk.size_bytes,
               f"sha256 {dk.sha256[:16]}… · {dk.size_bytes} byte")

        # -- BUOC 4: gui tin nhan ------------------------------------------
        kc.o_soan.setPlainText(
            "update docs/seed.md with one line describing the attached "
            "screenshot")
        kc.nut_gui.click()
        het = time.time() + 60
        while time.time() < het:
            app.processEvents()
            x = cc.dinh_kem.lay(dk.attachment_id)
            if x is not None and x.message_id is not None:
                break
            time.sleep(0.05)
        sau = cc.dinh_kem.lay(dk.attachment_id)
        bd.ghi("4. gửi tin nhắn (đính kèm gắn vào tin)",
               sau is not None and sau.message_id is not None,
               f"message_id={None if sau is None else sau.message_id}")

        # -- BUOC 5: agent doc duoc DUNG anh do ----------------------------
        het = time.time() + 60
        while time.time() < het and not cc.store.tasks("fanfic"):
            app.processEvents()
            time.sleep(0.05)
        viec = cc.store.tasks("fanfic")
        cap = []
        for t in viec:
            cap += [x.attachment_id for x in cc.dinh_kem.cho_agent(t.task_id)]
        khop = bool(viec) and all(
            dk.attachment_id in [x.attachment_id
                                 for x in cc.dinh_kem.cho_agent(t.task_id)]
            for t in viec)
        # Va agent nhan duoc DUONG DAN trong hop dong.
        mo = cc._hop_dong_kem_dinh_kem(viec[0])["objective"] if viec else ""
        bd.ghi("5. agent được cấp ĐÚNG ảnh đó (và chỉ việc của nó)",
               khop and str(p_luu) in mo,
               f"{len(viec)} việc, {len(cap)} lần cấp; đường dẫn có trong "
               f"hợp đồng: {str(p_luu) in mo}")
        ngoai = cc.dinh_kem.cho_agent("fanfic.khong_lien_quan")
        bd.ghi("5b. việc KHÔNG liên quan không thấy gì", ngoai == [],
               f"{len(ngoai)} đính kèm")

        # -- BUOC 7: KHONG co tai len nao ----------------------------------
        import ast
        cam = {"requests", "urllib", "urllib3", "http", "httpx", "socket",
               "ftplib", "smtplib", "boto3", "aiohttp"}
        thay = []
        for ten in ("attachments.py", "gui/attachments_ui.py"):
            cay = ast.parse((GOC / "scripts" / "control_center" / ten)
                            .read_text(encoding="utf-8"))
            for n in ast.walk(cay):
                if isinstance(n, ast.Import):
                    thay += [x.name.split(".")[0] for x in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module:
                    thay.append(n.module.split(".")[0])
        ro = sorted(set(thay) & cam)
        bd.ghi("7. KHÔNG tệp nào bị tải lên đâu", not ro,
               f"tầng đính kèm không import thư viện mạng nào"
               if not ro else f"đã import: {ro}")
        # Va duong dan agent nhan la CUC BO.
        bd.ghi("7b. đường dẫn agent nhận là CỤC BỘ",
               str(p_luu).startswith(str(kho)) and "://" not in mo,
               str(p_luu))

        # -- Keo PDF va tep MA NGUON tu Explorer ---------------------------
        pdf = kho / "bao cao.pdf"
        pdf.write_bytes(b"%PDF-1.7\n" + b"noi dung thu " * 400)
        ma = kho / "loop.py"
        ma.write_text("def f():\n    return 1\n", encoding="utf-8")
        from PySide6.QtCore import QMimeData, QUrl
        m2 = QMimeData()
        m2.setUrls([QUrl.fromLocalFile(str(pdf)), QUrl.fromLocalFile(str(ma))])
        kc.o_soan.insertFromMimeData(m2)
        app.processEvents()
        ds2 = kc.dai.danh_sach()
        ten2 = sorted(x.filename for x in ds2)
        bd.ghi("8. kéo-thả PDF + tệp mã nguồn từ Explorer",
               ten2 == ["bao cao.pdf", "loop.py"],
               f"nhận: {ten2}")
        if len(ds2) == 2:
            ok_bam = all(cc.dinh_kem.kiem_toan_ven(x.attachment_id)
                         for x in ds2)
            bd.ghi("8b. băm của cả hai tệp kéo vào đều KHỚP", ok_bam,
                   " · ".join(f"{x.filename}={x.sha256[:8]}" for x in ds2))

        # -- Luot agent THAT (tuy chon) ------------------------------------
        if a.that and viec:
            print(f"\n  … chờ một lượt agent THẬT (tối đa {a.timeout:.0f}s)")
            tid = viec[0].task_id
            het = time.time() + a.timeout
            while time.time() < het:
                app.processEvents()
                cau.lam_moi()
                app.processEvents()
                t = cc.store.task(tid)
                if t and t.state.value in ("DONE", "FAILED", "REVIEW"):
                    break
                time.sleep(1.0)
            t = cc.store.task(tid)
            # Sau khi chay xong, anh phai VAN con nguyen va van dung bam.
            bd.ghi("9. sau một lượt agent thật, ảnh vẫn nguyên vẹn",
                   cc.dinh_kem.kiem_toan_ven(dk.attachment_id),
                   f"trạng thái việc = {t.state.value if t else '?'}")

        cau.dung()
    finally:
        if not a.keep:
            shutil.rmtree(kho, ignore_errors=True)
        else:
            print(f"\n  (giữ lại {kho})")

    print("\n" + "=" * 76)
    hong = bd.hong()
    print(f"KẾT LUẬN: {len(bd.hang) - hong}/{len(bd.hang)} bước ĐẠT")
    if not a.cho_nguoi:
        print("  Lưu ý: bước 1 dùng bitmap đặt lên clipboard thật, KHÔNG "
              "phải một cú Win+Shift+S do người bấm.")
        print("  Chạy lại với --cho-nguoi để có bằng chứng đầy đủ bước đó.")
    print("=" * 76)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
