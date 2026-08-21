"""
Xoa tai khoan theo yeu cau cua chinh nguoi dung — `DELETE /api/account`.

BA tang duoc kiem o day, va chung kiem ba thu khac nhau:

  1. HOP DONG kho metadata/xa hoi — cung kich ban chay tren CA HAI ban
     (`MockMetadataStore` va `AppwriteMetadataStore` qua ban gia lap REST cua
     `test_appwrite_v2_contract.py`). Day la phan quan trong nhat: chinh sach
     luu tru (xoa / giu / giu-nhung-an-danh) chi dung neu CA HAI ban lam giong
     nhau — mot ban lech la du lieu ca nhan o lai tren production trong khi
     test van xanh.
  2. HOP DONG kho gamification — cung ly do, hai ban.
  3. TANG HTTP — thu tu don (danh tinh SAU CUNG), tinh idempotent khi goi lai,
     va rang buoc quan trong nhat: xoa tai khoan nay KHONG duoc dong toi du
     lieu cua nguoi khac.

Chinh sach day du o `MetadataStore.delete_account` (server/adapters.py).
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.appwrite_gamification_store import AppwriteGamificationStore
from server.appwrite_store import AppwriteMetadataStore
from server.config import AppwriteSettings
from server.domain import (
    AN_DANH_DA_XOA,
    AudioTrack,
    AuthorApplication,
    AuthorStats,
    AuthorStatus,
    Chapter,
    ContentReport,
    ListenCredit,
    ModerationEvent,
    Notification,
    NotificationKind,
    Novel,
    Post,
    PostLike,
    StoryFollow,
    TtsJob,
    UserFollow,
)
from server.gamification_domain import (
    CosmeticInventoryItem,
    QuestProgress,
    ReadingStreak,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
)
from server.gamification_store import MockGamificationStore
from server.social import (
    notification_key,
    post_like_key,
    report_key,
    story_follow_key,
    user_follow_key,
)
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _bo_client
from server.translation_domain import ProviderConnection
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore

#: Nguoi bi xoa, va mot nguoi NGOAI CUOC phai khong bi sut mot ban ghi nao.
TOI = "usr_toi"
NGUOI_KHAC = "usr_khac"


def _kho_appwrite(fake: FakeAppwrite) -> AppwriteMetadataStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteMetadataStore(cfg, client=_bo_client(fake))
    # `_supported_fields` tra None = "gui het" — ban gia lap khong co endpoint
    # metadata. Cung quy uoc voi `test_appwrite_v2_contract._kho_appwrite`.
    kho._attrs_cache = {}
    return kho


def _kho_gamification_appwrite(fake: FakeAppwrite) -> AppwriteGamificationStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteGamificationStore(cfg, client=_bo_client(fake))
    kho._attrs_cache = {}
    return kho


def _gieo_noi_dung(kho, uid: str) -> Dict[str, Any]:
    """Mot nguoi dung "day du": truyen, chuong, job, audio, bai dang, binh
    luan, thich, theo doi, thong bao, uy tin, don tac gia, bao cao.

    MOI id deu TAT DINH theo `uid` (khong dung `new_id` ngau nhien): nho vay
    `test_hai_kho_bao_cao_giong_het` so sanh duoc TRUC TIEP bao cao cua hai
    kho, ke ca danh sach khoa doi tuong."""
    novel = kho.create_novel(Novel(owner_id=uid, title=f"Truyen cua {uid}",
                                   novel_id=f"nov_{uid}",
                                   cover_key=f"covers/{uid}/anh.webp"))
    chuong = [
        kho.create_chapter(Chapter(novel_id=novel.novel_id, owner_id=uid,
                                   chapter_id=f"chp_{uid}_{i}",
                                   title=f"Chuong {i}", content="noi dung",
                                   order_index=i))
        for i in (1, 2)
    ]
    for i, c in enumerate(chuong):
        kho.create_job(TtsJob(owner_id=uid, chapter_id=c.chapter_id,
                              job_id=f"job_{uid}_{i}",
                              voice_id="v1", content_hash=f"h{i}{uid}"))
        kho.create_track(AudioTrack(
            chapter_id=c.chapter_id, owner_id=uid, voice_id="v1",
            track_id=f"trk_{uid}_{i}",
            object_key=f"audio/{uid}/{c.chapter_id}.mp3",
            content_hash=f"h{i}{uid}",
            transcript_key=f"audio/{uid}/{c.chapter_id}.transcript.json"))

    bai = kho.create_post(Post(author_user_id=uid, text="xin chao",
                               post_id=f"pst_{uid}",
                               images=[{"key": f"posts/{uid}/anh.webp",
                                        "mime": "image/webp", "width": 10,
                                        "height": 10, "bytes": 100}]))
    binh_luan = kho.create_comment(_binh_luan(uid, bai.post_id))
    kho.like_post(PostLike(post_id=bai.post_id, user_id=uid,
                           like_id=post_like_key(uid, bai.post_id)))
    kho.follow_user(UserFollow(follower_id=uid, target_id=NGUOI_KHAC,
                               follow_id=user_follow_key(uid, NGUOI_KHAC)))
    kho.follow_story(StoryFollow(follower_id=uid, novel_id="nov_cua_nguoi_khac",
                                 follow_id=story_follow_key(
                                     uid, "nov_cua_nguoi_khac")))
    kho.create_notification_once(Notification(
        user_id=uid, kind=NotificationKind.FOLLOW, actor_id=NGUOI_KHAC,
        notification_id=notification_key(uid, "follow", NGUOI_KHAC)))
    kho.save_stats(AuthorStats(user_id=uid, qualified_listens=3))
    kho.save_application(AuthorApplication(
        user_id=uid, pen_name="But danh that", bio="Tieu su that",
        intro="Loi gioi thieu that", status=AuthorStatus.APPROVED,
        reviewer_note="Duyet vi ho viet tot.", decided_at="2026-08-01T00:00:00+00:00"))
    kho.create_report_once(ContentReport(
        reporter_id=uid, target_kind="post", target_id="pst_cua_nguoi_khac",
        target_owner_id=NGUOI_KHAC, detail="Bai nay spam.",
        report_id=report_key(uid, "post", "pst_cua_nguoi_khac")))
    return {"novel": novel, "chuong": chuong, "bai": bai,
            "binh_luan": binh_luan}


def _binh_luan(uid: str, post_id: str):
    from server.domain import Comment

    return Comment(post_id=post_id, author_user_id=uid, text="mot binh luan",
                   comment_id=f"cmt_{uid}")


class HopDongXoaTaiKhoan(unittest.TestCase):
    """Moi bai duoi day chay tren CA HAI kho — `ten` bao ro ban nao lech."""

    def _cac_kho(self):
        return [("mock", MockMetadataStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # ================================================== xoa het noi dung

    def test_xoa_het_noi_dung_cua_chinh_nguoi_dung(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                du_lieu = _gieo_noi_dung(kho, TOI)
                bc = kho.delete_account(TOI)

                self.assertEqual(bc["novels"], 1, ten)
                self.assertEqual(bc["chapters"], 2, ten)
                self.assertEqual(bc["tts_jobs"], 2, ten)
                self.assertEqual(bc["audio_tracks"], 2, ten)
                self.assertEqual(bc["posts"], 1, ten)
                self.assertEqual(bc["comments"], 1, ten)
                self.assertEqual(bc["post_likes"], 1, ten)
                self.assertEqual(bc["user_follows"], 1, ten)
                self.assertEqual(bc["story_follows"], 1, ten)
                self.assertEqual(bc["notifications"], 1, ten)
                self.assertEqual(bc["author_stats"], 1, ten)

                self.assertEqual(kho.list_novels(owner_id=TOI), [], ten)
                self.assertEqual(kho.chapters_for_owner(TOI), [], ten)
                self.assertEqual(kho.list_jobs(TOI), [], ten)
                for c in du_lieu["chuong"]:
                    self.assertEqual(kho.tracks_for_chapter(c.chapter_id), [], ten)
                self.assertIsNone(kho.get_post(du_lieu["bai"].post_id), ten)
                self.assertIsNone(
                    kho.get_comment(du_lieu["binh_luan"].comment_id), ten)
                self.assertFalse(
                    kho.has_liked(post_like_key(TOI, du_lieu["bai"].post_id)), ten)
                self.assertFalse(
                    kho.is_following_user(user_follow_key(TOI, NGUOI_KHAC)), ten)
                self.assertFalse(
                    kho.is_following_story(
                        story_follow_key(TOI, "nov_cua_nguoi_khac")), ten)
                self.assertEqual(kho.count_unread(TOI), 0, ten)
                self.assertEqual(kho.get_stats(TOI).qualified_listens, 0, ten)

    def test_bao_cao_khoa_doi_tuong_de_nguoi_goi_don_kho_tep(self):
        """Kho metadata KHONG biet gi ve R2 — no chi bao lai khoa nao can xoa.
        Thieu mot khoa o day la mot object mo coi vinh vien trong kho."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                du_lieu = _gieo_noi_dung(kho, TOI)
                khoa = set(kho.delete_account(TOI)["object_keys"])

                self.assertIn(f"covers/{TOI}/anh.webp", khoa, ten)
                self.assertIn(f"posts/{TOI}/anh.webp", khoa, ten)
                for c in du_lieu["chuong"]:
                    self.assertIn(f"audio/{TOI}/{c.chapter_id}.mp3", khoa, ten)
                    self.assertIn(
                        f"audio/{TOI}/{c.chapter_id}.transcript.json", khoa, ten)

    def test_khong_dung_toi_du_lieu_cua_nguoi_khac(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                cua_toi = _gieo_noi_dung(kho, TOI)
                cua_ho = _gieo_noi_dung(kho, NGUOI_KHAC)
                # Nguoi khac theo doi CHINH nguoi sap bi xoa: canh do phai mat
                # (no tro toi mot tai khoan khong con), nhung moi thu khac cua
                # ho thi khong.
                kho.follow_user(UserFollow(
                    follower_id=NGUOI_KHAC, target_id=TOI,
                    follow_id=user_follow_key(NGUOI_KHAC, TOI)))

                bc = kho.delete_account(TOI)

                self.assertEqual(bc["user_follows"], 2, ten)
                self.assertFalse(
                    kho.is_following_user(user_follow_key(NGUOI_KHAC, TOI)), ten)
                self.assertEqual(len(kho.list_novels(owner_id=NGUOI_KHAC)), 1, ten)
                self.assertEqual(len(kho.chapters_for_owner(NGUOI_KHAC)), 2, ten)
                self.assertEqual(len(kho.list_jobs(NGUOI_KHAC)), 2, ten)
                for c in cua_ho["chuong"]:
                    self.assertEqual(len(kho.tracks_for_chapter(c.chapter_id)),
                                     1, ten)
                self.assertIsNotNone(kho.get_post(cua_ho["bai"].post_id), ten)
                self.assertIsNotNone(
                    kho.get_comment(cua_ho["binh_luan"].comment_id), ten)
                self.assertTrue(
                    kho.has_liked(post_like_key(NGUOI_KHAC, cua_ho["bai"].post_id)),
                    ten)
                self.assertEqual(kho.get_stats(NGUOI_KHAC).qualified_listens, 3, ten)
                self.assertEqual(kho.count_unread(NGUOI_KHAC), 1, ten)
                # Truyen cua nguoi khac khong bien mat vi mot chuong trung ten.
                self.assertIsNotNone(kho.get_novel(cua_ho["novel"].novel_id), ten)
                # Va bai cua chinh minh thi da mat.
                self.assertIsNone(kho.get_post(cua_toi["bai"].post_id), ten)

    def test_goi_lan_hai_khong_nem_va_khong_con_gi_de_xoa(self):
        """Request bi thu lai khong duoc thanh 500 — moi buoc IDEMPOTENT.

        HAI bo dem `*_anonymized` KHONG ve 0 giong nhau, va do la dung:

          - don tac gia tim theo `rowId` (= `user_id`) nen lan hai VAN thay
            hang do va ghi lai dung gia tri an danh — mot phep TU CHUA neu lan
            truoc hong nua duong, cung triet ly voi `publish_novel` ap lai
            quyen moi lan goi;
          - bao cao tim theo `reporter_id`, ma truong do vua bi thay bang dau
            an danh, nen lan hai khong con hang nao khop -> 0.

        Ca hai deu ve CUNG mot trang thai cuoi: hang o lai, van ban nhan dang
        da bi go."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                _gieo_noi_dung(kho, TOI)
                kho.delete_account(TOI)
                lai = kho.delete_account(TOI)
                self.assertEqual(lai["object_keys"], [], ten)
                for bang, so in lai.items():
                    if bang == "object_keys" or bang.endswith("_anonymized"):
                        continue
                    self.assertEqual(so, 0, f"{ten}/{bang}")
                self.assertEqual(lai["applications_anonymized"], 1, ten)
                self.assertEqual(lai["reports_anonymized"], 0, ten)
                self.assertEqual(kho.get_application(TOI).pen_name,
                                 AN_DANH_DA_XOA, ten)
                bao = kho.get_report(report_key(TOI, "post", "pst_cua_nguoi_khac"))
                self.assertIsNotNone(bao, ten)
                self.assertEqual(bao.reporter_id, AN_DANH_DA_XOA, ten)

    def test_nguoi_dung_khong_co_gi_thi_khong_nem(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bc = kho.delete_account("usr_chua_lam_gi")
                self.assertEqual(bc["novels"], 0, ten)

    def test_hai_kho_bao_cao_giong_het(self):
        """Mot ban tu them/bo mot khoa bao cao la mot lech khong ai thay ngay."""
        mock_kho = MockMetadataStore()
        aw_kho = _kho_appwrite(FakeAppwrite())
        _gieo_noi_dung(mock_kho, TOI)
        _gieo_noi_dung(aw_kho, TOI)
        bc_mock = mock_kho.delete_account(TOI)
        bc_aw = aw_kho.delete_account(TOI)
        self.assertEqual(sorted(bc_mock.keys()), sorted(bc_aw.keys()))
        for khoa in bc_mock:
            if khoa == "object_keys":
                self.assertEqual(sorted(bc_mock[khoa]), sorted(bc_aw[khoa]))
                continue
            self.assertEqual(bc_mock[khoa], bc_aw[khoa], khoa)

    # ================================================== giu nguyen

    def test_moderation_events_khong_bi_dong_toi(self):
        """`moderation_events` CHI THEM o moi tang — ke ca hang ma nguoi bi xoa
        la target hay actor. Mot nhat ky sua duoc la mot nhat ky vo dung."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.record_event(ModerationEvent(
                    action="author_approved", target_user_id=TOI,
                    actor_id="usr_quan_tri", event_id="evt_1",
                    note="Ghi chu noi bo."))
                kho.record_event(ModerationEvent(
                    action="post_removed", target_user_id=NGUOI_KHAC,
                    actor_id=TOI, event_id="evt_2"))

                kho.delete_account(TOI)

                hang, tong = kho.list_events(target_user_id=TOI)
                self.assertEqual(tong, 1, ten)
                self.assertEqual(hang[0].note, "Ghi chu noi bo.", ten)
                hang2, tong2 = kho.list_events(target_user_id=NGUOI_KHAC)
                self.assertEqual(tong2, 1, ten)
                self.assertEqual(hang2[0].actor_id, TOI, ten)

    def test_luot_nghe_phia_NGUOI_NGHE_o_lai_phia_TAC_GIA_thi_xoa(self):
        """Luot nghe cua nguoi bi xoa da tinh vao uy tin cua mot TAC GIA KHAC —
        xoa chung la lam tut thanh tich cua nguoi khong lien quan."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_credit_once(ListenCredit(
                    listener_id=TOI, author_id=NGUOI_KHAC, chapter_id="chp_ho",
                    credit_id="cre_toi_nghe_ho"))
                kho.create_credit_once(ListenCredit(
                    listener_id=NGUOI_KHAC, author_id=TOI, chapter_id="chp_toi",
                    credit_id="cre_ho_nghe_toi"))

                bc = kho.delete_account(TOI)

                self.assertEqual(bc["listen_credits"], 1, ten)
                self.assertEqual(kho.count_credits(NGUOI_KHAC), 1, ten)
                self.assertEqual(kho.count_credits(TOI), 0, ten)

    # ================================================== giu nhung an danh

    def test_don_tac_gia_o_lai_nhung_van_ban_nhan_dang_bi_an_danh(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                _gieo_noi_dung(kho, TOI)
                bc = kho.delete_account(TOI)

                self.assertEqual(bc["applications_anonymized"], 1, ten)
                don = kho.get_application(TOI)
                self.assertIsNotNone(don, ten)
                self.assertEqual(don.pen_name, AN_DANH_DA_XOA, ten)
                self.assertEqual(don.bio, AN_DANH_DA_XOA, ten)
                self.assertEqual(don.intro, AN_DANH_DA_XOA, ten)
                # Lich su quyet dinh cua nguoi duyet O LAI NGUYEN VEN.
                self.assertIs(don.status, AuthorStatus.APPROVED, ten)
                self.assertEqual(don.reviewer_note, "Duyet vi ho viet tot.", ten)
                self.assertEqual(don.decided_at, "2026-08-01T00:00:00+00:00", ten)
                # `user_id` giu lai: khu quan tri con truy vet duoc ai da nop.
                self.assertEqual(don.user_id, TOI, ten)

    def test_bao_cao_o_lai_nhung_nguoi_bao_bi_an_danh(self):
        """Bao cao la bang chung ve nguoi BI bao cao — xoa no la xoa bang
        chung. Chi danh tinh nguoi bao bi go."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                _gieo_noi_dung(kho, TOI)
                khoa_bao = report_key(TOI, "post", "pst_cua_nguoi_khac")

                bc = kho.delete_account(TOI)

                self.assertEqual(bc["reports_anonymized"], 1, ten)
                bao = kho.get_report(khoa_bao)
                self.assertIsNotNone(bao, ten)
                self.assertEqual(bao.reporter_id, AN_DANH_DA_XOA, ten)
                self.assertEqual(bao.target_id, "pst_cua_nguoi_khac", ten)
                self.assertEqual(bao.target_owner_id, NGUOI_KHAC, ten)
                self.assertEqual(bao.detail, "Bai nay spam.", ten)

    def test_bao_cao_ve_nguoi_bi_xoa_khong_bi_dong_toi(self):
        """Nguoi nay la BEN BI BAO CAO: hang do la bang chung cua mot nguoi
        khac, khong phai du lieu cua ho."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                khoa = report_key(NGUOI_KHAC, "post", "pst_cua_toi")
                kho.create_report_once(ContentReport(
                    reporter_id=NGUOI_KHAC, target_kind="post",
                    target_id="pst_cua_toi", target_owner_id=TOI,
                    detail="Nguoi nay spam.", report_id=khoa))

                bc = kho.delete_account(TOI)

                self.assertEqual(bc["reports_anonymized"], 0, ten)
                bao = kho.get_report(khoa)
                self.assertIsNotNone(bao, ten)
                self.assertEqual(bao.reporter_id, NGUOI_KHAC, ten)
                self.assertEqual(bao.target_owner_id, TOI, ten)

    # ================================================== trang thai dieu phoi

    def test_job_claims_va_job_locks_duoc_don(self):
        """Hai bang khoa dieu phoi: khong don thi chung chi tang len mai. Xem
        `delete_job` (`job_claims`) va `_don_job_locks`."""
        kho = MockMetadataStore()
        job = kho.create_job(TtsJob(owner_id=TOI, chapter_id="chp_1",
                                    voice_id="v1", content_hash="h1"))
        kho.claim_job(job, "worker-1", "2999-01-01T00:00:00+00:00")
        kho._job_locks[(TOI, "chp_1", "fp")] = job.job_id
        kho._job_locks[(NGUOI_KHAC, "chp_9", "fp")] = "job_cua_ho"

        kho.delete_account(TOI)

        self.assertEqual(kho._claims, set())
        self.assertEqual(list(kho._job_locks), [(NGUOI_KHAC, "chp_9", "fp")])

    def test_job_locks_appwrite_duoc_don_theo_owner(self):
        fake = FakeAppwrite()
        kho = _kho_appwrite(fake)
        fake.rows["job_locks"] = {
            "lock_toi": {"job_id": "job_1", "owner_id": TOI},
            "lock_ho": {"job_id": "job_2", "owner_id": NGUOI_KHAC},
        }

        kho.delete_account(TOI)

        self.assertEqual(list(fake.rows["job_locks"]), ["lock_ho"])


class HopDongXoaGamification(unittest.TestCase):
    """Trang thai CA NHAN — XP, nhat ky XP, thanh tuu, vat pham, chuoi ngay
    doc, nhiem vu. Cung kich ban tren CA HAI kho."""

    def _cac_kho(self):
        return [("mock", MockGamificationStore()),
                ("appwrite", _kho_gamification_appwrite(FakeAppwrite()))]

    @staticmethod
    def _gieo(kho, uid: str) -> None:
        kho.save_progress(UserProgress(user_id=uid, xp=120))
        kho.record_xp_event(XpLedgerEntry(
            entry_id=f"xp_{uid}_1", user_id=uid, event_type="doc_chuong",
            source_kind="chapter", source_id="chp_1", xp_awarded=10))
        kho.unlock_achievement(UnlockedAchievement(
            user_id=uid, achievement_key="doc_dau_tien"))
        kho.grant_cosmetic(CosmeticInventoryItem(
            user_id=uid, cosmetic_key="khung_dong"))
        kho.save_streak(ReadingStreak(user_id=uid, current_streak=3,
                                      longest_streak=5))
        kho.save_quest_progress(QuestProgress(
            user_id=uid, quest_key="doc_moi_ngay", period_key="2026-08-21",
            count=2))

    def test_don_sach_trang_thai_ca_nhan(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._gieo(kho, TOI)
                bc = kho.delete_account_data(TOI)

                self.assertEqual(bc["user_progress"], 1, ten)
                self.assertEqual(bc["xp_ledger"], 1, ten)
                self.assertEqual(bc["achievement_unlocks"], 1, ten)
                self.assertEqual(bc["cosmetic_inventory"], 1, ten)
                self.assertEqual(bc["reading_streaks"], 1, ten)
                self.assertEqual(bc["quest_progress"], 1, ten)

                self.assertEqual(kho.get_progress(TOI).xp, 0, ten)
                self.assertEqual(kho.list_xp_events(TOI), [], ten)
                self.assertEqual(kho.list_unlocked_achievements(TOI), [], ten)
                self.assertEqual(kho.list_cosmetics(TOI), [], ten)
                self.assertEqual(kho.get_streak(TOI).current_streak, 0, ten)
                self.assertEqual(kho.list_quest_progress(TOI), [], ten)
                # Bang xep hang khong con thay ho.
                trang, tong = kho.list_all_progress_ranked(10, 0)
                self.assertEqual(tong, 0, ten)

    def test_khong_dung_toi_nguoi_khac(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._gieo(kho, TOI)
                self._gieo(kho, NGUOI_KHAC)

                kho.delete_account_data(TOI)

                self.assertEqual(kho.get_progress(NGUOI_KHAC).xp, 120, ten)
                self.assertEqual(len(kho.list_xp_events(NGUOI_KHAC)), 1, ten)
                self.assertEqual(
                    len(kho.list_unlocked_achievements(NGUOI_KHAC)), 1, ten)
                self.assertEqual(len(kho.list_cosmetics(NGUOI_KHAC)), 1, ten)
                self.assertEqual(kho.get_streak(NGUOI_KHAC).current_streak, 3, ten)
                self.assertEqual(len(kho.list_quest_progress(NGUOI_KHAC)), 1, ten)

    def test_goi_lan_hai_khong_nem(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._gieo(kho, TOI)
                kho.delete_account_data(TOI)
                lai = kho.delete_account_data(TOI)
                self.assertEqual(set(lai.values()), {0}, ten)

    def test_hai_kho_bao_cao_giong_het(self):
        mock_kho = MockGamificationStore()
        aw_kho = _kho_gamification_appwrite(FakeAppwrite())
        self._gieo(mock_kho, TOI)
        self._gieo(aw_kho, TOI)
        self.assertEqual(mock_kho.delete_account_data(TOI),
                         aw_kho.delete_account_data(TOI))


class RouteXoaTaiKhoan(unittest.TestCase):
    """`DELETE /api/account` — tang HTTP. Moi bai bat dau tu kho SACH."""

    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.gamification_store = MockGamificationStore()
        server_main.translation_store = MockTranslationStore()
        server_main.translation_svc = TranslationService(
            server_main.translation_store, server_main.store)
        self.client = TestClient(server_main.app)

        self.token = self._dang_ky("toi@vidu.vn")
        self.uid = server_main.identity.profile_from_token(self.token).user_id
        self.token_ho = self._dang_ky("ho@vidu.vn")
        self.uid_ho = server_main.identity.profile_from_token(
            self.token_ho).user_id

    def _dang_ky(self, email: str) -> str:
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": "matkhau123"})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["token"]

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _gieo_du_an_dich(self, uid: str) -> str:
        du_an = server_main.translation_svc.create_project(
            uid, title="Ban dich", source_text="Chương 1\nmột câu.")
        server_main.translation_store.save_connection(ProviderConnection(
            user_id=uid, provider_id="groq",
            encrypted_secret="byok.v1.a.b", last4="AB12"))
        return du_an.project_id

    # -- duong chinh ----------------------------------------------------------

    def test_can_dang_nhap(self):
        self.assertEqual(self.client.delete("/api/account").status_code, 401)

    def test_xoa_toan_bo_du_lieu_va_danh_tinh(self):
        _gieo_noi_dung(server_main.store, self.uid)
        HopDongXoaGamification._gieo(server_main.gamification_store, self.uid)
        du_an = self._gieo_du_an_dich(self.uid)
        khoa_bia = f"covers/{self.uid}/anh.webp"
        server_main.storage.put(khoa_bia, b"anh gia")

        r = self.client.delete("/api/account", headers=self._auth(self.token))

        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["deleted"])
        ket_qua = r.json()["removed"]
        self.assertTrue(ket_qua["identity_deleted"])
        self.assertEqual(ket_qua["novels"], 1)
        self.assertEqual(ket_qua["translation_projects"], 1)
        self.assertEqual(ket_qua["provider_connections"], 1)
        self.assertEqual(ket_qua["gamification"]["user_progress"], 1)
        self.assertGreaterEqual(ket_qua["objects"], 1)

        self.assertEqual(server_main.store.list_novels(owner_id=self.uid), [])
        self.assertEqual(
            server_main.translation_store.list_projects(self.uid), [])
        self.assertEqual(
            server_main.translation_store.list_connections(self.uid), [])
        with self.assertRaises(Exception):
            server_main.translation_store.get_project(du_an)
        self.assertFalse(server_main.storage.exists(khoa_bia))
        # Danh tinh SAU CUNG, va no da di: khong the dang nhap lai.
        r2 = self.client.post("/api/auth/login",
                              json={"email": "toi@vidu.vn",
                                    "password": "matkhau123"})
        self.assertEqual(r2.status_code, 401)

    def test_goi_lan_thu_hai_khong_thanh_500(self):
        """Token cua phien nay chet cung tai khoan, nen lan hai dung o 401 —
        KHONG duoc la 500 (`profile_from_token` tung nem `KeyError` khi ho so
        da mat ma token con song)."""
        self.client.delete("/api/account", headers=self._auth(self.token))
        r = self.client.delete("/api/account", headers=self._auth(self.token))
        self.assertEqual(r.status_code, 401, r.text)

    def test_khong_dung_toi_du_lieu_nguoi_khac(self):
        _gieo_noi_dung(server_main.store, self.uid)
        cua_ho = _gieo_noi_dung(server_main.store, self.uid_ho)
        HopDongXoaGamification._gieo(server_main.gamification_store, self.uid_ho)
        self._gieo_du_an_dich(self.uid_ho)

        r = self.client.delete("/api/account", headers=self._auth(self.token))
        self.assertEqual(r.status_code, 200, r.text)

        self.assertEqual(len(server_main.store.list_novels(owner_id=self.uid_ho)), 1)
        self.assertEqual(len(server_main.store.chapters_for_owner(self.uid_ho)), 2)
        self.assertEqual(len(server_main.store.list_jobs(self.uid_ho)), 2)
        self.assertIsNotNone(server_main.store.get_post(cua_ho["bai"].post_id))
        self.assertEqual(
            server_main.gamification_store.get_progress(self.uid_ho).xp, 120)
        self.assertEqual(
            len(server_main.translation_store.list_projects(self.uid_ho)), 1)
        self.assertEqual(
            len(server_main.translation_store.list_connections(self.uid_ho)), 1)
        # Nguoi khac van dang nhap duoc.
        r2 = self.client.get("/api/auth/me", headers=self._auth(self.token_ho))
        self.assertEqual(r2.status_code, 200, r2.text)

    def test_appwrite_gian_doan_o_buoc_danh_tinh_tra_503_khong_phai_200(self):
        """Bao "da xoa" cho mot tai khoan VAN dang nhap duoc la loi hua sai
        nghiem trong nhat duong nay co the mac. Trang thai do nua duong la
        chap nhan duoc (moi buoc idempotent, nguoi dung bam lai duoc)."""
        from server.adapters import AppwriteUnavailableError

        class DanhTinhGianDoan(MockIdentityAdapter):
            def delete_account(self, user_id: str) -> bool:
                raise AppwriteUnavailableError(
                    "Không kết nối được Appwrite. Vui lòng thử lại sau.")

        cu = server_main.identity
        moi = DanhTinhGianDoan()
        moi._profiles = cu._profiles
        moi._by_email = cu._by_email
        moi._passwords = cu._passwords
        moi._tokens = cu._tokens
        server_main.identity = moi

        r = self.client.delete("/api/account", headers=self._auth(self.token))

        self.assertEqual(r.status_code, 503, r.text)
        # Tai khoan VAN con — nguoi dung goi lai duoc.
        self.assertIsNotNone(server_main.identity.get_profile(self.uid))

    def test_appwrite_gian_doan_o_kho_metadata_tra_503_khong_phai_404(self):
        """Phat hien khi review PR #23 (2026-08-21): mot loi TRANSPORT (mat
        mang/DNS/timeout) khi goi `AppwriteMetadataStore` giua luc xoa tai
        khoan bi bao thanh 404 ("khong tim thay gi de xoa") thay vi 503 ("thu
        lai sau") — vi `_call` truoc day gop lam mot loi TRANSPORT (ta CHUA
        BIET ban ghi co ton tai hay khong) voi mot response That su tra 404.
        Da sua rieng trong PR nay (`appwrite_store.py`/
        `appwrite_gamification_store.py`), kem test nay de khoa lai."""
        import httpx

        from server.appwrite_store import AppwriteMetadataStore

        class _ClientGianDoan:
            def request(self, method, url, json=None, params=None, headers=None):
                raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

        cfg = AppwriteSettings(
            endpoint="https://appwrite-khong-ton-tai.invalid/v1",
            project_id="p", api_key="khoa-gia", database_id="db")
        kho_gian_doan = AppwriteMetadataStore(cfg)
        kho_gian_doan._pool = _ClientGianDoan()  # "cat mang" — bo qua tao client that

        cu = server_main.store
        server_main.store = kho_gian_doan
        try:
            r = self.client.delete("/api/account", headers=self._auth(self.token))
        finally:
            server_main.store = cu

        self.assertEqual(r.status_code, 503, r.text)
        self.assertNotEqual(r.status_code, 404)

    def test_du_an_dich_cua_nguoi_khac_khong_bi_xoa_du_cung_tieu_de(self):
        """`delete_project` nhan `owner_id` — day la phep bao dam cuoi cung
        neu mot ngay nao do `list_projects` loc sai."""
        cua_toi = self._gieo_du_an_dich(self.uid)
        cua_ho = self._gieo_du_an_dich(self.uid_ho)

        self.client.delete("/api/account", headers=self._auth(self.token))

        self.assertIsNotNone(server_main.translation_store.get_project(cua_ho))
        with self.assertRaises(Exception):
            server_main.translation_store.get_project(cua_toi)


if __name__ == "__main__":
    unittest.main(verbosity=2)
