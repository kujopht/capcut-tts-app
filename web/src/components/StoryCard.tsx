/**
 * The truyen dung chung cho trang chu va trang Kham pha.
 *
 * CHI hien nhung gi `Novel` THAT SU co: `cover_url`, `title`, `tags`,
 * `description`, `updated_at`. Ba thu mot the truyen thuong co ma o day KHONG
 * co, va deu vi ly do o backend chu khong phai vi quen:
 *
 *   * ten tac gia — `Novel` chi mang `owner_id`, va khong co endpoint nao doi
 *     `user_id` sang ten hien thi;
 *   * so chuong — `GET /api/novels` khong tra ve, chi `getNovel` tung truyen
 *     moi co, tuc la mot request moi the (N+1). `tests/correctness-scale`
 *     dang khoa lai chinh cho do;
 *   * luot nghe / luot xem — khong ton tai o bat ky bang nao.
 *
 * Bia dat o tren cung va chiem phan lon chieu cao: day la giao dien de DOC
 * truyen, va bia la thu nguoi doc quet mat qua truoc tien.
 */

import Link from "next/link";
import type { Novel } from "@/lib/api";
import { NovelCover } from "@/components/NovelCover";
import { formatDate } from "@/components/ui";

/** So the toi da hien tren mot the. Nhieu hon thi the truyen thanh dam the. */
const MAX_TAGS = 3;

/**
 * Ba muc do, CUNG mot du lieu `Novel` — khong co bien the rieng nao bia them
 * truong. Thay `StoryHero` cu (V4 visual completion, Phan E): "featured"
 * KHONG phai mot hero nua chieu trang, chi la mot the noi bat, gioi han rong
 * toi da, de mot truyen duy nhat trong kho khong bi thoi phong thanh nua
 * man hinh.
 *
 *   compact   — the nho, dung o dai/rail (vd sidebar, "co the ban thich")
 *   standard  — the luoi mac dinh (kham pha, trang chu)
 *   featured  — noi bat mot the, gioi han `max-width`, co nut hanh dong
 */
export type StoryCardVariant = "compact" | "standard" | "featured";

export function StoryCard({
  novel,
  variant = "standard",
}: {
  novel: Novel;
  variant?: StoryCardVariant;
}) {
  if (variant === "compact") {
    return (
      <Link
        href={`/novels/${novel.novel_id}`}
        className="story-card story-card-compact"
      >
        <NovelCover
          novelId={novel.novel_id}
          title={novel.title}
          coverUrl={novel.cover_url}
          size="card"
        />
        <div className="story-body">
          <h3 className="story-title clamp-1">{novel.title}</h3>
          <span className="story-meta">Cập nhật {formatDate(novel.updated_at)}</span>
        </div>
      </Link>
    );
  }

  if (variant === "featured") {
    return (
      <article className="story-card-featured">
        <Link href={`/novels/${novel.novel_id}`} className="story-card-featured-cover">
          <NovelCover
            novelId={novel.novel_id}
            title={novel.title}
            coverUrl={novel.cover_url}
            size="wide"
          />
        </Link>
        <div className="story-card-featured-body">
          <span className="eyebrow">Truyện mới nhất</span>
          <h3 className="story-card-featured-title">
            <Link href={`/novels/${novel.novel_id}`}>{novel.title}</Link>
          </h3>
          {novel.tags.length > 0 ? (
            <div className="story-tags">
              {novel.tags.slice(0, MAX_TAGS).map((tag) => (
                <span key={tag} className="chip chip-static">
                  {tag}
                </span>
              ))}
            </div>
          ) : null}
          {novel.description ? (
            <p className="hint clamp-2">{novel.description}</p>
          ) : null}
          <Link href={`/novels/${novel.novel_id}`} className="btn btn-primary btn-sm">
            Đọc truyện
          </Link>
        </div>
      </article>
    );
  }

  return (
    <Link href={`/novels/${novel.novel_id}`} className="story-card">
      <NovelCover
        novelId={novel.novel_id}
        title={novel.title}
        coverUrl={novel.cover_url}
        size="card"
      />
      <div className="story-body">
        <h3 className="story-title clamp-2">{novel.title}</h3>
        {novel.tags.length > 0 ? (
          <div className="story-tags">
            {novel.tags.slice(0, MAX_TAGS).map((tag) => (
              <span key={tag} className="chip chip-static">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        {novel.description ? (
          <p className="hint clamp-2">{novel.description}</p>
        ) : null}
        <span className="story-meta">Cập nhật {formatDate(novel.updated_at)}</span>
      </div>
    </Link>
  );
}
