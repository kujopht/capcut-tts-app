"use client";

/**
 * THƯ VIỆN FANFIC WORLD — Trung tâm duyệt nội dung công khai & Tủ sách cá nhân.
 *
 * Phân chia rành mạch 3 mục:
 * 1. 📖 Fanfic & Tiểu thuyết (Toàn bộ kho tác phẩm thật trên hệ thống: Naruto, One Piece, Conan...)
 * 2. 📚 Sách & Tuyển tập (Tuyển tập đặc biệt biên soạn theo mùa, trạng thái trung thực)
 * 3. 🔖 Tủ sách của tôi (Tiến trình đọc/nghe tiếp, truyện đang theo dõi, đã lưu)
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  social,
  type FollowedStory,
  type ContinueItem,
  type Novel,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { NovelCover } from "@/components/NovelCover";
import { EmptyState, ErrorState, ProgressBar, SkeletonList, formatDate } from "@/components/ui";
import { IconBook, IconLibrary, IconHeadphones, IconSparkles } from "@/components/Icons";
import {
  novelHasAudio,
  novelFandom,
  formatAuthor,
  formatChapterCount,
} from "@/lib/catalog";

type TopTab = "fanfic" | "books" | "personal";
type PersonalFilter = "all" | "continue" | "following" | "completed";
type AudioFilter = "all" | "audio" | "text";
type StatusFilter = "all" | "ongoing" | "completed";
type SortMode = "updated" | "chapters" | "title";

const NHAN_TRANG_THAI: Record<string, string> = {
  ongoing: "Đang ra",
  completed: "Hoàn thành",
  hiatus: "Tạm ngưng",
};

function dinhDangGio(giay: number): string {
  const m = Math.floor(giay / 60);
  const s = Math.floor(giay % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

function LibraryContent() {
  const { profile, loading: dangNapPhien, signIn } = useSession();
  const [testLoggingIn, setTestLoggingIn] = useState(false);
  const searchParams = useSearchParams();

  const tabParam = searchParams.get("tab");
  const defaultTab: TopTab =
    tabParam === "books"
      ? "books"
      : tabParam === "personal" || tabParam === "mine"
      ? "personal"
      : "fanfic";

  const [selectedTab, setSelectedTab] = useState<TopTab | null>(null);
  const topTab = selectedTab ?? defaultTab;

  const setTopTab = (tab: TopTab) => {
    setSelectedTab(tab);
  };

  // State bộ lọc cho Danh mục công khai
  const initialQuery = searchParams.get("q") ?? "";
  const initialFandom = (() => {
    const f = searchParams.get("fandom");
    if (f) return f;
    const tag = searchParams.get("tag");
    if (tag && tag.startsWith("fandom:")) return tag.replace("fandom:", "");
    if (tag && tag !== "all") return tag;
    return "all";
  })();

  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [fandomFilter, setFandomFilter] = useState(initialFandom);
  const [audioFilter, setAudioFilter] = useState<AudioFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("updated");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // State bộ lọc cho Tủ sách cá nhân
  const [personalFilter, setPersonalFilter] = useState<PersonalFilter>("all");

  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number; opacity: number }>({
    left: 0,
    width: 0,
    opacity: 0,
  });
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const PAGE_SIZE = 12;
  const [pageIndex, setPageIndex] = useState(0);
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState(initialQuery);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q !== null && q !== searchQuery) {
      setSearchQuery(q);
      setDebouncedSearchQuery(q);
    }
    const f = searchParams.get("fandom");
    const tag = searchParams.get("tag");
    const targetFandom = f ?? (tag && tag.startsWith("fandom:") ? tag.replace("fandom:", "") : tag ?? null);
    if (targetFandom !== null && targetFandom !== fandomFilter) {
      setFandomFilter(targetFandom);
    }
  }, [searchParams]);

  const CORE_FANDOMS = useMemo(() => [
    "Naruto",
    "One Piece",
    "Detective Conan",
    "Genshin Impact",
    "Fairy Tail",
    "Thể thao / Bóng rổ",
    "Sci-Fi / Warhammer",
  ], []);
  const [availableFandoms, setAvailableFandoms] = useState<string[]>(CORE_FANDOMS);

  useEffect(() => {
    api.novelTags().then((res) => {
      const set = new Set(CORE_FANDOMS);
      (res.tags || []).forEach((t) => {
        if (t.startsWith("fandom:")) {
          const clean = t.replace("fandom:", "").trim();
          if (clean && !clean.includes("Unresolved")) set.add(clean);
        }
      });
      setAvailableFandoms(Array.from(set));
    }).catch(() => {});
  }, [CORE_FANDOMS]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Reset trang khi thay đổi bộ lọc
  useEffect(() => {
    setPageIndex(0);
  }, [debouncedSearchQuery, fandomFilter, audioFilter, statusFilter, sortMode]);

  // Tải dữ liệu: Danh mục công khai phân trang ở máy chủ, kèm dữ liệu cá nhân nếu đã đăng nhập
  const nap = useCallback(async () => {
    const [publicNovelsRes, userFollowedRes, tiepTucRes] = await Promise.all([
      api.browseNovels({
        query: debouncedSearchQuery,
        fandom: fandomFilter === "all" ? undefined : fandomFilter,
        status: statusFilter === "all" ? undefined : statusFilter,
        audio: audioFilter === "all" ? undefined : audioFilter === "audio",
        sort: sortMode,
        limit: PAGE_SIZE,
        offset: pageIndex * PAGE_SIZE,
      }).catch(() => api.listNovels(false).catch(() => ({
        novels: [] as Novel[],
        count: 0,
        total: 0,
        limit: PAGE_SIZE,
        offset: 0,
        has_more: false,
      }))),
      profile ? social.followedStories(100, 0).catch(() => ({ novels: [] })) : Promise.resolve({ novels: [] }),
      profile
        ? api
            .getContinueProgress()
            .catch(() => ({ reading: null, listening: null, watching: null }))
        : Promise.resolve({ reading: null, listening: null, watching: null }),
    ]);

    return {
      novels: publicNovelsRes.novels,
      totalNovels: ("total" in publicNovelsRes ? publicNovelsRes.total : publicNovelsRes.novels.length) as number,
      hasMore: ("has_more" in publicNovelsRes ? publicNovelsRes.has_more : false) as boolean,
      followed: userFollowedRes.novels,
      continueProgress: tiepTucRes,
    };
  }, [debouncedSearchQuery, fandomFilter, audioFilter, statusFilter, sortMode, pageIndex, profile]);

  const { data, loading, error, reload } = useAsyncData(nap);

  const filteredPublicNovels = useMemo<Novel[]>(() => data?.novels ?? [], [data?.novels]);
  const totalPublicNovels = data?.totalNovels ?? 0;
  const hasMore = data?.hasMore ?? false;
  const allNovels = filteredPublicNovels;
  const followedStories = useMemo<FollowedStory[]>(() => data?.followed ?? [], [data?.followed]);
  const dangDoc = data?.continueProgress?.reading ?? null;
  const dangNghe = data?.continueProgress?.listening ?? null;
  const hasPersonalProgress = Boolean(dangDoc || dangNghe);

  // Bộ lọc tủ sách cá nhân
  const filteredPersonalStories = useMemo(() => {
    return followedStories.filter((n) => {
      if (personalFilter === "all") return true;
      if (personalFilter === "completed") return n.status === "completed";
      if (personalFilter === "following") return n.status !== "completed";
      if (personalFilter === "continue") {
        return (
          (dangDoc && dangDoc.novel_id === n.novel_id) ||
          (dangNghe && dangNghe.novel_id === n.novel_id)
        );
      }
      return true;
    });
  }, [followedStories, personalFilter, dangDoc, dangNghe]);

  // Cập nhật vị trí thanh trượt tab
  useEffect(() => {
    const el = tabRefs.current[topTab];
    if (el) {
      setIndicatorStyle({
        left: el.offsetLeft,
        width: el.offsetWidth,
        opacity: 1,
      });
    }
  }, [topTab, allNovels.length, followedStories.length]);

  return (
    <div className="page stack-3" data-hero-theme="library">
      {/* 1. Header Thư viện với Tab trượt phân tách rành mạch 3 mục */}
      <header className="ent-header">
        <div className="ent-header-copy">
          <div className="ent-header-eyebrow">
            <IconLibrary size={13} />
            <span>TRUNG TÂM NỘI DUNG FANFIC WORLD</span>
          </div>
          <h1 className="ent-header-title">Thư viện</h1>
          <p className="ent-header-lead">
            {topTab === "books"
              ? "Tuyển tập đặc biệt, ấn phẩm tuyển chọn và các tác phẩm văn học đang được biên soạn."
              : topTab === "personal"
              ? "Tủ sách cá nhân của bạn: tiến trình đọc dở, nghe tiếp và các tác phẩm đang theo dõi."
              : "Khám phá toàn bộ kho truyện chữ, fanfic chuyển ngữ và audiobook chất lượng cao."}
          </p>
        </div>

        {/* 3 Tabs độc lập: Fanfic & Tiểu thuyết | Sách & Tuyển tập | Tủ sách của tôi */}
        <div className="ent-mode-switch" role="tablist" aria-label="Phân mục thư viện">
          <div
            className="ent-mode-indicator dynamic"
            style={{
              transform: `translateX(${indicatorStyle.left}px)`,
              width: `${indicatorStyle.width}px`,
              opacity: indicatorStyle.opacity,
            }}
            aria-hidden="true"
          />
          <button
            ref={(el) => { tabRefs.current["fanfic"] = el; }}
            type="button"
            role="tab"
            aria-selected={topTab === "fanfic"}
            className={`ent-mode-tab ${topTab === "fanfic" ? "is-active" : ""}`}
            onClick={() => setTopTab("fanfic")}
          >
            <span aria-hidden="true">📖</span> Fanfic &amp; Tiểu thuyết ({totalPublicNovels})
          </button>
          <button
            ref={(el) => { tabRefs.current["books"] = el; }}
            type="button"
            role="tab"
            aria-selected={topTab === "books"}
            className={`ent-mode-tab ${topTab === "books" ? "is-active" : ""}`}
            onClick={() => setTopTab("books")}
          >
            <span aria-hidden="true">📚</span> Sách &amp; Tuyển tập
          </button>
          <button
            ref={(el) => { tabRefs.current["personal"] = el; }}
            type="button"
            role="tab"
            aria-selected={topTab === "personal"}
            className={`ent-mode-tab ${topTab === "personal" ? "is-active" : ""}`}
            onClick={() => setTopTab("personal")}
          >
            <span aria-hidden="true">🔖</span> Tủ sách của tôi {profile ? `(${followedStories.length})` : ""}
          </button>
        </div>
      </header>

      {/* 2. Nội dung thư viện theo tab được chọn */}
      <div key={topTab} className="ent-tab-panel">
        {loading && dangNapPhien ? (
          <SkeletonList count={4} />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : topTab === "fanfic" ? (
          /* ================================================================ */
          /* TAB A: FANFIC & TIỂU THUYẾT (KHO NỘI DUNG CÔNG KHAI THẬT)       */
          /* ================================================================ */
          <div className="stack-4">
            {/* Nhắc nhở đọc tiếp nếu người dùng đã đăng nhập và có tiến độ */}
            {hasPersonalProgress && (
              <aside className="lib-continue-callout" aria-label="Tiến trình đang đọc dở">
                <div className="lib-continue-callout-inner">
                  <span className="lib-continue-icon" aria-hidden="true">
                    {dangNghe ? "🎧" : "📖"}
                  </span>
                  <div className="lib-continue-text">
                    <strong>
                      Tiếp tục: {dangNghe ? dangNghe.novel_title : dangDoc?.novel_title}
                    </strong>
                    <span className="hint">
                      Chương {dangNghe ? dangNghe.chapter_order_index : dangDoc?.chapter_order_index} ·{" "}
                      {dangNghe ? dangNghe.chapter_title : dangDoc?.chapter_title}
                    </span>
                  </div>
                  <Link
                    href={`/chapters/${dangNghe ? dangNghe.chapter_id : dangDoc?.chapter_id}`}
                    className="btn btn-sm btn-primary"
                    prefetch={false}
                  >
                    {dangNghe ? "Nghe tiếp" : "Đọc tiếp"}
                  </Link>
                </div>
              </aside>
            )}

            {/* Bảng điều khiển bộ lọc & tìm kiếm */}
            <div className="lib-filter-controls" role="toolbar" aria-label="Tìm kiếm và lọc tác phẩm">
              {/* Hàng 1: Ô tìm kiếm + Sắp xếp + Chế độ hiển thị */}
              <div className="lib-filter-row">
                <input
                  type="search"
                  className="lib-search-input"
                  placeholder="Tìm theo tên tác phẩm, tác giả, thể loại..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  aria-label="Tìm kiếm tác phẩm"
                />

                <div className="lib-filter-group">
                  <label htmlFor="lib-sort-select" className="hint" style={{ fontSize: "0.8rem" }}>
                    Sắp xếp:
                  </label>
                  <select
                    id="lib-sort-select"
                    className="lib-sort-select"
                    value={sortMode}
                    onChange={(e) => setSortMode(e.target.value as SortMode)}
                    aria-label="Sắp xếp danh sách"
                  >
                    <option value="updated">Mới cập nhật</option>
                    <option value="chapters">Số chương (Nhiều nhất)</option>
                    <option value="title">Tên tác phẩm (A–Z)</option>
                  </select>

                  <div className="lib-view-toggle" role="group" aria-label="Chế độ hiển thị">
                    <button
                      type="button"
                      className={`lib-view-btn ${viewMode === "grid" ? "is-active" : ""}`}
                      onClick={() => setViewMode("grid")}
                      aria-pressed={viewMode === "grid"}
                      title="Hiển thị dạng ô (Grid)"
                    >
                      ⊞ Dạng ô
                    </button>
                    <button
                      type="button"
                      className={`lib-view-btn ${viewMode === "list" ? "is-active" : ""}`}
                      onClick={() => setViewMode("list")}
                      aria-pressed={viewMode === "list"}
                      title="Hiển thị dạng danh sách (List)"
                    >
                      ☰ Danh sách
                    </button>
                  </div>
                </div>
              </div>

              {/* Hàng 2: Lọc theo Vũ trụ / Fandom */}
              <div className="lib-filter-row">
                <div className="lib-filter-group">
                  <span className="hint" style={{ fontSize: "0.8rem", marginRight: "4px" }}>
                    Vũ trụ:
                  </span>
                  <button
                    type="button"
                    className={`ent-mood-chip ${fandomFilter === "all" ? "is-active" : ""}`}
                    onClick={() => setFandomFilter("all")}
                  >
                    Tất cả ({totalPublicNovels})
                  </button>
                  {availableFandoms.map((f) => (
                    <button
                      key={f}
                      type="button"
                      className={`ent-mood-chip ${fandomFilter === f ? "is-active" : ""}`}
                      onClick={() => setFandomFilter(f)}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </div>

              {/* Hàng 3: Lọc Audio & Trạng thái */}
              <div className="lib-filter-row">
                <div className="lib-filter-group">
                  <span className="hint" style={{ fontSize: "0.8rem", marginRight: "4px" }}>
                    Định dạng:
                  </span>
                  <button
                    type="button"
                    className={`ent-mood-chip ${audioFilter === "all" ? "is-active" : ""}`}
                    onClick={() => setAudioFilter("all")}
                  >
                    Tất cả
                  </button>
                  <button
                    type="button"
                    className={`ent-mood-chip ${audioFilter === "audio" ? "is-active" : ""}`}
                    onClick={() => setAudioFilter("audio")}
                  >
                    🎧 Có Audio
                  </button>
                  <button
                    type="button"
                    className={`ent-mood-chip ${audioFilter === "text" ? "is-active" : ""}`}
                    onClick={() => setAudioFilter("text")}
                  >
                    📖 Chỉ văn bản
                  </button>

                  <span className="hint" style={{ fontSize: "0.8rem", margin: "0 4px 0 12px" }}>
                    Trạng thái:
                  </span>
                  <button
                    type="button"
                    className={`ent-mood-chip ${statusFilter === "all" ? "is-active" : ""}`}
                    onClick={() => setStatusFilter("all")}
                  >
                    Tất cả
                  </button>
                  <button
                    type="button"
                    className={`ent-mood-chip ${statusFilter === "ongoing" ? "is-active" : ""}`}
                    onClick={() => setStatusFilter("ongoing")}
                  >
                    Đang ra
                  </button>
                  <button
                    type="button"
                    className={`ent-mood-chip ${statusFilter === "completed" ? "is-active" : ""}`}
                    onClick={() => setStatusFilter("completed")}
                  >
                    Hoàn thành
                  </button>
                </div>
              </div>
            </div>

            {/* Danh sách hiển thị kết quả */}
            <section className="stack-2" aria-label="Danh sách tác phẩm">
              <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h2 className="section-title">
                  Tác phẩm Fanfic &amp; Tiểu thuyết
                  <span className="hint"> · {totalPublicNovels} tác phẩm</span>
                </h2>
              </div>

              {filteredPublicNovels.length === 0 ? (
                <EmptyState
                  icon="🔍"
                  title="Không tìm thấy tác phẩm phù hợp"
                  hint="Hãy thử đổi từ khóa tìm kiếm hoặc chọn lại các bộ lọc Vũ trụ / Định dạng."
                  action={
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setSearchQuery("");
                        setFandomFilter("all");
                        setAudioFilter("all");
                        setStatusFilter("all");
                      }}
                    >
                      Đặt lại bộ lọc
                    </button>
                  }
                />
              ) : viewMode === "grid" ? (
                <div className="lib-story-grid">
                  {filteredPublicNovels.map((n) => {
                    const hasAudio = novelHasAudio(n);
                    const fandom = novelFandom(n);
                    const author = formatAuthor(n);
                    const chapterCount = formatChapterCount(n.external_chapter_count);

                    return (
                      <Link
                        key={n.novel_id}
                        href={`/novels/${n.novel_id}`}
                        className="lib-card"
                        prefetch={false}
                      >
                        <div className="lib-card-cover-wrap">
                          <NovelCover
                            novelId={n.novel_id}
                            title={n.title}
                            coverUrl={n.cover_url}
                            size="portrait"
                          />
                          <span className={`lib-card-status-badge status-${n.status}`}>
                            {NHAN_TRANG_THAI[n.status] ?? n.status}
                          </span>
                          <span className="lib-badge-fandom-corner">
                            {fandom}
                          </span>
                          {hasAudio && (
                            <span className="lib-badge-audio-pill">
                              🎧 Audio
                            </span>
                          )}
                        </div>

                        <div className="lib-card-body">
                          <h3 className="lib-card-title clamp-2" title={n.title}>
                            {n.title}
                          </h3>
                          <div className="lib-card-meta">
                            <span className="lib-card-author clamp-1">✍️ {author}</span>
                            <span className="hint">
                              📚 {chapterCount}
                              {n.updated_at || n.created_at
                                ? ` · ${formatDate(n.updated_at || n.created_at)}`
                                : ""}
                            </span>
                          </div>
                          {n.tags && n.tags.length > 0 ? (
                            <div className="story-tags">
                              {n.tags
                                .filter((t) => !t.startsWith("work:") && t !== "imported")
                                .slice(0, 2)
                                .map((t) => (
                                  <span key={t} className="chip chip-static">
                                    {t}
                                  </span>
                                ))}
                            </div>
                          ) : null}
                        </div>

                        <div className="lib-card-footer">
                          <span className="btn btn-sm btn-primary btn-block">
                            {hasAudio ? "🎧 Nghe & Đọc" : "📖 Đọc tác phẩm"}
                          </span>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              ) : (
                <div className="list list-gon">
                  {filteredPublicNovels.map((n) => {
                    const hasAudio = novelHasAudio(n);
                    const fandom = novelFandom(n);
                    const author = formatAuthor(n);
                    const chapterCount = formatChapterCount(n.external_chapter_count);

                    return (
                      <div key={n.novel_id} className="list-item">
                        <NovelCover
                          novelId={n.novel_id}
                          title={n.title}
                          coverUrl={n.cover_url}
                          size="thumb"
                        />
                        <span className="stack-1 list-main">
                          <Link href={`/novels/${n.novel_id}`} className="truncate list-title" prefetch={false}>
                            {n.title}
                          </Link>
                          <span className="hint" style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                            <span className="lib-badge-fandom">{fandom}</span>
                            <span>✍️ {author}</span>
                            <span>· 📚 {chapterCount}</span>
                            {hasAudio ? (
                              <span className="lib-badge-audio">🎧 Có Audio</span>
                            ) : (
                              <span className="lib-badge-text-only">📖 Văn bản</span>
                            )}
                            <span>· {NHAN_TRANG_THAI[n.status] ?? n.status}</span>
                          </span>
                        </span>
                        <span className="list-actions">
                          <Link className="btn btn-sm btn-primary" href={`/novels/${n.novel_id}`} prefetch={false}>
                            {hasAudio ? "🎧 Nghe" : "📖 Đọc"}
                          </Link>
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Thanh phân trang ở máy chủ */}
              {totalPublicNovels > PAGE_SIZE && (
                <nav
                  className="lib-pagination"
                  aria-label="Phân trang danh mục"
                  style={{
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    gap: "16px",
                    marginTop: "32px",
                    padding: "16px 0",
                  }}
                >
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    disabled={pageIndex === 0 || loading}
                    onClick={() => {
                      setPageIndex((p) => Math.max(0, p - 1));
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    aria-label="Trang trước"
                  >
                    ← Trang trước
                  </button>
                  <span className="hint" style={{ fontSize: "0.85rem", fontWeight: 500 }}>
                    Trang {pageIndex + 1} / {Math.max(1, Math.ceil(totalPublicNovels / PAGE_SIZE))}
                  </span>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    disabled={!hasMore || loading || (pageIndex + 1) * PAGE_SIZE >= totalPublicNovels}
                    onClick={() => {
                      setPageIndex((p) => p + 1);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    aria-label="Trang sau"
                  >
                    Trang sau →
                  </button>
                </nav>
              )}
            </section>
          </div>
        ) : topTab === "books" ? (
          /* ================================================================ */
          /* TAB B: SÁCH & TUYỂN TẬP (TRẠNG THÁI BIÊN TẬP TRUNG THỰC)        */
          /* ================================================================ */
          <div className="stack-4">
            <EmptyState
              icon="📚"
              title="Tuyển tập & Tuyển tập đặc biệt đang được tuyển chọn"
              hint="Đội ngũ biên tập đang chuẩn bị các tuyển tập fanfic kinh điển, sách văn học và tác phẩm chuyển thể cao cấp theo chủ đề. Không có dữ liệu giả lập — các ấn phẩm sẽ xuất hiện tại đây ngay khi hoàn thành biên tập."
              action={
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setTopTab("fanfic")}
                >
                  <IconBook size={15} /> Khám phá Fanfic &amp; Tiểu thuyết ({allNovels.length})
                </button>
              }
            />
          </div>
        ) : (
          /* ================================================================ */
          /* TAB C: TỦ SÁCH CÁ NHÂN (TIẾN TRÌNH & THEO DÕI)                   */
          /* ================================================================ */
          <div className="stack-4">
            {!profile ? (
              <div className="lib-guest-banner" role="status">
                <div className="lib-guest-text">
                  <strong>Đăng nhập để quản lý tủ sách cá nhân</strong>
                  <p>
                    Lưu giữ các tác phẩm bạn đang theo dõi và tự động đồng bộ vị trí đọc dở, nghe tiếp trên mọi thiết bị.
                  </p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                  <Link className="btn btn-primary btn-sm" href="/login?next=/library?tab=personal" prefetch={false}>
                    Đăng nhập
                  </Link>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={testLoggingIn}
                    onClick={async () => {
                      try {
                        setTestLoggingIn(true);
                        await signIn("kujopht@gmail.com", "Password123!");
                      } catch {
                        try {
                          await signIn("reader@fanfic.vn", "Password123!");
                        } catch {
                          // ignore
                        }
                      } finally {
                        setTestLoggingIn(false);
                      }
                    }}
                  >
                    {testLoggingIn ? "Đang đăng nhập..." : "⚡ Đăng nhập nhanh (Test)"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* Thanh lọc trạng thái theo dõi */}
                <div className="ent-mood-row" role="toolbar" aria-label="Lọc tủ sách cá nhân">
                  <span className="ent-mood-label">Lọc:</span>
                  <button
                    type="button"
                    className={`ent-mood-chip ${personalFilter === "all" ? "is-active" : ""}`}
                    onClick={() => setPersonalFilter("all")}
                  >
                    Tất cả ({followedStories.length})
                  </button>
                  {hasPersonalProgress && (
                    <button
                      type="button"
                      className={`ent-mood-chip ${personalFilter === "continue" ? "is-active" : ""}`}
                      onClick={() => setPersonalFilter("continue")}
                    >
                      ▶ Đang đọc / Nghe dở
                    </button>
                  )}
                  <button
                    type="button"
                    className={`ent-mood-chip ${personalFilter === "following" ? "is-active" : ""}`}
                    onClick={() => setPersonalFilter("following")}
                  >
                    Đang theo dõi
                  </button>
                  <button
                    type="button"
                    className={`ent-mood-chip ${personalFilter === "completed" ? "is-active" : ""}`}
                    onClick={() => setPersonalFilter("completed")}
                  >
                    Đã lưu / Hoàn thành
                  </button>
                </div>

                {/* Khối Tiến trình đọc & nghe tiếp */}
                {hasPersonalProgress && (personalFilter === "all" || personalFilter === "continue") && (
                  <section className="stack-2" aria-labelledby="personal-continue-heading">
                    <div className="section-head">
                      <h2 className="section-title section-title-icon" id="personal-continue-heading">
                        <IconBook size={18} /> Đang đọc &amp; Nghe tiếp
                      </h2>
                    </div>
                    <div className="bento-grid">
                      {dangDoc && (
                        <Link href={`/chapters/${dangDoc.chapter_id}`} className="progress-card" prefetch={false}>
                          <span className="progress-card-icon" aria-hidden="true">📖</span>
                          <span className="progress-card-body">
                            <strong className="clamp-1">{dangDoc.novel_title}</strong>
                            <span className="progress-card-meta">
                              Chương {dangDoc.chapter_order_index} · {dangDoc.chapter_title}
                            </span>
                          </span>
                          <span className="btn btn-sm btn-primary" aria-hidden="true">
                            Đọc tiếp
                          </span>
                        </Link>
                      )}

                      {dangNghe && (
                        <Link href={`/chapters/${dangNghe.chapter_id}`} className="progress-card" prefetch={false}>
                          <span className="progress-card-icon" aria-hidden="true">🎧</span>
                          <span className="progress-card-body">
                            <strong className="clamp-1">{dangNghe.novel_title}</strong>
                            <span className="progress-card-meta">
                              Chương {dangNghe.chapter_order_index} · {dangNghe.chapter_title}
                              {dangNghe.position_seconds ? ` · ${dinhDangGio(dangNghe.position_seconds)}` : ""}
                            </span>
                            {dangNghe.position_seconds && dangNghe.duration_seconds ? (
                              <ProgressBar
                                percent={Math.min(
                                  100,
                                  Math.round((dangNghe.position_seconds / dangNghe.duration_seconds) * 100)
                                )}
                                label="Tiến trình nghe"
                              />
                            ) : null}
                          </span>
                          <span className="btn btn-sm btn-primary" aria-hidden="true">
                            Nghe tiếp
                          </span>
                        </Link>
                      )}
                    </div>
                  </section>
                )}

                {/* Khối Danh sách truyện đang theo dõi */}
                <section className="stack-2" aria-label="Truyện đang theo dõi">
                  <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h2 className="section-title">
                      Tác phẩm theo dõi
                      {filteredPersonalStories.length > 0 && (
                        <span className="hint"> · {filteredPersonalStories.length} tác phẩm</span>
                      )}
                    </h2>
                  </div>

                  {filteredPersonalStories.length === 0 ? (
                    <EmptyState
                      icon="⭐"
                      title="Tủ sách của bạn chưa có tác phẩm nào"
                      hint="Bấm nút “Theo dõi” ở các tác phẩm yêu thích để cập nhật chương mới và lưu vào tủ sách cá nhân."
                      action={
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => setTopTab("fanfic")}
                        >
                          <IconBook size={15} /> Khám phá kho truyện ({allNovels.length})
                        </button>
                      }
                    />
                  ) : (
                    <div className="lib-story-grid">
                      {filteredPersonalStories.map((n) => {
                        const isReading = dangDoc && dangDoc.novel_id === n.novel_id;
                        const isListening = dangNghe && dangNghe.novel_id === n.novel_id;

                        return (
                          <Link
                            key={n.novel_id}
                            href={`/novels/${n.novel_id}`}
                            className="lib-card"
                            prefetch={false}
                          >
                            <div className="lib-card-cover-wrap">
                              <NovelCover
                                novelId={n.novel_id}
                                title={n.title}
                                coverUrl={n.cover_url}
                                size="portrait"
                              />
                              <span className={`lib-card-status-badge status-${n.status}`}>
                                {NHAN_TRANG_THAI[n.status] ?? n.status}
                              </span>
                              {isReading ? (
                                <span className="lib-card-progress-pill">▶ Đang đọc dở</span>
                              ) : isListening ? (
                                <span className="lib-card-progress-pill is-listening">🎧 Đang nghe dở</span>
                              ) : null}
                            </div>
                            <div className="lib-card-body">
                              <h3 className="lib-card-title clamp-2" title={n.title}>
                                {n.title}
                              </h3>
                              <div className="lib-card-meta">
                                {n.external_author_name ? (
                                  <span className="lib-card-author clamp-1">✍️ {n.external_author_name}</span>
                                ) : null}
                                {n.updated_at ? (
                                  <span className="hint">Cập nhật {formatDate(n.updated_at)}</span>
                                ) : null}
                              </div>
                            </div>
                            <div className="lib-card-footer">
                              <span className="btn btn-sm btn-primary btn-block">
                                {isReading ? "Đọc tiếp" : isListening ? "Nghe tiếp" : "Mở tác phẩm"}
                              </span>
                            </div>
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ThuVienPage() {
  return (
    <Suspense fallback={<SkeletonList count={4} />}>
      <LibraryContent />
    </Suspense>
  );
}
