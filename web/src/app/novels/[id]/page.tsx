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
import { FollowButton } from "@/components/FollowButton";
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
        <Link href="/fanfic" className="hint crumb">
          ← Khám phá Fanfic
        </Link>
      </nav>

      {/*
        Bia va chu nam CANH nhau tren man hinh rong, chong len nhau o mobile
        (xem `.novel-head`). Ban cu xep bia 16:6 nam tren roi chu ben duoi: o
        desktop, bia rong 1180px chiem gan het man hinh dau tien va day ten
        truyen xuong duoi nep gap.
      */}
      <header className="novel-head">
        <div className="novel-head-cover">
          <NovelCover
            novelId={novel.novel_id}
            title={novel.title}
            coverUrl={novel.cover_url}
            size="card"
          />
        </div>

        <div className="stack-2 novel-head-body">
          <div className="row novel-head-tags">
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
          <p className="lead lead-narrow">
            {novel.description || "Chưa có mô tả."}
          </p>
          <span className="hint">
            {chapters.length} chương · cập nhật {formatDate(novel.updated_at)}
          </span>

          <div className="row novel-head-actions">
            {chapters.length > 0 ? (
              <Link
                className="btn btn-primary"
                href={`/chapters/${chapters[0].chapter_id}`}
              >
                Đọc từ đầu
              </Link>
            ) : null}
            {isOwner ? (
              <Link className="btn" href="/write">
                Quản lý truyện
              </Link>
            ) : null}
            {/*
              Theo dõi truyện — để được thông báo khi có chương mới.

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
              />
            ) : null}
          </div>
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
                  <span className="stack-2 list-main">
                    <Link
                      href={`/chapters/${chapter.chapter_id}`}
                      className="truncate list-title"
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
