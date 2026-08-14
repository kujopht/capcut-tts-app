"use client";

/**
 * Một bài đăng trong bảng tin — cấu trúc quen thuộc của mọi bảng tin xã hội:
 *
 *   đầu bài  (avatar · tên · huy hiệu · lúc nào · menu ⋯)
 *   thân     (chữ · gallery ảnh · thẻ truyện đính kèm)
 *   tóm tắt  (X lượt thích · Y bình luận)
 *   hành động (Thích · Bình luận · Chia sẻ)
 *   xem trước 2 bình luận mới nhất · "Xem tất cả"
 *
 * Cấu trúc là của Facebook; da thịt là của Fanfic World — kính tối, sắc tím,
 * không một pixel xanh-trắng nào.
 *
 * BÌNH LUẬN: bảng tin ghép sẵn 2 cái mới nhất (`comments_preview`, MỘT truy
 * vấn theo lô cho cả trang) nên thẻ hiện được ngay không tốn thêm mạng. Khối
 * đầy đủ chỉ tải khi bấm "Bình luận"/"Xem tất cả" — 20 bài không phải 20 truy
 * vấn cho thứ phần lớn người đọc cuộn qua.
 *
 * THÍCH cập nhật lạc quan rồi lấy con số thật của máy chủ; tim đổi màu + một
 * nhịp phồng NHỎ (tôn trọng reduced-motion), không pháo hoa.
 *
 * CHIA SẺ V1 = chép liên kết bền `/posts/{id}` vào clipboard. Không SDK mạng
 * nào — một URL tốt là hình thức chia sẻ tương thích với mọi nền tảng.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  social,
  type Post,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { loginHref } from "@/lib/nav";
import { khiNao } from "@/lib/time";
import { formatNumber } from "@/components/ui";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { Avatar } from "@/components/Avatar";
import { CommentThread } from "@/components/CommentThread";
import { ReportDialog } from "@/components/ReportDialog";
import { ImageLightbox } from "@/components/ImageLightbox";

/** Menu ⋯ của một bài: của mình → Sửa/Xóa; của người khác → Báo cáo. */
function MenuBai({
  cuaToi,
  onSua,
  onXoa,
  onBaoCao,
}: {
  cuaToi: boolean;
  onSua: () => void;
  onXoa: () => void;
  onBaoCao: () => void;
}) {
  const [mo, setMo] = useState(false);
  const hop = useRef<HTMLDivElement | null>(null);
  const nut = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!mo) return;
    const onDown = (e: MouseEvent) => {
      if (!hop.current?.contains(e.target as Node)) setMo(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setMo(false);
      nut.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [mo]);

  return (
    <div className="menu bai-menu" ref={hop}>
      <button
        ref={nut}
        type="button"
        className="btn btn-ghost btn-sm bai-menu-nut"
        aria-haspopup="menu"
        aria-expanded={mo}
        aria-label="Tuỳ chọn bài viết"
        onClick={() => setMo((v) => !v)}
      >
        ⋯
      </button>
      {mo ? (
        <div className="menu-panel" role="menu" aria-label="Tuỳ chọn bài viết">
          {cuaToi ? (
            <>
              <button type="button" className="menu-item" role="menuitem"
                onClick={() => { setMo(false); onSua(); }}>
                ✏ Sửa bài viết
              </button>
              <button type="button" className="menu-item" role="menuitem"
                onClick={() => { setMo(false); onXoa(); }}>
                🗑 Xóa bài viết
              </button>
            </>
          ) : (
            <button type="button" className="menu-item" role="menuitem"
              onClick={() => { setMo(false); onBaoCao(); }}>
              🚩 Báo cáo
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Gallery 1–4 ảnh. Bốn bố cục cố định — 1 lớn, 2 cột, 1 lớn + 2 nhỏ, lưới
 * 2×2 — không Pinterest, không tính toán. Bấm ảnh mở trình xem.
 */
function GalleryAnh({ urls }: { urls: string[] }) {
  const [xem, setXem] = useState<number | null>(null);
  if (!urls.length) return null;
  const lop = `bai-gallery bai-gallery-${Math.min(urls.length, 4)}`;
  return (
    <>
      <div className={lop}>
        {urls.slice(0, 4).map((u, i) => (
          <button
            key={i}
            type="button"
            className="bai-gallery-o"
            aria-label={`Xem ảnh ${i + 1} trên ${urls.length}`}
            onClick={() => setXem(i)}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={u} alt="" loading="lazy" />
          </button>
        ))}
      </div>
      {xem !== null ? (
        <ImageLightbox
          urls={urls}
          index={xem}
          onIndex={setXem}
          onClose={() => setXem(null)}
        />
      ) : null}
    </>
  );
}

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
   * Trang chứa thẻ này TỰ vẽ khối bình luận (trang một bài đơn lẻ) — nút bình
   * luận thành nhãn tĩnh, nếu không thì cùng một cuộc trao đổi hiện hai lần.
   */
  commentsElsewhere?: boolean;
}) {
  const { profile } = useSession();
  const pathname = usePathname();
  const toast = useToast();
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

  const chiaSe = useCallback(async () => {
    const url = `${window.location.origin}/posts/${bai.post_id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.ok("Đã chép liên kết bài viết.");
    } catch {
      // Clipboard bi chan (iframe, quyen): hien URL de nguoi dung tu chep —
      // mot loi im lang o nut Chia se doc ra nhu nut hong.
      toast.push("info", url);
    }
  }, [bai.post_id, toast]);

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
  const urls = bai.image_urls?.length
    ? bai.image_urls
    : bai.image_url
      ? [bai.image_url]
      : [];
  const xemTruoc = bai.comments_preview ?? [];

  return (
    <article className="card bai-dang" aria-labelledby={`bai-${bai.post_id}`}>
      <header className="bai-dau">
        <Avatar name={ten} avatarUrl={bai.author?.avatar_url} className="avatar" />
        <div className="bai-dau-chu">
          <h3 id={`bai-${bai.post_id}`} className="bai-ten">
            {bai.author?.username ? (
              <Link href={`/u/${bai.author.username}`}>{ten}</Link>
            ) : (
              ten
            )}
            {bai.author?.is_author ? <AuthorBadge size="sm" /> : null}
            {bai.author?.is_author && bai.author.rank ? (
              <RankBadge rank={bai.author.rank} size="sm" />
            ) : null}
          </h3>
          <span className="hint">
            <Link href={`/posts/${bai.post_id}`} className="bai-luc">
              {khiNao(bai.created_at)}
            </Link>
            {bai.kind === "story_update" ? " · cập nhật truyện" : null}
          </span>
        </div>
        <MenuBai
          cuaToi={bai.can_edit}
          onSua={() => setDangSua(true)}
          onXoa={async () => {
            try {
              await social.deletePost(bai.post_id);
              onDeleted?.(bai.post_id);
            } catch (e) {
              setLoi(e instanceof ApiError ? e.message : "Không xoá được.");
            }
          }}
          onBaoCao={() => setBaoCao(true)}
        />
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

      <GalleryAnh urls={urls} />

      {bai.novel ? (
        <Link href={`/novels/${bai.novel.novel_id}`} className="bai-truyen">
          {bai.novel.cover_url ? (
            <span
              className="bai-truyen-bia"
              aria-hidden="true"
              style={{
                backgroundImage: `url("${bai.novel.cover_url}")`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            />
          ) : (
            <span aria-hidden="true">📖</span>
          )}
          {bai.novel.title}
        </Link>
      ) : null}

      {/* Tom tat tuong tac — dong chu nho, chi hien khi CO gi de noi. */}
      {bai.like_count > 0 || bai.comment_count > 0 ? (
        <p className="hint bai-tom-tat">
          {bai.like_count > 0
            ? `♥ ${formatNumber(bai.like_count)}`
            : null}
          {bai.like_count > 0 && bai.comment_count > 0 ? " · " : null}
          {bai.comment_count > 0
            ? `${formatNumber(bai.comment_count)} bình luận`
            : null}
        </p>
      ) : null}

      <footer className="bai-day">
        {profile ? (
          <button
            type="button"
            className={bai.liked ? "btn btn-ghost bai-nut da-thich" : "btn btn-ghost bai-nut"}
            aria-pressed={bai.liked}
            onClick={thich}
          >
            <span aria-hidden="true" className="bai-tim">
              {bai.liked ? "♥" : "♡"}
            </span>{" "}
            Thích
          </button>
        ) : (
          <Link className="btn btn-ghost bai-nut" href={loginHref(pathname)}>
            <span aria-hidden="true">♡</span> Thích
          </Link>
        )}

        {commentsElsewhere ? (
          <span className="btn btn-ghost bai-nut bai-nut-tinh" aria-hidden="true">
            💬 Bình luận
          </span>
        ) : (
          <button
            type="button"
            className="btn btn-ghost bai-nut"
            aria-expanded={moBinhLuan}
            onClick={() => setMoBinhLuan((v) => !v)}
          >
            <span aria-hidden="true">💬</span> Bình luận
          </button>
        )}

        <button type="button" className="btn btn-ghost bai-nut" onClick={chiaSe}>
          <span aria-hidden="true">↗</span> Chia sẻ
        </button>
      </footer>

      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}

      {/*
        Xem truoc 2 binh luan MOI NHAT — ghep san tu backend, khong ton mang.
        Khi khoi day du dang mo thi AN xem truoc: cung du lieu hai lan doc ra
        nhu mot loi lap.
      */}
      {!moBinhLuan && !commentsElsewhere && xemTruoc.length > 0 ? (
        <div className="bai-xem-truoc">
          {xemTruoc.map((c) => (
            <p key={c.comment_id} className="bai-xt-dong">
              <strong>
                {c.author?.display_name || c.author?.username || "Ai đó"}
              </strong>{" "}
              {c.spoiler ? (
                <em className="hint">(có spoiler — mở bình luận để xem)</em>
              ) : (
                <span className="bai-xt-chu">{c.text}</span>
              )}
            </p>
          ))}
          {bai.comment_count > xemTruoc.length ? (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setMoBinhLuan(true)}
            >
              Xem thêm bình luận
            </button>
          ) : null}
        </div>
      ) : null}

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
