"use client";

/**
 * Bình luận của một bài, và trả lời MỘT cấp.
 *
 * ĐÚNG một cấp — cưỡng chế ở backend (`social.REPLY_MAX_DEPTH`) và phản ánh ở
 * đây bằng cấu trúc: `replies` là một mảng phẳng, không phải một cây đệ quy. Nếu
 * một ngày nào đó ai muốn nhiều cấp hơn, họ sẽ phải đổi cả hai chỗ — và đó là
 * điều tốt, vì nó buộc quyết định đó được nghĩ lại chứ không trôi vào.
 *
 * Bình luận ĐÃ BỊ GỠ vẫn hiện ra, kèm một dòng "đã bị gỡ" và không kèm nội dung.
 * Ẩn hẳn thì một trả lời sẽ treo lơ lửng dưới một khoảng trống, và số đếm trả
 * lời của bình luận gốc sẽ đọc ra sai.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  social,
  type Comment,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { loginHref } from "@/lib/nav";
import { khiNao } from "@/lib/time";
import { ReportDialog } from "@/components/ReportDialog";
import { AuthorBadge } from "@/components/AuthorBadge";

/** Hộp gõ dùng cho cả bình luận gốc và trả lời. */
function OGo({
  tranChu,
  nhan,
  moTa,
  onGui,
  onHuy,
}: {
  tranChu: number;
  nhan: string;
  moTa: string;
  onGui: (text: string) => Promise<void>;
  onHuy?: () => void;
}) {
  const [chu, setChu] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState("");

  const gui = useCallback(async () => {
    if (!chu.trim()) return;
    setDangGui(true);
    setLoi("");
    try {
      await onGui(chu.trim());
      setChu("");
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không gửi được.");
    } finally {
      setDangGui(false);
    }
  }, [chu, onGui]);

  return (
    <div className="binh-luan-go">
      <textarea
        className="input"
        rows={2}
        maxLength={tranChu}
        value={chu}
        onChange={(e) => setChu(e.target.value)}
        placeholder={moTa}
        aria-label={moTa}
      />
      <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
        {onHuy ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onHuy}>
            Huỷ
          </button>
        ) : null}
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={dangGui || !chu.trim()}
          onClick={gui}
        >
          {dangGui ? "Đang gửi…" : nhan}
        </button>
      </div>
      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}
    </div>
  );
}

