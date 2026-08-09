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

export function StoryCard({ novel }: { novel: Novel }) {
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

/**
 * Truyen dat o vi tri hero.
 *
 * Cung du lieu, khac bo cuc: bia rong 16:6 nam tren, chu ben duoi, va co nut
 * goi hanh dong. Khong nhan ban `Novel` va khong them truong nao.
 */
export function StoryHero({ novel }: { novel: Novel }) {
  return (
    <article className="hero-story">
      <Link href={`/novels/${novel.novel_id}`} className="hero-cover">
        <NovelCover
          novelId={novel.novel_id}
          title={novel.title}
          coverUrl={novel.cover_url}
          size="wide"
        />
      </Link>
      <div className="hero-body">
        <span className="eyebrow">Truyện mới nhất</span>
        <h2 className="hero-title">
          <Link href={`/novels/${novel.novel_id}`}>{novel.title}</Link>
        </h2>
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
          <p className="lead clamp-3">{novel.description}</p>
        ) : null}
        <div className="row">
          <Link
            href={`/novels/${novel.novel_id}`}
            className="btn btn-primary"
          >
            Đọc truyện
          </Link>
          <Link href="/fanfic" className="btn btn-ghost">
            Khám phá thêm
          </Link>
        </div>
      </div>
    </article>
  );
}
