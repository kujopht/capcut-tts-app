"use client";

/**
 * Một bài đăng trong bảng tin — cấu trúc quen thuộc của mọi bảng tin xã hội:
 *
 *   đầu bài  (avatar · tên · huy hiệu · lúc nào · đã sửa · fandom · menu ⋯)
 *   thân     (chữ · gallery ảnh · thẻ truyện đính kèm) — che nếu có spoiler
 *   tóm tắt  (X lượt thích · Y bình luận)
 *   hành động (Thích · Bình luận · Chia sẻ)
 *   xem trước 2 bình luận mới nhất · "Xem tất cả"
 *
 * Cấu trúc là của Facebook; da thịt là của Fanfic World — kính tối, sắc tím.
 *
 * BÌNH LUẬN: bảng tin ghép sẵn 2 cái mới nhất (`comments_preview`, MỘT truy
 * vấn theo lô cho cả trang). Khối đầy đủ chỉ tải khi bấm. Trạng thái mở/đóng
 * có thể do trang CHA giữ (`commentsOpen`) — để Back từ một hồ sơ về thì
 * những khối đang mở vẫn mở.
 *
 * THÍCH cập nhật lạc quan, KHOÁ trong lúc chờ (bấm đúp không gửi hai yêu cầu
 * chồng nhau), rồi lấy con số thật của máy chủ; lỗi thì trả về như cũ và nói rõ.
 *
 * CHIA SẺ = chép liên kết bền `/posts/{id}` vào clipboard.
 *
 * SPOILER: người viết tự đánh dấu; thân bài bị che sau một nút "Hiện nội dung"
 * — cần một thao tác CỐ Ý, không lộ khi chỉ lướt qua.
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
import { hoSoHref } from "@/lib/communityFeed";
import { ConfirmDialog, formatNumber } from "@/components/ui";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { UserAvatar, tenHienThi } from "@/components/UserAvatar";
import { CommentThread } from "@/components/CommentThread";
import { ReportDialog } from "@/components/ReportDialog";
import { ImageLightbox } from "@/components/ImageLightbox";

type HanhDongMenu = "sua" | "xoa" | "bao-cao" | "bao-cao-nguoi" | "an" | "chan";

/** Menu ⋯ của một bài: của mình → Sửa/Xóa; của người khác → Báo cáo/Ẩn/Chặn. */
function MenuBai({
  cuaToi,
  coTheChan,
  coTheBaoCaoNguoi,
  tenTacGia,
  onChon,
}: {
  cuaToi: boolean;
  coTheChan: boolean;
  coTheBaoCaoNguoi: boolean;
  tenTacGia: string;
  onChon: (h: HanhDongMenu) => void;
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

  const muc = (h: HanhDongMenu, nhan: string) => (
    <button
      type="button"
      className="menu-item"
      role="menuitem"
      onClick={() => {
        setMo(false);
        onChon(h);
      }}
    >
      {nhan}
    </button>
  );

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
              {muc("sua", "✏ Sửa bài viết")}
              {muc("xoa", "🗑 Xóa bài viết")}
            </>
          ) : (
            <>
              {muc("bao-cao", "🚩 Báo cáo bài viết")}
              {coTheBaoCaoNguoi ? muc("bao-cao-nguoi", `🚩 Báo cáo ${tenTacGia}`) : null}
              {coTheChan ? muc("an", `🔕 Ẩn bài của ${tenTacGia}`) : null}
              {coTheChan ? muc("chan", `⛔ Chặn ${tenTacGia}`) : null}
            </>
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
        <ImageLightbox urls={urls} index={xem} onIndex={setXem} onClose={() => setXem(null)} />
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
  commentsOpen,
  onCommentsOpenChange,
  onAuthorHidden,
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
  /** Trang cha giữ trạng thái mở bình luận (để Back khôi phục). */
  commentsOpen?: boolean;
  onCommentsOpenChange?: (mo: boolean) => void;
  /** Người xem vừa ẩn/chặn tác giả — trang cha bỏ bài của họ khỏi danh sách. */
  onAuthorHidden?: (userId: string) => void;
}) {
  const { profile } = useSession();
  const pathname = usePathname();
  const toast = useToast();
  const [bai, setBai] = useState(post);
  const [moBinhLuanNoiBo, setMoBinhLuanNoiBo] = useState(false);
  const [dangSua, setDangSua] = useState(false);
  const [chuSua, setChuSua] = useState(post.text);
  const [dangLuuSua, setDangLuuSua] = useState(false);
  const [baoCao, setBaoCao] = useState<null | "post" | "user">(null);
  const [hoi, setHoi] = useState<null | "xoa" | "chan" | "an">(null);
  const [dangLam, setDangLam] = useState(false);
  const [hienSpoiler, setHienSpoiler] = useState(false);
  const [loi, setLoi] = useState("");
  const dangThich = useRef(false);

  const moBinhLuan = commentsOpen ?? moBinhLuanNoiBo;
  const datMoBinhLuan = useCallback(
    (mo: boolean) => {
      if (onCommentsOpenChange) onCommentsOpenChange(mo);
      else setMoBinhLuanNoiBo(mo);
    },
    [onCommentsOpenChange],
  );

  const cap = limits?.capabilities ?? {};
  const fandoms = limits?.community_fandoms ?? [];

  const capNhat = useCallback(
    (moi: Post) => {
      setBai(moi);
      onChange?.(moi);
    },
    [onChange],
  );

  const thich = useCallback(async () => {
    if (!profile || dangThich.current) return;
    dangThich.current = true;
    const truoc = bai;
    capNhat({
      ...bai,
      liked: !truoc.liked,
      like_count: Math.max(0, bai.like_count + (truoc.liked ? -1 : 1)),
    });
    try {
      const ra = truoc.liked ? await social.unlike(bai.post_id) : await social.like(bai.post_id);
      capNhat({ ...truoc, liked: ra.liked, like_count: ra.like_count });
      setLoi("");
    } catch (e) {
      capNhat(truoc);
      setLoi(
        e instanceof ApiError
          ? `${e.message} Lượt thích chưa được ghi nhận.`
          : "Mất kết nối — lượt thích chưa được ghi nhận.",
      );
    } finally {
      dangThich.current = false;
    }
  }, [profile, bai, capNhat]);

  const chiaSe = useCallback(async () => {
    const url = `${window.location.origin}/posts/${bai.post_id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.ok("Đã chép liên kết bài viết.");
    } catch {
      // Clipboard bi chan: hien URL de nguoi dung tu chep — mot loi im lang o
      // nut Chia se doc ra nhu nut hong.
      toast.push("info", url);
    }
  }, [bai.post_id, toast]);

  const luuSua = useCallback(async () => {
    if (dangLuuSua) return;
    setDangLuuSua(true);
    try {
      const ra = await social.editPost(bai.post_id, chuSua.trim());
      capNhat(ra.post);
      setDangSua(false);
      setLoi("");
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không lưu được — chữ bạn sửa vẫn còn.");
    } finally {
      setDangLuuSua(false);
    }
  }, [dangLuuSua, bai.post_id, chuSua, capNhat]);

  const xacNhan = useCallback(async () => {
    if (!hoi || dangLam) return;
    setDangLam(true);
    try {
      if (hoi === "xoa") {
        await social.deletePost(bai.post_id);
        setHoi(null);
        onDeleted?.(bai.post_id);
        return;
      }
      if (hoi === "chan") await social.block(bai.author_user_id);
      if (hoi === "an") await social.mute(bai.author_user_id);
      setHoi(null);
      toast.ok(hoi === "chan" ? "Đã chặn. Bạn có thể bỏ chặn trong trang tài khoản." : "Đã ẩn bài của người này.");
      onAuthorHidden?.(bai.author_user_id);
    } catch (e) {
      setHoi(null);
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setDangLam(false);
    }
  }, [hoi, dangLam, bai.post_id, bai.author_user_id, onDeleted, onAuthorHidden, toast]);

  const ten = tenHienThi(bai.author);
  const href = hoSoHref(bai.author);
  const urls = bai.image_urls?.length ? bai.image_urls : bai.image_url ? [bai.image_url] : [];
  const xemTruoc = bai.comments_preview ?? [];
  const tenFandom = bai.fandom_id ? fandoms.find((f) => f.id === bai.fandom_id)?.label ?? "" : "";
  const biChe = Boolean(bai.spoiler) && !hienSpoiler && !dangSua;
  const khachChuaVao = !profile;

  return (
    <article className="card bai-dang" aria-labelledby={`bai-${bai.post_id}`}>
      <header className="bai-dau">
        <UserAvatar user={bai.author} className="avatar" link />
        <div className="bai-dau-chu">
          <h3 id={`bai-${bai.post_id}`} className="bai-ten">
            {href ? <Link href={href}>{ten}</Link> : ten}
            {bai.author?.is_author ? <AuthorBadge size="sm" /> : null}
            {bai.author?.is_author && bai.author.rank ? <RankBadge rank={bai.author.rank} size="sm" /> : null}
          </h3>
          <span className="hint bai-meta">
            <Link href={`/posts/${bai.post_id}`} className="bai-luc">
              {khiNao(bai.created_at)}
            </Link>
            {bai.edited ? (
              <span title={bai.edited_at ? `Sửa lúc ${new Date(bai.edited_at).toLocaleString("vi-VN")}` : undefined}>
                {" "}· đã chỉnh sửa
              </span>
            ) : null}
            {bai.kind === "story_update" ? " · cập nhật truyện" : null}
            {tenFandom ? <span className="chip chip-static bai-fandom">{tenFandom}</span> : null}
          </span>
        </div>
        {!khachChuaVao ? (
          <MenuBai
            cuaToi={bai.can_edit}
            coTheChan={Boolean(cap.blocks)}
            coTheBaoCaoNguoi={Boolean(cap.user_reports)}
            tenTacGia={ten}
            onChon={(h) => {
              if (h === "sua") setDangSua(true);
              else if (h === "xoa") setHoi("xoa");
              else if (h === "bao-cao") setBaoCao("post");
              else if (h === "bao-cao-nguoi") setBaoCao("user");
              else if (h === "chan") setHoi("chan");
              else if (h === "an") setHoi("an");
            }}
          />
        ) : null}
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
            <button type="button" className="btn btn-primary btn-sm" disabled={dangLuuSua} onClick={luuSua}>
              {dangLuuSua ? "Đang lưu…" : "Lưu"}
            </button>
          </div>
        </div>
      ) : biChe ? (
        <div className="bai-spoiler">
          <p className="hint">
            <strong>Có spoiler.</strong> Người viết đánh dấu bài này có tiết lộ nội dung.
          </p>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setHienSpoiler(true)}>
            Hiện nội dung
          </button>
        </div>
      ) : (
        <>
          {bai.text ? <p className="bai-chu">{bai.text}</p> : null}
          <GalleryAnh urls={urls} />
        </>
      )}

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
          {bai.like_count > 0 ? `♥ ${formatNumber(bai.like_count)}` : null}
          {bai.like_count > 0 && bai.comment_count > 0 ? " · " : null}
          {bai.comment_count > 0 ? `${formatNumber(bai.comment_count)} bình luận` : null}
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
            onClick={() => datMoBinhLuan(!moBinhLuan)}
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
        Khi khoi day du dang mo thi AN xem truoc.
      */}
      {!moBinhLuan && !commentsElsewhere && xemTruoc.length > 0 ? (
        <div className="bai-xem-truoc">
          {xemTruoc.map((c) => (
            <p key={c.comment_id} className="bai-xt-dong">
              <strong>{tenHienThi(c.author, "Ai đó")}</strong>{" "}
              {c.spoiler ? (
                <em className="hint">(có spoiler — mở bình luận để xem)</em>
              ) : (
                <span className="bai-xt-chu">{c.text}</span>
              )}
            </p>
          ))}
          {bai.comment_count > xemTruoc.length ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => datMoBinhLuan(true)}>
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
            capNhat({ ...bai, comment_count: Math.max(0, bai.comment_count + delta) })
          }
        />
      ) : null}

      {baoCao ? (
        <ReportDialog
          targetKind={baoCao}
          targetId={baoCao === "user" ? bai.author_user_id : bai.post_id}
          targetName={baoCao === "user" ? ten : undefined}
          onClose={() => setBaoCao(null)}
        />
      ) : null}

      <ConfirmDialog
        open={hoi !== null}
        title={
          hoi === "xoa" ? "Xoá bài viết này?" : hoi === "chan" ? `Chặn ${ten}?` : `Ẩn bài của ${ten}?`
        }
        body={
          hoi === "xoa"
            ? "Bài và bình luận của nó sẽ biến mất khỏi bảng tin. Không hoàn tác được."
            : hoi === "chan"
              ? "Hai bạn sẽ không thấy bài của nhau trong bảng tin và không thể thích, bình luận hay theo dõi nhau. Họ không nhận được thông báo nào."
              : "Bạn sẽ không thấy bài của họ trong bảng tin nữa. Họ không biết điều này và vẫn tương tác bình thường."
        }
        confirmLabel={hoi === "xoa" ? "Xoá" : hoi === "chan" ? "Chặn" : "Ẩn"}
        danger={hoi !== "an"}
        busy={dangLam}
        onConfirm={() => void xacNhan()}
        onCancel={() => setHoi(null)}
      />
    </article>
  );
}
