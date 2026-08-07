"use client";

/** Kham pha fanfic: danh sach truyen da xuat ban, tim kiem va loc theo the. */

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { api, type Novel } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { fanficOnly } from "@/lib/workspace";
import { EmptyState, ErrorState, SkeletonCards, formatDate } from "@/components/ui";
import { NovelCover } from "@/components/NovelCover";

export default function FanficPage() {
  const { profile } = useSession();
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");

  const fetchNovels = useCallback(
    () => api.listNovels(false).then((r) => fanficOnly(r.novels)),
    [],
  );
  const { data, loading, error, reload } = useAsyncData(fetchNovels);
  const novels = useMemo(() => data ?? [], [data]);

  const tags = useMemo(() => {
    const all = new Set<string>();
    novels.forEach((novel) => novel.tags.forEach((t) => all.add(t)));
    return [...all].sort((a, b) => a.localeCompare(b, "vi"));
  }, [novels]);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return novels.filter((novel) => {
      const matchText =
        !needle ||
        novel.title.toLowerCase().includes(needle) ||
        novel.description.toLowerCase().includes(needle);
      const matchTag = !tag || novel.tags.includes(tag);
      return matchText && matchTag;
    });
  }, [novels, query, tag]);

  return (
    <div className="page">
      <header className="row-between">
        <div className="stack-2">
          <span className="eyebrow">Fanfic</span>
          <h1 className="page-title">Khám phá truyện</h1>
          <p className="lead" style={{ maxWidth: 620 }}>
            Những truyện đã được tác giả xuất bản. Mỗi chương có thể kèm bản
            audio để bạn vừa đọc vừa nghe.
          </p>
        </div>
        <Link className="btn btn-primary" href={profile ? "/write" : "/login"}>
          {profile ? "Viết truyện của bạn" : "Đăng nhập để viết"}
        </Link>
      </header>

      <section className="card stack" aria-label="Bộ lọc">
        <div className="field">
          <label className="label" htmlFor="fanfic-q">
            Tìm truyện
          </label>
          <input
            id="fanfic-q"
            className="input"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tên truyện hoặc mô tả…"
          />
        </div>
        {tags.length > 0 ? (
          <div className="field">
            <span className="label" id="fanfic-tags-label">
              Thẻ
            </span>
            <div className="row" role="group" aria-labelledby="fanfic-tags-label">
              <button
                type="button"
                className="chip"
                aria-pressed={tag === ""}
                onClick={() => setTag("")}
              >
                Tất cả
              </button>
              {tags.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="chip"
                  aria-pressed={tag === item}
                  onClick={() => setTag(tag === item ? "" : item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      {loading ? (
        <SkeletonCards count={6} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : novels.length === 0 ? (
        <EmptyState
          icon="📚"
          title="Chưa có truyện nào được xuất bản"
          hint="Hãy là người đầu tiên: viết truyện rồi bấm xuất bản."
          action={
            <Link className="btn btn-primary" href={profile ? "/write" : "/login"}>
              Bắt đầu viết
            </Link>
          }
        />
      ) : shown.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="Không tìm thấy truyện phù hợp"
          hint="Thử từ khoá khác hoặc bỏ bớt bộ lọc."
          action={
            <button
              type="button"
              className="btn"
              onClick={() => {
                setQuery("");
                setTag("");
              }}
            >
              Xoá bộ lọc
            </button>
          }
        />
      ) : (
        <>
          <p className="hint" role="status">
            {shown.length} truyện
            {shown.length !== novels.length ? ` (lọc từ ${novels.length})` : ""}
          </p>
          <div className="grid">
            {shown.map((novel) => (
              <Link
                key={novel.novel_id}
                href={`/novels/${novel.novel_id}`}
                className="card card-flush card-link"
              >
                <NovelCover
                  novelId={novel.novel_id}
                  title={novel.title}
                  coverUrl={novel.cover_url}
                />
                <div className="stack-2" style={{ padding: "var(--s4)" }}>
                  <strong className="clamp-2">{novel.title}</strong>
                  <p className="hint clamp-3">
                    {novel.description || "Chưa có mô tả."}
                  </p>
                  <div className="row" style={{ gap: "var(--s2)" }}>
                    {novel.tags.slice(0, 3).map((item) => (
                      <span key={item} className="badge">
                        {item}
                      </span>
                    ))}
                  </div>
                  <span className="hint">{formatDate(novel.updated_at)}</span>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
