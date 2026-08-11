"""
Kho tang xa hoi tren Appwrite Databases.

MIXIN, giong `server/social_store.py` ben mock: `AppwriteMetadataStore` ke thua
no. Cung chu ky, cung ngu nghia — bo test hop dong
`server/tests/test_social_contract.py` chay cung mot kich ban qua ca hai ban.

BA dieu quyet dinh tinh dung dan cua ca tep nay:

1. `rowId` TAT DINH thay cho moi phep "kiem tra roi ghi".

   Theo doi, thich, bao cao, thong bao — tat ca deu co the bi bam hai lan trong
   cung mot phan giay. Mot phep doc-roi-ghi thua cuoc dua do; mot khoa tat dinh
   thi khong, vi chinh APPWRITE tu choi hang thu hai bang 409. Day la co che
   nguyen tu manh nhat ma kien truc hien tai co san, va no da duoc dung cho
   `job_locks` va `listen_credits`.

2. KHONG BAO GIO tai het ve roi loc o Python.

   Moi phep loc, sap xep va phan trang deu o phia Appwrite. Mot bang tin hay mot
   hang doi bao cao chi lon len theo thoi gian, va "tai het roi cat" la cach lam
   chay tot trong tuan dau roi hong dan ma khong ai thay.

3. Doc theo LO cho moi thu ghep vao mot TRANG.

   So nguoi theo doi, co da-thich, so bai — deu la cau hoi cho ca trang, khong
   phai cho tung hang. Hoi tung hang la dung cai N+1 da lam khu quan tri mat 34
   giay tren staging that.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from server.adapters import NotFoundError
from server.domain import (
    Comment,
    ContentReport,
    ContentState,
    Notification,
    NotificationKind,
    Post,
    PostKind,
    PostLike,
    ReportReason,
    ReportStatus,
    StoryFollow,
    UserFollow,
    now_iso_us,
)

COL_USER_FOLLOWS = "user_follows"
COL_STORY_FOLLOWS = "story_follows"
COL_POSTS = "posts"
COL_POST_LIKES = "post_likes"
COL_COMMENTS = "comments"
COL_NOTIFICATIONS = "notifications"
COL_REPORTS = "content_reports"

#: Thuoc tinh THUC SU co trong schema — xem `scripts/setup_appwrite.py`.
SOCIAL_PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_USER_FOLLOWS: ("follow_id", "follower_id", "target_id", "created_at"),
    COL_STORY_FOLLOWS: ("follow_id", "follower_id", "novel_id", "created_at"),
    COL_POSTS: (
        "post_id", "author_user_id", "kind", "novel_id", "text",
        "image_key", "image_mime", "image_width", "image_height", "image_bytes",
        "state", "like_count", "comment_count", "removed_by", "removed_reason",
        "created_at", "updated_at",
    ),
    COL_POST_LIKES: ("like_id", "post_id", "user_id", "created_at"),
    COL_COMMENTS: (
        "comment_id", "post_id", "author_user_id", "parent_id", "text",
        "state", "reply_count", "removed_by", "removed_reason",
        "created_at", "updated_at",
    ),
    COL_NOTIFICATIONS: (
        "notification_id", "user_id", "kind", "actor_id", "subject_id",
        "subject_kind", "preview", "read", "created_at",
    ),
    COL_REPORTS: (
        "report_id", "reporter_id", "target_kind", "target_id",
        "target_owner_id", "reason", "detail", "status", "resolution_note",
        "resolved_by", "created_at", "updated_at",
    ),
}


def q_greater_equal(attribute: str, value: Any) -> str:
    """
    Lon hon hoac bang. Dung cho cua so thoi gian cua han muc chong spam.

    Moc thoi gian duoc luu dang chuoi ISO UTC, va so sanh chuoi ISO UTC CUNG
    DINH DANG chinh la so sanh thoi gian. Dieu kien "cung dinh dang" la that:
    tron `timespec="seconds"` voi ban micro giay thi mot moc "10:00:00+00:00" va
    "10:00:00.5+00:00" so sanh theo ma ky tu ('+' truoc '.'), tuc la ban day du
    lai lon hon. O day dieu do chi lam cua so RONG them duoi mot giay, va no
    duoc chap nhan co y thuc — nghieng ve phia de lot mot thao tac hop le hon la
    chan nham mot nguoi dung that.
    """
    return json.dumps({"method": "greaterThanEqual", "attribute": attribute,
                       "values": [value]})


# -- doi hang Appwrite -> ban ghi domain --------------------------------------
#
# Mot cho duy nhat cho moi phep doi. Rai chung ra thi mot truong bi quen se im
# lang tra ve gia tri mac dinh, va do la loai loi khong ai thay cho toi khi mot
# nguoi dung hoi vi sao bai cua ho mat anh.


def _enum(kieu, gia_tri, mac_dinh):
    """Doi chuoi thanh enum, ve mac dinh khi gia tri la khong ro."""
    try:
        return kieu(str(gia_tri or "") or mac_dinh.value)
    except ValueError:
        return mac_dinh


def _post_from(row: Dict[str, Any]) -> Post:
    return Post(
        post_id=str(row.get("post_id") or row.get("$id") or ""),
        author_user_id=str(row.get("author_user_id") or ""),
        kind=_enum(PostKind, row.get("kind"), PostKind.POST),
        novel_id=str(row.get("novel_id") or ""),
        text=str(row.get("text") or ""),
        image_key=str(row.get("image_key") or ""),
        image_mime=str(row.get("image_mime") or ""),
        image_width=int(row.get("image_width") or 0),
        image_height=int(row.get("image_height") or 0),
        image_bytes=int(row.get("image_bytes") or 0),
        state=_enum(ContentState, row.get("state"), ContentState.VISIBLE),
        like_count=int(row.get("like_count") or 0),
        comment_count=int(row.get("comment_count") or 0),
        removed_by=str(row.get("removed_by") or ""),
        removed_reason=str(row.get("removed_reason") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _comment_from(row: Dict[str, Any]) -> Comment:
    return Comment(
        comment_id=str(row.get("comment_id") or row.get("$id") or ""),
        post_id=str(row.get("post_id") or ""),
        author_user_id=str(row.get("author_user_id") or ""),
        parent_id=str(row.get("parent_id") or ""),
        text=str(row.get("text") or ""),
        state=_enum(ContentState, row.get("state"), ContentState.VISIBLE),
        reply_count=int(row.get("reply_count") or 0),
        removed_by=str(row.get("removed_by") or ""),
        removed_reason=str(row.get("removed_reason") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _notification_from(row: Dict[str, Any]) -> Notification:
    return Notification(
        notification_id=str(row.get("notification_id") or row.get("$id") or ""),
        user_id=str(row.get("user_id") or ""),
        kind=_enum(NotificationKind, row.get("kind"), NotificationKind.FOLLOW),
        actor_id=str(row.get("actor_id") or ""),
        subject_id=str(row.get("subject_id") or ""),
        subject_kind=str(row.get("subject_kind") or ""),
        preview=str(row.get("preview") or ""),
        read=bool(row.get("read")),
        created_at=str(row.get("created_at") or ""),
    )


def _report_from(row: Dict[str, Any]) -> ContentReport:
    return ContentReport(
        report_id=str(row.get("report_id") or row.get("$id") or ""),
        reporter_id=str(row.get("reporter_id") or ""),
        target_kind=str(row.get("target_kind") or "post"),
        target_id=str(row.get("target_id") or ""),
        target_owner_id=str(row.get("target_owner_id") or ""),
        reason=_enum(ReportReason, row.get("reason"), ReportReason.OTHER),
        detail=str(row.get("detail") or ""),
        status=_enum(ReportStatus, row.get("status"), ReportStatus.OPEN),
        resolution_note=str(row.get("resolution_note") or ""),
        resolved_by=str(row.get("resolved_by") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


class AppwriteSocialStore:
    """
    Phan xa hoi cua kho Appwrite.

    Dua vao ha tang cua `AppwriteMetadataStore`: `_create`, `_create_kin`,
    `_get`, `_list`, `_page`, `_update`, `_delete`, va cac ham dung truy van
    (`q_equal`, `q_order_desc`, ...). Mixin nay khong mo ket noi rieng nao.
    """

    # =========================================================== THEO DOI NGUOI

    def follow_user(self, follow: UserFollow) -> bool:
        """
        Tao neu chua co. `False` = da theo doi tu truoc, HOAC mot loi mang.

        `_call` doi MOI ma >= 400 thanh `NotFoundError`, nen 409 (trung khoa)
        khong phan biet duoc voi mot loi khac. Huong nham o day la an toan: mot
        loi mang lam thao tac KHONG duoc ghi va KHONG gui thong bao, thay vi ghi
        hai lan va ban hai thong bao. Nguoi dung bam lai la xong.
        """
        return self._tao_mot_lan(COL_USER_FOLLOWS, follow.follow_id,
                                 follow.to_dict(), follow.follower_id)

    def unfollow_user(self, follow_id: str) -> bool:
        return self._xoa_neu_co(COL_USER_FOLLOWS, follow_id)

    def is_following_user(self, follow_id: str) -> bool:
        return self._ton_tai(COL_USER_FOLLOWS, follow_id)

    def following_user_ids(self, follower_id: str,
                           limit: int = 100) -> List[str]:
        from server.appwrite_store import (q_equal, q_limit, q_order_desc,
                                           q_select)

        rows = self._list(COL_USER_FOLLOWS, [
            q_equal("follower_id", follower_id),
            q_select("target_id", "created_at"),
            q_order_desc("created_at"),
            q_limit(limit),
        ])
        return [str(r.get("target_id") or "") for r in rows if r.get("target_id")]

    def follower_ids(self, target_id: str, limit: int = 1000) -> List[str]:
        from server.appwrite_store import (q_equal, q_limit, q_order_desc,
                                           q_select)

        rows = self._list(COL_USER_FOLLOWS, [
            q_equal("target_id", target_id),
            q_select("follower_id", "created_at"),
            q_order_desc("created_at"),
            q_limit(limit),
        ])
        return [str(r.get("follower_id") or "")
                for r in rows if r.get("follower_id")]

    def follower_counts(self, user_ids: Sequence[str]) -> Dict[str, int]:
        return self._dem_theo_khoa(COL_USER_FOLLOWS, "target_id", user_ids)

    def following_counts(self, user_ids: Sequence[str]) -> Dict[str, int]:
        return self._dem_theo_khoa(COL_USER_FOLLOWS, "follower_id", user_ids)

    def following_flags(self, follower_id: str,
                        target_ids: Sequence[str]) -> Set[str]:
        return self._co_theo_lo(COL_USER_FOLLOWS, "follower_id", follower_id,
                                "target_id", target_ids)

    def count_follows_since(self, follower_id: str, since: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_USER_FOLLOWS, [
            q_equal("follower_id", follower_id),
            q_greater_equal("created_at", since),
            q_limit(1),
        ])[1]

    # =========================================================== THEO DOI TRUYEN

    def follow_story(self, follow: StoryFollow) -> bool:
        return self._tao_mot_lan(COL_STORY_FOLLOWS, follow.follow_id,
                                 follow.to_dict(), follow.follower_id)

    def unfollow_story(self, follow_id: str) -> bool:
        return self._xoa_neu_co(COL_STORY_FOLLOWS, follow_id)

    def is_following_story(self, follow_id: str) -> bool:
        return self._ton_tai(COL_STORY_FOLLOWS, follow_id)

    def story_follower_ids(self, novel_id: str, limit: int = 1000) -> List[str]:
        from server.appwrite_store import (q_equal, q_limit, q_order_desc,
                                           q_select)

        rows = self._list(COL_STORY_FOLLOWS, [
            q_equal("novel_id", novel_id),
            q_select("follower_id", "created_at"),
            q_order_desc("created_at"),
            q_limit(limit),
        ])
        return [str(r.get("follower_id") or "")
                for r in rows if r.get("follower_id")]

    def followed_story_ids(self, follower_id: str,
                           limit: int = 200) -> List[str]:
        from server.appwrite_store import (q_equal, q_limit, q_order_desc,
                                           q_select)

        rows = self._list(COL_STORY_FOLLOWS, [
            q_equal("follower_id", follower_id),
            q_select("novel_id", "created_at"),
            q_order_desc("created_at"),
            q_limit(limit),
        ])
        return [str(r.get("novel_id") or "") for r in rows if r.get("novel_id")]

    def story_follower_counts(self, novel_ids: Sequence[str]) -> Dict[str, int]:
        return self._dem_theo_khoa(COL_STORY_FOLLOWS, "novel_id", novel_ids)

    def story_following_flags(self, follower_id: str,
                              novel_ids: Sequence[str]) -> Set[str]:
        return self._co_theo_lo(COL_STORY_FOLLOWS, "follower_id", follower_id,
                                "novel_id", novel_ids)

    # ================================================================= BAI DANG

    def create_post(self, post: Post) -> Post:
        # Quyen doc CONG KHAI: moi bai deu cong khai o giai doan nay. Bai bi go
        # van giu quyen do — noi dung khong ra ngoai vi `to_public_dict()` cat
        # no, chu khong phai vi permission. Mot duong bao ve duy nhat, o mot cho.
        self._create(COL_POSTS, post.post_id, post.to_dict(),
                     post.author_user_id, public_read=True)
        return post

    def get_post(self, post_id: str) -> Optional[Post]:
        try:
            return _post_from(self._get(COL_POSTS, post_id))
        except NotFoundError:
            return None

    def save_post(self, post: Post) -> Post:
        post.updated_at = now_iso_us()
        self._update(COL_POSTS, post.post_id, post.to_dict())
        return post

    def delete_post(self, post_id: str) -> bool:
        return self._xoa_neu_co(COL_POSTS, post_id)

    def posts_by_ids(self, post_ids: Sequence[str]) -> Dict[str, Post]:
        from server.appwrite_store import BATCH_IDS, _theo_lo, q_equal, q_limit

        ra: Dict[str, Post] = {}
        ids = [p for p in post_ids if p]
        for lo in _theo_lo(list(ids), BATCH_IDS):
            for row in self._list(COL_POSTS, [q_equal("post_id", *lo),
                                              q_limit(len(lo))]):
                bai = _post_from(row)
                ra[bai.post_id] = bai
        return ra

    def list_posts(self, *, author_ids: Optional[Sequence[str]] = None,
                   novel_id: str = "", query: str = "",
                   include_removed: bool = False,
                   limit: int = 20, offset: int = 0) -> Tuple[List[Post], int]:
        """
        Loc, sap xep va phan trang HOAN TOAN o phia Appwrite.

        `author_ids=[]` — danh sach RONG — tra ve rong ngay, khong goi mang.
        Khac han `author_ids=None` (khong loc). Gop hai truong hop nay lai la
        mot loi kinh dien: nguoi chua theo doi ai se thay bang tin toan he thong.
        """
        from server.appwrite_store import (q_contains, q_equal, q_limit,
                                           q_offset, q_or, q_order_desc)

        if author_ids is not None and not list(author_ids):
            return [], 0

        queries: List[str] = []
        if author_ids is not None:
            # `equal` nhan nhieu gia tri — chinh la mot truy van IN.
            queries.append(q_equal("author_user_id", *list(author_ids)))
        if novel_id:
            queries.append(q_equal("novel_id", novel_id))
        if not include_removed:
            queries.append(q_equal("state", ContentState.VISIBLE.value))
        if query:
            queries.append(q_or(q_contains("text", query)))
        queries += [q_order_desc("created_at"), q_limit(limit), q_offset(offset)]
        rows, total = self._page(COL_POSTS, queries)
        return [_post_from(r) for r in rows], total

    def post_counts(self, user_ids: Sequence[str]) -> Dict[str, int]:
        from server.appwrite_store import q_equal

        return self._dem_theo_khoa(
            COL_POSTS, "author_user_id", user_ids,
            them=[q_equal("state", ContentState.VISIBLE.value)])

    def count_posts_since(self, author_user_id: str, since: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_POSTS, [
            q_equal("author_user_id", author_user_id),
            q_greater_equal("created_at", since),
            q_limit(1),
        ])[1]

    def bump_post_counter(self, post_id: str, field: str, delta: int) -> int:
        """
        Cong don. DOC-ROI-GHI — xem `MockSocialStore.bump_post_counter` de biet
        vi sao han che nay chap nhan duoc va dem lai bang cach nao.
        """
        bai = self.get_post(post_id)
        if bai is None:
            return 0
        moi = max(0, int(getattr(bai, field, 0) or 0) + delta)
        self._update(COL_POSTS, post_id, {field: moi, "updated_at": now_iso_us()})
        return moi

    # ============================================================ LUOT THICH

    def like_post(self, like: PostLike) -> bool:
        return self._tao_mot_lan(COL_POST_LIKES, like.like_id, like.to_dict(),
                                 like.user_id)

    def unlike_post(self, like_id: str) -> bool:
        return self._xoa_neu_co(COL_POST_LIKES, like_id)

    def has_liked(self, like_id: str) -> bool:
        return self._ton_tai(COL_POST_LIKES, like_id)

    def liked_flags(self, user_id: str, post_ids: Sequence[str]) -> Set[str]:
        return self._co_theo_lo(COL_POST_LIKES, "user_id", user_id,
                                "post_id", post_ids)

    def count_post_likes(self, post_id: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_POST_LIKES, [q_equal("post_id", post_id),
                                           q_limit(1)])[1]

    # ============================================================== BINH LUAN

    def create_comment(self, comment: Comment) -> Comment:
        self._create(COL_COMMENTS, comment.comment_id, comment.to_dict(),
                     comment.author_user_id, public_read=True)
        return comment

    def get_comment(self, comment_id: str) -> Optional[Comment]:
        try:
            return _comment_from(self._get(COL_COMMENTS, comment_id))
        except NotFoundError:
            return None

    def save_comment(self, comment: Comment) -> Comment:
        comment.updated_at = now_iso_us()
        self._update(COL_COMMENTS, comment.comment_id, comment.to_dict())
        return comment

    def delete_comment(self, comment_id: str) -> bool:
        return self._xoa_neu_co(COL_COMMENTS, comment_id)

    def comments_by_ids(self, comment_ids: Sequence[str]) -> Dict[str, Comment]:
        from server.appwrite_store import BATCH_IDS, _theo_lo, q_equal, q_limit

        ra: Dict[str, Comment] = {}
        ids = [c for c in comment_ids if c]
        for lo in _theo_lo(list(ids), BATCH_IDS):
            for row in self._list(COL_COMMENTS, [q_equal("comment_id", *lo),
                                                 q_limit(len(lo))]):
                c = _comment_from(row)
                ra[c.comment_id] = c
        return ra

    def list_comments(self, post_id: str, *, parent_id: Optional[str] = None,
                      include_removed: bool = True,
                      limit: int = 20,
                      offset: int = 0) -> Tuple[List[Comment], int]:
        """CU NHAT truoc — mot cuoc trao doi doc theo thu tu no dien ra."""
        from server.appwrite_store import (q_equal, q_limit, q_offset,
                                           q_order_asc)

        queries = [q_equal("post_id", post_id)]
        if parent_id is not None:
            queries.append(q_equal("parent_id", parent_id))
        if not include_removed:
            queries.append(q_equal("state", ContentState.VISIBLE.value))
        queries += [q_order_asc("created_at"), q_limit(limit), q_offset(offset)]
        rows, total = self._page(COL_COMMENTS, queries)
        return [_comment_from(r) for r in rows], total

    def replies_for(self, parent_ids: Sequence[str],
                    moi_cha: int = 3) -> Dict[str, List[Comment]]:
        """
        Vai tra loi dau cua NHIEU binh luan goc, bang MOT truy van.

        Lay `len(ids) * moi_cha` hang roi cat o Python. Do la cho DUY NHAT trong
        tep nay cat o phia ung dung, va no co ly do: Appwrite khong co "N hang
        dau moi nhom", va cach con lai la mot truy van cho MOI binh luan goc —
        dung cai N+1 ma ca tep nay ton tai de tranh.
        """
        from server.appwrite_store import (BATCH_IDS, _theo_lo, q_equal,
                                           q_limit, q_order_asc)

        ids = [p for p in parent_ids if p]
        gom: Dict[str, List[Comment]] = {pid: [] for pid in ids}
        if not ids:
            return {}
        for lo in _theo_lo(list(ids), BATCH_IDS):
            rows = self._list(COL_COMMENTS, [
                q_equal("parent_id", *lo),
                q_order_asc("created_at"),
                q_limit(len(lo) * max(1, moi_cha)),
            ])
            for row in rows:
                c = _comment_from(row)
                cho = gom.setdefault(c.parent_id, [])
                if len(cho) < moi_cha:
                    cho.append(c)
        return gom

    def count_post_comments(self, post_id: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_COMMENTS, [
            q_equal("post_id", post_id),
            q_equal("state", ContentState.VISIBLE.value),
            q_limit(1),
        ])[1]

    def count_comments_since(self, author_user_id: str, since: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_COMMENTS, [
            q_equal("author_user_id", author_user_id),
            q_greater_equal("created_at", since),
            q_limit(1),
        ])[1]

    def bump_comment_counter(self, comment_id: str, field: str,
                             delta: int) -> int:
        row = self.get_comment(comment_id)
        if row is None:
            return 0
        moi = max(0, int(getattr(row, field, 0) or 0) + delta)
        self._update(COL_COMMENTS, comment_id,
                     {field: moi, "updated_at": now_iso_us()})
        return moi

    # =============================================================== THONG BAO

    def create_notification_once(self, note: Notification) -> bool:
        """
        Khoa tat dinh CO GO NGAY — xem `social.notification_key`. Tinh duy nhat
        cua no la toan bo co che chong lap.

        Quyen doc cap cho NGUOI NHAN, khong phai nguoi gay ra.
        """
        return self._tao_mot_lan(COL_NOTIFICATIONS, note.notification_id,
                                 note.to_dict(), note.user_id)

    def list_notifications(self, user_id: str, *, unread_only: bool = False,
                           limit: int = 20,
                           offset: int = 0) -> Tuple[List[Notification], int]:
        from server.appwrite_store import (q_equal, q_limit, q_offset,
                                           q_order_desc)

        queries = [q_equal("user_id", user_id)]
        if unread_only:
            queries.append(q_equal("read", False))
        queries += [q_order_desc("created_at"), q_limit(limit), q_offset(offset)]
        rows, total = self._page(COL_NOTIFICATIONS, queries)
        return [_notification_from(r) for r in rows], total

    def count_unread(self, user_id: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_NOTIFICATIONS, [
            q_equal("user_id", user_id),
            q_equal("read", False),
            q_limit(1),
        ])[1]

    def mark_notification_read(self, user_id: str,
                               notification_id: str) -> bool:
        """
        `user_id` la mot phan cua DIEU KIEN, khong phai trang tri: khong co no
        thi ai doan duoc mot id la danh dau duoc thong bao cua nguoi khac.
        """
        try:
            row = self._get(COL_NOTIFICATIONS, notification_id)
        except NotFoundError:
            return False
        if str(row.get("user_id") or "") != user_id:
            return False
        self._update(COL_NOTIFICATIONS, notification_id, {"read": True})
        return True

    def mark_all_read(self, user_id: str) -> int:
        """
        Danh dau het. Mot vong PATCH cho tung hang chua doc.

        Appwrite khong co cap nhat hang loat, va day la mot thao tac NGUOI DUNG
        CHU DONG bam — no khong nam trong duong tai trang. Chi lay ve nhung hang
        con chua doc, nen mot nguoi doc thuong xuyen chi ton vai lan goi.
        """
        from server.appwrite_store import (q_equal, q_limit, q_select)

        dem = 0
        while True:
            rows = self._list(COL_NOTIFICATIONS, [
                q_equal("user_id", user_id),
                q_equal("read", False),
                q_select("notification_id"),
                q_limit(100),
            ])
            if not rows:
                return dem
            for row in rows:
                nid = str(row.get("notification_id") or row.get("$id") or "")
                if nid:
                    self._update(COL_NOTIFICATIONS, nid, {"read": True})
                    dem += 1
            if len(rows) < 100:
                return dem

    # ================================================================= BAO CAO

    def create_report_once(self, report: ContentReport) -> bool:
        """
        Hang bao cao KHONG cap quyen doc cho client nao — `_create_kin`.

        Ly do giong `moderation_events`: hang nay chua `resolution_note` (ghi
        chu noi bo cua quan tri) va `resolved_by`. Moi duong doc hop le deu di
        qua backend bang API key, nen danh sach quyen rong khong hong chuc nang.
        """
        try:
            self._create_kin(COL_REPORTS, report.report_id, report.to_dict())
            return True
        except NotFoundError:
            return False

    def get_report(self, report_id: str) -> Optional[ContentReport]:
        try:
            return _report_from(self._get(COL_REPORTS, report_id))
        except NotFoundError:
            return None

    def save_report(self, report: ContentReport) -> ContentReport:
        report.updated_at = now_iso_us()
        self._update(COL_REPORTS, report.report_id, report.to_dict())
        return report

    def list_reports(self, *, status: Optional[ReportStatus] = None,
                     target_kind: str = "", limit: int = 25,
                     offset: int = 0) -> Tuple[List[ContentReport], int]:
        from server.appwrite_store import (q_equal, q_limit, q_offset,
                                           q_order_asc)

        queries: List[str] = []
        if status is not None:
            queries.append(q_equal("status", status.value))
        if target_kind:
            queries.append(q_equal("target_kind", target_kind))
        queries += [q_order_asc("created_at"), q_limit(limit), q_offset(offset)]
        rows, total = self._page(COL_REPORTS, queries)
        return [_report_from(r) for r in rows], total

    def count_reports(self, status: Optional[ReportStatus] = None) -> int:
        from server.appwrite_store import q_equal, q_limit

        queries = [q_limit(1)]
        if status is not None:
            queries.insert(0, q_equal("status", status.value))
        return self._page(COL_REPORTS, queries)[1]

    def count_reports_since(self, reporter_id: str, since: str) -> int:
        from server.appwrite_store import q_equal, q_limit

        return self._page(COL_REPORTS, [
            q_equal("reporter_id", reporter_id),
            q_greater_equal("created_at", since),
            q_limit(1),
        ])[1]

    def reports_for_targets(self, target_ids: Sequence[str]) -> Dict[str, int]:
        from server.appwrite_store import q_equal

        return self._dem_theo_khoa(
            COL_REPORTS, "target_id", target_ids,
            them=[q_equal("status", ReportStatus.OPEN.value)])

    # ================================================================== HA TANG

    def _tao_mot_lan(self, collection: str, doc_id: str, data: Dict[str, Any],
                     owner_id: str) -> bool:
        """
        Tao hang voi `rowId` tat dinh. `False` neu da ton tai.

        `_call` doi moi ma >= 400 thanh `NotFoundError`, nen khong phan biet
        duoc 409 voi loi mang. Huong nham la an toan — xem `follow_user`.
        """
        try:
            self._create(collection, doc_id, data, owner_id)
            return True
        except NotFoundError:
            return False

    def _xoa_neu_co(self, collection: str, doc_id: str) -> bool:
        try:
            self._delete(collection, doc_id)
            return True
        except NotFoundError:
            return False

    def _ton_tai(self, collection: str, doc_id: str) -> bool:
        try:
            self._get(collection, doc_id)
            return True
        except NotFoundError:
            return False

    def _dem_theo_khoa(self, collection: str, khoa: str,
                       gia_tri: Sequence[str],
                       them: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Dem hang theo tung gia tri cua mot cot.

        HAN CHE THAT: Appwrite khong co `GROUP BY`, nen day la MOT truy van cho
        moi gia tri. Voi mot trang 25 hang do la 25 lan goi — cham, nhung van
        la mot con so CO TRAN theo kich thuoc trang, khong phai theo kich thuoc
        bang. Do moi la dieu quan trong: mot trang quan tri khong cham dan khi
        he thong lon len.

        Cach lam nhanh hon can mot bang tong hop nhu `author_stats`, va do la
        viec cua giai doan sau — them mot bang tong hop nua bay gio la them mot
        cho nua co the lech ma chua ai chung minh la can.
        """
        from server.appwrite_store import q_equal, q_limit

        ra: Dict[str, int] = {}
        for gt in {g for g in gia_tri if g}:
            queries = list(them or []) + [q_equal(khoa, gt), q_limit(1)]
            ra[gt] = self._page(collection, queries)[1]
        for gt in gia_tri:
            ra.setdefault(gt, 0)
        return ra

    def _co_theo_lo(self, collection: str, khoa_nguoi: str, nguoi_id: str,
                    khoa_muc: str, muc_ids: Sequence[str]) -> Set[str]:
        """
        "Trong danh sach nay, nguoi do da lam gi voi nhung muc nao."

        MOT truy van cho ca trang (hoac vai truy van neu trang rat dai), thay vi
        mot truy van moi muc. Day la ham chan N+1 cho co "dang theo doi" va co
        "da thich".
        """
        from server.appwrite_store import BATCH_IDS, _theo_lo, q_equal, q_limit

        ids = [m for m in muc_ids if m]
        if not nguoi_id or not ids:
            return set()
        thay: Set[str] = set()
        for lo in _theo_lo(list(ids), BATCH_IDS):
            rows = self._list(collection, [
                q_equal(khoa_nguoi, nguoi_id),
                q_equal(khoa_muc, *lo),
                q_limit(len(lo)),
            ])
            thay.update(str(r.get(khoa_muc) or "") for r in rows)
        return thay - {""}
