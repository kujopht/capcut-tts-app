"""
Cac route HTTP cua he thong tac gia.

Bo test nay lo nhung thu chi lo ra o TANG HTTP: ma trang thai nao, truong nao lo
ra ngoai, va cong chan xuat ban co dung theo co cau hinh hay khong.

Chay hoan toan offline: kho va danh tinh la ban mock.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.creator_service import CreatorService
from server.domain import Novel, PublishState


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.creators = CreatorService(server_main.identity,
                                              server_main.store)
        self.identity = server_main.identity
        self.store = server_main.store
        self.svc = server_main.creators
        # `Settings` la frozen dataclass: doi co bang `replace`, khong bang phep
        # gan. Frozen la co y — cau hinh khong duoc doi giua duong chay.
        self._settings_cu = server_main.settings
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.settings = self._settings_cu

    def _dat_co(self, bat: bool) -> None:
        from dataclasses import replace
        server_main.settings = replace(server_main.settings,
                                       author_gate_enabled=bat)

    def _dang_ky(self, email="a@x.local", ten="Nam Kujo"):
        self.client.post("/api/auth/register", json={
            "email": email, "password": "matkhau123", "display_name": ten})
        r = self.client.post("/api/auth/login",
                             json={"email": email, "password": "matkhau123"})
        token = r.json()["token"]
        return token, {"Authorization": f"Bearer {token}"}

    def _don(self, headers):
        return self.client.post("/api/creator/apply", headers=headers, json={
            "pen_name": "Kẻ Dệt Mộng",
            "bio": "Viết fanfic One Piece.",
            "genres": ["One Piece"],
            "intro": "Tôi viết fanfic đã ba năm.",
            "accepted_rules": True,
        })


class CreatorStateRouteTest(Base):
    def test_can_dang_nhap(self):
        self.assertEqual(self.client.get("/api/creator/me").status_code, 401)

    def test_nguoi_moi_thi_none_va_khong_xuat_ban_duoc(self):
        _, h = self._dang_ky()
        d = self.client.get("/api/creator/me", headers=h).json()
        self.assertEqual(d["author_status"], "none")
        self.assertFalse(d["can_publish"])
        self.assertTrue(d["can_apply"])

    def test_chua_co_username_thi_co_goi_y(self):
        _, h = self._dang_ky()
        d = self.client.get("/api/creator/me", headers=h).json()
        self.assertEqual(d["username_suggestion"], "nam-kujo")

    def test_co_username_roi_thi_KHONG_con_goi_y(self):
        _, h = self._dang_ky()
        self.client.put("/api/creator/username", headers=h,
                        json={"username": "namkujo"})
        d = self.client.get("/api/creator/me", headers=h).json()
        self.assertNotIn("username_suggestion", d)

    def test_bang_hang_KHONG_can_dang_nhap(self):
        # Giao dien can ve thang bac truoc ca khi biet nguoi dung la ai.
        r = self.client.get("/api/creator/ranks")
        self.assertEqual(r.status_code, 200)
        tiers = r.json()["tiers"]
        self.assertEqual(len(tiers), 6)
        self.assertEqual(tiers[0]["min_listens"], 0)
        self.assertEqual([t["level"] for t in tiers], [1, 2, 3, 4, 5, 6])


class UsernameRouteTest(Base):
    def test_dat_username(self):
        _, h = self._dang_ky()
        r = self.client.put("/api/creator/username", headers=h,
                            json={"username": "Kẻ Dệt Mộng"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["username"], "ke-det-mong")

    def test_username_sai_quy_tac_tra_400(self):
        _, h = self._dang_ky()
        for xau in ("ab", "admin", "nam kujo!"):
            r = self.client.put("/api/creator/username", headers=h,
                                json={"username": xau})
            self.assertEqual(r.status_code, 400, xau)

    def test_username_trung_tra_409(self):
        _, h1 = self._dang_ky("a@x.local", "A")
        _, h2 = self._dang_ky("b@x.local", "B")
        self.client.put("/api/creator/username", headers=h1,
                        json={"username": "trungten"})
        r = self.client.put("/api/creator/username", headers=h2,
                            json={"username": "trungten"})
        self.assertEqual(r.status_code, 409)


class PublicProfileRouteTest(Base):
    def test_trang_cong_khai_KHONG_can_dang_nhap(self):
        _, h = self._dang_ky()
        self.client.put("/api/creator/username", headers=h,
                        json={"username": "namkujo"})
        r = self.client.get("/api/users/namkujo")
        self.assertEqual(r.status_code, 200)

    def test_KHONG_lo_email(self):
        _, h = self._dang_ky()
        self.client.put("/api/creator/username", headers=h,
                        json={"username": "namkujo"})
        d = self.client.get("/api/users/namkujo").json()["profile"]
        self.assertNotIn("email", d)
        self.assertNotIn("author_status", d)
        self.assertNotIn("tier", d)

    def test_khong_ton_tai_va_chua_chon_username_deu_tra_404(self):
        """
        Phan biet hai truong hop nay ra thi thanh mot cach do xem ai da dang ky.
        """
        self._dang_ky()          # co nguoi dung, nhung chua chon username
        self.assertEqual(self.client.get("/api/users/namkujo").status_code, 404)
        self.assertEqual(self.client.get("/api/users/khong-he-co").status_code, 404)

    def test_chi_liet_ke_truyen_da_xuat_ban(self):
        _, h = self._dang_ky()
        self.client.put("/api/creator/username", headers=h,
                        json={"username": "namkujo"})
        me = self.client.get("/api/auth/me", headers=h).json()["profile"]
        self.store.create_novel(Novel(owner_id=me["user_id"], title="Nháp",
                                      state=PublishState.DRAFT))
        self.store.create_novel(Novel(owner_id=me["user_id"], title="Công khai",
                                      state=PublishState.PUBLISHED))
        d = self.client.get("/api/users/namkujo").json()["profile"]
        self.assertEqual([n["title"] for n in d["novels"]], ["Công khai"])

    def test_tac_gia_da_duyet_thi_co_huy_hieu_va_hang(self):
        _, h = self._dang_ky()
        self.client.put("/api/creator/username", headers=h,
                        json={"username": "namkujo"})
        self._don(h)
        me = self.client.get("/api/auth/me", headers=h).json()["profile"]
        self.svc.approve(me["user_id"])
        d = self.client.get("/api/users/namkujo").json()["profile"]
        self.assertTrue(d["is_author"])
        self.assertEqual(d["rank"]["key"], "tan_but")


class ApplyRouteTest(Base):
    def test_nop_don_tra_201(self):
        _, h = self._dang_ky()
        r = self._don(h)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["author_status"], "pending")

    def test_don_tra_ve_KHONG_kem_khoa_noi_bo(self):
        _, h = self._dang_ky()
        d = self._don(h).json()["application"]
        self.assertNotIn("user_id", d)
        self.assertNotIn("application_id", d)

    def test_khong_dong_y_quy_dinh_tra_409(self):
        _, h = self._dang_ky()
        r = self.client.post("/api/creator/apply", headers=h, json={
            "pen_name": "X Y", "intro": "Xin chào", "accepted_rules": False})
        self.assertEqual(r.status_code, 409)

    def test_thieu_gioi_thieu_thi_pydantic_chan_o_422(self):
        _, h = self._dang_ky()
        r = self.client.post("/api/creator/apply", headers=h, json={
            "pen_name": "X Y", "intro": "", "accepted_rules": True})
        self.assertEqual(r.status_code, 422)

    def test_nop_hai_lan_tra_409(self):
        _, h = self._dang_ky()
        self._don(h)
        self.assertEqual(self._don(h).status_code, 409)


class PublishGateTest(Base):
    """
    Cong chan xuat ban, ca hai trang thai co.

    Vi sao co MOT CAI CO chu khong bat luon: moi ho so dang ton tai deu co
    `author_status = "none"`, ke ca nhung nguoi da xuat ban muoi truyen. Bat cong
    truoc khi chay migration grandfather la khoa toan bo tac gia hien co ra khoi
    chinh cong viec cua ho.
    """

    def _truyen(self, headers):
        r = self.client.post("/api/novels", headers=headers,
                             json={"title": "Truyện thử"})
        return r.json()["novel"]["novel_id"]

    def test_co_TAT_thi_ai_cung_xuat_ban_duoc(self):
        self._dat_co(False)
        _, h = self._dang_ky()
        nid = self._truyen(h)
        r = self.client.post(f"/api/novels/{nid}/publish", headers=h)
        self.assertEqual(r.status_code, 200)

    def test_co_BAT_thi_nguoi_chua_dang_ky_bi_403(self):
        self._dat_co(True)
        _, h = self._dang_ky()
        nid = self._truyen(h)
        r = self.client.post(f"/api/novels/{nid}/publish", headers=h)
        self.assertEqual(r.status_code, 403)
        self.assertIn("đăng ký tác giả", r.json()["detail"])

    def test_co_BAT_va_dang_cho_duyet_thi_thong_diep_KHAC(self):
        # Giao dien mo mot luong khac nhau cho tung trang thai, nen thong diep
        # phai phan biet duoc — khong duoc la mot loi chung.
        self._dat_co(True)
        _, h = self._dang_ky()
        self._don(h)
        nid = self._truyen(h)
        r = self.client.post(f"/api/novels/{nid}/publish", headers=h)
        self.assertEqual(r.status_code, 403)
        self.assertIn("chờ duyệt", r.json()["detail"])

    def test_co_BAT_va_da_duyet_thi_xuat_ban_duoc(self):
        self._dat_co(True)
        _, h = self._dang_ky()
        self._don(h)
        me = self.client.get("/api/auth/me", headers=h).json()["profile"]
        self.svc.approve(me["user_id"])
        nid = self._truyen(h)
        r = self.client.post(f"/api/novels/{nid}/publish", headers=h)
        self.assertEqual(r.status_code, 200)

    def test_co_BAT_van_KHONG_chan_tao_va_sua_ban_nhap(self):
        """
        Ai cung viet duoc, chi khong ai cung dua ra cong khai duoc. Cong chi nam
        o route publish — day la phep kiem giu dieu do.
        """
        self._dat_co(True)
        _, h = self._dang_ky()
        nid = self._truyen(h)                      # tao duoc
        r = self.client.patch(f"/api/novels/{nid}", headers=h,
                              json={"title": "Sửa được"})
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/chapters", headers=h, json={
            "novel_id": nid, "title": "Chương 1", "content": "Nội dung."})
        self.assertEqual(r.status_code, 201)

    def test_co_BAT_va_bi_treo_thi_403_voi_thong_diep_rieng(self):
        self._dat_co(True)
        _, h = self._dang_ky()
        self._don(h)
        me = self.client.get("/api/auth/me", headers=h).json()["profile"]
        self.svc.approve(me["user_id"])
        self.svc.suspend(me["user_id"], note="Vi phạm.")
        nid = self._truyen(h)
        r = self.client.post(f"/api/novels/{nid}/publish", headers=h)
        self.assertEqual(r.status_code, 403)
        self.assertIn("tạm dừng", r.json()["detail"])


class SearchRouteTest(Base):
    def _nguoi(self, email, ten, username, duyet=False):
        _, h = self._dang_ky(email, ten)
        self.client.put("/api/creator/username", headers=h,
                        json={"username": username})
        me = self.client.get("/api/auth/me", headers=h).json()["profile"]
        if duyet:
            self._don(h)
            self.svc.approve(me["user_id"])
        return me["user_id"], h

    def test_tim_nguoi_KHONG_can_dang_nhap(self):
        self._nguoi("a@x.local", "Nam Kujo", "namkujo")
        r = self.client.get("/api/search/people", params={"q": "nam"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["people"]), 1)

    def test_muc_tac_gia_CHI_tra_nguoi_da_duyet(self):
        self._nguoi("a@x.local", "Tác Giả", "tacgia", duyet=True)
        self._nguoi("b@x.local", "Người Đọc", "nguoidoc")
        d = self.client.get("/api/search/people",
                            params={"q": "", "kind": "authors"}).json()
        self.assertEqual([p["username"] for p in d["people"]], ["tacgia"])

    def test_muc_nguoi_dung_tra_ca_hai_loai(self):
        self._nguoi("a@x.local", "Tác Giả", "tacgia", duyet=True)
        self._nguoi("b@x.local", "Người Đọc", "nguoidoc")
        d = self.client.get("/api/search/people", params={"q": ""}).json()
        self.assertEqual(len(d["people"]), 2)

    def test_KHONG_lo_trang_thai_duyet_trong_ket_qua(self):
        _, h = self._dang_ky("c@x.local", "Đang Chờ")
        self.client.put("/api/creator/username", headers=h,
                        json={"username": "dangcho"})
        self._don(h)
        d = self.client.get("/api/search/people", params={"q": "dang"}).json()
        self.assertNotIn("author_status", d["people"][0])
        self.assertFalse(d["people"][0]["is_author"])

    def test_gioi_han_bi_ep_ve_khoang_an_toan(self):
        # Mot client goi `limit=100000` khong duoc keo ca bang ve.
        d = self.client.get("/api/search/people",
                            params={"q": "", "limit": 100000}).json()
        self.assertLessEqual(d["limit"], 50)
        d = self.client.get("/api/search/people",
                            params={"q": "", "limit": 0, "offset": -5}).json()
        self.assertGreaterEqual(d["limit"], 1)
        self.assertEqual(d["offset"], 0)


class ListenRouteTest(Base):
    def setUp(self):
        super().setUp()
        _, self.h_tacgia = self._dang_ky("a@x.local", "Tác Giả")
        self.tacgia = self.client.get("/api/auth/me",
                                      headers=self.h_tacgia).json()["profile"]
        _, self.h_doc = self._dang_ky("b@x.local", "Người Đọc")
        nid = self.client.post("/api/novels", headers=self.h_tacgia,
                               json={"title": "T"}).json()["novel"]["novel_id"]
        self.chuong = self.client.post("/api/chapters", headers=self.h_tacgia, json={
            "novel_id": nid, "title": "C1", "content": "x" * 200,
        }).json()["chapter"]["chapter_id"]

    def _bao(self, headers, giay):
        return self.client.post("/api/listens", headers=headers or {},
                                json={"chapter_id": self.chuong,
                                      "listened_seconds": giay})

    def test_khach_an_danh_KHONG_bi_401(self):
        """
        Tra 401 se lam trinh phat cua khach hien loi cho mot viec ho khong lam
        gi sai. No tra 200 kem `credited=false`.
        """
        r = self._bao(None, 120)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["credited"])
        self.assertEqual(r.json()["reason"], "khong_dang_nhap")

    def test_nghe_du_lau_thi_duoc_tinh(self):
        r = self._bao(self.h_doc, 120)
        self.assertTrue(r.json()["credited"])
        self.assertEqual(
            self.store.get_stats(self.tacgia["user_id"]).qualified_listens, 1)

    def test_bam_phat_roi_tat_KHONG_duoc_tinh(self):
        r = self._bao(self.h_doc, 2)
        self.assertFalse(r.json()["credited"])
        self.assertEqual(r.json()["reason"], "chua_du_lau")

    def test_tac_gia_tu_nghe_KHONG_duoc_tinh(self):
        r = self._bao(self.h_tacgia, 600)
        self.assertFalse(r.json()["credited"])
        self.assertEqual(r.json()["reason"], "tu_nghe")

    def test_bao_lai_ngay_thi_KHONG_cong_them(self):
        self._bao(self.h_doc, 120)
        r = self._bao(self.h_doc, 120)
        self.assertFalse(r.json()["credited"])
        self.assertEqual(r.json()["reason"], "da_tinh_trong_24h")
        self.assertEqual(
            self.store.get_stats(self.tacgia["user_id"]).qualified_listens, 1)

    def test_KHONG_tra_ve_so_lan_nghe_cua_tac_gia(self):
        # Tra ve thi thanh mot cach dem uy tin cua nguoi khac bang cach bam Phat.
        d = self._bao(self.h_doc, 120).json()
        self.assertEqual(set(d.keys()), {"credited", "reason"})

    def test_chuong_khong_ton_tai_tra_404(self):
        r = self.client.post("/api/listens", headers=self.h_doc,
                             json={"chapter_id": "chp_khong_co",
                                   "listened_seconds": 60})
        self.assertEqual(r.status_code, 404)

    def test_so_giay_vo_ly_bi_pydantic_chan(self):
        for giay in (-5, 999_999):
            r = self.client.post("/api/listens", headers=self.h_doc,
                                 json={"chapter_id": self.chuong,
                                       "listened_seconds": giay})
            self.assertEqual(r.status_code, 422, giay)


class NoAdminEndpointTest(Base):
    def test_duong_duyet_CHI_ton_tai_duoi_khu_quan_tri(self):
        """
        Bai test nay da doi mot lan, va lich su cua no la phan quan trong nhat.

        BAN TRUOC: cam MOI route co chua `approve`/`reject`/`suspend`/`admin`.
        Luc do du an chua co co che phan quyen quan tri nao, va mot endpoint duyet
        khong duoc bao ve la mot cai cong mo — bat ky ai doan duoc duong dan deu
        tu phong minh lam tac gia. Bai test do da DO dung vao lan them khu quan
        tri, y nhu no duoc viet ra de lam.

        BAN NAY: cho phep chung ton tai, nhung CHI duoi `/api/admin/*`, va
        `test_admin.py::test_moi_route_admin_deu_duoc_bao_ve` kiem tung cai co
        `Depends(admin_profile)` hay khong.

        Nghia la: mot route duyet nam ngoai `/api/admin/` van bi cam — do la cach
        de nhat de vo tinh mo lai cai cong cu.
        """
        cam = ("approve", "reject", "suspend", "restore", "moderation")
        for r in server_main.app.routes:
            d = getattr(r, "path", "")
            if d.startswith("/api/admin/"):
                continue
            for tu in cam:
                self.assertNotIn(tu, d.lower(),
                                 f"{d} là cổng duyệt nằm NGOÀI khu quản trị")

    def test_cac_ham_duyet_VAN_ton_tai_o_tang_service(self):
        # Trang quan tri goi DUNG nhung ham nay — khong nhan ban logic nghiep vu
        # vao than route. Xem `main.py` muc QUAN TRI.
        for ten in ("approve", "reject", "suspend", "restore",
                    "pending_applications", "grandfather_existing_authors"):
            self.assertTrue(callable(getattr(self.svc, ten, None)), ten)


if __name__ == "__main__":
    unittest.main()
