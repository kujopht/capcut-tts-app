"""
KHU QUAN TRI: quyen truy cap, va nhung gi lo ra qua duong nay.

Bai test quan trong nhat cua ca tep la `test_moi_route_admin_deu_duoc_bao_ve`:
no tu LIET KE cac route `/api/admin/*` roi kiem tung cai. Mot route moi duoc
them ma quen `Depends(admin_profile)` se lam bai do do — khong ai phai nho bo
sung mot dong vao danh sach test.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.creator_service import CreatorService
from server.domain import AuthorStatus, Novel, PublishState


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.creators = CreatorService(server_main.identity,
                                              server_main.store)
        self.identity = server_main.identity
        self.store = server_main.store
        self.svc = server_main.creators
        self._settings_cu = server_main.settings
        self.client = TestClient(server_main.app)

        # Quan tri: mot tai khoan that, va `user_id` cua no duoc dat vao CAU HINH.
        self.admin, self.h_admin = self._dang_ky("admin@fanfic.local", "Quản Trị")
        self._dat_admin([self.admin["user_id"]])

        # Nguoi dung thuong.
        self.thuong, self.h_thuong = self._dang_ky("thuong@fanfic.local", "Người Thường")

    def tearDown(self) -> None:
        server_main.settings = self._settings_cu

    def _dat_admin(self, ids) -> None:
        server_main.settings = replace(server_main.settings,
                                       admin_user_ids=tuple(ids))

    def _dat_vai_tro(self, owner=(), admin=(), moderator=()) -> None:
        """Dat CA BA danh sach vai tro cung luc (Admin Control Center V2)."""
        server_main.settings = replace(
            server_main.settings,
            owner_user_ids=tuple(owner),
            admin_user_ids=tuple(admin),
            moderator_user_ids=tuple(moderator),
        )

    def _dang_ky(self, email, ten):
        self.client.post("/api/auth/register", json={
            "email": email, "password": "matkhau123", "display_name": ten})
        r = self.client.post("/api/auth/login",
                             json={"email": email, "password": "matkhau123"})
        d = r.json()
        return d["profile"], {"Authorization": f"Bearer {d['token']}"}

    def _tac_gia(self, email="tg@fanfic.local", ten="Tác Giả", duyet=True):
        me, h = self._dang_ky(email, ten)
        self.client.put("/api/creator/username", headers=h,
                        json={"username": ten.lower().replace(" ", "-")})
        self.client.post("/api/creator/apply", headers=h, json={
            "pen_name": ten, "intro": "Tôi viết fanfic.", "accepted_rules": True})
        if duyet:
            self.svc.approve(me["user_id"], actor_id=self.admin["user_id"])
        return me, h


class AdminAuthTest(Base):
    """Ba trang thai nguoi goi, ba ket qua khac nhau."""

    DUONG_GET = [
        "/api/admin/overview",
        "/api/admin/author-applications",
        "/api/admin/authors",
        "/api/admin/users",
        "/api/admin/novels",
        "/api/admin/events",
    ]

    def test_an_danh_nhan_401(self):
        for d in self.DUONG_GET:
            self.assertEqual(self.client.get(d).status_code, 401, d)

    def test_nguoi_dung_THUONG_nhan_403(self):
        for d in self.DUONG_GET:
            self.assertEqual(self.client.get(d, headers=self.h_thuong).status_code,
                             403, d)

    def test_quan_tri_vao_duoc(self):
        for d in self.DUONG_GET:
            self.assertEqual(self.client.get(d, headers=self.h_admin).status_code,
                             200, d)

    def test_nguoi_thuong_KHONG_thay_mot_byte_du_lieu_nao(self):
        """
        403 phai la 403 RONG. Mot thong diep loi co kem so lieu — "co 3 don dang
        cho" — la ro ri du lieu qua duong bao loi.
        """
        r = self.client.get("/api/admin/overview", headers=self.h_thuong)
        than = r.json()
        self.assertEqual(set(than.keys()), {"detail"})
        for khoa in ("pending", "authors", "users", "email", "novels"):
            self.assertNotIn(khoa, str(than).lower(), khoa)

    def test_moi_route_admin_deu_duoc_bao_ve(self):
        """
        Tu liet ke va tu kiem. Mot route `/api/admin/*` moi ma quen mot trong
        BA phu thuoc quan tri (Admin Control Center V2: `admin_profile` — bat
        ky muc nao; `admin_or_owner_profile` — ADMIN tro len; `owner_profile`
        — CHI OWNER, danh cho cai dat he thong/tai chinh) se lam bai nay do —
        khong ai phai nho bo sung mot dong vao danh sach test.
        """
        duong = sorted({
            getattr(r, "path", "") for r in server_main.app.routes
            if getattr(r, "path", "").startswith("/api/admin/")
        })
        self.assertGreaterEqual(len(duong), 10, "chưa có route quản trị nào?")

        PHU_THUOC_HOP_LE = {
            server_main.admin_profile,
            server_main.admin_or_owner_profile,
            server_main.owner_profile,
        }
        chua_bao_ve = []
        for r in server_main.app.routes:
            d = getattr(r, "path", "")
            if not d.startswith("/api/admin/"):
                continue
            ten_tham_so = set(getattr(r, "dependant", None).query_params and [] or [])
            # Tham so `admin` la ket qua cua mot trong ba `Depends(...)` o
            # tren; kiem theo CHINH ham phu thuoc chu khong theo ten bien.
            phu_thuoc = [
                sub.call for sub in getattr(r.dependant, "dependencies", [])
            ]
            if not (PHU_THUOC_HOP_LE & set(phu_thuoc)):
                chua_bao_ve.append(f"{sorted(r.methods)} {d}")
            del ten_tham_so
        self.assertEqual(chua_bao_ve, [],
                         "route quản trị thiếu Depends(admin_profile/"
                         "admin_or_owner_profile/owner_profile)")

    def test_khong_co_quan_tri_nao_thi_KHONG_AI_vao_duoc(self):
        """Mac dinh la RONG: mot he thong moi trien khai khong co cua sau nao."""
        self._dat_admin([])
        self.assertEqual(
            self.client.get("/api/admin/overview", headers=self.h_admin).status_code,
            403)

    def test_health_KHONG_lo_danh_sach_quan_tri(self):
        # `/api/health` la cong khai. Lo `user_id` cua quan tri la chi dich.
        d = self.client.get("/api/health").json()
        self.assertNotIn(self.admin["user_id"], str(d))


class AdminRoleModelTest(Base):
    """
    Ba muc quan tri (Admin Control Center V2): OWNER > ADMIN > MODERATOR,
    van la BIEN MOI TRUONG (xem `Settings.admin_role_of`), khong phai cot du
    lieu — chi mo rong tu MOT danh sach thanh BA.
    """

    def setUp(self) -> None:
        super().setUp()
        self.chu, self.h_chu = self._dang_ky("owner@fanfic.local", "Chủ Sở Hữu")
        self.kiemduyet, self.h_kiemduyet = self._dang_ky(
            "mod@fanfic.local", "Kiểm Duyệt")
        self._dat_vai_tro(
            owner=[self.chu["user_id"]],
            admin=[self.admin["user_id"]],
            moderator=[self.kiemduyet["user_id"]],
        )

    def test_owner_profile_chi_owner_vao_duoc(self):
        d = "/api/admin/image-studio/kill-switch"
        payload = {"engaged": True}
        self.assertEqual(
            self.client.post(d, json=payload, headers=self.h_chu).status_code, 200)
        for h in (self.h_admin, self.h_kiemduyet, self.h_thuong):
            self.assertEqual(
                self.client.post(d, json=payload, headers=h).status_code, 403)

    def test_admin_or_owner_profile_tu_choi_moderator(self):
        # `/api/admin/users` dung `admin_or_owner_profile` — MODERATOR khong
        # duoc quan ly nguoi dung, chi duoc xu ly bao cao/kiem duyet noi dung.
        d = "/api/admin/users"
        self.assertEqual(
            self.client.get(d, headers=self.h_admin).status_code, 200)
        self.assertEqual(
            self.client.get(d, headers=self.h_chu).status_code, 200)
        self.assertEqual(
            self.client.get(d, headers=self.h_kiemduyet).status_code, 403)

    def test_admin_profile_van_nhan_ca_ba_muc(self):
        # `/api/admin/overview` dung `admin_profile` — bat ky vai tro nao
        # trong ba cung vao duoc, dung tinh than "MODERATOR van la quan tri".
        d = "/api/admin/overview"
        for h in (self.h_chu, self.h_admin, self.h_kiemduyet):
            self.assertEqual(self.client.get(d, headers=h).status_code, 200)
        self.assertEqual(
            self.client.get(d, headers=self.h_thuong).status_code, 403)

    def test_nam_trong_nhieu_danh_sach_thi_muc_cao_nhat_thang(self):
        """Sai sot cau hinh (cung mot id trong ca owner lan moderator) khong
        duoc CONG DON quyen — luon lay muc CAO NHAT."""
        self._dat_vai_tro(
            owner=[self.thuong["user_id"]],
            moderator=[self.thuong["user_id"]],
        )
        self.assertEqual(
            server_main.settings.admin_role_of(self.thuong["user_id"]),
            server_main.AdminRole.OWNER,
        )

    def test_auth_me_tra_dung_admin_role_theo_tung_muc(self):
        for h, muc in (
            (self.h_chu, "owner"), (self.h_admin, "admin"),
            (self.h_kiemduyet, "moderator"), (self.h_thuong, "none"),
        ):
            d = self.client.get("/api/auth/me", headers=h).json()["profile"]
            self.assertEqual(d["admin_role"], muc)
            self.assertEqual(d["is_admin"], muc != "none")


class ApplicationQueueTest(Base):
    def test_hang_doi_va_bo_loc(self):
        self._tac_gia("a@x.local", "Đã Duyệt", duyet=True)
        self._tac_gia("b@x.local", "Đang Chờ", duyet=False)

        het = self.client.get("/api/admin/author-applications",
                              headers=self.h_admin).json()
        self.assertEqual(het["total"], 2)

        cho = self.client.get(
            "/api/admin/author-applications?status_filter=pending",
            headers=self.h_admin).json()
        self.assertEqual(cho["total"], 1)
        self.assertEqual(cho["applications"][0]["status"], "pending")

    def test_moi_don_kem_danh_tinh_nguoi_nop(self):
        # Khong kem thi giao dien phai goi them mot vong cho tung dong.
        self._tac_gia("a@x.local", "Đang Chờ", duyet=False)
        d = self.client.get("/api/admin/author-applications",
                            headers=self.h_admin).json()["applications"][0]
        self.assertEqual(d["user"]["display_name"], "Đang Chờ")
        self.assertIn("email", d["user"])          # duong quan tri: CO email
        self.assertIn("intro", d)

    def test_duyet_va_tu_choi(self):
        me, _ = self._tac_gia("a@x.local", "Chờ Duyệt", duyet=False)
        r = self.client.post(
            f"/api/admin/author-applications/{me['user_id']}/approve",
            headers=self.h_admin, json={"note": "Ổn."})
        self.assertEqual(r.status_code, 200)
        self.assertIs(self.identity.get_profile(me["user_id"]).author_status,
                      AuthorStatus.APPROVED)

        me2, _ = self._tac_gia("b@x.local", "Bị Từ Chối", duyet=False)
        r = self.client.post(
            f"/api/admin/author-applications/{me2['user_id']}/reject",
            headers=self.h_admin, json={"note": "Giới thiệu quá ngắn."})
        self.assertEqual(r.status_code, 200)
        self.assertIs(self.identity.get_profile(me2["user_id"]).author_status,
                      AuthorStatus.REJECTED)

    def test_tu_choi_KHONG_ghi_chu_bi_tu_choi(self):
        me, _ = self._tac_gia("a@x.local", "Chờ", duyet=False)
        r = self.client.post(
            f"/api/admin/author-applications/{me['user_id']}/reject",
            headers=self.h_admin, json={"note": "  "})
        self.assertEqual(r.status_code, 409)

    def test_buoc_chuyen_khong_hop_le_tra_409_chu_khong_500(self):
        me, _ = self._tac_gia("a@x.local", "Đã Duyệt", duyet=True)
        r = self.client.post(
            f"/api/admin/author-applications/{me['user_id']}/approve",
            headers=self.h_admin, json={"note": ""})
        self.assertEqual(r.status_code, 409)

    def test_nguoi_thuong_KHONG_duyet_duoc(self):
        me, _ = self._tac_gia("a@x.local", "Chờ", duyet=False)
        r = self.client.post(
            f"/api/admin/author-applications/{me['user_id']}/approve",
            headers=self.h_thuong, json={"note": "tôi tự duyệt tôi"})
        self.assertEqual(r.status_code, 403)
        self.assertIs(self.identity.get_profile(me["user_id"]).author_status,
                      AuthorStatus.PENDING)


class AuthorManagementTest(Base):
    def test_danh_sach_tac_gia_kem_hang_va_so_truyen(self):
        me, _ = self._tac_gia()
        self.store.create_novel(Novel(owner_id=me["user_id"], title="Đã đăng",
                                      state=PublishState.PUBLISHED))
        d = self.client.get("/api/admin/authors",
                            headers=self.h_admin).json()["authors"][0]
        self.assertEqual(d["published_novels"], 1)
        self.assertIn("rank", d)
        self.assertEqual(d["author_status"], "approved")

    def test_treo_va_phuc_hoi(self):
        me, _ = self._tac_gia()
        r = self.client.post(f"/api/admin/authors/{me['user_id']}/suspend",
                             headers=self.h_admin, json={"note": "Vi phạm."})
        self.assertEqual(r.status_code, 200)
        self.assertIs(self.identity.get_profile(me["user_id"]).author_status,
                      AuthorStatus.SUSPENDED)

        r = self.client.post(f"/api/admin/authors/{me['user_id']}/restore",
                             headers=self.h_admin, json={"note": "Đã xử lý."})
        self.assertEqual(r.status_code, 200)
        self.assertIs(self.identity.get_profile(me["user_id"]).author_status,
                      AuthorStatus.APPROVED)

    def test_treo_KHONG_dong_toi_noi_dung_da_co(self):
        """
        Rang buoc quan trong nhat cua thao tac treo.

        Mot tac gia bi treo van con doc gia. Rut truyen cua ho khoi tay nguoi doc
        la mot hinh phat danh vao nguoi khac — va xoa ban nhap thi la pha huy
        cong viec cua chinh ho.
        """
        me, h = self._tac_gia()
        da_dang = self.store.create_novel(Novel(
            owner_id=me["user_id"], title="Đã đăng", state=PublishState.PUBLISHED))
        ban_nhap = self.store.create_novel(Novel(
            owner_id=me["user_id"], title="Bản nháp", state=PublishState.DRAFT))

        self.client.post(f"/api/admin/authors/{me['user_id']}/suspend",
                         headers=self.h_admin, json={"note": "Vi phạm."})

        self.assertIs(self.store.get_novel(da_dang.novel_id).state,
                      PublishState.PUBLISHED)
        self.assertIs(self.store.get_novel(ban_nhap.novel_id).state,
                      PublishState.DRAFT)
        # Va truyen da xuat ban VAN nam trong danh sach cong khai.
        cong_khai = self.client.get("/api/novels").json()["novels"]
        self.assertIn(da_dang.novel_id, [n["novel_id"] for n in cong_khai])


class UserLookupTest(Base):
    def test_tim_nguoi_dung_co_email(self):
        self._tac_gia("timduoc@x.local", "Tìm Được")
        d = self.client.get("/api/admin/users?q=tim",
                            headers=self.h_admin).json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["users"][0]["email"], "timduoc@x.local")

    def test_email_KHONG_bao_gio_ra_duong_cong_khai(self):
        """Doi chieu hai duong canh nhau — day la cho de lech nhat."""
        me, h = self._tac_gia("rieng@x.local", "Riêng Tư")
        cong_khai = self.client.get("/api/users/riêng-tư")
        if cong_khai.status_code == 200:
            self.assertNotIn("email", cong_khai.json()["profile"])
        tim = self.client.get("/api/search/people?q=riêng").json()
        for p in tim["people"]:
            self.assertNotIn("email", p)

    def test_chi_tiet_nguoi_dung_kem_don_va_nhat_ky(self):
        me, _ = self._tac_gia("chitiet@x.local", "Chi Tiết")
        self.client.post(f"/api/admin/authors/{me['user_id']}/suspend",
                         headers=self.h_admin, json={"note": "Thử."})
        d = self.client.get(f"/api/admin/users/{me['user_id']}",
                            headers=self.h_admin).json()["user"]
        self.assertIsNotNone(d["application"])
        self.assertTrue(d["events"])
        self.assertEqual(d["events"][0]["action"], "author_suspended")

    def test_khong_ton_tai_tra_404(self):
        self.assertEqual(
            self.client.get("/api/admin/users/usr_khong_co",
                            headers=self.h_admin).status_code, 404)


class AuditLogTest(Base):
    def test_moi_thao_tac_deu_de_lai_mot_dong(self):
        me, _ = self._tac_gia("nhatky@x.local", "Nhật Ký", duyet=False)
        uid = me["user_id"]
        self.client.post(f"/api/admin/author-applications/{uid}/approve",
                         headers=self.h_admin, json={"note": "ok"})
        self.client.post(f"/api/admin/authors/{uid}/suspend",
                         headers=self.h_admin, json={"note": "vi phạm"})
        self.client.post(f"/api/admin/authors/{uid}/restore",
                         headers=self.h_admin, json={"note": "đã xử lý"})

        d = self.client.get("/api/admin/events", headers=self.h_admin).json()
        hanh_dong = [e["action"] for e in d["events"]]
        # Moi nhat truoc.
        self.assertEqual(hanh_dong[:3],
                         ["author_restored", "author_suspended", "author_approved"])

    def test_nhat_ky_ghi_dung_AI_lam(self):
        me, _ = self._tac_gia("ailam@x.local", "Ai Làm", duyet=False)
        self.client.post(
            f"/api/admin/author-applications/{me['user_id']}/approve",
            headers=self.h_admin, json={"note": "ok"})
        e = self.client.get("/api/admin/events",
                            headers=self.h_admin).json()["events"][0]
        self.assertEqual(e["actor_id"], self.admin["user_id"])
        self.assertEqual(e["target_user_id"], me["user_id"])
        self.assertEqual(e["note"], "ok")

    def test_nhat_ky_KHONG_co_duong_sua_hay_xoa(self):
        # Chi THEM. Mot nhat ky sua duoc la mot nhat ky khong dung de lam gi.
        duong = [(getattr(r, "path", ""), sorted(getattr(r, "methods", [])))
                 for r in server_main.app.routes
                 if "events" in getattr(r, "path", "")]
        for d, methods in duong:
            self.assertEqual([m for m in methods if m not in ("HEAD", "OPTIONS")],
                             ["GET"], d)

    def test_nhat_ky_KHONG_lo_ra_duong_cong_khai(self):
        me, _ = self._tac_gia("kin@x.local", "Kín", duyet=False)
        self.client.post(
            f"/api/admin/author-applications/{me['user_id']}/reject",
            headers=self.h_admin, json={"note": "ghi chú nội bộ"})
        # Nguoi nop DUOC doc ghi chu (ho can biet vi sao), nhung `actor_id` thi
        # khong: ai da duyet la viec noi bo.
        r = self.client.get("/api/creator/me",
                            headers=self._dang_ky("kin@x.local", "x")[1])
        self.assertNotIn("actor_id", r.text)


class NovelBrowserTest(Base):
    def test_liet_ke_truyen_kem_chu_va_so_chuong(self):
        me, h = self._tac_gia("chu@x.local", "Chủ Truyện")
        nid = self.client.post("/api/novels", headers=h,
                               json={"title": "Truyện A"}).json()["novel"]["novel_id"]
        self.client.post("/api/chapters", headers=h, json={
            "novel_id": nid, "title": "C1", "content": "x"})
        d = self.client.get("/api/admin/novels", headers=self.h_admin).json()
        row = next(n for n in d["novels"] if n["novel_id"] == nid)
        self.assertEqual(row["chapters"], 1)
        self.assertEqual(row["owner"]["display_name"], "Chủ Truyện")

    def test_loc_theo_trang_thai(self):
        me, h = self._tac_gia("loc@x.local", "Lọc")
        self.client.post("/api/novels", headers=h, json={"title": "Nháp"})
        d = self.client.get("/api/admin/novels?state=draft",
                            headers=self.h_admin).json()
        self.assertTrue(all(n["state"] == "draft" for n in d["novels"]))

    def test_KHONG_co_route_xoa_truyen_o_khu_quan_tri(self):
        """
        Backend chua co luong takedown nao an toan. Dat mot nut xoa len mot luong
        chua thiet ke la cach nhanh nhat de mat noi dung cua nguoi khac.
        """
        for r in server_main.app.routes:
            d = getattr(r, "path", "")
            if d.startswith("/api/admin/") and "novel" in d:
                methods = {m for m in getattr(r, "methods", set())
                           if m not in ("HEAD", "OPTIONS")}
                self.assertEqual(methods, {"GET"}, d)


class DashboardMoRongTest(Base):
    """
    Cac muc MOI cua /api/admin/overview (Admin Control Center V2, Phase 2,
    A1) — cong THEM ben canh cac truong cu, khong thay the.
    """

    def test_van_giu_cac_truong_cu(self):
        d = self.client.get("/api/admin/overview", headers=self.h_admin).json()
        for khoa in ("pending_applications", "approved_authors",
                    "rejected_applications", "suspended_authors",
                    "published_novels", "users_with_username",
                    "qualified_listens"):
            self.assertIn(khoa, d)

    def test_co_du_sau_muc_moi(self):
        d = self.client.get("/api/admin/overview", headers=self.h_admin).json()
        for khoa in ("users", "content", "product", "trusted_sources",
                    "traffic", "system"):
            self.assertIn(khoa, d)

    def test_dem_nguoi_dung_dung_va_moi_hom_nay(self):
        d = self.client.get("/api/admin/overview", headers=self.h_admin).json()
        # setUp da tao self.admin + self.thuong -> it nhat 2 nguoi.
        self.assertGreaterEqual(d["users"]["total"], 2)
        # Ca hai deu vua dang ky trong bai test nay -> phai nam trong "hom nay".
        self.assertGreaterEqual(d["users"]["new_today"], 2)
        self.assertGreaterEqual(d["users"]["new_7d"], d["users"]["new_today"])
        self.assertGreaterEqual(d["users"]["new_30d"], d["users"]["new_7d"])

    def test_truong_chua_theo_doi_tra_None_khong_bia_so_0(self):
        d = self.client.get("/api/admin/overview", headers=self.h_admin).json()
        self.assertIsNone(d["users"]["verified"])
        self.assertIsNone(d["users"]["unverified"])
        self.assertIsNone(d["users"]["suspended"])
        self.assertIsNone(d["product"]["image_generations_total"])

    def test_dem_noi_dung_dung_sau_khi_tao_truyen_chuong_series(self):
        me, h = self._tac_gia("dash@x.local", "Dash")
        truoc = self.client.get("/api/admin/overview",
                                headers=self.h_admin).json()
        nid = self.client.post("/api/novels", headers=h,
                               json={"title": "Truyện Dash"}).json()["novel"]["novel_id"]
        self.client.post("/api/chapters", headers=h, json={
            "novel_id": nid, "title": "C1", "content": "x"})
        sau = self.client.get("/api/admin/overview",
                              headers=self.h_admin).json()
        self.assertEqual(sau["content"]["novels_total"],
                         truoc["content"]["novels_total"] + 1)
        self.assertEqual(sau["content"]["chapters_total"],
                         truoc["content"]["chapters_total"] + 1)

    def test_trusted_sources_va_traffic_chua_cau_hinh(self):
        """Phan B (Trusted Video Sources) va Cloudflare traffic analytics
        CHUA xay/CHUA co credential — phai bao ro, khong bia du lieu."""
        d = self.client.get("/api/admin/overview", headers=self.h_admin).json()
        self.assertFalse(d["trusted_sources"]["configured"])
        self.assertFalse(d["traffic"]["configured"])
        self.assertIn("not configured", d["traffic"]["message"])

    def test_moderator_van_xem_duoc_dashboard(self):
        """Dashboard dung `admin_profile` (bat ky vai tro nao) — MODERATOR
        van can thay tong quan de lam viec, chi khong quan ly duoc user/
        trusted source (xem AdminRoleModelTest)."""
        prof_mod, h_mod = self._dang_ky("dashmod@fanfic.local", "Dash Mod")
        self._dat_vai_tro(admin=[self.admin["user_id"]],
                          moderator=[prof_mod["user_id"]])
        self.assertEqual(
            self.client.get("/api/admin/overview", headers=h_mod).status_code,
            200)


class HoSoKemQuyenTest(Base):
    """
    Bit `is_admin` trong ho so CHINH CHU — nguon duy nhat de giao dien quyet
    dinh co ve loi vao "Quản trị" hay khong.

    Vi sao phai co: khong co bit nay thi frontend chi con cach nhung email/id
    quan tri vao ma nguon — mot danh sach quan tri thu hai, va no SE lech voi
    `FAS_ADMIN_USER_IDS` that. May chu tra loi, giao dien chi ve.
    """

    def test_admin_thay_is_admin_true(self):
        r = self.client.get("/api/auth/me", headers=self.h_admin)
        self.assertIs(r.json()["profile"]["is_admin"], True)

    def test_nguoi_thuong_thay_is_admin_false(self):
        r = self.client.get("/api/auth/me", headers=self.h_thuong)
        self.assertIs(r.json()["profile"]["is_admin"], False)

    def test_login_cung_mang_bit(self):
        """Dang nhap xong phai biet ngay, khong doi den lan goi `me` ke tiep."""
        r = self.client.post("/api/auth/login", json={
            "email": "admin@fanfic.local", "password": "matkhau123"})
        self.assertIs(r.json()["profile"]["is_admin"], True)

    def test_ho_so_cong_khai_khong_lo_is_admin(self):
        """
        Trang cong khai van la danh sach cho phep — ai la quan tri khong phai
        viec cua nguoi xem trang.
        """
        self.client.put("/api/creator/username", headers=self.h_admin,
                        json={"username": "quan-tri-vien"})
        r = self.client.get("/api/users/quan-tri-vien")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("is_admin", r.json()["profile"])


if __name__ == "__main__":
    unittest.main()
