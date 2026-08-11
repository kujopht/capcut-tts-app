"""
Tang SERVICE cho tac gia: don, duyet, uy tin.

Vi sao co tang nay thay vi viet thang trong route: mot phan cua no KHONG CO
route. Cac ham `approve` / `reject` / `suspend` / `restore` la thao tac cua
NGUOI DUYET, va du an nay chua co co che phan quyen quan tri nao — khong co vai
tro, khong co bang admin, khong co xac thuc hai buoc.

Mo mot endpoint duyet ma khong co cai do la tang mot cai cong: bat ky ai doan
duoc duong dan deu tu phong minh lam tac gia. Nen o day cac ham do ton tai,
duoc kiem thu day du, va KHONG mot route HTTP nao goi chung. Trang quan tri la
viec sau, va khi lam thi no chi can goi dung nhung ham nay.

Xem `docs/AUTHOR_RANK.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from server.creator import (
    ALREADY_CREDITED,
    AuthorStateError,
    CREDITED,
    UsernameTaken,
    can_publish,
    can_resubmit,
    can_transition,
    credit_key,
    dedupe_day_bucket,
    evaluate_listen,
    public_author_card,
    public_profile,
    rank_progress,
    validate_username,
)
from server.domain import (
    AuthorApplication,
    AuthorStats,
    AuthorStatus,
    ListenCredit,
    ModerationEvent,
    Profile,
    PublishState,
    now_iso,
)

#: Gioi han do dai. Cat o backend chu khong tin vao `maxLength` cua o nhap: mot
#: request curl khong di qua o nhap nao.
MAX_PEN_NAME = 60
MAX_BIO = 400
MAX_INTRO = 1000
MAX_GENRES = 8


class CreatorService:
    """
    Moi thay doi ve trang thai tac gia va uy tin di qua day.

    Nhan `identity` (noi ho so song) va `store` (noi don / thong ke / luot nghe
    song) — cung hai doi tuong ma cac route dang dung, nen khong co duong ghi
    nao thu hai.
    """

    def __init__(self, identity: Any, store: Any):
        self._identity = identity
        self._store = store
        #: Moc goi khi mot don duoc DUYET hoac TU CHOI. `None` = khong ai nghe.
        #: `server/main.py` gan `SocialService.notify_author_decision` vao day.
        #: Xem ghi chu trong `_decide` ve vi sao la mot moc chu khong phai mot
        #: import.
        self.on_decision: Optional[Any] = None

    # =========================================================== ho so cong khai

    def set_username(self, profile: Profile, raw: str) -> Profile:
        """
        Dat ten cong khai. Nem `UsernameError` voi ly do doc duoc.

        CHO doi ten: nguoi ta go sai, hoac doi y. Khong gioi han so lan o V1 —
        nhung khi da co lien ket ngoai tro toi `/u/ten-cu` thi doi ten se lam
        chung hong, nen day la mot cho can xem lai truoc khi mo cho nguoi that
        (ghi trong "Han che da biet").
        """
        ten = validate_username(raw)
        hien = self._identity.profile_by_username(ten)
        if hien is not None and hien.user_id != profile.user_id:
            raise UsernameTaken("Tên người dùng này đã có người dùng.")
        profile.username = ten
        return self._identity.save_profile(profile)

    def set_bio(self, profile: Profile, bio: str) -> Profile:
        profile.bio = (bio or "").strip()[:MAX_BIO]
        return self._identity.save_profile(profile)

    def public_profile_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Trang cong khai theo username, KEM truyen da xuat ban.

        Tra `None` khi khong co — route se doi thanh 404. Khong phan biet "khong
        ton tai" voi "ton tai nhung chua chon username": ca hai deu la khong co
        trang cong khai, va phan biet ra thi thanh mot cach do xem email nao da
        dang ky.
        """
        profile = self._identity.profile_by_username(username)
        if profile is None:
            return None
        return self._public_bundle(profile)

    def _public_bundle(self, profile: Profile) -> Dict[str, Any]:
        stats = self._store.get_stats(profile.user_id)
        truyen = [
            n.to_dict() for n in self._store.list_novels(
                owner_id=profile.user_id, published_only=True)
        ]
        # `published_novels` lay tu SO DEM THAT ngay day, khong tu ban tong hop:
        # ban tong hop co the lech, con day thi vua doc xong danh sach.
        goi = public_profile(profile.to_dict(), stats={
            "qualified_listens": stats.qualified_listens,
            "published_novels": len(truyen),
        })
        goi["novels"] = truyen
        return goi

    # =========================================================== don tac gia

    def creator_state(self, profile: Profile) -> Dict[str, Any]:
        """
        Toan bo thu giao dien can de ve khu Creator, trong MOT lan goi.

        Gop lai chu khong de frontend goi ba lan: ba lan goi thi co ba trang
        thai tai va giao dien phai ve ca ba, va cai thu ba luon la cai bi quen.
        """
        status = profile.author_status
        app = self._store.get_application(profile.user_id)
        stats = self._store.get_stats(profile.user_id)
        duoc_nop, ly_do = can_resubmit(status, app.decided_at if app else None)
        data: Dict[str, Any] = {
            "author_status": status.value,
            "can_publish": can_publish(status),
            "can_apply": duoc_nop,
            "apply_blocked_reason": ly_do,
            "username": profile.username,
            "bio": profile.bio,
            "application": app.to_public_dict() if app else None,
        }
        if status is AuthorStatus.APPROVED:
            data["rank"] = rank_progress(stats.qualified_listens)
            data["qualified_listens"] = stats.qualified_listens
            data["published_novels"] = len(self._store.list_novels(
                owner_id=profile.user_id, published_only=True))
        return data

    def apply(
        self,
        profile: Profile,
        *,
        pen_name: str,
        bio: str = "",
        genres: Optional[List[str]] = None,
        intro: str = "",
        accepted_rules: bool = False,
        now: Optional[datetime] = None,
    ) -> AuthorApplication:
        """
        Nop (hoac nop lai) don. Chuyen trang thai `none|rejected -> pending`.

        KHONG hoi thong tin danh tinh doi thuc: khong so CMND, khong ngay sinh,
        khong dia chi. Muc dich cua buoc duyet nay la chan spam va noi dung sai
        quy dinh, khong phai lap mot ho so cong dan — va du lieu khong thu thap
        la du lieu khong the bi ro ri.
        """
        cu = profile.author_status
        duoc, ly_do = can_resubmit(cu, None if cu is not AuthorStatus.REJECTED
                                   else self._decided_at(profile), now=now)
        if not duoc:
            raise AuthorStateError(ly_do)
        if not accepted_rules:
            raise AuthorStateError("Bạn cần đồng ý với quy định xuất bản.")
        ten = (pen_name or "").strip()
        if len(ten) < 2:
            raise AuthorStateError("Bút danh cần ít nhất 2 ký tự.")
        if not (intro or "").strip():
            raise AuthorStateError("Hãy viết vài dòng giới thiệu về bạn.")
        if not can_transition(cu, AuthorStatus.PENDING):
            raise AuthorStateError("Không thể gửi đơn từ trạng thái hiện tại.")

        cu_app = self._store.get_application(profile.user_id)
        app = AuthorApplication(
            user_id=profile.user_id,
            pen_name=ten[:MAX_PEN_NAME],
            bio=(bio or "").strip()[:MAX_BIO],
            genres=[g.strip() for g in (genres or []) if g.strip()][:MAX_GENRES],
            intro=(intro or "").strip()[:MAX_INTRO],
            accepted_rules=True,
            status=AuthorStatus.PENDING,
            # Nop lai thi giu so lan va XOA ghi chu cua nguoi duyet truoc: ghi
            # chu do noi ve ban don cu, de lai canh don moi la gay hieu nham.
            attempts=(cu_app.attempts + 1) if cu_app else 1,
            reviewer_note="",
            decided_at=None,
        )
        # Nop lai thi GIU nguyen `application_id` va `created_at`: day la cung
        # mot don duoc viet lai, va doi khoa se lam moi lien ket cu tro toi mot
        # ban ghi khong con.
        if cu_app is not None:
            app.application_id = cu_app.application_id
            app.created_at = cu_app.created_at
        self._store.save_application(app)
        self._set_status(profile, AuthorStatus.PENDING)
        return app

    def _decided_at(self, profile: Profile) -> Optional[str]:
        app = self._store.get_application(profile.user_id)
        return app.decided_at if app else None

    # ====================================================== MODERATION
    #
    # KHONG co route nao goi cac ham duoi day. Xem ghi chu o dau tep: du an chua
    # co co che phan quyen quan tri, va mot endpoint duyet khong duoc bao ve la
    # mot cai cong mo. Chung o day, duoc kiem thu, cho trang quan tri.

    def approve(self, user_id: str, *, note: str = "",
                actor_id: str = "") -> AuthorApplication:
        """Duyet. `pending -> approved`."""
        return self._decide(user_id, AuthorStatus.APPROVED, note,
                            actor_id, "author_approved")

    def reject(self, user_id: str, *, note: str = "",
               actor_id: str = "") -> AuthorApplication:
        """
        Tu choi. `pending -> rejected`.

        `note` HIEN cho nguoi nop — ho can biet phai sua gi. Nem loi neu de
        trong: mot lan tu choi khong ly do la mot cai cua dong im lang.
        """
        if not (note or "").strip():
            raise AuthorStateError("Cần ghi chú lý do khi từ chối đơn.")
        return self._decide(user_id, AuthorStatus.REJECTED, note,
                            actor_id, "author_rejected")

    def suspend(self, user_id: str, *, note: str = "",
                actor_id: str = "") -> AuthorApplication:
        """
        Tam dung quyen xuat ban. `approved -> suspended`.

        KHONG go xuat ban cac truyen da co: mot tac gia bi treo van con doc gia,
        va rut truyen cua ho khoi tay nguoi doc la mot hinh phat danh vao nguoi
        khac. Chi chan xuat ban MOI. Ban nhap, chuong va audio deu khong bi cham.
        """
        return self._decide(user_id, AuthorStatus.SUSPENDED, note,
                            actor_id, "author_suspended")

    def restore(self, user_id: str, *, note: str = "",
                actor_id: str = "") -> AuthorApplication:
        """Phuc hoi sau khi treo. `suspended -> approved`."""
        return self._decide(user_id, AuthorStatus.APPROVED, note,
                            actor_id, "author_restored")

    def _decide(self, user_id: str, moi: AuthorStatus, note: str,
                actor_id: str = "", hanh_dong: str = "") -> AuthorApplication:
        profile = self._identity.get_profile(user_id)
        cu = profile.author_status
        if not can_transition(cu, moi):
            raise AuthorStateError(
                f"Không thể chuyển từ '{cu.value}' sang '{moi.value}'."
            )
        app = self._store.get_application(user_id)
        if app is None:
            # Grandfather: tac gia co san truoc khi co he thong duyet. Tao mot
            # ban ghi de lich su van giai thich duoc — xem `TRANSITIONS`, khong
            # co buoc nao nhay thang tu `none`.
            app = AuthorApplication(
                user_id=user_id,
                pen_name=profile.display_name or profile.username or "",
                accepted_rules=True,
                status=cu,
            )
        app.status = moi
        app.reviewer_note = (note or "").strip()
        app.decided_at = now_iso()
        self._store.save_application(app)
        self._set_status(profile, moi)

        # Ghi nhat ky SAU khi da doi trang thai thanh cong. Ghi truoc thi mot buoc
        # chuyen bi tu choi van de lai mot dong "da duyet" trong nhat ky.
        if hanh_dong:
            self._store.record_event(ModerationEvent(
                action=hanh_dong,
                target_user_id=user_id,
                actor_id=actor_id,
                note=(note or "").strip(),
            ))

        # Bao cho nguoi nop don, neu co ai dang nghe.
        #
        # `on_decision` la mot MOC, mac dinh `None`. Tang nay khong import tang
        # xa hoi: `SocialService` da phu thuoc vao `creator` (no dung
        # `public_author_card` va `rank_progress`), nen mot import nguoc se tao
        # vong phu thuoc — thu rat kho thao ra sau nay. `server/main.py` gan moc
        # nay khi khoi tao.
        #
        # Loi trong duong thong bao KHONG duoc lam hong quyet dinh kiem duyet:
        # trang thai da doi va nhat ky da ghi, nen mot thong bao that lac la thu
        # nho hon nhieu so voi mot lan duyet bao loi ma van co hieu luc mot nua.
        if self.on_decision is not None and moi in (AuthorStatus.APPROVED,
                                                    AuthorStatus.REJECTED):
            try:
                self.on_decision(user_id,
                                 approved=moi is AuthorStatus.APPROVED,
                                 actor_id=actor_id, note=(note or "").strip())
            except Exception:
                pass
        return app

    def _set_status(self, profile: Profile, status: AuthorStatus) -> Profile:
        profile.author_status = status
        return self._identity.save_profile(profile)

    def pending_applications(self, limit: int = 50,
                             offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """Danh sach cho trang quan tri sau nay. Chua co route nao goi toi."""
        rows, total = self._store.list_applications(
            status=AuthorStatus.PENDING, limit=limit, offset=offset)
        return [r.to_dict() for r in rows], total

    # =========================================================== xuat ban

    def assert_can_publish(self, profile: Profile) -> None:
        """
        Cong CHAN XUAT BAN. Nem `AuthorStateError` voi thong diep dung trang thai.

        Goi ngay TRUOC khi doi `state` cua truyen, va khong bao gio o cho khac:
        tao/sua/xoa ban nhap deu khong di qua day, va do la co y — ai cung viet
        duoc, chi khong ai cung dua ra cong khai duoc.
        """
        status = profile.author_status
        if can_publish(status):
            return
        if status is AuthorStatus.PENDING:
            raise AuthorStateError(
                "Đơn tác giả của bạn đang chờ duyệt. Bản nháp vẫn sửa được."
            )
        if status is AuthorStatus.REJECTED:
            raise AuthorStateError(
                "Đơn tác giả của bạn chưa được duyệt. Bạn có thể gửi lại đơn."
            )
        if status is AuthorStatus.SUSPENDED:
            raise AuthorStateError(
                "Quyền xuất bản của bạn đang bị tạm dừng."
            )
        raise AuthorStateError(
            "Bạn cần đăng ký tác giả trước khi xuất bản truyện."
        )

    # =========================================================== uy tin

    def record_listen(
        self,
        *,
        listener_id: Optional[str],
        chapter_id: str,
        author_id: str,
        listened_seconds: float,
        duration_seconds: float,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Ghi nhan mot lan nghe. May chu la nguon su that.

        Tra ve `{"credited": bool, "reason": str}`. KHONG tra ve so lan nghe moi
        cua tac gia: nguoi nghe khong can biet, va tra ve thi thanh mot cach dem
        uy tin cua nguoi khac bang cach bam Phat.

        Trinh tu: danh gia bang ham THUAN truoc (re, khong cham kho), roi moi ghi.
        Buoc ghi dung khoa TAT DINH nen mot cuoc dua chi tao mot hang.
        """
        moment = now or datetime.now(timezone.utc)
        moc_cu = (self._store.last_credit_at(listener_id, chapter_id)
                  if listener_id else None)
        duoc, ly_do = evaluate_listen(
            listener_id=listener_id,
            author_id=author_id,
            listened_seconds=listened_seconds,
            duration_seconds=duration_seconds,
            last_credit_at=moc_cu,
            now=moment,
        )
        if not duoc:
            return {"credited": False, "reason": ly_do}

        credit = ListenCredit(
            listener_id=listener_id or "",
            author_id=author_id,
            chapter_id=chapter_id,
            day_bucket=dedupe_day_bucket(moment),
            listened_seconds=float(listened_seconds),
            credit_id=credit_key(listener_id or "", chapter_id, moment),
        )
        if not self._store.create_credit_once(credit):
            # Mot request khac vua thang cuoc dua. Khong phai loi.
            return {"credited": False, "reason": ALREADY_CREDITED}
        self._store.add_qualified_listen(author_id, 1)
        return {"credited": True, "reason": CREDITED}

    def recount_listens(self, author_id: str) -> AuthorStats:
        """
        Dung lai ban tong hop tu bang su that.

        Dung khi nghi `stats` da lech (mot buoc cong bi mat vi loi mang giua hai
        lenh). Chay lai bao nhieu lan cung duoc.
        """
        that = self._store.count_credits(author_id)
        stats = self._store.get_stats(author_id)
        stats.qualified_listens = that
        return self._store.save_stats(stats)

    # =========================================================== tim kiem

    def search_people(self, query: str, *, authors_only: bool = False,
                      limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        Tim nguoi. `authors_only=True` thi CHI tac gia da duyet.

        Loc `authors_only` ap SAU khi phan trang cua kho tra ve, nen tong so co
        the lon hon so hang tra ve. Do la mot han che da biet cua V1 (ghi trong
        bao cao): kho hien tai khong loc theo `author_status` o tang truy van.
        """
        rows, total = self._identity.search_profiles(query, limit=limit,
                                                     offset=offset)
        ket_qua = []
        for p in rows:
            if authors_only and p.author_status is not AuthorStatus.APPROVED:
                continue
            stats = self._store.get_stats(p.user_id)
            ket_qua.append(public_author_card(p.to_dict(), {
                "qualified_listens": stats.qualified_listens,
                "published_novels": stats.published_novels,
            }))
        return {"people": ket_qua, "total": total,
                "limit": limit, "offset": offset}

    # =========================================================== grandfather

    def grandfather_existing_authors(self, *, dry_run: bool = True) -> Dict[str, Any]:
        """
        Cong nhan cac tac gia DA CO truoc khi he thong duyet ton tai.

        Vi sao bat buoc phai co: neu bat co che chan xuat ban ma khong chay buoc
        nay, moi nguoi dung dang co truyen da xuat ban se mat quyen xuat ban
        chuong tiep theo cua chinh truyen ho dang viet. Do la mot loi khoa cua
        nguoi dung ra khoi cong viec cua ho, va no am tham.

        Quy tac: ai dang so huu it nhat MOT truyen `published` thi thanh
        `approved`, kem mot ban ghi don ghi ro day la grandfather.

        `dry_run=True` la MAC DINH va co y: goi ham nay khong bao gio doi du lieu
        tru khi nguoi goi noi ro. Xem `scripts/grandfather_authors.py`.
        """
        ai: Dict[str, int] = {}
        for novel in self._store.list_novels(owner_id=None, published_only=True):
            if novel.state is PublishState.PUBLISHED:
                ai[novel.owner_id] = ai.get(novel.owner_id, 0) + 1

        ke_hoach: List[Dict[str, Any]] = []
        for user_id, so_truyen in sorted(ai.items()):
            try:
                profile = self._identity.get_profile(user_id)
            except Exception:
                ke_hoach.append({"user_id": user_id, "novels": so_truyen,
                                 "action": "bo_qua_khong_tim_thay_ho_so"})
                continue
            if profile.author_status is AuthorStatus.APPROVED:
                ke_hoach.append({"user_id": user_id, "novels": so_truyen,
                                 "action": "bo_qua_da_duyet"})
                continue
            if profile.author_status is AuthorStatus.SUSPENDED:
                # KHONG tu dong bo treo cho ai. Treo la mot quyet dinh cua nguoi.
                ke_hoach.append({"user_id": user_id, "novels": so_truyen,
                                 "action": "bo_qua_dang_bi_treo"})
                continue
            ke_hoach.append({"user_id": user_id, "novels": so_truyen,
                             "action": "duyet"})
            if not dry_run:
                app = self._store.get_application(user_id) or AuthorApplication(
                    user_id=user_id,
                    pen_name=profile.display_name or profile.username or "",
                    accepted_rules=True,
                    status=AuthorStatus.PENDING,
                )
                app.status = AuthorStatus.APPROVED
                app.reviewer_note = (
                    "Được công nhận tự động: đã có truyện xuất bản trước khi "
                    "hệ thống duyệt tác giả tồn tại."
                )
                app.decided_at = now_iso()
                self._store.save_application(app)
                profile.author_status = AuthorStatus.APPROVED
                self._identity.save_profile(profile)

        dem: Dict[str, int] = {}
        for hang in ke_hoach:
            dem[hang["action"]] = dem.get(hang["action"], 0) + 1

        return {
            "dry_run": dry_run,
            # Chu so huu KHAC NHAU co it nhat mot truyen da xuat ban.
            "candidates": len(ai),
            "would_approve": dem.get("duyet", 0),
            "already_approved": dem.get("bo_qua_da_duyet", 0),
            "skipped_suspended": dem.get("bo_qua_dang_bi_treo", 0),
            "missing_profile": dem.get("bo_qua_khong_tim_thay_ho_so", 0),
            # Cac hang khong roi vao nhom nao o tren — hien tai khong co, nhung
            # neu mot nhanh moi duoc them ma quen dem thi con so nay lo ra ngay
            # thay vi im lang bien mat khoi bao cao.
            "unclassified": len(ke_hoach) - sum(dem.values()),
            "plan": ke_hoach,
        }

    # =========================================================== QUAN TRI
    #
    # Cac ham duoi day phuc vu `/api/admin/*`. Chung KHONG tu kiem quyen: viec do
    # nam o tang route (`Depends(admin_profile)`), va gop hai trach nhiem vao mot
    # cho la cach chac chan de mot ngay nao do co cho goi thang ma quen kiem.
    #
    # Doi lai, MOI ham o day deu tra ve du lieu RIENG TU (email, trang thai duyet,
    # ghi chu noi bo). Khong bao gio goi chung tu mot route cong khai.

    def admin_overview(self) -> Dict[str, Any]:
        """
        So lieu cho bang dieu khien — SAU phep DEM, khong hang nao duoc keo ve.

        Ban truoc keo TAT CA ho so ve roi goi `get_stats` cho tung nguoi, cong
        them mot lan liet ke moi truyen da xuat ban. Tren Appwrite that do la
        23 giay cho sau persona.

        Gio: bon phep dem tren `author_applications`, mot phep dem tren `novels`,
        va mot phep cong tren `author_stats` — bang do co mot hang moi tac gia,
        nho hon bang luot nghe nhieu bac.
        """
        return {
            "pending_applications": self._store.count_applications(
                AuthorStatus.PENDING),
            "approved_authors": self._store.count_applications(
                AuthorStatus.APPROVED),
            "rejected_applications": self._store.count_applications(
                AuthorStatus.REJECTED),
            "suspended_authors": self._store.count_applications(
                AuthorStatus.SUSPENDED),
            "published_novels": self._store.total_published_novels(),
            # `search_profiles` CHI dem nguoi da chon username — mot su that ve
            # du lieu, khong phai mot phep dem thieu. Dat ten cho dung.
            "users_with_username": self._identity.search_profiles("", limit=1)[1],
            "qualified_listens": self._store.sum_qualified_listens(),
        }

    def admin_applications(self, status: Optional[str] = None, limit: int = 25,
                           offset: int = 0) -> Dict[str, Any]:
        """Hang doi don. Danh tinh duoc GHEP THEO LO cho dung trang hien tai."""
        loc = None
        if status:
            try:
                loc = AuthorStatus(status)
            except ValueError:
                loc = None
        rows, total = self._store.list_applications(status=loc, limit=limit,
                                                    offset=offset)
        ids = [r.user_id for r in rows]
        ho_so = self._identity.profiles_by_ids(ids)
        thong_ke = self._store.stats_by_ids(ids)
        return {
            "applications": [self._kem_nguoi(app, ho_so, thong_ke) for app in rows],
            "total": total, "limit": limit, "offset": offset,
        }

    def admin_application(self, user_id: str) -> Optional[Dict[str, Any]]:
        app = self._store.get_application(user_id)
        if app is None:
            return None
        return self._kem_nguoi(app,
                               self._identity.profiles_by_ids([user_id]),
                               self._store.stats_by_ids([user_id]))

    def _kem_nguoi(self, app: AuthorApplication,
                   ho_so: Dict[str, Profile],
                   thong_ke: Dict[str, Any]) -> Dict[str, Any]:
        data = app.to_dict()
        profile = ho_so.get(app.user_id)
        if profile is None:
            data["user"] = None
            return data
        stats = thong_ke.get(app.user_id)
        data["user"] = {
            "user_id": profile.user_id,
            # `email` CHI o duong quan tri. Khong bao gio o `/api/users/*`.
            "email": profile.email,
            "display_name": profile.display_name,
            "username": profile.username,
            "author_status": profile.author_status.value,
            "created_at": profile.created_at,
            "qualified_listens": stats.qualified_listens if stats else 0,
        }
        return data

    def admin_authors(self, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        """
        Tac gia da duyet VA dang bi treo, o cung mot cho.

        HAN CHE DA BIET: kho khong loc duoc theo `author_status` o tang truy van
        (cot do nam o bang `profiles`, va `search_profiles` khong nhan bo loc do),
        nen o day van phai keo mot trang lon roi loc. Khac ban truoc o cho: sau
        khi loc, MOI phep lam giau deu di THEO LO thay vi tung hang.
        """
        nguoi, _ = self._identity.search_profiles("", limit=500)
        loc = [p for p in nguoi if p.author_status in
               (AuthorStatus.APPROVED, AuthorStatus.SUSPENDED)]
        thong_ke = self._store.stats_by_ids([p.user_id for p in loc])
        loc.sort(key=lambda p: -thong_ke[p.user_id].qualified_listens)
        trang = loc[offset:offset + limit]
        return {
            "authors": self._lam_giau(trang),
            "total": len(loc), "limit": limit, "offset": offset,
        }

    def _lam_giau(self, ds: List[Profile]) -> List[Dict[str, Any]]:
        """Ghep hang + so truyen cho MOT TRANG ho so, bang dung hai truy van."""
        ids = [p.user_id for p in ds]
        thong_ke = self._store.stats_by_ids(ids)
        so_truyen = self._store.published_counts(ids)
        ra = []
        for p in ds:
            nghe = thong_ke[p.user_id].qualified_listens
            ra.append({
                "user_id": p.user_id,
                "email": p.email,
                "display_name": p.display_name,
                "username": p.username,
                "author_status": p.author_status.value,
                "created_at": p.created_at,
                "qualified_listens": nghe,
                "published_novels": so_truyen.get(p.user_id, 0),
                "rank": rank_progress(nghe),
            })
        return ra

    def admin_users(self, query: str = "", limit: int = 25,
                    offset: int = 0) -> Dict[str, Any]:
        """Tim o MAY CHU, phan trang o MAY CHU, lam giau THEO LO cho dung trang."""
        rows, total = self._identity.search_profiles(query, limit=limit,
                                                     offset=offset)
        return {
            "users": self._lam_giau(rows),
            "total": total, "limit": limit, "offset": offset,
        }

    def admin_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Chi tiet mot nguoi dung, KEM don va nhat ky kiem duyet cua ho."""
        profile = self._identity.profiles_by_ids([user_id]).get(user_id)
        if profile is None:
            return None
        data = self._lam_giau([profile])[0]
        data["bio"] = profile.bio
        app = self._store.get_application(user_id)
        data["application"] = app.to_dict() if app else None
        su_kien, _ = self._store.list_events(target_user_id=user_id, limit=25)
        data["events"] = [e.to_dict() for e in su_kien]
        data["novels"] = [
            n.to_dict() for n in self._store.list_novels(owner_id=user_id)
        ]
        return data

    def admin_novels(self, query: str = "", state: str = "", limit: int = 25,
                     offset: int = 0) -> Dict[str, Any]:
        """
        Duyet truyen cho quan tri — CHI DOC, va phan trang o phia KHO.

        Ban truoc keo TAT CA truyen ve roi cat o Python, cong them mot lan liet
        ke chuong VA mot lan doc ho so cho TUNG truyen. Gio: mot truy van co
        phan trang, roi hai truy van theo lo.

        KHONG co thao tac go xuong hay xoa — xem `docs/ADMIN.md`.
        """
        rows, total = self._store.find_novels(
            published_only=(state == "published"),
            query=query, limit=limit, offset=offset,
        )
        if state == "draft":
            # Kho chi loc duoc "chi da xuat ban"; ban nhap phai loc o day. Ghi
            # nhan la mot han che, khong giau no di.
            rows = [n for n in rows if n.state is PublishState.DRAFT]

        so_chuong = self._store.chapter_counts([n.novel_id for n in rows])
        ho_so = self._identity.profiles_by_ids([n.owner_id for n in rows])

        ra = []
        for n in rows:
            d = n.to_dict()
            d["chapters"] = so_chuong.get(n.novel_id, 0)
            chu = ho_so.get(n.owner_id)
            d["owner"] = ({"display_name": chu.display_name,
                           "username": chu.username} if chu else None)
            ra.append(d)
        return {"novels": ra, "total": total, "limit": limit, "offset": offset}

    def admin_events(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        rows, total = self._store.list_events(limit=limit, offset=offset)
        return {"events": [e.to_dict() for e in rows], "total": total}
