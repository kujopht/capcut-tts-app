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
 * "Cộng đồng đang nói gì": `GET /api/feed` — CONG KHAI, khong doi dang nhap
 * (xem docstring `server/main.py::api_feed`) — khach vang lai van thay bang
 * tin kham pha.
 *
 * "Tiếp tục doc/nghe/xem" KHONG BIA: goi `GET /api/progress/continue`, mot
 * API THAT tra ve con tro CA NHAN da luu. Nguoi da dang nhap nhung CHUA
 * doc/nghe/xem gi thi thay mot dong onboarding GON (khong phai mot khoi
 * rong to) — khach vang lai khong thay muc nay (thay vao do la CTA dang
 * nhap rieng, xem `DaiThanhVien`).
 */

import Image from "next/image";
import Link from "next/link";
import { useCallback } from "react";
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
import { Avatar } from "@/components/Avatar";
import { CosmeticFrame } from "@/components/cosmetics/Cosmetics";
import { NovelCover } from "@/components/NovelCover";
import {
  CelestialDivider,
  CornerRune,
  MotifFilmFrame,
  MotifManuscript,
  MotifWaveform,
} from "@/components/Ornaments";
import { ErrorState, ProgressBar } from "@/components/ui";
import {
  IconBook,
  IconCompass,
  IconCrown,
  IconFeather,
  IconFilm,
  IconFlame,
  IconHeadphones,
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
          Khám phá
        </Link>
        <Link className="btn btn-outline" href="/write" prefetch={false}>
          Viết truyện
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
    <p className="hint home-gamification-line rise rise-1">
      Lv. {gamification.progress.level} · {gamification.progress.xp}
      {gamification.progress.next_level_xp
        ? `/${gamification.progress.next_level_xp}`
        : ""}{" "}
      XP · {gamification.progress.equipped_title}
      {gamification.thanhTuuMoiNhat ? (
        <>
          {" "}
          · Thành tựu mới nhất: {gamification.thanhTuuMoiNhat.icon}{" "}
          {gamification.thanhTuuMoiNhat.name}
        </>
      ) : null}
    </p>
  );
}

interface DiemDen {
  href: string;
  icon: React.ReactNode;
  ten: string;
  mota: string;
}

/**
 * BA diem den CHINH — moi diem la mot "cong" rieng, khong phai mot the trong
 * mot hang deu nhau (Visual Renaissance Phase 3, thay `DANH_SACH_TINH_NANG`
 * cu). Thu tu ke ca kich thuoc phan anh dung uu tien san pham: Truyen la ly
 * do chinh nguoi ta den, Animation la san pham thu hai manh nhat, Audio la
 * mot cach tieu thu CHINH Truyen (khong phai mot the ngang hang doc lap).
 */
const DIEM_DEN_CHINH: DiemDen[] = [
  {
    href: "/fanfic",
    icon: <IconBook size={22} />,
    ten: "Truyện",
    mota: "Khám phá fanfic do cộng đồng viết",
  },
  {
    href: "/animation",
    icon: <IconFilm size={19} />,
    ten: "Animation",
    mota: "Xem các series và tập mới",
  },
  {
    href: "/studio",
    icon: <IconHeadphones size={19} />,
    ten: "Audio",
    mota: "Nghe truyện bằng giọng đọc",
  },
];

/** BA diem den VE TINH — nho hon, mot hang gon duoi ba cong chinh. */
const DIEM_DEN_PHU: DiemDen[] = [
  {
    href: "/community",
    icon: <IconMegaphone size={17} />,
    ten: "Cộng đồng",
    mota: "Thảo luận và chia sẻ",
  },
  {
    href: "/write",
    icon: <IconFeather size={17} />,
    ten: "Sáng tác",
    mota: "Viết và xuất bản truyện",
  },
  {
    href: "/image-studio",
    icon: <IconSparkles size={17} />,
    ten: "Image Studio",
    mota: "Tạo hình ảnh cho thế giới của bạn",
  },
];

