"""
Kho tang xa hoi trong bo nho.

Day la mot MIXIN, khong phai mot lop doc lap: `MockMetadataStore` ke thua no.
Ly do khong nhet thang vao `server/adapters.py` la do dai — tep do da 1400 dong
va them 500 dong nua se bien no thanh thu khong ai doc het duoc. Ranh gioi o day
la mot ranh gioi CHU DE (xa hoi / noi dung), khong phai mot ranh gioi ky thuat.

Ban Appwrite tuong ung o `server/appwrite_social.py`, va bo test hop dong
`server/tests/test_social_contract.py` chay CUNG mot kich ban qua ca hai — do la
thu duy nhat chung minh hai ban that su cung hanh vi.

KHONG PHAI kho ben vung. Du lieu chi song trong vong doi tien trinh.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence, Set, Tuple

from server.domain import (
    Comment,
    ContentReport,
    ContentState,
    Notification,
    Post,
    PostLike,
    ReportStatus,
    StoryFollow,
    UserFollow,
    now_iso_us,
)


class MockSocialStore:
    """
    Phan xa hoi cua kho mock.

    Moi ham deu giu CUNG chu ky va CUNG ngu nghia voi ban Appwrite. Cho nao ban
    that co han che (vd khong cong nguyen tu duoc) thi ban nay KHONG gia vo manh
    hon: no bat chuoc dung han che do, de test khong xanh o mock roi do o that.
    """

    # Duoc `MockMetadataStore.__init__` goi. Tach ra thay vi dung `__init__` cua
    # mixin: mot mixin co `__init__` rieng lam thu tu khoi tao phu thuoc vao MRO,
    # va do la thu de vo im lang khi ai do doi thu tu ke thua.
    def _khoi_tao_xa_hoi(self) -> None:
        if not hasattr(self, "_lock"):
            self._lock = threading.RLock()
        #: follow_id (tat dinh) -> ban ghi
        self._user_follows: Dict[str, UserFollow] = {}
        self._story_follows: Dict[str, StoryFollow] = {}
        self._posts: Dict[str, Post] = {}
        #: like_id (tat dinh) -> ban ghi
        self._post_likes: Dict[str, PostLike] = {}
        self._comments: Dict[str, Comment] = {}
        #: notification_id (tat dinh, co go ngay) -> ban ghi
        self._notifications: Dict[str, Notification] = {}
        #: report_id (tat dinh) -> ban ghi
        self._reports: Dict[str, ContentReport] = {}

    # =========================================================== THEO DOI NGUOI

    def follow_user(self, follow: UserFollow) -> bool:
        """
        Tao neu chua co. `False` nghia la DA theo doi tu truoc.

        Tra ve co "co that su moi khong" thay vi im lang: tang dich vu dung no
        de quyet dinh CO GUI THONG BAO HAY KHONG. Khong co co nay thi bam theo
        doi lai lan thu hai se ban them mot thong bao nua.
        """
        with self._lock:
            if follow.follow_id in self._user_follows:
                return False
            self._user_follows[follow.follow_id] = follow
            return True

    def unfollow_user(self, follow_id: str) -> bool:
        with self._lock:
            return self._user_follows.pop(follow_id, None) is not None

    def is_following_user(self, follow_id: str) -> bool:
        with self._lock:
            return follow_id in self._user_follows

    def following_user_ids(self, follower_id: str,
                           limit: int = 100) -> List[str]:
        """
        Ai nguoi nay dang theo doi. MOI NHAT truoc.

        Co `limit` vi day la dau vao cua truy van bang tin, va truy van do loc
        theo `author_user_id IN (...)` — mot danh sach khong tran se lam vo truy
        van khi nguoi dung theo doi vai nghin nguoi. Xem
        `social.NGUOI_THEO_DOI_TOI_DA`.
        """
        with self._lock:
            rows = [f for f in self._user_follows.values()
                    if f.follower_id == follower_id]
        rows.sort(key=lambda f: (f.created_at, f.target_id), reverse=True)
        return [f.target_id for f in rows[:limit]]

    def follower_ids(self, target_id: str, limit: int = 1000) -> List[str]:
        """Ai dang theo doi nguoi nay — dung de phat thong bao."""
        with self._lock:
            rows = [f for f in self._user_follows.values()
                    if f.target_id == target_id]
        rows.sort(key=lambda f: (f.created_at, f.follower_id), reverse=True)
        return [f.follower_id for f in rows[:limit]]

    def follower_counts(self, user_ids: Sequence[str]) -> Dict[str, int]:
        """So NGUOI THEO DOI cua nhieu nguoi, MOT luot."""
        can = set(user_ids)
        dem = {uid: 0 for uid in can}
        with self._lock:
            for f in self._user_follows.values():
                if f.target_id in can:
                    dem[f.target_id] += 1
        return dem

    def following_counts(self, user_ids: Sequence[str]) -> Dict[str, int]:
        """So nguoi MA HO theo doi, MOT luot."""
        can = set(user_ids)
        dem = {uid: 0 for uid in can}
        with self._lock:
            for f in self._user_follows.values():
                if f.follower_id in can:
                    dem[f.follower_id] += 1
        return dem

    def following_flags(self, follower_id: str,
                        target_ids: Sequence[str]) -> Set[str]:
        """
        Trong danh sach nay, minh dang theo doi nhung ai.

        MOT luot cho ca trang. Hoi tung nguoi mot la dung cai N+1 da tung lam
        khu quan tri mat 34 giay — xem ghi chu o `MockMetadataStore`.
        """
        can = set(target_ids)
        with self._lock:
            return {f.target_id for f in self._user_follows.values()
                    if f.follower_id == follower_id and f.target_id in can}

    def count_follows_since(self, follower_id: str, since: str) -> int:
        """Bao nhieu lan theo doi ke tu moc nay — cho han muc chong spam."""
        with self._lock:
            return sum(1 for f in self._user_follows.values()
                       if f.follower_id == follower_id and f.created_at >= since)

    # =========================================================== THEO DOI TRUYEN

    def follow_story(self, follow: StoryFollow) -> bool:
        with self._lock:
            if follow.follow_id in self._story_follows:
                return False
            self._story_follows[follow.follow_id] = follow
            return True

    def unfollow_story(self, follow_id: str) -> bool:
        with self._lock:
            return self._story_follows.pop(follow_id, None) is not None

    def is_following_story(self, follow_id: str) -> bool:
        with self._lock:
            return follow_id in self._story_follows

    def story_follower_ids(self, novel_id: str, limit: int = 1000) -> List[str]:
        """Ai theo doi truyen nay — dung khi co chuong moi."""
        with self._lock:
            rows = [f for f in self._story_follows.values()
                    if f.novel_id == novel_id]
        rows.sort(key=lambda f: (f.created_at, f.follower_id), reverse=True)
        return [f.follower_id for f in rows[:limit]]

    def followed_story_ids(self, follower_id: str,
                           limit: int = 200) -> List[str]:
        with self._lock:
            rows = [f for f in self._story_follows.values()
                    if f.follower_id == follower_id]
        rows.sort(key=lambda f: (f.created_at, f.novel_id), reverse=True)
        return [f.novel_id for f in rows[:limit]]

    def story_follower_counts(self, novel_ids: Sequence[str]) -> Dict[str, int]:
        can = set(novel_ids)
        dem = {nid: 0 for nid in can}
        with self._lock:
            for f in self._story_follows.values():
                if f.novel_id in can:
                    dem[f.novel_id] += 1
        return dem

    def story_following_flags(self, follower_id: str,
                              novel_ids: Sequence[str]) -> Set[str]:
        can = set(novel_ids)
        with self._lock:
            return {f.novel_id for f in self._story_follows.values()
                    if f.follower_id == follower_id and f.novel_id in can}

    # ================================================================= BAI DANG

    def create_post(self, post: Post) -> Post:
        with self._lock:
            self._posts[post.post_id] = post
            return post

    def get_post(self, post_id: str) -> Optional[Post]:
        with self._lock:
            return self._posts.get(post_id)

    def save_post(self, post: Post) -> Post:
        with self._lock:
            post.updated_at = now_iso_us()
            self._posts[post.post_id] = post
            return post

    def delete_post(self, post_id: str) -> bool:
        """
        Xoa THAT. Chi dung khi CHINH CHU xoa bai cua minh.

        Kiem duyet KHONG di duong nay — no dat `state = REMOVED`. Xem
        `ContentState`.
        """
        with self._lock:
            return self._posts.pop(post_id, None) is not None

    def posts_by_ids(self, post_ids: Sequence[str]) -> Dict[str, Post]:
        can = set(post_ids)
        with self._lock:
            return {pid: p for pid, p in self._posts.items() if pid in can}

    def list_posts(self, *, author_ids: Optional[Sequence[str]] = None,
                   novel_id: str = "", query: str = "",
                   include_removed: bool = False,
                   limit: int = 20, offset: int = 0) -> Tuple[List[Post], int]:
        """
        Bai dang, MOI NHAT truoc, da loc va da phan trang.

        `author_ids=None` nghia la KHONG loc theo tac gia (bang tin kham pha).
        `author_ids=[]` — danh sach RONG — nghia la khong ai ca, va tra ve rong.
        Hai truong hop do khac nhau, va gop chung lai la mot loi kinh dien: mot
        nguoi chua theo doi ai se thay bang tin cua TOAN he thong.
        """
        with self._lock:
            rows = list(self._posts.values())
        if author_ids is not None:
            can = set(author_ids)
            rows = [p for p in rows if p.author_user_id in can]
        if novel_id:
            rows = [p for p in rows if p.novel_id == novel_id]
        if not include_removed:
            rows = [p for p in rows if p.state is ContentState.VISIBLE]
        if query:
            can_tim = query.strip().lower()
            rows = [p for p in rows if can_tim in (p.text or "").lower()]
        rows.sort(key=lambda p: (p.created_at, p.post_id), reverse=True)
        return rows[offset:offset + limit], len(rows)

    def post_counts(self, user_ids: Sequence[str]) -> Dict[str, int]:
        """So bai CON HIEN cua nhieu nguoi, MOT luot."""
        can = set(user_ids)
        dem = {uid: 0 for uid in can}
        with self._lock:
            for p in self._posts.values():
                if p.author_user_id in can and p.state is ContentState.VISIBLE:
                    dem[p.author_user_id] += 1
        return dem

    def count_posts_since(self, author_user_id: str, since: str) -> int:
        with self._lock:
            return sum(1 for p in self._posts.values()
                       if p.author_user_id == author_user_id
                       and p.created_at >= since)

    def bump_post_counter(self, post_id: str, field: str, delta: int) -> int:
        """
        Cong don vao mot bo dem cua bai, tra ve gia tri MOI.

        HAN CHE DA BIET, va ban Appwrite cung the: day la DOC-ROI-GHI. Hai luot
        thich cho cung mot bai trong cung mot phan giay co the lam mat mot don
        vi. Chap nhan duoc vi buoc QUAN TRONG — khong tao hai luot thich cho
        cung mot nguoi — da duoc tinh duy nhat cua `like_id` chan tuyet doi;
        cai co the mat o day chi la mot con so dem, va no dem lai duoc tu bang
        su that bang `recount_post`.
        """
        with self._lock:
            post = self._posts.get(post_id)
            if post is None:
                return 0
            cu = int(getattr(post, field, 0) or 0)
            moi = max(0, cu + delta)
            setattr(post, field, moi)
            return moi

    # ============================================================ LUOT THICH

    def like_post(self, like: PostLike) -> bool:
        """`False` = da thich tu truoc. Xem `follow_user` ve y nghia cua co nay."""
        with self._lock:
            if like.like_id in self._post_likes:
                return False
            self._post_likes[like.like_id] = like
            return True

    def unlike_post(self, like_id: str) -> bool:
        with self._lock:
            return self._post_likes.pop(like_id, None) is not None

    def has_liked(self, like_id: str) -> bool:
        with self._lock:
            return like_id in self._post_likes

    def liked_flags(self, user_id: str, post_ids: Sequence[str]) -> Set[str]:
        """Trong trang nay, minh da thich nhung bai nao. MOT luot."""
        can = set(post_ids)
        with self._lock:
            return {lk.post_id for lk in self._post_likes.values()
                    if lk.user_id == user_id and lk.post_id in can}

    def count_post_likes(self, post_id: str) -> int:
        """Dem lai tu bang SU THAT — dung de doi soat bo dem khi nghi no lech."""
        with self._lock:
            return sum(1 for lk in self._post_likes.values()
                       if lk.post_id == post_id)

    # ============================================================== BINH LUAN

    def create_comment(self, comment: Comment) -> Comment:
        with self._lock:
            self._comments[comment.comment_id] = comment
            return comment

    def get_comment(self, comment_id: str) -> Optional[Comment]:
        with self._lock:
            return self._comments.get(comment_id)

    def save_comment(self, comment: Comment) -> Comment:
        with self._lock:
            comment.updated_at = now_iso_us()
            self._comments[comment.comment_id] = comment
            return comment

    def delete_comment(self, comment_id: str) -> bool:
        with self._lock:
            return self._comments.pop(comment_id, None) is not None

    def list_comments(self, post_id: str, *, parent_id: Optional[str] = None,
                      include_removed: bool = True,
                      newest_first: bool = False,
                      limit: int = 20,
                      offset: int = 0) -> Tuple[List[Comment], int]:
        """
        Binh luan cua mot DICH (bai dang hoac chuong), mac dinh CU NHAT truoc.

        Nguoc voi bang tin, va co ly do: mot cuoc trao doi doc theo thu tu no
        dien ra. Bang tin thi khong — o do "vua co gi moi" la cau hoi.
        `newest_first=True` danh cho binh luan CHUONG: mot chuong co the gom
        binh luan qua nhieu thang, va nguoi vua nghe xong muon thay nguoi ta
        vua noi gi.

        `parent_id=""` lay binh luan GOC; mot `comment_id` lay cac tra loi cua
        no; `None` lay tat ca.

        `include_removed` mac dinh BAT: binh luan bi go van tra ve (khong kem
        noi dung) de mot tra loi khong treo lo lung — xem `Comment.to_public_dict`.
        """
        with self._lock:
            rows = [c for c in self._comments.values() if c.post_id == post_id]
        if parent_id is not None:
            rows = [c for c in rows if c.parent_id == parent_id]
        if not include_removed:
            rows = [c for c in rows if c.state is ContentState.VISIBLE]
        rows.sort(key=lambda c: (c.created_at, c.comment_id),
                  reverse=newest_first)
        return rows[offset:offset + limit], len(rows)

    def comments_for_posts(self, post_ids: Sequence[str],
                           moi_bai: int = 2) -> Dict[str, List[Comment]]:
        """
        Vai binh luan GOC MOI NHAT cua NHIEU bai, MOT luot — cho phan xem
        truoc kieu bang tin. Cung ly do ton tai voi `replies_for`: khong co no
        thi 20 bai tren bang tin la 20 truy van nua.

        Tra ve theo thu tu CU->MOI trong tung bai (dung thu tu doc), nhung
        chon N cai MOI NHAT — nhu moi bang tin quen thuoc.
        """
        can = set(p for p in post_ids if p)
        if not can:
            return {}
        with self._lock:
            rows = [c for c in self._comments.values()
                    if c.post_id in can and c.parent_id == ""
                    and c.state is ContentState.VISIBLE]
        rows.sort(key=lambda c: (c.created_at, c.comment_id), reverse=True)
        gom: Dict[str, List[Comment]] = {pid: [] for pid in can}
        for c in rows:
            if len(gom[c.post_id]) < moi_bai:
                gom[c.post_id].append(c)
        return {pid: list(reversed(ds)) for pid, ds in gom.items()}

    def count_comments(self, *, created_after: str = "") -> int:
        """Tong so binh luan TREN TOAN NEN TANG (bai dang + tap animation) —
        bang dieu khien quan tri (Admin Control Center V2, A1 + Phase 7
        analytics: `created_after` loc theo ngay tao)."""
        with self._lock:
            if not created_after:
                return len(self._comments)
            return sum(1 for c in self._comments.values()
                      if c.created_at >= created_after)

    def list_comments_all(self, *, target_kind: str = "",
                          limit: int = 25,
                          offset: int = 0) -> Tuple[List[Comment], int]:
        """
        Duyet binh luan toan he thong cho khu QUAN TRI, moi nhat truoc.

        `target_kind=""` = binh luan bai dang (gia tri cua moi hang cu);
        `"chapter"` = binh luan chuong. Khu quan tri can phan biet duoc hai
        loai — chung dan toi hai noi khac nhau.
        """
        with self._lock:
            rows = [c for c in self._comments.values()
                    if (c.target_kind or "") == (target_kind or "")]
        rows.sort(key=lambda c: (c.created_at, c.comment_id), reverse=True)
        return rows[offset:offset + limit], len(rows)

    def replies_for(self, parent_ids: Sequence[str],
                    moi_cha: int = 3) -> Dict[str, List[Comment]]:
        """
        Vai tra loi dau cua NHIEU binh luan goc, MOT luot.

        Khong co ham nay thi mot trang 20 binh luan goc thanh 20 truy van nua.
        `moi_cha` la so tra loi hien san; phan con lai di qua `list_comments`
        khi nguoi dung bam "Xem thêm".
        """
        can = set(parent_ids)
        if not can:
            return {}
        gom: Dict[str, List[Comment]] = {pid: [] for pid in can}
        with self._lock:
            rows = [c for c in self._comments.values() if c.parent_id in can]
        rows.sort(key=lambda c: (c.created_at, c.comment_id))
        for c in rows:
            if len(gom[c.parent_id]) < moi_cha:
                gom[c.parent_id].append(c)
        return gom

    def count_post_comments(self, post_id: str) -> int:
        """Dem lai tu bang su that, chi tinh binh luan CON HIEN."""
        with self._lock:
            return sum(1 for c in self._comments.values()
                       if c.post_id == post_id
                       and c.state is ContentState.VISIBLE)

    def count_comments_since(self, author_user_id: str, since: str) -> int:
        with self._lock:
            return sum(1 for c in self._comments.values()
                       if c.author_user_id == author_user_id
                       and c.created_at >= since)

    def bump_comment_counter(self, comment_id: str, field: str,
                             delta: int) -> int:
        with self._lock:
            row = self._comments.get(comment_id)
            if row is None:
                return 0
            cu = int(getattr(row, field, 0) or 0)
            moi = max(0, cu + delta)
            setattr(row, field, moi)
            return moi

    def comments_by_ids(self, comment_ids: Sequence[str]) -> Dict[str, Comment]:
        can = set(comment_ids)
        with self._lock:
            return {cid: c for cid, c in self._comments.items() if cid in can}

    # =============================================================== THONG BAO

    def create_notification_once(self, note: Notification) -> bool:
        """
        Tao neu khoa chua ton tai. `False` = da co thong bao giong het hom nay.

        Chinh tinh duy nhat cua `notification_id` la co che chong lap — xem
        `social.notification_key`. Khong co bo dem nao ca.
        """
        with self._lock:
            if note.notification_id in self._notifications:
                return False
            self._notifications[note.notification_id] = note
            return True

    def list_notifications(self, user_id: str, *, unread_only: bool = False,
                           limit: int = 20,
                           offset: int = 0) -> Tuple[List[Notification], int]:
        with self._lock:
            rows = [n for n in self._notifications.values()
                    if n.user_id == user_id]
        if unread_only:
            rows = [n for n in rows if not n.read]
        rows.sort(key=lambda n: (n.created_at, n.notification_id), reverse=True)
        return rows[offset:offset + limit], len(rows)

    def count_unread(self, user_id: str) -> int:
        with self._lock:
            return sum(1 for n in self._notifications.values()
                       if n.user_id == user_id and not n.read)

    def mark_notification_read(self, user_id: str,
                               notification_id: str) -> bool:
        """
        Danh dau da doc. `user_id` la mot phan cua DIEU KIEN, khong phai mot
        tham so trang tri: khong co no thi bat ky ai doan duoc mot id la danh
        dau duoc thong bao cua nguoi khac.
        """
        with self._lock:
            note = self._notifications.get(notification_id)
            if note is None or note.user_id != user_id:
                return False
            note.read = True
            return True

    def mark_all_read(self, user_id: str) -> int:
        with self._lock:
            dem = 0
            for note in self._notifications.values():
                if note.user_id == user_id and not note.read:
                    note.read = True
                    dem += 1
            return dem

    # ================================================================= BAO CAO

    def create_report_once(self, report: ContentReport) -> bool:
        """`False` = nguoi nay da bao cao dung noi dung nay roi."""
        with self._lock:
            if report.report_id in self._reports:
                return False
            self._reports[report.report_id] = report
            return True

    def get_report(self, report_id: str) -> Optional[ContentReport]:
        with self._lock:
            return self._reports.get(report_id)

    def save_report(self, report: ContentReport) -> ContentReport:
        with self._lock:
            report.updated_at = now_iso_us()
            self._reports[report.report_id] = report
            return report

    def list_reports(self, *, status: Optional[ReportStatus] = None,
                     target_kind: str = "", limit: int = 25,
                     offset: int = 0) -> Tuple[List[ContentReport], int]:
        """Cho xu ly thi CU NHAT truoc — khong ai bi bo quen vinh vien."""
        with self._lock:
            rows = list(self._reports.values())
        if status is not None:
            rows = [r for r in rows if r.status is status]
        if target_kind:
            rows = [r for r in rows if r.target_kind == target_kind]
        rows.sort(key=lambda r: (r.created_at, r.report_id))
        return rows[offset:offset + limit], len(rows)

    def count_reports(self, status: Optional[ReportStatus] = None) -> int:
        with self._lock:
            rows = list(self._reports.values())
        if status is not None:
            rows = [r for r in rows if r.status is status]
        return len(rows)

    def count_reports_since(self, reporter_id: str, since: str) -> int:
        with self._lock:
            return sum(1 for r in self._reports.values()
                       if r.reporter_id == reporter_id and r.created_at >= since)

    def reports_for_targets(self, target_ids: Sequence[str]) -> Dict[str, int]:
        """So bao cao CON MO cua nhieu doi tuong, MOT luot."""
        can = set(target_ids)
        dem = {tid: 0 for tid in can}
        with self._lock:
            for r in self._reports.values():
                if r.target_id in can and r.status is ReportStatus.OPEN:
                    dem[r.target_id] += 1
        return dem
