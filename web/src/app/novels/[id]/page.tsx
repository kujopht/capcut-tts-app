/**
 * Chi tiet truyen: thong tin, nut hanh dong theo tien do, muc luc.
 *
 * PRODUCT UX SPRINT 2:
 * - Anh nen rong (hero) CHI khi truyen co `hero_background_url` that. Ban
 *   truoc roi ve bia DOC va keo gian no lam nen — mot bia 2:3 phong to thanh
 *   16:9 roi lam mo trong nhu anh hong. Khong co hero thi nen tinh.
 * - Nut chinh doi theo tien do (`NovelPrimaryCta`): Bắt đầu đọc / Đọc tiếp /
 *   Nghe tiếp / Tiếp tục đọc & nghe, mo DUNG chuong dang do. "Theo dõi" la nut
 *   PHU (vien), khong con tim dac canh tranh voi nut doc.
 * - Nhan khong day ten truyen xuong: bo nhan "Đã xuất bản" (trang cong khai
 *   thi truyen nao cung da xuat ban — chi con nhan "Bản nháp" khi dung), the
 *   the loai (toi da 4) xuong DUOI mo ta, fandom la lien ket ve Thu vien.
 * - Mo ta dai thu gon 4 dong + "Xem thêm".
 * - Muc luc tim duoc, dao thu tu duoc, danh dau chuong dang/da doc.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { API_BASE, api, ApiError, type Chapter, type Novel } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import {
  EmptyState,
  ErrorState,
} from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";
import { NovelCover } from "@/components/NovelCover";
import { FollowButton } from "@/components/FollowButton";
import {
  NovelOwnerActions,
  OwnerAddChapterAction,
} from "@/components/NovelInteractiveActions";
import { fandomCauTruc, theChoThe } from "@/lib/taxonomy";
import { novelPortraitUrl, isLegacyAudioOnly } from "@/lib/catalog";
import { IconHeadphones } from "@/components/Icons";
import { NovelPrimaryCta, type LienKetBatDau } from "@/components/novel/NovelPrimaryCta";
import { NovelDescription } from "@/components/novel/NovelDescription";
import { ChapterList } from "@/components/novel/ChapterList";

/**
 * Dynamic metadata cho SEO, OpenGraph (book), Twitter card va canonical URL.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const res = await fetch(`${API_BASE}/api/novels/${encodeURIComponent(id)}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) throw new Error("not found");
    const data = await res.json();
    const novel: Novel = data.novel;
    const title = `${novel.title} | Fanfic World`;
    const description = novel.description
      ? novel.description.slice(0, 160)
      : `Đọc truyện fanfic ${novel.title} trên Fanfic World.`;
    const canonical = `https://fanfic.world/novels/${novel.novel_id}`;
    const images = novel.cover_url ? [novel.cover_url] : [];

    return {
      title,
      description,
      alternates: { canonical },
      openGraph: {
        title,
        description,
        url: canonical,
        siteName: "Fanfic World",
        type: "book",
        images,
      },
      twitter: {
        card: "summary_large_image",
        title,
        description,
        images,
      },
    };
  } catch {
    return {
      title: "Chi tiết truyện | Fanfic World",
      description: "Đọc truyện fanfic tiếng Việt và audio tại Fanfic World.",
    };
  }
}

/**
 * Tien do tac pham -> nhan tieng Viet.
 *
 * Gia tri khong nam trong bang thi TRA VE NGUYEN VAN, khong doi thanh "Khac"
 * hay chuoi rong: backend co the them trang thai moi truoc frontend, va luc do
 * hien dung chu cua backend van dung hon la giau no di.
 */
const NHAN_TIEN_DO: Record<string, string> = {
  ongoing: "Đang ra",
  completed: "Hoàn thành",
  hiatus: "Tạm ngưng",
  abandoned: "Đã bỏ",
};

function nhanTienDo(status: string): string {
  return NHAN_TIEN_DO[status] ?? status;
}

/** Ten tac gia hien duoc; "Unknown Author" / rong thi an (khong bia ten). */
function tacGiaThat(raw?: string | null): string | null {
  const s = (raw ?? "").trim();
  if (!s || /^(unknown|unknown author|anonymous|n\/a)$/i.test(s)) return null;
  return s;
}

