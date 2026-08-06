"use client";

/** Trang chuong: trinh phat audio + noi dung chuong. */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api, type AudioTrack, type Chapter, type Novel } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { AudioPlayer } from "@/components/AudioPlayer";
import { EmptyState, ErrorState, Loading } from "@/components/states";

export default function ChapterPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [novel, setNovel] = useState<Novel | null>(null);
  const [audio, setAudio] = useState<AudioTrack | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    setMissing(false);
    api
      .getChapter(id)
      .then(async (r) => {
        setChapter(r.chapter);
        setAudio(r.audio);
        try {
          const parent = await api.getNovel(r.chapter.novel_id);
          setNovel(parent.novel);
        } catch {
          /* thieu novel khong chan viec doc chuong */
        }
      })
      .catch((e) => {
        if (e?.status === 404) setMissing(true);
        else setError(errorMessage(e));
      })
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(load, [load]);

  if (loading) return <Loading label="Đang tải chương..." />;

  if (missing) {
    return (
      <EmptyState
        icon="🔎"
        title="Không tìm thấy chương"
        body="Chương này có thể đã bị xoá hoặc đường dẫn không đúng."
        action={
          <Link href="/library" className="btn btn-primary">
            Về thư viện
          </Link>
        }
      />
    );
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!chapter) return null;

  return (
    <>
      <nav aria-label="Đường dẫn" style={{ marginTop: 24 }}>
        <Link href={`/novels/${chapter.novel_id}`} className="hint">
          ← {novel?.title ?? "Về tiểu thuyết"}
        </Link>
      </nav>

      <h1 className="page-title" style={{ marginTop: 12 }}>
        {chapter.title}
      </h1>
      <p className="page-sub">
        Chương {chapter.order_index}
        {novel ? ` · ${novel.title}` : ""} ·{" "}
        {chapter.char_count.toLocaleString("vi-VN")} ký tự
      </p>

      {audio ? (
        <AudioPlayer
          src={api.audioUrl(chapter.chapter_id)}
          title={chapter.title}
          subtitle={novel?.title}
        />
      ) : (
        <div className="card">
          <p className="state-title" style={{ marginTop: 0 }}>
            Chương này chưa có audio
          </p>
          <p className="hint" style={{ marginBottom: 12 }}>
            Vào Creator Studio, chọn giọng đọc và gửi yêu cầu tạo audio cho
            chương này.
          </p>
          <Link href="/studio" className="btn btn-primary">
            Tạo audio trong Creator Studio
          </Link>
        </div>
      )}

      <section style={{ marginTop: 28 }} aria-label="Nội dung chương">
        <h2 style={{ fontSize: 18 }}>Nội dung</h2>
        {chapter.content ? (
          <article
            className="card"
            style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}
          >
            {chapter.content}
          </article>
        ) : (
          <p className="hint">Chương này chưa có nội dung.</p>
        )}
      </section>
    </>
  );
}
