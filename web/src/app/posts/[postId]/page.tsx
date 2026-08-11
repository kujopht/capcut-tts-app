"use client";

/**
 * Một bài đăng riêng, và bình luận của nó.
 *
 * VÌ SAO CẦN TRANG NÀY: thông báo dẫn tới đây. Không có nó thì một thông báo
 * "ai đó đã thích bài của bạn" chỉ dẫn về bảng tin, và người dùng phải tự cuộn
 * đi tìm bài nào — với một bảng tin đủ dài thì bài đó không còn ở đó nữa.
 *
 * Bình luận MỞ SẴN ở đây, khác bảng tin. Người vào trang một bài đơn lẻ gần như
 * luôn muốn xem cuộc trao đổi; lý do tải theo yêu cầu ở bảng tin (20 bài × 1
 * truy vấn) không tồn tại khi chỉ có một bài.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, social, type Post, type ServerLimits } from "@/lib/api";
import {
  PageHeader,
  SkeletonList,
  ErrorState,
  EmptyState,
} from "@/components/ui";
import { PostCard } from "@/components/PostCard";
import { CommentThread } from "@/components/CommentThread";

export default function PostPage() {
  const params = useParams<{ postId: string }>();
  const postId = params?.postId ?? "";
  const [bai, setBai] = useState<Post | null>(null);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [loi, setLoi] = useState("");
  const [daXoa, setDaXoa] = useState(false);

  useEffect(() => {
    if (!postId) return;
    let huy = false;
    social
      .post(postId)
      .then((r) => {
        if (!huy) setBai(r.post);
      })
      .catch((e) => {
        if (huy) return;
        setLoi(
          e instanceof ApiError ? e.message : "Không tải được bài đăng.",
        );
      });
    return () => {
      huy = true;
    };
  }, [postId]);

  useEffect(() => {
    social.limits().then(setLimits).catch(() => {});
  }, []);

  if (daXoa) {
    return (
      <div className="stack">
        <PageHeader title="Đã xoá" />
        <EmptyState
          title="Bài đăng đã được xoá"
          hint="Nội dung này không còn nữa."
          action={
            <Link className="btn btn-primary" href="/community">
              Về Cộng đồng
            </Link>
          }
        />
      </div>
    );
  }

  if (loi) {
    return (
      <div className="stack">
        <PageHeader title="Bài đăng" />
        <ErrorState message={loi} />
        <Link className="btn btn-ghost btn-sm" href="/community">
          ← Về Cộng đồng
        </Link>
      </div>
    );
  }

  if (!bai) return <SkeletonList count={2} />;

  return (
    <div className="stack">
      <Link className="btn btn-ghost btn-sm" href="/community">
        ← Cộng đồng
      </Link>
      <PostCard
        post={bai}
        limits={limits}
        onChange={setBai}
        onDeleted={() => setDaXoa(true)}
        commentsElsewhere
      />
      {/* Mở sẵn — xem ghi chú đầu tệp. `commentsElsewhere` tắt khối bình luận
          BÊN TRONG thẻ, nếu không thì bấm nút bình luận sẽ mở một khối thứ hai
          ngay dưới khối này và cùng một cuộc trao đổi hiện ra hai lần. */}
      <section className="card" aria-label="Bình luận">
        <CommentThread
          postId={bai.post_id}
          limits={limits}
          onCountChange={(delta) =>
            setBai((truoc) =>
              truoc
                ? {
                    ...truoc,
                    comment_count: Math.max(0, truoc.comment_count + delta),
                  }
                : truoc,
            )
          }
        />
      </section>
    </div>
  );
}