export default async function NovelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let data: {
    novel: Novel;
    chapters: Chapter[];
    follow?: { following: boolean; follower_count: number };
  } | null = null;
  let missing = false;
  let errorMsg = "";

  try {
    data = await api.getNovel(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      missing = true;
    } else {
      errorMsg = errorMessage(err);
    }
  }

  const novel: Novel | null = data?.novel ?? null;
  const chapters: Chapter[] = data?.chapters ?? [];

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy truyện này"
          hint="Truyện có thể đã bị xoá hoặc chưa được xuất bản."
          action={
            <Link className="btn btn-primary" href="/library" prefetch={false}>
              Về Thư viện
            </Link>
          }
        />
      </div>
    );
  }

  if (errorMsg || !novel) {
    return (
      <div className="page">
        <nav aria-label="Đường dẫn">
          <Link href="/library" className="hint crumb" prefetch={false}>
            ← Thư viện
          </Link>
        </nav>
        <ErrorState message={errorMsg || "Không tải được truyện."} />
      </div>
    );
  }

  const isOwner = false;
  // `has_audio` da co san trong danh sach chuong (xem ghi chu o `fetchNovel`),
  // nen tong hop nay khong ton them request nao.
  const soChuongCoAudio = chapters.filter((c) => c.has_audio).length;
  const chiAudio = isLegacyAudioOnly(novel);
  // Fandom CO CAU TRUC (fandom_ids / the) — dung cai bo loc Thu vien hieu,
  // nen lien ket "Naruto" o day mo dung danh sach Naruto.
  const fandom = fandomCauTruc(novel);
  const tacGia = tacGiaThat(novel.external_author_name);
  // Toi da BON the the loai, bo the trung voi fandom (fandom co chip rieng).
  const theLoai = theChoThe(novel, 4, [fandom]);
  // Anh nen rong CHI tu hero 16:9 that — khong keo gian bia doc lam nen.
  const heroThat = novel.hero_background_url || null;

  /*
    Lien ket BAT DAU dung tham so ma trang chuong Sprint 1 hieu
    (`readerSession.cheDoKhiMo`): `mode` quyet dinh bo cuc, `autoplay=1` xin
    phat ngay (nguoi doc vua bam nut — trinh duyet cho phep).
  */
  const dau = chapters[0]?.chapter_id;
  const batDau: LienKetBatDau | null = !dau
    ? null
    : chiAudio
      ? { href: `/chapters/${dau}?mode=listen&autoplay=1`, nhan: "Bắt đầu nghe", nghe: true }
      : { href: `/chapters/${dau}?mode=read`, nhan: "Bắt đầu đọc", nghe: false };
  const batDauPhu: LienKetBatDau | null =
    dau && !chiAudio && soChuongCoAudio > 0
      ? { href: `/chapters/${dau}?mode=read_listen&autoplay=1`, nhan: "Đọc & nghe", nghe: true }
      : null;

  return (
    <div className="page novel-page">
      <nav aria-label="Đường dẫn">
        <Link href="/library" className="hint crumb" prefetch={false}>
          ← Thư viện
        </Link>
      </nav>

      {/*
        Bia va chu nam CANH nhau tren man hinh rong, chong len nhau o mobile
        (xem `.novel-head`). Ban cu xep bia 16:6 nam tren roi chu ben duoi: o
        desktop, bia rong 1180px chiem gan het man hinh dau tien va day ten
        truyen xuong duoi nep gap.
      */}
      <header className={`novel-head${heroThat ? " has-hero" : ""}`}>
        {heroThat ? (
          <>
            <div
              className="novel-head-backdrop"
              style={{ backgroundImage: `url("${heroThat}")` }}
              aria-hidden="true"
            />
            <div className="novel-head-overlay" aria-hidden="true" />
          </>
        ) : null}

        <div className="novel-head-cover">
          <NovelCover
            novelId={novel.novel_id}
            title={novel.title}
            coverUrl={novelPortraitUrl(novel)}
            size="portrait"
          />
        </div>

        <div className="stack-2 novel-head-body">
          {/* Dong nho TREN ten: fandom (lien ket ve Thu vien) + tien do tac
              pham. Nhan the loai xuong duoi mo ta — khong day ten xuong. */}
          <div className="row novel-head-kicker">
            {fandom ? (
              <Link
                href={`/library?fandom=${encodeURIComponent(fandom)}`}
                className="novel-kicker-fandom"
                prefetch={false}
              >
                {fandom}
              </Link>
            ) : null}
            {/*
              Tien do TAC PHAM (`status`), khac han trang thai XUAT BAN
              (`state`): mot truyen da hoan thanh van co the dang la ban nhap.
              Trang cong khai chi hien `state` khi no la BAN NHAP — "Đã xuất
              bản" dung o moi truyen cong khai thi khong noi gi.
            */}
            {novel.status ? (
              <span className={`novel-kicker-status status-${novel.status}`}>{nhanTienDo(novel.status)}</span>
            ) : null}
            {novel.state !== "published" ? <span className="badge badge-warn">Bản nháp</span> : null}
          </div>
          <h1 className="page-title novel-title">{novel.title}</h1>

          {/*
            GHI CONG NGUON. Kho nay chua fanfic NHAP tu noi khac, nen ten tac
            gia goc va duong ve nguon khong phai "metadata cho dep" — do la dieu
            toi thieu phai hien.

            `nofollow` tren lien ket ngoai: day la link do nguoi nhap dat, khong
            phai mot su gioi thieu cua Fanfic World.
          */}
          <p className="novel-facts">
            {tacGia ? (
              <span>
                Tác giả gốc: <strong>{novel.external_author_name}</strong>
              </span>
            ) : null}
            <span>{formatNumber(chapters.length)} chương</span>
            {soChuongCoAudio > 0 ? (
              <span className="novel-fact-audio">
                <IconHeadphones size={14} />{" "}
                {soChuongCoAudio === chapters.length ? "Có audio mọi chương" : `${soChuongCoAudio} chương có audio`}
              </span>
            ) : null}
            <span>Cập nhật {formatDate(novel.updated_at)}</span>
            {novel.language ? <span>Ngôn ngữ gốc: {novel.language}</span> : null}
            {novel.external_source_url ? (
              <a
                href={novel.external_source_url}
                target="_blank"
                rel="noopener noreferrer nofollow"
              >
                Nguồn gốc ↗
              </a>
            ) : null}
          </p>

          {/*
            Nguon cong bo NHIEU chuong hon so dang co o day. KHONG che con so
            nay va cung khong "hoa giai" hai con so: mot ban nhap moi nhap duoc
            15/60 chuong la su that ma nguoi doc can biet truoc khi bat dau.
          */}
          {novel.external_chapter_count > 0 &&
          novel.external_chapter_count !== chapters.length ? (
            <span className="hint">
              Nguồn công bố {formatNumber(novel.external_chapter_count)} chương
            </span>
          ) : null}

          <div className="row novel-head-actions">
            {batDau ? (
              <NovelPrimaryCta
                novelId={novel.novel_id}
                coAudio={soChuongCoAudio > 0}
                chiAudio={chiAudio}
                chuong={chapters.map((c) => ({ id: c.chapter_id, tieuDe: c.title }))}
                batDau={batDau}
                phu={batDauPhu}
              />
            ) : null}
            <NovelOwnerActions ownerId={novel.owner_id} />
            {/*
              Theo dõi truyện — để được thông báo khi có chương mới. Nút PHỤ:
              đọc mới là việc chính ở trang này.

              KHÔNG hiện với chủ sở hữu: một tác giả tự theo dõi truyện của mình
              thì backend cũng không gửi thông báo (xem `notify_new_chapter`),
              nên cái nút đó là một lời hứa suông.

              Cũng không hiện với bản nháp: `data.follow` chỉ có mặt với truyện
              đã xuất bản, nên phép kiểm này đi theo đúng sự thật của backend
              thay vì đoán lại nó ở đây.
            */}
            {!isOwner && data?.follow ? (
              <FollowButton
                kind="story"
                targetId={novel.novel_id}
                initialFollowing={data.follow.following}
                initialCount={data.follow.follower_count}
                label="Theo dõi truyện"
                phu
              />
            ) : null}
          </div>

          <NovelDescription text={novel.description || "Chưa có mô tả."} />

          {theLoai.length > 0 ? (
            <ul className="novel-tags" aria-label="Thể loại">
              {theLoai.map((tag) => (
                <li key={tag}>{tag}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </header>

      <section className="stack" aria-labelledby="novel-toc-h">
        <div className="novel-toc-head">
          <h2 className="section-title" id="novel-toc-h">
            Danh sách chương
          </h2>
          <span className="hint">{formatNumber(chapters.length)} chương</span>
        </div>
        {chapters.length === 0 ? (
          <EmptyState
            icon="📄"
            title="Truyện chưa có chương nào"
            action={<OwnerAddChapterAction ownerId={novel.owner_id} />}
          />
        ) : (
          <ChapterList
            novelId={novel.novel_id}
            chapters={chapters.map((c) => ({
              chapter_id: c.chapter_id,
              title: c.title,
              char_count: c.char_count,
              has_audio: c.has_audio,
              audio_outdated: c.audio_outdated,
            }))}
          />
        )}
      </section>
    </div>
  );
}
