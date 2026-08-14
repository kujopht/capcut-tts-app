"""
Tang dich vu cua nen tang xa hoi.

MOI duong ghi cua tang xa hoi di qua day. Khong route nao cham thang vao kho, va
do khong phai mot quy uoc phong cach — day la noi ba thu duoc cuong che:

  1. QUYEN. "Bai nay co phai cua ban khong" duoc hoi o MOT cho. Rai phep kiem do
     ra tung route thi som muon cung co mot route quen no, va mot route quen la
     mot nguoi sua duoc bai cua nguoi khac.
  2. HAN MUC. Dem tren chinh bang du lieu, khong phai mot bo dem trong bo nho —
     backend co the chay nhieu tien trinh, va bo dem cuc bo se dem rieng o moi
     tien trinh, tuc la han muc that gap doi mot cach am tham.
  3. THONG BAO. Sinh ra ngay canh thao tac gay ra chung. Mot "duong thong bao"
     rieng chay sau se lech voi su that ngay lan dau ai do quen goi no.

Tang nay khong biet gi ve HTTP. No nem `SocialError` / `RateLimited` /
`PermissionDenied` / `NotFoundError`, va `server/main.py` doi chung thanh ma
trang thai. Nho vay no kiem thu duoc ma khong can dung mot may chu nao.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.adapters import NotFoundError, PermissionDenied
from server.creator import public_author_card, rank_progress
from server.domain import (
    Comment,
    ContentReport,
    ContentState,
    ModerationEvent,
    Notification,
    NotificationKind,
    Post,
    PostKind,
    PostLike,
    ReportReason,
    ReportStatus,
    StoryFollow,
    UserFollow,
    AuthorStatus,
    Profile,
    PublishState,
    now_iso_us,
)
from server.social import (
    COMMENT_MAX_CHARS,
    POST_MAX_IMAGES,
    kiem_bo_anh,
    kiem_timestamp,
    HAN_MUC_MAC_DINH,
    HanMuc,
    MODERATION_NOTE_MAX_CHARS,
    POST_MAX_CHARS,
    REPORT_DETAIL_MAX_CHARS,
    RateLimited,
    SocialError,
    clean_text,
    comment_like_key,
    kich_thuoc_trang,
    kiem_anh,
    kiem_han_muc,
    notification_key,
    object_key,
    parent_hop_le,
    post_like_key,
    report_key,
    story_follow_key,
    tron_bang_tin,
    user_follow_key,
    NGUOI_THEO_DOI_TOI_DA,
)

#: Doan xem truoc kem trong thong bao. Du de nhan ra bai nao, khong du de thay
#: thong bao lam nguoi ta khoi phai mo bai.
PREVIEW_CHARS = 80

#: Bao nhieu nguoi theo doi duoc bao khi co chuong moi, MOI lan xuat ban.
#:
#: Co tran vi day la mot vong lap ghi chay TRONG request xuat ban chuong. Mot
#: tac gia co nam nghin nguoi theo doi se lam request do treo. Khi con so nay
#: thanh mot han che that, cach dung la mot hang doi — khong phai mot con so to
#: hon.
FANOUT_TOI_DA = 500


class SocialService:
    """
    Theo doi, bai dang, thich, binh luan, thong bao, bao cao.

    Nhan `identity` (noi ho so song), `store` (noi moi bang song) va `storage`
    (kho doi tuong cho anh) — dung ba doi tuong ma cac route dang dung, nen
    khong co duong ghi nao thu hai.
    """

    def __init__(self, identity: Any, store: Any, storage: Any = None,
                 han_muc: Optional[Dict[str, HanMuc]] = None):
        self._identity = identity
        self._store = store
        self._storage = storage
        self._han_muc = dict(HAN_MUC_MAC_DINH)
        if han_muc:
            self._han_muc.update(han_muc)

    # ==================================================================== THEO DOI

    def follow_user(self, actor: Profile, target_id: str) -> Dict[str, Any]:
        """
        Theo doi mot nguoi.

        Tu theo doi minh bi tu choi ngay tai day. Khong phai vi no nguy hiem, ma
        vi no lam moi con so ve sau sai mot cach kho truy: so nguoi theo doi cua
        ai cung du mot, va bang tin cua ai cung co bai cua chinh ho.
        """
        if not target_id:
            raise SocialError("Thiếu người cần theo dõi.")
        if target_id == actor.user_id:
            raise SocialError("Bạn không thể theo dõi chính mình.")
        self._nguoi_phai_ton_tai(target_id)
        self._kiem_han_muc("follow", actor.user_id)

        khoa = user_follow_key(actor.user_id, target_id)
        moi = self._store.follow_user(UserFollow(
            follower_id=actor.user_id, target_id=target_id, follow_id=khoa))
        if moi:
            # CHI khi that su moi. Khong co co nay thi bam theo doi lan thu hai
            # se ban them mot thong bao nua.
            self._bao(target_id, NotificationKind.FOLLOW,
                      actor_id=actor.user_id, subject_id=actor.user_id,
                      subject_kind="user",
                      preview=self._ten(actor))
        return self._trang_thai_theo_doi_nguoi(actor.user_id, target_id)

    def unfollow_user(self, actor: Profile, target_id: str) -> Dict[str, Any]:
        self._store.unfollow_user(user_follow_key(actor.user_id, target_id))
        return self._trang_thai_theo_doi_nguoi(actor.user_id, target_id)

    def follow_story(self, actor: Profile, novel_id: str) -> Dict[str, Any]:
        """
        Theo doi mot truyen — de duoc bao khi co chuong moi.

        CHI theo doi duoc truyen DA XUAT BAN. Mot ban nhap la thu rieng cua tac
        gia, va cho theo doi no la mot cach do xem ai dang viet gi.
        """
        novel = self._truyen(novel_id)
        if novel.state is not PublishState.PUBLISHED:
            raise NotFoundError("Không tìm thấy truyện.")
        self._kiem_han_muc("follow", actor.user_id)
        khoa = story_follow_key(actor.user_id, novel_id)
        self._store.follow_story(StoryFollow(
            follower_id=actor.user_id, novel_id=novel_id, follow_id=khoa))
        return self._trang_thai_theo_doi_truyen(actor.user_id, novel_id)

    def unfollow_story(self, actor: Profile, novel_id: str) -> Dict[str, Any]:
        self._store.unfollow_story(story_follow_key(actor.user_id, novel_id))
        return self._trang_thai_theo_doi_truyen(actor.user_id, novel_id)

    def story_follow_state(self, novel_id: str,
                           viewer: Optional[Profile] = None) -> Dict[str, Any]:
        """
        Trang thai theo doi mot truyen, cho trang chi tiet truyen.

        Nhan nguoi xem TUY CHON: khach vang lai van thay so nguoi theo doi, chi
        `following` luon `false`. Hai duong di chung mot ham de con so hien ra
        khong the lech giua nguoi da dang nhap va nguoi chua.
        """
        if viewer is None:
            dem = self._store.story_follower_counts([novel_id])
            return {"following": False,
                    "follower_count": int(dem.get(novel_id, 0))}
        return self._trang_thai_theo_doi_truyen(viewer.user_id, novel_id)

    def _trang_thai_theo_doi_nguoi(self, viewer_id: str,
                                   target_id: str) -> Dict[str, Any]:
        dem = self._store.follower_counts([target_id])
        return {
            "following": self._store.is_following_user(
                user_follow_key(viewer_id, target_id)),
            "follower_count": int(dem.get(target_id, 0)),
        }

    def _trang_thai_theo_doi_truyen(self, viewer_id: str,
                                    novel_id: str) -> Dict[str, Any]:
        dem = self._store.story_follower_counts([novel_id])
        return {
            "following": self._store.is_following_story(
                story_follow_key(viewer_id, novel_id)),
            "follower_count": int(dem.get(novel_id, 0)),
        }

    # ==================================================================== BAI DANG

    def create_post(self, actor: Profile, *, text: str,
                    kind: str = "post", novel_id: str = "",
                    image: Optional[Dict[str, Any]] = None,
                    images: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Dang mot bai.

        `images` (V3, toi da BON) — moi phan tu `{"data": bytes, "mime": str,
        "width": int, "height": int}`, anh DA duoc xu ly. `image` (so it) giu
        lai cho tuong thich; co ca hai thi gop lam mot danh sach. Tang nay
        khong giai ma anh: doc kich thuoc that tu mot tep do nguoi la gui len
        can mot thu vien anh, va moi thu vien anh la mot be mat tan cong. Chung
        ta chi kiem MIME, so byte va tran so — nhung thu doc duoc ma khong phai
        phan tich noi dung tep.
        """
        loai = self._loai_bai(kind)
        bo_anh = list(images or [])
        if image:
            bo_anh.insert(0, image)
        noi_dung = clean_text(text, toi_da=POST_MAX_CHARS, ten="Nội dung bài",
                              bat_buoc=not bo_anh)
        truyen = None
        if loai is PostKind.STORY_UPDATE:
            if actor.author_status is not AuthorStatus.APPROVED:
                raise PermissionDenied(
                    "Chỉ tác giả đã duyệt mới đăng được cập nhật truyện.")
            truyen = self._truyen(novel_id)
            if truyen.owner_id != actor.user_id:
                raise PermissionDenied("Bạn không sở hữu truyện này.")
            if truyen.state is not PublishState.PUBLISHED:
                raise SocialError("Chỉ đăng cập nhật cho truyện đã xuất bản.")

        self._kiem_han_muc("post", actor.user_id)

        bai = Post(
            author_user_id=actor.user_id,
            text=noi_dung,
            kind=loai,
            novel_id=truyen.novel_id if truyen else "",
        )
        if bo_anh:
            self._gan_bo_anh(bai, bo_anh)
        self._store.create_post(bai)
        return self._mot_bai(bai, actor)

    def edit_post(self, actor: Profile, post_id: str, *,
                  text: str) -> Dict[str, Any]:
        bai = self._bai_cua_minh(actor, post_id)
        bai.text = clean_text(text, toi_da=POST_MAX_CHARS, ten="Nội dung bài",
                              bat_buoc=not bai.has_image)
        self._store.save_post(bai)
        return self._mot_bai(bai, actor)

    def delete_post(self, actor: Profile, post_id: str) -> None:
        """
        Chinh chu xoa bai cua minh — xoa THAT, ke ca anh trong kho.

        Khac han duong kiem duyet, cai do dat `state = REMOVED` va giu hang lai.
        Ly do khac nhau: mot nguoi xoa bai cua chinh ho dang thu hoi thu ho da
        noi, con mot quan tri go mot bai dang tao ra mot quyet dinh co the bi
        khieu nai — va mot quyet dinh khong con bang chung thi khong xem lai duoc.
        """
        bai = self._bai_cua_minh(actor, post_id)
        self._xoa_anh(bai)
        self._store.delete_post(bai.post_id)

    def _bai_cua_minh(self, actor: Profile, post_id: str) -> Post:
        """
        Lay bai VA kiem quyen so huu, trong mot buoc.

        Gop lai co chu y: hai buoc roi thi mot cho nao do se lam buoc dau ma
        quen buoc sau.
        """
        bai = self._store.get_post(post_id)
        if bai is None:
            raise NotFoundError("Không tìm thấy bài đăng.")
        if bai.author_user_id != actor.user_id:
            raise PermissionDenied("Bạn không sở hữu bài đăng này.")
        if bai.state is not ContentState.VISIBLE:
            raise PermissionDenied("Bài đăng này đã bị gỡ.")
        return bai

    def _gan_bo_anh(self, bai: Post, bo: List[Dict[str, Any]]) -> None:
        """
        Kiem va tai TOI DA BON anh len kho, roi ghi metadata vao bai.

        KIEM HET truoc khi tai cai dau tien: anh thu ba hong ma hai cai dau da
        len kho thi hoac phai don, hoac de rac. Kiem truoc thi that bai la that
        bai SACH — chua co gi de don.
        """
        if self._storage is None:
            raise SocialError("Máy chủ chưa cấu hình kho ảnh.")
        da_kiem = []
        for anh in bo:
            data = anh.get("data") or b""
            mime = str(anh.get("mime") or "")
            chinh_sach = kiem_anh("post", mime=mime, so_byte=len(data))
            da_kiem.append((data, mime, anh, chinh_sach))
        kiem_bo_anh("post", [{"so_byte": len(d)} for d, *_ in da_kiem])

        for i, (data, mime, anh, chinh_sach) in enumerate(da_kiem):
            duoi = mime.split("/")[-1] or "webp"
            # `anh-0.webp`, `anh-1.webp`… trong CUNG thu muc cua bai — xoa bai
            # la xoa mot tien to, khong phai di tim tung khoa.
            khoa = object_key("post", user_id=bai.author_user_id,
                              subject_id=bai.post_id, duoi=duoi)
            khoa = khoa.replace("anh.", f"anh-{i}.")
            self._storage.put(khoa, data, content_type=mime)
            bai.images.append({
                "key": khoa,
                "mime": mime,
                "bytes": len(data),
                "width": max(0, min(int(anh.get("width") or 0),
                                    chinh_sach.canh_toi_da)),
                "height": max(0, min(int(anh.get("height") or 0),
                                     chinh_sach.canh_toi_da)),
            })

    def _xoa_anh(self, bai: Post) -> None:
        """Xoa MOI anh cua bai trong kho, khong lam hong thao tac neu kho tu choi."""
        if self._storage is None:
            return
        for anh in bai.all_images():
            khoa = str(anh.get("key") or "")
            if not khoa:
                continue
            try:
                self._storage.delete(khoa)
            except Exception:
                # Mot anh mo coi ton vai tram KB; mot loi 500 khi nguoi dung
                # bam Xoa thi ho se bam lai, va lan sau hang da mat nen bai
                # khong bao gio xoa duoc nua. Uu tien ro rang.
                pass

    # =================================================================== LUOT THICH

    def like_post(self, actor: Profile, post_id: str) -> Dict[str, Any]:
        bai = self._bai_hien(post_id)
        khoa = post_like_key(actor.user_id, post_id)
        if self._store.like_post(PostLike(post_id=post_id,
                                          user_id=actor.user_id, like_id=khoa)):
            self._store.bump_post_counter(post_id, "like_count", 1)
            if bai.author_user_id != actor.user_id:
                self._bao(bai.author_user_id, NotificationKind.POST_LIKE,
                          actor_id=actor.user_id, subject_id=post_id,
                          subject_kind="post",
                          preview=_cat(bai.text))
        return self._trang_thai_thich(actor.user_id, post_id)

    def unlike_post(self, actor: Profile, post_id: str) -> Dict[str, Any]:
        khoa = post_like_key(actor.user_id, post_id)
        if self._store.unlike_post(khoa):
            self._store.bump_post_counter(post_id, "like_count", -1)
        return self._trang_thai_thich(actor.user_id, post_id)

    def _trang_thai_thich(self, viewer_id: str, post_id: str) -> Dict[str, Any]:
        bai = self._store.get_post(post_id)
        return {
            "liked": self._store.has_liked(post_like_key(viewer_id, post_id)),
            "like_count": int(bai.like_count) if bai else 0,
        }

    def recount_post(self, post_id: str) -> Dict[str, Any]:
        """
        Dung lai bo dem tu bang SU THAT.

        `like_count`/`comment_count` la ban tong hop cong don, va cong don co
        the mat mot don vi khi hai request trung nhau — xem
        `bump_post_counter`. Ham nay la duong sua, va no chay lai bao nhieu lan
        cung duoc.
        """
        bai = self._store.get_post(post_id)
        if bai is None:
            raise NotFoundError("Không tìm thấy bài đăng.")
        bai.like_count = self._store.count_post_likes(post_id)
        bai.comment_count = self._store.count_post_comments(post_id)
        self._store.save_post(bai)
        return {"like_count": bai.like_count, "comment_count": bai.comment_count}

    # ===================================================================== BINH LUAN

    def create_comment(self, actor: Profile, post_id: str, *, text: str,
                       parent_id: str = "") -> Dict[str, Any]:
        """
        Binh luan mot BAI DANG, hoac tra loi mot binh luan goc.

        DUNG mot cap tra loi — `parent_hop_le` tu choi tra loi mot tra loi ngay
        tai day thay vi am tham gan no vao dau do. Xem `social.REPLY_MAX_DEPTH`.
        """
        bai = self._bai_hien(post_id)
        noi_dung = clean_text(text, toi_da=COMMENT_MAX_CHARS, ten="Bình luận")
        self._kiem_han_muc("comment", actor.user_id)

        cha = self._cha_hop_le(post_id, parent_id)
        bl = Comment(post_id=post_id, author_user_id=actor.user_id,
                     text=noi_dung, parent_id=parent_id)
        self._store.create_comment(bl)
        self._store.bump_post_counter(post_id, "comment_count", 1)
        if cha is not None:
            self._store.bump_comment_counter(cha.comment_id, "reply_count", 1)

        # Thong bao: MOT nguoi nhan cho moi su kien, va khong bao gio la chinh
        # nguoi vua go. Tra loi bao cho chu binh luan goc; binh luan goc bao cho
        # chu bai. `subject_id` la BAI de bam vao thong bao mo dung trang.
        if cha is not None:
            if cha.author_user_id != actor.user_id:
                self._bao(cha.author_user_id, NotificationKind.COMMENT_REPLY,
                          actor_id=actor.user_id, subject_id=bl.comment_id,
                          subject_kind="comment", preview=_cat(noi_dung))
        elif bai.author_user_id != actor.user_id:
            self._bao(bai.author_user_id, NotificationKind.POST_COMMENT,
                      actor_id=actor.user_id, subject_id=bl.comment_id,
                      subject_kind="comment", preview=_cat(noi_dung))
        return self._mot_binh_luan(bl, actor)

    def _cha_hop_le(self, target_id: str,
                    parent_id: str) -> Optional[Comment]:
        """Binh luan cha, da kiem cung DICH va dung MOT cap."""
        if not parent_id:
            return None
        cha = self._store.get_comment(parent_id)
        if cha is None or cha.post_id != target_id:
            raise NotFoundError("Không tìm thấy bình luận cha.")
        parent_hop_le(parent_id, cha.parent_id)
        return cha

    # ======================================================== BINH LUAN CHUONG

    def _chuong_cong_khai(self, chapter_id: str):
        """
        Chuong + truyen, VA truyen phai DA XUAT BAN.

        Day la hang rao duy nhat giua binh luan cong khai va ban nhap rieng tu:
        chuong nhap khong co chuoi binh luan cong khai, va audio Studio (khong
        co trang chuong) thi khong bao gio toi duoc day. Tra 404 chu khong 403
        — nguoi la khong can biet ban nhap nay ton tai.
        """
        try:
            chuong = self._store.get_chapter(chapter_id)
            truyen = self._store.get_novel(chuong.novel_id)
        except NotFoundError:
            raise NotFoundError("Không tìm thấy chương.")
        if truyen.state is not PublishState.PUBLISHED:
            raise NotFoundError("Không tìm thấy chương.")
        return chuong, truyen

    def chapter_comments(self, chapter_id: str, *,
                         sort: str = "moi",
                         limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        Binh luan cua mot chuong, kem vai tra loi dau — y het trang bai dang,
        chi khac DICH va thu tu mac dinh (MOI NHAT truoc: mot chuong gom binh
        luan qua nhieu thang, nguoi vua nghe xong muon thay nguoi ta vua noi gi).
        """
        self._chuong_cong_khai(chapter_id)
        goc, tong = self._store.list_comments(
            chapter_id, parent_id="", newest_first=(sort != "cu"),
            limit=limit, offset=offset)
        tra_loi = self._store.replies_for([c.comment_id for c in goc])
        moi = list(goc) + [c for ds in tra_loi.values() for c in ds]
        the = self._the_nguoi([c.author_user_id for c in moi])
        return {
            "items": [
                {
                    **c.to_public_dict(),
                    "author": the.get(c.author_user_id),
                    "replies": [
                        {**r.to_public_dict(),
                         "author": the.get(r.author_user_id)}
                        for r in tra_loi.get(c.comment_id, [])
                    ],
                }
                for c in goc
            ],
            "total": tong,
            "limit": limit,
            "offset": offset,
            "sort": "cu" if sort == "cu" else "moi",
        }

    def create_chapter_comment(self, actor: Profile, chapter_id: str, *,
                               text: str, parent_id: str = "",
                               timestamp_ms: Optional[int] = None,
                               spoiler: bool = False) -> Dict[str, Any]:
        """
        Binh luan mot CHUONG — dich la `chapter_id`, KHONG phai file MP3.

        Tac gia tao lai audio thi `chapter_id` khong doi, nen chuoi binh luan
        song sot qua moi lan tao lai. Moc thoi gian duoc kiem theo thoi luong
        THAT cua track hien tai neu biet — xem `social.kiem_timestamp`.
        """
        chuong, truyen = self._chuong_cong_khai(chapter_id)
        noi_dung = clean_text(text, toi_da=COMMENT_MAX_CHARS, ten="Bình luận")
        self._kiem_han_muc("comment", actor.user_id)

        track = self._store.track_for_chapter(chapter_id)
        moc = kiem_timestamp(
            timestamp_ms,
            float(track.duration_seconds) if track is not None else None)

        cha = self._cha_hop_le(chapter_id, parent_id)
        bl = Comment(post_id=chapter_id, author_user_id=actor.user_id,
                     text=noi_dung, parent_id=parent_id,
                     target_kind="chapter", timestamp_ms=moc,
                     spoiler=bool(spoiler))
        self._store.create_comment(bl)
        if cha is not None:
            self._store.bump_comment_counter(cha.comment_id, "reply_count", 1)

        # Tra loi -> bao chu binh luan goc; binh luan goc -> bao TAC GIA truyen.
        # `subject_id` la CHUONG de thong bao mo dung trang doc. Khoa chong lap
        # theo (nguoi nhan, loai, nguoi gay, chuong, ngay): mot nguoi binh luan
        # hang chuc cau trong mot buoi nghe chi sinh MOT thong bao cho tac gia.
        if cha is not None:
            if cha.author_user_id != actor.user_id:
                self._bao(cha.author_user_id, NotificationKind.COMMENT_REPLY,
                          actor_id=actor.user_id, subject_id=chapter_id,
                          subject_kind="chapter", preview=_cat(noi_dung))
        elif truyen.owner_id != actor.user_id:
            self._bao(truyen.owner_id, NotificationKind.CHAPTER_COMMENT,
                      actor_id=actor.user_id, subject_id=chapter_id,
                      subject_kind="chapter",
                      preview=_cat(f"{chuong.title} — {noi_dung}"))
        return self._mot_binh_luan(bl, actor)

    def edit_comment(self, actor: Profile, comment_id: str, *,
                     text: str) -> Dict[str, Any]:
        bl = self._binh_luan_cua_minh(actor, comment_id)
        bl.text = clean_text(text, toi_da=COMMENT_MAX_CHARS, ten="Bình luận")
        self._store.save_comment(bl)
        return self._mot_binh_luan(bl, actor)

    def delete_comment(self, actor: Profile, comment_id: str) -> None:
        bl = self._binh_luan_cua_minh(actor, comment_id)
        self._store.delete_comment(comment_id)
        self._store.bump_post_counter(bl.post_id, "comment_count", -1)
        if bl.parent_id:
            self._store.bump_comment_counter(bl.parent_id, "reply_count", -1)

    def _binh_luan_cua_minh(self, actor: Profile, comment_id: str) -> Comment:
        bl = self._store.get_comment(comment_id)
        if bl is None:
            raise NotFoundError("Không tìm thấy bình luận.")
        if bl.author_user_id != actor.user_id:
            raise PermissionDenied("Bạn không sở hữu bình luận này.")
        if bl.state is not ContentState.VISIBLE:
            raise PermissionDenied("Bình luận này đã bị gỡ.")
        return bl

    def comments(self, post_id: str, *, viewer: Optional[Profile] = None,
                 limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        Binh luan GOC cua mot bai, kem vai tra loi dau cua tung cai.

        BA truy van cho ca trang, khong phu thuoc so binh luan: danh sach goc,
        mot luot lay tra loi cho tat ca (`replies_for`), mot luot lay ho so.
        """
        self._bai_hien(post_id)
        goc, tong = self._store.list_comments(
            post_id, parent_id="", limit=limit, offset=offset)
        tra_loi = self._store.replies_for([c.comment_id for c in goc])
        moi = list(goc) + [c for ds in tra_loi.values() for c in ds]
        the = self._the_nguoi([c.author_user_id for c in moi])
        return {
            "items": [
                {
                    **c.to_public_dict(),
                    "author": the.get(c.author_user_id),
                    "replies": [
                        {**r.to_public_dict(), "author": the.get(r.author_user_id)}
                        for r in tra_loi.get(c.comment_id, [])
                    ],
                }
                for c in goc
            ],
            "total": tong,
            "limit": limit,
            "offset": offset,
        }

    def replies(self, comment_id: str, *, limit: int = 20,
                offset: int = 0) -> Dict[str, Any]:
        """Toan bo tra loi cua MOT binh luan goc — duong "Xem thêm"."""
        cha = self._store.get_comment(comment_id)
        if cha is None:
            raise NotFoundError("Không tìm thấy bình luận.")
        ds, tong = self._store.list_comments(
            cha.post_id, parent_id=comment_id, limit=limit, offset=offset)
        the = self._the_nguoi([c.author_user_id for c in ds])
        return {
            "items": [{**c.to_public_dict(), "author": the.get(c.author_user_id)}
                      for c in ds],
            "total": tong, "limit": limit, "offset": offset,
        }

    # ====================================================================== BANG TIN

    def feed(self, viewer: Optional[Profile], *, limit: Optional[int] = None,
             offset: int = 0) -> Dict[str, Any]:
        """
        Bang tin cong dong.

        Bai cua nguoi minh theo doi len TRUOC; phan con lai cua trang duoc lap
        day bang bai kham pha. Nguoi chua theo doi ai thi thay toan bo la kham
        pha — khong phai mot trang trong, va do la ca quyet dinh: mot bang tin
        rong o lan dau vao la mot ly do de khong quay lai.

        KHONG co mo hinh xep hang. Xem `social.tron_bang_tin`.
        """
        so = kich_thuoc_trang(limit)
        theo_doi_ids: List[str] = []
        if viewer is not None:
            theo_doi_ids = self._store.following_user_ids(
                viewer.user_id, limit=NGUOI_THEO_DOI_TOI_DA)

        tu_theo_doi: List[Post] = []
        tong = 0
        if theo_doi_ids:
            tu_theo_doi, tong = self._store.list_posts(
                author_ids=theo_doi_ids, limit=so, offset=offset)

        # Chi hoi them bai kham pha khi trang con cho. Mot nguoi theo doi nhieu
        # se khong bao gio ton them mot truy van nao.
        kham_pha: List[Post] = []
        if len(tu_theo_doi) < so:
            kham_pha, tong_kp = self._store.list_posts(
                limit=so + len(tu_theo_doi), offset=offset if not theo_doi_ids else 0)
            if not theo_doi_ids:
                tong = tong_kp

        gop = tron_bang_tin(
            [{"post_id": p.post_id} for p in tu_theo_doi],
            [{"post_id": p.post_id} for p in kham_pha],
            so,
        )
        theo_id = {p.post_id: p for p in list(tu_theo_doi) + list(kham_pha)}
        bai = [theo_id[str(x["post_id"])] for x in gop if x["post_id"] in theo_id]
        return {
            "items": self._lam_giau_bai(bai, viewer, kem_xem_truoc=True),
            "total": tong,
            "limit": so,
            "offset": offset,
            "personalized": bool(theo_doi_ids),
            # Noi ro khi danh sach theo doi bi cat, thay vi im lang bo bot.
            "following_truncated": len(theo_doi_ids) >= NGUOI_THEO_DOI_TOI_DA,
        }

    def posts_by_user(self, author_id: str, *,
                      viewer: Optional[Profile] = None,
                      limit: Optional[int] = None,
                      offset: int = 0) -> Dict[str, Any]:
        """Tab "Bài viết" cua mot trang ca nhan."""
        so = kich_thuoc_trang(limit)
        ds, tong = self._store.list_posts(author_ids=[author_id], limit=so,
                                          offset=offset)
        return {"items": self._lam_giau_bai(ds, viewer, kem_xem_truoc=True),
                "total": tong, "limit": so, "offset": offset}

    def post_detail(self, post_id: str,
                    viewer: Optional[Profile] = None) -> Dict[str, Any]:
        bai = self._bai_hien(post_id)
        return self._lam_giau_bai([bai], viewer)[0]

    def search_posts(self, query: str, *, limit: int = 5,
                     viewer: Optional[Profile] = None) -> Dict[str, Any]:
        """Muc phu cua tim kiem toan cuc. Truyen va nguoi van la uu tien."""
        can = (query or "").strip()
        if len(can) < 2:
            return {"items": [], "total": 0}
        ds, tong = self._store.list_posts(query=can, limit=limit)
        return {"items": self._lam_giau_bai(ds, viewer), "total": tong}

    def _bai_hien(self, post_id: str) -> Post:
        bai = self._store.get_post(post_id)
        if bai is None or bai.state is not ContentState.VISIBLE:
            # Khong phan biet "khong ton tai" voi "da bi go": phan biet ra thi
            # thanh mot cach do xem noi dung nao da bi kiem duyet.
            raise NotFoundError("Không tìm thấy bài đăng.")
        return bai

    # ================================================================= LAM GIAU

    def _lam_giau_bai(self, bai: Sequence[Post],
                      viewer: Optional[Profile],
                      kem_xem_truoc: bool = False) -> List[Dict[str, Any]]:
        """
        Ghep tac gia, co da-thich, the truyen — va khi `kem_xem_truoc`, VAI
        binh luan moi nhat — vao MOT TRANG bai dang.

        Van la so truy van CO DINH cho ca trang, khong phu thuoc so bai: ho so,
        thong ke, co da-thich, tieu de truyen, va MOT luot binh luan xem truoc
        (`comments_for_posts`). Hoi tung bai mot la dung cai N+1 da lam khu
        quan tri mat 34 giay tren staging that.
        """
        if not bai:
            return []
        xem_truoc: Dict[str, List[Comment]] = {}
        if kem_xem_truoc:
            xem_truoc = self._store.comments_for_posts(
                [p.post_id for p in bai], moi_bai=2)
        nguoi_xt = [c.author_user_id for ds in xem_truoc.values() for c in ds]
        the = self._the_nguoi([p.author_user_id for p in bai] + nguoi_xt)
        da_thich = set()
        if viewer is not None:
            da_thich = self._store.liked_flags(
                viewer.user_id, [p.post_id for p in bai])
        truyen_ids = [p.novel_id for p in bai if p.novel_id]
        truyen = self._store.novels_by_ids(truyen_ids) if truyen_ids else {}

        ra: List[Dict[str, Any]] = []
        for p in bai:
            muc = p.to_public_dict()
            muc["author"] = the.get(p.author_user_id)
            muc["liked"] = p.post_id in da_thich
            muc["can_edit"] = viewer is not None and viewer.user_id == p.author_user_id
            if p.has_image and self._storage is not None:
                urls = [self._anh_url(str(a.get("key") or ""))
                        for a in p.all_images()]
                muc["image_urls"] = [u for u in urls if u]
                # Truong cu — client cu chi biet mot anh van hien duoc anh dau.
                muc["image_url"] = muc["image_urls"][0] if muc["image_urls"] else ""
            n = truyen.get(p.novel_id) if p.novel_id else None
            if n is not None:
                # `cover_key` GIU LAI cho client cu (chi them, khong doi ten —
                # cung nguyen tac voi `image_url` o tren); `cover_url` la truong
                # MOI, da ky, de the truyen trong bai dang co the hien bia that
                # thay vi chi mot lien ket chu.
                muc["novel"] = {"novel_id": n.novel_id, "title": n.title,
                                "cover_key": n.cover_key,
                                "cover_url": self._anh_url(n.cover_key or "") or None}
            if kem_xem_truoc:
                muc["comments_preview"] = [
                    {**c.to_public_dict(), "author": the.get(c.author_user_id)}
                    for c in xem_truoc.get(p.post_id, [])
                ]
            ra.append(muc)
        return ra

    def _anh_url(self, key: str) -> str:
        """
        URL da ky, ngan han. Khoa doi tuong tho khong bao gio ra khoi backend.

        `LocalStorageAdapter` (che do dev) khong ky URL va tra `None` — luc do
        tra chuoi rong de giao dien don gian la khong ve anh, thay vi ve mot
        the `<img src="None">`. Anh chi hien tren R2 that; da ghi trong bao cao.
        """
        if not key:
            return ""
        try:
            return self._storage.signed_url(key, expires_seconds=3600) or ""
        except Exception:
            return ""

    def _the_nguoi(self, user_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """
        The tac gia gon cho nhieu nguoi, HAI truy van (+ ky URL avatar CUC BO).

        Dung `public_author_card` — cung danh sach cho phep ma tim kiem va trang
        ca nhan dung. Mot danh sach cho phep, mot cho — MOI noi hien avatar
        (bai dang, binh luan, tra loi, thong bao, tim kiem, the tac gia) deu
        di qua ham nay nen chi can sua MOT cho.

        Ky URL avatar KHONG phai mot truy van them: `_anh_url` tinh chu ky
        cuc bo (HMAC/presign), khong goi mang — nen ky N avatar o day van la
        hai truy van kho du lieu, khong phai N+1.
        """
        ids = sorted({u for u in user_ids if u})
        if not ids:
            return {}
        ho_so = self._identity.profiles_by_ids(ids)
        thong_ke = self._store.stats_by_ids(ids)
        ra: Dict[str, Dict[str, Any]] = {}
        for uid in ids:
            p = ho_so.get(uid)
            if p is None:
                continue
            st = thong_ke.get(uid)
            the = public_author_card(p.to_dict(), {
                "qualified_listens": st.qualified_listens if st else 0,
                "published_novels": st.published_novels if st else 0,
            })
            the["avatar_url"] = self._anh_url(p.avatar_key) or None
            ra[uid] = the
        return ra

    def _mot_bai(self, bai: Post, viewer: Optional[Profile]) -> Dict[str, Any]:
        return self._lam_giau_bai([bai], viewer)[0]

    def _mot_binh_luan(self, bl: Comment,
                       viewer: Optional[Profile]) -> Dict[str, Any]:
        the = self._the_nguoi([bl.author_user_id])
        return {**bl.to_public_dict(), "author": the.get(bl.author_user_id),
                "replies": []}

    # ================================================================== HO SO

    def profile_social(self, profile: Profile,
                       viewer: Optional[Profile] = None) -> Dict[str, Any]:
        """Phan xa hoi cua mot trang ca nhan: so lieu + minh co dang theo doi."""
        uid = profile.user_id
        return {
            "follower_count": int(self._store.follower_counts([uid]).get(uid, 0)),
            "following_count": int(self._store.following_counts([uid]).get(uid, 0)),
            "post_count": int(self._store.post_counts([uid]).get(uid, 0)),
            "following": (
                viewer is not None and viewer.user_id != uid
                and self._store.is_following_user(
                    user_follow_key(viewer.user_id, uid))
            ),
            "is_self": viewer is not None and viewer.user_id == uid,
        }

    def account_summary(self, profile: Profile) -> Dict[str, Any]:
        """
        Tom tat cho `/account`.

        Tac gia DA DUYET co them hang, luot nghe hop le va so truyen. Nguoi
        thuong khong — hien mot o "Hạng: chưa có" cho nguoi chua nop don la mot
        loi moi vao mot he thong ho khong o trong.
        """
        uid = profile.user_id
        ra: Dict[str, Any] = {
            "follower_count": int(self._store.follower_counts([uid]).get(uid, 0)),
            "following_count": int(self._store.following_counts([uid]).get(uid, 0)),
            "post_count": int(self._store.post_counts([uid]).get(uid, 0)),
            "followed_stories": len(self._store.followed_story_ids(uid)),
            "unread_notifications": self._store.count_unread(uid),
        }
        if profile.author_status is AuthorStatus.APPROVED:
            st = self._store.get_stats(uid)
            ra["rank"] = rank_progress(st.qualified_listens)
            ra["qualified_listens"] = st.qualified_listens
            ra["published_novels"] = len(self._store.list_novels(
                owner_id=uid, published_only=True))
        return ra

    # ================================================================ THONG BAO

    def notifications(self, viewer: Profile, *, unread_only: bool = False,
                      limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        ds, tong = self._store.list_notifications(
            viewer.user_id, unread_only=unread_only, limit=limit, offset=offset)
        the = self._the_nguoi([n.actor_id for n in ds])
        return {
            "items": [{**n.to_public_dict(), "actor": the.get(n.actor_id)}
                      for n in ds],
            "total": tong,
            "unread": self._store.count_unread(viewer.user_id),
            "limit": limit, "offset": offset,
        }

    def unread_count(self, viewer: Profile) -> Dict[str, Any]:
        return {"unread": self._store.count_unread(viewer.user_id)}

    def mark_read(self, viewer: Profile, notification_id: str) -> Dict[str, Any]:
        self._store.mark_notification_read(viewer.user_id, notification_id)
        return self.unread_count(viewer)

    def mark_all_read(self, viewer: Profile) -> Dict[str, Any]:
        so = self._store.mark_all_read(viewer.user_id)
        return {"marked": so, "unread": self._store.count_unread(viewer.user_id)}

    def _bao(self, user_id: str, kind: NotificationKind, *, actor_id: str = "",
             subject_id: str = "", subject_kind: str = "",
             preview: str = "", now: Optional[datetime] = None) -> bool:
        """
        Sinh mot thong bao, chong lap bang khoa TAT DINH co go ngay.

        KHONG BAO GIO tu bao cho chinh nguoi gay ra — nguoi goi da loc, va o day
        loc lai mot lan nua: mot cho quen la mot nguoi nhan duoc thong bao ve
        chinh minh, va do la thu doc ra nhu mot loi.
        """
        if not user_id or user_id == actor_id:
            return False
        khoa = notification_key(user_id, kind.value, actor_id, subject_id,
                                now=now)
        return self._store.create_notification_once(Notification(
            user_id=user_id, kind=kind, actor_id=actor_id,
            subject_id=subject_id, subject_kind=subject_kind,
            preview=preview, notification_id=khoa,
        ))

    def notify_new_chapter(self, novel: Any, chapter: Any) -> int:
        """
        Bao cho nguoi theo doi truyen khi co chuong moi.

        Duoc goi tu duong XUAT BAN chuong. CO TRAN (`FANOUT_TOI_DA`) vi day la
        mot vong lap ghi chay trong chinh request do; khi tran nay thanh mot han
        che that thi cach dung la mot hang doi, khong phai mot con so to hon.

        Loi o day KHONG duoc lam hong viec xuat ban: chuong da len roi, va mot
        thong bao that lac la thu nho hon nhieu so voi mot lan xuat ban that bai.
        """
        try:
            nguoi = self._store.story_follower_ids(novel.novel_id,
                                                   limit=FANOUT_TOI_DA)
        except Exception:
            return 0
        dem = 0
        for uid in nguoi:
            if uid == novel.owner_id:
                continue
            try:
                if self._bao(uid, NotificationKind.STORY_CHAPTER,
                             actor_id=novel.owner_id, subject_id=novel.novel_id,
                             subject_kind="novel",
                             preview=_cat(f"{novel.title} — {chapter.title}")):
                    dem += 1
            except Exception:
                continue
        return dem

    def notify_author_decision(self, user_id: str, *, approved: bool,
                               actor_id: str = "", note: str = "") -> bool:
        """
        Bao ket qua duyet don. Duoc goi tu duong kiem duyet cua `CreatorService`.

        `actor_id` KHONG di vao thong bao: nguoi nop don khong can biet quan tri
        nao da bam, va cho ho biet la bien mot quyet dinh he thong thanh mot
        chuyen ca nhan.
        """
        kind = (NotificationKind.AUTHOR_APPROVED if approved
                else NotificationKind.AUTHOR_REJECTED)
        return self._bao(user_id, kind, actor_id="", subject_id=user_id,
                         subject_kind="user", preview=_cat(note))

    # ==================================================================== BAO CAO

    def report(self, actor: Profile, *, target_kind: str, target_id: str,
               reason: str, detail: str = "") -> Dict[str, Any]:
        """
        Bao cao mot bai hoac mot binh luan.

        BAO CAO KHONG BAO GIO TU GO NOI DUNG — no chi dua noi dung vao hang doi
        kiem duyet. Neu no tu go duoc, mot nhom nguoi phoi hop bam Bao cao se
        thanh mot cong cu xoa noi dung cua nguoi ho khong thich, va do la ket
        qua nguoc hoan toan voi muc dich cua nut do.
        """
        loai = (target_kind or "").strip().lower()
        if loai not in ("post", "comment"):
            raise SocialError("Loại nội dung báo cáo không hợp lệ.")
        try:
            ly_do = ReportReason(str(reason or "").strip().lower())
        except ValueError:
            raise SocialError("Lý do báo cáo không hợp lệ.")

        chu = self._chu_so_huu(loai, target_id)
        if chu == actor.user_id:
            raise SocialError("Bạn không cần báo cáo nội dung của chính mình.")
        self._kiem_han_muc("report", actor.user_id)

        bc = ContentReport(
            reporter_id=actor.user_id, target_kind=loai, target_id=target_id,
            target_owner_id=chu, reason=ly_do,
            detail=clean_text(detail, toi_da=REPORT_DETAIL_MAX_CHARS,
                              ten="Mô tả", bat_buoc=False),
            report_id=report_key(actor.user_id, loai, target_id),
        )
        moi = self._store.create_report_once(bc)
        return {"reported": True, "created": moi}

    def _chu_so_huu(self, target_kind: str, target_id: str) -> str:
        if target_kind == "post":
            return self._bai_hien(target_id).author_user_id
        bl = self._store.get_comment(target_id)
        if bl is None or bl.state is not ContentState.VISIBLE:
            raise NotFoundError("Không tìm thấy bình luận.")
        return bl.author_user_id

    # ============================================================ KIEM DUYET

    def admin_reports(self, *, status: str = "open", target_kind: str = "",
                      limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        """
        Hang doi bao cao cho khu quan tri, kem NOI DUNG bi bao cao.

        BA truy van cho ca trang: bao cao, noi dung, ho so. Doc noi dung cho
        tung hang la dung cai N+1 ma ban truoc cua khu quan tri mac phai.
        """
        tt = _trang_thai_bao_cao(status)
        ds, tong = self._store.list_reports(status=tt, target_kind=target_kind,
                                            limit=limit, offset=offset)
        bai_ids = [r.target_id for r in ds if r.target_kind == "post"]
        bl_ids = [r.target_id for r in ds if r.target_kind == "comment"]
        bai = self._store.posts_by_ids(bai_ids) if bai_ids else {}
        bl = self._store.comments_by_ids(bl_ids) if bl_ids else {}
        the = self._the_nguoi(
            [r.reporter_id for r in ds] + [r.target_owner_id for r in ds])

        muc: List[Dict[str, Any]] = []
        for r in ds:
            noi_dung: Optional[Dict[str, Any]] = None
            if r.target_kind == "post":
                p = bai.get(r.target_id)
                # Ban QUAN TRI: co ca `state` va truong kiem duyet. Do la ca
                # muc dich cua man hinh nay.
                noi_dung = p.to_dict() if p else None
            else:
                c = bl.get(r.target_id)
                noi_dung = c.to_dict() if c else None
            duong_nguon = ""
            if r.target_kind == "post":
                duong_nguon = f"/posts/{r.target_id}"
            elif noi_dung is not None:
                # Binh luan: nguon la BAI hoac CHUONG chua no.
                duong_nguon = (f"/chapters/{noi_dung.get('post_id')}"
                               if noi_dung.get("target_kind") == "chapter"
                               else f"/posts/{noi_dung.get('post_id')}")
            muc.append({
                **r.to_dict(),
                "content": noi_dung,
                "reporter": the.get(r.reporter_id),
                "target_owner": the.get(r.target_owner_id),
                "context_url": duong_nguon,
            })
        return {"items": muc, "total": tong, "limit": limit, "offset": offset}

    def resolve_report(self, admin: Profile, report_id: str, *,
                       dismiss: bool = False, note: str = "") -> Dict[str, Any]:
        """Dong mot bao cao. KHONG dong thoi go noi dung — do la thao tac rieng."""
        bc = self._store.get_report(report_id)
        if bc is None:
            raise NotFoundError("Không tìm thấy báo cáo.")
        bc.status = ReportStatus.DISMISSED if dismiss else ReportStatus.RESOLVED
        bc.resolution_note = clean_text(note, toi_da=MODERATION_NOTE_MAX_CHARS,
                                        ten="Ghi chú", bat_buoc=False)
        bc.resolved_by = admin.user_id
        self._store.save_report(bc)
        self._ghi_nhat_ky(
            "report_dismissed" if dismiss else "report_resolved",
            target_user_id=bc.target_owner_id, actor_id=admin.user_id,
            note=f"{bc.target_kind}:{bc.target_id} — {bc.resolution_note}")
        return bc.to_dict()

    def remove_post(self, admin: Profile, post_id: str, *,
                    reason: str = "") -> Dict[str, Any]:
        """
        Go mot bai. Hang VAN CON — xem `ContentState`.

        Tra ve ban quan tri (co `state`), khong phai ban cong khai: nguoi vua go
        can thay ket qua that cua thao tac vua roi.
        """
        return self._doi_trang_thai_bai(admin, post_id, ContentState.REMOVED,
                                        reason)

    def restore_post(self, admin: Profile, post_id: str) -> Dict[str, Any]:
        return self._doi_trang_thai_bai(admin, post_id, ContentState.VISIBLE, "")

    def _doi_trang_thai_bai(self, admin: Profile, post_id: str,
                            moi: ContentState, reason: str) -> Dict[str, Any]:
        bai = self._store.get_post(post_id)
        if bai is None:
            raise NotFoundError("Không tìm thấy bài đăng.")
        go = moi is ContentState.REMOVED
        bai.state = moi
        bai.removed_by = admin.user_id if go else ""
        bai.removed_reason = clean_text(
            reason, toi_da=MODERATION_NOTE_MAX_CHARS, ten="Lý do",
            bat_buoc=False) if go else ""
        self._store.save_post(bai)
        self._ghi_nhat_ky("post_removed" if go else "post_restored",
                          target_user_id=bai.author_user_id,
                          actor_id=admin.user_id,
                          note=f"{post_id} — {bai.removed_reason}")
        return bai.to_dict()

    def remove_comment(self, admin: Profile, comment_id: str, *,
                       reason: str = "") -> Dict[str, Any]:
        return self._doi_trang_thai_bl(admin, comment_id, ContentState.REMOVED,
                                       reason)

    def restore_comment(self, admin: Profile, comment_id: str) -> Dict[str, Any]:
        return self._doi_trang_thai_bl(admin, comment_id, ContentState.VISIBLE,
                                       "")

    def _doi_trang_thai_bl(self, admin: Profile, comment_id: str,
                           moi: ContentState, reason: str) -> Dict[str, Any]:
        bl = self._store.get_comment(comment_id)
        if bl is None:
            raise NotFoundError("Không tìm thấy bình luận.")
        go = moi is ContentState.REMOVED
        if bl.state is not moi:
            # So binh luan cua bai phai theo kip, neu khong mot bai se hien "3
            # bình luận" o duoi mot danh sach chi con hai.
            self._store.bump_post_counter(bl.post_id, "comment_count",
                                          -1 if go else 1)
        bl.state = moi
        bl.removed_by = admin.user_id if go else ""
        bl.removed_reason = clean_text(
            reason, toi_da=MODERATION_NOTE_MAX_CHARS, ten="Lý do",
            bat_buoc=False) if go else ""
        self._store.save_comment(bl)
        self._ghi_nhat_ky("comment_removed" if go else "comment_restored",
                          target_user_id=bl.author_user_id,
                          actor_id=admin.user_id,
                          note=f"{comment_id} — {bl.removed_reason}")
        return bl.to_dict()

    def admin_posts(self, *, query: str = "", include_removed: bool = True,
                    limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        ds, tong = self._store.list_posts(query=query,
                                          include_removed=include_removed,
                                          limit=limit, offset=offset)
        the = self._the_nguoi([p.author_user_id for p in ds])
        bao_cao = self._store.reports_for_targets([p.post_id for p in ds])
        return {
            "items": [{**p.to_dict(), "author": the.get(p.author_user_id),
                       "open_reports": int(bao_cao.get(p.post_id, 0))}
                      for p in ds],
            "total": tong, "limit": limit, "offset": offset,
        }

    def admin_comments(self, post_id: str, *, limit: int = 50,
                       offset: int = 0) -> Dict[str, Any]:
        ds, tong = self._store.list_comments(post_id, limit=limit,
                                             offset=offset)
        the = self._the_nguoi([c.author_user_id for c in ds])
        bao_cao = self._store.reports_for_targets([c.comment_id for c in ds])
        return {
            "items": [{**c.to_dict(), "author": the.get(c.author_user_id),
                       "open_reports": int(bao_cao.get(c.comment_id, 0))}
                      for c in ds],
            "total": tong, "limit": limit, "offset": offset,
        }

    def admin_browse_comments(self, *, target_kind: str = "",
                              limit: int = 25,
                              offset: int = 0) -> Dict[str, Any]:
        """
        Duyet binh luan TOAN HE THONG cho khu quan tri, tach duoc hai loai:
        binh luan bai dang (`target_kind=""`) va binh luan chuong ("chapter").

        Hai loai dan toi hai noi khac nhau, nen nguoi kiem duyet can mot duong
        toi NGUON: bai thi `/posts/{id}`, chuong thi `/chapters/{id}` — tra
        `context_url` san thay vi bat giao dien tu suy.
        """
        ds, tong = self._store.list_comments_all(
            target_kind=target_kind, limit=limit, offset=offset)
        the = self._the_nguoi([c.author_user_id for c in ds])
        bao_cao = self._store.reports_for_targets([c.comment_id for c in ds])
        return {
            "items": [{
                **c.to_dict(),
                "author": the.get(c.author_user_id),
                "open_reports": int(bao_cao.get(c.comment_id, 0)),
                "context_url": (f"/chapters/{c.post_id}"
                                if c.target_kind == "chapter"
                                else f"/posts/{c.post_id}"),
            } for c in ds],
            "total": tong, "limit": limit, "offset": offset,
        }

    def social_overview(self) -> Dict[str, Any]:
        """So lieu xa hoi cho trang tong quan quan tri. Bon phep dem."""
        return {
            "open_reports": self._store.count_reports(ReportStatus.OPEN),
            "total_reports": self._store.count_reports(),
            "total_posts": self._store.list_posts(include_removed=True,
                                                  limit=1)[1],
            "removed_posts": (self._store.list_posts(include_removed=True,
                                                     limit=1)[1]
                              - self._store.list_posts(limit=1)[1]),
        }

    def _ghi_nhat_ky(self, action: str, *, target_user_id: str, actor_id: str,
                     note: str = "") -> None:
        """
        Moi thao tac kiem duyet xa hoi vao CUNG mot nhat ky voi kiem duyet tac
        gia.

        Mot nhat ky, khong phai hai: nguoi doc lai mot vu viec muon thay MOI thu
        da xay ra voi mot nguoi, theo thu tu — chu khong phai ghep hai danh sach
        o hai man hinh.
        """
        self._store.record_event(ModerationEvent(
            action=action, target_user_id=target_user_id, actor_id=actor_id,
            note=note[:MODERATION_NOTE_MAX_CHARS]))

    # ==================================================================== HA TANG

    def _kiem_han_muc(self, ten: str, user_id: str,
                      now: Optional[datetime] = None) -> None:
        """Dem tren chinh bang du lieu — xem ghi chu dau tep ve vi sao."""
        muc = self._han_muc.get(ten)
        if muc is None:
            return
        moc = muc.moc_bat_dau(now or datetime.now(timezone.utc))
        dem_ham = {
            "post": lambda: self._store.count_posts_since(user_id, moc),
            "comment": lambda: self._store.count_comments_since(user_id, moc),
            "follow": lambda: self._store.count_follows_since(user_id, moc),
            "report": lambda: self._store.count_reports_since(user_id, moc),
        }.get(ten)
        if dem_ham is None:
            return
        kiem_han_muc(ten, dem_ham(), muc)

    def _nguoi_phai_ton_tai(self, user_id: str) -> Profile:
        ho_so = self._identity.profiles_by_ids([user_id]).get(user_id)
        if ho_so is None:
            raise NotFoundError("Không tìm thấy người dùng.")
        return ho_so

    def _truyen(self, novel_id: str) -> Any:
        if not novel_id:
            raise SocialError("Thiếu truyện.")
        try:
            return self._store.get_novel(novel_id)
        except NotFoundError:
            raise NotFoundError("Không tìm thấy truyện.")

    @staticmethod
    def _loai_bai(kind: str) -> PostKind:
        try:
            return PostKind(str(kind or "post").strip().lower())
        except ValueError:
            raise SocialError("Loại bài đăng không hợp lệ.")

    @staticmethod
    def _ten(profile: Profile) -> str:
        return profile.display_name or profile.username or ""


def _cat(text: str, toi_da: int = PREVIEW_CHARS) -> str:
    """Cat mot doan xem truoc, khong cat giua mot tu neu tranh duoc."""
    sach = " ".join(str(text or "").split())
    if len(sach) <= toi_da:
        return sach
    cat = sach[:toi_da].rsplit(" ", 1)[0] or sach[:toi_da]
    return cat + "…"


def _trang_thai_bao_cao(raw: str) -> Optional[ReportStatus]:
    """`""` hoac `all` = moi trang thai."""
    can = (raw or "").strip().lower()
    if not can or can == "all":
        return None
    try:
        return ReportStatus(can)
    except ValueError:
        raise SocialError("Trạng thái báo cáo không hợp lệ.")
