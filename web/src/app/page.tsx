"use client";

/**
 * Trang chu — Fanfic World HUB (V2, Homepage Hub + Search Glow).
 *
 * TRUOC (V4 visual completion): mot dai gioi thieu gon roi thang toi luoi
 * truyen — hop ly khi kho chi co truyen, nhung tro thanh MOT trang landing
 * truyen don le. `published_novels == 0` thi ca trang chi con lai hero +
 * MOT hop "Chưa có truyện nào được xuất bản" chiem giua man hinh.
 *
 * SAU: trang chu la mot HUB bien tap gon — hero va cac diem den o dau trang,
 * tiep theo la mot bang hai cot: thanh vien XP tuan o ben trai, danh sach
 * truyen moi dang hang o ben phai. Animation/Cong dong cung nam canh nhau,
 * nen nguoi dung khong phai cuon qua mot luoi 12 bia dai moi thay het trang.
 *
 * VE DU LIEU — day van la phan quan trong nhat khi doc file nay:
 *
 * `GET /api/novels` chi sap xep `orderDesc(created_at)` va KHONG nhan tham so
 * sort. Ke "Đang nổi bật" o day dung nghia la MOI TAO, khong phai moi cap
 * nhat — KHONG co ke "Mới cập nhật" rieng (se doi hoi mot khai niem
 * "cap nhat noi dung" ma schema hien tai khong co, xem ghi chu cu o day
 * truoc ban V2 nay — bia no ra se la mot lai noi sai voi du lieu that).
 *
 * KHONG co ke "Nghe ngay" (audio cong khai): khong ton tai mot API liet ke
 * "audio moi/noi bat" doc lap voi tim kiem — `GET /api/search/audio` can MOT
 * tu khoa, khong phai mot danh sach duyet. Bia mot ke dua tren API tim kiem
 * rong se la mot loai du lieu KHONG duoc backend ho tro that.
 *
 * "Animation mới": `GET /api/animation/series` (published-only mac dinh khi
 * khong `mine=true`, xem `server/main.py::list_animation_series`) — DA
 * XUAT BAN THAT, khong bia.
 *
 * "Bài đăng mới": `GET /api/feed` — CONG KHAI, khong doi dang nhap
 * (xem docstring `server/main.py::api_feed`) — khach vang lai van thay bang
 * tin kham pha trong Hero.
 *
 * "Tiếp tục doc/nghe/xem" KHONG BIA: goi `GET /api/progress/continue`, mot
 * API THAT tra ve con tro CA NHAN da luu. Nguoi da dang nhap nhung CHUA
 * doc/nghe/xem gi thi thay mot dong onboarding GON (khong phai mot khoi
 * rong to) — khach vang lai khong thay muc nay (thay vao do la CTA dang
 * nhap rieng, xem `DaiThanhVien`).
 */

import Image from "next/image";
import Link from "next/link";
import { useCallback, useState } from "react";
import {
  api,
  social,
  type Achievement,
  type AnimationSeries,
  type ContinueItem,
  type ContinueWatchItem,
  type LeaderboardEntry,
  type Novel,
  type OwnProgress,
  type Post,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { getReaderTags } from "@/lib/taxonomy";
import {
  novelHasAudio,
  novelFandom,
  formatAuthor,
  formatChapterCount,
} from "@/lib/catalog";
import { Avatar } from "@/components/Avatar";
import { CosmeticFrame } from "@/components/cosmetics/Cosmetics";
import { NovelCover } from "@/components/NovelCover";
import {
  CelestialDivider,
  MotifManuscript,
} from "@/components/Ornaments";
import { ErrorState, ProgressBar } from "@/components/ui";
import {
  IconBook,
  IconCompass,
  IconCrown,
  IconFilm,
  IconFlame,
  IconHeadphones,
  IconLibrary,
  IconMegaphone,
  IconSparkles,
  IconTag,
  IconUser,
} from "@/components/Icons";

/** Mot danh sach 6 hang du de quet nhanh ma khong day trang chu qua dai. */
const GRID_COUNT = 6;
/** So the hien o muc kham pha theo the. Du de goi y, khong du de thanh mot bai tuong. */
const MAX_TAGS = 12;
/** So series lay ve cho ke "Animation mới" — gon, khong canh tranh voi ke truyen. */
const ANIM_SHELF_COUNT = 4;
/** So hang lay ve cho "Bảng vàng tuần" — mot dong nhin luot qua duoc, khong
 * phai ca bang xep hang (xem /leaderboard cho ban day du). */
const BANG_VANG_COUNT = 5;
/** So bai dang lay ve cho o xem truoc cong dong — "2–4 the" theo dac ta. */
const FEED_SHELF_COUNT = 3;

interface HomeData {
  novels: Novel[];
  tags: string[];
  animationSeries: AnimationSeries[];
  communityPosts: Post[];
  reading: ContinueItem | null;
  listening: ContinueItem | null;
  watching: ContinueWatchItem | null;
  gamification: { progress: OwnProgress; thanhTuuMoiNhat: Achievement | null } | null;
  /** Top XP tuần ISO hiện tại — "Bảng vàng tuần". Rỗng khi chưa ai kiếm XP
   * trong tuần (`GET /api/leaderboard?mode=weekly` thật, xem
   * `app/leaderboard/page.tsx` — KHÔNG bịa chỉ số mới nào). */
  bangVangTuan: LeaderboardEntry[];
}

function dinhDangGio(giay: number): string {
  const s = Math.max(0, Math.floor(giay));
  const gio = Math.floor(s / 3600);
  const phut = Math.floor((s % 3600) / 60);
  const con = s % 60;
  const hai = (n: number) => String(n).padStart(2, "0");
  return gio > 0 ? `${gio}:${hai(phut)}:${hai(con)}` : `${phut}:${hai(con)}`;
}

function dinhDangNgay(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
  } catch {
    return "";
  }
}

