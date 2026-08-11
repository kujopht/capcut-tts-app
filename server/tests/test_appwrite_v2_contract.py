"""
HOP DONG giua kho mock va kho Appwrite cho cac mo hinh V2.

VI SAO CAN: toan bo tinh nang V2 va khu quan tri duoc kiem thu tren kho MOCK.
Neu ban Appwrite lech ngu nghia du chi mot cho — tra `None` thay vi nem, dem sai
tong so, hay cho phep ghi hai lan cung mot khoa — thi moi bai test kia van xanh
va he thong van hong o production.

Bo test nay chay CUNG mot kich ban tren CA HAI kho va doi soat ket qua.

Appwrite duoc thay bang mot ban gia lap TRONG BO NHO noi dung REST that: nhan
`request(method, url, json, params, headers)`, hieu `documentId`, cuong che tinh
DUY NHAT cua `rowId`, va hieu cac truy van JSON ma `appwrite_store` sinh ra. No
khong phai Appwrite that — cac han che duoc ghi ro o `docs/APPWRITE_V2.md` — nhung
no du de bat dung loai loi ma bo test nay ton tai vi no.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List

from server.adapters import MockMetadataStore
from server.appwrite_store import AppwriteMetadataStore
from server.config import AppwriteSettings
from server.domain import (
    AuthorApplication,
    AuthorStats,
    AuthorStatus,
    ListenCredit,
    ModerationEvent,
)


class FakeAppwrite:
    """
    Ban gia lap REST cua Appwrite, chi du cho cac bang V2.

    CUONG CHE TINH DUY NHAT cua `documentId` — day la thu quan trong nhat no phai
    lam dung: ca co che chong farm dua vao viec Appwrite tu choi hang thu hai.
    """

    def __init__(self) -> None:
        #: collection -> {rowId: data}
        self.rows: Dict[str, Dict[str, Dict[str, Any]]] = {}
        #: Quyen da cap cho tung hang — de test kiem `moderation_events` kin.
        self.perms: Dict[str, List[str]] = {}

    # -- REST ----------------------------------------------------------------

    def request(self, method: str, url: str, json: Any = None,
                params: Any = None, headers: Any = None) -> Dict[str, Any]:
        phan = url.split("/collections/")[-1]
        col = phan.split("/")[0]
        doc = phan.split("/documents/")[1] if "/documents/" in phan else ""
        bang = self.rows.setdefault(col, {})

        if method == "POST":
            rid = str(json.get("documentId"))
            if rid in bang:
                # Appwrite tra 409; `_call` doi MOI ma >=400 thanh NotFoundError.
                raise _Loi409(f"Document with the requested ID already exists: {rid}")
            bang[rid] = dict(json.get("data") or {})
            self.perms[f"{col}/{rid}"] = list(json.get("permissions") or [])
            return {"$id": rid, **bang[rid]}

        if method == "GET" and doc:
            if doc not in bang:
                raise _Loi404("Document not found")
            return {"$id": doc, **bang[doc]}

        if method == "GET":
            return self._truy_van(bang, (params or {}).get("queries[]") or [])

        if method == "PATCH":
            if doc not in bang:
                raise _Loi404("Document not found")
            bang[doc].update(dict(json.get("data") or {}))
            return {"$id": doc, **bang[doc]}

        raise AssertionError(f"chưa mô phỏng: {method} {url}")

    # -- truy van ------------------------------------------------------------

    def _truy_van(self, bang: Dict[str, Dict[str, Any]],
                  queries: List[str]) -> Dict[str, Any]:
        import json as _json

        rows = [{"$id": k, **v} for k, v in bang.items()]
        limit, offset, order = 25, 0, None

        for q in queries:
            d = _json.loads(q)
            m, attr, vals = d.get("method"), d.get("attribute"), d.get("values") or []
            if m == "equal":
                rows = [r for r in rows if r.get(attr) in vals]
            elif m == "notEqual":
                rows = [r for r in rows if r.get(attr) not in vals]
            elif m == "contains":
                rows = [r for r in rows
                        if vals and str(vals[0]).lower() in str(r.get(attr, "")).lower()]
            elif m == "or":
                giu = []
                for r in rows:
                    for dk in d.get("values") or []:
                        a, v = dk.get("attribute"), (dk.get("values") or [""])[0]
                        if str(v).lower() in str(r.get(a, "")).lower():
                            giu.append(r)
                            break
                rows = giu
            elif m == "orderAsc":
                order = (attr, False)
            elif m == "orderDesc":
                order = (attr, True)
            elif m == "limit":
                limit = int(vals[0])
            elif m == "offset":
                offset = int(vals[0])

        if order:
            rows.sort(key=lambda r: str(r.get(order[0], "")), reverse=order[1])
        # `total` DOC LAP voi limit/offset — day la hanh vi that cua Appwrite, va
        # code phan trang dua vao no.
        return {"documents": rows[offset:offset + limit], "total": len(rows)}


class _Loi404(Exception):
    pass


class _Loi409(Exception):
    pass


def _bo_client(fake: FakeAppwrite):
    """Boc ban gia lap thanh doi tuong ma `AppwriteMetadataStore` mong doi."""

    class Client:
        def request(self, method, url, json=None, params=None, headers=None):
            try:
                return fake.request(method, url, json=json, params=params,
                                    headers=headers)
            except (_Loi404, _Loi409) as exc:
                from server.adapters import NotFoundError
                raise NotFoundError(str(exc)) from exc

    return Client()


def _kho_appwrite(fake: FakeAppwrite) -> AppwriteMetadataStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteMetadataStore(cfg, client=_bo_client(fake))
    # Bo qua buoc hoi schema: ban gia lap khong co endpoint metadata, va
    # `_supported_fields` tra None nghia la "gui het" — dung nhu ta muon o day.
    kho._attrs_cache = {}
    return kho


BAY_GIO = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class HopDongV2(unittest.TestCase):
    """
    Moi bai duoi day chay tren CA HAI kho.

    `_cac_kho()` tra ve cap `(ten, kho)` de thong bao that bai noi ro ban nao
    lech — "mock" hay "appwrite".
    """

    def _cac_kho(self):
        return [("mock", MockMetadataStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # -- don tac gia ---------------------------------------------------------

    def test_chua_co_don_thi_tra_None(self):
        for ten, kho in self._cac_kho():
            self.assertIsNone(kho.get_application("usr_1"), ten)

    def test_tao_roi_doc_lai_giu_nguyen_moi_truong(self):
        for ten, kho in self._cac_kho():
            app = AuthorApplication(
                user_id="usr_1", pen_name="Kẻ Dệt Mộng",
                bio="Viết fanfic.", genres=["One Piece", "Phiêu lưu"],
                intro="Tôi viết đã ba năm.", accepted_rules=True,
                status=AuthorStatus.PENDING, attempts=2,
            )
            kho.save_application(app)
            lai = kho.get_application("usr_1")
            self.assertIsNotNone(lai, ten)
            self.assertEqual(lai.pen_name, "Kẻ Dệt Mộng", ten)
            self.assertEqual(lai.genres, ["One Piece", "Phiêu lưu"], ten)
            self.assertIs(lai.status, AuthorStatus.PENDING, ten)
            self.assertEqual(lai.attempts, 2, ten)
            self.assertTrue(lai.accepted_rules, ten)

    def test_nop_lai_la_GHI_DE_chu_khong_tao_ban_thu_hai(self):
        for ten, kho in self._cac_kho():
            kho.save_application(AuthorApplication(user_id="usr_1", pen_name="A"))
            kho.save_application(AuthorApplication(user_id="usr_1", pen_name="B"))
            rows, total = kho.list_applications()
            self.assertEqual(total, 1, ten)
            self.assertEqual(rows[0].pen_name, "B", ten)

    def test_loc_theo_trang_thai_va_dem_dung_tong(self):
        for ten, kho in self._cac_kho():
            kho.save_application(AuthorApplication(user_id="u1", pen_name="A",
                                                   status=AuthorStatus.PENDING))
            kho.save_application(AuthorApplication(user_id="u2", pen_name="B",
                                                   status=AuthorStatus.APPROVED))
            kho.save_application(AuthorApplication(user_id="u3", pen_name="C",
                                                   status=AuthorStatus.PENDING))
            rows, total = kho.list_applications(status=AuthorStatus.PENDING)
            self.assertEqual(total, 2, ten)
            self.assertEqual({r.user_id for r in rows}, {"u1", "u3"}, ten)

    def test_hang_doi_sap_CU_NHAT_TRUOC(self):
        # Thu tu duy nhat khong lam ai bi bo quen vinh vien.
        for ten, kho in self._cac_kho():
            for i, moc in enumerate(["2026-08-01T00:00:00+00:00",
                                     "2026-08-03T00:00:00+00:00",
                                     "2026-08-02T00:00:00+00:00"]):
                kho.save_application(AuthorApplication(
                    user_id=f"u{i}", pen_name=str(i), created_at=moc))
            rows, _ = kho.list_applications()
            self.assertEqual([r.user_id for r in rows], ["u0", "u2", "u1"], ten)

    def test_phan_trang_giu_dung_tong_so(self):
        for ten, kho in self._cac_kho():
            for i in range(5):
                kho.save_application(AuthorApplication(
                    user_id=f"u{i}", pen_name=str(i),
                    created_at=f"2026-08-0{i + 1}T00:00:00+00:00"))
            rows, total = kho.list_applications(limit=2, offset=2)
            self.assertEqual(total, 5, ten)
            self.assertEqual(len(rows), 2, ten)

    # -- uy tin --------------------------------------------------------------

    def test_chua_co_thong_ke_thi_tra_ban_RONG_chu_khong_nem(self):
        for ten, kho in self._cac_kho():
            s = kho.get_stats("usr_1")
            self.assertEqual(s.qualified_listens, 0, ten)
            self.assertEqual(s.user_id, "usr_1", ten)

    def test_cong_don_va_doc_lai(self):
        for ten, kho in self._cac_kho():
            kho.add_qualified_listen("usr_1", 1)
            kho.add_qualified_listen("usr_1", 1)
            self.assertEqual(kho.get_stats("usr_1").qualified_listens, 2, ten)

    def test_khong_bao_gio_am(self):
        for ten, kho in self._cac_kho():
            kho.add_qualified_listen("usr_1", -5)
            self.assertEqual(kho.get_stats("usr_1").qualified_listens, 0, ten)

    def test_ghi_de_thong_ke(self):
        for ten, kho in self._cac_kho():
            kho.save_stats(AuthorStats(user_id="u1", qualified_listens=999))
            kho.save_stats(AuthorStats(user_id="u1", qualified_listens=7))
            self.assertEqual(kho.get_stats("u1").qualified_listens, 7, ten)

    # -- luot nghe hop le ----------------------------------------------------

    def test_KHOA_TAT_DINH_chan_lan_ghi_thu_hai(self):
        """
        Rang buoc quan trong nhat cua ca tep nay.

        Ca co che chong farm dua vao viec kho tu choi hang thu hai co cung
        `credit_id`. Neu ban Appwrite khong cuong che dieu do thi mot cuoc dua se
        tao hai lan tinh, va khong bai test nao khac bat duoc.
        """
        for ten, kho in self._cac_kho():
            c = ListenCredit(listener_id="b", author_id="a", chapter_id="chp",
                             credit_id="lst_khoa_co_dinh")
            self.assertTrue(kho.create_credit_once(c), ten)
            self.assertFalse(kho.create_credit_once(c), ten)

    def test_moc_lan_tinh_gan_nhat(self):
        for ten, kho in self._cac_kho():
            kho.create_credit_once(ListenCredit(
                listener_id="b", author_id="a", chapter_id="chp",
                credit_id="k1", created_at="2026-08-01T00:00:00+00:00"))
            kho.create_credit_once(ListenCredit(
                listener_id="b", author_id="a", chapter_id="chp",
                credit_id="k2", created_at="2026-08-05T00:00:00+00:00"))
            self.assertEqual(kho.last_credit_at("b", "chp"),
                             "2026-08-05T00:00:00+00:00", ten)

    def test_khong_co_lan_nao_thi_tra_None(self):
        for ten, kho in self._cac_kho():
            self.assertIsNone(kho.last_credit_at("b", "chp"), ten)

    def test_moc_KHONG_lan_sang_chuong_khac_hay_nguoi_khac(self):
        for ten, kho in self._cac_kho():
            kho.create_credit_once(ListenCredit(
                listener_id="b", author_id="a", chapter_id="chp_1", credit_id="k1"))
            self.assertIsNone(kho.last_credit_at("b", "chp_2"), ten)
            self.assertIsNone(kho.last_credit_at("c", "chp_1"), ten)

    def test_dem_lai_tu_bang_su_that(self):
        for ten, kho in self._cac_kho():
            for i in range(3):
                kho.create_credit_once(ListenCredit(
                    listener_id=f"b{i}", author_id="a", chapter_id="chp",
                    credit_id=f"k{i}"))
            kho.create_credit_once(ListenCredit(
                listener_id="b9", author_id="KHAC", chapter_id="chp",
                credit_id="k9"))
            self.assertEqual(kho.count_credits("a"), 3, ten)

    # -- nhat ky -------------------------------------------------------------

    def test_ghi_va_doc_nhat_ky(self):
        for ten, kho in self._cac_kho():
            kho.record_event(ModerationEvent(
                action="author_approved", target_user_id="u1",
                actor_id="admin_1", note="ok"))
            rows, total = kho.list_events()
            self.assertEqual(total, 1, ten)
            self.assertEqual(rows[0].action, "author_approved", ten)
            self.assertEqual(rows[0].actor_id, "admin_1", ten)
            self.assertEqual(rows[0].note, "ok", ten)

    def test_nhat_ky_MOI_NHAT_TRUOC(self):
        for ten, kho in self._cac_kho():
            for i, moc in enumerate(["2026-08-01T00:00:00.100000+00:00",
                                     "2026-08-01T00:00:00.300000+00:00",
                                     "2026-08-01T00:00:00.200000+00:00"]):
                kho.record_event(ModerationEvent(
                    action="author_approved", target_user_id=f"u{i}",
                    event_id=f"e{i}", created_at=moc))
            rows, _ = kho.list_events()
            self.assertEqual([r.target_user_id for r in rows],
                             ["u1", "u2", "u0"], ten)

    def test_loc_nhat_ky_theo_nguoi_bi_tac_dong(self):
        for ten, kho in self._cac_kho():
            kho.record_event(ModerationEvent(action="author_approved",
                                             target_user_id="u1", event_id="e1"))
            kho.record_event(ModerationEvent(action="author_suspended",
                                             target_user_id="u2", event_id="e2"))
            rows, total = kho.list_events(target_user_id="u1")
            self.assertEqual(total, 1, ten)
            self.assertEqual(rows[0].target_user_id, "u1", ten)

    def test_KHONG_kho_nao_co_duong_sua_hay_xoa_nhat_ky(self):
        # Chi THEM. Mot nhat ky sua duoc la mot nhat ky khong dung de lam gi.
        for ten, kho in self._cac_kho():
            for cam in ("update_event", "delete_event", "save_event"):
                self.assertFalse(hasattr(kho, cam), f"{ten}.{cam}")


class QuyenHangTest(unittest.TestCase):
    """Quyen tren tung hang — ban Appwrite, vi mock khong co khai niem nay."""

    def test_nhat_ky_KHONG_cap_quyen_doc_cho_bat_ky_client_nao(self):
        """
        Hang nhat ky chua ghi chu noi bo va `actor_id` cua quan tri. Moi duong
        doc hop le deu di qua backend bang API key, nen danh sach quyen rong
        khong lam hong chuc nang nao — no chi dong duong doc THANG tu trinh duyet.
        """
        fake = FakeAppwrite()
        kho = _kho_appwrite(fake)
        kho.record_event(ModerationEvent(action="author_rejected",
                                         target_user_id="u1", event_id="e1",
                                         note="ghi chú nội bộ"))
        self.assertEqual(fake.perms["moderation_events/e1"], [])

    def test_cac_bang_khac_VAN_cap_quyen_doc_cho_chinh_chu(self):
        # Khong duoc lam yeu di mo hinh quyen dang co: chu so huu van doc duoc
        # ban ghi cua chinh minh.
        fake = FakeAppwrite()
        kho = _kho_appwrite(fake)
        kho.save_application(AuthorApplication(user_id="u1", pen_name="A"))
        kho.save_stats(AuthorStats(user_id="u1"))
        kho.create_credit_once(ListenCredit(listener_id="u1", author_id="a",
                                            chapter_id="c", credit_id="k1"))
        self.assertEqual(fake.perms["author_applications/u1"],
                         ['read("user:u1")'])
        self.assertEqual(fake.perms["author_stats/u1"], ['read("user:u1")'])
        self.assertEqual(fake.perms["listen_credits/k1"], ['read("user:u1")'])


class TruongLuuTruTest(unittest.TestCase):
    """
    `to_dict()` cua domain phai KHOP voi cac cot da khai.

    Cung loai loi ma `test_appwrite_schema_contract.py` bat cho cac bang cu:
    gui mot thuoc tinh chua ton tai thi Appwrite tu choi CA document.
    """

    def test_moi_truong_cua_ban_ghi_V2_deu_co_cot(self):
        from server.appwrite_store import (
            COL_APPLICATIONS, COL_CREDITS, COL_EVENTS, COL_STATS,
            PERSISTED_FIELDS,
        )

        mau = {
            COL_APPLICATIONS: AuthorApplication(user_id="u", pen_name="p").to_dict(),
            COL_STATS: AuthorStats(user_id="u").to_dict(),
            COL_CREDITS: ListenCredit(listener_id="l", author_id="a",
                                      chapter_id="c").to_dict(),
            COL_EVENTS: ModerationEvent(action="author_approved",
                                        target_user_id="u").to_dict(),
        }
        for col, data in mau.items():
            thua = set(data) - set(PERSISTED_FIELDS[col])
            self.assertEqual(thua, set(),
                             f"{col}: trường không có cột tương ứng: {thua}")

    def test_moi_cot_deu_duoc_mot_ban_ghi_sinh_ra(self):
        # Chieu nguoc lai: mot cot khong bao gio duoc ghi la mot cot thua.
        from server.appwrite_store import (
            COL_APPLICATIONS, COL_CREDITS, COL_EVENTS, COL_STATS,
            PERSISTED_FIELDS,
        )

        mau = {
            COL_APPLICATIONS: AuthorApplication(user_id="u", pen_name="p").to_dict(),
            COL_STATS: AuthorStats(user_id="u").to_dict(),
            COL_CREDITS: ListenCredit(listener_id="l", author_id="a",
                                      chapter_id="c").to_dict(),
            COL_EVENTS: ModerationEvent(action="author_approved",
                                        target_user_id="u").to_dict(),
        }
        for col, data in mau.items():
            thieu = set(PERSISTED_FIELDS[col]) - set(data)
            self.assertEqual(thieu, set(), f"{col}: cột không ai ghi: {thieu}")

    def test_schema_setup_khai_du_bon_bang_V2(self):
        from scripts.setup_appwrite import SCHEMA
        from server.appwrite_store import (
            COL_APPLICATIONS, COL_CREDITS, COL_EVENTS, COL_STATS,
        )

        for col in (COL_APPLICATIONS, COL_STATS, COL_CREDITS, COL_EVENTS):
            self.assertIn(col, SCHEMA, f"schema thiếu bảng {col}")
            khai = {a[0] for a in SCHEMA[col]["attributes"]}
            from server.appwrite_store import PERSISTED_FIELDS
            self.assertEqual(khai, set(PERSISTED_FIELDS[col]),
                             f"{col}: schema và PERSISTED_FIELDS lệch nhau")


if __name__ == "__main__":
    unittest.main()
