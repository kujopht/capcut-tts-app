"use client";

/** Thu vien: danh sach tieu thuyet da xuat ban, co tim kiem va loc. */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Novel } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { EmptyState, ErrorState, Loading } from "@/components/states";

export default function LibraryPage() {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");

  // Chi nap du lieu; moi setState deu nam trong callback bat dong bo.
  const fetchNovels = useCallback(
    () =>
      api
        .listNovels(false)
        .then((r) => setNovels(r.novels))
        .catch((e) => setError(errorMessage(e)))
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    void fetchNovels();
  }, [fetchNovels]);

  // Nut "Thu lai" la event handler nen dat state truc tiep o day la dung.
  const retry = useCallback(() => {
    setLoading(true);
    setError("");
    void fetchNovels();
  }, [fetchNovels]);

  const tags = useMemo(() => {
    const all = new Set<string>();
    novels.forEach((n) => n.tags.forEach((t) => all.add(t)));
    return Array.from(all).sort();
  }, [novels]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return novels.filter((n) => {
      if (tag && !n.tags.includes(tag)) return false;
      if (!needle) return true;
      return (
        n.title.toLowerCase().includes(needle) ||
        n.description.toLowerCase().includes(needle)
      );
    });
  }, [novels, query, tag]);

  return (
    <>
      <h1 className="page-title">Thư viện</h1>
      <p className="page-sub">Các tiểu thuyết đã được xuất bản.</p>

      <div
        style={{ display: "flex", gap: 12, marginBottom: 22, flexWrap: "wrap" }}
      >
        <div style={{ flex: "1 1 260px" }}>
          <label className="label" htmlFor="lib-search">
            Tìm kiếm
          </label>
          <input
            id="lib-search"
            className="input"
            type="search"
            placeholder="Tên truyện hoặc mô tả..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div style={{ flex: "0 1 220px" }}>
          <label className="label" htmlFor="lib-tag">
            Thẻ
          </label>
          <select
            id="lib-tag"
            className="select"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
          >
            <option value="">Tất cả</option>
            {tags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <Loading label="Đang tải thư viện..." />
      ) : error ? (
        <ErrorState message={error} onRetry={retry} />
      ) : novels.length === 0 ? (
        <EmptyState
          title="Chưa có truyện nào được xuất bản"
          body="Hãy vào Creator Studio để tạo truyện đầu tiên rồi xuất bản."
          action={
            <Link href="/studio" className="btn btn-primary">
              Mở Creator Studio
            </Link>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="Không tìm thấy truyện phù hợp"
          body="Thử đổi từ khoá hoặc bỏ bộ lọc thẻ."
        />
      ) : (
        <>
          <p className="hint" style={{ marginBottom: 12 }} role="status">
            Hiện {visible.length}/{novels.length} truyện
          </p>
          <div className="grid">
            {visible.map((novel) => (
              <Link
                key={novel.novel_id}
                href={`/novels/${novel.novel_id}`}
                className="novel-card"
              >
                <div className="novel-cover" aria-hidden="true">
                  📖
                </div>
                <div className="novel-body">
                  <div className="novel-title">{novel.title}</div>
                  <p
                    className="hint"
                    style={{
                      margin: "0 0 10px",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {novel.description || "Chưa có mô tả."}
                  </p>
                  <div
                    style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
                  >
                    <span className="badge badge-ok">Đã xuất bản</span>
                    {novel.tags.slice(0, 2).map((t) => (
                      <span className="badge" key={t}>
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}
