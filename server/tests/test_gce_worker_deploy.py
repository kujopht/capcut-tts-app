"""
Bộ tệp triển khai worker PRODUCTION trên GCE.

Mỗi ràng buộc ở đây là một cách hỏng cụ thể, và phần lớn đều **hỏng lặng lẽ**:

  * `TimeoutStopSec` ≤ thời gian ân hạn → systemd SIGKILL đúng lúc worker đang
    chờ job cuối. Nhìn từ ngoài `systemctl restart` vẫn "thành công".
  * Dùng chung `FAS_VAR_DIR` với staging → hai worker ghi đè tệp nhịp của nhau
    và `--check` của cả hai cùng vô nghĩa.
  * Thiếu `FAS_PIPER_MODELS_DIR` → worker tìm model trong thư mục dữ liệu người
    dùng, không thấy gì, và mọi job Piper hỏng `MODEL_NOT_INSTALLED`.
  * Script cài tự khởi động → worker production bắt đầu nhận job thật ngay
    trong lệnh mà người vận hành tưởng chỉ là "cài".

Đọc thẳng nội dung tệp: unit systemd và script bash không chạy được trên
Windows, và thứ cần khoá là NỘI DUNG chứ không phải hành vi của systemd.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from server import worker as server_worker

GOC = Path(__file__).resolve().parents[2]
UNIT_PROD = GOC / "deploy" / "fanfic-worker-prod.service"
UNIT_STAGING = GOC / "deploy" / "fanfic-worker.service"
INSTALL = GOC / "scripts" / "install_gce_worker.sh"


def doc(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def khoa(noi_dung: str, ten: str) -> str:
    tim = re.findall(rf"^{ten}=(.*)$", noi_dung, flags=re.MULTILINE)
    return tim[-1].strip() if tim else ""


def moi_khoa(noi_dung: str, ten: str):
    return [d.strip() for d in re.findall(rf"^{ten}=(.*)$", noi_dung,
                                          flags=re.MULTILINE)]


def giay(v: str) -> int:
    v = v.strip()
    return int(v[:-3]) * 60 if v.endswith("min") else int(v.rstrip("s"))


class TepTonTai(unittest.TestCase):
    def test_du_hai_tep(self) -> None:
        for p in (UNIT_PROD, INSTALL):
            self.assertTrue(p.is_file(), f"thiếu {p.name}")


class TachHoanToanKhoiStaging(unittest.TestCase):
    """Hai worker chạy cùng máy được, nhưng chỉ khi KHÔNG dùng chung trạng thái."""

    def setUp(self) -> None:
        self.prod = doc(UNIT_PROD)
        self.stg = doc(UNIT_STAGING)

    def test_require_env_la_production(self) -> None:
        self.assertIn("--require-env production", khoa(self.prod, "ExecStart"))
        self.assertIn("--require-env staging", khoa(self.stg, "ExecStart"))

    def test_FAS_VAR_DIR_khac_staging(self) -> None:
        """Tệp nhịp lấy từ `var_dir`. Dùng chung là ghi đè nhịp của nhau."""
        env_prod = [e for e in moi_khoa(self.prod, "Environment")
                    if e.startswith("FAS_VAR_DIR=")]
        self.assertEqual(len(env_prod), 1, "production phải đặt FAS_VAR_DIR")
        duong_prod = env_prod[0].split("=", 1)[1]
        self.assertNotIn(duong_prod, self.stg,
                         "production dùng chung FAS_VAR_DIR với staging")

    def test_StateDirectory_khac_nhau(self) -> None:
        self.assertNotEqual(khoa(self.prod, "StateDirectory"),
                            khoa(self.stg, "StateDirectory"))

    def test_EnvironmentFile_khac_nhau(self) -> None:
        self.assertNotEqual(khoa(self.prod, "EnvironmentFile"),
                            khoa(self.stg, "EnvironmentFile"))

    def test_ReadWritePaths_tro_dung_StateDirectory_cua_no(self) -> None:
        self.assertIn(khoa(self.prod, "StateDirectory"),
                      khoa(self.prod, "ReadWritePaths"))


class CauHinhModel(unittest.TestCase):

    def test_dat_FAS_PIPER_MODELS_DIR(self) -> None:
        env = [e for e in moi_khoa(doc(UNIT_PROD), "Environment")
               if e.startswith("FAS_PIPER_MODELS_DIR=")]
        self.assertEqual(len(env), 1)
        self.assertTrue(env[0].split("=", 1)[1].startswith("/"),
                        "phải là đường dẫn tuyệt đối")

    def test_ten_bien_khop_voi_thu_ma_nguon_doc(self) -> None:
        """Đặt sai tên biến thì worker im lặng tìm nhầm chỗ."""
        from desktop_app.providers.piper_models import MODELS_DIR_ENV

        self.assertIn(f"Environment={MODELS_DIR_ENV}=", doc(UNIT_PROD))

    def test_khong_cho_worker_ghi_vao_thu_muc_model(self) -> None:
        """Worker chỉ đọc model. Quyền ghi là mở đường sửa model khi bị chiếm."""
        noi_dung = doc(UNIT_PROD)
        models = [e.split("=", 1)[1] for e in moi_khoa(noi_dung, "Environment")
                  if e.startswith("FAS_PIPER_MODELS_DIR=")][0]
        self.assertNotIn(models, khoa(noi_dung, "ReadWritePaths"))


class DungSachVaTuHoiPhuc(unittest.TestCase):

    def setUp(self) -> None:
        self.prod = doc(UNIT_PROD)

    def test_timeout_dai_hon_thoi_gian_an_han(self) -> None:
        t = giay(khoa(self.prod, "TimeoutStopSec"))
        self.assertGreater(
            t, server_worker.GRACE_SECONDS,
            f"TimeoutStopSec={t}s ≤ ân hạn {server_worker.GRACE_SECONDS}s — "
            "systemd sẽ SIGKILL đúng lúc worker đang chờ job cuối")

    def test_dung_bang_SIGTERM(self) -> None:
        self.assertEqual(khoa(self.prod, "KillSignal"), "SIGTERM")

    def test_tu_chay_sau_reboot(self) -> None:
        self.assertIn("WantedBy=multi-user.target", self.prod)

    def test_tu_restart_khi_crash(self) -> None:
        self.assertEqual(khoa(self.prod, "Restart"), "always")

    def test_loi_cau_hinh_thi_dung_han(self) -> None:
        """Mã 2 = FAS_ENV không khớp. Restart mãi không chữa được cấu hình sai."""
        self.assertEqual(khoa(self.prod, "RestartPreventExitStatus"), "2")

    def test_co_tran_so_lan_restart(self) -> None:
        self.assertTrue(khoa(self.prod, "StartLimitBurst"))

    def test_co_do_tre_giua_hai_lan_restart(self) -> None:
        self.assertTrue(khoa(self.prod, "RestartSec"))


class AnToanVanHanh(unittest.TestCase):
    """Task F — rà soát bảo mật/vận hành."""

    def setUp(self) -> None:
        self.prod = doc(UNIT_PROD)
        self.sh = doc(INSTALL)

    def test_khong_chay_bang_root(self) -> None:
        u = khoa(self.prod, "User")
        self.assertTrue(u)
        self.assertNotEqual(u, "root")

    def test_khong_ghi_cung_ten_dang_nhap_cua_VM(self) -> None:
        """Ghi cứng tên người vận hành thì hỏng khi đổi người hoặc đổi VM."""
        self.assertEqual(khoa(self.prod, "User"), "fanfic")

    def test_secret_den_tu_tep_ngoai_repo(self) -> None:
        self.assertTrue(khoa(self.prod, "EnvironmentFile").startswith("/etc/"))

    def test_khong_bien_bi_mat_nao_trong_unit(self) -> None:
        """`systemctl show` in ra mọi `Environment=`, và unit thì nằm trong git."""
        for cam in ("APPWRITE_API_KEY", "R2_ACCESS_KEY_ID",
                    "R2_SECRET_ACCESS_KEY", "APPWRITE_PROJECT_ID",
                    "R2_BUCKET", "APPWRITE_ENDPOINT"):
            self.assertNotIn(f"Environment={cam}", self.prod)

    def test_co_rao_chan_quyen(self) -> None:
        for co in ("NoNewPrivileges=true", "ProtectSystem=strict",
                   "ProtectHome=true", "PrivateTmp=true"):
            self.assertIn(co, self.prod)

    def test_worker_khong_mo_cong(self) -> None:
        """Không cần inbound HTTP, nên VM không phải mở 80/443 cho nó."""
        for cam in ("ListenStream", "healthCheckPath", "Sockets="):
            self.assertNotIn(cam, self.prod)

    def test_log_qua_journal(self) -> None:
        self.assertEqual(khoa(self.prod, "StandardOutput"), "journal")
        self.assertEqual(khoa(self.prod, "StandardError"), "journal")


class ScriptCaiDat(unittest.TestCase):

    def setUp(self) -> None:
        self.sh = doc(INSTALL)

    def test_khong_tu_khoi_dong_khi_chi_install_only(self) -> None:
        """
        Khởi động worker production nghĩa là nó bắt đầu nhận job THẬT và ghi
        vào Appwrite/R2 production. Không được nằm sau cùng một lệnh với "cài".
        """
        # So THU TU, khong cat cua so co dinh: cua so dai qua se tran sang
        # nhanh `--enable-and-start` ngay ben duoi va bat nham chinh no.
        bat_dau = self.sh.index('CHE_DO" == "install"')
        thoat = self.sh.index("exit 0", bat_dau)
        for lenh in ("systemctl start", "systemctl restart", "systemctl enable"):
            vi_tri = self.sh.find(lenh, bat_dau)
            self.assertTrue(
                vi_tri == -1 or vi_tri > thoat,
                f"{lenh!r} nam TRUOC `exit 0` cua nhanh --install-only")

    def test_khong_lam_gi_khi_khong_co_tham_so(self) -> None:
        self.assertIn("Phải chọn MỘT trong hai", self.sh)

    def test_KHONG_tao_hay_sua_secret(self) -> None:
        # Chỉ được ĐỌC tệp env để kiểm tra, không bao giờ ghi.
        self.assertNotIn("> $ENV_FILE", self.sh)
        self.assertNotIn('> "$ENV_FILE"', self.sh)
        self.assertNotIn("tee $ENV_FILE", self.sh)

    def test_kiem_du_cac_phu_thuoc(self) -> None:
        for can in ("ffmpeg", "piper", "VENV_PY", "MODELS_DIR", "ENV_FILE"):
            self.assertIn(can, self.sh, f"script không kiểm {can}")

    def test_goi_validator_model(self) -> None:
        self.assertIn("validate_nghitts_models.py", self.sh)

    def test_dung_lai_khi_co_muc_hong(self) -> None:
        self.assertIn("DỪNG: còn mục HỎNG", self.sh)
        self.assertIn("exit 1", self.sh)

    def test_idempotent_khong_ghi_de_vo_ich(self) -> None:
        """Chạy lại không được ghi lại unit khi nội dung không đổi."""
        self.assertIn("cmp -s", self.sh)

    def test_tao_nguoi_dung_khong_login_duoc(self) -> None:
        self.assertIn("--shell /usr/sbin/nologin", self.sh)
        self.assertIn("--system", self.sh)

    def test_nhac_quyen_600_cho_tep_env(self) -> None:
        self.assertIn("600", self.sh)


if __name__ == "__main__":
    unittest.main()
