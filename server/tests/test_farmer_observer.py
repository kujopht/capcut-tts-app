"""Kiem thu ANH CHUP QUAN SAT DA LOC cho Router Control Center.

Vi sao lop nay ton tai: `status.json` phan lon an toan, nhung no co HAI
duong van ban tu do cua ben thu ba chay thang vao:

    archive.detail    <- proc.stderr THO cua rclone (drive_archive.probe)
    lanes[*].errors[] <- msg[:300] cua mot ngoai le bat ky (note_error)

Hai ong dan mo do lam `status.json` KHONG chung minh duoc la sach, nen no
khong duoc noi quyen. `observer.py` giai bai toan bang mot DANH SACH CHO
PHEP rieng, va van ban loi bi quy ve mot MA LOP LOI dong.

Bat bien duoc khoa lai o day:

    - dau ra chi gom sieu du lieu van hanh, khong mot chu bi mat nao
    - `rclone.conf` khong bao gio bi doc/phoi
    - `status.json` THO khong bao gio di ra ngoai
    - ngu nghia discovered / deduped / produced duoc giu dung
    - quan sat HONG thi vong san xuat VAN CHAY
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from server.farmer.metrics import FarmerStatus, LaneMetrics, MetricsWriter
from server.farmer.observer import (
    ERROR_CLASSES, LANE_COUNTERS, OBSERVER_MODE, OBSERVER_SCHEMA_VERSION,
    build_snapshot, classify_error, observer_path, publish, write_snapshot,
)

#: Bi mat GIA, dung hinh dang that, de chung minh khong lot.
TOKEN_GOOGLE = "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
KHOA_AWS = "AKIAIOSFODNN7EXAMPLE"
REFRESH = "1//0eXxXxXxXxXxXxXxXxXxXxXxXx"


def status_that() -> dict:
    """Hinh dang THAT cua `FarmerStatus.as_dict()`, co ca hai ong dan mo."""
    lane_a = LaneMetrics(discovered=7, deduped=2, reviewed=5, approved=3,
                         rejected=2, produced=3, published_candidates=3,
                         review_pending=1, audio_attached=2, archived=2,
                         archive_pending=1, failed=1)
    lane_a.note_error(f"HttpError 401: invalid_grant token={TOKEN_GOOGLE}")
    lane_b = LaneMetrics(discovered=2, deduped=2)
    st = FarmerStatus(
        started_at="2026-09-08T15:55:31+00:00",
        updated_at="2026-09-11T10:00:00+00:00",
        round_number=214, round_started_at="2026-09-11T09:59:00+00:00",
        round_seconds=41.2, healthy=True, unhealthy_reason="",
        lanes={"text": lane_a.as_dict(), "audio": lane_b.as_dict()},
        quotas={"daily_remaining": 40},
        archive={
            "remote": "fanfic-gdrive",
            "root": "fanfic-gdrive:FanficWorld/production",
            "legacy_root_untouched": "fanfic-gdrive:FanficWorld/archive",
            "enabled": True, "rclone_installed": True, "reachable": False,
            "status": "ARCHIVE_PENDING",
            # stderr THO cua rclone — dung cho nguy hiem nhat
            "detail": (f"Failed to copy: googleapi: Error 403: Rate Limit "
                       f"Exceeded key={KHOA_AWS} refresh={REFRESH}"),
        },
        integrity={"ok": True,
                   "interpreter": "/opt/fanfic-audio/.venv/bin/python"},
        serving_cover={"known_gap": True},
        totals={"discovered": 9, "deduped": 4, "produced": 3, "archived": 2},
    )
    return st.as_dict()


class TestKhongRoBiMat(unittest.TestCase):

    def setUp(self):
        self.anh = build_snapshot(status_that())
        self.tho = json.dumps(self.anh, ensure_ascii=False)

    def test_van_ban_loi_THO_khong_bao_gio_di_ra(self):
        for xau in (TOKEN_GOOGLE, KHOA_AWS, REFRESH, "googleapi",
                    "Rate Limit Exceeded", "HttpError", "invalid_grant token"):
            with self.subTest(xau=xau[:24]):
                self.assertNotIn(xau, self.tho)

    def test_loi_thanh_MA_LOP_chu_khong_mat_han(self):
        # Mat han cung sai: mot su co that se bi giau.
        self.assertEqual(self.anh["archive"]["last_error_class"],
                         "quota_exceeded")
        self.assertEqual(self.anh["lanes"]["text"]["last_error_class"],
                         "auth_invalid_grant")
        self.assertEqual(self.anh["lanes"]["text"]["error_count"], 1)
        self.assertEqual(self.anh["lanes"]["audio"]["last_error_class"], "")

    def test_moi_ma_lop_loi_deu_nam_trong_bo_DONG(self):
        for tho in ("invalid_grant", "429 rate limit", "permission denied",
                    "404 not found", "timed out", "connection reset",
                    "mot loi la hoac", ""):
            with self.subTest(tho=tho):
                self.assertIn(classify_error(tho), ERROR_CLASSES)

    def test_co_loi_ma_chua_phan_loai_duoc_thi_unknown_KHONG_phai_rong(self):
        # "co loi nhung chua biet loai" != "khong co loi". Gop lai la giau
        # mot su co.
        self.assertEqual(classify_error("mot loi hoan toan la"), "unknown")
        self.assertEqual(classify_error(""), "")

    def test_KHONG_xuat_duong_trinh_thong_dich_hay_truong_la(self):
        self.assertNotIn("/opt/fanfic-audio/.venv", self.tho)
        self.assertNotIn("serving_cover", self.anh)
        self.assertEqual(set(self.anh["integrity"]), {"ok"})

    def test_khoa_cap_MOT_dung_danh_sach_cho_phep(self):
        self.assertEqual(
            set(self.anh),
            {"schema_version", "generated_at", "farmer", "round", "lanes",
             "totals", "quotas", "archive", "integrity"})


class TestRcloneConfKhongBaoGioLoRa(unittest.TestCase):

    def test_anh_chup_chi_neu_BI_DANH_remote(self):
        anh = build_snapshot(status_that())
        self.assertEqual(anh["archive"]["remote_alias"], "fanfic-gdrive")
        self.assertEqual(anh["archive"]["root"],
                         "fanfic-gdrive:FanficWorld/production")

    def test_KHONG_nhac_toi_rclone_conf_o_bat_ky_dau(self):
        tho = json.dumps(build_snapshot(status_that()), ensure_ascii=False)
        self.assertNotIn("rclone.conf", tho)
        self.assertNotIn("[fanfic-gdrive]", tho)   # dang khoi cau hinh rclone

    def test_ma_observer_KHONG_doc_rclone_conf(self):
        # Chi xet DONG MA — phan chu thich/docstring CO nhac `rclone.conf`
        # dung de giai thich vi sao khong phoi no, va do la thu nen giu.
        import ast

        from server.farmer import observer
        nguon = Path(observer.__file__).read_text(encoding="utf-8")
        cay = ast.parse(nguon)
        # Moi hang chuoi trong MA (khong tinh docstring cua module/ham/lop).
        chuoi_ma = []
        docstrings = set()
        for nut in ast.walk(cay):
            if isinstance(nut, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
                d = ast.get_docstring(nut, clean=False)
                if d:
                    docstrings.add(d)
        for nut in ast.walk(cay):
            if isinstance(nut, ast.Constant) and isinstance(nut.value, str):
                if nut.value not in docstrings:
                    chuoi_ma.append(nut.value)
        # Bat bien: khong hang chuoi nao trong MA tro toi TEP CAU HINH rclone
        # hay mot tep `.conf` nao. (`rclone_missing` la mot NHAN lop loi hop
        # le — no khong doc gi ca.)
        for s in chuoi_ma:
            thap = s.lower()
            self.assertNotIn("rclone.conf", thap,
                             f"hang chuoi trong MA tro toi rclone.conf: {s[:60]!r}")
            self.assertNotIn(".conf", thap,
                             f"hang chuoi trong MA tro toi mot tep .conf: {s[:60]!r}")

    def test_KHONG_xuat_goc_legacy(self):
        # `legacy_root_untouched` co trong status.json nhung KHONG can cho
        # quan sat, va cay legacy la thu tuyet doi khong duoc dung toi.
        anh = build_snapshot(status_that())
        self.assertNotIn("legacy_root_untouched", anh["archive"])


class TestStatusJsonThoKhongDiRa(unittest.TestCase):

    def test_anh_chup_KHONG_phai_ban_sao_status_json(self):
        st = status_that()
        anh = build_snapshot(st)
        # Khong mot truong van ban tu do nao cua status.json di sang.
        self.assertNotIn("detail", anh["archive"])
        for lane in anh["lanes"].values():
            self.assertNotIn("errors", lane)

    def test_lane_chi_giu_SO_NGUYEN_va_hai_truong_loi_da_quy_ma(self):
        anh = build_snapshot(status_that())
        for ten, lane in anh["lanes"].items():
            with self.subTest(lane=ten):
                for k, v in lane.items():
                    if k == "last_error_class":
                        self.assertIsInstance(v, str)
                    else:
                        self.assertIn(k, tuple(LANE_COUNTERS) + ("error_count",))
                        self.assertIsInstance(v, int)

    def test_quyen_tep_anh_chup_la_644_chu_khong_phai_600(self):
        # `status.json` la 600 vi `mkstemp` tao 600 roi `os.replace` giu
        # nguyen. Anh chup thi CAN doc duoc, nen phai `chmod` tuong minh.
        self.assertEqual(OBSERVER_MODE, 0o644)
        with tempfile.TemporaryDirectory() as tam:
            p = Path(tam) / "observability.json"
            write_snapshot(build_snapshot(status_that()), p)
            json.loads(p.read_text(encoding="utf-8"))
            if os.name != "nt":
                self.assertEqual(p.stat().st_mode & 0o777, 0o644)


class TestNguNghiaBoDem(unittest.TestCase):
    """discovered / deduped / produced phai giu dung nghia cua farmer."""

    def test_bo_dem_di_qua_nguyen_ven(self):
        anh = build_snapshot(status_that())
        text = anh["lanes"]["text"]
        self.assertEqual(text["discovered"], 7)
        self.assertEqual(text["deduped"], 2)
        self.assertEqual(text["produced"], 3)
        self.assertEqual(text["archived"], 2)
        self.assertEqual(text["archive_pending"], 1)
        self.assertEqual(text["review_pending"], 1)

    def test_totals_di_qua_nguyen_ven(self):
        anh = build_snapshot(status_that())
        self.assertEqual(anh["totals"]["discovered"], 9)
        self.assertEqual(anh["totals"]["deduped"], 4)
        self.assertEqual(anh["totals"]["produced"], 3)

    def test_vong_TOAN_BAN_TRUNG_van_doc_duoc_la_khong_co_viec_moi(self):
        # Do that tren production: discovered=2, deduped=2, produced=0.
        # Router doc thanh "khong co ung vien MOI" (A), khong phai "tac
        # nghen" (D) — va phep tru do chi dung neu hai bo dem nay di qua
        # nguyen ven.
        st = FarmerStatus(lanes={"text": LaneMetrics(discovered=2,
                                                     deduped=2).as_dict()})
        anh = build_snapshot(st.as_dict())
        lane = anh["lanes"]["text"]
        self.assertEqual(lane["discovered"] - lane["deduped"], 0)
        self.assertEqual(lane["produced"], 0)

    def test_archive_totals_do_nguoi_goi_dua_vao(self):
        anh = build_snapshot(status_that(),
                             archive_totals={"done": 11, "pending": 2,
                                             "failed": 0})
        self.assertEqual(anh["archive"]["done"], 11)
        self.assertEqual(anh["archive"]["pending"], 2)
        self.assertEqual(anh["archive"]["failed"], 0)

    def test_thieu_archive_totals_thi_la_0_chu_khong_bia(self):
        anh = build_snapshot(status_that())
        self.assertEqual(anh["archive"]["done"], 0)
        self.assertEqual(anh["archive"]["pending"], 0)

    def test_moc_thoi_gian_archive_de_RONG_chu_khong_bia(self):
        # Farmer chua theo doi hai moc nay. Bia ra mot gia tri "hop ly" se
        # lam Router ket luan sai. Khoang trong DA BIET, giu nguyen o v0.7.
        anh = build_snapshot(status_that())
        self.assertEqual(anh["archive"]["last_attempt_at"], "")
        self.assertEqual(anh["archive"]["last_success_at"], "")


class TestQuanSatHongKhongLamChetFarming(unittest.TestCase):
    """Quan sat la PHU. Hong o day khong duoc keo theo vong san xuat."""

    def test_publish_nuot_moi_loi_va_tra_None(self):
        self.assertIsNone(publish({"round": object()}))

    def test_publish_duong_dan_khong_ghi_duoc_van_khong_nem(self):
        # Cha cua duong dan la mot TEP, nen `mkdir(parents=True)` chac chan
        # hong tren ca Windows lan Linux. (Mot duong kieu `/khong/ton/tai`
        # KHONG dung de thu: tren Windows no la duong theo o dia hien tai va
        # se duoc TAO ra that.)
        with tempfile.TemporaryDirectory() as tam:
            chan = Path(tam) / "toi_la_mot_tep"
            chan.write_text("x", encoding="utf-8")
            cu = os.environ.get("FARMER_OBSERVER_PATH")
            os.environ["FARMER_OBSERVER_PATH"] = str(chan / "z.json")
            try:
                self.assertIsNone(publish(status_that()))
            finally:
                if cu is None:
                    os.environ.pop("FARMER_OBSERVER_PATH", None)
                else:
                    os.environ["FARMER_OBSERVER_PATH"] = cu

    def test_MetricsWriter_write_VAN_tra_status_khi_observer_hong(self):
        # Bat bien quan trong nhat cua tich hop: `write()` phai tra
        # `FarmerStatus` binh thuong ke ca khi anh chup khong ghi duoc.
        with tempfile.TemporaryDirectory() as tam:
            cu = os.environ.get("FARMER_OBSERVER_PATH")
            os.environ["FARMER_OBSERVER_PATH"] = "/khong/ton/tai/x/y/z.json"
            try:
                w = MetricsWriter(Path(tam) / "status.json")
                w.begin_round()
                st = w.write(lanes={"text": LaneMetrics(discovered=1)},
                             quotas={}, round_started=0.0)
                self.assertIsInstance(st, FarmerStatus)
                self.assertEqual(st.lanes["text"]["discovered"], 1)
                # status.json VAN duoc ghi binh thuong
                self.assertTrue((Path(tam) / "status.json").is_file())
            finally:
                if cu is None:
                    os.environ.pop("FARMER_OBSERVER_PATH", None)
                else:
                    os.environ["FARMER_OBSERVER_PATH"] = cu


class TestTichHopMetricsWriter(unittest.TestCase):

    def test_write_sinh_ra_CA_HAI_tep(self):
        with tempfile.TemporaryDirectory() as tam:
            cu = os.environ.get("FARMER_OBSERVER_PATH")
            obs = Path(tam) / "observability.json"
            os.environ["FARMER_OBSERVER_PATH"] = str(obs)
            try:
                w = MetricsWriter(Path(tam) / "status.json")
                w.begin_round()
                w.write(lanes={"text": LaneMetrics(discovered=3, deduped=3,
                                                   archived=0)},
                        quotas={}, round_started=0.0,
                        archive={"remote": "fanfic-gdrive",
                                 "root": "fanfic-gdrive:FanficWorld/production",
                                 "enabled": True, "rclone_installed": True,
                                 "reachable": True, "status": "ARCHIVE_DONE",
                                 "detail": ""})
                self.assertTrue((Path(tam) / "status.json").is_file())
                self.assertTrue(obs.is_file(), "anh chup phai duoc ghi")
                d = json.loads(obs.read_text(encoding="utf-8"))
                self.assertEqual(d["schema_version"], OBSERVER_SCHEMA_VERSION)
                self.assertEqual(d["round"]["number"], 1)
                self.assertEqual(d["lanes"]["text"]["discovered"], 3)
                self.assertEqual(d["archive"]["remote_alias"], "fanfic-gdrive")
                self.assertEqual(d["archive"]["status"], "ARCHIVE_DONE")
            finally:
                if cu is None:
                    os.environ.pop("FARMER_OBSERVER_PATH", None)
                else:
                    os.environ["FARMER_OBSERVER_PATH"] = cu

    def test_duong_dan_mac_dinh_va_bien_moi_truong(self):
        cu = os.environ.get("FARMER_OBSERVER_PATH")
        os.environ.pop("FARMER_OBSERVER_PATH", None)
        try:
            self.assertEqual(str(observer_path()).replace("\\", "/"),
                             "/var/lib/fanfic-farmer/observability.json")
        finally:
            if cu is not None:
                os.environ["FARMER_OBSERVER_PATH"] = cu


class TestHanhViFarmerKhongDoi(unittest.TestCase):
    """Ban va chi THEM mot khoi; moi thu cu phai y nguyen."""

    def test_status_json_giu_nguyen_hinh_dang(self):
        with tempfile.TemporaryDirectory() as tam:
            cu = os.environ.get("FARMER_OBSERVER_PATH")
            os.environ["FARMER_OBSERVER_PATH"] = str(Path(tam) / "o.json")
            try:
                w = MetricsWriter(Path(tam) / "status.json")
                w.begin_round()
                w.write(lanes={"text": LaneMetrics(discovered=1)}, quotas={},
                        round_started=0.0)
                d = json.loads((Path(tam) / "status.json")
                               .read_text(encoding="utf-8"))
            finally:
                if cu is None:
                    os.environ.pop("FARMER_OBSERVER_PATH", None)
                else:
                    os.environ["FARMER_OBSERVER_PATH"] = cu
        # Cac khoa cu cua status.json van con nguyen.
        for k in ("schema_version", "started_at", "updated_at", "round",
                  "healthy", "unhealthy_reason", "lanes", "quotas",
                  "archive", "integrity", "serving_cover", "totals"):
            self.assertIn(k, d)

    def test_totals_van_cong_don_nhu_cu(self):
        with tempfile.TemporaryDirectory() as tam:
            cu = os.environ.get("FARMER_OBSERVER_PATH")
            os.environ["FARMER_OBSERVER_PATH"] = str(Path(tam) / "o.json")
            try:
                w = MetricsWriter(Path(tam) / "status.json")
                for _ in range(3):
                    w.begin_round()
                    w.write(lanes={"text": LaneMetrics(discovered=2)},
                            quotas={}, round_started=0.0)
                st = w.write(lanes={"text": LaneMetrics(discovered=2)},
                             quotas={}, round_started=0.0)
            finally:
                if cu is None:
                    os.environ.pop("FARMER_OBSERVER_PATH", None)
                else:
                    os.environ["FARMER_OBSERVER_PATH"] = cu
        self.assertEqual(st.totals["discovered"], 8)


if __name__ == "__main__":
    unittest.main()
