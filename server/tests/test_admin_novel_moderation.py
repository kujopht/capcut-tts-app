"""Kiem duyet truyen: SCRAPED -> DUYET -> XUAT BAN.

VI SAO CO TEP NAY.

Truoc ban nay, ban nhap do may gat tao ra thuoc `svc_harvester` — mot danh
tinh DICH VU khong ai dang nhap duoc. `POST /api/novels/{id}/publish` doi
dung chu so huu, va `_may_read` chi mo cho truyen da xuat ban hoac cho chinh
chu so huu. Ket qua do duoc tren kho san xuat: hai tac pham van ban hoan
chinh (23.970 va 55.384 ky tu, du tranh, da co audio) nam o `draft`, va
KHONG mot con nguoi nao xuat ban duoc chung.

Bo kiem nay khoa ca hai nua:

    nua MO   — quan tri doc va xuat ban duoc ban nhap cua may gat
    nua DONG — khong ai KHAC co them mot chut quyen nao

Nua thu hai quan trong hon, va de mat hon: mot ban sua "cho tien" o
`_may_read` se mo ban nhap cho ca the gioi ma khong bai nao o day do — nen
co bai kiem rieng cho chinh dieu do.
"""
from __future__ import annotations

import unittest

from server import novel_kind
from server.tests.test_admin import Base


