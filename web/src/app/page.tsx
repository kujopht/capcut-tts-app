"use client";

/**
 * Trang chu — mat tien cho NGUOI DOC.
 *
 * Truoc day day la landing tinh gioi thieu cong cu tao giong: hai the lon
 * "Tạo audio" / "Khám phá Fanfic", khong goi mot API nao va khong hien mot
 * truyen nao. Nguoi vao lan dau khong thay duoc thu san pham thuc su ban —
 * truyen.
 *
 * VE DU LIEU, va day la phan quan trong nhat khi doc file nay:
 *
 * `GET /api/novels` chi sap xep `orderDesc(created_at)` va KHONG nhan tham so
 * sort. Nen "Truyện mới" o day dung nghia la MOI TAO, khong phai moi cap nhat.
 * Goi no la "Mới cập nhật" se la mot lai noi khong dung voi du lieu.
 *
 * Khong co muc "nổi bật" hay "nghe nhiều": khong ton tai co featured, khong
 * ton tai luot nghe theo truyen. `Profile.listened_minutes` la cua NGUOI DUNG
 * chu khong phai cua truyen. Bia dat mot muc nhu vay se phai bia ca thu tu.
 *
 * Chi HAI request, khong phu thuoc so truyen: mot trang truyen va mot lan lay
 * the. Khong bao gio goi `getNovel` tung truyen de dem chuong — do la N+1,
 * va `tests/correctness-scale.test.mjs` dang khoa lai dung cho do.
 */

import Link from "next/link";
import { useCallback } from "react";
import { api, type Novel } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { StoryCard, StoryHero } from "@/components/StoryCard";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui";

/** Mot truyen cho hero + 12 the ben duoi. */
const HERO_COUNT = 1;
const GRID_COUNT = 12;

/** So the hien o muc kham pha. Du de goi y, khong du de thanh mot bai tuong. */
const MAX_TAGS = 12;

interface HomeData {
  novels: Novel[];
  tags: string[];
}

export default function HomePage() {
  const load = useCallback(async (): Promise<HomeData> => {
    const [page, tags] = await Promise.all([
      api.browseNovels({ limit: HERO_COUNT + GRID_COUNT }),
      api.novelTags(),
    ]);
    return { novels: page.novels, tags: tags.tags };
  }, []);

  const { data, error, loading, reload } = useAsyncData(load);

  const novels = data?.novels ?? [];
  const hero = novels[0];
  const rest = novels.slice(HERO_COUNT);

  return (
    <div className="page">
      {loading ? (
        <SkeletonCards count={6} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !hero ? (
        <EmptyState
          icon="📚"
          title="Chưa có truyện nào được xuất bản"
          hint="Khi có tác giả xuất bản truyện đầu tiên, nó sẽ xuất hiện ở đây."
          action={
            <Link className="btn btn-primary" href="/write">
              Viết truyện đầu tiên
            </Link>
          }
        />
      ) : (
        <>
          <StoryHero novel={hero} />

          {rest.length > 0 ? (
            <section className="stack-5" aria-labelledby="home-moi">
              <div className="section-head">
                <h2 className="section-title" id="home-moi">
                  Truyện mới
                </h2>
                <Link href="/fanfic" className="section-more">
                  Xem tất cả <span aria-hidden="true">→</span>
                </Link>
              </div>
              <div className="story-grid">
                {rest.map((novel) => (
                  <StoryCard key={novel.novel_id} novel={novel} />
                ))}
              </div>
            </section>
          ) : null}

          {data && data.tags.length > 0 ? (
            <section className="stack-2" aria-labelledby="home-the">
              <h2 className="section-title" id="home-the">
                Khám phá theo thẻ
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
        </>
      )}
    </div>
  );
}
