"use client";

/**
 * Hai tab của trang cá nhân: Truyện và Bài viết.
 *
 * TRUYỆN đã có sẵn trong lần gọi hồ sơ; BÀI VIẾT chỉ tải khi tab đó được mở.
 * Một trang cá nhân mở ra để xem truyện — tải luôn bài viết là một truy vấn cho
 * thứ phần lớn người xem không bấm vào.
 *
 * `role="tablist"` thật, không phải hai cái nút trông giống tab: trình đọc màn
 * hình cần biết đây là một bộ tab để đọc ra "tab 2 trên 2", và mũi tên trái/phải
 * phải chuyển tab được. Hai cái nút thường thì không cho cả hai điều đó.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  social as apiSocial,
  type Achievement,
  type Novel,
  type Post,
  type ServerLimits,
} from "@/lib/api";
import { StoryCard } from "@/components/StoryCard";
import { PostCard } from "@/components/PostCard";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui";

type Tab = "bai" | "truyen" | "thanh-tuu";

/** Thu tu theo brief Social & Play V1: bai viet, truyen da xuat ban, thanh tuu. */
const TABS: ReadonlyArray<{ key: Tab; label: string }> = [
  { key: "bai", label: "Bài viết" },
  { key: "truyen", label: "Truyện" },
  { key: "thanh-tuu", label: "Thành tựu" },
];

export function ProfileTabs({
  userId,
  novels,
  isAuthor,
  postCount,
  achievements = [],
}: {
  userId: string;
  novels: Novel[];
  isAuthor: boolean;
  postCount: number;
  /** Thanh tuu CONG KHAI — chi hien nhung cai da mo. */
  achievements?: Achievement[];
}) {
  // Tac gia co truyen thi mo tab Truyen truoc; con lai la Bai viet.
  const [tab, setTab] = useState<Tab>(isAuthor && novels.length ? "truyen" : "bai");
  const daMo = achievements.filter((a) => a.unlocked);
  const [bai, setBai] = useState<Post[] | null>(null);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [loi, setLoi] = useState("");
  const nutRef = useRef<Map<Tab, HTMLButtonElement>>(new Map());

  const taiBai = useCallback(() => {
    setLoi("");
    apiSocial
      .userPosts(userId)
      .then((r) => setBai(r.items))
      .catch((e) => {
        setBai([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được bài viết.");
      });
  }, [userId]);

  /* Chỉ tải khi tab Bài viết được mở, và chỉ MỘT lần. */
  useEffect(() => {
    if (tab !== "bai" || bai !== null) return;
    // `queueMicrotask`: `taiBai()` mo dau bang `setLoi("")`. Xem
    // `app/community/page.tsx`.
    queueMicrotask(taiBai);
  }, [tab, bai, taiBai]);

  useEffect(() => {
    if (tab !== "bai" || limits !== null) return;
    apiSocial.limits().then(setLimits).catch(() => {});
  }, [tab, limits]);

  /* Mũi tên trái/phải chuyển tab — hành vi mà `role="tablist"` hứa với người
     dùng bàn phím. Không có nó thì cái vai trò đó là một lời hứa suông. */
  const banPhim = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = TABS.findIndex((t) => t.key === tab);
    const j = (i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
    const moi = TABS[j].key;
    setTab(moi);
    nutRef.current.get(moi)?.focus();
  }, [tab]);

  return (
    <section className="stack ho-so-tabs">
      <div role="tablist" aria-label="Nội dung của người này" className="tab-hang">
        {TABS.map((t) => (
          <button
            key={t.key}
            ref={(el) => {
              if (el) nutRef.current.set(t.key, el);
              else nutRef.current.delete(t.key);
            }}
            type="button"
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            /* Chỉ tab đang chọn nằm trong luồng Tab — đúng mẫu tablist: Tab đi
               vào bộ tab, rồi mũi tên di chuyển trong đó. */
            tabIndex={tab === t.key ? 0 : -1}
            className={tab === t.key ? "tab-nut tab-chon" : "tab-nut"}
            onClick={() => setTab(t.key)}
            onKeyDown={banPhim}
          >
            {t.label}
            <span className="hint tab-so">
              {t.key === "truyen" ? novels.length : t.key === "bai" ? postCount : daMo.length}
            </span>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id="panel-truyen"
        aria-labelledby="tab-truyen"
        hidden={tab !== "truyen"}
      >
        {novels.length === 0 ? (
          <EmptyState
            icon="📖"
            title={
              isAuthor
                ? "Chưa có truyện nào được xuất bản"
                : "Người này chưa xuất bản truyện nào"
            }
            hint="Bản nháp không hiện ở trang công khai."
          />
        ) : (
          <div className="story-grid">
            {novels.map((n) => (
              <StoryCard key={n.novel_id} novel={n} />
            ))}
          </div>
        )}
      </div>

      <div
        role="tabpanel"
        id="panel-bai"
        aria-labelledby="tab-bai"
        hidden={tab !== "bai"}
      >
        {loi ? <ErrorState message={loi} onRetry={taiBai} /> : null}
        {bai === null && !loi ? (
          <SkeletonList count={2} />
        ) : bai && bai.length === 0 && !loi ? (
          <EmptyState
            icon="✍"
            title="Chưa có bài viết nào"
            hint="Bài đăng của người này sẽ hiện ở đây."
          />
        ) : (
          <div className="stack">
            {(bai ?? []).map((b) => (
              <PostCard
                key={b.post_id}
                post={b}
                limits={limits}
                onChange={(moi) =>
                  setBai((truoc) =>
                    (truoc ?? []).map((x) =>
                      x.post_id === moi.post_id ? moi : x,
                    ),
                  )
                }
                onDeleted={(id) =>
                  setBai((truoc) => (truoc ?? []).filter((x) => x.post_id !== id))
                }
              />
            ))}
          </div>
        )}
      </div>

      <div role="tabpanel" id="panel-thanh-tuu" aria-labelledby="tab-thanh-tuu" hidden={tab !== "thanh-tuu"}>
        {daMo.length === 0 ? (
          <EmptyState icon="🏅" title="Chưa mở thành tựu nào" hint="Thành tựu mở khoá khi đọc, nghe, viết và tham gia cộng đồng." />
        ) : (
          <div className="bento-grid">
            {daMo.map((a) => (
              <div key={a.key} className={`achievement-card do-hiem-${a.rarity}`}>
                <span className="achievement-card-icon" aria-hidden="true">
                  {a.icon}
                </span>
                <span className="progress-card-body">
                  <strong>{a.name}</strong>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
