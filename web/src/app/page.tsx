"use client";

/**
 * Trang chu — mat tien cho NGUOI DOC.
 *
 * Truoc day day la landing tinh gioi thieu cong cu tao giong: hai the lon
 * "Tạo audio" / "Khám phá Fanfic", khong goi mot API nao va khong hien mot
 * truyen nao. Nguoi vao lan dau khong thay duoc thu san pham thuc su ban —
 * truyen.
 *
 * Dai mo dau o tren la MOT dai ngan, khong phai mot hero cao ca man hinh. No
 * noi day la cho doc va nghe, va tac gia tu viet duoc; roi nhuong cho ngay cho
 * truyen that. Mot hero cao se day truyen dau tien xuong duoi nep gap va bien
 * trang nay tro lai thanh landing gioi thieu cong cu.
 *
 * VE DU LIEU, va day la phan quan trong nhat khi doc file nay:
 *
 * `GET /api/novels` chi sap xep `orderDesc(created_at)` va KHONG nhan tham so
 * sort. Nen "Truyện mới" o day dung nghia la MOI TAO, khong phai moi cap nhat.
 * Goi no la "Mới cập nhật" se la mot lai noi khong dung voi du lieu.
 *
 * Khong co muc "nổi bật", "nghe nhiều" hay "có audio": khong ton tai co
 * featured, khong ton tai luot nghe theo truyen, va `Novel` khong mang co nao
 * cho biet truyen da co audio hay chua. `Profile.listened_minutes` la cua
 * NGUOI DUNG chu khong phai cua truyen. Bia dat mot muc nhu vay se phai bia ca
 * thu tu.
 *
 * Chi HAI request, khong phu thuoc so truyen: mot trang truyen va mot lan lay
 * the. Khong bao gio goi `getNovel` tung truyen de dem chuong — do la N+1,
 * va `tests/correctness-scale.test.mjs` dang khoa lai dung cho do.
 */

import Link from "next/link";
import { useCallback } from "react";
import { api, type Novel } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { StoryCard, StoryHero } from "@/components/StoryCard";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui";
import { IconFlame, IconTag } from "@/components/Icons";

/** Mot truyen cho hero + 12 the ben duoi. */
const HERO_COUNT = 1;
const GRID_COUNT = 12;

/** So the hien o muc kham pha. Du de goi y, khong du de thanh mot bai tuong. */
const MAX_TAGS = 12;

interface HomeData {
  novels: Novel[];
  tags: string[];
}

/**
 * Dai mo dau. LUON ve, ke ca khi chua co truyen nao.
 *
 * Do la ca diem cua no: khi kho con trong, day la thu duy nhat noi cho nguoi
 * vao lan dau biet ho dang o dau va lam duoc gi.
 */
function HomeHero({ daDangNhap }: { daDangNhap: boolean }) {
  return (
    <section className="home-hero rise" aria-labelledby="home-hero-title">
      <span className="pill">
        <span className="pill-dot" aria-hidden="true" />
        Đọc và nghe fanfic tiếng Việt
      </span>

      <h1 className="home-hero-title" id="home-hero-title">
        Truyện của cộng đồng, <em>đọc bằng mắt hoặc bằng tai</em>
      </h1>

      <p className="lead home-hero-lead">
        Khám phá fanfic do chính người viết xuất bản, và nghe bằng giọng đọc
        tiếng Việt tự nhiên. Bạn cũng có thể tự viết và tự tạo audio cho truyện
        của mình.
      </p>

      <div className="row">
        <Link className="btn btn-primary btn-lg" href="/fanfic">
          Khám phá truyện
        </Link>
        <Link className="btn btn-outline btn-lg" href="/write">
          Viết truyện của bạn
        </Link>
        {/* Da dang nhap thi loi vao huu ich nhat la cho ho da nghe do dang. */}
        {daDangNhap ? (
          <Link className="btn btn-ghost btn-lg" href="/library">
            Thư viện của bạn
          </Link>
        ) : null}
      </div>
    </section>
  );
}

export default function HomePage() {
  const { profile } = useSession();

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
      <HomeHero daDangNhap={Boolean(profile)} />

      {loading ? (
        <SkeletonCards count={6} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !hero ? (
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
      ) : (
        <>
          <div className="rise rise-1">
            <StoryHero novel={hero} />
          </div>

          {rest.length > 0 ? (
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
                {rest.map((novel) => (
                  <StoryCard key={novel.novel_id} novel={novel} />
                ))}
              </div>
            </section>
          ) : null}

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
        </>
      )}

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
