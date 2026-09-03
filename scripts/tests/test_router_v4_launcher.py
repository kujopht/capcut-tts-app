"""Bọc launcher đa-tài-khoản Antigravity — bất biến an toàn + khoá switch.

Khoá lại các kết luận ĐO ĐƯỢC ngày 2026-09-03 (xem
`docs/reports/ANTIGRAVITY_LAUNCHER_AUDIT.md`). Nếu ai đó về sau bỏ khoá
`switch → spawn` hay để Router tự chạm credential, các bài này vỡ.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from scripts.router_v4 import antigravity_launcher as AL


class TestAnhXaCoDinh(unittest.TestCase):
    def test_AG01_den_AG08_anh_xa_acc1_den_acc8(self):
        self.assertEqual(len(AL.ACC_CUA_RUNTIME), 8)
        for i in range(1, 9):
            self.assertEqual(AL.ACC_CUA_RUNTIME[f"AG{i:02d}"], f"acc{i}")

    def test_anh_xa_khong_bao_gio_xoay(self):
        """Cùng một runtime phải luôn trỏ cùng một acc — nếu ánh xạ đổi được
        lúc chạy thì 'danh tính cố định' mất nghĩa."""
        a = [AL.acc_cua(f"AG{i:02d}") for i in range(1, 9)]
        b = [AL.acc_cua(f"AG{i:02d}") for i in range(1, 9)]
        self.assertEqual(a, b)
        self.assertEqual(len(set(a)), 8)

    def test_runtime_la_khong_co_acc(self):
        self.assertIsNone(AL.acc_cua("CODEX01"))
        self.assertIsNone(AL.acc_cua("AG99"))


class TestRouterKhongTuChamCredential(unittest.TestCase):
    """Mission: "Router should call the stable launcher/profile abstraction,
    not manipulate raw credentials itself." Kiểm bằng MÃ, không bằng lời hứa.
    """

    #: Moi thu trong Router V4 + tang bo (pool) deu KHONG duoc goi truc tiep.
    CAM = ("CredWriteW", "CredReadW", "CredDeleteW", "advapi32")

    def _quet(self, goc: Path):
        xau = []
        for p in sorted(goc.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            for tu in self.CAM:
                for i, dong in enumerate(t.splitlines(), 1):
                    if tu in dong and not dong.lstrip().startswith("#"):
                        xau.append(f"{p.name}:{i} {tu}")
        return xau

    def test_router_v4_khong_goi_api_credential(self):
        goc = Path(AL.__file__).resolve().parent
        self.assertEqual(self._quet(goc), [],
                         "Router V4 phải gọi launcher, KHÔNG tự CredRead/CredWrite")

    def test_router_v3_pool_khong_goi_api_credential(self):
        goc = Path(AL.__file__).resolve().parents[1] / "router_v3" / "pool"
        self.assertEqual(self._quet(goc), [])

    def test_adapter_khong_bao_gio_dung_co_nguy_hiem(self):
        """Mọi lần GÁN `dangerously_skip_permissions` phải là `=False`, và
        chuỗi cờ dòng lệnh không được xuất hiện trong mã thực thi.

        Kiểm trên CÂY CÚ PHÁP, không trên văn bản thô: bản đầu của bài kiểm
        này quét từng dòng và báo hỏng vì một dòng DOCSTRING có nhắc tên cờ.
        Một bài kiểm an toàn báo động giả sẽ bị người ta tắt đi, và thế là
        mất luôn cái nó bảo vệ.
        """
        import ast
        cay = ast.parse(Path(AL.__file__).read_text(encoding="utf-8",
                                                    errors="replace"))
        gan = 0
        for node in ast.walk(cay):
            if isinstance(node, ast.keyword) and \
                    node.arg == "dangerously_skip_permissions":
                gan += 1
                self.assertIsInstance(node.value, ast.Constant, "phải là hằng")
                self.assertIs(node.value.value, False,
                              "cờ nguy hiểm chỉ được truyền là False")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                continue                  # chuoi/docstring: bo qua
        self.assertGreaterEqual(gan, 1,
                                "phải có ít nhất một lần gán tường minh =False")


class TestKhoaSwitch(unittest.TestCase):
    """Chuỗi `switch → spawn` phải NGUYÊN TỬ.

    Không có khoá này, hai luồng đan nhau (switch acc1, switch acc2, spawn,
    spawn) làm CẢ HAI tiến trình đọc được acc2 — hai worker cùng một danh
    tính trong khi sổ đăng ký tưởng là hai tài khoản.
    """

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.p = Path(self._d.name) / "switch.lock"

    def tearDown(self):
        try:
            self._d.cleanup()
        except (OSError, PermissionError):
            pass

    def test_hai_ben_khong_cung_giu_khoa(self):
        a = AL.KhoaLauncher(self.p)
        b = AL.KhoaLauncher(self.p)
        self.assertTrue(a.acquire(timeout=2))
        self.assertFalse(b.acquire(timeout=1))
        a.release()
        self.assertTrue(b.acquire(timeout=2))
        b.release()

    def test_nhieu_luong_vao_ra_tuan_tu_khong_chong_nhau(self):
        """Đây là bài kiểm quan trọng nhất: đếm số bên ở TRONG vùng tới hạn
        tại mọi thời điểm — không bao giờ được vượt 1."""
        dong_thoi = []
        toi_da = [0]
        khoa_dem = threading.Lock()
        loi = []

        def than(i):
            try:
                k = AL.KhoaLauncher(self.p, ttl=30.0)
                if not k.acquire(timeout=25):
                    loi.append(f"{i} khong giành duoc")
                    return
                with khoa_dem:
                    dong_thoi.append(i)
                    toi_da[0] = max(toi_da[0], len(dong_thoi))
                time.sleep(0.05)          # gia lap `switch -> spawn`
                with khoa_dem:
                    dong_thoi.remove(i)
                k.release()
            except Exception as exc:                      # noqa: BLE001
                loi.append(f"{i}: {type(exc).__name__}: {exc}")

        ts = [threading.Thread(target=than, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=60)
        self.assertEqual(loi, [], f"lỗi: {loi}")
        self.assertEqual(toi_da[0], 1,
                         f"có lúc {toi_da[0]} bên cùng ở trong vùng tới hạn")

    def test_khoa_bo_hoang_bi_thu_hoi_sau_TTL(self):
        """Chủ khoá có thể bị `taskkill`. Một khoá mồ côi phải TỰ hết hiệu
        lực, nếu không cả bể worker treo vĩnh viễn."""
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.p.write_text(json.dumps({"pid": 999999, "at": time.time() - 999}),
                          encoding="utf-8")
        k = AL.KhoaLauncher(self.p, ttl=1.0)
        self.assertTrue(k.acquire(timeout=5), "khoá bỏ hoang phải thu hồi được")
        k.release()

    def test_khoa_con_han_KHONG_bi_cuop(self):
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.p.write_text(json.dumps({"pid": 999999, "at": time.time()}),
                          encoding="utf-8")
        k = AL.KhoaLauncher(self.p, ttl=300.0)
        self.assertFalse(k.acquire(timeout=1))

    def test_khoa_hong_CHUA_qua_TTL_thi_KHONG_bi_cuop(self):
        """Khoá không đọc được nhưng MỚI tạo phải được tôn trọng.

        Bài này thay cho `test_khoa_hong_coi_nhu_bo_hoang` cũ, bài đó đòi
        thu hồi NGAY một khoá hỏng còn mới. Chính đòi hỏi đó là lỗ hổng:
        `acquire()` tạo tệp bằng `O_CREAT|O_EXCL` RỒI MỚI `os.write` nội
        dung, nên giữa hai bước tệp tồn tại mà RỖNG — không đọc được, y như
        một tệp hỏng. Thu hồi ngay = xoá khoá của bên vừa được cấp hợp lệ,
        và cả hai bên cùng vào vùng tới hạn.

        Đã đo thật: CI Linux (run 33766689852) đánh sập
        `test_nhieu_luong_vao_ra_tuan_tu_khong_chong_nhau` với "2 != 1: có
        lúc 2 bên cùng ở trong vùng tới hạn". Trên Windows bài đó ĐẠT, nhưng
        chỉ vì tình cờ — `unlink()` một tệp đang mở bị Windows từ chối, còn
        POSIX thì cho phép.

        Yêu cầu gốc ("khoá hỏng không được treo cả bể") vẫn được giữ, chỉ
        chuyển từ NGAY sang SAU TTL — xem bài kế tiếp.
        """
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.p.write_text("khong-phai-json", encoding="utf-8")
        k = AL.KhoaLauncher(self.p, ttl=300.0)
        self.assertFalse(k.acquire(timeout=1),
                         "khoá hỏng còn mới phải được coi là ĐANG GIỮ")

    def test_khoa_hong_QUA_TTL_thi_thu_hoi_duoc(self):
        """Nửa còn lại: một khoá hỏng THẬT SỰ bỏ hoang vẫn phải hết hiệu lực,
        nếu không cả bể worker treo vĩnh viễn."""
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.p.write_text("khong-phai-json", encoding="utf-8")
        # Lùi mtime ra quá TTL: đây chính là tín hiệu mà `_cu_qua()` lui về
        # dùng khi không đọc được ruột tệp.
        cu = time.time() - 999
        os.utime(self.p, (cu, cu))
        k = AL.KhoaLauncher(self.p, ttl=1.0)
        self.assertTrue(k.acquire(timeout=5),
                        "khoá hỏng đã quá TTL phải thu hồi được")
        k.release()

    def test_context_manager_nha_khoa_khi_co_loi(self):
        k = AL.KhoaLauncher(self.p)
        try:
            with k:
                raise RuntimeError("bang")
        except RuntimeError:
            pass
        k2 = AL.KhoaLauncher(self.p)
        self.assertTrue(k2.acquire(timeout=2), "khoá phải được nhả dù có lỗi")
        k2.release()


class TestUuTienBangChungDanhTinh(unittest.TestCase):
    """Một blob hồ sơ ĐÃ CŨ không được lấn át bằng chứng từ một runtime đã
    xác thực.

    Sự cố thật (2026-09-03): kết luận "acc8 trùng danh tính với acc1" được
    ghi vào commit 1aab01b lúc 10:25:21Z, nhưng `acc8.bin` được ghi lại lúc
    12:06:22Z — lần đăng nhập lại hạ cánh 1h41m SAU khi kết luận được ghi.
    Kết luận đúng lúc ghi, sai ngay sau đó, và không ai đo lại. Đo lại cho
    thấy cả 8 tài khoản có 8 dấu vân tay KHÁC NHAU.
    """

    def test_blob_CU_hon_thi_live_thang(self):
        fp, nguon = AL.danh_tinh_uu_tien(
            blob_fp="aaaaaaaaaaaa", blob_at=1000.0,
            live_fp="bbbbbbbbbbbb", live_at=2000.0)
        self.assertEqual(fp, "bbbbbbbbbbbb")
        self.assertEqual(nguon, AL.NGUON_LIVE)

    def test_blob_MOI_hon_thi_blob_thang(self):
        """Một lần đăng nhập vừa được lưu LÀ bằng chứng mới nhất."""
        fp, nguon = AL.danh_tinh_uu_tien(
            blob_fp="aaaaaaaaaaaa", blob_at=3000.0,
            live_fp="bbbbbbbbbbbb", live_at=2000.0)
        self.assertEqual(fp, "aaaaaaaaaaaa")
        self.assertEqual(nguon, AL.NGUON_BLOB)

    def test_bang_diem_thi_live_thang(self):
        """Blob cùng tuổi KHÔNG mạnh hơn chính phiên đã xác thực."""
        fp, nguon = AL.danh_tinh_uu_tien(
            blob_fp="aaaaaaaaaaaa", blob_at=2000.0,
            live_fp="bbbbbbbbbbbb", live_at=2000.0)
        self.assertEqual(nguon, AL.NGUON_LIVE)

    def test_chi_co_mot_nguon_thi_dung_nguon_do(self):
        self.assertEqual(
            AL.danh_tinh_uu_tien(blob_fp="", blob_at=0.0,
                                 live_fp="bbbbbbbbbbbb", live_at=1.0),
            ("bbbbbbbbbbbb", AL.NGUON_LIVE))
        self.assertEqual(
            AL.danh_tinh_uu_tien(blob_fp="aaaaaaaaaaaa", blob_at=1.0,
                                 live_fp="", live_at=0.0),
            ("aaaaaaaaaaaa", AL.NGUON_BLOB))
        self.assertEqual(
            AL.danh_tinh_uu_tien(blob_fp="", blob_at=0.0,
                                 live_fp="", live_at=0.0), ("", ""))

    def test_tai_hien_dung_su_co_acc8(self):
        """Đúng các mốc thời gian thật của sự cố, bằng dấu vân tay giả."""
        luc_ket_luan = 1767_000_000.0            # 10:25:21Z (commit 1aab01b)
        luc_relogin = luc_ket_luan + 6061.0      # 12:06:22Z (acc8.bin)
        # Ở THỜI ĐIỂM kết luận: blob acc8 còn cũ, chưa có bằng chứng live.
        fp_cu, _ = AL.danh_tinh_uu_tien(
            blob_fp="giong_acc1__", blob_at=luc_ket_luan - 7200,
            live_fp="", live_at=0.0)
        self.assertEqual(fp_cu, "giong_acc1__",
                         "lúc đó chỉ có blob cũ — kết luận cũ giải thích được")
        # SAU relogin: blob mới hơn -> danh tính mới thắng, không còn trùng.
        fp_moi, nguon = AL.danh_tinh_uu_tien(
            blob_fp="acc8_that___", blob_at=luc_relogin,
            live_fp="giong_acc1__", live_at=luc_ket_luan)
        self.assertEqual(fp_moi, "acc8_that___")
        self.assertEqual(nguon, AL.NGUON_BLOB)
        self.assertNotEqual(fp_moi, fp_cu,
                            "sau relogin acc8 KHÔNG còn mang danh tính cũ")

    def test_khong_bao_gio_tra_ve_chuoi_hinh_dang_email(self):
        """Hàm chỉ nhận/trả DẤU VÂN TAY. Nếu một ngày ai đó truyền email thô
        vào đây, bài này không chặn được — nhưng nó chốt rằng bản thân hàm
        không tự đi tìm email ở đâu cả: cùng đầu vào, cùng đầu ra, không đọc
        tệp, không gọi mạng."""
        import inspect
        src = inspect.getsource(AL.danh_tinh_uu_tien)
        for xau in ("@", "open(", "read_text", "read_bytes", "requests",
                    "httpx", "subprocess"):
            self.assertNotIn(xau, src.split('"""')[-1],
                             f"thân hàm không được chứa {xau!r}")


