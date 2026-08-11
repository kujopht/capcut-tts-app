"use client";

/**
 * MỘT engine bình luận cho HAI nơi: bài đăng cộng đồng và chương truyện
 * (bình luận audio). Không có engine thứ hai — khác biệt giữa hai chế độ chỉ
 * là ĐÍCH gọi API và vài khả năng thêm:
 *
 *   post      cũ→mới, composer thường
 *   chapter   MỚI→cũ (đổi được), composer có nút mốc thời gian + cờ spoiler
 *
 * MỐC THỜI GIAN đọc từ AudioEngine dùng chung — không có thẻ `<audio>` thứ
 * hai, không đo lại gì cả. Bấm vào mốc trên một bình luận gọi `dieuKhien.tua`
 * của CHÍNH engine đó. Trang chưa có audio thì hook tùy chọn trả `null`: nút
 * đính mốc biến mất, mốc cũ hiển thị tĩnh (audio đã bị gỡ thì mốc vẫn là
 * thông tin — "phút 3:42 từng có một đoạn hay").
 *
 * SPOILER do người viết TỰ đánh dấu. Thân bị che cho tới khi người đọc bấm
 * "Hiện spoiler" — mỗi người tự mở, không có trạng thái chia sẻ, không máy
 * dò spoiler nào cả.
 *
 * Trả lời ĐÚNG một cấp — cưỡng chế ở backend (`social.REPLY_MAX_DEPTH`) và
 * phản ánh ở đây bằng cấu trúc: `replies` là mảng phẳng, không cây đệ quy.
 * Bình luận đã gỡ vẫn hiện dòng "đã bị gỡ" để trả lời không treo lơ lửng.
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
import { khiNao, dongHo } from "@/lib/time";
import { ReportDialog } from "@/components/ReportDialog";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { useAudioEngineOptional } from "@/components/AudioEngine";

type DichKind = "post" | "chapter";

/** Gọi đúng API theo đích — một chỗ rẽ nhánh duy nhất của cả engine. */
function nguon(kind: DichKind, id: string) {
  if (kind === "chapter") {
    return {
      list: (sort: "moi" | "cu", limit: number, offset: number) =>
        social.chapterComments(id, sort, limit, offset),
      create: (payload: {
        text: string;
        parent_id?: string;
        timestamp_ms?: number | null;
        spoiler?: boolean;
      }) => social.createChapterComment(id, payload),
    };
  }
  return {
    list: (_sort: "moi" | "cu", limit: number, offset: number) =>
      social.comments(id, limit, offset),
    create: (payload: { text: string; parent_id?: string }) =>
      social.createComment(id, payload.text, payload.parent_id ?? ""),
  };
}