/**
 * Mot the "Tiep tuc doc"/"Tiep tuc nghe" — dan thang toi trang doc chuong.
 *
 * Thanh tien do CHI ve khi biet `duration_seconds` that (khong bia mau so
 * 0 de ve "17:42 / 0:00" — xem ghi chu o `server/main.py::_tiep_tuc_mot_muc`).
 */
function TheTiepTuc({ kieu, muc }: { kieu: "read" | "listen"; muc: ContinueItem }) {
  const viTriGiay = muc.position_seconds ?? 0;
  const phanTram =
    kieu === "listen" && muc.duration_seconds
      ? Math.max(0, Math.min(100, Math.round((viTriGiay / muc.duration_seconds) * 100)))
      : null;

  return (
    <Link href={`/chapters/${muc.chapter_id}`} className="progress-card">
      <span className="progress-card-icon" aria-hidden="true">
        {kieu === "listen" ? "🎧" : "📖"}
      </span>
      <span className="progress-card-body">
        <strong className="clamp-1">{muc.novel_title}</strong>
        <span className="progress-card-meta">
          Chương {muc.chapter_order_index} · {muc.chapter_title}
          {kieu === "listen"
            ? ` · ${dinhDangGio(viTriGiay)}${
                muc.duration_seconds ? ` / ${dinhDangGio(muc.duration_seconds)}` : ""
              }`
            : ""}
        </span>
        {phanTram !== null ? (
          <ProgressBar percent={phanTram} label={`Đã nghe ${phanTram}%`} />
        ) : null}
      </span>
      <span className="btn btn-sm" aria-hidden="true">
        Tiếp tục
      </span>
    </Link>
  );
}

/**
 * Thẻ "Tiếp tục xem" Animation — cùng vai trò với `TheTiepTuc`, hình dạng
 * riêng vì series/episode không phải novel/chapter.
 */
function TheTiepTucXem({ muc }: { muc: ContinueWatchItem }) {
  const viTriGiay = muc.position_seconds ?? 0;
  const phanTram = muc.duration_seconds
    ? Math.max(0, Math.min(100, Math.round((viTriGiay / muc.duration_seconds) * 100)))
    : null;

  return (
    <Link href={`/animation/watch/${muc.episode_id}`} className="progress-card">
      <span className="progress-card-icon" aria-hidden="true">
        🎬
      </span>
      <span className="progress-card-body">
        <strong className="clamp-1">{muc.series_title}</strong>
        <span className="progress-card-meta">
          Tập {muc.episode_order_index} · {muc.episode_title} ·{" "}
          {dinhDangGio(viTriGiay)}
          {muc.duration_seconds ? ` / ${dinhDangGio(muc.duration_seconds)}` : ""}
        </span>
        {phanTram !== null ? (
          <ProgressBar percent={phanTram} label={`Đã xem ${phanTram}%`} />
        ) : null}
      </span>
      <span className="btn btn-sm" aria-hidden="true">
        Tiếp tục
      </span>
    </Link>
  );
}

/**
 * HERO — "cổng vào thế giới" (Visual Renaissance Phase 3, xem Visual Bible
 * mục 2 và 15). Giữ `.hero-copy` (khớp `PageHero`/theme hiện tại của
 * `layout.tsx` — Candidate A ra đời trước hệ thống này nên không có, nhưng
 * bỏ đi sẽ mất lớp sương/toả sáng sau chữ dùng nhất quán ở mọi trang khác).
 *
 * SUA so voi Homepage Hub V2: ban truoc nhet CA nut chinh LAN mot hang ba
 * pill lien ket nhanh (Animation/Audio Studio/Cộng đồng) vao Hero — nam CTA
 * dang-nut trong mot man hinh dau. Ba lien ket do gio nam trong luoi
 * `TheGioiCong` ngay duoi day (dieu huong phu duoc "tich hop tinh te hon"
 * thay vi lap lai o Hero) — Hero chi con DUNG MOT hanh dong chinh va MOT
 * hanh dong phu, dung tinh than "one dominant action, one secondary action".
 */
