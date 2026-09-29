"use client";

/**
 * Bảng tin cộng đồng — Social & Play V1.
 *
 * KHÔNG đòi đăng nhập: khách vãng lai đọc được tab "Mới nhất", chỉ không đăng/
 * thích/bình luận được. Một trang cộng đồng trả 401 cho khách là một cánh cửa
 * đóng, và nội dung ở đây vốn là công khai.
 *
 * Bố cục: một tiêu đề GỌN (không còn khối hero to trống) + tab + chip fandom;
 * desktop là cột đọc ~680px ở giữa và một cột phụ nhỏ (hồ sơ mini, điều hướng,
 * tác giả nổi bật THẬT); điện thoại là một cột toàn chiều rộng.
 *
 * Những thứ bảng tin cũ làm sai và bản này sửa:
 *   * bộ lọc sống trên URL — Back và liên kết chia sẻ giữ đúng tab/fandom;
 *   * phân trang CURSOR tất định, gộp không trùng, có trần độ sâu nói rõ;
 *   * bài mới KHÔNG chen lên đầu dưới mắt người đang đọc — chỉ báo "Có N bài
 *     mới", bấm mới gộp vào;
 *   * mở một bài/hồ sơ rồi Back: thấy lại đúng danh sách, đúng chỗ cuộn, đúng
 *     những khối bình luận đang mở.
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  social,
  type FeedPage,
  type FeedPageV2,
  type Novel,
  type Post,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  chuoiTruyVanFeed,
  demBaiMoi,
  docTruyVanFeed,
  ghiAnhChup,
  gopTrang,
  hoSoHref,
  layAnhChup,
  nhanBaiMoi,
  urlFeed,
  xoaAnhChup,
  type FeedQuery,
  type KhoChuoi,
} from "@/lib/communityFeed";
import { SkeletonList, ErrorState, EmptyState } from "@/components/ui";
import { PostCard } from "@/components/PostCard";
import { PostComposer } from "@/components/PostComposer";
import { TacGiaNoiBat } from "@/components/CommunitySidebar";
import { UserAvatar, tenHienThi } from "@/components/UserAvatar";

const CO_TRANG = 20;
/** Hỏi lại trang đầu để báo bài mới. Dừng hẳn khi tab bị ẩn. */
const NHIP_BAI_MOI_MS = 60_000;

function khoPhien(): KhoChuoi | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

interface TrangThai {
  items: Post[];
  nextCursor: string | null;
  depthCapped: boolean;
  followingTruncated: boolean;
}

/** Cursor gia cho MAY CHU CU (chua biet `scope`): "off:<offset>". */
const TIEN_TO_OFFSET = "off:";

/**
 * Web va API trien khai TACH NHAU (Render tat autoDeploy): web moi co the len
 * truoc API. API cu bo qua `scope` va tra hinh dang cu (`total`, khong
 * `next_cursor`) — khong doan: nhan ra va lui ve phan trang offset, thay vi mat
 * nut "Xem thêm" hay dan nhan "Đang theo dõi" cho mot bang tin tron.
 */
function laMayChuCu(ra: FeedPageV2 | FeedPage): ra is FeedPage {
  return !("scope" in ra);
}

