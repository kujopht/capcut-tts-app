"use client";

/**
 * THU VIEN CUA NGUOI DOC — truyen dang theo doi + cho doc tiep.
 *
 * Khac `/studio/library`, von la thu vien AUDIO cua nguoi sang tac (danh
 * sach job TTS). Hai thu khac nhau va tung bi gop lam mot: thanh dieu huong
 * chinh co muc "Thư viện", mot nguoi doc bam vao, va roi thang vao mot cong
 * cu san xuat. Trang nay tra muc do ve dung nghia cua no.
 *
 * `GET /api/me/following/stories` duoc them cung luc: truoc do
 * `followed_story_ids` chi duoc dung de DEM trong ho so, nen nguoi dung theo
 * doi duoc va thay con so, ma khong bao gio mo duoc danh sach ra.
 */

import Link from "next/link";
import { useCallback } from "react";
import { api, social, type FollowedStory } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { NovelCover } from "@/components/NovelCover";
import { EmptyState, ErrorState, SkeletonList, formatDate } from "@/components/ui";
import { IconBook } from "@/components/Icons";

const NHAN_TRANG_THAI: Record<string, string> = {
  ongoing: "Đang ra",
  completed: "Hoàn thành",
  hiatus: "Tạm ngưng",
};

export default function ThuVienPage() {
  const { profile, loading: dangNapPhien } = useSession();

  const nap = useCallback(async () => {
    const [theoDoi, tiepTuc] = await Promise.all([
      social.followedStories(50, 0),
      /*
        "Đọc tiếp" la thu PHU o day: hong no thi thu vien van con y nghia,
        nen no khong duoc phep lam ca trang thanh trang loi.
      */
      api
        .getContinueProgress()
        .catch(() => ({ reading: null, listening: null, watching: null })),
    ]);
    return { theoDoi, tiepTuc };
  }, []);

  const { data, loading, error, reload } = useAsyncData(nap, {
    enabled: Boolean(profile),
  });

  if (dangNapPhien) return <SkeletonList count={4} />;

  if (!profile) {
    return (
      <div className="page stack">
        <h1 className="page-title">Thư viện</h1>
        <EmptyState
          icon="🔖"
          title="Đăng nhập để mở thư viện của bạn"
          hint="Thư viện giữ những truyện bạn đang theo dõi và chỗ bạn đang đọc dở."
          action={
            <Link className="btn btn-primary" href="/login?next=/library" prefetch={false}>
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  const dang = data?.tiepTuc?.reading ?? null;
  const ds: FollowedStory[] = data?.theoDoi?.novels ?? [];

  return (
    <div className="page stack">
      <header className="stack-2">
        <h1 className="page-title">Thư viện</h1>
        <p className="hint">Truyện bạn theo dõi và chỗ bạn đang đọc dở.</p>
      </header>

      {dang ? (
        <section className="stack-2" aria-label="Đọc tiếp">
          <h2 className="section-title">Đọc tiếp</h2>
          <Link className="card thu-vien-tiep" href={`/chapters/${dang.chapter_id}`}>
            <span className="stack-2">
              <span className="list-title">{dang.novel_title}</span>
              <span className="hint">{dang.chapter_title}</span>
            </span>
            <span className="btn btn-sm btn-primary" aria-hidden="true">
              Đọc tiếp
            </span>
          </Link>
        </section>
      ) : null}

      <section className="stack-2" aria-label="Truyện đang theo dõi">
        <h2 className="section-title">
          Đang theo dõi
          {data?.theoDoi?.total ? (
            <span className="hint"> · {data.theoDoi.total}</span>
          ) : null}
        </h2>

        {loading ? (
          <SkeletonList count={4} />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : ds.length === 0 ? (
          <EmptyState
            icon="🔖"
            title="Chưa theo dõi truyện nào"
            hint="Mở một truyện rồi bấm “Theo dõi truyện” để nó xuất hiện ở đây."
            action={
              <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
                <IconBook size={15} /> Khám phá truyện
              </Link>
            }
          />
        ) : (
          <div className="list list-gon">
            {ds.map((n) => (
              <div key={n.novel_id} className="list-item">
                <NovelCover novelId={n.novel_id} title={n.title} size="thumb" />
                <span className="stack-2 list-main">
                  <Link href={`/novels/${n.novel_id}`} className="truncate list-title">
                    {n.title}
                  </Link>
                  <span className="hint">
                    {NHAN_TRANG_THAI[n.status] ?? n.status}
                    {n.external_author_name ? ` · ${n.external_author_name}` : ""}
                    {n.updated_at ? ` · ${formatDate(n.updated_at)}` : ""}
                  </span>
                </span>
                <span className="list-actions">
                  <Link className="btn btn-sm" href={`/novels/${n.novel_id}`}>
                    Mở
                  </Link>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
