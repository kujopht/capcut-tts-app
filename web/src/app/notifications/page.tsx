"use client";

/**
 * Trang thông báo đầy đủ.
 *
 * Bảng nhỏ trên cái chuông chỉ hiện 8 dòng gần nhất; trang này có phân trang và
 * bộ lọc "chỉ chưa đọc". Hai chỗ dùng CÙNG một endpoint, nên không có nguy cơ
 * một chỗ hiện khác chỗ kia.
 *
 * ĐÒI đăng nhập — khác `/community`. Thông báo là của riêng một người, nên ở đây
 * không có phiên bản nào cho khách vãng lai.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  social,
  type Notification,
  type NotificationPage,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  PageHeader,
  SkeletonList,
  ErrorState,
  EmptyState,
} from "@/components/ui";
import { khiNao } from "@/lib/time";

/** Cùng bảng câu với `NotificationBell` — một nguồn, hai chỗ hiện. */
const CAU: Record<Notification["kind"], string> = {
  follow: "đã theo dõi bạn",
  post_like: "đã thích bài của bạn",
  post_comment: "đã bình luận bài của bạn",
  comment_reply: "đã trả lời bình luận của bạn",
  story_chapter: "vừa đăng chương mới",
  chapter_comment: "đã bình luận chương của bạn",
  author_approved: "Đơn tác giả của bạn đã được duyệt",
  author_rejected: "Đơn tác giả của bạn chưa được duyệt",
};

function laHeThong(n: Notification): boolean {
  return n.kind === "author_approved" || n.kind === "author_rejected";
}

function dichDen(n: Notification): string | null {
  if (laHeThong(n)) return "/creator/apply";
  if (n.subject_kind === "post") return `/posts/${n.subject_id}`;
  if (n.subject_kind === "novel") return `/novels/${n.subject_id}`;
  if (n.subject_kind === "chapter") return `/chapters/${n.subject_id}`;
  if (n.subject_kind === "user" && n.actor?.username) {
    return `/u/${n.actor.username}`;
  }
  return null;
}

export default function NotificationsPage() {
  const { profile, loading: dangTaiPhien } = useSession();
  const [trang, setTrang] = useState<NotificationPage | null>(null);
  const [chiChuaDoc, setChiChuaDoc] = useState(false);
  const [loi, setLoi] = useState("");

  const tai = useCallback(() => {
    if (!profile) return;
    setLoi("");
    setTrang(null);
    social
      .notifications(chiChuaDoc, 30)
      .then(setTrang)
      .catch((e) =>
        setLoi(e instanceof ApiError ? e.message : "Không tải được thông báo."),
      );
  }, [profile, chiChuaDoc]);

  /* `queueMicrotask`: `tai()` mo dau bang `setLoi("")`/`setTrang(null)`, va mot
     `setState` dong bo trong than effect bi quy tac
     `react-hooks/set-state-in-effect` cam. Xem ghi chu day hon o
     `app/community/page.tsx`. */
  useEffect(() => {
    queueMicrotask(tai);
  }, [tai]);

  const docHet = useCallback(async () => {
    await social.markAllRead();
    tai();
  }, [tai]);

  if (dangTaiPhien) return <SkeletonList count={4} />;

  if (!profile) {
    return (
      <div className="stack">
        <PageHeader title="Thông báo" />
        <EmptyState
          icon="🔔"
          title="Cần đăng nhập"
          hint="Thông báo là của riêng bạn."
          action={
            <Link className="btn btn-primary" href="/login?next=%2Fnotifications">
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Của bạn"
        title="Thông báo"
        lead={
          trang
            ? `${trang.unread} chưa đọc trong ${trang.total} thông báo.`
            : undefined
        }
        action={
          <>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              aria-pressed={chiChuaDoc}
              onClick={() => setChiChuaDoc((v) => !v)}
            >
              Chỉ chưa đọc
            </button>
            {trang && trang.unread > 0 ? (
              <button type="button" className="btn btn-sm" onClick={docHet}>
                Đánh dấu đã đọc hết
              </button>
            ) : null}
          </>
        }
      />

      {loi ? <ErrorState message={loi} onRetry={tai} /> : null}

      {trang === null && !loi ? (
        <SkeletonList count={5} />
      ) : trang && trang.items.length === 0 ? (
        <EmptyState
          icon="🔔"
          title={chiChuaDoc ? "Không còn gì chưa đọc" : "Chưa có thông báo nào"}
          hint="Theo dõi vài tác giả để biết khi họ đăng chương mới."
        />
      ) : (
        <ul className="tb-ds">
          {(trang?.items ?? []).map((n) => {
            const den = dichDen(n);
            const noiDung = (
              <>
                <span className="tb-chu">
                  {laHeThong(n) ? null : (
                    <strong>
                      {n.actor?.display_name || n.actor?.username || "Ai đó"}{" "}
                    </strong>
                  )}
                  {CAU[n.kind] ?? "có hoạt động mới"}
                  {n.preview ? <em className="tb-xem"> “{n.preview}”</em> : null}
                </span>
                <span className="hint">{khiNao(n.created_at)}</span>
              </>
            );
            return (
              <li
                key={n.notification_id}
                id={n.notification_id}
                className={n.read ? "tb-muc" : "tb-muc tb-moi"}
              >
                {den ? (
                  <Link
                    href={den}
                    className="tb-lien-ket"
                    /* Bấm vào là đã đọc — không cần một nút riêng. Lỗi ở đây bị
                       bỏ qua: điều hướng vẫn phải xảy ra. */
                    onClick={() => {
                      void social.markRead(n.notification_id).catch(() => {});
                    }}
                  >
                    {noiDung}
                  </Link>
                ) : (
                  <div className="tb-lien-ket">{noiDung}</div>
                )}
                {!n.read ? (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={async () => {
                      await social.markRead(n.notification_id);
                      setTrang((truoc) =>
                        truoc
                          ? {
                              ...truoc,
                              unread: Math.max(0, truoc.unread - 1),
                              items: truoc.items.map((x) =>
                                x.notification_id === n.notification_id
                                  ? { ...x, read: true }
                                  : x,
                              ),
                            }
                          : truoc,
                      );
                    }}
                  >
                    Đã đọc
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