class KiemDuyetTruyenTest(Base):
    """Luong day du, tren kho gia nhung di qua DUNG cac route that."""

    def setUp(self):
        super().setUp()
        # Mot "ban nhap cua may gat": chu so huu la mot danh tinh DICH VU ma
        # khong ai trong bo kiem nay dang nhap duoc.
        self.harvester = "svc_harvester"
        self.nov = self._tao_truyen_cua(self.harvester, "Tác phẩm máy gặt",
                                        tags=["Farmer"])
        self._tao_chuong(self.nov, "Chương 1", "Nội dung thật sự đọc được.")

    # ---------------------------------------------------------- tien ich --

    def _tao_truyen_cua(self, owner_id: str, title: str, *, tags=None):
        from server.domain import Novel
        return self.store.create_novel(Novel(
            owner_id=owner_id, title=title, description="",
            tags=list(tags or []))).novel_id

    def _tao_chuong(self, novel_id: str, title: str, content: str):
        from server.domain import Chapter
        n = self.store.get_novel(novel_id)
        return self.store.create_chapter(Chapter(
            novel_id=novel_id, owner_id=n.owner_id, title=title,
            content=content, order_index=1)).chapter_id

    def _user_id(self) -> str:
        return self.thuong["user_id"]

    # ------------------------------------------------ nua DONG (an toan) --

    def test_an_danh_KHONG_doc_duoc_ban_nhap(self):
        r = self.client.get(f"/api/novels/{self.nov}")
        self.assertEqual(r.status_code, 404, r.text)

    def test_nguoi_dung_thuong_KHONG_doc_duoc_ban_nhap_cua_nguoi_khac(self):
        r = self.client.get(f"/api/novels/{self.nov}", headers=self.h_thuong)
        self.assertEqual(r.status_code, 404, r.text)

    def test_nguoi_dung_thuong_KHONG_vao_duoc_be_mat_quan_tri(self):
        for duong, method in (
            (f"/api/admin/novels/{self.nov}", "get"),
            (f"/api/admin/novels/{self.nov}/publish", "post"),
            (f"/api/admin/novels/{self.nov}/unpublish", "post"),
        ):
            with self.subTest(duong=duong):
                r = getattr(self.client, method)(duong, headers=self.h_thuong)
                self.assertEqual(r.status_code, 403, r.text)

    def test_chu_so_huu_VAN_doc_duoc_ban_nhap_cua_chinh_minh(self):
        nov = self._tao_truyen_cua(self._user_id(), "Của tôi")
        r = self.client.get(f"/api/novels/{nov}", headers=self.h_thuong)
        self.assertEqual(r.status_code, 200, r.text)

    def test_duong_CONG_KHAI_khong_co_nhanh_admin(self):
        """Quan tri doc ban nhap qua be mat RIENG, khong qua `_may_read`.

        Neu mot ban sau nay them "neu la admin" vao `_may_read`, bai nay do —
        va no phai do, vi moi route doc cong khai deu thua ke ham do.
        """
        r = self.client.get(f"/api/novels/{self.nov}", headers=self.h_admin)
        self.assertEqual(r.status_code, 404, r.text)

    # ------------------------------------------------------- nua MO (dung) --

    def test_admin_doc_duoc_ban_nhap_cua_may_gat_KEM_noi_dung_chuong(self):
        r = self.client.get(f"/api/admin/novels/{self.nov}",
                            headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["novel"]["novel_id"], self.nov)
        self.assertEqual(len(d["chapters"]), 1)
        # Doc duoc THAT — khong chi dem chuong.
        self.assertIn("đọc được", d["chapters"][0]["content"])
        self.assertGreater(d["total_chars"], 0)

    def test_admin_xuat_ban_duoc_va_cong_khai_doc_duoc_NGAY_SAU_DO(self):
        r = self.client.post(f"/api/admin/novels/{self.nov}/publish",
                             json={"note": "đã đọc"}, headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["novel"]["state"], "published")

        # Va nguoi la doc duoc — day la dieu ca luong ton tai de dat toi.
        r = self.client.get(f"/api/novels/{self.nov}")
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["chapters"][0]["chapter_id"]
        r = self.client.get(f"/api/chapters/{cid}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("đọc được", r.json()["chapter"]["content"])

    def test_xuat_ban_LAP_LAI_la_an_toan(self):
        for _ in range(3):
            r = self.client.post(f"/api/admin/novels/{self.nov}/publish",
                                 headers=self.h_admin)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["novel"]["state"], "published")
        # Khong sinh ban trung.
        r = self.client.get("/api/novels?limit=100")
        ids = [n["novel_id"] for n in r.json()["novels"]]
        self.assertEqual(ids.count(self.nov), 1)

    def test_admin_go_xuong_duoc_va_cong_khai_MAT_ngay(self):
        self.client.post(f"/api/admin/novels/{self.nov}/publish",
                         headers=self.h_admin)
        r = self.client.post(f"/api/admin/novels/{self.nov}/unpublish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["novel"]["state"], "draft")
        self.assertEqual(self.client.get(f"/api/novels/{self.nov}").status_code,
                         404)

    def test_go_xuong_LAP_LAI_la_an_toan(self):
        for _ in range(2):
            r = self.client.post(f"/api/admin/novels/{self.nov}/unpublish",
                                 headers=self.h_admin)
            self.assertEqual(r.status_code, 200, r.text)

    def test_sua_sieu_du_lieu(self):
        r = self.client.patch(f"/api/admin/novels/{self.nov}",
                              json={"title": "Tên đã sửa"},
                              headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["novel"]["title"], "Tên đã sửa")

    # --------------------------------------------------- cong CHONG RONG --

    def test_truyen_KHONG_CO_CHUONG_khong_xuat_ban_duoc(self):
        nov = self._tao_truyen_cua(self.harvester, "Rỗng hoàn toàn")
        r = self.client.post(f"/api/admin/novels/{nov}/publish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self.store.get_novel(nov).state.value, "draft")

    def test_truyen_co_chuong_nhung_RONG_CHU_khong_xuat_ban_duoc(self):
        """`len(chapters) > 0` chua du.

        13 truyen dang song tren trang deu co dung mot chuong VA
        `char_count == 0` (nhap tu audio dai tap). Mot ban nhap van ban ma
        moi chuong deu rong thi xuat ban ra la mot trang trong.
        """
        nov = self._tao_truyen_cua(self.harvester, "Có chương nhưng rỗng")
        self._tao_chuong(nov, "Chương 1", "   \n  ")
        r = self.client.post(f"/api/admin/novels/{nov}/publish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 409, r.text)

    def test_MODERATOR_xem_duoc_nhung_KHONG_bam_duoc(self):
        """Doc va GHI khong cung mot bac quyen — va do la co y.

        Kiem duyet vien can DOC de phan loai. Nhung xuat ban la dua noi dung
        ra truoc cong chung, nen bac quyen cua no phai bang bac quan ly noi
        dung/nguoi dung (`admin_or_owner_profile`), khong phai bac xem.
        """
        mod, h_mod = self._dang_ky("mod@fanfic.local", "Kiểm Duyệt")
        self._dat_vai_tro(admin=[self.admin["user_id"]],
                          moderator=[mod["user_id"]])

        self.assertEqual(
            self.client.get(f"/api/admin/novels/{self.nov}",
                            headers=h_mod).status_code, 200)
        for duong in (f"/api/admin/novels/{self.nov}/publish",
                      f"/api/admin/novels/{self.nov}/unpublish"):
            with self.subTest(duong=duong):
                self.assertEqual(
                    self.client.post(duong, headers=h_mod).status_code, 403)
        self.assertEqual(
            self.client.patch(f"/api/admin/novels/{self.nov}",
                              json={"title": "x"},
                              headers=h_mod).status_code, 403)

    def test_hanh_dong_duoc_ghi_vao_NHAT_KY_kiem_duyet(self):
        self.client.post(f"/api/admin/novels/{self.nov}/publish",
                         json={"note": "đã đọc hết"}, headers=self.h_admin)
        d = self.client.get("/api/admin/events?limit=50",
                            headers=self.h_admin).json()
        cua_truyen = [e for e in d.get("events", [])
                      if e.get("target_id") == self.nov]
        self.assertTrue(cua_truyen, "không ghi nhật ký lần xuất bản")
        self.assertEqual(cua_truyen[0]["action"], "content_publish")
        self.assertEqual(cua_truyen[0]["target_type"], "novel")

    def test_khong_co_route_XOA_truyen_o_be_mat_moi(self):
        for duong in (f"/api/admin/novels/{self.nov}",):
            self.assertEqual(self.client.delete(duong,
                                                headers=self.h_admin).status_code,
                             405, duong)


class LocHaTangTest(Base):
    """Hang doi kiem duyet chi duoc chua TAC PHAM."""

    def test_phan_loai_dung_tung_loai(self):
        from server.domain import Novel
        for tags, mong_doi in (
            (["audio-studio"], novel_kind.LOAI_KHO_STUDIO),
            (["qa-canary", "test"], novel_kind.LOAI_KIEM_THU),
            (["Farmer"], novel_kind.LOAI_FARMER),
            (["work:CAT-1"], novel_kind.LOAI_MEDIA),
            (["Naruto"], novel_kind.LOAI_TRUYEN),
            ([], novel_kind.LOAI_TRUYEN),
        ):
            with self.subTest(tags=tags):
                n = Novel(owner_id="u", title="x", tags=list(tags))
                self.assertEqual(novel_kind.loai_ban_ghi(n), mong_doi)

    def test_kho_chua_studio_KHONG_phai_tac_pham(self):
        from server.domain import Novel
        self.assertFalse(novel_kind.la_tac_pham(
            Novel(owner_id="u", title="Audio Studio", tags=["audio-studio"])))

    def test_lan_media_VAN_la_tac_pham(self):
        """13 truyen dang song tren trang deu thuoc lan nay."""
        from server.domain import Novel
        self.assertTrue(novel_kind.la_tac_pham(
            Novel(owner_id="u", title="x", tags=["work:CAT-1", "imported"])))

    def test_danh_sach_kiem_duyet_bo_ha_tang_va_dem_DUNG(self):
        from server.domain import Novel
        for i in range(4):
            self.store.create_novel(Novel(owner_id="u1", title=f"kho {i}",
                                        tags=["audio-studio"]))
        for i in range(3):
            self.store.create_novel(Novel(owner_id="u1", title=f"truyện {i}",
                                        tags=["Naruto"]))
        self.store.create_novel(Novel(owner_id="u1", title="qa", tags=["test"]))

        d = self.client.get("/api/admin/novels?kind=story&state=draft&limit=100",
                            headers=self.h_admin).json()
        ten = [n["title"] for n in d["novels"]]
        self.assertNotIn("kho 0", ten)
        self.assertNotIn("qa", ten)
        self.assertIn("truyện 0", ten)
        # `total` la tong cua DUNG nhung dong nguoi quan tri se thay.
        self.assertEqual(d["total"], len(d["novels"]))

    def test_phan_trang_KHONG_bi_ngan_di_vi_loc(self):
        """Loc RA TRUOC roi moi cat trang.

        Ban cu loc mot TRANG da cat san, nen mot trang co the tra ve it hon
        `limit` du con du du lieu — va `total` la tong CHUA loc.
        """
        from server.domain import Novel
        for i in range(10):
            self.store.create_novel(Novel(owner_id="u1", title=f"kho {i}",
                                        tags=["audio-studio"]))
            self.store.create_novel(Novel(owner_id="u1", title=f"truyện {i}",
                                        tags=["Naruto"]))

        d = self.client.get("/api/admin/novels?kind=story&state=draft&limit=5",
                            headers=self.h_admin).json()
        self.assertEqual(len(d["novels"]), 5, "trang bị ngắn đi vì lọc sau")
        for n in d["novels"]:
            self.assertNotEqual(n["kind"], novel_kind.LOAI_KHO_STUDIO)

    def test_trang_thai_loc_o_KHO_chu_khong_sau_phan_trang(self):
        from server.domain import Novel
        for i in range(6):
            n = self.store.create_novel(Novel(owner_id="u1", title=f"pub {i}",
                                            tags=["Naruto"]))
            self.store.admin_publish_novel(n.novel_id)
        for i in range(4):
            self.store.create_novel(Novel(owner_id="u1", title=f"nhap {i}",
                                        tags=["Naruto"]))

        d = self.client.get("/api/admin/novels?state=draft&limit=100",
                            headers=self.h_admin).json()
        for n in d["novels"]:
            self.assertEqual(n["state"], "draft")
        self.assertEqual(d["total"], len(d["novels"]))



if __name__ == "__main__":
    unittest.main()