function BangTinCongDong() {
  const { profile, loading: dangTaiPhien } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const tham = useSearchParams();
  const q: FeedQuery = useMemo(() => docTruyVanFeed(tham.toString()), [tham]);
  const khoa = chuoiTruyVanFeed(q);

  const [tt, setTt] = useState<TrangThai | null>(null);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [truyenCuaToi, setTruyenCuaToi] = useState<Novel[]>([]);
  const [loi, setLoi] = useState("");
  const [loiThem, setLoiThem] = useState("");
  const [dangThem, setDangThem] = useState(false);
  const [baiMoi, setBaiMoi] = useState<Post[]>([]);
  /** API chua ho tro bang tin theo tab (xem `laMayChuCu`). */
  const [mayChuCu, setMayChuCu] = useState(false);
  const [moBinhLuan, setMoBinhLuan] = useState<Set<string>>(() => new Set());
  const cuonCuoi = useRef(0);
  /** Da bam mot lien ket roi trang: vi tri cuon DONG BANG — Next cuon trang moi
      len dau TRUOC khi cleanup chay, doc `scrollY` luc do la doc so 0. */
  const dongBang = useRef(false);
  const cuonCho = useRef<number | null>(null);
  const ttRef = useRef<TrangThai | null>(null);
  const moRef = useRef<Set<string>>(moBinhLuan);
  useEffect(() => {
    ttRef.current = tt;
  }, [tt]);
  useEffect(() => {
    moRef.current = moBinhLuan;
  }, [moBinhLuan]);

  // Tab "Đang theo dõi" chỉ có nghĩa khi đã đăng nhập.
  const canDangNhap = q.scope === "following" && !profile && !dangTaiPhien;

  const tai = useCallback(async () => {
    setLoi("");
    setLoiThem("");
    setBaiMoi([]);
    // Back tu mot bai/ho so: khoi phuc anh chup cua DUNG bo loc nay. KHONG xoa
    // luc doc — effect co the chay lai; xoa sau khi da cuon ve cho cu.
    const anh = layAnhChup<Post>(khoPhien(), khoa, Date.now(), false);
    if (anh && anh.items.length) {
      setTt({
        items: anh.items,
        nextCursor: anh.nextCursor,
        depthCapped: anh.depthCapped,
        followingTruncated: false,
      });
      setMoBinhLuan(new Set(anh.moBinhLuan));
      cuonCho.current = anh.y;
      return;
    }
    setTt(null);
    setMoBinhLuan(new Set());
    try {
      const ra = (await social.feedV2({ scope: q.scope, fandom: q.fandom, limit: CO_TRANG })) as FeedPageV2 | FeedPage;
      if (laMayChuCu(ra)) {
        setMayChuCu(true);
        // May chu cu khong loc duoc theo tab/fandom: KHONG dan nhan sai cho bang tin tron.
        const locDuoc = q.scope === "latest" && !q.fandom;
        setTt({
          items: locDuoc ? ra.items : [],
          nextCursor: locDuoc && ra.items.length < ra.total ? `${TIEN_TO_OFFSET}${ra.items.length}` : null,
          depthCapped: false,
          followingTruncated: false,
        });
        return;
      }
      setMayChuCu(false);
      setTt({
        items: ra.items,
        nextCursor: ra.next_cursor,
        depthCapped: ra.depth_capped,
        followingTruncated: Boolean(ra.following_truncated),
      });
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không tải được bảng tin.");
    }
  }, [khoa, q.scope, q.fandom]);

  useEffect(() => {
    if (dangTaiPhien) return;
    if (canDangNhap) {
      queueMicrotask(() => setTt({ items: [], nextCursor: null, depthCapped: false, followingTruncated: false }));
      return;
    }
    queueMicrotask(() => void tai());
  }, [tai, dangTaiPhien, canDangNhap, profile?.user_id]);

  /* Cuon lai vi tri cu khi danh sach da ve (anh chup), ROI moi xoa anh chup.
     Hai nhip rAF: nhip dau de cac khoi binh luan dang mo kip ve chieu cao. */
  useEffect(() => {
    if (tt && cuonCho.current !== null) {
      const y = cuonCho.current;
      cuonCho.current = null;
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          window.scrollTo({ top: y, behavior: "instant" as ScrollBehavior });
          cuonCuoi.current = y;
          xoaAnhChup(khoPhien());
        }),
      );
    }
  }, [tt]);

  /* Theo doi vi tri cuon lien tuc (rAF) — luc roi trang, Next co the da doi
     cuon, nen doc `scrollY` trong cleanup la qua muon. Bam mot lien ket noi bo
     thi DONG BANG gia tri (xem `dongBang`). */
  useEffect(() => {
    dongBang.current = false;
    let cho = 0;
    const onScroll = () => {
      if (cho || dongBang.current) return;
      cho = requestAnimationFrame(() => {
        cho = 0;
        if (!dongBang.current) cuonCuoi.current = window.scrollY;
      });
    };
    const onClick = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a[href]");
      const href = a?.getAttribute("href") ?? "";
      if (!href.startsWith("/") || href.startsWith("/community")) return;
      cuonCuoi.current = window.scrollY;
      dongBang.current = true;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("scroll", onScroll);
      document.removeEventListener("click", onClick, true);
      if (cho) cancelAnimationFrame(cho);
    };
  }, []);

  /* Roi trang (mo bai/ho so/…): ghi anh chup cho DUNG bo loc dang xem. */
  useEffect(() => {
    return () => {
      const s = ttRef.current;
      if (!s || !s.items.length) return;
      ghiAnhChup(khoPhien(), {
        khoa,
        items: s.items,
        nextCursor: s.nextCursor,
        depthCapped: s.depthCapped,
        moBinhLuan: [...moRef.current],
        y: cuonCuoi.current,
        t: Date.now(),
      });
    };
  }, [khoa]);

  /* Gioi han may chu. Loi o day KHONG hien: hop soan van dung duoc voi con so
     du phong, va may chu van la noi cuong che. */
  useEffect(() => {
    social.limits().then(setLimits).catch(() => {});
  }, []);

  /* Truyen da xuat ban cua chinh minh — de dang "cap nhat truyen". */
  const laTacGia = profile?.author_status === "approved";
  useEffect(() => {
    if (!laTacGia) return;
    api
      .listNovels(true)
      .then((r) => setTruyenCuaToi(r.novels.filter((n) => n.state === "published")))
      .catch(() => {});
  }, [laTacGia]);

  /* "Co N bai moi": hoi lai trang dau moi phut KHI tab dang hien. */
  useEffect(() => {
    if (!tt || canDangNhap) return;
    let huy = false;
    const hoi = async () => {
      if (document.visibilityState !== "visible") return;
      const s = ttRef.current;
      if (!s || !s.items.length) return;
      try {
        const ra = await social.feedV2({ scope: q.scope, fandom: q.fandom, limit: CO_TRANG });
        if (huy) return;
        const n = demBaiMoi(s.items, ra.items);
        if (n > 0) {
          const da = new Set(s.items.map((x) => x.post_id));
          setBaiMoi(ra.items.filter((x) => !da.has(x.post_id) && x.created_at >= s.items[0].created_at));
        }
      } catch {
        /* im lang: day chi la goi y, khong phai loi cua nguoi dung */
      }
    };
    const h = window.setInterval(() => void hoi(), NHIP_BAI_MOI_MS);
    return () => {
      huy = true;
      window.clearInterval(h);
    };
  }, [tt, canDangNhap, q.scope, q.fandom]);

  const hienBaiMoi = useCallback(() => {
    setTt((s) => (s ? { ...s, items: gopTrang(baiMoi, s.items) } : s));
    setBaiMoi([]);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [baiMoi]);

  const themVaoDau = useCallback((bai: Post) => {
    setTt((s) => (s ? { ...s, items: gopTrang([bai], s.items) } : s));
  }, []);

  const themTrang = useCallback(async () => {
    const s = ttRef.current;
    if (!s?.nextCursor || dangThem) return;
    setDangThem(true);
    setLoiThem("");
    try {
      if (s.nextCursor.startsWith(TIEN_TO_OFFSET)) {
        // May chu cu: phan trang offset nhu truoc.
        const off = Number(s.nextCursor.slice(TIEN_TO_OFFSET.length)) || 0;
        const cu = await social.feed(CO_TRANG, off);
        setTt((truoc) => {
          if (!truoc) return truoc;
          const items = gopTrang(truoc.items, cu.items);
          const tiep = off + cu.items.length;
          return { ...truoc, items, nextCursor: cu.items.length && tiep < cu.total ? `${TIEN_TO_OFFSET}${tiep}` : null };
        });
        return;
      }
      const ra = await social.feedV2({ scope: q.scope, fandom: q.fandom, cursor: s.nextCursor, limit: CO_TRANG });
      setTt((cu) =>
        cu
          ? {
              ...cu,
              items: gopTrang(cu.items, ra.items),
              nextCursor: ra.next_cursor,
              depthCapped: ra.depth_capped,
            }
          : cu,
      );
    } catch (e) {
      setLoiThem(e instanceof ApiError ? e.message : "Không tải thêm được. Thử lại nhé.");
    } finally {
      setDangThem(false);
    }
  }, [dangThem, q.scope, q.fandom]);

  const doiBoLoc = useCallback(
    (moi: Partial<FeedQuery>) => {
      router.push(urlFeed({ ...q, ...moi }), { scroll: false });
    },
    [q, router],
  );

  const anNguoi = useCallback((userId: string) => {
    setTt((s) => (s ? { ...s, items: s.items.filter((x) => x.author_user_id !== userId) } : s));
  }, []);

  const fandoms = limits?.community_fandoms ?? [];
  const tenFandom = fandoms.find((f) => f.id === q.fandom)?.label ?? q.fandom;
  const nhanMoi = nhanBaiMoi(baiMoi.length, CO_TRANG);

  return (
    <div className="page cong-dong-trang" data-hero-theme="community">
      <header className="cong-dong-dau">
        <div className="cong-dong-dau-chu">
          <h1 className="cong-dong-tieu-de">Cộng đồng</h1>
          <p className="hint">
            {q.scope === "following"
              ? "Bài mới từ những người bạn theo dõi."
              : "Bài mới nhất từ khắp Fanfic World."}
          </p>
        </div>
        {!profile && !dangTaiPhien ? (
          <Link href={`/login?next=${encodeURIComponent(pathname + chuoiTruyVanFeed(q))}`} className="btn btn-primary btn-sm" prefetch={false}>
            Đăng nhập để tham gia
          </Link>
        ) : null}
      </header>

      <div className="cong-dong-luoi">
        <div className="stack cong-dong-chinh">
          <nav className="cong-dong-loc" aria-label="Lọc bảng tin">
            <div className="seg" role="group" aria-label="Tab bảng tin">
              <button
                type="button"
                className="seg-item"
                aria-pressed={q.scope === "latest"}
                onClick={() => doiBoLoc({ scope: "latest" })}
              >
                Mới nhất
              </button>
              {profile && !mayChuCu ? (
                <button
                  type="button"
                  className="seg-item"
                  aria-pressed={q.scope === "following"}
                  onClick={() => doiBoLoc({ scope: "following" })}
                >
                  Đang theo dõi
                </button>
              ) : null}
            </div>
            {fandoms.length ? (
              <div className="chip-rail cong-dong-fandom" role="group" aria-label="Lọc theo fandom">
                <button type="button" className="chip" aria-pressed={!q.fandom} onClick={() => doiBoLoc({ fandom: "" })}>
                  Tất cả fandom
                </button>
                {fandoms.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className="chip"
                    aria-pressed={q.fandom === f.id}
                    onClick={() => doiBoLoc({ fandom: q.fandom === f.id ? "" : f.id })}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            ) : null}
          </nav>

          {profile ? (
            <PostComposer
              limits={limits}
              defaultFandom={q.fandom}
              storyOptions={
                laTacGia ? truyenCuaToi.map((n) => ({ novel_id: n.novel_id, title: n.title })) : []
              }
              onPosted={themVaoDau}
            />
          ) : null}

          {nhanMoi ? (
            <button type="button" className="cong-dong-bai-moi" onClick={hienBaiMoi}>
              ↑ {nhanMoi} — bấm để xem
            </button>
          ) : null}

          {tt?.followingTruncated ? (
            <p className="hint">
              Bạn theo dõi rất nhiều người — bảng tin đang hiện bài của những người bạn theo dõi gần nhất.
            </p>
          ) : null}

          {loi ? <ErrorState message={loi} onRetry={() => void tai()} /> : null}

          {canDangNhap ? (
            <EmptyState
              title="Đăng nhập để xem bài từ người bạn theo dõi"
              hint="Tab Mới nhất vẫn mở cho mọi người."
            />
          ) : mayChuCu && (q.scope !== "latest" || q.fandom) ? (
            <EmptyState
              title="Máy chủ chưa hỗ trợ bộ lọc này"
              hint="Tab Mới nhất vẫn dùng được. Bộ lọc theo dõi/fandom sẽ mở khi máy chủ được cập nhật."
            />
          ) : tt === null && !loi ? (
            <SkeletonList count={3} />
          ) : tt && tt.items.length === 0 ? (
            <EmptyState
              title={
                q.fandom
                  ? `Chưa có bài nào về ${tenFandom}`
                  : q.scope === "following"
                    ? "Chưa có bài nào từ người bạn theo dõi"
                    : "Chưa có bài nào"
              }
              hint={
                q.scope === "following"
                  ? "Theo dõi tác giả hoặc bạn đọc khác để bài của họ hiện ở đây."
                  : profile
                    ? "Hãy là người đầu tiên chia sẻ điều gì đó."
                    : "Đăng nhập để bắt đầu."
              }
            />
          ) : (
            <div className="stack cong-dong-ds">
              {(tt?.items ?? []).map((bai) => (
                <PostCard
                  key={bai.post_id}
                  post={bai}
                  limits={limits}
                  commentsOpen={moBinhLuan.has(bai.post_id)}
                  onCommentsOpenChange={(mo) =>
                    setMoBinhLuan((cu) => {
                      const s = new Set(cu);
                      if (mo) s.add(bai.post_id);
                      else s.delete(bai.post_id);
                      return s;
                    })
                  }
                  onChange={(moi) =>
                    setTt((s) =>
                      s ? { ...s, items: s.items.map((x) => (x.post_id === moi.post_id ? moi : x)) } : s,
                    )
                  }
                  onDeleted={(id) =>
                    setTt((s) => (s ? { ...s, items: s.items.filter((x) => x.post_id !== id) } : s))
                  }
                  onAuthorHidden={anNguoi}
                />
              ))}
            </div>
          )}

          {tt && tt.items.length > 0 ? (
            tt.nextCursor ? (
              <div className="cong-dong-them">
                <button type="button" className="btn btn-ghost" disabled={dangThem} onClick={() => void themTrang()}>
                  {dangThem ? "Đang tải…" : "Xem thêm"}
                </button>
                {loiThem ? (
                  <p className="hint loi" role="alert">
                    {loiThem}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="hint cong-dong-het">
                {tt.depthCapped
                  ? "Bạn đã xem tới giới hạn của bảng tin. Lọc theo fandom để tìm bài cũ hơn."
                  : "Bạn đã xem hết bài."}
              </p>
            )
          ) : null}
        </div>

        <aside className="cong-dong-phai" aria-label="Cộng đồng của bạn">
          {profile ? (
            <section className="card cong-dong-toi">
              <div className="cong-dong-toi-dau">
                <UserAvatar user={profile} className="avatar" link />
                <div className="cong-dong-toi-chu">
                  <strong>{tenHienThi(profile)}</strong>
                  {profile.username ? <span className="hint">@{profile.username}</span> : null}
                </div>
              </div>
              <ul className="sidebar-ds cong-dong-nav">
                {/* prefetch={false}: cot phu thuong truc trong khung nhin — xem
                    tests/static-link-prefetch.test.mjs (bao prefetch tren production). */}
                <li>
                  <Link href={hoSoHref(profile) || "/account"} prefetch={false}>Hồ sơ của tôi</Link>
                </li>
                <li>
                  <Link href={urlFeed({ scope: "following", fandom: "" })} prefetch={false}>Đang theo dõi</Link>
                </li>
                <li>
                  <Link href="/notifications" prefetch={false}>Thông báo</Link>
                </li>
                <li>
                  <Link href="/leaderboard" prefetch={false}>Bảng xếp hạng</Link>
                </li>
              </ul>
            </section>
          ) : !dangTaiPhien ? (
            <section className="card cong-dong-toi">
              <p className="sidebar-tieu-de">Tham gia cộng đồng</p>
              <p className="hint">Đăng nhập bằng Google để đăng bài, thích, bình luận và theo dõi tác giả.</p>
              <Link href={`/login?next=${encodeURIComponent("/community")}`} className="btn btn-primary btn-sm" prefetch={false}>
                Đăng nhập
              </Link>
            </section>
          ) : null}
          {/* Du lieu THAT: tac gia xep theo luot nghe hop le; rong thi an. */}
          <TacGiaNoiBat />
        </aside>
      </div>
    </div>
  );
}

export default function CommunityPage() {
  // `useSearchParams` can mot ranh gioi Suspense de trang van dung duoc khi dung san.
  return (
    <Suspense fallback={<div className="page"><SkeletonList count={3} /></div>}>
      <BangTinCongDong />
    </Suspense>
  );
}
