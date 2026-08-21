#!/usr/bin/env python3
"""
Tao database / collections / attributes / indexes cho Fanfic Audio Studio.

AN TOAN KHI CHAY LAI: moi buoc deu bo qua neu doi tuong da ton tai (409).

Script nay KHONG chua secret. No doc cau hinh tu bien moi truong:
    APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, APPWRITE_DATABASE_ID

Chay:
    .venv\\Scripts\\python.exe -m scripts.setup_appwrite
    .venv\\Scripts\\python.exe -m scripts.setup_appwrite --dry-run
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

import httpx

from server.config import load_settings
from server.secret_redaction import thong_diep_loi_an_toan

TIMEOUT = 30.0

# Console Windows mac dinh la cp1252, khong ma hoa duoc tieng Viet co dau ->
# script chet bang UnicodeEncodeError truoc khi lam duoc gi. Ep UTF-8 de lenh
# trong tai lieu chay duoc ngay, khong bat nguoi van hanh dat PYTHONIOENCODING.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: (key, kieu, bat_buoc, kich_thuoc/tuy_chon)
SCHEMA: Dict[str, Dict[str, Any]] = {
    "profiles": {
        "name": "Profiles",
        "attributes": [
            ("user_id", "string", True, 64),
            ("email", "email", True, None),
            ("display_name", "string", False, 120),
            ("tier", "enum", True, ["free", "listener_pro", "creator_pro", "ultra"]),
            ("listened_minutes", "integer", False, None),
            ("tts_characters_used", "integer", False, None),
            ("created_at", "datetime", True, None),
            # --- danh tinh CONG KHAI + moderation tac gia (V2) ----------------
            # Ba thuoc tinh nay CHUA duoc ap len production. Chung o day de
            # `--dry-run` in ra dung ke hoach, va de mot lan chay script sau nay
            # tao chung. Ma nguon KHONG phu thuoc vao viec chung da ton tai:
            # `AppwriteIdentityAdapter` loc theo thuoc tinh that su co, nen
            # trien khai code truoc schema chi lam mat tinh nang, khong lam vo
            # duong dang ky.
            ("username", "string", False, 24),
            ("bio", "string", False, 400),
            ("author_status", "enum", False,
             ["none", "pending", "approved", "rejected", "suspended"]),
            # --- V4: anh dai dien (Phase 6) ------------------------------------
            # Khoa doi tuong R2, KHONG PHAI url — cung quy uoc voi
            # `novels.cover_key`. 512 la muc rong rai giong het cover_key, du
            # avatar_key thuc te ngan hon nhieu (khong co subject_id).
            ("avatar_key", "string", False, 512),
            # --- V4 visual completion: "tiep tuc doc/nghe" (Phan B) -----------
            # CON TRO DUY NHAT toi noi dang do dang, khong phai lich su — xem
            # `server/domain.py::Profile`. Tat ca deu KHONG bat buoc: thieu
            # schema nay chi lam module "Tiep tuc..." AN o trang chu, khong
            # lam vo dang ky/cap nhat ho so (cung co che voi ba truong V2 o
            # tren, xem `AppwriteIdentityAdapter._writable_profile`).
            ("last_read_novel_id", "string", False, 64),
            ("last_read_chapter_id", "string", False, 64),
            ("last_read_at", "datetime", False, None),
            ("last_listen_novel_id", "string", False, 64),
            ("last_listen_chapter_id", "string", False, 64),
            ("last_listen_position_seconds", "double", False, None),
            ("last_listen_at", "datetime", False, None),
            # --- V6 (overnight Phase 5): "tiep tuc xem" Animation --------------
            # CUNG co che dong-thieu-thi-bo-qua voi ba nhom truong tren — xem
            # `server/appwrite_adapter.py::_PROFILE_V2_FIELDS`.
            ("last_watch_series_id", "string", False, 64),
            ("last_watch_episode_id", "string", False, 64),
            ("last_watch_position_seconds", "double", False, None),
            ("last_watch_duration_seconds", "double", False, None),
            ("last_watch_at", "datetime", False, None),
        ],
        "indexes": [
            ("email_unique", "unique", ["email"]),
            # Rang buoc THAT cho tinh duy nhat cua username. Phep kiem o tang
            # service la de tra ve thong bao doc duoc; cai chan duoc mot cuoc dua
            # giua hai request la index nay.
            ("username_unique", "unique", ["username"]),
            # Phase 13 (overnight hardening): `profiles_by_ids` (appwrite_adapter.py)
            # loc `equal("user_id", ...)` hang loat cho khu quan tri (vd
            # /api/admin/author-applications) — truoc day khong co chi muc nao
            # phu chi muc nay, dan den quet toan bang moi lan goi.
            ("user_idx", "key", ["user_id"]),
        ],
    },
    # --- V2: tac gia ---------------------------------------------------------
    # CHUA ap len production. Xem `docs/AUTHOR_RANK.md` muc "Ke hoach migration".
    "author_applications": {
        "name": "Author applications",
        "attributes": [
            ("application_id", "string", True, 64),
            # MOT don moi nguoi dung — nop lai thi ghi de. `rowId` la `user_id`.
            ("user_id", "string", True, 64),
            ("pen_name", "string", True, 60),
            ("bio", "string", False, 400),
            ("genres", "string", False, 40),        # mang
            ("intro", "string", False, 1000),
            ("accepted_rules", "boolean", False, None),
            ("status", "enum", True,
             ["none", "pending", "approved", "rejected", "suspended"]),
            ("reviewer_note", "string", False, 1000),
            ("attempts", "integer", False, None),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
            ("decided_at", "datetime", False, None),
        ],
        "indexes": [
            ("user_unique", "unique", ["user_id"]),
            # Cho trang quan tri: liet ke don dang cho, cu lau nhat truoc.
            ("status_created_idx", "key", ["status", "created_at"]),
        ],
    },
    "author_stats": {
        "name": "Author stats",
        "attributes": [
            ("user_id", "string", True, 64),
            ("qualified_listens", "integer", False, None),
            ("published_novels", "integer", False, None),
            ("updated_at", "datetime", True, None),
        ],
        # `rowId` la `user_id`, nen mot ban tong hop moi tac gia.
        "indexes": [("user_unique", "unique", ["user_id"])],
    },
    "listen_credits": {
        "name": "Listen credits",
        "attributes": [
            ("credit_id", "string", True, 64),
            ("listener_id", "string", True, 64),
            ("author_id", "string", True, 64),
            ("chapter_id", "string", True, 64),
            ("day_bucket", "integer", False, None),
            ("listened_seconds", "double", False, None),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            # Chong farm: `rowId` la khoa TAT DINH tu (nguoi nghe, chuong, ngay
            # UTC) — xem `creator.credit_key`. Chinh tinh duy nhat cua rowId la
            # co che chan dua, y nhu `job_locks`.
            ("listener_chapter_idx", "key", ["listener_id", "chapter_id"]),
            # Dem lai de doi soat `author_stats` khi nghi no lech.
            ("author_idx", "key", ["author_id"]),
        ],
    },
    "moderation_events": {
        "name": "Moderation events",
        # CHI THEM. Khong co duong sua hay xoa o bat ky tang nao — mot nhat ky
        # sua duoc la mot nhat ky khong dung de lam gi.
        #
        # MO RONG (Admin Control Center V2, feature/admin-trusted-video-v2):
        # day van la MOT nhat ky duy nhat cho MOI hanh dong quan tri — tiep
        # tuc dung tinh than "mot nhat ky, khong phai hai" da co tu truoc, chi
        # mo rong tu vựng `action` va them bon truong ngu canh
        # (actor_role/target_type/target_id/metadata). Cac gia tri
        # user_*/content_*/trusted_source_*/youtube_mapping_*/auto_* CHUA co
        # route nao ghi (se den trong cac giai doan sau cua nhanh nay) — them
        # truoc de tranh phai chay lai migration enum nhieu lan.
        "attributes": [
            ("event_id", "string", True, 64),
            ("action", "enum", True,
             ["author_approved", "author_rejected", "author_suspended",
              "author_restored",
              # Kiem duyet xa hoi vao CUNG mot nhat ky. Mot nhat ky, khong phai
              # hai: nguoi doc lai mot vu viec muon thay MOI thu da xay ra voi
              # mot nguoi theo thu tu, chu khong phai ghep hai danh sach.
              "post_removed", "post_restored",
              "comment_removed", "comment_restored",
              "report_resolved", "report_dismissed",
              # Quan ly nguoi dung (A2/A3, Admin Control Center V2).
              "user_suspend", "user_unsuspend", "user_session_terminate",
              "user_role_change", "user_delete",
              # Kiem duyet noi dung ngoai pham vi bai dang/binh luan (A4).
              "content_unpublish", "content_restore",
              # Nguon tin cay YouTube va anh xa series (Phan B).
              "trusted_source_add", "trusted_source_disable",
              "trusted_source_enable", "youtube_mapping_create",
              "youtube_mapping_update",
              # Hang doi nhap tu dong (Phan B4-B6).
              "auto_import_approve", "auto_import_reject",
              "auto_publish_toggle",
              # Phase 5 (Trusted Video Sources) — MO RONG them cac hanh dong
              # THAT SU dung (khac ten voi bon dong tren, von la du doan tu
              # Phase 1 truoc khi Phase 5 duoc dac ta chi tiet). KHONG xoa
              # bon gia tri cu — enum chi duoc MO RONG, khong thu hep.
              "trusted_source_update", "trusted_source_remove",
              "youtube_mapping_remove",
              "video_scan_start", "video_import", "video_import_publish",
              "video_reject", "video_ignore",
              # Phase 6 (YouTube WebSub + pipeline tu dong) — dang ky/gia
              # han/thong bao qua PubSubHubbub, va ket qua pipeline tu dong
              # (khac voi "video_import"/"video_reject" thu cong o tren).
              "websub_subscribe", "websub_unsubscribe", "websub_renew",
              "websub_notification", "websub_failure",
              "auto_video_discover", "auto_video_import", "auto_video_publish",
              "reconciliation_run"]),
            ("target_user_id", "string", True, 64),
            # Rong = he thong (vd migration grandfather), khong phai mot nguoi.
            ("actor_id", "string", False, 64),
            # Vai tro cua actor TAI THOI DIEM hanh dong — "owner"/"admin"/
            # "moderator". Ghi lai vi vai tro co the doi sau (bien moi truong).
            ("actor_role", "string", False, 16),
            # Loai doi tuong khi KHONG PHAI la user (vd "novel",
            # "animation_series", "trusted_source"). Rong = doi tuong la user.
            ("target_type", "string", False, 32),
            ("target_id", "string", False, 64),
            ("note", "string", False, 1000),
            # JSON, AN TOAN — khong bao gio chua API key/OAuth/BYOP token/
            # cookie/session secret/khoa ma hoa. Xem docstring
            # `ModerationEvent.metadata` o server/domain.py.
            ("metadata", "string", False, 2000),
            # `datetime` cua Appwrite giu duoc micro giay — can dung the: hai
            # thao tac trong cung mot giay phai doc ra dung thu tu.
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("target_created_idx", "key", ["target_user_id", "created_at"]),
            ("created_idx", "key", ["created_at"]),
            # Loc nhat ky theo LOAI doi tuong (vd chi xem hanh dong len
            # trusted_source) — dung cho /admin/audit-log (A5).
            ("target_type_created_idx", "key", ["target_type", "created_at"]),
            # Phase 13 (overnight hardening): `list_events(target_id=...)` va
            # `list_events(action=...)` (appwrite_store.py) loc THEM cho
            # /admin/audit-log — khong duoc chi muc nao o tren phu (chi muc
            # hien co deu lay target_user_id/target_type lam cot dau). Nhat ky
            # nay CHI THEM va lon dan vo han, nen thieu chi muc o day la mot
            # phep quet toan bang ngay cang cham theo thoi gian.
            ("target_id_idx", "key", ["target_id"]),
            ("action_idx", "key", ["action"]),
        ],
    },
    # ========================================================== TANG XA HOI
    #
    # BAY bang. Moi chi muc duoi day tuong ung voi mot truy van CO THAT trong
    # `server/appwrite_social.py` — khong co chi muc nao dat "cho chac". Mot chi
    # muc thua ton dung luong va lam moi lan ghi cham hon, va no khong bao gio
    # duoc go ra vi khong ai biet no dung cho gi.
    #
    # KHONG bang nao co chi muc `unique`: tinh duy nhat o day do `rowId` TAT
    # DINH cuong che (xem `server/social.py`). Mot chi muc unique nua se la mot
    # rang buoc thu hai noi cung mot dieu — va hai nguon su that cho cung mot
    # rang buoc la mot cho de lech.
    "user_follows": {
        "name": "User follows",
        "attributes": [
            ("follow_id", "string", True, 64),
            ("follower_id", "string", True, 64),
            ("target_id", "string", True, 64),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            # `following_user_ids` — ai toi dang theo doi, moi nhat truoc.
            ("follower_created_idx", "key", ["follower_id", "created_at"]),
            # `follower_ids` / `follower_counts` — ai theo doi nguoi nay.
            ("target_created_idx", "key", ["target_id", "created_at"]),
            # `following_flags` — mot truy van cho ca trang.
            ("pair_idx", "key", ["follower_id", "target_id"]),
        ],
    },
    "story_follows": {
        "name": "Story follows",
        # BANG RIENG voi `user_follows`, khong gop bang mot cot `kind`. "Ai theo
        # doi truyen nay" va "ai theo doi nguoi nay" la hai cau hoi chay o hai
        # cho khac nhau; gop lai thi moi truy van phai mang them mot dieu kien
        # loc chi de bo di mot nua bang.
        "attributes": [
            ("follow_id", "string", True, 64),
            ("follower_id", "string", True, 64),
            ("novel_id", "string", True, 64),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("follower_created_idx", "key", ["follower_id", "created_at"]),
            # Phat thong bao khi co chuong moi.
            ("novel_created_idx", "key", ["novel_id", "created_at"]),
            ("pair_idx", "key", ["follower_id", "novel_id"]),
        ],
    },
    "posts": {
        "name": "Posts",
        "attributes": [
            ("post_id", "string", True, 64),
            ("author_user_id", "string", True, 64),
            ("kind", "enum", True, ["post", "story_update"]),
            # Chi co nghia voi `story_update`.
            ("novel_id", "string", False, 64),
            ("text", "string", False, 2000),
            # Khoa doi tuong trong R2, KHONG phai binary. Xem `social.object_key`.
            ("image_key", "string", False, 512),
            ("image_mime", "string", False, 60),
            ("image_width", "integer", False, None),
            ("image_height", "integer", False, None),
            ("image_bytes", "integer", False, None),
            # V3: toi da BON anh, luu MOT cot JSON — them mot bang con chi de
            # dem bon hang la them mot vong mang cho moi bai tren bang tin.
            # 6000 ky tu du cho 4 muc metadata day du (moi muc ~120 ky tu).
            ("images_json", "string", False, 6000),
            # `removed` la kiem duyet, KHONG phai xoa: hang o lai de mot quyet
            # dinh bi khieu nai con xem lai duoc. Xem `domain.ContentState`.
            ("state", "enum", True, ["visible", "removed"]),
            # Ban TONG HOP, dem lai duoc tu `post_likes`/`comments` — xem
            # `SocialService.recount_post`.
            ("like_count", "integer", False, None),
            ("comment_count", "integer", False, None),
            ("removed_by", "string", False, 64),
            ("removed_reason", "string", False, 1000),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            # Bang tin "theo doi": `author_user_id IN (...)` + moi nhat truoc.
            ("author_created_idx", "key", ["author_user_id", "created_at"]),
            # Bang tin kham pha: loc `state` + moi nhat truoc.
            ("state_created_idx", "key", ["state", "created_at"]),
            ("novel_idx", "key", ["novel_id"]),
            # Phase 13 (overnight hardening): `posts_by_ids` (appwrite_social.py)
            # loc `equal("post_id", ...)` hang loat — `post_id` LA `documentId`
            # (xem `create_post`), nen ve nguyen tac co the doi sang loc `$id`
            # nhu `get_series_by_ids`; cho toi khi doi, chi muc nay tranh quet
            # toan bang.
            ("post_id_idx", "key", ["post_id"]),
        ],
    },
    "post_likes": {
        "name": "Post likes",
        # `rowId` = khoa tat dinh tu (nguoi, bai) — xem `social.post_like_key`.
        # Do la co che chan hai luot thich cua cung mot nguoi, va no manh hon
        # moi phep doc-roi-kiem-tra: request thu hai va vao 409 cua Appwrite.
        "attributes": [
            ("like_id", "string", True, 64),
            ("post_id", "string", True, 64),
            ("user_id", "string", True, 64),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            # `count_post_likes` — dem lai tu bang su that.
            ("post_idx", "key", ["post_id"]),
            # `liked_flags` — mot truy van cho ca trang bang tin.
            ("user_post_idx", "key", ["user_id", "post_id"]),
        ],
    },
    "comments": {
        "name": "Comments",
        "attributes": [
            ("comment_id", "string", True, 64),
            ("post_id", "string", True, 64),
            ("author_user_id", "string", True, 64),
            # Rong = binh luan goc. DUNG mot cap tra loi — xem
            # `social.REPLY_MAX_DEPTH` de biet vi sao khong phai mot cay.
            ("parent_id", "string", False, 64),
            # V3: binh luan chuong/audio. `""` (hoac NULL o hang cu) = binh
            # luan bai dang; "chapter" = binh luan chuong. String chu khong
            # enum: enum Appwrite khong nhan chuoi rong lam gia tri.
            ("target_kind", "string", False, 20),
            # Moc audio dinh kem, mili giay. NULL = khong dinh kem — 0 la mot
            # moc HOP LE (dau chuong) nen khong dung 0 lam "khong co".
            ("timestamp_ms", "integer", False, None),
            ("spoiler", "boolean", False, None),
            ("text", "string", False, 1000),
            ("state", "enum", True, ["visible", "removed"]),
            ("reply_count", "integer", False, None),
            ("removed_by", "string", False, 64),
            ("removed_reason", "string", False, 1000),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            # Binh luan cua mot bai, cu nhat truoc.
            ("post_created_idx", "key", ["post_id", "created_at"]),
            # `replies_for` — tra loi cua NHIEU binh luan goc, mot truy van.
            ("parent_created_idx", "key", ["parent_id", "created_at"]),
            # Han muc chong spam: dem binh luan cua mot nguoi trong mot gio.
            ("author_created_idx", "key", ["author_user_id", "created_at"]),
            # Khu quan tri duyet theo LOAI, moi nhat truoc —
            # `list_comments_all(target_kind=...)`.
            ("kind_created_idx", "key", ["target_kind", "created_at"]),
            # Phase 13 (overnight hardening): `comments_by_ids` (appwrite_social.py)
            # loc `equal("comment_id", ...)` hang loat — cung tinh huong voi
            # `post_id_idx` o `posts` phia tren.
            ("comment_id_idx", "key", ["comment_id"]),
        ],
    },
    "notifications": {
        "name": "Notifications",
        # `rowId` = khoa tat dinh CO GO NGAY — xem `social.notification_key`.
        # Chinh tinh duy nhat cua no la toan bo co che chong lap: cung mot nguoi
        # lam cung mot viec voi cung mot doi tuong trong mot ngay chi sinh MOT
        # thong bao. Khong co bo dem nao ca.
        "attributes": [
            ("notification_id", "string", True, 64),
            # NGUOI NHAN.
            ("user_id", "string", True, 64),
            ("kind", "enum", True,
             ["follow", "post_like", "post_comment", "comment_reply",
              "story_chapter",
              # V3: co nguoi binh luan vao mot CHUONG cua minh.
              "chapter_comment",
              "author_approved", "author_rejected",
              # V6 (overnight Phase 5): co nguoi binh luan vao mot TAP animation.
              "episode_comment"]),
            # Rong = he thong (vd don duoc duyet), khong phai mot nguoi.
            ("actor_id", "string", False, 64),
            ("subject_id", "string", False, 64),
            ("subject_kind", "string", False, 20),
            ("preview", "string", False, 200),
            ("read", "boolean", False, None),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("user_created_idx", "key", ["user_id", "created_at"]),
            # Con so tren cai chuong — chay o MOI trang, nen phai re.
            ("user_read_idx", "key", ["user_id", "read"]),
        ],
    },
    "content_reports": {
        "name": "Content reports",
        # Hang duoc tao KHONG cap quyen doc cho client nao (`_create_kin`): no
        # chua `resolution_note` — ghi chu noi bo cua quan tri.
        "attributes": [
            ("report_id", "string", True, 64),
            ("reporter_id", "string", True, 64),
            ("target_kind", "enum", True, ["post", "comment"]),
            ("target_id", "string", True, 64),
            # Chep lai luc bao cao de khu quan tri khong phai doc them mot bang
            # nua cho moi hang.
            ("target_owner_id", "string", False, 64),
            ("reason", "enum", True,
             ["spam", "harassment", "inappropriate", "copyright", "other"]),
            ("detail", "string", False, 500),
            ("status", "enum", True, ["open", "resolved", "dismissed"]),
            ("resolution_note", "string", False, 1000),
            ("resolved_by", "string", False, 64),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            # Hang doi kiem duyet: cu nhat truoc, khong ai bi bo quen.
            ("status_created_idx", "key", ["status", "created_at"]),
            # `reports_for_targets` — so bao cao con mo cua ca mot trang.
            ("target_status_idx", "key", ["target_id", "status"]),
            ("reporter_created_idx", "key", ["reporter_id", "created_at"]),
            # Phase 13 (overnight hardening): `list_reports(target_kind=...)`
            # co the loc CHI theo target_kind (khong kem status) — khong chi
            # muc nao o tren co target_kind lam cot dau.
            ("target_kind_idx", "key", ["target_kind"]),
        ],
    },
    "novels": {
        "name": "Novels",
        "attributes": [
            ("novel_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            ("description", "string", False, 2000),
            ("cover_key", "string", False, 512),
            ("state", "enum", True, ["draft", "published", "archived"]),
            ("tags", "string", False, 64),          # mang
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("owner_idx", "key", ["owner_id"]),
            ("state_idx", "key", ["state"]),
            ("state_created_idx", "key", ["state", "created_at"]),
            # Phase 13 (overnight hardening): `novels_by_ids` (appwrite_store.py)
            # loc `equal("novel_id", ...)` hang loat de gom nhieu truyen mot
            # truy van (chong N+1 cho khu quan tri) — cung tinh huong voi
            # `post_id_idx`/`comment_id_idx` o tren, chua co chi muc phu truoc do.
            ("novel_id_idx", "key", ["novel_id"]),
        ],
    },
    "chapters": {
        "name": "Chapters",
        "attributes": [
            ("chapter_id", "string", True, 64),
            ("novel_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            ("content", "string", False, 1000000),
            ("order_index", "integer", True, None),
            ("state", "enum", True, ["draft", "published", "archived"]),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("novel_idx", "key", ["novel_id"]),
            ("novel_order_idx", "key", ["novel_id", "order_index"]),
            ("owner_idx", "key", ["owner_id"]),
        ],
    },
    "tts_jobs": {
        "name": "TTS Jobs",
        "attributes": [
            ("job_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("chapter_id", "string", True, 64),
            ("voice_id", "string", True, 128),
            ("content_hash", "string", True, 64),
            ("status", "enum", True, ["pending", "running", "completed", "failed"]),
            ("output_key", "string", False, 512),
            ("error_kind", "string", False, 64),
            ("error_message", "string", False, 1000),
            ("total_parts", "integer", False, None),
            ("done_parts", "integer", False, None),
            ("rate", "string", False, 16),
            ("chunk_chars", "integer", False, None),
            # --- worker recovery ---------------------------------------------
            # Ba thuoc tinh TUY CHON. Job tao truoc khi them chung se mang gia
            # tri null, va code coi "khong co lease" = "khong con worker nao
            # giu" — dung nhu y muon, vi job cu ket `running` chinh la thu can
            # duoc recovery.
            #
            # Them thuoc tinh la thao tac CONG THEM: khong ghi lai ban ghi nao,
            # khong pha du lieu cu, va chay lai script nay bao nhieu lan cung
            # duoc (`_ensure_attribute` bo qua neu da co).
            #
            # ROLLBACK: xoa ba thuoc tinh nay. Gia tri trong do la trang thai
            # dieu phoi, khong phai du lieu nguoi dung — mat di thi he thong chi
            # tro lai hanh vi cu (khong co recovery), khong mat audio nao.
            ("lease_expires_at", "datetime", False, None),
            ("lease_owner", "string", False, 64),
            ("attempts", "integer", False, None),
            ("created_at", "datetime", True, None),
            ("started_at", "datetime", False, None),
            ("finished_at", "datetime", False, None),
        ],
        "indexes": [
            # Index QUAN TRONG NHAT: phuc vu idempotency
            ("idempotency_idx", "key", ["owner_id", "chapter_id", "content_hash"]),
            ("status_idx", "key", ["status"]),
            # Quet job ket: tim theo trang thai roi loc theo lease
            ("status_lease_idx", "key", ["status", "lease_expires_at"]),
        ],
    },
    # Khoa cua viec nhan job. MOT hang cho MOI lan thu cua MOI job, id tat dinh
    # `{job_id}-{attempt}`.
    #
    # Ca collection nay ton tai vi mot ly do duy nhat: tinh DUY NHAT cua rowId do
    # database cuong che. Dat thao tac `create` hang nay VAO TRONG transaction
    # cung voi `update` job row thi duoc mot compare-and-set that su — worker thua
    # co commit hong han, khong phai "ghi roi doc lai thay minh thua".
    #
    # ROLLBACK: xoa ca collection. Khong mat du lieu nguoi dung nao — day thuan
    # tuy la trang thai dieu phoi. Mat no thi he thong quay ve khong co claim
    # nguyen tu, khong mat audio.
    "job_claims": {
        "name": "Job Claims",
        "attributes": [
            ("job_id", "string", True, 64),
            ("attempt", "integer", True, None),
            ("worker_id", "string", True, 64),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("job_idx", "key", ["job_id"]),
        ],
    },
    # Khoa TAT DINH chan hai request cung tao mot job.
    #
    # `$id` la bam cua (owner_id, chapter_id, fingerprint), va hang khoa duoc
    # tao trong CUNG transaction voi hang job — nen chi mot request commit
    # duoc. Ban va cho mot loi da xay ra that: nam request trong 2 giay deu doc
    # thay "chua co" roi deu tao mot job cho cung mot chuong.
    #
    # KHONG co index: moi truy cap deu theo `$id`.
    "job_locks": {
        "name": "Job Locks",
        "attributes": [
            ("job_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [],
    },
    # ==========================================================================
    # Animation (V6, overnight Phase 5) — subsystem RIENG, doc lap voi
    # novels/chapters. Xem `server/animation_domain.py` va
    # `server/appwrite_animation_store.py` ve vi sao day KHONG dung chung bang
    # voi Truyen: Animation la mot san pham XEM, khong phai ban chuyen the.
    "animation_series": {
        "name": "Animation Series",
        "attributes": [
            ("series_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            ("description", "string", False, 2000),
            ("cover_key", "string", False, 512),
            ("state", "enum", True, ["draft", "published", "archived"]),
            ("tags", "string", False, 64),               # mang
            # Lien ket TUY CHON toi mot truyen — RONG = khong lien ket. Xem
            # `AnimationSeries.related_novel_id`.
            ("related_novel_id", "string", False, 64),
            # Kiem duyet (Phase 4, Admin Control Center V2) — THEM SAU, KHONG
            # bat buoc: hang tao TRUOC Phase 4 khong co gia tri, doc thanh
            # VISIBLE qua `_moderation_state_from_doc` (xem
            # `appwrite_animation_store.py`). TACH BACH voi `state` o tren —
            # xem docstring `AnimationSeries.moderation_state`.
            ("moderation_state", "enum", False, ["visible", "removed"]),
            ("removed_by", "string", False, 64),
            ("removed_reason", "string", False, 1000),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("owner_idx", "key", ["owner_id"]),
            ("state_idx", "key", ["state"]),
            ("state_created_idx", "key", ["state", "created_at"]),
            ("moderation_idx", "key", ["moderation_state"]),
        ],
    },
    "animation_episodes": {
        "name": "Animation Episodes",
        "attributes": [
            ("episode_id", "string", True, 64),
            ("series_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            # Chi "youtube" duoc trien khai — ba gia tri con lai (native,
            # google_drive_private, cloudflare_stream) la KIEN TRUC DANH SAN,
            # xem `AnimationSource`.
            ("source", "enum", True,
             ["youtube", "native", "google_drive_private", "cloudflare_stream"]),
            # ID YouTube 11 ky tu DA CHUAN HOA — KHONG PHAI url tho. Xem
            # `animation_domain.parse_youtube_id`.
            ("external_id", "string", True, 32),
            ("order_index", "integer", True, None),
            ("state", "enum", True, ["draft", "published", "archived"]),
            ("duration_seconds", "double", False, None),
            # Kiem duyet (Phase 4) — cung mau voi `animation_series` o tren.
            ("moderation_state", "enum", False, ["visible", "removed"]),
            ("removed_by", "string", False, 64),
            ("removed_reason", "string", False, 1000),
            # Thuoc tinh nguon (Trusted Channels ingestion) — RONG cho tap
            # tao qua luong thu cong thuong (khong tu Trusted Channels). Xem
            # docstring `AnimationEpisode.source_channel_id` — dung de hien
            # "Nguon: <ten kenh>" canh trinh phat, KHONG bao gio dung de xac
            # thuc/phan quyen.
            ("source_channel_id", "string", False, 64),
            ("source_channel_title", "string", False, 200),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("series_idx", "key", ["series_id"]),
            ("series_order_idx", "key", ["series_id", "order_index"]),
            ("owner_idx", "key", ["owner_id"]),
            ("moderation_idx", "key", ["moderation_state"]),
            # Phase 5 (Trusted Video Sources) — phat hien MOT video YouTube
            # da la mot tap that o BAT KY series nao, tranh nhap trung. Xem
            # `AnimationStore.episodes_by_external_ids`.
            ("external_id_idx", "key", ["external_id"]),
        ],
    },
    # ==========================================================================
    # Trusted Video Sources (Phase 5, Animation Phan B) — subsystem RIENG, DOC
    # LAP voi animation_series/animation_episodes. Xem
    # `server/trusted_source_domain.py` ve moi quan he giua ba bang duoi day:
    # TrustedSource -> SeriesMapping -> AnimationSeries (da co san).
    "trusted_sources": {
        "name": "Trusted Sources",
        "attributes": [
            ("source_id", "string", True, 64),
            ("source_type", "enum", True,
             ["youtube_channel", "youtube_playlist", "youtube_video",
              "direct_hls", "direct_mp4"]),
            ("youtube_channel_id", "string", False, 64),
            ("youtube_playlist_id", "string", False, 64),
            ("youtube_video_id", "string", False, 32),
            ("display_name", "string", False, 200),
            ("thumbnail_url", "string", False, 512),
            ("enabled", "boolean", True, None),
            ("auto_discover", "boolean", True, None),
            ("auto_import", "boolean", True, None),
            ("auto_publish", "boolean", True, None),
            ("minimum_confidence", "double", True, None),
            ("created_by", "string", False, 64),
            ("last_scan_at", "datetime", False, None),
            ("last_success_at", "datetime", False, None),
            ("last_error_at", "datetime", False, None),
            ("last_error_message", "string", False, 1000),
            # WebSub (Phase 6) — dang ky/gia han that voi hub PubSubHubbub
            # cua YouTube, xem `SubscriptionStatus`/`server/youtube_websub.py`.
            ("subscription_status", "enum", True,
             ["none", "pending", "active", "expired", "failed"]),
            ("subscription_expires_at", "datetime", False, None),
            ("last_subscription_attempt_at", "datetime", False, None),
            ("last_notification_at", "datetime", False, None),
            ("last_websub_error", "string", False, 1000),
            ("last_successful_sync_at", "datetime", False, None),
            # Bi mat HMAC ky/xac minh thong bao WebSub — KHONG BAO GIO ra
            # `to_dict()`/API quan tri, xem docstring `TrustedSource.
            # websub_secret`. Do dai du cho `secrets.token_urlsafe(32)`.
            ("websub_secret", "string", False, 64),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("channel_idx", "key", ["youtube_channel_id"]),
            ("playlist_idx", "key", ["youtube_playlist_id"]),
            ("video_idx", "key", ["youtube_video_id"]),
            ("enabled_idx", "key", ["enabled"]),
        ],
    },
    "series_mappings": {
        "name": "Series Mappings",
        "attributes": [
            ("mapping_id", "string", True, 64),
            ("trusted_source_id", "string", True, 64),
            ("animation_series_id", "string", True, 64),
            ("aliases", "string", False, 200),           # mang
            ("include_keywords", "string", False, 100),  # mang
            ("exclude_keywords", "string", False, 100),   # mang
            # `None`/vang mat = ke thua `TrustedSource.minimum_confidence` —
            # KHONG bat buoc, xem `SeriesMapping.minimum_confidence`.
            ("minimum_confidence", "double", False, None),
            ("auto_import", "boolean", False, None),
            ("auto_publish", "boolean", False, None),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("source_idx", "key", ["trusted_source_id"]),
            ("series_idx", "key", ["animation_series_id"]),
        ],
    },
    "video_imports": {
        "name": "Video Imports",
        "attributes": [
            ("import_id", "string", True, 64),
            ("trusted_source_id", "string", False, 64),
            # ID video YouTube — DUY NHAT trong toan he thong. `import_id`
            # TAT DINH tu gia tri nay, xem
            # `trusted_source_domain.video_import_id`.
            ("youtube_video_id", "string", True, 32),
            ("title", "string", False, 300),
            ("channel_id", "string", False, 64),
            ("channel_title", "string", False, 200),
            ("thumbnail_url", "string", False, 512),
            ("published_at", "datetime", False, None),
            ("duration_seconds", "double", False, None),
            ("detected_mapping_id", "string", False, 64),
            ("detected_series_id", "string", False, 64),
            ("detected_episode_number", "integer", False, None),
            ("confidence", "double", False, None),
            ("signals", "string", False, 300),  # mang
            ("status", "enum", True,
             ["new", "pending", "auto_imported", "auto_published", "imported",
              "rejected", "ignored", "duplicate", "conflict", "unavailable",
              "failed"]),
            ("reason", "string", False, 500),
            ("created_episode_id", "string", False, 64),
            ("reviewed_by", "string", False, 64),
            ("reviewed_at", "datetime", False, None),
            # Auto-Ingestion Phase 4 — THEM SAU (additive, khong bat buoc):
            # trigger nao lam ban ghi nay xuat hien LAN DAU, xem docstring
            # `VideoImport.discovered_via`. Ban ghi CU truoc Phase 4 doc
            # thanh "" (tuong thich nguoc, khong phai loi) — KHONG can
            # migration du lieu nguoc, chi can chay lai script nay de them
            # thuoc tinh (an toan, "dong-thieu-thi-bo-qua" cung mau voi
            # `moderation_state` o Phase 4 cu cua Animation).
            ("discovered_via", "enum", False,
             ["manual_scan", "reconcile", "websub", "auto_discovery"]),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("video_idx", "unique", ["youtube_video_id"]),
            ("source_idx", "key", ["trusted_source_id"]),
            ("status_idx", "key", ["status"]),
            ("series_idx", "key", ["detected_series_id"]),
        ],
    },
    "audio_tracks": {
        "name": "Audio Tracks",
        "attributes": [
            ("track_id", "string", True, 64),
            ("chapter_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("voice_id", "string", True, 128),
            ("object_key", "string", True, 512),
            ("content_hash", "string", True, 64),
            ("duration_seconds", "double", False, None),
            ("size_bytes", "integer", False, None),
            ("created_at", "datetime", True, None),
            # Phu de dong bo (V4, Phan 2H) — additive. Khoa sidecar trong CUNG
            # kho voi `object_key` (R2/local), KHONG phai noi dung transcript:
            # xem `server/transcript.py` va docstring `AudioTrack`.
            ("transcript_key", "string", False, 512),
            ("transcript_version", "integer", False, None),
            ("source_content_hash", "string", False, 64),
        ],
        "indexes": [
            ("chapter_idx", "key", ["chapter_id"]),
            ("chapter_created_idx", "key", ["chapter_id", "created_at"]),
        ],
    },
    # ==========================================================================
    # Novel Translation Studio (V5) — subsystem RIENG, KHONG dung chung bang
    # voi novels/chapters/tts_jobs o tren. Xem
    # `server/appwrite_translation_store.py` va docstring cua no ve vi sao
    # CHUA co collection "chapters"/"characters" rieng (mo hinh hien tai gom
    # chuong/tom-tat trong CHINH translation_projects, nhan vat la mot LOAI
    # trong translation_glossary).
    #
    # BA COLLECTION NAY CHUA duoc ap len bat ky moi truong nao (dev/staging/
    # production) — chi khai bao o day de `setup_appwrite.py` san sang khi
    # can, giong dung mo hinh voi ba thuoc tinh V2 (username/bio/author_status)
    # da tung nam cho san truoc khi ap.
    # ==========================================================================
    "translation_projects": {
        "name": "Translation Projects",
        "attributes": [
            ("project_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            # 300000 = MAX_CHARS_PER_PROJECT (server/translation_service.py) —
            # ca du an khong the vuot muc nay du chia lam bao nhieu chuong.
            ("source_text", "string", True, 300000),
            ("source_language", "string", False, 8),
            ("target_language", "string", False, 8),
            ("genre", "enum", False,
             ["tien_hiep", "huyen_huyen", "vo_hiep", "do_thi", "ngon_tinh",
              "lich_su", "he_thong", "dong_nhan", "kinh_di", "auto"]),
            ("naming_mode", "enum", False,
             ["han_viet", "pinyin", "thuan_viet", "fandom", "auto"]),
            ("quality_mode", "enum", False, ["nhanh", "can_bang", "van_hoc"]),
            ("custom_instruction", "string", False, 1000),
            ("source_filename", "string", False, 255),
            # Hai MANG song song, chi so khop CHI SO CHUONG (tach tu
            # source_text luc doc, khong luu rieng danh sach chuong).
            ("chapter_summaries", "string", False, 500),      # mang
            ("translated_chapters", "string", False, 300000), # mang
            ("imported_to_novel_id", "string", False, 64),
            # --- Part N/Q3, THEM SAU — chua ap len bat ky moi truong nao ------
            # Moi chuong 1 chuoi JSON (danh sach canh bao) — xem
            # `server/appwrite_translation_store.py::_project_to_row`.
            ("chapter_warnings", "string", False, 2000),        # mang
            ("provider_mode", "string", False, 16),
            ("selected_provider_id", "string", False, 64),
            ("allow_fallback", "boolean", False, None),
            # V5.1 Part F, THEM SAU — "Ưu tiên API key cá nhân".
            ("prefer_personal_provider", "boolean", False, None),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("owner_idx", "key", ["owner_id"]),
            ("owner_created_idx", "key", ["owner_id", "created_at"]),
        ],
    },
    "translation_jobs": {
        "name": "Translation Jobs",
        "attributes": [
            ("job_id", "string", True, 64),
            ("project_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("status", "enum", True,
             ["queued", "analyzing", "glossary", "translating", "reviewing",
              "qa", "waiting_for_provider", "completed", "failed", "cancelled"]),
            ("current_chapter", "integer", False, None),
            ("total_chapters", "integer", False, None),
            ("current_chapter_done_segments", "integer", False, None),
            ("current_chapter_total_segments", "integer", False, None),
            # --- claim/lease (worker nen rieng, cung khuon voi tts_jobs) ------
            # Bon thuoc tinh nay CHUA duoc ap len bat ky moi truong nao (giong
            # het ba thuoc tinh V2 cua `profiles` truoc khi duoc ap) — chi
            # khai bao truoc de mot lan chay script sau nay tao chung.
            ("current_pass", "string", False, 32),
            ("attempts", "integer", False, None),
            ("lease_owner", "string", False, 64),
            ("lease_expires_at", "datetime", False, None),
            ("error", "string", False, 300),
            # Part Q4, THEM SAU — moc thu lai khi job dang cho han muc mien phi.
            ("waiting_retry_at", "datetime", False, None),
            # V5.1 Part G, THEM SAU — ly do/hanh dong AN TOAN cho frontend.
            ("waiting_reason", "string", False, 32),
            ("waiting_action", "string", False, 32),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
            ("finished_at", "datetime", False, None),
        ],
        "indexes": [
            ("project_idx", "key", ["project_id"]),
            ("project_created_idx", "key", ["project_id", "created_at"]),
            ("owner_idx", "key", ["owner_id"]),
            ("status_idx", "key", ["status"]),
        ],
    },
    # Khoa cua viec nhan job dich — cung ly do ton tai voi `job_claims` cua
    # TTS: tinh DUY NHAT cua rowId do database cuong che, dat thao tac
    # `create` hang nay VAO TRONG transaction cung voi `update` job row thi
    # duoc mot compare-and-set that su. Xem
    # `server/appwrite_translation_store.py::AppwriteTranslationStore.claim_job`.
    #
    # ROLLBACK: xoa ca collection — chi la trang thai dieu phoi, khong mat du
    # lieu dich nao.
    "translation_job_claims": {
        "name": "Translation Job Claims",
        "attributes": [
            ("job_id", "string", True, 64),
            ("attempt", "integer", True, None),
            ("worker_id", "string", True, 64),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("job_idx", "key", ["job_id"]),
        ],
    },
    "translation_glossary": {
        "name": "Translation Glossary",
        "attributes": [
            ("term_id", "string", True, 64),
            ("project_id", "string", True, 64),
            ("category", "enum", True,
             ["character", "place", "organization", "power_system", "item",
              "other"]),
            ("original", "string", True, 80),
            ("translated", "string", True, 80),
            ("aliases", "string", False, 80),     # mang
            ("note", "string", False, 500),
            ("locked", "boolean", False, None),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("project_idx", "key", ["project_id"]),
        ],
    },
    # Lich su ban dich (Part O) — COLLECTION THU NAM, CONG THEM, chua ap len
    # bat ky moi truong nao. Additive-only theo dung yeu cau: khong sua/xoa
    # ban ghi cu, chi luon them ban ghi moi (xem
    # `server/translation_domain.py::TranslationVersion`).
    "translation_versions": {
        "name": "Translation Versions",
        "attributes": [
            ("version_id", "string", True, 64),
            ("project_id", "string", True, 64),
            ("chapter_index", "integer", True, None),
            ("paragraph_index", "integer", False, None),  # -1 = ca chuong
            ("operation", "string", True, 32),
            ("pass_type", "string", True, 16),
            ("previous_text", "string", False, 300000),
            ("new_text", "string", False, 300000),
            ("actor_id", "string", False, 64),
            ("provider_id", "string", False, 64),
            ("model_id", "string", False, 128),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("project_idx", "key", ["project_id"]),
            ("project_chapter_idx", "key", ["project_id", "chapter_index"]),
            ("project_created_idx", "key", ["project_id", "created_at"]),
        ],
    },
    # Ket noi provider AI CA NHAN cua nguoi dung (V5.1, BYOK) — COLLECTION
    # THU SAU, CONG THEM, chua ap len bat ky moi truong nao.
    #
    # `encrypted_secret` LA CHUOI DA MA HOA (AES-256-GCM, xem
    # `server/translation_byok_crypto.py`) — KHONG BAO GIO la api key ro.
    # Ban than viec ap schema nay KHONG lam lo bi mat gi (chi tao cot rong);
    # rui ro chi phat sinh khi co du lieu that duoc ghi vao SAU khi ap, va
    # luc do van an toan vi gia tri luon o dang da ma hoa.
    #
    # ROLLBACK: xoa ca collection — nguoi dung se can ket noi lai API key
    # rieng cua ho (khong mat gi thuoc ve Fanfic, chi mat ket noi CA NHAN).
    "translation_provider_connections": {
        "name": "Translation Provider Connections",
        "attributes": [
            ("connection_id", "string", True, 64),
            ("user_id", "string", True, 64),
            ("provider_id", "string", True, 32),
            # Du cho tien to "byok.v1." + base64(nonce 12B) + "." +
            # base64(ciphertext) cho mot api key that dai toi ~200 ky tu.
            ("encrypted_secret", "string", True, 1000),
            ("last4", "string", False, 8),
            ("status", "enum", False,
             ["available", "rate_limited", "quota_exhausted", "unavailable",
              "disabled", "unknown"]),
            ("selected_model", "string", False, 128),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
            ("last_verified_at", "datetime", False, None),
        ],
        "indexes": [
            ("user_idx", "key", ["user_id"]),
        ],
    },
    # --- V4 visual completion, Phan G/K/L: cap do + vat pham suu tam --------
    # THIET KE — logic thuan da co test (server/gamification.py,
    # server/gamification_domain.py) VA da noi vao route that qua
    # `MockGamificationStore` (server/gamification_store.py). Bon collection
    # duoi day CHUA duoc ap len production trong dot nay; chi them vao SCHEMA
    # de --dry-run the hien dung ke hoach khi lam ban Appwrite that cua kho
    # (tuong tu `appwrite_translation_store.py`).
    #
    # ROLLBACK: xoa ca bon collection — khong anh huong gi den du lieu dang
    # dung (kho dang chay la `MockGamificationStore` trong bo nho, khong
    # collection nao o day duoc doc/ghi that hien nay).
    "user_progress": {
        "name": "User Progress",
        "attributes": [
            ("user_id", "string", True, 64),
            ("xp", "integer", True, None),
            ("equipped_title_key", "string", False, 64),
            # So goi thuong mien phi dang cho mo — xem
            # `gamification_domain.UserProgress.goi_thuong_dang_cho`.
            ("pending_reward_packs", "integer", False, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("user_idx", "unique", ["user_id"]),
            # Phase 13 (overnight hardening): `list_all_progress_ranked`
            # (bang xep hang XP toan thoi gian) sap `orderDesc("xp")`, va
            # `count_users_above_xp` loc `greaterThan("xp", ...)` — ca hai
            # deu khong co chi muc nao phu truoc do, nen la mot phep sap toan
            # bang moi lan mo trang xep hang.
            ("xp_idx", "key", ["xp"]),
        ],
    },
    "cosmetic_inventory": {
        "name": "Cosmetic Inventory",
        "attributes": [
            ("user_id", "string", True, 64),
            ("cosmetic_key", "string", True, 64),
            ("acquired_at", "datetime", True, None),
            ("equipped", "boolean", False, None),
        ],
        "indexes": [
            ("user_idx", "key", ["user_id"]),
        ],
    },
    # Nhat ky XP kiem toan duoc — xem `gamification_domain.XpLedgerEntry`.
    # `entry_id` la khoa idempotency: `MockGamificationStore.record_xp_event`
    # tu choi ghi neu id da co, chan client refresh/retry cong XP hai lan.
    "xp_ledger": {
        "name": "XP Ledger",
        "attributes": [
            ("entry_id", "string", True, 128),
            ("user_id", "string", True, 64),
            ("event_type", "string", True, 64),
            ("source_kind", "string", True, 32),
            ("source_id", "string", True, 64),
            ("xp_awarded", "integer", True, None),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("entry_idx", "unique", ["entry_id"]),
            ("user_idx", "key", ["user_id"]),
            # Phase 13 (overnight hardening): `xp_earned_since` quet TOAN BO
            # nhat ky XP (moi nguoi dung) tu mot moc thoi gian — khong co chi
            # muc nao phu `created_at` truoc do.
            ("created_idx", "key", ["created_at"]),
        ],
    },
    # Thanh tuu DA MO KHOA that su kem moc thoi gian — xem
    # `gamification_domain.UnlockedAchievement`. Tach khoi tinh toan tai cho
    # (`gamification.tinh_trang_thanh_tuu`) de khong "quen mo lai" khi du
    # lieu nguon giam sau nay (vi du xoa truyen).
    "achievement_unlocks": {
        "name": "Achievement Unlocks",
        "attributes": [
            ("user_id", "string", True, 64),
            ("achievement_key", "string", True, 64),
            ("unlocked_at", "datetime", True, None),
        ],
        "indexes": [
            ("user_achievement_idx", "unique", ["user_id", "achievement_key"]),
            ("user_idx", "key", ["user_id"]),
        ],
    },
    # V6 gamification (chuoi ngay doc + nhiem vu) — xem
    # `gamification_domain.ReadingStreak`/`QuestProgress`. THIET KE, chua ap
    # len production; kho dang chay la `MockGamificationStore` trong bo nho.
    # `documentId` = `user_id` (giong `user_progress`) nen "user_idx" o day
    # chi phuc vu truy van tuong minh, khong thay the rang buoc duy nhat.
    #
    # ROLLBACK: xoa ca hai collection — khong anh huong du lieu dang dung.
    "reading_streaks": {
        "name": "Reading Streaks",
        "attributes": [
            ("user_id", "string", True, 64),
            ("current_streak", "integer", True, None),
            ("longest_streak", "integer", True, None),
            # Ngay ISO "YYYY-MM-DD" theo lich UTC — xem gioi han da ghi trong
            # `gamification_domain.advance_streak` (chua theo mui gio nguoi
            # dung). La chuoi, khong phai `datetime`, de tranh lech gio.
            ("last_read_date", "string", False, 10),
            ("grace_used_this_run", "boolean", False, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("user_idx", "unique", ["user_id"]),
        ],
    },
    # `documentId` = `id_tien_do_nhiem_vu(user_id, quest_key, period_key)` —
    # xem `gamification.py`. Idempotency + tinh duy nhat theo bo ba do khoa
    # tai lop id, khong can index unique rieng cho ba truong nay.
    "quest_progress": {
        "name": "Quest Progress",
        "attributes": [
            ("user_id", "string", True, 64),
            ("quest_key", "string", True, 64),
            # "YYYY-MM-DD" (daily) hoac "YYYY-Www" (weekly) — xem
            # `gamification_domain.quest_period_key`.
            ("period_key", "string", True, 16),
            ("count", "integer", True, None),
            ("claimed", "boolean", False, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("user_idx", "key", ["user_id"]),
        ],
    },
    # ================================================================
    # Image Studio V1 (overnight build) — THIET KE, CHUA co adapter Appwrite
    # that (chay tren `MockWalletStore`/`MockByopConnectionStore`/
    # `MockImageLibraryStore` trong bo nho, xem `server/image_*.py`).
    #
    # Schema o day CHI la chuan bi cho lan bat Appwrite production mo lai —
    # xem `docs/reports/appwrite-selfhost-gce-summary.md` muc "Phase 7".
    # KHONG doi mac dinh Shared Premium/BYOP: hai tinh nang do van tat theo
    # `IMAGE_SHARED_PREMIUM_ENABLED`/`IMAGE_BYOP_MASTER_KEY` du schema da co.
    # ================================================================

    # So cai vi Fanfic Credit — xem `image_domain.WalletTransaction`.
    # APPEND-ONLY BAT BUOC: adapter Appwrite sau nay KHONG duoc phep UPDATE
    # mot document da ghi, chi INSERT moi — cung nguyen tac voi
    # `MockWalletStore._ghi_giao_dich`. `idempotency_idx` (unique) la diem
    # chan tru tien hai lan DUY NHAT — day la rang buoc quan trong nhat cua
    # toan bo Image Studio, phai giu nguyen khi chuyen sang Appwrite that.
    "image_wallet_transactions": {
        "name": "Image Wallet Transactions",
        "attributes": [
            ("transaction_id", "string", True, 64),
            ("user_id", "string", True, 64),
            # Rong khi la giao dich TOP_UP (chua gan voi mot lan sinh anh nao).
            ("generation_id", "string", False, 64),
            ("entry_type", "enum", True,
             ["top_up", "reserve", "settle", "release", "refund", "promotional"]),
            # Am = tru so du kha dung, duong = tra lai/nap them — xem
            # `WalletTransaction.amount_micro`.
            ("amount_micro", "integer", True, None),
            ("idempotency_key", "string", True, 128),
            ("created_at", "datetime", True, None),
            ("note", "string", False, 500),
        ],
        "indexes": [
            ("idempotency_idx", "unique", ["idempotency_key"]),
            ("user_idx", "key", ["user_id"]),
            ("generation_idx", "key", ["generation_id"]),
        ],
    },
    # Trang thai giu cho MOT lan sinh anh — xem `image_domain.GenerationReservation`.
    # `documentId` NEN la `generation_id` khi adapter that duoc viet (giong quy
    # uoc `user_progress`/`documentId = user_id`) — tu than no da la khoa
    # idempotency, index rieng o day chi phuc vu truy van tuong minh.
    "image_generation_reservations": {
        "name": "Image Generation Reservations",
        "attributes": [
            ("generation_id", "string", True, 64),
            ("user_id", "string", True, 64),
            ("mode", "enum", True,
             ["quick_free", "shared_premium", "byop", "community_free"]),
            ("provider_id", "string", True, 64),
            ("model", "string", True, 80),
            ("estimated_cost_micro", "integer", True, None),
            ("status", "enum", True,
             ["pending", "reserved", "succeeded", "failed", "refunded"]),
            ("idempotency_key", "string", True, 128),
            # Rong cho toi khi status == SUCCEEDED va provider tra chi phi that.
            ("actual_cost_micro", "integer", False, None),
            ("pricing_snapshot_version", "string", False, 32),
            ("created_at", "datetime", True, None),
            ("settled_at", "string", False, 32),
            ("error_message", "string", False, 500),
        ],
        "indexes": [
            ("generation_idx", "unique", ["generation_id"]),
            ("idempotency_idx", "unique", ["idempotency_key"]),
            ("user_idx", "key", ["user_id"]),
        ],
    },
    # Anh nguoi dung CHU DONG "Luu" — xem `image_domain.SavedImage`. CHI ghi
    # khi nguoi dung bam Luu (PHASE 9: "Do NOT store every generated
    # candidate permanently") — moi ung vien tam khac song trong bo nho
    # (`ImageStudioService._anh_tam`), khong bao gio toi day.
    "image_saved_library": {
        "name": "Image Saved Library",
        "attributes": [
            ("image_id", "string", True, 64),
            ("owner_user_id", "string", True, 64),
            ("generation_id", "string", True, 64),
            ("prompt", "string", True, 2000),
            ("negative_prompt", "string", False, 1000),
            ("model", "string", False, 80),
            ("mode", "enum", True,
             ["quick_free", "shared_premium", "byop", "community_free"]),
            ("aspect_ratio", "string", False, 10),
            # Khoa doi tuong storage (Local/R2), KHONG PHAI url truc tiep —
            # cung quy uoc voi `novels.cover_key`/`profiles.avatar_key`.
            ("storage_key", "string", True, 512),
            ("created_at", "datetime", True, None),
            ("safety_status", "string", False, 32),
        ],
        "indexes": [
            ("image_idx", "unique", ["image_id"]),
            ("owner_idx", "key", ["owner_user_id"]),
        ],
    },
    # Ket noi BYOP (Bring-Your-Own-Pollinations) — xem
    # `image_domain.PollinationsConnection`. TUYET DOI KHONG duoc them thuoc
    # tinh chua token dang RO — CHI hai truong `encrypted_*` (AES-256-GCM qua
    # `ByokCrypto`, xem `image_byop_crypto.py`). Kich thuoc 2048 du rong cho
    # ciphertext + nonce + tag ma hoa base64 cua token OAuth thong thuong.
    "image_byop_connections": {
        "name": "Image BYOP Connections",
        "attributes": [
            ("user_id", "string", True, 64),
            ("provider_id", "string", True, 32),
            ("encrypted_access_token", "string", False, 2048),
            ("encrypted_refresh_token", "string", False, 2048),
            ("scope", "string", False, 64),
            ("expires_at", "string", False, 32),
            # Ngan sach nguoi dung TU CHON — chi hien thi/canh bao phia Fanfic
            # World, KHONG phai gioi han that (Pollinations tu quan ly Pollen).
            ("user_budget_micro", "integer", False, None),
            ("connected_at", "datetime", True, None),
            ("revoked_at", "string", False, 32),
        ],
        "indexes": [
            # MOI nguoi dung CHI mot ket noi BYOP dang hieu luc tai mot thoi
            # diem — khop voi `MockByopConnectionStore` (dict khoa boi user_id).
            ("user_idx", "unique", ["user_id"]),
        ],
    },
}

#: Cac thuoc tinh la MANG. Appwrite doi co `array: true` luc tao; thieu no thi
#: thuoc tinh thanh chuoi don va buoc ghi dau tien bi tu choi.
#:
#: `chapter_summaries`/`translated_chapters`/`aliases` CHI dung o
#: `translation_projects`/`translation_glossary` — ten trung voi truong khac
#: (vi du neu sau nay mot collection khac cung dung ten "aliases" ma KHONG
#: phai mang) se vo tinh bi ep `array: true`. Chua xay ra o schema hien tai,
#: ghi chu o day de tranh bay khi them collection moi.
#:
#: `include_keywords`/`exclude_keywords`/`signals` them o Phase 5 (Trusted
#: Video Sources, `series_mappings`/`video_imports`) — DUNG chinh cai bay
#: nay bi vap THAT luc chay smoke test that voi Appwrite tu luu tru: thieu
#: ten trong tap nay lam Appwrite tu choi ghi voi loi "invalid type" khi
#: kho gui mot `List[str]` vao thuoc tinh tuong duoc tao nhu chuoi don.
ARRAY_ATTRIBUTES = frozenset({
    "tags", "genres", "chapter_summaries", "translated_chapters", "aliases",
    "chapter_warnings", "include_keywords", "exclude_keywords", "signals",
})

#: Quyen o muc COLLECTION: khong cap gi cho client.
#:
#: Truoc day day la `['create("users")']`, tuc la BAT KY nguoi dung da dang
#: nhap nao cung tu tao document truc tiep qua Appwrite API duoc, o CA NAM
#: collection - bo qua hoan toan backend. Quyen o muc collection ap dung
#: THEM vao quyen tung document, nen no vo hieu hoa chinh mo hinh phan quyen
#: theo document ma ta thiet ke.
#:
#: Moi thao tac GHI deu di qua backend bang API key, ma API key bo qua
#: permission - nen de rong o day khong lam hong chuc nang nao.
#: Quyen DOC van do tung document quyet dinh (documentSecurity=True).
COLLECTION_PERMISSIONS: List[str] = []


class Setup:
    def __init__(self, dry_run: bool = False):
        settings = load_settings()
        # Che do thu chi in ke hoach nen khong can credential
        if not settings.appwrite.configured and not dry_run:
            raise SystemExit(
                "Thiếu cấu hình Appwrite. Cần đủ APPWRITE_ENDPOINT, "
                "APPWRITE_PROJECT_ID, APPWRITE_API_KEY, APPWRITE_DATABASE_ID."
            )
        self.cfg = settings.appwrite
        # `api_base` da bo `/v1` o cuoi neu co - moi path duoi day tu them `/v1`
        self.endpoint = self.cfg.api_base or "https://<endpoint>"
        self.dry_run = dry_run
        self.created = 0
        self.skipped = 0
        # Khoa cho viec quan SCHEMA: uu tien `APPWRITE_SCHEMA_API_KEY`.
        #
        # Khoa runtime cua backend chi can quyen documents; quyen sua schema
        # song o mot khoa RIENG khong bao gio len Render. Thieu khoa rieng thi
        # lui ve khoa runtime (staging cap du quyen cho no) — va neu khoa do
        # cung thieu scope, Appwrite tu choi TRUOC khi ghi bat cu gi, `_call`
        # se in huong dan doc duoc thay vi mot stack trace. Chi in TEN bien,
        # khong bao gio in gia tri.
        self.api_key = self.cfg.schema_api_key or self.cfg.api_key
        if not dry_run:
            print("Khoá schema:",
                  "APPWRITE_SCHEMA_API_KEY" if self.cfg.schema_api_key
                  else "APPWRITE_API_KEY (fallback — chưa đặt khoá schema riêng)")

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self.cfg.project_id,
            "X-Appwrite-Key": self.api_key,     # CHI o phia server
        }

    def _exists(self, path: str) -> bool:
        """GET de kiem tra ton tai. Khong nem loi, chi tra True/False."""
        if self.dry_run:
            print(f"    [dry-run] GET {path}")
            return False
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{self.endpoint}{path}", headers=self._headers())
        return response.status_code == 200

    def _call(self, method: str, path: str, payload: Optional[Dict] = None,
              *, doc_thoi: bool = False) -> Any:
        """
        :param doc_thoi: mot phep DOC de so sanh, khong phai mot thay doi —
            khong in dong dry-run va khong cong vao bo dem `created`. Khong co
            co nay thi moi lan chay lai, moi enum da ton tai lam "tạo mới" tang
            mot don vi, va dong tong ket idempotent noi doi.
        """
        if self.dry_run:
            if not doc_thoi:
                print(f"    [dry-run] {method} {path}")
            return None
        headers = self._headers()
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(
                method, f"{self.endpoint}{path}", json=payload, headers=headers
            )
        if response.status_code == 409:
            self.skipped += 1
            return "exists"
        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            # `thong_diep_loi_an_toan` loc bi mat theo MAU (vd khoa API dang
            # "standard_...") ke ca khi roi vao nhanh fallback (JSON khong
            # doc duoc) — truoc day nhanh do dung `response.text[:300]` THO,
            # chua qua loc.
            message = thong_diep_loi_an_toan(
                body, status_code=response.status_code, gioi_han_ky_tu=2000)
            # Appwrite 1.9.6 tu-luu-tru: da xac nhan bang cach lap lai that
            # (khong doan) — tao trung index tra ve HTTP 400 kem thong diep
            # nay, KHONG PHAI 409 nhu ban Appwrite ma script duoc kiem chung
            # truoc do dung. Chi khop CHINH XAC thong diep nay (khong phai
            # moi loi 400) de khong che giau loi that khac.
            if (response.status_code == 400
                    and "already an index with the same attributes" in message):
                self.skipped += 1
                return "exists"
            # Thieu scope schema: chi ra DUNG viec can lam thay vi mot dong
            # loi tho. Da gap that o production: khoa runtime chi co quyen
            # documents, va 401 nay chan TRUOC khi bat ky thu gi bi ghi.
            if response.status_code == 401 and "missing scopes" in message:
                raise SystemExit(
                    f"Appwrite lỗi 401: {message}\n\n"
                    "Khoá đang dùng không có quyền quản schema. Tạo một API "
                    "key riêng trong Appwrite Console với scopes: "
                    "databases.read, collections.read/write, "
                    "attributes.read/write, indexes.read/write, rồi đặt vào "
                    "biến APPWRITE_SCHEMA_API_KEY (tệp env cục bộ — KHÔNG "
                    "phải Render). Khoá runtime giữ nguyên quyền documents."
                )
            raise SystemExit(f"Appwrite lỗi {response.status_code}: {message}")
        if not doc_thoi:
            self.created += 1
        return response.json() if response.content else {}

    # -- cac buoc -------------------------------------------------------------

    def ensure_database(self) -> None:
        """
        Bao dam database ton tai.

        KIEM TRA TRUOC KHI TAO. Appwrite Cloud tu ban 1.9 tao database kieu
        `tablesdb`, va `POST /v1/databases` (kieu cu) tra ve 404 - nen khong
        the dua vao 409 de biet "da co". Cac endpoint con lai cua API cu van
        chay binh thuong tren database kieu moi.
        """
        print(f"Database {self.cfg.database_id or '<APPWRITE_DATABASE_ID>'}")
        if self._exists(f"/v1/databases/{self.cfg.database_id}"):
            self.skipped += 1
            print("  đã có sẵn")
            return

        try:
            result = self._call("POST", "/v1/databases", {
                "databaseId": self.cfg.database_id,
                "name": "Fanfic Audio Studio",
            })
        except SystemExit as exc:
            raise SystemExit(
                f"{exc}\n\n"
                f"Không tạo được database qua API. Bản Appwrite Cloud mới không "
                f"cho tạo database bằng endpoint cũ.\n"
                f"Hãy vào Console tạo database với ID chính xác là "
                f"'{self.cfg.database_id}' rồi chạy lại script này."
            ) from exc
        print("  đã có sẵn" if result == "exists" else "  đã tạo")

    def ensure_collection(self, cid: str, spec: Dict[str, Any]) -> None:
        print(f"Collection {cid}")
        result = self._call("POST", f"/v1/databases/{self.cfg.database_id}/collections", {
            "collectionId": cid,
            "name": spec["name"],
            "permissions": COLLECTION_PERMISSIONS,
            "documentSecurity": True,      # quyen theo TUNG document
        })
        print("  đã có sẵn" if result == "exists" else "  đã tạo")

        base = f"/v1/databases/{self.cfg.database_id}/collections/{cid}"
        # DOC danh sach thuoc tinh HIEN CO mot lan, bo qua POST cho cai da ton
        # tai. Truoc day script cu POST roi coi 409 la "da co" — nhung tren mot
        # collection GAN TRAN dung luong hang, Appwrite kiem suc chua TRUOC khi
        # kiem trung: POST trung tra 400 "maximum size reached" thay vi 409, va
        # lan chay lai chet dung o thuoc tinh cuoi cung vua tao. Da gap that
        # tren staging voi `posts.images_json`. Kiem ton tai truoc thi khong
        # con POST trung nao de ma hong.
        da_co: set = set()
        if not self.dry_run:
            hien = self._call("GET", base, doc_thoi=True) or {}
            da_co = {a.get("key") for a in hien.get("attributes", [])}
        for key, kind, required, extra in spec["attributes"]:
            if key in da_co and kind != "enum":
                # Enum van di duong rieng: no con phai SO SANH danh sach gia
                # tri de mo rong — xem `_ensure_enum`.
                self.skipped += 1
                print(f"    - {key} ({kind}): đã có")
            else:
                self._ensure_attribute(base, key, kind, required, extra)
            if not self.dry_run:
                # CHỜ RIÊNG cho từng thuộc tính, kể cả khi "đã có" — một
                # thuộc tính đã TỒN TẠI không có nghĩa là nó DÙNG ĐƯỢC. Sự cố
                # thật (2026-08-21, self-host PROD): job nền tạo attribute
                # `profiles.user_id` bị Appwrite đánh dấu "failed" trong hàng
                # đợi (Utopia queue `*.failed.*`, xác nhận qua Redis) do một
                # lần Mongo "receive timeout" thoáng qua — KHÔNG có cơ chế
                # tự động thử lại. Thuộc tính kẹt vĩnh viễn ở "processing",
                # và mọi lần chạy lại trước đây đều coi "đã có" là xong,
                # không bao giờ phát hiện ra nó không dùng được, cho tới khi
                # `_ensure_index` thất bại với lỗi mơ hồ "not yet available".
                self._cho_thuoc_tinh_san_sang(base, key)
        for name, kind, keys in spec["indexes"]:
            if not self.dry_run:
                self._kiem_thuoc_tinh_san_sang_cho_index(base, name, keys)
            self._ensure_index(base, name, kind, keys)
            if not self.dry_run:
                self._cho_index_san_sang(base, name)

    def _goi_doc_thoi_thu_lai(self, base: str, han_chot: float) -> Optional[Dict]:
        """`GET base` (doc_thoi=True) nhưng KHÔNG để một lỗi mạng thoáng qua
        (vd `httpx.ReadTimeout`, connection reset) làm sập cả vòng chờ.

        Sự cố thật (2026-08-21, cùng self-host PROD): instance MongoDB đôi
        khi mất >30s để trả lời (đã xác nhận qua log `Utopia\\Mongo\\Exception:
        Receive timeout`), khiến httpx tự ném `ReadTimeout` — một ngoại lệ
        Python thật, KHÔNG phải một status Appwrite trả về, nên vòng lặp cũ
        (chỉ bắt trạng thái 'failed'/'stuck' từ JSON) không bắt được, và cả
        script sập ngang giữa `_cho_thuoc_tinh_san_sang`/`_cho_index_san_sang`.

        Coi lỗi mạng như MỘT LẦN THỬ THẤT BẠI bình thường trong ngân sách
        thời gian đã có (`han_chot`), không phải một lý do để dừng khác."""
        import time
        try:
            return self._call("GET", base, doc_thoi=True)
        except httpx.TransportError as exc:
            if time.monotonic() >= han_chot:
                raise SystemExit(
                    f"Lỗi mạng lặp lại khi hỏi trạng thái {base}, hết thời "
                    f"gian chờ: {exc}"
                ) from exc
            return None

    def _cho_thuoc_tinh_san_sang(self, base: str, key: str,
                                 *, timeout_giay: float = 120.0) -> None:
        """Cho DUY NHAT MOT thuoc tinh dat 'available', backoff mu tang dan
        co gioi han (0.5s -> toi da 8s giua cac lan thu, tong khong qua
        `timeout_giay`). Nem loi RO RANG (khong im lang bo qua) neu:
        - thuoc tinh bien mat khoi collection giua chung (khong nen xay ra),
        - status la 'failed' hoac 'stuck' (job nen da hong han, cho tiep vo
          ich — xem su co 2026-08-21 o docstring ben tren),
        - het `timeout_giay` ma van khong 'available'.
        KHONG bao gio tra ve lang le khi chua san sang — day la khac biet cot
        loi voi ham cu (`_doi_thuoc_tinh_san_sang`, da bo), von im lang bo
        qua sau khi het luot thu va de `_ensure_index` tu bao loi mo ho."""
        import time
        han_chot = time.monotonic() + timeout_giay
        khoang_cho = 0.5
        while True:
            hien = self._goi_doc_thoi_thu_lai(base, han_chot)
            if hien is None:
                # Loi mang thoang qua, da trong ngan sach thoi gian — thu lai,
                # KHONG coi la "thuoc tinh bien mat".
                time.sleep(khoang_cho)
                khoang_cho = min(khoang_cho * 1.5, 8.0)
                continue
            thuoc_tinh = next((a for a in hien.get("attributes", [])
                               if a.get("key") == key), None)
            if thuoc_tinh is None:
                raise SystemExit(
                    f"Thuộc tính '{key}' biến mất khỏi {base} trong lúc chờ "
                    "sẵn sàng — không nên xảy ra, kiểm tra thủ công."
                )
            trang_thai = thuoc_tinh.get("status")
            if trang_thai == "available":
                return
            if trang_thai in ("failed", "stuck"):
                raise SystemExit(
                    f"Thuộc tính '{key}' ở {base} có trạng thái '{trang_thai}': "
                    f"{thuoc_tinh.get('error') or '(Appwrite không kèm thông điệp lỗi)'}. "
                    "Job nền tạo thuộc tính này đã hỏng hẳn (không tự thử lại) — "
                    "cách sửa AN TOÀN NHỎ NHẤT đã xác nhận qua sự cố thật "
                    "2026-08-21: DELETE thuộc tính này (chỉ khi collection "
                    "CHƯA có document thật nào phụ thuộc), rồi chạy lại script "
                    "này để nó tự tạo lại. Xem docs/reports/preprod-security-audit.md"
                    " hoặc lịch sử sửa lỗi commit này để biết chi tiết."
                )
            if time.monotonic() >= han_chot:
                raise SystemExit(
                    f"Thuộc tính '{key}' ở {base} vẫn '{trang_thai}' sau "
                    f"{timeout_giay:.0f}s chờ — có thể job nền bị kẹt/mất "
                    "(kiểm tra Redis 'utopia-queue.failed.*' và log "
                    "appwrite-worker-databases trước khi chạy lại)."
                )
            time.sleep(khoang_cho)
            khoang_cho = min(khoang_cho * 1.5, 8.0)

    def _cho_index_san_sang(self, base: str, key: str,
                            *, timeout_giay: float = 120.0) -> None:
        """Tuong tu `_cho_thuoc_tinh_san_sang` nhung cho MOT index."""
        import time
        han_chot = time.monotonic() + timeout_giay
        khoang_cho = 0.5
        while True:
            hien = self._goi_doc_thoi_thu_lai(base, han_chot)
            if hien is None:
                time.sleep(khoang_cho)
                khoang_cho = min(khoang_cho * 1.5, 8.0)
                continue
            idx = next((i for i in hien.get("indexes", []) if i.get("key") == key), None)
            if idx is None:
                raise SystemExit(
                    f"Index '{key}' biến mất khỏi {base} trong lúc chờ sẵn sàng."
                )
            trang_thai = idx.get("status")
            if trang_thai == "available":
                return
            if trang_thai in ("failed", "stuck"):
                raise SystemExit(
                    f"Index '{key}' ở {base} có trạng thái '{trang_thai}': "
                    f"{idx.get('error') or '(Appwrite không kèm thông điệp lỗi)'}."
                )
            if time.monotonic() >= han_chot:
                raise SystemExit(
                    f"Index '{key}' ở {base} vẫn '{trang_thai}' sau "
                    f"{timeout_giay:.0f}s chờ."
                )
            time.sleep(khoang_cho)
            khoang_cho = min(khoang_cho * 1.5, 8.0)

    def _ensure_attribute(self, base: str, key: str, kind: str,
                          required: bool, extra: Any) -> None:
        payload: Dict[str, Any] = {"key": key, "required": required}
        if kind == "string":
            path, payload["size"] = f"{base}/attributes/string", extra
            if key in ARRAY_ATTRIBUTES:
                payload["array"] = True
        elif kind == "email":
            path = f"{base}/attributes/email"
        elif kind == "enum":
            path, payload["elements"] = f"{base}/attributes/enum", extra
            # Enum la kieu DUY NHAT ma "da co" chua chac la "da dung": danh
            # sach gia tri co the duoc MO RONG giua hai lan chay (nhat ky kiem
            # duyet vua nhan them sau hanh dong xa hoi). POST tra 409 roi bo
            # qua se de lai enum cu — va moi hang mang gia tri moi bi Appwrite
            # tu choi AM THAM o dung cho can no nhat: luc ghi nhat ky.
            self._ensure_enum(base, key, required, list(extra))
            return
        elif kind == "boolean":
            path = f"{base}/attributes/boolean"
        elif kind == "integer":
            path = f"{base}/attributes/integer"
        elif kind == "double":
            path = f"{base}/attributes/float"
        elif kind == "datetime":
            path = f"{base}/attributes/datetime"
        else:
            raise SystemExit(f"Kiểu thuộc tính chưa hỗ trợ: {kind}")

        result = self._call("POST", path, payload)
        print(f"    - {key} ({kind}): {'đã có' if result == 'exists' else 'đã tạo'}")

    def _ensure_enum(self, base: str, key: str, required: bool,
                     elements: List[str]) -> None:
        """
        Tao enum, hoac MO RONG danh sach gia tri neu no da ton tai ma thieu.

        Chi mo rong, khong thu hep: bot mot gia tri khoi enum trong khi bang
        da co hang mang gia tri do la mot thao tac pha du lieu, va no phai la
        mot quyet dinh cua nguoi that chu khong phai cua mot script idempotent.
        """
        path = f"{base}/attributes/enum"
        ket_qua = self._call("POST", path,
                             {"key": key, "required": required,
                              "elements": elements})
        if ket_qua != "exists":
            print(f"    - {key} (enum): đã tạo")
            return
        if self.dry_run:
            return
        # Da ton tai — doc ve va so sanh danh sach gia tri.
        hien_co = self._call("GET", path.rsplit("/attributes", 1)[0],
                             doc_thoi=True)
        cot = next((a for a in (hien_co or {}).get("attributes", [])
                    if a.get("key") == key), None)
        dang_co = list((cot or {}).get("elements") or [])
        thieu = [e for e in elements if e not in dang_co]
        if not thieu:
            print(f"    - {key} (enum): đã có, đủ {len(elements)} giá trị")
            return
        gop = dang_co + thieu
        self._call("PATCH", f"{path}/{key}",
                   {"elements": gop, "required": required, "default": None})
        print(f"    - {key} (enum): MỞ RỘNG {len(dang_co)} -> {len(gop)} "
              f"giá trị (+{', '.join(thieu)})")

    def _kiem_thuoc_tinh_san_sang_cho_index(self, base: str, name: str,
                                            keys: List[str]) -> None:
        """Kiểm TRƯỚC KHI POST index: liệt kê rõ thuộc tính nào chưa
        'available' thay vì để Appwrite trả lỗi 400 mơ hồ 'not yet
        available' không nói rõ thuộc tính nào."""
        import time
        hien = self._goi_doc_thoi_thu_lai(base, time.monotonic() + 30.0) or {}
        trang_thai = {a.get("key"): a.get("status")
                      for a in hien.get("attributes", [])}
        chua_san_sang = [k for k in keys if trang_thai.get(k) != "available"]
        if chua_san_sang:
            raise SystemExit(
                f"Không thể tạo index '{name}' trên {base}: thuộc tính "
                f"{chua_san_sang} chưa 'available' (trạng thái: "
                f"{[trang_thai.get(k) for k in chua_san_sang]}). Kiểm tra "
                "job nền (Redis utopia-queue.failed.*, log "
                "appwrite-worker-databases) trước khi chạy lại."
            )

    def _ensure_index(self, base: str, name: str, kind: str, keys: List[str]) -> None:
        result = self._call("POST", f"{base}/indexes", {
            "key": name,
            "type": kind,
            "attributes": keys,
            "orders": ["ASC"] * len(keys),
        })
        print(f"    * index {name} {keys}: {'đã có' if result == 'exists' else 'đã tạo'}")

    def run(self, only: str = "") -> None:
        """
        :param only: chi cham DUNG mot collection. Bo trong = tat ca.

        Co `--only` ton tai cho migration co pham vi hep: chay ca script tren
        mot production dang song van an toan (moi buoc deu idempotent), nhung
        no van ban ra hang chuc request POST vao cac bang khong lien quan. Khi
        viec duoc cho phep chi la "tao mot bang", pham vi chay nen dung bang
        pham vi duoc cho phep.
        """
        if only and only not in SCHEMA:
            raise SystemExit(f"Không có collection {only!r} trong SCHEMA. "
                             f"Chọn một trong: {', '.join(SCHEMA)}")
        # `ensure_database` chi DOC khi database da co, nen no vo hai; giu lai
        # de script khong chay tren mot database khong ton tai.
        self.ensure_database()
        for cid, spec in SCHEMA.items():
            if only and cid != only:
                continue
            self.ensure_collection(cid, spec)
        print(f"\nHoàn tất — tạo mới {self.created}, bỏ qua (đã có) {self.skipped}.")
        print("Chạy lại script này bất cứ lúc nào đều an toàn.")


def main(argv: List[str]) -> int:
    dry_run = "--dry-run" in argv
    if dry_run:
        print("Chế độ thử: không gọi Appwrite, chỉ in các bước sẽ chạy.\n")
    only = ""
    for i, tham_so in enumerate(argv):
        if tham_so == "--only" and i + 1 < len(argv):
            only = argv[i + 1]
        elif tham_so.startswith("--only="):
            only = tham_so.split("=", 1)[1]
    if only:
        print(f"Chỉ chạm collection: {only}")
    Setup(dry_run=dry_run).run(only=only)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
