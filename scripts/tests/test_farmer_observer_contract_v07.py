"""HỢP ĐỒNG giữa ảnh chụp quan sát của farmer và bộ đọc của Router.

Bản đề xuất `docs/deploy/fanfic_farmer_observer/observer.py` nằm ở kho Router
nhưng sẽ chạy ở kho Fanfic. Bộ kiểm này giữ hai đầu khớp nhau, và quan trọng
hơn: chứng minh ảnh chụp KHÔNG mang văn bản lỗi thô — thứ khiến `status.json`
không nới quyền được.

Nó dựng đầu vào GIỐNG THẬT: hình dạng `FarmerStatus.as_dict()` của
`server/farmer/metrics.py`, gồm cả hai đường văn bản tự do có thật
(`archive.detail` <- stderr rclone, `lanes[*].errors[]` <- ngoại lệ).
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from scripts.control_center import probe_van_hanh as PV

#: Trỏ vào MODULE THẬT đang chạy trên production, không vào một bản sao.
#:
#: Bản đầu trỏ vào `docs/deploy/fanfic_farmer_observer/observer.py` — một bản
#: chép, vì lúc đó mã chưa được phép vào cây Fanfic. Sau khi
#: `feat/farmer-sanitized-observability` vào `main`, giữ hai bản giống hệt
#: nhau là đúng cách để chúng lệch nhau — nên bản chép đã bị xoá và bài kiểm
#: hợp đồng nay soi thẳng thứ thật sự được triển khai.
_DUONG = (Path(__file__).resolve().parents[2] / "server" / "farmer"
          / "observer.py")


def _nap_observer():
    spec = importlib.util.spec_from_file_location("_farmer_observer", _DUONG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OB = _nap_observer()

#: Bí mật giả, đúng hình dạng thật, để chứng minh không lọt.
TOKEN = "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
AWS = "AKIAIOSFODNN7EXAMPLE"

STATUS_THAT = {
    "schema_version": 1,
    "started_at": "2026-09-08T15:55:31+00:00",
    "updated_at": "2026-09-11T10:00:00+00:00",
    "round": {"number": 214, "started_at": "2026-09-11T09:59:00+00:00",
              "seconds": 41.2},
    "healthy": True,
    "unhealthy_reason": "",
    "lanes": {
        "A": {"discovered": 7, "deduped": 2, "reviewed": 5, "approved": 3,
              "rejected": 2, "produced": 3, "published_candidates": 3,
              "blocked_no_cover": 0, "review_pending": 1, "resumed": 0,
              "audio_attached": 2, "archived": 2, "archive_pending": 1,
              "failed": 1, "skipped_quota": 0,
              # Duong van ban tu do THU HAI — ngoai le bat ky.
              "errors": [f"HttpError 401: invalid_grant token={TOKEN}"]},
        "B": {"discovered": 0, "produced": 0, "errors": []},
    },
    "quotas": {"daily_remaining": 40},
    "archive": {
        "remote": "gdrive",
        "root": "gdrive:FanficWorld/production",
        "legacy_root_untouched": "gdrive:FanficWorld/archive",
        "enabled": True, "rclone_installed": True, "reachable": False,
        "status": "ARCHIVE_PENDING",
        # Duong van ban tu do THU NHAT — stderr tho cua rclone.
        "detail": (f"Failed to copy: googleapi: Error 403: Rate Limit "
                   f"Exceeded, userRateLimitExceeded key={AWS}"),
    },
    "integrity": {"ok": True, "interpreter": "/opt/fanfic-audio/.venv/bin/python"},
    "serving_cover": {"known_gap": True},
    "totals": {"produced": 1180, "archived": 1170},
}


class TestKhongRoBiMat(unittest.TestCase):

    def test_van_ban_loi_THO_khong_bao_gio_di_ra(self):
        anh = OB.build_snapshot(STATUS_THAT)
        tho = json.dumps(anh, ensure_ascii=False)
        for xau in (TOKEN, AWS, "invalid_grant token=", "googleapi",
                    "userRateLimitExceeded", "HttpError"):
            with self.subTest(xau=xau):
                self.assertNotIn(xau, tho)

    def test_loi_thanh_MA_LOP_chu_khong_mat_han(self):
        anh = OB.build_snapshot(STATUS_THAT)
        # stderr rclone noi "Rate Limit Exceeded" -> quota_exceeded
        self.assertEqual(anh["archive"]["last_error_class"], "quota_exceeded")
        # errors[] cua lane A noi "invalid_grant" -> auth_invalid_grant
        self.assertEqual(anh["lanes"]["A"]["last_error_class"],
                         "auth_invalid_grant")
        self.assertEqual(anh["lanes"]["A"]["error_count"], 1)
        self.assertEqual(anh["lanes"]["B"]["last_error_class"], "")

    def test_KHONG_xuat_duong_dan_trinh_thong_dich_hay_truong_la(self):
        anh = OB.build_snapshot(STATUS_THAT)
        tho = json.dumps(anh, ensure_ascii=False)
        self.assertNotIn("/opt/fanfic-audio/.venv", tho)
        self.assertNotIn("serving_cover", anh)
        self.assertEqual(set(anh["integrity"]), {"ok"})

    def test_chi_xuat_BI_DANH_remote_khong_xuat_cau_hinh(self):
        anh = OB.build_snapshot(STATUS_THAT)
        self.assertEqual(anh["archive"]["remote_alias"], "gdrive")
        self.assertEqual(anh["archive"]["root"],
                         "gdrive:FanficWorld/production")
        self.assertNotIn("rclone.conf", json.dumps(anh, ensure_ascii=False))

    def test_moi_lop_loi_deu_nam_trong_bo_DONG(self):
        for tho in ("invalid_grant", "429 rate limit", "permission denied",
                    "404 not found", "timed out", "connection reset",
                    "thu gi do la", ""):
            with self.subTest(tho=tho):
                self.assertIn(OB.classify_error(tho), OB.ERROR_CLASSES)

    def test_co_loi_ma_khong_phan_loai_duoc_thi_unknown_khong_phai_rong(self):
        self.assertEqual(OB.classify_error("mot loi la hoac"), "unknown")
        self.assertEqual(OB.classify_error(""), "")


class TestHaiDauKhopNhau(unittest.TestCase):

    def test_phien_ban_hop_dong_khop(self):
        self.assertEqual(OB.OBSERVER_SCHEMA_VERSION, PV.TELEMETRY_SCHEMA)

    def test_lop_loi_hai_ben_khop(self):
        self.assertEqual(set(OB.ERROR_CLASSES), set(PV.LOP_LOI))

    def test_ROUTER_khong_bo_truong_nao_cua_ANH_CHUP(self):
        anh = OB.build_snapshot(STATUS_THAT)
        sach, bo = PV.loc_telemetry(anh)
        self.assertEqual(bo, [], f"Router bỏ mất trường: {bo}")
        self.assertEqual(sach["archive"]["remote_alias"], "gdrive")
        self.assertEqual(sach["round"]["number"], 214)

    def test_bo_dem_lane_hai_ben_khop(self):
        self.assertTrue(set(OB.LANE_COUNTERS) <= set(PV.DEM_LANE))

    def test_ROUTER_phan_loai_duoc_tu_anh_chup_that(self):
        anh = OB.build_snapshot(STATUS_THAT,
                                archive_totals={"done": 1170, "pending": 1,
                                                "failed": 0})
        sach, _ = PV.loc_telemetry(anh)
        pl, vi = PV._phan_loai_tu_telemetry(sach)
        # reachable=False + co ma loi -> E (sai remote/duong dan)
        self.assertEqual(pl, "E")
        self.assertTrue(vi)


class TestGhiAnhChup(unittest.TestCase):

    def test_ghi_ra_tep_MODE_644_va_la_JSON_hop_le(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tam:
            p = Path(tam) / "observability.json"
            OB.write_snapshot(OB.build_snapshot(STATUS_THAT), p)
            self.assertTrue(p.is_file())
            json.loads(p.read_text(encoding="utf-8"))
            if os.name != "nt":       # Windows khong co mode POSIX that
                self.assertEqual(p.stat().st_mode & 0o777, 0o644)

    def test_publish_KHONG_NEM_khi_co_su_co(self):
        # Quan sat khong duoc lam chet vong san xuat: `publish` phai nuot
        # moi loi va tra `None`, khong duoc de mot loi ghi tep keo theo ca
        # farmer. Dua vao mot `status` sai kieu de ep loi.
        self.assertIsNone(OB.publish({"round": object()}))


if __name__ == "__main__":
    unittest.main()
