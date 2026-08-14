"use client";

/**
 * Trang chu — mat tien cho NGUOI DOC.
 *
 * V4 VISUAL COMPLETION (Phan A/B) — VIET LAI bo cuc, khong chi doi mau:
 *
 *   TRUOC: HomeHero cao gan het man hinh dau tien, ROI DEN mot StoryHero
 *   thu hai (bia+chu chia doi trang) truoc khi toi duoc luoi truyen that.
 *   Hai khoi gioi thieu lien tiep day noi dung that xuong duoi nep gap.
 *
 *   SAU: mot dai gioi thieu GON (mot dong tieu de + nut, khong choan man
 *   hinh), roi toi NGAY module "Tiep tuc" (nguoi da dang nhap) hoac luoi
 *   truyen — khong con StoryHero rieng. Chi con DUY NHAT mot truyen trong
 *   kho thi dung the "featured" (gioi han rong, xem `StoryCard`), khong bia
 *   thanh mot hero nua trang.
 *
 * VE DU LIEU, va day la phan quan trong nhat khi doc file nay:
 *
 * `GET /api/novels` chi sap xep `orderDesc(created_at)` va KHONG nhan tham so
 * sort. Nen "Truyện mới" o day dung nghia la MOI TAO, khong phai moi cap nhat.
 * Goi no la "Mới cập nhật" se la mot lai noi khong dung voi du lieu.
 *
 * Khong co muc "nổi bật", "nghe nhiều" hay "có audio": khong ton tai co
 * featured (SAI: xem tren — "featured" o day la mot BIEN THE HIEN THI khi
 * kho chi co it truyen, khong phai mot truong xep hang), khong ton tai luot
 * nghe theo truyen. `Profile.listened_minutes` la cua NGUOI DUNG chu khong
 * phai cua truyen.
 *
 * "Tiep tuc doc/nghe" KHONG BIA: goi `GET /api/progress/continue`, mot API
 * THAT tra ve con tro CA NHAN da luu (xem `server/main.py`). Nguoi chua
 * dang nhap hoac chua doc/nghe gi thi KHONG thay module nay — an gon,
 * khong ve khung rong.
 */

import Link from "next/link";
import { useCallback } from "react";
import { api, type Achievement, type ContinueItem, type Novel, type OwnProgress } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { StoryCard } from "@/components/StoryCard";
import { EmptyState, ErrorState, ProgressBar, SkeletonCards } from "@/components/ui";
import { IconFlame, IconTag } from "@/components/Icons";

/** So truyen lay ve cho luoi kham pha. */
const GRID_COUNT = 12;

/** So the hien o muc kham pha theo the. Du de goi y, khong du de thanh mot bai tuong. */
const MAX_TAGS = 12;

