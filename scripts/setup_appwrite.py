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
              "report_resolved", "report_dismissed"]),
            ("target_user_id", "string", True, 64),
            # Rong = he thong (vd migration grandfather), khong phai mot nguoi.
            ("actor_id", "string", False, 64),
            ("note", "string", False, 1000),
            # `datetime` cua Appwrite giu duoc micro giay — can dung the: hai
            # thao tac trong cung mot giay phai doc ra dung thu tu.
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("target_created_idx", "key", ["target_user_id", "created_at"]),
            ("created_idx", "key", ["created_at"]),
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
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("owner_idx", "key", ["owner_id"]),
            ("state_idx", "key", ["state"]),
            ("state_created_idx", "key", ["state", "created_at"]),
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
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("series_idx", "key", ["series_id"]),
            ("series_order_idx", "key", ["series_id", "order_index"]),
            ("owner_idx", "key", ["owner_id"]),
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
}

#: Cac thuoc tinh la MANG. Appwrite doi co `array: true` luc tao; thieu no thi
#: thuoc tinh thanh chuoi don va buoc ghi dau tien bi tu choi.
#:
#: `chapter_summaries`/`translated_chapters`/`aliases` CHI dung o
#: `translation_projects`/`translation_glossary` — ten trung voi truong khac
#: (vi du neu sau nay mot collection khac cung dung ten "aliases" ma KHONG
#: phai mang) se vo tinh bi ep `array: true`. Chua xay ra o schema hien tai,
#: ghi chu o day de tranh bay khi them collection moi.
ARRAY_ATTRIBUTES = frozenset({
    "tags", "genres", "chapter_summaries", "translated_chapters", "aliases",
    "chapter_warnings",
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
            message = response.text[:300]
            try:
                body = response.json()
                message = body.get("message", message)
            except Exception:
                pass
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
                continue
            self._ensure_attribute(base, key, kind, required, extra)
        for name, kind, keys in spec["indexes"]:
            self._ensure_index(base, name, kind, keys)

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