function Hero({ daDangNhap }: { daDangNhap: boolean }) {
  return (
    <section className="hero-v2 rise" aria-labelledby="home-hero-title">
      <div className="hero-copy">
        <span className="pill">
          <span className="pill-dot" aria-hidden="true" />
          Đọc · Nghe · Xem · Sáng tác
        </span>
        <h1 className="hero-v2-title" id="home-hero-title">
          Truyện của cộng đồng, <em>đọc bằng mắt hoặc bằng tai</em>
        </h1>
        <p className="hero-v2-lead">
          Fanfic World là nơi đọc và nghe fanfic tiếng Việt do cộng đồng viết,
          xem Animation từ YouTube, tạo audio bằng giọng đọc tự nhiên, và tham
          gia thảo luận cùng những người viết khác.
        </p>
      </div>
      <div className="row hero-v2-cta">
        {/*
          2026-08-26: Hero LUON nam trong khung nhin dau tien cua trang chu —
          cung nguyen nhan/cung sua nhu 6 muc header (xem NavAuth.tsx): prefetch
          tu dong cho cac lien ket TINH nay gay ra mot luong request nen tang
          lap lai lien tuc. Cac trang dich deu da tinh/prerender nen tat
          prefetch khong lam cham dieu huong that su.
        */}
        <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
          Khám phá truyện
        </Link>
        <Link className="btn btn-outline" href="/studio" prefetch={false}>
          Fanfic Studio
        </Link>
      </div>
      {!daDangNhap ? (
        <p className="hero-v2-guest-hint">
          <Link href="/login" prefetch={false}>Đăng nhập</Link> để lưu tiến độ đọc, nghe và xem.
        </p>
      ) : null}
    </section>
  );
}

/**
 * Khung kính nổi bật đầu trang (Khai thác vùng phải còn trống trên desktop)
 * Hiển thị CÙNG LÚC 2 cột gọn:
 * - Cột 1: Truyện mới (Tối đa 3 tác phẩm thật, ảnh bìa chân dung compact)
 * - Cột 2: Bài đăng mới (Tối đa 3 bài viết thật từ cộng đồng, không dùng thông báo giả)
 */
