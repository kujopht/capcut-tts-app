"use client";

/**
 * THƯ VIỆN CỦA NGƯỜI ĐỌC — Trung tâm nội dung cá nhân (Đọc & Nghe).
 *
 * Phân chia rành mạch 2 mục chuyên biệt:
 * 1. 📖 Fanfic & Tiểu thuyết (Truyện chữ nhiều kỳ, sáng tác cộng đồng)
 * 2. 📚 Sách & Tuyển tập (Sách tham khảo, văn học, non-fiction)
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { api, social, type FollowedStory, type ContinueItem } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { NovelCover } from "@/components/NovelCover";
import { EmptyState, ErrorState, ProgressBar, SkeletonList, formatDate } from "@/components/ui";
import { IconBook, IconLibrary, IconHeadphones, IconSparkles } from "@/components/Icons";

type TopTab = "fanfic" | "books";
type BehaviorFilter = "all" | "continue" | "following" | "completed";

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

function isBookItem(item: FollowedStory): boolean {
  const text = `${item.title} ${item.description} ${(item.tags ?? []).join(" ")}`.toLowerCase();
  return (
    text.includes("sách") ||
    text.includes("book") ||
    text.includes("văn học") ||
    text.includes("tác phẩm") ||
    text.includes("kinh điển") ||
    text.includes("tuyển tập") ||
    text.includes("non-fiction")
  );
}

function isBookContinue(item: ContinueItem | null): boolean {
  if (!item) return false;
  const text = `${item.novel_title} ${item.chapter_title}`.toLowerCase();
  return (
    text.includes("sách") ||
    text.includes("book") ||
    text.includes("văn học") ||
    text.includes("tác phẩm") ||
    text.includes("kinh điển") ||
    text.includes("tuyển tập") ||
    text.includes("non-fiction")
  );
}

function LibraryContent() {
  const { profile, loading: dangNapPhien, signIn } = useSession();
  const [testLoggingIn, setTestLoggingIn] = useState(false);
  const searchParams = useSearchParams();

  const tabParam = searchParams.get("tab");
  const defaultTab: TopTab = tabParam === "books" ? "books" : "fanfic";
  const [selectedTab, setSelectedTab] = useState<TopTab | null>(null);
  const topTab = selectedTab ?? defaultTab;
  const setTopTab = (tab: TopTab) => {
    setSelectedTab(tab);
    setBehaviorFilter("all");
  };

  const [behaviorFilter, setBehaviorFilter] = useState<BehaviorFilter>("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number; opacity: number }>({
    left: 0,
    width: 0,
    opacity: 0,
  });
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const nap = useCallback(async () => {
    const [theoDoi, tiepTuc] = await Promise.all([
      social.followedStories(50, 0),
      api
        .getContinueProgress()
        .catch(() => ({ reading: null, listening: null, watching: null })),
    ]);
    return { theoDoi, tiepTuc };
  }, []);

  const { data, loading, error, reload } = useAsyncData(nap, {
    enabled: Boolean(profile),
  });

  const ds: FollowedStory[] = data?.theoDoi?.novels ?? [];
  const dsBooks = ds.filter((item) => isBookItem(item));
  const dsFanfics = ds.filter((item) => !isBookItem(item));

  useEffect(() => {
    const el = tabRefs.current[topTab];
    if (el) {
      setIndicatorStyle({
        left: el.offsetLeft,
        width: el.offsetWidth,
        opacity: 1,
      });
    }
  }, [topTab, dsFanfics.length, dsBooks.length]);

  const isDataLoading = Boolean(profile) && loading;

  if (dangNapPhien) return <SkeletonList count={4} />;

  const dangDoc = data?.tiepTuc?.reading ?? null;
  const dangNghe = data?.tiepTuc?.listening ?? null;

  // Determine items based on active top-level tab
  const currentTabStories = topTab === "books" ? dsBooks : dsFanfics;

  // Check if reading/listening progress belongs to the active tab
  const showReadingProgress = dangDoc && (topTab === "books" ? isBookContinue(dangDoc) : !isBookContinue(dangDoc));
  const showListeningProgress = dangNghe && (topTab === "books" ? isBookContinue(dangNghe) : !isBookContinue(dangNghe));
  const hasTabProgress = Boolean(showReadingProgress || showListeningProgress);

  // Apply behavior filter
  const filteredStories = currentTabStories.filter((n) => {
    if (behaviorFilter === "all") return true;
    if (behaviorFilter === "completed") return n.status === "completed";
    if (behaviorFilter === "following") return n.status !== "completed";
    if (behaviorFilter === "continue") {
      return (
        (dangDoc && dangDoc.novel_id === n.novel_id) ||
        (dangNghe && dangNghe.novel_id === n.novel_id)
      );
    }
    return true;
  });

  return (
    <div className="page stack-3" data-hero-theme="library">
      {/* 1. Header Thư viện với Tab trượt phân tách rành mạch 2 mục */}
      <header className="ent-header">
        <div className="ent-header-copy">
          <div className="ent-header-eyebrow">
            <IconLibrary size={13} />
            <span>THƯ VIỆN CÁ NHÂN</span>
          </div>
          <h1 className="ent-header-title">Thư viện</h1>
          <p className="ent-header-lead">
            {topTab === "books"
              ? "Tủ sách tuyển tập, sách văn học và tác phẩm nghiên cứu bạn đã lưu."
              : "Bộ sưu tập truyện chữ nhiều kỳ, fanfic và tiểu thuyết sáng tác của bạn."}
          </p>
        </div>

        {/* 2 Tabs độc lập: Fanfic & Tiểu thuyết | Sách & Tuyển tập */}
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
            <span aria-hidden="true">📖</span> Fanfic &amp; Tiểu thuyết ({dsFanfics.length})
          </button>
          <button
            ref={(el) => { tabRefs.current["books"] = el; }}
            type="button"
            role="tab"
            aria-selected={topTab === "books"}
            className={`ent-mode-tab ${topTab === "books" ? "is-active" : ""}`}
            onClick={() => setTopTab("books")}
          >
            <span aria-hidden="true">📚</span> Sách &amp; Tuyển tập ({dsBooks.length})
          </button>
        </div>
      </header>

      {/* 2. Nội dung thư viện với hiệu ứng chuyển tab mượt mà */}
      <div key={topTab} className="ent-tab-panel">

        {/* Toolbar lọc trạng thái */}
        <div className="ent-mood-row" role="toolbar" aria-label="Lọc theo trạng thái">
          <span className="ent-mood-label">Lọc:</span>
          <button
            type="button"
            className={`ent-mood-chip ${behaviorFilter === "all" ? "is-active" : ""}`}
            onClick={() => setBehaviorFilter("all")}
          >
            Tất cả ({currentTabStories.length})
          </button>
          {hasTabProgress ? (
            <button
              type="button"
              className={`ent-mood-chip ${behaviorFilter === "continue" ? "is-active" : ""}`}
              onClick={() => setBehaviorFilter("continue")}
            >
              ▶ Đang đọc / Nghe dở
            </button>
          ) : null}
          <button
            type="button"
            className={`ent-mood-chip ${behaviorFilter === "following" ? "is-active" : ""}`}
            onClick={() => setBehaviorFilter("following")}
          >
            Đang theo dõi
          </button>
          <button
            type="button"
            className={`ent-mood-chip ${behaviorFilter === "completed" ? "is-active" : ""}`}
            onClick={() => setBehaviorFilter("completed")}
          >
            Đã lưu / Hoàn thành
          </button>
        </div>

        {!profile && (
          <div className="lib-guest-banner" role="status">
            <div className="lib-guest-text">
              <strong>Đăng nhập để mở toàn bộ thư viện</strong>
              <p>
                Thư viện lưu giữ những truyện, sách bạn theo dõi và vị trí đang đọc dở trên mọi thiết bị.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
              <Link className="btn btn-primary btn-sm" href="/login?next=/library" prefetch={false}>
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
        )}

        {isDataLoading ? (
          <SkeletonList count={4} />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : (
          <div className="stack-4">
            {/* Tiến trình đọc/nghe dở của danh mục hiện tại */}
            {hasTabProgress && (behaviorFilter === "all" || behaviorFilter === "continue") ? (
              <section className="stack-2" aria-labelledby="lib-continue-heading">
                <div className="section-head">
                  <h2 className="section-title section-title-icon" id="lib-continue-heading">
                    <IconBook size={18} /> Đang đọc &amp; Nghe tiếp
                  </h2>
                </div>
                <div className="bento-grid">
                  {showReadingProgress && dangDoc ? (
                    <Link href={`/chapters/${dangDoc.chapter_id}`} className="progress-card">
                      <span className="progress-card-icon" aria-hidden="true">
                        📖
                      </span>
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
                  ) : null}

                  {showListeningProgress && dangNghe ? (
                    <Link href={`/chapters/${dangNghe.chapter_id}`} className="progress-card">
                      <span className="progress-card-icon" aria-hidden="true">
                        🎧
                      </span>
                      <span className="progress-card-body">
                        <strong className="clamp-1">{dangNghe.novel_title}</strong>
                        <span className="progress-card-meta">
                          Chương {dangNghe.chapter_order_index} · {dangNghe.chapter_title}
                          {dangNghe.position_seconds
                            ? ` · ${dinhDangGio(dangNghe.position_seconds)}`
                            : ""}
                        </span>
                        {dangNghe.position_seconds && dangNghe.duration_seconds ? (
                          <ProgressBar
                            percent={Math.min(
                              100,
                              Math.round(
                                (dangNghe.position_seconds / dangNghe.duration_seconds) * 100
                              )
                            )}
                            label="Tiến trình nghe"
                          />
                        ) : null}
                      </span>
                      <span className="btn btn-sm btn-primary" aria-hidden="true">
                        Nghe tiếp
                      </span>
                    </Link>
                  ) : null}
                </div>
              </section>
            ) : null}

            {/* Danh sách tác phẩm của danh mục được chọn */}
            <section className="stack-2" aria-label={topTab === "books" ? "Danh sách sách" : "Danh sách fanfic"}>
              <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                <h2 className="section-title">
                  {topTab === "books" ? "Tủ Sách & Tuyển tập" : "Fanfic & Tiểu thuyết"}
                  {filteredStories.length ? (
                    <span className="hint"> · {filteredStories.length} tác phẩm</span>
                  ) : null}
                </h2>
                {filteredStories.length > 0 ? (
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
                ) : null}
              </div>

              {filteredStories.length === 0 ? (
                <EmptyState
                  icon={topTab === "books" ? "📚" : "📖"}
                  title={
                    topTab === "books"
                      ? "Tủ sách của bạn hiện chưa có tác phẩm nào"
                      : "Chưa có bộ fanfic hay tiểu thuyết nào được theo dõi"
                  }
                  hint={
                    topTab === "books"
                      ? "Bấm nút “Theo dõi” ở các ấn phẩm, sách văn học hoặc tuyển tập để lưu vào tủ sách cá nhân."
                      : "Khám phá kho truyện chữ cộng đồng và bấm “Theo dõi” để lưu truyện vào danh sách đọc."
                  }
                  action={
                    <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
                      <IconBook size={15} /> {topTab === "books" ? "Tìm sách hay" : "Khám phá truyện"}
                    </Link>
                  }
                />
              ) : viewMode === "grid" ? (
                <div className="lib-story-grid">
                  {filteredStories.map((n) => {
                    const isCurrentlyReading = dangDoc && dangDoc.novel_id === n.novel_id;
                    const isCurrentlyListening = dangNghe && dangNghe.novel_id === n.novel_id;
                    return (
                      <Link
                        key={n.novel_id}
                        href={`/novels/${n.novel_id}`}
                        className="lib-card"
                      >
                        <div className="lib-card-cover-wrap">
                          <NovelCover
                            novelId={n.novel_id}
                            title={n.title}
                            size="card"
                          />
                          <span className={`lib-card-status-badge status-${n.status}`}>
                            {NHAN_TRANG_THAI[n.status] ?? n.status}
                          </span>
                          {isCurrentlyReading ? (
                            <span className="lib-card-progress-pill">
                              ▶ Đang đọc dở
                            </span>
                          ) : isCurrentlyListening ? (
                            <span className="lib-card-progress-pill is-listening">
                              🎧 Đang nghe dở
                            </span>
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
                          {n.tags && n.tags.length > 0 ? (
                            <div className="story-tags">
                              {n.tags.slice(0, 2).map((t) => (
                                <span key={t} className="chip chip-static">
                                  {t}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                        <div className="lib-card-footer">
                          <span className="btn btn-sm btn-primary btn-block">
                            {isCurrentlyReading
                              ? "Đọc tiếp"
                              : isCurrentlyListening
                                ? "Nghe tiếp"
                                : "Mở tác phẩm"}
                          </span>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              ) : (
                <div className="list list-gon">
                  {filteredStories.map((n) => (
                    <div key={n.novel_id} className="list-item">
                      <NovelCover novelId={n.novel_id} title={n.title} size="thumb" />
                      <span className="stack-2 list-main">
                        <Link href={`/novels/${n.novel_id}`} className="truncate list-title">
                          {n.title}
                        </Link>
                        <span className="hint">
                          {NHAN_TRANG_THAI[n.status] ?? n.status}
                          {n.external_author_name ? ` · ${n.external_author_name}` : ""}
                          {n.updated_at ? ` · ${formatDate(n.updated_at)}` : ""}
                        </span>
                      </span>
                      <span className="list-actions">
                        <Link className="btn btn-sm btn-primary" href={`/novels/${n.novel_id}`}>
                          {dangDoc && dangDoc.novel_id === n.novel_id ? "Đọc tiếp" : "Mở"}
                        </Link>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
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
