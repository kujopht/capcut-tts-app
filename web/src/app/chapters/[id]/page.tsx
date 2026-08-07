"use client";

/** Doc chuong: trinh phat audio o tren, noi dung o duoi. */

import Link from "next/link";
import { use, useCallback } from "react";
import { api, type AudioTrack, type Chapter, type NovelBrief } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { AudioPlayer } from "@/components/AudioPlayer";
import { EmptyState, ErrorState, SkeletonList, formatNumber } from "@/components/ui";
import { NovelCover } from "@/components/NovelCover";

export default function ChapterPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();

  // Backend tra kem `novel` trong chinh phan hoi cua chuong, nen khong con
  // phai goi them mot vong `/api/novels/{id}` chi de lay ten va anh bia.
  const fetchChapter = useCallback(() => api.getChapter(id), [id]);

  const { data, loading, error, missing, reload } = useAsyncData(fetchChapter);
  const chapter: Chapter | null = data?.chapter ?? null;
  const audio: AudioTrack | null = data?.audio ?? null;
  const novel: NovelBrief | null = data?.novel ?? null;
  const audioOutdated = Boolean(data?.audio_outdated);

  if (loading) {
    return (
      <div className="page">
        <div className="sk sk-title" style={{ height: 30, width: "45%" }} />
        <SkeletonList count={3} />
      </div>
    );
  }

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy chương này"
          action={
            <Link className="btn btn-primary" href="/fanfic">
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !chapter) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được chương."} onRetry={reload} />
      </div>
    );
  }

  const isOwner = profile?.user_id === chapter.owner_id;

  return (
    <div className="page">
      <nav aria-label="Đường dẫn">
        <Link href={`/novels/${chapter.novel_id}`} className="hint">
          ← {novel?.title ?? "Về truyện"}
        </Link>
      </nav>

      <header className="stack-2">
        <h1 className="page-title">{chapter.title}</h1>
        <span className="hint">{formatNumber(chapter.char_count)} ký tự</span>
      </header>

      {audio ? (
        <div className="stack">
          {/* M4: audio van phat duoc va van tai duoc — chi canh bao rang no
              duoc tao truoc lan sua noi dung gan nhat. Chu so huu duoc chi
              duong tao lai; nguoi doc chi can biet de khong ngo ngang. */}
          {audioOutdated ? (
            <div className="alert alert-warn" role="status">
              <span aria-hidden="true">⚠</span>
              <span className="stack-2">
                <span>
                  Chương này đã được sửa sau khi tạo audio, nên{" "}
                  <strong>audio có thể không còn khớp</strong> với nội dung bên
                  dưới. Bản audio hiện tại vẫn nghe và tải được.
                </span>
                {/* Nut that, khong phai lien ket trong cau: vung bam du to o
                    mobile, va M4 yeu cau duong dan RO RANG sang cho tao lai. */}
                {isOwner ? (
                  <Link className="btn btn-sm" href="/write">
                    Tạo lại audio trong khu vực tác giả
                  </Link>
                ) : null}
              </span>
            </div>
          ) : null}
          <div className="listen">
            <NovelCover
              novelId={chapter.novel_id}
              title={novel?.title ?? chapter.title}
              coverUrl={novel?.cover_url}
              size="thumb"
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <AudioPlayer chapterId={chapter.chapter_id} title={chapter.title} />
            </div>
          </div>
        </div>
      ) : (
        <EmptyState
          icon="🎧"
          title="Chương này chưa có audio"
          hint={
            isOwner
              ? "Bạn có thể tạo audio cho chương trong khu vực tác giả."
              : "Tác giả chưa tạo bản audio cho chương này."
          }
          action={
            isOwner ? (
              <Link className="btn btn-primary" href="/write">
                Tạo audio cho chương
              </Link>
            ) : undefined
          }
        />
      )}

      <section className="card" aria-label="Nội dung chương">
        {chapter.content ? (
          <div className="prose">{chapter.content}</div>
        ) : (
          <p className="hint">Chương này chưa có nội dung.</p>
        )}
      </section>
    </div>
  );
}