/** Hộp gõ. Ở chế độ chương, kèm nút đính mốc audio + cờ spoiler. */
function OGo({
  tranChu,
  nhan,
  moTa,
  chuong = false,
  onGui,
  onHuy,
}: {
  tranChu: number;
  nhan: string;
  moTa: string;
  /** Bật các khả năng riêng của bình luận chương. */
  chuong?: boolean;
  onGui: (text: string, extras: {
    timestamp_ms: number | null;
    spoiler: boolean;
  }) => Promise<void>;
  onHuy?: () => void;
}) {
  const { profile } = useSession();
  const engine = useAudioEngineOptional();
  const [chu, setChu] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState("");
  /** Mốc đã ĐÓNG BĂNG lúc bấm nút — không trôi theo audio đang phát. */
  const [moc, setMoc] = useState<number | null>(null);
  const [spoiler, setSpoiler] = useState(false);

  const ten = profile?.display_name || profile?.username || "?";

  const gui = useCallback(async () => {
    if (!chu.trim()) return;
    setDangGui(true);
    setLoi("");
    try {
      await onGui(chu.trim(), { timestamp_ms: moc, spoiler });
      setChu("");
      setMoc(null);
      setSpoiler(false);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không gửi được.");
    } finally {
      setDangGui(false);
    }
  }, [chu, moc, spoiler, onGui]);

  return (
    <div className="binh-luan-go">
      <div className="binh-luan-go-hang">
        <span className="avatar avatar-sm" aria-hidden="true">
          {ten.slice(0, 2).toUpperCase()}
        </span>
        <textarea
          className="input"
          rows={2}
          maxLength={tranChu}
          value={chu}
          onChange={(e) => setChu(e.target.value)}
          placeholder={moTa}
          aria-label={moTa}
        />
      </div>

      {chuong ? (
        <div className="row binh-luan-cong-cu">
          {/*
            Nut dinh moc chi hien khi CO engine (trang co audio). Bam mot lan
            DONG BANG vi tri hien tai; bam lai thi bo. Khong tu cap nhat theo
            audio dang chay — nguoi ta muon danh dau "cho toi VUA nghe", khong
            phai mot con so troi.
          */}
          {engine ? (
            <button
              type="button"
              className={moc === null ? "btn btn-ghost btn-sm" : "btn btn-sm"}
              aria-pressed={moc !== null}
              onClick={() =>
                setMoc((m) =>
                  m === null
                    ? Math.floor(engine.trangThai.thoiDiem * 1000)
                    : null,
                )
              }
            >
              {moc === null
                ? `⏱ Bình luận tại ${dongHo(engine.trangThai.thoiDiem)}`
                : `⏱ ${dongHo(moc / 1000)} ✕`}
            </button>
          ) : null}
          <label className="radio-hang binh-luan-spoiler">
            <input
              type="checkbox"
              checked={spoiler}
              onChange={(e) => setSpoiler(e.target.checked)}
            />
            <span>Có spoiler</span>
          </label>
        </div>
      ) : null}

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

/** Mốc audio trên một bình luận: bấm để tua — qua CHÍNH engine dùng chung. */
function MocAudio({ ms }: { ms: number }) {
  const engine = useAudioEngineOptional();
  const nhan = dongHo(ms / 1000);
  if (!engine) {
    // Audio khong con (hoac trang khong co): moc van la thong tin, hien tinh.
    return <span className="moc-audio moc-tinh">⏱ {nhan}</span>;
  }
  return (
    <button
      type="button"
      className="moc-audio"
      aria-label={`Tua audio tới ${nhan}`}
      onClick={() => engine.dieuKhien.tua(ms / 1000)}
    >
      ⏱ {nhan}
    </button>
  );
}

/** Thân bình luận, có màn che spoiler. */
function ThanBinhLuan({ bl }: { bl: Comment }) {
  const [hien, setHien] = useState(false);
  if (bl.spoiler && !hien) {
    return (
      <button
        type="button"
        className="spoiler-che"
        aria-expanded={false}
        onClick={() => setHien(true)}
      >
        <span aria-hidden="true">⚠</span> Bình luận có spoiler ·{" "}
        <strong>Hiện spoiler</strong>
      </button>
    );
  }
  return <p className="binh-luan-chu">{bl.text}</p>;
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
        {bl.author?.is_author && bl.author.rank ? (
          <RankBadge rank={bl.author.rank} size="sm" />
        ) : null}
        {bl.timestamp_ms !== null && bl.timestamp_ms !== undefined ? (
          <MocAudio ms={bl.timestamp_ms} />
        ) : null}
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
        <ThanBinhLuan bl={bl} />
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
  targetKind = "post",
  limits,
  placeholder,
  onCountChange,
}: {
  /** Id của ĐÍCH — bài đăng, hoặc chương khi `targetKind="chapter"`. */
  postId: string;
  targetKind?: DichKind;
  limits: ServerLimits | null;
  /** Ghi đè câu mời của composer — chương dùng "Bạn nghĩ gì về chương này?". */
  placeholder?: string;
  /** Nơi chứa hiện số bình luận, nên nó cần biết khi số đó đổi. */
  onCountChange?: (delta: number) => void;
}) {
  const { profile } = useSession();
  const pathname = usePathname();
  const laChuong = targetKind === "chapter";
  const [ds, setDs] = useState<Comment[] | null>(null);
  const [tong, setTong] = useState(0);
  const [loi, setLoi] = useState("");
  const [dangTraLoi, setDangTraLoi] = useState("");
  /** Chỉ chương mới đổi được thứ tự; bài đăng luôn cũ→mới. */
  const [sort, setSort] = useState<"moi" | "cu">(laChuong ? "moi" : "cu");
  const tranChu = limits?.comment_max_chars ?? 1000;
  const goi = nguon(targetKind, postId);

  useEffect(() => {
    let huy = false;
    nguon(targetKind, postId)
      .list(sort, 20, 0)
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
  }, [postId, targetKind, sort]);

  const themGoc = useCallback(
    async (text: string, extras: { timestamp_ms: number | null; spoiler: boolean }) => {
      const ra = await goi.create({
        text,
        ...(laChuong
          ? { timestamp_ms: extras.timestamp_ms, spoiler: extras.spoiler }
          : {}),
      });
      // Chuong sap MOI truoc -> len dau; bai dang cu->moi -> xuong cuoi.
      setDs((truoc) =>
        laChuong && sort === "moi"
          ? [{ ...ra.comment, replies: [] }, ...(truoc ?? [])]
          : [...(truoc ?? []), { ...ra.comment, replies: [] }],
      );
      setTong((t) => t + 1);
      onCountChange?.(1);
    },
    [goi, laChuong, sort, onCountChange],
  );

  const themTraLoi = useCallback(
    async (chaId: string, text: string) => {
      const ra = await goi.create({ text, parent_id: chaId });
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
    [goi, onCountChange],
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
          moTa={placeholder ?? "Viết bình luận…"}
          chuong={laChuong}
          onGui={themGoc}
        />
      ) : (
        <p className="hint">
          <Link href={loginHref(pathname)}>Đăng nhập</Link> để bình luận.
        </p>
      )}

      {laChuong && tong > 1 ? (
        <div className="row" style={{ gap: 6 }}>
          {(["moi", "cu"] as const).map((k) => (
            <button
              key={k}
              type="button"
              className={sort === k ? "btn btn-sm" : "btn btn-ghost btn-sm"}
              aria-pressed={sort === k}
              onClick={() => setSort(k)}
            >
              {k === "moi" ? "Mới nhất" : "Cũ nhất"}
            </button>
          ))}
        </div>
      ) : null}

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
            const ra = await goi.list(sort, 50, ds.length);
            setDs((truoc) => [...(truoc ?? []), ...ra.items]);
          }}
        >
          Xem thêm bình luận ({tong - ds.length})
        </button>
      ) : null}
    </div>
  );
}