interface HomeData {
  novels: Novel[];
  tags: string[];
  reading: ContinueItem | null;
  listening: ContinueItem | null;
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
 * Dai gioi thieu GON — mot dong tieu de, khong phai mot man hinh. Nguoi
 * dang nhap khong can nghe lai "day la gi" moi lan ve trang chu, nen tieu
 * de rut lai con mot loi chao; loi vao nhanh cung doi tu hai nut CTA lon
 * (khach vang lai) sang mot lien ket gon toi thu vien cua ho (da dang nhap).
 *
 * `gamification` (V4 visual completion, vong 2, Buoc 12) — MOT dong nho:
 * bac/XP/danh xung, kem thanh tuu moi mo gan nhat neu co. KHONG phai bang
 * dieu khien, khong co thanh tien do rieng o day — muon xem day du thi vao
 * `/account`. Thieu du lieu (chua tai xong / loi) thi AN het dong nay thay
 * vi ve mot cho trong.
 */
function DaiGioiThieu({
  daDangNhap,
  gamification,
}: {
  daDangNhap: boolean;
  gamification: { progress: OwnProgress; thanhTuuMoiNhat: Achievement | null } | null;
}) {
  return (
    <section className="home-intro rise" aria-labelledby="home-intro-title">
      <span className="pill">
        <span className="pill-dot" aria-hidden="true" />
        Đọc và nghe fanfic tiếng Việt
      </span>
      <h1 className="home-intro-title" id="home-intro-title">
        {daDangNhap ? (
          "Chào mừng trở lại"
        ) : (
          <>
            Truyện của cộng đồng, <em>đọc bằng mắt hoặc bằng tai</em>
          </>
        )}
      </h1>
      {daDangNhap ? (
        <Link className="section-more" href="/library">
          Thư viện của bạn <span aria-hidden="true">→</span>
        </Link>
      ) : (
        <div className="row">
          <Link className="btn btn-primary" href="/fanfic">
            Khám phá truyện
          </Link>
          <Link className="btn btn-outline" href="/write">
            Viết truyện của bạn
          </Link>
        </div>
      )}
      {gamification ? (
        <p className="hint home-gamification-line">
          Lv. {gamification.progress.level} ·{" "}
          {gamification.progress.xp}
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
      ) : null}
    </section>
  );
}

export default function HomePage() {
  const { profile } = useSession();
  const daDangNhap = Boolean(profile);

  const load = useCallback(async (): Promise<HomeData> => {
    const [page, tags, tiepTuc, gam] = await Promise.all([
      api.browseNovels({ limit: GRID_COUNT }),
      api.novelTags(),
      daDangNhap
        ? api.getContinueProgress().catch(() => ({ reading: null, listening: null }))
        : Promise.resolve({ reading: null, listening: null }),
      daDangNhap
        ? Promise.all([api.getProgress(), api.getAchievements()]).catch(() => null)
        : Promise.resolve(null),
    ]);
    const thanhTuuMoiNhat = gam
      ? gam[1].achievements
          .filter((a) => a.unlocked && a.unlocked_at)
          .sort((a, b) => (b.unlocked_at! < a.unlocked_at! ? -1 : 1))[0] ?? null
      : null;
    return {
      novels: page.novels,
      tags: tags.tags,
      reading: tiepTuc.reading,
      listening: tiepTuc.listening,
      gamification: gam ? { progress: gam[0], thanhTuuMoiNhat } : null,
    };
  }, [daDangNhap]);

  const { data, error, loading, reload } = useAsyncData(load);

  const novels = data?.novels ?? [];
  const coTiepTuc = Boolean(data?.reading || data?.listening);

  return (
    <div className="page">
      <DaiGioiThieu daDangNhap={daDangNhap} gamification={data?.gamification ?? null} />

      {/* An hoan toan khi chua co gi de tiep tuc — KHONG ve khung rong. */}
      {coTiepTuc ? (
        <section className="stack-2 rise rise-1" aria-labelledby="home-tiep-tuc">
          <h2 className="section-title" id="home-tiep-tuc">
            Tiếp tục
          </h2>
          <div className="bento-grid">
            {data?.reading ? <TheTiepTuc kieu="read" muc={data.reading} /> : null}
            {data?.listening ? <TheTiepTuc kieu="listen" muc={data.listening} /> : null}
          </div>
        </section>
      ) : null}

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
        <section className="rise rise-2" aria-label="Truyện duy nhất hiện có">
          <StoryCard novel={novels[0]} variant="featured" />
        </section>
      ) : (
        <section className="stack-5 rise rise-2" aria-labelledby="home-moi">
          <div className="section-head">
            <h2 className="section-title section-title-icon" id="home-moi">
              <IconFlame size={20} /> Truyện mới
            </h2>
            <Link href="/fanfic" className="section-more">
              Xem tất cả <span aria-hidden="true">→</span>
            </Link>
          </div>
          <div className="story-grid">
            {novels.map((novel) => (
              <StoryCard key={novel.novel_id} novel={novel} />
            ))}
          </div>
        </section>
      )}

      {data && data.tags.length > 0 ? (
        <section className="stack-2" aria-labelledby="home-the">
          <h2 className="section-title section-title-icon" id="home-the">
            <IconTag size={19} /> Khám phá theo thẻ
          </h2>
          <p className="hint">
            Thẻ do chính tác giả đặt khi xuất bản truyện.
          </p>
          <div className="story-tags">
            {data.tags.slice(0, MAX_TAGS).map((tag) => (
              <Link
                key={tag}
                href={`/fanfic?tag=${encodeURIComponent(tag)}`}
                className="chip"
              >
                {tag}
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {/*
        Dat o CUOI, sau khi nguoi doc da xem truyen. Dat no o tren thi thanh ra
        bao nguoi vua vao rang hay di lam viec — trong khi ho den de doc.
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
