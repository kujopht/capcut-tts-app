"use client";

/**
 * Trang chu — Fanfic World HUB (V2, Homepage Hub + Search Glow).
 *
 * TRUOC (V4 visual completion): mot dai gioi thieu gon roi thang toi luoi
 * truyen — hop ly khi kho chi co truyen, nhung tro thanh MOT trang landing
 * truyen don le. `published_novels == 0` thi ca trang chi con lai hero +
 * MOT hop "Chưa có truyện nào được xuất bản" chiem giua man hinh.
 *
 * SAU: trang chu la mot HUB gom nhieu module DOC LAP — hero gon, luoi tinh
 * nang (6 khu vuc), roi cac "ke" noi dung rieng cho Truyen/Animation/Cong
 * dong. Moi ke tu quyet dinh AN minh neu nguon du lieu cua no rong — trang
 * KHONG BAO GIO chi con mot hop rong choan giua man hinh nua, du kho truyen
 * co rong that.
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

import Link from "next/link";
import { useCallback } from "react";
import {
  api,
  social,
  type Achievement,
  type AnimationSeries,
  type ContinueItem,
  type ContinueWatchItem,
  type Novel,
  type OwnProgress,
  type Post,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { StoryCard } from "@/components/StoryCard";
import { Avatar } from "@/components/Avatar";
import { NovelCover } from "@/components/NovelCover";
import { MotifWaveArcs } from "@/components/Ornaments";
import { EmptyState, ErrorState, ProgressBar, SkeletonCards } from "@/components/ui";
import {
  IconBook,
  IconCompass,
  IconFeather,
  IconFilm,
  IconFlame,
  IconHeadphones,
  IconMegaphone,
  IconSparkles,
  IconTag,
  IconUser,
} from "@/components/Icons";

/** So truyen lay ve cho ke "Đang nổi bật". */
const GRID_COUNT = 12;
/** So the hien o muc kham pha theo the. Du de goi y, khong du de thanh mot bai tuong. */
const MAX_TAGS = 12;
/** So series lay ve cho ke "Animation mới" — gon, khong canh tranh voi ke truyen. */
const ANIM_SHELF_COUNT = 6;
/** So bai dang lay ve cho o xem truoc cong dong — "2–4 the" theo dac ta. */
const FEED_SHELF_COUNT = 4;