function HomeHeroShowcase({
  novels,
  communityPosts,
}: {
  novels: Novel[];
  communityPosts: Post[];
}) {
  const danhSachTruyen = novels.slice(0, 3);
  const danhSachBaiDang = communityPosts.slice(0, 3);

  return (
    <div className="home-hero-showcase rise rise-1" aria-label="Tiêu điểm trên Fanfic World">
      <div className="showcase-header">
        <span className="eyebrow">DANH MỤC &amp; TIÊU ĐIỂM</span>
        <span className="hint">Cập nhật trực tiếp</span>
      </div>

      <div className="showcase-dual-cols">
        {/* Cột 1: Truyện mới thật từ cơ sở dữ liệu */}
        <div className="showcase-col">
          <div className="showcase-col-head">
            <div className="showcase-col-title">
              <IconFlame size={16} />
              <strong>Truyện mới</strong>
            </div>
            <Link href="/library" className="showcase-more" prefetch={false}>
              Tất cả →
            </Link>
          </div>
          <div className="showcase-scroll-list">
            {danhSachTruyen.length === 0 ? (
              <div className="hint showcase-empty-hint">
                Đang tải danh mục tác phẩm...
              </div>
            ) : (
              danhSachTruyen.map((n) => {
                const hasAudio = novelHasAudio(n);
                const author = formatAuthor(n);
                const chapterCount = formatChapterCount(n.external_chapter_count);
                const fandom = novelFandom(n);

                return (
                  <Link
                    key={n.novel_id}
                    href={`/novels/${n.novel_id}`}
                    className="showcase-item"
                    prefetch={false}
                  >
                    <div className="showcase-item-cover">
                      <NovelCover
                        novelId={n.novel_id}
                        title={n.title}
                        coverUrl={n.cover_url}
                        size="landscape"
                      />
                    </div>
                    <div className="showcase-item-info">
                      <div className="showcase-item-title clamp-1" title={n.title}>
                        {n.title}
                      </div>
                      <div className="showcase-item-meta clamp-1">
                        <span className="fandom-chip">{fandom}</span>
                        <span className="chapters">{chapterCount}</span>
                        {hasAudio && (
                          <span className="badge badge-brand badge-sm">Audio</span>
                        )}
                      </div>
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </div>

        {/* Vách ngăn ma pháp phân tách 2 cột */}
        <div className="showcase-vertical-divider" aria-hidden="true">
          <span className="showcase-divider-gem" />
        </div>

        {/* Cột 2: Bài đăng mới — Thảo luận thật từ cộng đồng (communityPosts) */}
        <div className="showcase-col">
          <div className="showcase-col-head">
            <div className="showcase-col-title">
              <IconMegaphone size={16} />
              <strong>Bài đăng mới</strong>
            </div>
            <Link href="/community" className="showcase-more" prefetch={false}>
              Xem cộng đồng →
            </Link>
          </div>
          <div className="showcase-scroll-list">
            {danhSachBaiDang.length === 0 ? (
              <div className="hint showcase-empty-hint">
                Chưa có thảo luận mới từ cộng đồng.
              </div>
            ) : (
              danhSachBaiDang.map((bai) => {
                const authorName = bai.author?.display_name || bai.author?.username || "Ẩn danh";
                return (
                  <Link
                    key={bai.post_id}
                    href={`/posts/${bai.post_id}`}
                    className="showcase-item showcase-post-item"
                    prefetch={false}
                  >
                    <Avatar
                      name={authorName}
                      avatarUrl={bai.author?.avatar_url}
                      className="showcase-avatar"
                    />
                    <div className="showcase-item-info">
                      <div className="showcase-post-author clamp-1">
                        <strong className="clamp-1 showcase-update-title" title={authorName}>
                          {authorName}
                        </strong>
                        <span className="hint mono showcase-post-meta">
                          ❤ {bai.like_count} · 💬 {bai.comment_count}
                        </span>
                      </div>
                      <p className="showcase-post-snippet clamp-1" title={bai.text}>
                        {bai.text}
                      </p>
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Dai thanh vien GON (Phan 11 dac ta) — mot dong duy nhat.
 *
 * Da dang nhap: bac/XP/danh xung, giong het dong gamification cua ban V4
 * cu, chi doi vi tri (gio nam SAU hero, truoc "Tiep tuc"). Thieu du lieu
 * (chua tai xong / loi) thi AN het dong nay thay vi ve mot cho trong.
 *
 * Khach vang lai: KHONG hien gi o day — CTA dang nhap da nam trong Hero
 * (`hero-v2-guest-hint`), khong lap lai hai lan tren cung mot man hinh.
 */
function DaiThanhVien({
  gamification,
}: {
  gamification: { progress: OwnProgress; thanhTuuMoiNhat: Achievement | null } | null;
}) {
  if (!gamification) return null;
  return (
    <div className="home-gamification-line rise rise-1">
      <span className="home-gamification-badge">
        <IconCrown size={14} className="home-gamification-icon" />
        <strong>Lv. {gamification.progress.level}</strong>
      </span>
      <span className="home-gamification-xp">
        {gamification.progress.xp}
        {gamification.progress.next_level_xp
          ? `/${gamification.progress.next_level_xp}`
          : ""}{" "}
        XP
      </span>
      <span className="home-gamification-sep" aria-hidden="true">·</span>
      <span className="home-gamification-title">{gamification.progress.equipped_title}</span>
      {gamification.thanhTuuMoiNhat ? (
        <>
          <span className="home-gamification-sep" aria-hidden="true">·</span>
          <span className="home-gamification-achievement">
            Thành tựu: {gamification.thanhTuuMoiNhat.icon} {gamification.thanhTuuMoiNhat.name}
          </span>
        </>
      ) : null}
    </div>
  );
}

/**
 * O trong GON cho mot ke rieng (Phan 8 dac ta: "KHONG ve them mot hop
 * kinh rong 400px"). Chi mot dong icon + chu + (tuy chon) mot nut CTA nho —
 * khac han `EmptyState` (danh cho toan trang, to hon nhieu).
 */
function KeTrongGon({
  icon,
  text,
  action,
}: {
  icon: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="shelf-empty-compact">
      <span aria-hidden="true">{icon}</span>
      <span className="hint">{text}</span>
      {action}
    </div>
  );
}

/**
 * O trong minh hoa CHO RIENG ke "Đang nổi bật" — day la ke QUAN TRONG NHAT
 * cua trang chu nen duoc phep co mot hoa tiet + nut CTA rieng, nhung van nho
 * hon nhieu so voi `EmptyState` (vien dut, padding 48px) dung chung cho toan
 * site — xem `.empty-noibat` o `globals.css`.
 *
 * Phuc hoi tu `feature/fanfic-visual-renaissance-v1` (dat ten class rieng,
 * KHONG dung tien to "portal-" cua ban goc — ban goc dung chung he thong
 * class voi The Gioi Cong, con qua trinh phuc hoi nay CHU DINH khong dong
 * cham den The Gioi Cong, xem bao cao Phase A).
 */
function KeTrongNoiBat() {
  return (
    <div className="empty-noibat">
      <MotifManuscript className="empty-noibat-motif" />
      <span className="empty-noibat-body">
        <strong>Thư viện vẫn còn một chỗ trống.</strong>
        <span className="hint">
          Chưa có truyện nào được xuất bản — chỗ đầu tiên đang chờ tác giả
          đầu tiên.
        </span>
        <Link className="btn btn-primary btn-sm" href="/studio/write" prefetch={false}>
          Viết câu chuyện đầu tiên
        </Link>
      </span>
    </div>
  );
}


/**
 * Series Animation DUY NHAT trong kho — chi mot series thi KHONG con nam lot
 * thom trong mot luoi (`.anim-grid-shelf`), mot the nho co canh trong rat co
 * don, nhu mot carousel bi gay. Dung LAI dung mau "mot muc duy nhat" da co
 * san cho Truyen (`.story-card-featured`, xem `StoryCard.tsx`) thay vi bia
 * mot kieu rieng cho Animation — CUNG mot ngu phap thi giac cho "chi mot thu
 * trong kho" o ca hai khu vuc.
 */
function TheAnimNoiBat({ series }: { series: AnimationSeries }) {
  return (
    <article className="story-card-featured">
      <Link href={`/animation/${series.series_id}`} className="story-card-featured-cover">
        <NovelCover
          novelId={series.series_id}
          title={series.title}
          coverUrl={series.cover_url}
          size="wide"
        />
      </Link>
      <div className="story-card-featured-body">
        <span className="eyebrow">Series mới nhất</span>
        <h3 className="story-card-featured-title">
          <Link href={`/animation/${series.series_id}`}>{series.title}</Link>
        </h3>
        {series.tags && getReaderTags(series, 3).length > 0 ? (
          <div className="story-tags">
            {getReaderTags(series, 3).map((tag) => (
              <span key={tag} className="chip chip-static">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        {series.description ? (
          <p className="hint clamp-2">{series.description}</p>
        ) : null}
        <Link href={`/animation/${series.series_id}`} className="btn btn-primary btn-sm">
          Xem series
        </Link>
      </div>
    </article>
  );
}

/**
 * Mot hang cua "Bảng vàng tuần" — dung LAI nguyen bo lop `.lb-*` cua
 * `HangXepHang` o `app/leaderboard/page.tsx` (cung mot du lieu, cung mot
 * ngu phap hang bang xep hang), bo qua huy hieu vang hang 1-3: hang muc nay
 * la MOT dong xem luot, khong phai ca bang xep hang.
 */
function HangBangVang({ it }: { it: LeaderboardEntry }) {
  return (
    <li className="lb-row">
      <span className="lb-rank" aria-hidden="true">#{it.rank}</span>
      <CosmeticFrame
        cosmetic={it.equipped_cosmetics.find((c) => c.slot === "avatar_frame")}
      >
        <Avatar
          name={it.display_name || it.username || "?"}
          avatarUrl={it.avatar_url}
          className="avatar avatar-sm"
        />
      </CosmeticFrame>
      <span className="lb-info">
        {it.username ? (
          <Link href={`/u/${it.username}`} className="binh-luan-ten">
            {it.display_name || it.username}
          </Link>
        ) : (
          <strong>{it.display_name || "Ẩn danh"}</strong>
        )}
      </span>
      <span className="lb-xp">{it.xp.toLocaleString("vi-VN")} XP</span>
    </li>
  );
}

/**
 * Hang truyen gon cho trang chu. API danh sach khong tra tac gia, so chuong
 * hay luot doc, nen hang chi hien dung cac truong co that: bia, ten, mo ta,
 * the va ngay tao. Ca hang la mot vung bam lon, de quet nhanh hon luoi bia.
 */
function HangTruyenMoi({ novel }: { novel: Novel }) {
  return (
    <Link href={`/novels/${novel.novel_id}`} className="home-story-row">
      <NovelCover
        novelId={novel.novel_id}
        title={novel.title}
        coverUrl={novel.cover_url}
        size="landscape"
      />
      <span className="home-story-row-body">
        <strong className="home-story-row-title clamp-1">{novel.title}</strong>
        {novel.description ? (
          <span className="hint clamp-1">{novel.description}</span>
        ) : null}
        <span className="home-story-row-meta">
          {getReaderTags(novel, 2).map((tag) => (
            <span key={tag} className="chip chip-static">{tag}</span>
          ))}
          <span className="hint">Xuất bản {dinhDangNgay(novel.created_at)}</span>
        </span>
      </span>
      <span className="home-story-row-arrow" aria-hidden="true">→</span>
    </Link>
  );
}

function KhungChoDanhSach() {
  return (
    <div className="home-story-list" role="status" aria-label="Đang tải truyện">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="home-story-row home-story-row-loading" aria-hidden="true">
          <span className="sk home-story-row-cover-sk" />
          <span className="home-story-row-body">
            <span className="sk sk-title" />
            <span className="sk sk-text" />
          </span>
        </div>
      ))}
    </div>
  );
}

export default function HomePage() {
  const { profile } = useSession();
  const daDangNhap = Boolean(profile);

  const load = useCallback(async (): Promise<HomeData> => {
    /*
      SAU nguon DOC LAP, goi SONG SONG trong MOT `Promise.all` — khong phai
      sau request tuan tu. Bon nguon PHU (tiep tuc/gamification/animation/
      cong dong) deu tu `.catch` ve gia tri rong rieng: mot nguon loi KHONG
      duoc keo sap ca trang chu (cung triet ly voi ban V4 cu, mo rong cho hai
      nguon moi).
    */
    const [page, tags, tiepTuc, gam, animRes, feedRes, lbRes] = await Promise.all([
      api.browseNovels({ limit: GRID_COUNT, content_mode: "readable" }),
      api.novelTags(),
      daDangNhap
        ? api.getContinueProgress().catch(() => ({ reading: null, listening: null, watching: null }))
        : Promise.resolve({ reading: null, listening: null, watching: null }),
      daDangNhap
        ? Promise.all([api.getProgress(), api.getAchievements()]).catch(() => null)
        : Promise.resolve(null),
      api.listAnimationSeries({ limit: ANIM_SHELF_COUNT }).catch(() => ({ series: [] })),
      social.feed(FEED_SHELF_COUNT).catch(() => ({ items: [] })),
      api.getLeaderboard("weekly", BANG_VANG_COUNT, 0).catch(() => ({ items: [] })),
    ]);
    const thanhTuuMoiNhat = gam
      ? gam[1].achievements
          .filter((a) => a.unlocked && a.unlocked_at)
          .sort((a, b) => (b.unlocked_at! < a.unlocked_at! ? -1 : 1))[0] ?? null
      : null;
    return {
      novels: page.novels,
      tags: tags.tags,
      animationSeries: animRes.series,
      communityPosts: feedRes.items,
      bangVangTuan: lbRes.items,
      reading: tiepTuc.reading,
      listening: tiepTuc.listening,
      watching: tiepTuc.watching,
      gamification: gam ? { progress: gam[0], thanhTuuMoiNhat } : null,
    };
  }, [daDangNhap]);

  const { data, error, loading, reload } = useAsyncData(load);

  const novels = data?.novels ?? [];
  const animationSeries = data?.animationSeries ?? [];
  const communityPosts = data?.communityPosts ?? [];
  const bangVangTuan = data?.bangVangTuan ?? [];
  const coTiepTuc = Boolean(data?.reading || data?.listening || data?.watching);
  /*
    `.home-secondary-grid` la MOT flex item cua `.page` (co `gap`) — neu ke
    ben trong deu an (dang tai, hoac ca hai nguon that su rong), div bao
    ngoai van chiem mot khe `gap` RONG, y het loi "hop rong choan giua trang"
    ma trang nay tu dat ra la KHONG duoc lam (xem dau tep). Phai an CA khoi
    bao ngoai khi khong co gi de hien, khong chi tung ke ben trong.
  */
  const coKeThuHai = !loading && animationSeries.length > 0;
  /* Cung nguyen tac voi `coKeThuHai`: khong dat cho cho mot cot rong. */
  const coBangVang = !loading && bangVangTuan.length > 0;

  /**
   * Tối giản trang chủ: Ẩn khối truyện trùng lặp ở dưới vì Showcase trên Hero đã hiển thị tab "Truyện mới"
   */
  const HIEN_KE_TRUYEN_DUOI = false;
  /**
   * Tối giản trang chủ: Ẩn phần Tiếp tục theo phản hồi người dùng
   */
  const HIEN_TIEP_TUC = false;

  return (
    // Themed Page Hero — "Ocean Sky": bien+troi+phieu luu, cyan troi la
    // nhan CHINH. Dat o day (khong phai rieng tren .hero-v2) de dong bo voi
    // cach cac trang khac dat theme tren the bao ngoai cung.
    <div className="page" data-hero-theme="home">
      <div className="home-hero-wrap">
        <div className="home-hero-left">
          <Hero daDangNhap={daDangNhap} />
          <DaiThanhVien gamification={data?.gamification ?? null} />
        </div>
        <HomeHeroShowcase novels={novels} communityPosts={communityPosts} />
      </div>

      {/*
        "Tiếp tục" (Phần 6 đặc tả): người đã đăng nhập nhưng CHƯA có gì để
        tiếp tục thấy một dòng onboarding GỌN — KHÔNG phải một khối rỗng to.
        Khách vãng lai không thấy mục này (CTA đăng nhập đã ở Hero).
      */}
      {daDangNhap ? (
        <section className={HIEN_TIEP_TUC ? "stack-2 rise rise-1" : "home-hidden-shelf"} aria-labelledby="home-tiep-tuc">
          <div className="section-head">
            <h2 id="home-tiep-tuc" className="section-title">
              Tiếp tục của bạn
            </h2>
            <Link className="section-more" href="/library" prefetch={false}>
              Thư viện của bạn <span aria-hidden="true">→</span>
            </Link>
          </div>
          {coTiepTuc ? (
            <div className="bento-grid">
              {data?.reading ? <TheTiepTuc kieu="read" muc={data.reading} /> : null}
              {data?.listening ? <TheTiepTuc kieu="listen" muc={data.listening} /> : null}
              {data?.watching ? <TheTiepTucXem muc={data.watching} /> : null}
            </div>
          ) : (
            <KeTrongGon
              icon="📖"
              text="Bạn chưa đọc, nghe hay xem gì để tiếp tục — bắt đầu từ Khám phá hoặc Animation."
            />
          )}
        </section>
      ) : null}

      {HIEN_KE_TRUYEN_DUOI ? (
        <div className="home-divider" aria-hidden="true">
          <CelestialDivider />
        </div>
      ) : null}

      {/*
        Bang bien tap hai cot. DOM dat truyen truoc de mobile/doc man hinh gap
        noi dung chinh truoc; CSS dua thanh vien sang cot trai tren desktop.
      */}
      {HIEN_KE_TRUYEN_DUOI ? (
        <div
          className={`home-editorial-grid rise rise-2${
            coBangVang ? "" : " home-editorial-grid-mot-cot"
          }`}
        >
          <section className="home-editorial-stories stack-2" aria-labelledby="home-noi-bat">
            <div className="section-head">
              <div className="stack-1">
                <h2 className="section-title section-title-icon" id="home-noi-bat">
                  <IconFlame size={20} /> Truyện mới đáng chú ý
                </h2>
                <p className="hint">Sáu truyện vừa xuất bản để bạn chọn nhanh.</p>
              </div>
              <Link href="/fanfic" className="section-more" prefetch={false}>
                Xem tất cả <span aria-hidden="true">→</span>
              </Link>
            </div>
            {loading ? (
            <KhungChoDanhSach />
            ) : error ? (
              <ErrorState message={error} onRetry={reload} />
            ) : novels.length === 0 ? (
              <KeTrongNoiBat />
            ) : (
              <div className="home-story-list">
                {novels.map((novel) => (
                  <HangTruyenMoi key={novel.novel_id} novel={novel} />
                ))}
              </div>
            )}
          </section>

          {coBangVang ? (
            <aside className="home-editorial-members stack-2" aria-labelledby="home-bang-vang">
              <div className="section-head">
                <div className="stack-1">
                  <h2 className="section-title section-title-icon" id="home-bang-vang">
                    <IconCrown size={20} /> Thành viên nổi bật
                  </h2>
                  <p className="hint">Dẫn đầu XP trong tuần này.</p>
                </div>
                <Link href="/leaderboard" className="section-more" aria-label="Xem bảng xếp hạng" prefetch={false}>
                  Xem hết <span aria-hidden="true">→</span>
                </Link>
              </div>
              <ol className="lb-list home-lb-list">
                {bangVangTuan.map((it) => (
                  <HangBangVang key={it.user_id} it={it} />
                ))}
              </ol>
            </aside>
          ) : loading ? (
            <aside className="home-editorial-members stack-2" aria-hidden="true">
              <div className="home-member-loading" role="status" aria-label="Đang tải thành viên">
                {Array.from({ length: 5 }, (_, i) => (
                  <span key={i} className="sk" aria-hidden="true" />
                ))}
              </div>
            </aside>
          ) : null}
        </div>
      ) : null}

      {/*
        Ke "Animation mới" (Phan 8) — DOC LAP voi ke truyen tren: rong thi tu
        an, KHONG lam rong ca trang du kho truyen dang co du lieu (hoac
        nguoc lai).

        Chi MOT series thi KHONG con nam lot thom trong mot luoi
        (`.anim-grid-shelf`) — mot the nho co canh trong rat co don. Dung
        LAI dung mau "mot muc duy nhat" da co san cho Truyen o tren, cung
        mot ngu phap thi giac cho "chi mot thu trong kho" o ca hai khu vuc.
      */}
      {coKeThuHai ? (
      <div className="home-secondary-grid rise rise-2">
      {!loading && animationSeries.length === 1 ? (
        <section className="home-secondary-card stack-2" aria-labelledby="home-animation">
          <div className="section-head">
            <h2 className="section-title section-title-icon" id="home-animation">
              <IconFilm size={20} /> Animation mới
            </h2>
            <Link href="/animation" className="section-more" prefetch={false}>
              Xem tất cả <span aria-hidden="true">→</span>
            </Link>
          </div>
          <TheAnimNoiBat series={animationSeries[0]} />
        </section>
      ) : !loading && animationSeries.length > 1 ? (
        <section className="home-secondary-card stack-2" aria-labelledby="home-animation">
          <div className="section-head">
            <h2 className="section-title section-title-icon" id="home-animation">
              <IconFilm size={20} /> Animation mới
            </h2>
            <Link href="/animation" className="section-more" prefetch={false}>
              Xem tất cả <span aria-hidden="true">→</span>
            </Link>
          </div>
          <div className="anim-grid anim-grid-shelf">
            {animationSeries.map((s) => (
              <Link key={s.series_id} href={`/animation/${s.series_id}`} className="anim-card">
                <NovelCover novelId={s.series_id} title={s.title} coverUrl={s.cover_url} size="card" />
                <span className="anim-card-title">{s.title}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
      </div>
      ) : null}

      {/* Lối tắt — Trung tâm chuyển hướng Truyện, Sách, Âm Nhạc, Studio, Cộng đồng */}
      <section className="home-discovery-strip stack-2" aria-labelledby="home-kham-pha-nhanh">
        <h2 className="section-title section-title-icon" id="home-kham-pha-nhanh">
          <IconCompass size={19} /> Lối tắt
        </h2>
        <div className="home-util-grid" aria-label="Tiện ích nhanh">
          <Link href="/fanfic" className="home-util-card" prefetch={false}>
            <div className="home-util-icon home-util-icon-book">
              <IconBook size={20} />
            </div>
            <div className="home-util-text">
              <strong className="home-util-name">Truyện</strong>
              <span className="home-util-desc">Kho fanfic &amp; chương mới</span>
            </div>
          </Link>
          <Link href="/library?tab=books" className="home-util-card" prefetch={false}>
            <div className="home-util-icon home-util-icon-shelf">
              <IconLibrary size={20} />
            </div>
            <div className="home-util-text">
              <strong className="home-util-name">Sách</strong>
              <span className="home-util-desc">Tủ sách &amp; tuyển tập</span>
            </div>
          </Link>
          <Link href="/entertainment" className="home-util-card" prefetch={false}>
            <div className="home-util-icon home-util-icon-audio">
              <IconHeadphones size={20} />
            </div>
            <div className="home-util-text">
              <strong className="home-util-name">Âm Nhạc</strong>
              <span className="home-util-desc">Fantasy ambient &amp; bài hát</span>
            </div>
          </Link>
          <Link href="/studio" className="home-util-card" prefetch={false}>
            <div className="home-util-icon home-util-icon-studio">
              <IconSparkles size={20} />
            </div>
            <div className="home-util-text">
              <strong className="home-util-name">Studio</strong>
              <span className="home-util-desc">Sáng tác &amp; xuất bản AI</span>
            </div>
          </Link>
          <Link href="/community" className="home-util-card" prefetch={false}>
            <div className="home-util-icon home-util-icon-community">
              <IconUser size={20} />
            </div>
            <div className="home-util-text">
              <strong className="home-util-name">Cộng đồng</strong>
              <span className="home-util-desc">Thảo luận &amp; giao lưu</span>
            </div>
          </Link>
        </div>
      </section>

      {/* Khám phá theo vũ trụ — danh mục fandom sạch cho người đọc, không lặp lại navbar */}
      <section className="home-discovery-strip stack-2" aria-labelledby="home-kham-pha-vu-tru">
        <h2 className="section-title section-title-icon" id="home-kham-pha-vu-tru">
          <IconCompass size={19} /> Khám phá theo vũ trụ
        </h2>
        <div className="story-tags" aria-label="Vũ trụ fanfic">
          <Link href="/fanfic?tag=fandom:One Piece" className="chip" prefetch={false}>
            One Piece
          </Link>
          <Link href="/fanfic?tag=fandom:Naruto" className="chip" prefetch={false}>
            Naruto
          </Link>
          <Link href="/fanfic?q=Conan" className="chip" prefetch={false}>
            Conan
          </Link>
          <Link href="/fanfic?q=Fairy+Tail" className="chip" prefetch={false}>
            Fairy Tail
          </Link>
          <Link href="/fanfic?q=B%C3%B3ng+R%E1%BB%95" className="chip" prefetch={false}>
            Bóng rổ
          </Link>
        </div>
      </section>

      {/*
        Dat o CUOI, sau khi nguoi doc da xem het cac ke. Dat no o tren thi
        thanh ra bao nguoi vua vao rang hay di lam viec — trong khi ho den
        de doc/xem/nghe.
      */}
      <section className="cta-band creator-sanctum-band" aria-labelledby="home-tac-gia">
        <div className="creator-sanctum-hero">
          <div className="creator-sanctum-avatar" aria-hidden="true">
            <IconSparkles size={28} />
          </div>
          <div className="creator-sanctum-body">
            <span className="eyebrow">SÁNG TÁC</span>
            <h2 className="section-title" id="home-tac-gia">
              Dựng nên thế giới của riêng bạn
            </h2>
            <p className="hint">
              Viết truyện, thêm chương, rồi biến câu chữ thành giọng đọc sống động
              và hình ảnh hoạt họa. Tự do kiến tạo vũ trụ fanfic của riêng bạn.
            </p>
            <div className="row creator-sanctum-actions">
              <Link className="btn btn-primary btn-sm" href="/studio/write" prefetch={false}>
                Bắt đầu viết
              </Link>
              <Link className="btn btn-outline btn-sm" href="/studio" prefetch={false}>
                Mở Fanfic Studio
              </Link>
            </div>
          </div>
          <div className="creator-sanctum-plan">
            <span className="badge badge-brand">Khu tác giả</span>
            <span className="hint">
              Bản MVP riêng tư — tự do sáng tác và lưu trữ đám mây.
            </span>
          </div>
        </div>

        <div className="creator-sanctum-grid">
          <Link href="/studio/write" className="creator-feature-card" prefetch={false}>
            <div className="creator-feature-icon-wrap icon-tome">
              <IconBook size={20} />
            </div>
            <div className="creator-feature-text">
              <strong>Soạn thảo & Chương truyện</strong>
              <span>Trình viết mượt mà, lưu nháp đám mây tự động</span>
            </div>
          </Link>

          <Link href="/studio" className="creator-feature-card" prefetch={false}>
            <div className="creator-feature-icon-wrap icon-audio">
              <IconHeadphones size={20} />
            </div>
            <div className="creator-feature-text">
              <strong>Biến chữ thành Giọng đọc</strong>
              <span>Giọng đọc tự nhiên, đa ngữ điệu và cảm xúc</span>
            </div>
          </Link>

          <Link href="/entertainment" className="creator-feature-card" prefetch={false}>
            <div className="creator-feature-icon-wrap icon-anim">
              <IconFilm size={20} />
            </div>
            <div className="creator-feature-text">
              <strong>Hoạt họa & Xuất bản</strong>
              <span>Gắn phụ đề, tạo animation và chia sẻ độc quyền</span>
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}
