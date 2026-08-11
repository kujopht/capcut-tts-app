"use client";

/**
 * Một bài đăng trong bảng tin.
 *
 * BÌNH LUẬN TẢI THEO YÊU CẦU. Một bảng tin 20 bài mà mỗi bài tự tải bình luận là
 * 20 truy vấn nữa cho thứ phần lớn người đọc cuộn qua mà không mở. Nút "N bình
 * luận" mở khối bình luận, và chỉ lúc đó mới gọi mạng.
 *
 * LƯỢT THÍCH cập nhật LẠC QUAN rồi lấy con số thật của máy chủ — cùng lý do với
 * `FollowButton`: chờ mạng xong mới đổi nút làm cú bấm cảm giác nặng.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import {
  ApiError,
  social,
  type Post,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { loginHref } from "@/lib/nav";
import { khiNao } from "@/lib/time";
import { formatNumber } from "@/components/ui";
import { AuthorBadge } from "@/components/AuthorBadge";
import { CommentThread } from "@/components/CommentThread";
import { ReportDialog } from "@/components/ReportDialog";

export function PostCard({
  post,
  limits,
  onChange,
  onDeleted,
  commentsElsewhere = false,
}: {
  post: Post;
  limits: ServerLimits | null;
  onChange?: (moi: Post) => void;
  onDeleted?: (postId: string) => void;
  /**
   * Trang chứa thẻ này TỰ vẽ khối bình luận (trang một bài đơn lẻ).
   *
   * Lúc đó nút bình luận thành một liên kết neo thay vì một nút bật/tắt — nếu
   * không, bấm vào nó sẽ mở khối bình luận THỨ HAI ngay bên dưới khối đã mở sẵn,
   * và cùng một cuộc trao đổi hiện ra hai lần.
   */
  commentsElsewhere?: boolean;
}) {
  const { profile } = useSession();
  const pathname = usePathname();
  const [bai, setBai] = useState(post);
  const [moBinhLuan, setMoBinhLuan] = useState(false);
  const [dangSua, setDangSua] = useState(false);
  const [chuSua, setChuSua] = useState(post.text);
  const [baoCao, setBaoCao] = useState(false);
  const [loi, setLoi] = useState("");

  const capNhat = useCallback(
    (moi: Post) => {
      setBai(moi);
      onChange?.(moi);
    },
    [onChange],
  );

  const thich = useCallback(async () => {
    if (!profile) return;
    const truoc = bai.liked;
    // Lạc quan, hoàn lại nếu máy chủ từ chối.
    capNhat({
      ...bai,
      liked: !truoc,
      like_count: Math.max(0, bai.like_count + (truoc ? -1 : 1)),
    });
    try {
      const ra = truoc
        ? await social.unlike(bai.post_id)
        : await social.like(bai.post_id);
      capNhat({ ...bai, liked: ra.liked, like_count: ra.like_count });
    } catch (e) {
      capNhat(bai);
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    }
  }, [profile, bai, capNhat]);

  const luuSua = useCallback(async () => {
    try {
      const ra = await social.editPost(bai.post_id, chuSua.trim());
      capNhat(ra.post);
      setDangSua(false);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không lưu được.");
    }
  }, [bai.post_id, chuSua, capNhat]);

  const ten = bai.author?.display_name || bai.author?.username || "Người dùng";

  return (
    <article className="card bai-dang" aria-labelledby={`bai-${bai.post_id}`}>
      <header className="bai-dau">
        <span className="avatar" aria-hidden="true">
          {ten.slice(0, 2).toUpperCase()}
        </span>
        <div className="bai-dau-chu">
          <h3 id={`bai-${bai.post_id}`} className="bai-ten">
            {bai.author?.username ? (
              <Link href={`/u/${bai.author.username}`}>{ten}</Link>
            ) : (
              ten
            )}
            {bai.author?.is_author ? <AuthorBadge size="sm" /> : null}
          </h3>
          <span className="hint">
            {khiNao(bai.created_at)}
            {bai.kind === "story_update" ? " · cập nhật truyện" : null}
          </span>
        </div>
      </header>

      {dangSua ? (
        <div className="bai-sua">
          <textarea
            className="input"
            rows={3}
            maxLength={limits?.post_max_chars ?? 2000}
            value={chuSua}
            onChange={(e) => setChuSua(e.target.value)}
            aria-label="Sửa nội dung bài"
          />
          <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setDangSua(false);
                setChuSua(bai.text);
              }}
            >
              Huỷ
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={luuSua}>
              Lưu
            </button>
          </div>
        </div>
      ) : bai.text ? (
        <p className="bai-chu">{bai.text}</p>
      ) : null}

      {bai.has_image && bai.image_url ? (
        // `<img>` thuần: `image_url` là URL đã ký, ngắn hạn và ở một miền khác —
        // `next/image` sẽ cần cấu hình `remotePatterns` cho một URL đổi mỗi giờ.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="bai-anh"
          src={bai.image_url}
          alt=""
          width={bai.image_width || undefined}
          height={bai.image_height || undefined}
          loading="lazy"
        />
      ) : null}

      {bai.novel ? (
        <Link href={`/novels/${bai.novel.novel_id}`} className="bai-truyen">
          <span aria-hidden="true">📖</span> {bai.novel.title}
        </Link>
      ) : null}

      <footer className="bai-day">
        {profile ? (
          <button
            type="button"
            className={bai.liked ? "btn btn-ghost btn-sm da-thich" : "btn btn-ghost btn-sm"}
            aria-pressed={bai.liked}
            aria-label={bai.liked ? "Bỏ thích" : "Thích"}
            onClick={thich}
          >
            <span aria-hidden="true">{bai.liked ? "♥" : "♡"}</span>{" "}
            {formatNumber(bai.like_count)}
          </button>
        ) : (
          <Link className="btn btn-ghost btn-sm" href={loginHref(pathname)}>
            <span aria-hidden="true">♡</span> {formatNumber(bai.like_count)}
          </Link>
        )}

        {commentsElsewhere ? (
          <span className="hint bai-so-bl">
            <span aria-hidden="true">💬</span>{" "}
            {formatNumber(bai.comment_count)} bình luận
          </span>
        ) : (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            aria-expanded={moBinhLuan}
            onClick={() => setMoBinhLuan((v) => !v)}
          >
            <span aria-hidden="true">💬</span>{" "}
            {formatNumber(bai.comment_count)} bình luận
          </button>
        )}

        {bai.can_edit ? (
          <>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setDangSua(true)}
            >
              Sửa
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={async () => {
                try {
                  await social.deletePost(bai.post_id);
                  onDeleted?.(bai.post_id);
                } catch (e) {
                  setLoi(e instanceof ApiError ? e.message : "Không xoá được.");
                }
              }}
            >
              Xoá
            </button>
          </>
        ) : profile ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setBaoCao(true)}
          >
            Báo cáo
          </button>
        ) : null}
      </footer>

      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}

      {/* Bình luận chỉ tải khi được mở — xem ghi chú đầu tệp. */}
      {moBinhLuan && !commentsElsewhere ? (
        <CommentThread
          postId={bai.post_id}
          limits={limits}
          onCountChange={(delta) =>
            capNhat({
              ...bai,
              comment_count: Math.max(0, bai.comment_count + delta),
            })
          }
        />
      ) : null}

      {baoCao ? (
        <ReportDialog
          targetKind="post"
          targetId={bai.post_id}
          onClose={() => setBaoCao(false)}
        />
      ) : null}
    </article>
  );
}