/**
 * "CHỌN LỐI ĐI CỦA BẠN" — cổng thế giới bất đối xứng (Visual Renaissance
 * Phase 3), thay lưới 6 thẻ đều nhau cũ (`.hub-grid`/`.quick-card`, vẫn còn
 * dùng ở `/account`).
 *
 * Truyện là cổng THỐNG TRỊ (chiếm 2/3 chiều rộng, cao gấp đôi) — đây là lý do
 * chính người dùng đến. Animation/Audio xếp dọc bên phải, nhỏ hơn nhưng vẫn
 * là hai đích đến độc lập. Cộng đồng/Sáng tác/Image Studio là một dải vệ
 * tinh gọn — trên mobile dải này CUỘN NGANG thay vì xếp chồng vô hạn (xem
 * `.portal-satellites` ở `globals.css`).
 *
 * Mỗi cổng có MỘT hoạ tiết SVG nền riêng (`Ornaments.tsx`) để bản sắc đến từ
 * chất liệu/hình ảnh, không chỉ icon+nhãn — đúng yêu cầu "destination art".
 */
function TheGioiCong() {
  return (
    <section className="stack-2 rise rise-1 home-portals" aria-labelledby="home-tinh-nang">
      <h2 className="section-title" id="home-tinh-nang">
        Chọn lối đi của bạn
      </h2>
      {/*
        Ca 6 cong (chinh + ve tinh) LUON trong khung nhin dau tien cua trang
        chu, va deu tro toi trang TINH da prerender — cung ly do tat prefetch
        nhu Hero/header (xem NavAuth.tsx). `prefetch={false}` dat tren TUNG
        the ben duoi, khong phai o day.
      */}
      <div className="portal-primary">
        <Link href={DIEM_DEN_CHINH[0].href} className="portal-card portal-truyen" prefetch={false}>
          <Image
            src="/images/portals/truyen-manuscript.webp"
            alt=""
            fill
            priority
            sizes="(max-width: 900px) 100vw, 66vw"
            className="portal-art"
          />
          <span className="portal-overlay" aria-hidden="true" />
          <CornerRune className="portal-rune" />
          <MotifManuscript className="portal-motif" />
          <span className="portal-body">
            <span className="portal-icon" aria-hidden="true">
              {DIEM_DEN_CHINH[0].icon}
            </span>
            <strong className="portal-title">{DIEM_DEN_CHINH[0].ten}</strong>
            <span className="hint">{DIEM_DEN_CHINH[0].mota}</span>
          </span>
        </Link>
        <div className="portal-stack">
          <Link href={DIEM_DEN_CHINH[1].href} className="portal-card portal-animation" prefetch={false}>
            <Image
              src="/images/portals/animation-projector.webp"
              alt=""
              fill
              loading="eager"
              sizes="(max-width: 900px) 50vw, 33vw"
              className="portal-art"
            />
            <span className="portal-overlay" aria-hidden="true" />
            <MotifFilmFrame className="portal-motif" />
            <span className="portal-body">
              <span className="portal-icon" aria-hidden="true">
                {DIEM_DEN_CHINH[1].icon}
              </span>
              <strong className="portal-title">{DIEM_DEN_CHINH[1].ten}</strong>
              <span className="hint">{DIEM_DEN_CHINH[1].mota}</span>
            </span>
          </Link>
          <Link href={DIEM_DEN_CHINH[2].href} className="portal-card portal-audio" prefetch={false}>
            <MotifWaveform className="portal-motif" />
            <span className="portal-body">
              <span className="portal-icon" aria-hidden="true">
                {DIEM_DEN_CHINH[2].icon}
              </span>
              <strong className="portal-title">{DIEM_DEN_CHINH[2].ten}</strong>
              <span className="hint">{DIEM_DEN_CHINH[2].mota}</span>
            </span>
          </Link>
        </div>
      </div>
      <div className="portal-satellites">
        {DIEM_DEN_PHU.map((d) => (
          <Link key={d.href} href={d.href} className={`portal-satellite portal-sat-${d.href.replace(/\//g, "")}`} prefetch={false}>
            <span className="portal-satellite-icon" aria-hidden="true">
              {d.icon}
            </span>
            <span className="portal-satellite-body">
              <strong>{d.ten}</strong>
              <span className="hint">{d.mota}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
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
        <Link className="btn btn-primary btn-sm" href="/write" prefetch={false}>
          Viết câu chuyện đầu tiên
        </Link>
      </span>
    </div>
  );
}

/** The xem truoc mot bai dang cong dong (Phan 10 dac ta). */
function TheCongDong({ bai }: { bai: Post }) {
  return (
    <Link href={`/posts/${bai.post_id}`} className="community-preview-card">
      <div className="row row-tight">
        <Avatar
          name={bai.author?.display_name || bai.author?.username || "?"}
          avatarUrl={bai.author?.avatar_url}
          className="community-preview-avatar"
        />
        <span className="community-preview-author">
          <strong className="hint">
            {bai.author?.display_name || bai.author?.username || "Ẩn danh"}
          </strong>
          <span className="hint mono community-preview-timestamp">
            {dinhDangNgay(bai.created_at)}
          </span>
        </span>
      </div>
      <p className="clamp-3 community-preview-text">
        {bai.text.length > 140 ? `${bai.text.slice(0, 140)}…` : bai.text}
      </p>
      <span className="hint community-preview-meta">
        ❤ {bai.like_count} · 💬 {bai.comment_count}
      </span>
    </Link>
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
        {series.tags.length > 0 ? (
          <div className="story-tags">
            {series.tags.slice(0, 3).map((tag) => (
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
        size="thumb"
      />
      <span className="home-story-row-body">
        <strong className="home-story-row-title clamp-1">{novel.title}</strong>
        {novel.description ? (
          <span className="hint clamp-1">{novel.description}</span>
        ) : null}
        <span className="home-story-row-meta">
          {novel.tags.slice(0, 2).map((tag) => (
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
      api.browseNovels({ limit: GRID_COUNT }),
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
  const coKeThuHai = !loading && (animationSeries.length > 0 || communityPosts.length > 0);

  return (
    // Themed Page Hero — "Ocean Sky": bien+troi+phieu luu, cyan troi la
    // nhan CHINH. Dat o day (khong phai rieng tren .hero-v2) de dong bo voi
    // cach cac trang khac dat theme tren the bao ngoai cung.
    <div className="page" data-hero-theme="home">
      {/*
        Desktop: gom loi chao va cac diem den vao CUNG mot dai hai cot. Ban
        truoc xep doc hai khoi lon, nen rieng phan dieu huong dau trang da an
        gan tron mot viewport truoc khi nguoi dung thay noi dung that.

        Tablet/mobile tu tro ve mot cot trong CSS; khong doi thu tu DOM, nen
        doc man hinh va dieu huong ban phim van gap Hero truoc cac diem den.
      */}
      <div className="home-entry-grid">
        <div className="home-entry-copy">
          <Hero daDangNhap={daDangNhap} />
          <DaiThanhVien gamification={data?.gamification ?? null} />
        </div>
        <TheGioiCong />
      </div>

      {/*
        "Tiếp tục" (Phần 6 đặc tả): người đã đăng nhập nhưng CHƯA có gì để
        tiếp tục thấy một dòng onboarding GỌN — KHÔNG phải một khối rỗng to.
        Khách vãng lai không thấy mục này (CTA đăng nhập đã ở Hero).
      */}
      {daDangNhap ? (
        <section className="stack-2 rise rise-1" aria-labelledby="home-tiep-tuc">
          <div className="section-head">
            <h2 className="section-title" id="home-tiep-tuc">
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

      <div className="home-divider" aria-hidden="true">
        <CelestialDivider />
      </div>

      {/*
        Bang bien tap hai cot. DOM dat truyen truoc de mobile/doc man hinh gap
        noi dung chinh truoc; CSS dua thanh vien sang cot trai tren desktop.
      */}
      <div className="home-editorial-grid rise rise-2">
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
          {loading ? (
            <div className="home-member-loading" role="status" aria-label="Đang tải thành viên">
              {Array.from({ length: 5 }, (_, i) => (
                <span key={i} className="sk" aria-hidden="true" />
              ))}
            </div>
          ) : bangVangTuan.length > 0 ? (
            <ol className="lb-list home-lb-list">
              {bangVangTuan.map((it) => (
                <HangBangVang key={it.user_id} it={it} />
              ))}
            </ol>
          ) : (
            <KeTrongGon icon="✨" text="Chưa có thành viên ghi XP trong tuần này." />
          )}
        </aside>
      </div>

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

      {/*
        Ke "Cộng đồng đang nói gì" (Phan 10) — `/api/feed` cong khai that,
        khong doi dang nhap. Rong thi AN het, khong bia noi dung.
      */}
      {!loading && communityPosts.length > 0 ? (
        <section className="home-secondary-card stack-2" aria-labelledby="home-cong-dong">
          <div className="section-head">
            <h2 className="section-title section-title-icon" id="home-cong-dong">
              <IconMegaphone size={20} /> Cộng đồng đang nói gì
            </h2>
            <Link href="/community" className="section-more" prefetch={false}>
              Xem cộng đồng <span aria-hidden="true">→</span>
            </Link>
          </div>
          <div className="community-preview-grid">
            {communityPosts.map((bai) => (
              <TheCongDong key={bai.post_id} bai={bai} />
            ))}
          </div>
        </section>
      ) : null}
      </div>
      ) : null}

      {/* Gom loi tat va the that vao mot dai, thay vi hai section xep doc. */}
      <section className="home-discovery-strip stack-2" aria-labelledby="home-kham-pha-nhanh">
        <h2 className="section-title section-title-icon" id="home-kham-pha-nhanh">
          <IconCompass size={19} /> Khám phá nhanh
        </h2>
        <div className="home-discovery-groups">
          <div className="story-tags">
            <Link href="/fanfic" className="chip" prefetch={false}>
              <IconBook size={13} /> Truyện mới
            </Link>
            <Link href="/animation" className="chip" prefetch={false}>
              <IconFilm size={13} /> Animation
            </Link>
            <Link href="/community" className="chip" prefetch={false}>
              <IconUser size={13} /> Cộng đồng
            </Link>
          </div>
          {data && data.tags.length > 0 ? (
            <div className="story-tags" aria-label="Thẻ truyện">
              <span className="home-discovery-label"><IconTag size={14} /> Thẻ:</span>
              {data.tags.slice(0, MAX_TAGS).map((tag) => (
                <Link key={tag} href={`/fanfic?tag=${encodeURIComponent(tag)}`} className="chip">
                  {tag}
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      </section>

      {/*
        Dat o CUOI, sau khi nguoi doc da xem het cac ke. Dat no o tren thi
        thanh ra bao nguoi vua vao rang hay di lam viec — trong khi ho den
        de doc/xem/nghe.
      */}
      <section className="cta-band" aria-labelledby="home-tac-gia">
        <Image
          src="/images/portals/creator-worldbuilding.webp"
          alt=""
          fill
          loading="lazy"
          sizes="100vw"
          className="cta-band-art"
        />
        <span className="cta-band-overlay" aria-hidden="true" />
        <div className="cta-band-body">
          <h2 className="section-title" id="home-tac-gia">
            Dựng nên thế giới của riêng bạn
          </h2>
          <p className="hint">
            Viết truyện, thêm chương, rồi biến chữ thành giọng đọc và hình
            ảnh. Truyện để ở bản nháp cho tới khi bạn tự xuất bản.
          </p>
        </div>
        <div className="row">
          <Link className="btn btn-primary" href="/write" prefetch={false}>
            Bắt đầu viết
          </Link>
          <Link className="btn" href="/studio" prefetch={false}>
            Thử Audio Studio
          </Link>
        </div>
      </section>
    </div>
  );
}