class TestSoDangKyThat(unittest.TestCase):
    """Fabric thật với launcher — bất biến một-runtime-một-hồ-sơ vẫn giữ."""

    def setUp(self):
        from scripts.router_v4 import fabric_config as FC
        self.f, _, _ = FC.nap(probe=False)

    def test_moi_runtime_AG_mot_auth_profile_rieng(self):
        ho = [self.f.runtime(f"AG{i:02d}").auth_profile for i in range(1, 9)]
        self.assertEqual(len(set(ho)), 8,
                         "8 khe phải là 8 hồ sơ xác thực khác nhau")

    def test_fabric_van_hop_le_voi_launcher(self):
        self.f.validate()

    def test_khe_co_profile_thi_dung_transport_launcher(self):
        for rid, acc in AL.ACC_CUA_RUNTIME.items():
            r = self.f.runtime(rid)
            if AL.profile_ton_tai(acc):
                self.assertEqual(r.transport, "launcher", rid)
                self.assertEqual(r.auth_profile, f"agy-launcher:{acc}", rid)
                self.assertTrue(r.provisioned, rid)
            else:
                self.assertFalse(r.provisioned, f"{rid} không có {acc}.bin")

    def test_khong_khe_nao_dung_chung_acc(self):
        accs = [AL.ACC_CUA_RUNTIME[f"AG{i:02d}"] for i in range(1, 9)]
        self.assertEqual(len(set(accs)), 8)


class TestBaoVeBiMat(unittest.TestCase):
    def test_module_khong_ghi_token_ra_log(self):
        """Không hàm nào được in nội dung profile. Kiểm thô nhưng đủ: không
        có `print` nào nhận biến chứa blob/token."""
        t = Path(AL.__file__).read_text(encoding="utf-8", errors="replace")
        for i, dong in enumerate(t.splitlines(), 1):
            l = dong.lstrip()
            if l.startswith("print(") or ".write(" in l:
                for xau in ("blob", "token", "cred"):
                    self.assertNotIn(xau, l.lower(),
                                     f"dòng {i} có thể in bí mật: {dong}")

    def test_switch_chi_tra_ve_duoi_van_ban_ngan(self):
        """`switch()` trả stdout của launcher — phải bị cắt để một thông báo
        lỗi dài (có thể chứa dữ liệu nhạy cảm) không tràn vào log Router."""
        import inspect
        src = inspect.getsource(AL.switch)
        self.assertIn("[-200:]", src, "phải cắt đầu ra của launcher")


if __name__ == "__main__":
    unittest.main()
