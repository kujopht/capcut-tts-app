"use client";

/**
 * Kham pha fanfic: danh sach truyen da xuat ban, tim kiem va loc theo the.
 *
 * TIM KIEM, LOC VA PHAN TRANG DEU DO BACKEND LAM. Ban truoc tai HET truyen ve
 * roi loc bang JavaScript — du cho vai chuc truyen, khong du cho vai nghin.
 *
 * Kho chua cua Audio Studio khong can loc o day: no luon o trang thai ban nhap
 * nen khong bao gio lot vao danh sach da xuat ban (xem `lib/workspace.ts`).
 */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, type Novel } from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { fanficOnly } from "@/lib/workspace";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonCards,
} from "@/components/ui";
import { IconCompass } from "@/components/Icons";
import { StoryCard } from "@/components/StoryCard";

/** So truyen moi trang. Backend chan tran tren o 60. */
const PAGE_SIZE = 12;

/** Cho nguoi dung go xong hay hoi backend — tranh mot request moi ky tu. */
const DEBOUNCE_MS = 350;

/**
 * `useSearchParams` bat trang phai co ranh gioi Suspense khi Next dung san
 * trang. Thieu no thi `next build` bao loi chu khong phai loi luc chay.
 */
export default function FanficPage() {
  return (
    <Suspense fallback={<SkeletonCards count={6} />}>
      <FanficBrowser />
    </Suspense>
  );
}

function FanficBrowser() {
  const { profile } = useSession();

  /*
    Nhan `?q=` va `?tag=` tu URL — o tim o header dieu huong sang day chu
    khong tu tim (xem `components/SiteSearch.tsx`), va the o trang chu cung
    tro toi `?tag=`. Chi doc mot lan lam GIA TRI KHOI TAO: sau do o tim tren
    trang nay lam chu trang thai, neu khong thi go phim se bi URL keo nguoc.
  */
  const params = useSearchParams();
  const [query, setQuery] = useState(() => params.get("q") ?? "");
  const [tag, setTag] = useState(() => params.get("tag") ?? "");
  const [page, setPage] = useState(0);

  const [novels, setNovels] = useState<Novel[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [tags, setTags] = useState<string[]>([]);

  /** Bo qua phan hoi cua request cu neu nguoi dung da go tiep. */
  const latest = useRef(0);

  const fetchPage = useCallback(async () => {
    const ticket = latest.current + 1;
    latest.current = ticket;
    setLoading(true);
    setError("");
    try {
      const r = await api.browseNovels({
        query,
        tag,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      if (latest.current !== ticket) return;   // da co request moi hon
      // `fanficOnly` o day la LOP PHONG VE, khong phai bo loc: kho chua cua
      // Audio Studio luon la ban nhap nen khong bao gio lot vao danh sach da
      // xuat ban. Giu lai de bat buoc do thanh hien nhien trong code — no khong
      // bao gio thuc su bo phan tu nao, nen khong lam lech so dem cua trang.
      setNovels(fanficOnly(r.novels));
      setTotal(r.total);
      setHasMore(r.has_more);
    } catch (cause) {
      if (latest.current !== ticket) return;
      setError(errorMessage(cause));
      setNovels([]);
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

  // Danh sach the lay mot lan, khong phu thuoc trang dang xem
  useEffect(() => {
    api
      .novelTags()
      .then((r) => setTags(r.tags))
      .catch(() => setTags([]));
  }, []);

  /** Doi bo loc thi ve trang dau — trang 5 cua ket qua cu thuong khong ton tai. */
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
  const to = page * PAGE_SIZE + novels.length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Fanfic"
        icon={<IconCompass />}
        title="Khám phá truyện"
        lead="Những truyện đã được tác giả xuất bản. Mỗi chương có thể kèm bản audio để bạn vừa đọc vừa nghe."
        action={
          <Link className="btn btn-primary" href={profile ? "/write" : "/login"}>
            {profile ? "Viết truyện của bạn" : "Đăng nhập để viết"}
          </Link>
        }
      />

      <section className="filter-bar" aria-label="Bộ lọc">
        <div className="field">
          <label className="label" htmlFor="fanfic-q">
            Tìm truyện
          </label>
          {/*
            Bieu tuong nam trong mot `<span>` rieng dat chong len o nhap, chu
            khong phai `background-image` cua chinh o do: o `<input type=search>`
            trinh duyet ve nut xoa cua rieng no o ben phai, va mot anh nen se
            nam duoi nut do o mot so trinh duyet.
          */}
          <div className="input-icon">
            <span className="input-icon-mark" aria-hidden="true">
              🔍
            </span>
            <input
              id="fanfic-q"
              className="input"
              type="search"
              value={query}
              onChange={(e) => changeQuery(e.target.value)}
              placeholder="Tên truyện hoặc mô tả…"
            />
          </div>
        </div>
        {tags.length > 0 ? (
          <div className="field">
            <span className="label" id="fanfic-tags-label">
              Thẻ
            </span>
            {/*
              Cuon NGANG chu khong xuong dong: voi vai chuc the, mot khoi chip
              nhieu dong cao bang ca man hinh va day het truyen xuong duoi.
            */}
            <div
              className="chip-rail"
              role="group"
              aria-labelledby="fanfic-tags-label"
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
      ) : novels.length === 0 ? (
        filtering ? (
          <EmptyState
            icon="🔍"
            title="Không tìm thấy truyện phù hợp"
            hint="Thử từ khoá khác hoặc bỏ bớt bộ lọc."
            action={
              <button type="button" className="btn" onClick={clearFilters}>
                Xoá bộ lọc
              </button>
            }
          />
        ) : (
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
        )
      ) : (
        <>
          {/* Cung mot loi trinh bay voi dong dem o Thu vien — xem `.hang-muc`. */}
          <p className="hint hang-muc" role="status">
            {from}–{to} trong {total} truyện
            {filtering ? " khớp bộ lọc" : ""}
          </p>
          {/*
            CUNG `StoryCard` voi trang chu. Truoc day the o day duoc viet
            rieng, nen hai trang cung hien mot truyen bang hai hinh dang khac
            nhau — nguoi dung bam tu trang chu sang day thay nhu doi trang.
          */}
          <div className="story-grid">
            {novels.map((novel) => (
              <StoryCard key={novel.novel_id} novel={novel} />
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
