"""
Kiem tra bo tep trien khai worker (`deploy/fanfic-worker*`).

Day khong phai test hinh thuc. Moi rang buoc o duoi deu la mot cach hong CU THE
ma khong ai phat hien duoc tu ben ngoai:

  * `TimeoutStopSec` <= thoi gian an han -> systemd SIGKILL dung luc worker dang
    cho job cuoi ket thuc. Nhin tu ngoai thi `systemctl restart` van "thanh
    cong"; chi co mot job bi giet giua chung va phai cho het lease.
  * Thieu `--require-env staging` -> worker im lang xu ly job cua moi truong
    khac neu tep secret bi thay.
  * Mot gia tri secret lot vao tep unit -> `systemctl show` in ra, va tep unit
    thi nam trong git.

Tep unit khong chay duoc tren Windows nen doc thang noi dung; do la CHU Y — cai
can khoa la noi dung, khong phai hanh vi cua systemd.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from server import main as server_main
from server import worker as server_worker

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
UNIT = DEPLOY / "fanfic-worker.service"
HEALTH = DEPLOY / "fanfic-worker-health.service"
TIMER = DEPLOY / "fanfic-worker-health.timer"
MAU_ENV = DEPLOY / "fanfic-worker.env.example"


def doc(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def khoa(noi_dung: str, ten: str) -> str:
    """Gia tri cua `ten=` cuoi cung trong tep unit."""
    tim = re.findall(rf"^{ten}=(.*)$", noi_dung, flags=re.MULTILINE)
    return tim[-1].strip() if tim else ""


def giay(gia_tri: str) -> int:
    """`150`, `150s`, `2min` -> so giay."""
    gia_tri = gia_tri.strip()
    if gia_tri.endswith("min"):
        return int(gia_tri[:-3]) * 60
    return int(gia_tri.rstrip("s"))


class TepTrienKhaiTonTai(unittest.TestCase):
    def test_du_bon_tep(self) -> None:
        for p in (UNIT, HEALTH, TIMER, MAU_ENV):
            self.assertTrue(p.is_file(), f"thiếu {p.name}")


class DungSachDuocThat(unittest.TestCase):
    """Rang buoc quan trong nhat, va la cai de pha nhat khi chinh tay."""

    def test_timeout_dai_hon_thoi_gian_an_han(self) -> None:
        t = giay(khoa(doc(UNIT), "TimeoutStopSec"))
        self.assertGreater(
            t, server_worker.GRACE_SECONDS,
            f"TimeoutStopSec={t}s không được nhỏ hơn hoặc bằng thời gian ân hạn "
            f"{server_worker.GRACE_SECONDS}s — systemd sẽ SIGKILL đúng lúc worker "
            "đang chờ job cuối kết thúc")

    def test_dung_bang_sigterm(self) -> None:
        # Worker chi bat SIGINT/SIGTERM. Tin hieu khac la giet thang.
        self.assertEqual(khoa(doc(UNIT), "KillSignal"), "SIGTERM")


class TuLenLaiVaTuKhoiDong(unittest.TestCase):
    def test_tu_chay_sau_reboot(self) -> None:
        self.assertIn("WantedBy=multi-user.target", doc(UNIT))

    def test_tu_restart_khi_crash(self) -> None:
        self.assertEqual(khoa(doc(UNIT), "Restart"), "always")

    def test_loi_cau_hinh_thi_dung_han_chu_khong_quay_vong(self) -> None:
        # `chay()` tra ve 2 khi FAS_ENV khong khop. Restart mai khong chua duoc
        # mot tep cau hinh sai, chi lam log ngap.
        self.assertEqual(khoa(doc(UNIT), "RestartPreventExitStatus"), "2")

    def test_co_tran_so_lan_restart(self) -> None:
        self.assertTrue(khoa(doc(UNIT), "StartLimitBurst"))


class ChongTroNhamTaiNguyen(unittest.TestCase):
    def test_unit_chay_kem_require_env(self) -> None:
        self.assertIn("--require-env staging", khoa(doc(UNIT), "ExecStart"))

    def test_mau_env_dat_staging(self) -> None:
        self.assertIn("FAS_ENV=staging", doc(MAU_ENV))

    def test_worker_khong_chay_inline(self) -> None:
        self.assertIn("FAS_INLINE_WORKER=false", doc(MAU_ENV))


class SecretKhongNamTrongGit(unittest.TestCase):
    #: Ten bien mang gia tri bi mat. Trong tep unit va tep mau, chung chi duoc
    #: xuat hien voi gia tri RONG.
    BIEN_MAT = ("APPWRITE_API_KEY", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "APPWRITE_PROJECT_ID", "APPWRITE_DATABASE_ID", "R2_ACCOUNT_ID",
                "R2_BUCKET", "APPWRITE_ENDPOINT")

    def test_tep_unit_khong_co_bien_mat_nao(self) -> None:
        noi_dung = doc(UNIT) + doc(HEALTH)
        for ten in self.BIEN_MAT:
            self.assertNotIn(
                f"Environment={ten}", noi_dung,
                f"{ten} không được đặt trong tệp unit — `systemctl show` in ra hết")

    def test_mau_env_de_trong_moi_gia_tri(self) -> None:
        for dong in doc(MAU_ENV).splitlines():
            dong = dong.strip()
            if dong.startswith("#") or "=" not in dong:
                continue
            ten, _, gia_tri = dong.partition("=")
            if ten.strip() in self.BIEN_MAT:
                self.assertEqual(
                    gia_tri.strip(), "",
                    f"{ten} trong tệp mẫu phải để trống")

    def test_secret_den_tu_tep_ngoai_repo(self) -> None:
        self.assertIn("EnvironmentFile=/etc/fanfic-audio/worker.env", doc(UNIT))


class HealthcheckDungCach(unittest.TestCase):
    def test_goi_dung_lenh_check(self) -> None:
        self.assertIn("-m server.worker --check", khoa(doc(HEALTH), "ExecStart"))

    def test_khong_kiem_tra_khi_worker_dung_co_chu_y(self) -> None:
        # Khong co `Requisite=` thi moi lan bao tri se tu bat worker lai ngay
        # sau lung nguoi van hanh.
        self.assertIn("Requisite=fanfic-worker.service", doc(HEALTH))

    def test_chu_ky_kiem_tra_du_day_so_voi_nguong_nhip_cu(self) -> None:
        chu_ky = giay(khoa(doc(TIMER), "OnUnitActiveSec"))
        # Kiem tra thua hon nguong thi worker treo co the nam im rat lau.
        self.assertLessEqual(
            chu_ky, server_worker.STALE_SECONDS * 3,
            f"kiểm tra mỗi {chu_ky}s là quá thưa so với ngưỡng nhịp cũ "
            f"{server_worker.STALE_SECONDS}s")


class LeaseVaNhipVanHopLe(unittest.TestCase):
    """Bat bien nay duoc cuong che luc `server.main` duoc nap."""

    def test_lease_dai_hon_ba_chu_ky_nhip(self) -> None:
        self.assertGreaterEqual(server_main.JOB_LEASE_SECONDS,
                                server_main.JOB_HEARTBEAT_SECONDS * 3)

    def test_tai_lieu_ghi_dung_hai_bien_dieu_chinh(self) -> None:
        mau = doc(MAU_ENV)
        self.assertIn("FAS_JOB_LEASE_SECONDS", mau)
        self.assertIn("FAS_JOB_HEARTBEAT_SECONDS", mau)


if __name__ == "__main__":
    unittest.main()
