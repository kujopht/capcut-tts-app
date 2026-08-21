"""
`server/secret_redaction.py` — chan bi mat lot vao log/loi/output.

Test quan trong nhat (`test_tai_hien_su_co_that_apikey_trong_trace_long_nhau`)
tai hien hinh dang response gay ro ri that 2026-08-16 (khong phai NOI DUNG):
mot loi validate 400 cua Appwrite echo lai toan bo tham so request (bao gom
`apiKey`) trong `trace[].args[]`, long nhieu tang.

AN TOAN (2026-08-20, sau su co khoa production bi commit nham vao ban cu cua
chinh file nay): gia tri khoa dung de kiem thu o day la BIA DUNG, TU SINH tu
mot doan lap lai vo hai luc chay module — KHONG PHAI mot khoa Appwrite that,
KHONG BAO GIO dung duoc voi bat ky Appwrite nao (Cloud hay tu luu tru). No chi
can dung DINH DANG "standard_<hex dai>" de khop mau `_MAU_BI_MAT_THEO_GIA_TRI`
trong `secret_redaction.py`, khong can va TUYET DOI KHONG duoc la mot bi mat
that. Xem lich su sua o commit sau su co nay de biet chi tiet.
"""

from __future__ import annotations

import unittest

from server.secret_redaction import (
    loc_bo_de_qui,
    loc_bo_theo_gia_tri,
    thong_diep_loi_an_toan,
)

#: BIA DUNG tu sinh — KHONG PHAI khoa Appwrite that. Ghep tu MOT doan hex 12
#: ky tu lap lai nhieu lan (ro rang khong ngau nhien khi doc bang mat), chi
#: du dai (>=40 ky tu hex sau "standard_") de khop mau phat hien trong
#: `secret_redaction.py`. Dung "standard_" (khong phai "console_") vi day la
#: dinh dang khoa API nguoi dung tao thu cong tren Appwrite, dung hinh dang
#: voi su co 2026-08-16 dang tai hien.
_DOAN_HEX_LAP_LAI = "0a1b2c3d4e5f"
_KHOA_APPWRITE_GIA_LAP = "standard_" + _DOAN_HEX_LAP_LAI * 12


class TaiHienSuCoThatTest(unittest.TestCase):
    def test_tai_hien_su_co_that_apikey_trong_trace_long_nhau(self):
        """Tai hien HINH DANG response loi da gay ro ri that (2026-08-16):
        'message' o dau, nhung 'apiKey' nam sau trong 'trace[1].args[2]' —
        dung cau truc Appwrite 1.9.6 tra ve that. Gia tri `apiKey` ben duoi
        la BIA DUNG (`_KHOA_APPWRITE_GIA_LAP`), khong phai khoa that."""
        body = {
            "message": "Invalid `resources` param: Value must a valid array",
            "code": 400,
            "type": "general_argument_invalid",
            "version": "1.9.6",
            "file": "/usr/src/code/vendor/utopia-php/http/src/Http/Http.php",
            "trace": [
                {
                    "file": "Http.php", "line": 745, "function": "validate",
                    "args": ["resources", {}, [
                        {}, {"projectId": "abc123"},
                        {
                            "migrationId": "unique()",
                            "endpoint": "https://sgp.cloud.appwrite.io/v1",
                            "projectID": "6a749d140018e367bc2f",
                            "apiKey": _KHOA_APPWRITE_GIA_LAP,
                            "resources": ["users", "databases"],
                        },
                        {},
                    ]],
                },
            ],
        }
        ket_qua = loc_bo_de_qui(body)
        chuoi = str(ket_qua)
        self.assertNotIn(_KHOA_APPWRITE_GIA_LAP, chuoi)
        # Cac truong KHONG nhay cam van con nguyen — khong loc qua tay.
        self.assertIn("projectID", str(ket_qua["trace"][0]["args"][2][2]))
        self.assertIn("resources", chuoi)

    def test_thong_diep_loi_an_toan_khong_lo_apikey_qua_message(self):
        """Ngay ca khi 'message' (khong phai mot truong sau) vo tinh chua
        chuoi giong khoa API, van phai bi loc — phong khi Appwrite doi cach
        dinh dang loi trong tuong lai."""
        body = {"message": f"Lỗi xác thực với khoá {_KHOA_APPWRITE_GIA_LAP}"}
        ra = thong_diep_loi_an_toan(body, status_code=401)
        self.assertNotIn(_KHOA_APPWRITE_GIA_LAP, ra)

    def test_thong_diep_loi_an_toan_binh_thuong_khong_bi_anh_huong(self):
        body = {"message": "Không tìm thấy bản ghi."}
        self.assertEqual(thong_diep_loi_an_toan(body, status_code=404),
                         "Không tìm thấy bản ghi.")

    def test_thong_diep_loi_an_toan_khong_co_message_dung_mac_dinh(self):
        self.assertEqual(
            thong_diep_loi_an_toan(None, status_code=500),
            "Appwrite trả về lỗi 500.",
        )