interface HomeData {
  novels: Novel[];
  tags: string[];
  animationSeries: AnimationSeries[];
  communityPosts: Post[];
  reading: ContinueItem | null;
  listening: ContinueItem | null;
  watching: ContinueWatchItem | null;
  gamification: { progress: OwnProgress; thanhTuuMoiNhat: Achievement | null } | null;
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
 * HERO (Phần 5 đặc tả) — giữ bản sắc fantasy/anime + nền hiện có
 * (`PageBackground`, xem `layout.tsx`), nhưng rút gọn xuống một vùng nội
 * dung hữu ích thay vì một khối trống gần hết màn hình đầu tiên.
 */
function Hero({ daDangNhap }: { daDangNhap: boolean }) {
  return (
    <section className="hero-v2 rise" aria-labelledby="home-hero-title">
      <MotifWaveArcs className="hero-v2-motif" />
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
        <Link className="btn btn-primary" href="/fanfic">
          Khám phá
        </Link>
        <Link className="btn btn-outline" href="/write">
          Viết truyện
        </Link>
      </div>
      <div className="row hero-v2-secondary" aria-label="Lối tắt nhanh">
        <Link className="hero-v2-pill" href="/animation">
          <IconFilm size={15} /> Animation
        </Link>
        <Link className="hero-v2-pill" href="/studio">
          <IconHeadphones size={15} /> Audio Studio
        </Link>
        <Link className="hero-v2-pill" href="/community">
          <IconMegaphone size={15} /> Cộng đồng
        </Link>
      </div>
      {!daDangNhap ? (
        <p className="hero-v2-guest-hint">
          <Link href="/login">Đăng nhập</Link> để lưu tiến độ đọc, nghe và xem.
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

interface TinhNang {
  href: string;
  icon: React.ReactNode;
  ten: string;
  mota: string;
}

/** Luoi tinh nang (Phan 7 dac ta) — CHI tro toi cac duong da co that. */
const DANH_SACH_TINH_NANG: TinhNang[] = [
  {
    href: "/fanfic",
    icon: <IconBook size={19} />,
    ten: "Truyện",
    mota: "Khám phá fanfic cộng đồng",
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
  {
    href: "/community",
    icon: <IconMegaphone size={19} />,
    ten: "Cộng đồng",
    mota: "Thảo luận và chia sẻ",
  },
  {
    href: "/write",
    icon: <IconFeather size={19} />,
    ten: "Sáng tác",
    mota: "Viết và xuất bản truyện",
  },
  {
    href: "/image-studio",
    icon: <IconSparkles size={19} />,
    ten: "Image Studio",
    mota: "Tạo hình ảnh cho thế giới của bạn",
  },
];

function LuoiTinhNang() {
  return (
    <section className="stack-2 rise rise-1" aria-labelledby="home-tinh-nang">
      <h2 className="section-title" id="home-tinh-nang">
        Khám phá Fanfic World
      </h2>
      <div className="hub-grid">
        {DANH_SACH_TINH_NANG.map((t) => (
          <Link key={t.href} className="quick-card" href={t.href}>
            <span className="quick-icon" aria-hidden="true">
              {t.icon}
            </span>
            <strong>{t.ten}</strong>
            <span className="hint">{t.mota}</span>
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
    const [page, tags, tiepTuc, gam, animRes, feedRes] = await Promise.all([
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
  const coTiepTuc = Boolean(data?.reading || data?.listening || data?.watching);

  return (
    // Themed Page Hero — "Ocean Sky": bien+troi+phieu luu, cyan troi la
    // nhan CHINH. Dat o day (khong phai rieng tren .hero-v2) de dong bo voi
    // cach cac trang khac dat theme tren the bao ngoai cung.
    <div className="page" data-hero-theme="home">
      <Hero daDangNhap={daDangNhap} />
      <DaiThanhVien gamification={data?.gamification ?? null} />

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
            <Link className="section-more" href="/library">
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

      <LuoiTinhNang />

      {/* Ke "Đang nổi bật" — moi tao gan day nhat trong kho truyen (Phan 8). */}
      <section className="stack-5 rise rise-2" aria-labelledby="home-noi-bat">
        <div className="section-head">
          <h2 className="section-title section-title-icon" id="home-noi-bat">
            <IconFlame size={20} /> Đang nổi bật
          </h2>
          <Link href="/fanfic" className="section-more">
            Xem tất cả <span aria-hidden="true">→</span>
          </Link>
        </div>
        {loading ? (
          <SkeletonCards count={6} />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : novels.length === 0 ? (
          <EmptyState
            icon="📚"
            title="Chưa có truyện nào được xuất bản"
            hint="Khi có tác giả xuất bản truyện đầu tiên, nó sẽ xuất hiện ở đây. Trong lúc chờ, bạn có thể tự viết chương đầu tiên."
            action={
              <Link className="btn btn-primary" href="/write">
                Viết truyện đầu tiên
              </Link>
            }
          />
        ) : novels.length === 1 ? (
          // CHI mot truyen trong ca kho: mot the noi bat gioi han rong, KHONG
          // phai mot hero choan nua trang cho mot du lieu duy nhat.
          <StoryCard novel={novels[0]} variant="featured" />
        ) : (
          <div className="story-grid">
            {novels.map((novel) => (
              <StoryCard key={novel.novel_id} novel={novel} />
            ))}
          </div>
        )}
      </section>

      {/*
        Ke "Animation mới" (Phan 8) — DOC LAP voi ke truyen tren: rong thi tu
        an, KHONG lam rong ca trang du kho truyen dang co du lieu (hoac
        nguoc lai).
      */}
      {!loading && animationSeries.length > 0 ? (
        <section className="stack-2 rise rise-2" aria-labelledby="home-animation">
          <div className="section-head">
            <h2 className="section-title section-title-icon" id="home-animation">
              <IconFilm size={20} /> Animation mới
            </h2>
            <Link href="/animation" className="section-more">
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
        <section className="stack-2 rise rise-2" aria-labelledby="home-cong-dong">
          <div className="section-head">
            <h2 className="section-title section-title-icon" id="home-cong-dong">
              <IconMegaphone size={20} /> Cộng đồng đang nói gì
            </h2>
            <Link href="/community" className="section-more">
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

      {/* Kham pha theo the (Phan 9) — chi hien khi kho truyen co the that. */}
      {data && data.tags.length > 0 ? (
        <section className="stack-2" aria-labelledby="home-the">
          <h2 className="section-title section-title-icon" id="home-the">
            <IconTag size={19} /> Khám phá theo thẻ
          </h2>
          <p className="hint">Thẻ do chính tác giả đặt khi xuất bản truyện.</p>
          <div className="story-tags">
            {data.tags.slice(0, MAX_TAGS).map((tag) => (
              <Link key={tag} href={`/fanfic?tag=${encodeURIComponent(tag)}`} className="chip">
                {tag}
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {/* Kham pha nhanh theo khu vuc (Phan 9) — luon hien, khong phu thuoc du lieu. */}
      <section className="stack-2" aria-labelledby="home-kham-pha-nhanh">
        <h2 className="section-title section-title-icon" id="home-kham-pha-nhanh">
          <IconCompass size={19} /> Khám phá theo
        </h2>
        <div className="story-tags">
          <Link href="/fanfic" className="chip">
            <IconBook size={13} /> Truyện mới
          </Link>
          <Link href="/animation" className="chip">
            <IconFilm size={13} /> Animation
          </Link>
          <Link href="/community" className="chip">
            <IconUser size={13} /> Cộng đồng
          </Link>
        </div>
      </section>

      {/*
        Dat o CUOI, sau khi nguoi doc da xem het cac ke. Dat no o tren thi
        thanh ra bao nguoi vua vao rang hay di lam viec — trong khi ho den
        de doc/xem/nghe.
      */}
      <section className="cta-band" aria-labelledby="home-tac-gia">
        <div className="cta-band-body">
          <h2 className="section-title" id="home-tac-gia">
            Bạn cũng viết fanfic?
          </h2>
          <p className="hint">
            Tạo truyện, thêm chương, rồi tạo audio bằng giọng đọc tiếng Việt.
            Truyện để ở bản nháp cho tới khi bạn tự xuất bản.
          </p>
        </div>
        <div className="row">
          <Link className="btn btn-primary" href="/write">
            Bắt đầu viết
          </Link>
          <Link className="btn" href="/studio">
            Thử Audio Studio
          </Link>
        </div>
      </section>
    </div>
  );
}
