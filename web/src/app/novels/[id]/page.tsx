"use client";

/** Chi tiet truyen: thong tin, danh sach chuong kem trang thai audio. */

import Link from "next/link";
import { use, useCallback } from "react";
import { api, type Chapter, type Novel } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  EmptyState,
  ErrorState,
  SkeletonList,
  formatDate,
  formatNumber,
} from "@/components/ui";

export default function NovelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();

  const fetchNovel = useCallback(async () => {
    const r = await api.getNovel(id);
    const flags = await Promise.all(
      r.chapters.map((chapter) =>
        api
          .getChapter(chapter.chapter_id)
          .then((detail) => [chapter.chapter_id, detail.audio !== null] as const)
          .catch(() => [chapter.chapter_id, false] as const),
      ),
    );
    return {
      novel: r.novel,
      chapters: r.chapters,
      audioReady: Object.fromEntries(flags) as Record<string, boolean>,
    };
  }, [id]);

  const { data, loading, error, missing, reload } = useAsyncData(fetchNovel);
  const novel: Novel | null = data?.novel ?? null;
  const chapters: Chapter[] = data?.chapters ?? [];
  const audioReady: Record<string, boolean> = data?.audioReady ?? {};

  if (loading) {
    return (
      <div className="page">
        <div className="sk sk-title" style={{ height: 32, width: "40%" }} />
        <SkeletonList count={5} />
      </div>
    );
  }

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy truyện này"
          hint="Truyện có thể đã bị xoá hoặc chưa được xuất bản."
          action={
            <Link className="btn btn-primary" href="/fanfic">
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !novel) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được truyện."} onRetry={reload} />
      </div>
    );
  }

  const isOwner = profile?.user_id === novel.owner_id;

  return (
    <div className="page">
      <nav aria-label="Đường dẫn">
        <Link href="/fanfic" className="hint">
          ← Khám phá Fanfic
        </Link>
      </nav>

      <header className="card stack">
        <div className="row-between">
          <div className="stack-2" style={{ minWidth: 0, flex: "1 1 320px" }}>
            <div className="row" style={{ gap: "var(--s2)" }}>
              <span className={`badge ${novel.state === "published" ? "badge-ok" : ""}`}>
                {novel.state === "published" ? "Đã xuất bản" : "Bản nháp"}
              </span>
              {novel.tags.map((tag) => (
                <span key={tag} className="badge">
                  {tag}
                </span>
              ))}
            </div>
            <h1 className="page-title">{novel.title}</h1>
            <p className="lead">{novel.description || "Chưa có mô tả."}</p>
            <span className="hint">
              {chapters.length} chương · cập nhật {formatDate(novel.updated_at)}
            </span>
          </div>
          {isOwner ? (
            <Link className="btn" href="/write">
              Quản lý truyện
            </Link>
          ) : null}
        </div>
      </header>

      <section className="stack" aria-label="Danh sách chương">
        <h2 className="section-title">Danh sách chương</h2>
        {chapters.length === 0 ? (
          <EmptyState
            icon="📄"
            title="Truyện chưa có chương nào"
            action={
              isOwner ? (
                <Link className="btn btn-primary" href="/write">
                  Thêm chương đầu tiên
                </Link>
              ) : undefined
            }
          />
        ) : (
          <div className="list">
            {chapters.map((chapter, index) => (
              <Link
                key={chapter.chapter_id}
                href={`/chapters/${chapter.chapter_id}`}
                className="list-item"
              >
                <span className="list-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="stack-2" style={{ flex: 1, minWidth: 0 }}>
                  <strong className="truncate" style={{ fontSize: "var(--t-sm)" }}>
                    {chapter.title}
                  </strong>
                  <span className="hint">
                    {formatNumber(chapter.char_count)} ký tự
                  </span>
                </span>
                {audioReady[chapter.chapter_id] ? (
                  <span className="badge badge-ok">
                    <span aria-hidden="true">🎧</span> Có audio
                  </span>
                ) : (
                  <span className="badge">Chưa có audio</span>
                )}
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
