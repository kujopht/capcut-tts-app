"use client";

/** Chi tiet tieu thuyet: thong tin + danh sach chuong kem trang thai audio. */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api, type Chapter, type Novel } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { EmptyState, ErrorState, Loading } from "@/components/states";

export default function NovelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [novel, setNovel] = useState<Novel | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [audioReady, setAudioReady] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);

  // Chi nap du lieu; moi setState deu nam trong callback bat dong bo.
  const fetchNovel = useCallback(
    () =>
      api
        .getNovel(id)
        .then(async (r) => {
          setNovel(r.novel);
          setChapters(r.chapters);
          // Hoi trang thai audio cua tung chuong
          const flags: Record<string, boolean> = {};
          await Promise.all(
            r.chapters.map(async (c) => {
              try {
                const detail = await api.getChapter(c.chapter_id);
                flags[c.chapter_id] = Boolean(detail.audio);
              } catch {
                flags[c.chapter_id] = false;
              }
            }),
          );
          setAudioReady(flags);
        })
        .catch((e) => {
          if (e?.status === 404) setMissing(true);
          else setError(errorMessage(e));
        })
        .finally(() => setLoading(false)),
    [id],
  );

  useEffect(() => {
    void fetchNovel();
  }, [fetchNovel]);

  // Nut "Thu lai" la event handler nen dat state truc tiep o day la dung.
  const retry = useCallback(() => {
    setLoading(true);
    setError("");
    setMissing(false);
    void fetchNovel();
  }, [fetchNovel]);

  if (loading) return <Loading label="Đang tải tiểu thuyết..." />;

  if (missing) {
    return (
      <EmptyState
        icon="🔎"
        title="Không tìm thấy tiểu thuyết"
        body="Truyện này có thể đã bị xoá hoặc đường dẫn không đúng."
        action={
          <Link href="/library" className="btn btn-primary">
            Về thư viện
          </Link>
        }
      />
    );
  }

  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!novel) return null;

  return (
    <>
      <nav aria-label="Đường dẫn" style={{ marginTop: 24 }}>
        <Link href="/library" className="hint">
          ← Thư viện
        </Link>
      </nav>

      <header
        style={{
          display: "flex",
          gap: 20,
          marginTop: 14,
          marginBottom: 28,
          flexWrap: "wrap",
        }}
      >
        <div
          className="novel-cover"
          aria-hidden="true"
          style={{ width: 150, height: 150, borderRadius: 14, flexShrink: 0 }}
        >
          📖
        </div>
        <div style={{ flex: "1 1 300px" }}>
          <h1 style={{ fontSize: 28, margin: "0 0 8px" }}>{novel.title}</h1>
          <p style={{ color: "var(--text-dim)", marginTop: 0 }}>
            {novel.description || "Chưa có mô tả."}
          </p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span
              className={
                novel.state === "published" ? "badge badge-ok" : "badge"
              }
            >
              {novel.state === "published" ? "Đã xuất bản" : "Bản nháp"}
            </span>
            {novel.tags.map((t) => (
              <span className="badge" key={t}>
                {t}
              </span>
            ))}
            <span className="badge">{chapters.length} chương</span>
          </div>
        </div>
      </header>

      <h2 style={{ fontSize: 18 }}>Danh sách chương</h2>

      {chapters.length === 0 ? (
        <EmptyState
          icon="📄"
          title="Truyện chưa có chương nào"
          body="Vào Creator Studio để thêm chương đầu tiên."
          action={
            <Link href="/studio" className="btn">
              Mở Creator Studio
            </Link>
          }
        />
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {chapters.map((chapter) => (
            <li key={chapter.chapter_id} style={{ marginBottom: 10 }}>
              <div
                className="card"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  flexWrap: "wrap",
                }}
              >
                <span
                  className="hint"
                  style={{ minWidth: 34 }}
                  aria-hidden="true"
                >
                  #{chapter.order_index}
                </span>
                <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{chapter.title}</div>
                  <div className="hint">
                    {chapter.char_count.toLocaleString("vi-VN")} ký tự
                  </div>
                </div>
                {audioReady[chapter.chapter_id] ? (
                  <span className="badge badge-ok">Có audio</span>
                ) : (
                  <span className="badge">Chưa có audio</span>
                )}
                <Link
                  href={`/chapters/${chapter.chapter_id}`}
                  className={
                    audioReady[chapter.chapter_id] ? "btn btn-primary" : "btn"
                  }
                >
                  {audioReady[chapter.chapter_id] ? "▶ Nghe" : "Mở chương"}
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