/** Một bình luận. `tra` = đây là một trả lời (thụt lề, không có nút Trả lời). */
function MotBinhLuan({
  bl,
  tra,
  tranChu,
  onTraLoi,
  onDoi,
  onXoa,
}: {
  bl: Comment;
  tra: boolean;
  tranChu: number;
  onTraLoi?: () => void;
  onDoi: (moi: Comment) => void;
  onXoa: () => void;
}) {
  const { profile } = useSession();
  const [dangSua, setDangSua] = useState(false);
  const [baoCao, setBaoCao] = useState(false);
  const cuaToi = !!profile && profile.user_id === bl.author_user_id;
  const daGo = bl.state !== "visible";

  if (daGo) {
    return (
      <li className={tra ? "binh-luan tra-loi da-go" : "binh-luan da-go"}>
        <p className="hint">Bình luận này đã bị gỡ.</p>
      </li>
    );
  }

  return (
    <li className={tra ? "binh-luan tra-loi" : "binh-luan"} id={bl.comment_id}>
      <div className="binh-luan-dau">
        {bl.author?.username ? (
          <Link href={`/u/${bl.author.username}`} className="binh-luan-ten">
            {bl.author.display_name || bl.author.username}
          </Link>
        ) : (
          <span className="binh-luan-ten">
            {bl.author?.display_name || "Người dùng"}
          </span>
        )}
        {bl.author?.is_author ? <AuthorBadge size="sm" /> : null}
        <span className="hint">{khiNao(bl.created_at)}</span>
      </div>

      {dangSua ? (
        <OGo
          tranChu={tranChu}
          nhan="Lưu"
          moTa="Sửa bình luận"
          onHuy={() => setDangSua(false)}
          onGui={async (text) => {
            const ra = await social.editComment(bl.comment_id, text);
            onDoi(ra.comment);
            setDangSua(false);
          }}
        />
      ) : (
        <p className="binh-luan-chu">{bl.text}</p>
      )}

      <div className="binh-luan-day">
        {onTraLoi ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onTraLoi}>
            Trả lời
          </button>
        ) : null}
        {cuaToi ? (
          <>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setDangSua((v) => !v)}
            >
              Sửa
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={async () => {
                await social.deleteComment(bl.comment_id);
                onXoa();
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
      </div>

      {baoCao ? (
        <ReportDialog
          targetKind="comment"
          targetId={bl.comment_id}
          onClose={() => setBaoCao(false)}
        />
      ) : null}
    </li>
  );
}

export function CommentThread({
  postId,
  limits,
  onCountChange,
}: {
  postId: string;
  limits: ServerLimits | null;
  /** Bài đăng hiện số bình luận, nên nó cần biết khi số đó đổi. */
  onCountChange?: (delta: number) => void;
}) {
  const { profile } = useSession();
  const pathname = usePathname();
  const [ds, setDs] = useState<Comment[] | null>(null);
  const [tong, setTong] = useState(0);
  const [loi, setLoi] = useState("");
  const [dangTraLoi, setDangTraLoi] = useState("");
  const tranChu = limits?.comment_max_chars ?? 1000;

  useEffect(() => {
    let huy = false;
    social
      .comments(postId)
      .then((r) => {
        if (huy) return;
        setDs(r.items);
        setTong(r.total);
      })
      .catch((e) => {
        if (huy) return;
        setDs([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được bình luận.");
      });
    return () => {
      huy = true;
    };
  }, [postId]);

  const themGoc = useCallback(
    async (text: string) => {
      const ra = await social.createComment(postId, text);
      setDs((truoc) => [...(truoc ?? []), { ...ra.comment, replies: [] }]);
      setTong((t) => t + 1);
      onCountChange?.(1);
    },
    [postId, onCountChange],
  );

  const themTraLoi = useCallback(
    async (chaId: string, text: string) => {
      const ra = await social.createComment(postId, text, chaId);
      setDs((truoc) =>
        (truoc ?? []).map((c) =>
          c.comment_id === chaId
            ? { ...c, replies: [...(c.replies ?? []), ra.comment],
                reply_count: c.reply_count + 1 }
            : c,
        ),
      );
      setDangTraLoi("");
      onCountChange?.(1);
    },
    [postId, onCountChange],
  );

  if (ds === null) {
    return (
      <p className="hint" role="status">
        Đang tải bình luận…
      </p>
    );
  }

  return (
    <div className="binh-luan-khoi">
      {profile ? (
        <OGo
          tranChu={tranChu}
          nhan="Bình luận"
          moTa="Viết bình luận…"
          onGui={themGoc}
        />
      ) : (
        <p className="hint">
          <Link href={loginHref(pathname)}>Đăng nhập</Link> để bình luận.
        </p>
      )}

      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}

      {ds.length === 0 ? (
        <p className="hint">Chưa có bình luận nào. Hãy là người đầu tiên.</p>
      ) : (
        <ul className="binh-luan-ds">
          {ds.map((c) => (
            <li key={c.comment_id} className="binh-luan-nhanh">
              <ul className="binh-luan-ds">
                <MotBinhLuan
                  bl={c}
                  tra={false}
                  tranChu={tranChu}
                  onTraLoi={
                    profile
                      ? () =>
                          setDangTraLoi((v) =>
                            v === c.comment_id ? "" : c.comment_id,
                          )
                      : undefined
                  }
                  onDoi={(moi) =>
                    setDs((truoc) =>
                      (truoc ?? []).map((x) =>
                        x.comment_id === moi.comment_id
                          ? { ...moi, replies: x.replies }
                          : x,
                      ),
                    )
                  }
                  onXoa={() => {
                    setDs((truoc) =>
                      (truoc ?? []).filter((x) => x.comment_id !== c.comment_id),
                    );
                    setTong((t) => Math.max(0, t - 1));
                    onCountChange?.(-1);
                  }}
                />
                {(c.replies ?? []).map((r) => (
                  <MotBinhLuan
                    key={r.comment_id}
                    bl={r}
                    tra
                    tranChu={tranChu}
                    onDoi={(moi) =>
                      setDs((truoc) =>
                        (truoc ?? []).map((x) =>
                          x.comment_id === c.comment_id
                            ? {
                                ...x,
                                replies: (x.replies ?? []).map((y) =>
                                  y.comment_id === moi.comment_id ? moi : y,
                                ),
                              }
                            : x,
                        ),
                      )
                    }
                    onXoa={() => {
                      setDs((truoc) =>
                        (truoc ?? []).map((x) =>
                          x.comment_id === c.comment_id
                            ? {
                                ...x,
                                replies: (x.replies ?? []).filter(
                                  (y) => y.comment_id !== r.comment_id,
                                ),
                                reply_count: Math.max(0, x.reply_count - 1),
                              }
                            : x,
                        ),
                      );
                      onCountChange?.(-1);
                    }}
                  />
                ))}
              </ul>

              {/* Backend chỉ trả vài trả lời đầu của mỗi bình luận gốc — nói rõ
                  còn bao nhiêu thay vì im lặng cắt bớt. */}
              {c.reply_count > (c.replies?.length ?? 0) ? (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={async () => {
                    const ra = await social.replies(c.comment_id, 50);
                    setDs((truoc) =>
                      (truoc ?? []).map((x) =>
                        x.comment_id === c.comment_id
                          ? { ...x, replies: ra.items }
                          : x,
                      ),
                    );
                  }}
                >
                  Xem thêm {c.reply_count - (c.replies?.length ?? 0)} trả lời
                </button>
              ) : null}

              {dangTraLoi === c.comment_id ? (
                <OGo
                  tranChu={tranChu}
                  nhan="Trả lời"
                  moTa={`Trả lời ${c.author?.display_name || "bình luận"}…`}
                  onHuy={() => setDangTraLoi("")}
                  onGui={(text) => themTraLoi(c.comment_id, text)}
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {tong > ds.length ? (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={async () => {
            const ra = await social.comments(postId, 50, ds.length);
            setDs((truoc) => [...(truoc ?? []), ...ra.items]);
          }}
        >
          Xem thêm bình luận ({tong - ds.length})
        </button>
      ) : null}
    </div>
  );
}
