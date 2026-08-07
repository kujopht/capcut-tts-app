"use client";

/** Chi tiet truyen: thong tin, danh sach chuong kem trang thai audio. */

import Link from "next/link";
import { use, useCallback, useState } from "react";
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
import { NovelCover } from "@/components/NovelCover";
import { AudioPlayer } from "@/components/AudioPlayer";

export default function NovelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();

  // MOT request duy nhat, du truyen co bao nhieu chuong: `has_audio` da nam
  // san trong danh sach chuong. Truoc day cho nay goi them `/api/chapters/{id}`
  // cho tung chuong chi de doc mot gia tri boolean.
  const fetchNovel = useCallback(() => api.getNovel(id), [id]);

  const { data, loading, error, missing, reload } = useAsyncData(fetchNovel);
  const novel: Novel | null = data?.novel ?? null;
  const chapters: Chapter[] = data?.chapters ?? [];

  // Chuong dang mo trinh phat. MOT chuoi id chu khong phai tap hop: mo chuong
  // khac thi chuong cu dong lai, nen khong bao gio co hai audio cung phat.
  const [playingId, setPlayingId] = useState("");

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
        <NovelCover
          novelId={novel.novel_id}
          title={novel.title}
          coverUrl={novel.cover_url}
          size="wide"
        />
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
            {chapters.map((chapter, index) => {
              const playing = playingId === chapter.chapter_id;
              return (
                // KHONG con boc ca hang trong <Link>: the <a> khong duoc chua
                // <button>, va nut nghe phai nam ngay trong hang. Tieu de moi
                // la lien ket, cac nut la anh em cua no.
                <div
                  key={chapter.chapter_id}
                  className={`list-item${playing ? " list-item-open" : ""}`}
                >
                  <span className="list-index" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span className="stack-2" style={{ flex: 1, minWidth: 0 }}>
                    <Link
                      href={`/chapters/${chapter.chapter_id}`}
                      className="truncate list-title"
                      style={{ fontWeight: 600, fontSize: "var(--t-sm)" }}
                    >
                      {chapter.title}
                    </Link>
                    <span className="hint">
                      {formatNumber(chapter.char_count)} ký tự
                    </span>
                  </span>

                  <span className="list-actions">
                    {chapter.has_audio ? (
                      <>
                        {/* M4: audio con nghe duoc, chi la co the khong khop
                            noi dung moi nhat. Noi ro thay vi im lang. */}
                        {chapter.audio_outdated ? (
                          <span
                            className="badge badge-warn"
                            title="Chương đã sửa sau khi tạo audio — audio có thể không còn khớp"
                          >
                            <span aria-hidden="true">⚠</span> Audio cũ
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className={`btn btn-sm${playing ? "" : " btn-primary"}`}
                          aria-expanded={playing}
                          onClick={() =>
                            setPlayingId(playing ? "" : chapter.chapter_id)
                          }
                        >
                          <span aria-hidden="true">{playing ? "✕" : "▶"}</span>
                          {playing ? "Đóng" : "Nghe"}
                        </button>
                      </>
                    ) : (
                      <span className="badge">Chưa có audio</span>
                    )}
                  </span>

                  {playing ? (
                    <div className="list-player">
                      <AudioPlayer
                        chapterId={chapter.chapter_id}
                        title={chapter.title}
                        compact
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
