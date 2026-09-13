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
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
import { MotifCompassArc } from "@/components/Ornaments";
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
    URL LA NGUON SU THAT cua bo loc, khong phai `useState`.

    Truoc day trang nay chi doc `?q=`/`?tag=` MOT LAN lam gia tri khoi tao roi
    giu trang thai cuc bo. Hau qua: go mot tu khoa, chon mot the, lat sang
    trang 3 — URL van y nguyen `/fanfic`. Khong chia se duoc ket qua, khong
    dat dau trang duoc, va nut Back cua trinh duyet thoat han khoi trang thay
    vi lui mot buoc loc. `?page=` thi truoc day khong doc lay mot lan.

    Nay ca ba deu suy TU URL. O nhap van giu mot trang thai cuc bo rieng
    (`oNhap`) de go phim khong giat, roi lang xuong URL sau `DEBOUNCE_MS`.
  */
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const query = params.get("q") ?? "";
  const tag = params.get("tag") ?? "";
  const page = Math.max(0, Number(params.get("page") ?? "0") || 0);

  /*
    Gia tri DANG GO trong o nhap. Tach khoi `query` vi `query` chi doi sau khi
    lang; neu buoc o nhap doc thang `query` thi moi ky tu se bi keo nguoc ve
    gia tri cu cho toi khi URL kip cap nhat.
  */
  const [oNhap, datONhap] = useState(query);

  /*
    Back/Forward: URL doi tu BEN NGOAI, nen o nhap phai di theo. Chi dong bo
    khi that su lech — neu khong, moi lan `query` doi se dam len chinh nhung
    ky tu nguoi dung vua go.
  */
  const queryTruoc = useRef(query);
  useEffect(() => {
    if (queryTruoc.current !== query) {
      queryTruoc.current = query;
      datONhap(query);
    }
  }, [query]);

  /** Ghi bo loc xuong URL. `thay` = khong them mot muc lich su moi. */
  const datURL = useCallback(
    (moi: { q?: string; tag?: string; page?: number }, thay = false) => {
      const p = new URLSearchParams(params.toString());
      const dat = (k: string, v: string) => {
        if (v) p.set(k, v);
        else p.delete(k);          // khong de `?q=` rong lam ban URL
      };
      if (moi.q !== undefined) dat("q", moi.q.trim());
      if (moi.tag !== undefined) dat("tag", moi.tag);
      if (moi.page !== undefined) dat("page", moi.page > 0 ? String(moi.page) : "");
      const chuoi = p.toString();
      const dich = chuoi ? `${pathname}?${chuoi}` : pathname;
      // `scroll: false` — doi mot bo loc khong phai mot lan dieu huong sang
      // trang khac; keo nguoi dung ve dau trang o day la cuop mat cho ho dang
      // nhin.
      if (thay) router.replace(dich, { scroll: false });
      else router.push(dich, { scroll: false });
    },
    [params, pathname, router],
  );

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

  /*
    Doi bo loc thi ve trang dau — trang 5 cua ket qua cu thuong khong ton tai.

    O NHAP dung `replace`: mot tu khoa 12 ky tu ma day 12 muc vao lich su thi
    nut Back thanh vo dung. CHON THE va LAT TRANG dung `push`: do la nhung
    thao tac ROI RAC, va lui lai mot buoc loc la dieu nguoi ta that su muon.
  */
  const changeQuery = (value: string) => {
    datONhap(value);
  };
  const changeTag = (value: string) => {
    datURL({ tag: value, page: 0 });
  };
  const clearFilters = () => {
    datONhap("");
    datURL({ q: "", tag: "", page: 0 });
  };
  const changePage = (value: number) => {
    datURL({ page: value });
  };

  /*
    O nhap -> URL, sau khi lang. Cung nhip `DEBOUNCE_MS` von da dung cho lan
    goi API, nen khong them mot do tre thu hai nao.
  */
  useEffect(() => {
    if (oNhap === query) return;
    const id = window.setTimeout(() => {
      queryTruoc.current = oNhap.trim();
      datURL({ q: oNhap, page: 0 }, true);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [oNhap, query, datURL]);

  const filtering = Boolean(query.trim() || tag);
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = page * PAGE_SIZE + novels.length;

  return (
    <div className="page" data-hero-theme="explore">
      <PageHeader
        eyebrow="Fanfic"
        icon={<IconCompass />}
        title="Khám phá truyện"
        lead="Những truyện đã được tác giả xuất bản. Mỗi chương có thể kèm bản audio để bạn vừa đọc vừa nghe."
        motif={<MotifCompassArc />}
        action={
          <Link className="btn btn-primary" href={profile ? "/studio/write" : "/login"} prefetch={false}>
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
              value={oNhap}
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
              <Link className="btn btn-primary" href={profile ? "/studio/write" : "/login"} prefetch={false}>
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
                onClick={() => changePage(Math.max(0, page - 1))}
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
                onClick={() => changePage(page + 1)}
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