class LocTheoTenTruongTest(unittest.TestCase):
    """Moi loai bi mat nguoi dung liet ke ro: X-Appwrite-Key, Authorization,
    API key, BYOP token, OAuth token, khoa ma hoa, cookie/session."""

    def test_x_appwrite_key(self):
        d = loc_bo_de_qui({"headers": {"X-Appwrite-Key": "sk_thattest123"}})
        self.assertEqual(d["headers"]["X-Appwrite-Key"], "<redacted>")

    def test_authorization_header(self):
        d = loc_bo_de_qui({"headers": {"Authorization": "Bearer abcdef123456"}})
        self.assertEqual(d["headers"]["Authorization"], "<redacted>")

    def test_api_key_ca_hai_kieu_viet(self):
        d = loc_bo_de_qui({"apiKey": "x", "api_key": "y", "apikey": "z"})
        self.assertEqual(d["apiKey"], "<redacted>")
        self.assertEqual(d["api_key"], "<redacted>")
        self.assertEqual(d["apikey"], "<redacted>")

    def test_byop_oauth_token(self):
        d = loc_bo_de_qui({
            "encrypted_access_token": "ciphertext-abc",
            "encrypted_refresh_token": "ciphertext-def",
            "access_token": "raw-token-should-not-happen-but-still-redact",
            "id_token": "eyJhbGciOiJIUzI1NiJ9.xyz.abc",
        })
        self.assertEqual(d["encrypted_access_token"], "<redacted>")
        self.assertEqual(d["encrypted_refresh_token"], "<redacted>")
        self.assertEqual(d["access_token"], "<redacted>")
        self.assertEqual(d["id_token"], "<redacted>")

    def test_khoa_ma_hoa(self):
        d = loc_bo_de_qui({"byop_master_key": "abc", "private_key": "def",
                          "openssl_key": "ghi"})
        self.assertEqual(d["byop_master_key"], "<redacted>")
        self.assertEqual(d["private_key"], "<redacted>")
        self.assertEqual(d["openssl_key"], "<redacted>")

    def test_cookie_session(self):
        d = loc_bo_de_qui({"cookie": "a_session_console=xyz", "cookies": {},
                          "session_secret": "abc"})
        self.assertEqual(d["cookie"], "<redacted>")
        self.assertEqual(d["session_secret"], "<redacted>")

    def test_khong_phan_biet_hoa_thuong(self):
        d = loc_bo_de_qui({"APIKEY": "x", "Api_Key": "y"})
        self.assertEqual(d["APIKEY"], "<redacted>")
        self.assertEqual(d["Api_Key"], "<redacted>")

    def test_khong_loc_nham_truong_khong_nhay_cam_co_hau_to_key(self):
        """Yeu cau tu ket qua audit: KHONG duoc loc theo substring "key" —
        `storage_key`/`avatar_key`/`cosmetic_key` la ID, khong phai bi mat."""
        d = loc_bo_de_qui({
            "storage_key": "images/u1/img1.jpg",
            "avatar_key": "avatars/u1.png",
            "cosmetic_key": "frame_vang",
            "keyId": "6a8114a814ee288c2d94",
        })
        self.assertEqual(d["storage_key"], "images/u1/img1.jpg")
        self.assertEqual(d["avatar_key"], "avatars/u1.png")
        self.assertEqual(d["cosmetic_key"], "frame_vang")
        self.assertEqual(d["keyId"], "6a8114a814ee288c2d94")


class LocTheoGiaTriTest(unittest.TestCase):
    """Bi mat lot vao MOT truong khong nam trong danh sach ten da biet —
    vi du nhu trong su co that dang tai hien (hinh dang, KHONG phai gia
    tri that), `apiKey` nam trong mot phan tu mang khong ten (`args[2]`)."""

    def test_khoa_appwrite_dang_standard_trong_van_ban_tu_do(self):
        cau = f"Đã gọi API với khoá {_KHOA_APPWRITE_GIA_LAP} nhưng thất bại."
        self.assertNotIn(_KHOA_APPWRITE_GIA_LAP, loc_bo_theo_gia_tri(cau))

    def test_bearer_token_trong_van_ban(self):
        cau = "Header gửi đi: Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"
        ra = loc_bo_theo_gia_tri(cau)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", ra)

    def test_jwt_trong_van_ban(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ"
        ra = loc_bo_theo_gia_tri(f"token: {jwt}")
        self.assertNotIn(jwt, ra)

    def test_van_ban_binh_thuong_khong_bi_dam(self):
        cau = "Không tìm thấy bản ghi có project_id abc123 và document_id xyz789."
        self.assertEqual(loc_bo_theo_gia_tri(cau), cau)


class GioiHanDeQuiTest(unittest.TestCase):
    def test_khong_de_qui_vo_han_tren_cau_truc_sau(self):
        sau = {"a": {"a": {"a": {"a": {"a": {"a": {"a": {"a": {"a": {
            "a": {"a": {"a": {"apiKey": "sau-qua-gioi-han"}}}}}}}}}}}}}
        # Khong nem loi du sau hon `do_sau_toi_da` mac dinh.
        ra = loc_bo_de_qui(sau)
        self.assertIsInstance(ra, dict)
