"use client";

/**
 * Trang chu Animation (overnight Phase 5, V6) — /animation.
 *
 * SAN PHAM DOC LAP voi Truyen/Audio (xem docstring dau
 * `server/animation_domain.py`) — day la mot khu vuc XEM rieng, khong phai
 * mot the trong trang truyen.
 *
 * CHI DU LIEU THAT: danh sach series MOI DANG (sap theo `created_at`, that su
 * lay tu backend), khong co "trending"/"luot xem" gia lap. Cac danh muc
 * Vietsub/Dub Viet cua ban thiet ke goc (subvid.app THAM KHAO, khong sao chep)
 * doi hoi mot truong phan loai rieng ma schema hien tai chua co (chi co
 * `tags` tu do) — CHUA lam dem tren, dung mot luoi kham pha + loc theo the
 * duy nhat thay vi bia ra cac muc khong co du lieu dung sau.
 */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, type AnimationSeries } from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { EmptyState, ErrorState, PageHeader, SkeletonCards } from "@/components/ui";
import { IconFilm } from "@/components/Icons";
import { MotifFilmFrame, MotifNebulaOrbit } from "@/components/Ornaments";
import { NovelCover } from "@/components/NovelCover";

const PAGE_SIZE = 12;
const DEBOUNCE_MS = 350;

export default function AnimationPage() {
  return (
    <Suspense fallback={<SkeletonCards count={6} />}>
      <AnimationBrowser />
    </Suspense>
  );
}

function AnimationBrowser() {
  const { profile } = useSession();
  const params = useSearchParams();
  const [query, setQuery] = useState(() => params.get("q") ?? "");
  const [tag, setTag] = useState(() => params.get("tag") ?? "");
  const [page, setPage] = useState(0);

  const [series, setSeries] = useState<AnimationSeries[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  const latest = useRef(0);

  const fetchPage = useCallback(async () => {
    const ticket = latest.current + 1;
    latest.current = ticket;
    setLoading(true);
    setError("");
    try {
      const r = await api.listAnimationSeries({
        query,
        tag,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      if (latest.current !== ticket) return;
      setSeries(r.series);
      setTotal(r.total);
      setHasMore(r.has_more);
    } catch (cause) {
      if (latest.current !== ticket) return;
      setError(errorMessage(cause));
      setSeries([]);
      setTotal(0);
      setHasMore(false);
    } finally {
      if (latest.current === ticket) setLoading(false);
    }
  }, [query, tag, page]);

  useEffect(() => {
    const id = window.setTimeout(fetchPage, DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [fetchPage]);

  useEffect(() => {
    api
      .animationSeriesTags()
      .then((r) => setTags(r.tags))
      .catch(() => setTags([]));
  }, []);

  const changeQuery = (value: string) => {
    setQuery(value);
    setPage(0);
  };
  const changeTag = (value: string) => {
    setTag(value);
    setPage(0);
  };
  const clearFilters = () => {
    setQuery("");
    setTag("");
    setPage(0);
  };

  const filtering = Boolean(query.trim() || tag);
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = page * PAGE_SIZE + series.length;

  return (
    // Themed Page Hero V2 — "Cinematic Nebula": cham/xanh dem + mot diem
    // cam/hong rat kiem che, cyan nho cho cam giac "anh chieu". Hoa tiet la
    // mot vanh quy dao thien the + sao (MotifNebulaOrbit) thay vi khung hinh
    // dien anh (MotifFilmFrame van con dung o portal-card cua trang chu).
    <div className="page" data-hero-theme="animation">
      <PageHeader
        eyebrow="Animation"
        icon={<IconFilm />}
        motif={<MotifNebulaOrbit />}
        title="Animation"
        lead="Xem series animation từ YouTube — video luôn phát trực tiếp từ YouTube, Fanfic không tải lại hay lưu trữ video của ai cả."
        action={
          <Link
            className="btn btn-primary"
            href={profile ? "/animation/new" : "/login"}
          >
            {profile ? "Tạo series" : "Đăng nhập để tạo"}
          </Link>
        }
      />

      <section className="filter-bar" aria-label="Bộ lọc">
        <div className="field">
          <label className="label" htmlFor="animation-q">
            Tìm series
          </label>
          <div className="input-icon">
            <span className="input-icon-mark" aria-hidden="true">
              🔍
            </span>
            <input
              id="animation-q"
              className="input"
              type="search"
              value={query}
              onChange={(e) => changeQuery(e.target.value)}
              placeholder="Tên series…"
            />
          </div>
        </div>
        {tags.length > 0 ? (
          <div className="field">
            <span className="label" id="animation-tags-label">
              Thẻ
            </span>
            <div
              className="chip-rail"
              role="group"
              aria-labelledby="animation-tags-label"
            >
              <button
                type="button"
                className="chip"
                aria-pressed={tag === ""}
                onClick={() => changeTag("")}
              >
                Tất cả
              </button>
              {tags.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="chip"
                  aria-pressed={tag === item}
                  onClick={() => changeTag(tag === item ? "" : item)}
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
        <ErrorState message={error} onRetry={fetchPage} />
      ) : series.length === 0 ? (
        filtering ? (
          <EmptyState
            icon="🔍"
            title="Không tìm thấy series phù hợp"
            hint="Thử từ khoá khác hoặc bỏ bớt bộ lọc."
            action={
              <button type="button" className="btn" onClick={clearFilters}>
                Xoá bộ lọc
              </button>
            }
          />
        ) : (
          <EmptyState
            art={<MotifFilmFrame />}
            title="Chưa có series animation nào được xuất bản"
            hint="Hãy là người đầu tiên: tạo series rồi thêm tập từ YouTube."
            action={
              <Link
                className="btn btn-primary"
                href={profile ? "/animation/new" : "/login"}
              >
                Tạo series
              </Link>
            }
          />
        )
      ) : (
        <>
          <p className="hint hang-muc" role="status">
            {/*
              Phase 3.6 Phan V: "1–1 trong 1 series" khong sai nhung khong
              tu nhien — khoang from-to chi co ich khi CO phan trang that
              (nhieu hon mot trang/mot muc). Dung mot cau ngan khi total=1.
            */}
            {total === 1 ? "1 series" : `${from}–${to} trong ${total} series`}
            {filtering ? " khớp bộ lọc" : ""}
          </p>
          <div className="anim-grid">
            {series.map((s) => (
              <Link key={s.series_id} href={`/animation/${s.series_id}`}
                    className="anim-card">
                <NovelCover
                  novelId={s.series_id}
                  title={s.title}
                  coverUrl={s.cover_url}
                  size="card"
                />
                <span className="anim-card-title">{s.title}</span>
              </Link>
            ))}
          </div>

          {total > PAGE_SIZE ? (
            <nav className="pager" aria-label="Phân trang">
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                <span aria-hidden="true">←</span> Trang trước
              </button>
              <span className="hint" role="status">
                Trang {page + 1} / {lastPage + 1}
              </span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasMore}
              >
                Trang sau <span aria-hidden="true">→</span>
              </button>
            </nav>
          ) : null}
        </>
      )}
    </div>
  );
}
