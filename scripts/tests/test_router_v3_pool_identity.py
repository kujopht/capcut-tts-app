"""Bất biến danh tính — khe cố định, cấm xoay tài khoản.

Đây là các bài kiểm KHOÁ LẠI kết luận đo được ngày 2026-09-03: trên Windows
một hồ sơ người dùng = một Credential Manager = một tài khoản Antigravity.
Nếu ai đó về sau nới lỏng `validate_pool` để "cho tiện", các bài này vỡ.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.router_v3.pool import identity as I


def _ag(worker_id: str, realm: str, **kw) -> I.Identity:
    kw.setdefault("model", "gemini-3.8-flash-high")
    return I.Identity(worker_id=worker_id, provider="antigravity",
                      transport=I.Transport.NATIVE, auth_realm=realm, **kw)


class TestKheTaiKhoan(unittest.TestCase):
    def test_be_mac_dinh_hop_le(self):
        ds = I.mac_dinh()
        I.validate_pool(ds)                      # khong duoc nem
        ten = [d.worker_id for d in ds]
        for slot in I.AG_SLOTS:
            self.assertIn(slot, ten, f"thiếu khe cố định {slot}")

    def test_tam_khe_ag_deu_co_mat_ke_ca_khi_chua_cap_phat(self):
        ds = {d.worker_id: d for d in I.mac_dinh()}
        for slot in I.AG_SLOTS:
            self.assertTrue(ds[slot].account_slot,
                            f"{slot} phải là KHE TÀI KHOẢN, không phải làn")

    def test_hai_khe_cung_realm_bi_tu_choi(self):
        with self.assertRaises(I.IdentityError) as ctx:
            I.validate_pool([_ag("AG01", "windows-user:x"),
                             _ag("AG02", "windows-user:x")])
        self.assertIn("auth_realm", str(ctx.exception))

    def test_khe_chua_cap_phat_khong_chiem_realm(self):
        # Hai khe CHUA cap phat khong the dung nhau vi khong khe nao chay.
        I.validate_pool([
            _ag("AG03", "windows-user:x", needs_provisioning="chưa có hồ sơ"),
            _ag("AG04", "windows-user:x", needs_provisioning="chưa có hồ sơ"),
        ])

    def test_thieu_auth_realm_bi_tu_choi(self):
        with self.assertRaises(I.IdentityError):
            _ag("AGX", "").validate()


class TestLanTrenTaiKhoan(unittest.TestCase):
    def test_lan_phai_khai_lane_of(self):
        with self.assertRaises(I.IdentityError) as ctx:
            _ag("AGX", "windows-user:x", account_slot=False).validate()
        self.assertIn("lane_of", str(ctx.exception))

    def test_lan_tro_toi_khe_khong_ton_tai_bi_tu_choi(self):
        with self.assertRaises(I.IdentityError):
            I.validate_pool([_ag("AGX", "windows-user:x", account_slot=False,
                                 lane_of="KHONG_CO")])

    def test_lan_khai_realm_khac_khe_chu_bi_tu_choi(self):
        """Cửa sau nguy hiểm nhất: đặt account_slot=False rồi khai một realm
        khác để né kiểm trùng. Phải bị chặn."""
        with self.assertRaises(I.IdentityError) as ctx:
            I.validate_pool([
                _ag("AG01", "windows-user:a"),
                _ag("AGFAKE", "windows-user:b", account_slot=False,
                    lane_of="AG01"),
            ])
        self.assertIn("giả làm làn", str(ctx.exception))

    def test_lan_khong_duoc_tro_toi_lan_khac(self):
        with self.assertRaises(I.IdentityError):
            I.validate_pool([
                _ag("AG01", "windows-user:a"),
                _ag("L1", "windows-user:a", account_slot=False, lane_of="AG01"),
                _ag("L2", "windows-user:a", account_slot=False, lane_of="L1"),
            ])

    def test_dem_tai_khoan_khong_tinh_lan(self):
        ds = I.mac_dinh()
        dem = I.dem_tai_khoan(ds)
        # AG01 la khe AG duy nhat da cap phat; AG01_MED/AG_OPUS/AG_GPTOSS la lan.
        self.assertEqual(dem.get("antigravity"), 1,
                         "làn model bị đếm nhầm thành tài khoản")


class TestCamXoayTaiKhoan(unittest.TestCase):
    def test_chan_ten_cong_cu_xoay(self):
        for xau in ("python agy_profile.py 3", "acc.cmd save 2",
                    "advapi32.CredWriteW", "saved_profiles/acc1.bin",
                    "target gemini:antigravity"):
            with self.subTest(xau=xau):
                with self.assertRaises(I.IdentityError):
                    I.assert_khong_xoay_tai_khoan(xau)

    def test_van_ban_binh_thuong_khong_bi_chan(self):
        I.assert_khong_xoay_tai_khoan("windows-user:AG02",
                                      "hồ sơ Windows riêng, credential riêng")

    def test_nap_tu_choi_tep_cau_hinh_co_cong_cu_xoay(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "identities.json"
            p.write_text(json.dumps({"identities": [
                {"worker_id": "AG01", "provider": "antigravity",
                 "transport": "native", "auth_realm": "windows-user:x",
                 "notes": "chạy acc.cmd 2 trước khi dùng"}]}),
                encoding="utf-8")
            with self.assertRaises(I.IdentityError):
                I.nap(p)


class TestVongDoiCauHinh(unittest.TestCase):
    def test_ghi_roi_nap_lai_giu_nguyen(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "identities.json"
            goc = I.mac_dinh()
            I.ghi(goc, p)
            lai = I.nap(p)
            self.assertEqual([x.worker_id for x in goc],
                             [x.worker_id for x in lai])
            self.assertEqual([x.account_slot for x in goc],
                             [x.account_slot for x in lai])
            self.assertEqual([x.lane_of for x in goc], [x.lane_of for x in lai])

    def test_cau_hinh_cu_khong_co_account_slot_van_nap_duoc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "identities.json"
            p.write_text(json.dumps({"identities": [
                {"worker_id": "AG01", "provider": "antigravity",
                 "transport": "native", "auth_realm": "windows-user:x"}]}),
                encoding="utf-8")
            ds = I.nap(p)
            self.assertTrue(ds[0].account_slot)

    def test_to_spec_mang_theo_auth_realm_va_model(self):
        s = _ag("AG01", "windows-user:x").to_spec()
        self.assertEqual(s.auth_realm, "windows-user:x")
        self.assertEqual(s.model, "gemini-3.8-flash-high")
        s.validate()


if __name__ == "__main__":
    unittest.main()
