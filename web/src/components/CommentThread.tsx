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
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  social,
  type Comment,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { loginHref } from "@/lib/nav";
import { khiNao, dongHo } from "@/lib/time";
import { hoSoHref, taoKhoaGui } from "@/lib/communityFeed";
import { ReportDialog } from "@/components/ReportDialog";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { useAudioEngineOptional } from "@/components/AudioEngine";
import { UserAvatar, tenHienThi } from "@/components/UserAvatar";
import { ConfirmDialog } from "@/components/ui";

type DichKind = "post" | "chapter" | "animation_episode";

function khoaMoi(): string {
  return taoKhoaGui(() =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36),
  );
}

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
  if (kind === "animation_episode") {
    // Cùng khả năng đổi thứ tự với "chapter" (backend nhận cùng `sort`), NHƯNG
    // không có mốc thời gian/spoiler: một tập là video YouTube, không phải
    // audio của Fanfic — xem `SocialService.create_episode_comment`.
    return {
      list: (sort: "moi" | "cu", limit: number, offset: number) =>
        social.episodeComments(id, sort, limit, offset),
      create: (payload: { text: string; parent_id?: string }) =>
        social.createEpisodeComment(id, payload),
    };
  }
  return {
    list: (_sort: "moi" | "cu", limit: number, offset: number) =>
      social.comments(id, limit, offset),
    create: (payload: { text: string; parent_id?: string; client_key?: string; spoiler?: boolean }) =>
      social.createComment(id, payload.text, payload.parent_id ?? "", {
        ...(payload.client_key ? { client_key: payload.client_key } : {}),
        ...(payload.spoiler ? { spoiler: true } : {}),
      }),
  };
}

/** Hộp gõ. Ở chế độ chương, kèm nút đính mốc audio + cờ spoiler. */
function OGo({
  tranChu,
  nhan,
  moTa,
  chuong = false,
  choSpoiler = false,
  chapterId,
  onGui,
  onHuy,
  giaTriDau = "",
}: {
  tranChu: number;
  nhan: string;
  moTa: string;
  /** Bật các khả năng riêng của bình luận chương. */
  chuong?: boolean;
  /** Cho đánh dấu spoiler ngoài chế độ chương (bình luận bài đăng, V1). */
  choSpoiler?: boolean;
  /** Chương ĐANG xem — dùng để kiểm engine toàn cục có đúng đang phát CHƯƠNG
      NÀY không (provider giờ là toàn cục, có thể đang phát một chương khác
      hoàn toàn). Chỉ có ý nghĩa khi `chuong` là true. */
  chapterId?: string;
  onGui: (text: string, extras: {
    timestamp_ms: number | null;
    spoiler: boolean;
    /** Khoá idempotent của LẦN gửi này — giữ nguyên qua mọi lần bấm lại. */
    client_key: string;
  }) => Promise<void>;
  onHuy?: () => void;
  /** Chữ sẵn có (khi sửa một bình luận). */
  giaTriDau?: string;
}) {
  const { profile } = useSession();
  const engine = useAudioEngineOptional();
  const [chu, setChu] = useState(giaTriDau);
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState("");
  /** Mốc đã ĐÓNG BĂNG lúc bấm nút — không trôi theo audio đang phát. */
  const [moc, setMoc] = useState<number | null>(null);
  const [spoiler, setSpoiler] = useState(false);
  const khoa = useRef("");

  const gui = useCallback(async () => {
    if (!chu.trim() || dangGui) return;
    if (!khoa.current) khoa.current = khoaMoi();
    setDangGui(true);
    setLoi("");
    try {
      await onGui(chu.trim(), { timestamp_ms: moc, spoiler, client_key: khoa.current });
      khoa.current = "";
      setChu("");
      setMoc(null);
      setSpoiler(false);
    } catch (e) {
      // GIU chu va khoa: bam lai la gui DUNG binh luan do, khong thanh hai.
      setLoi(
        e instanceof ApiError
          ? `${e.message} Chữ của bạn vẫn còn — bấm lại để thử.`
          : "Mất kết nối. Chữ của bạn vẫn còn — bấm lại để thử.",
      );
    } finally {
      setDangGui(false);
    }
  }, [chu, dangGui, moc, spoiler, onGui]);

  return (
    <div className="binh-luan-go">
      <div className="binh-luan-go-hang">
        <UserAvatar user={profile} className="avatar avatar-sm" />
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
            Nut dinh moc chi hien khi engine TOAN CUC dang phat DUNG chuong
            nay (khong chi "co provider" — provider gio luon co mat, co the
            dang phat mot chuong khac). Bam mot lan DONG BANG vi tri hien tai;
            bam lai thi bo. Khong tu cap nhat theo audio dang chay — nguoi ta
            muon danh dau "cho toi VUA nghe", khong phai mot con so troi.
          */}
          {engine && chapterId && engine.trangThai.chapterId === chapterId ? (
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
      ) : choSpoiler ? (
        <div className="row binh-luan-cong-cu">
          <label className="radio-hang binh-luan-spoiler">
            <input type="checkbox" checked={spoiler} onChange={(e) => setSpoiler(e.target.checked)} />
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

/**
 * Mốc audio trên một bình luận: bấm để tua — qua CHÍNH engine dùng chung.
 *
 * `chapterId` PHẢI khớp `engine.trangThai.chapterId`: provider giờ là toàn
 * cục, nên chỉ "có engine" không còn nghĩa là "engine đang phát CHƯƠNG NÀY"
 * — nó có thể đang phát một chương khác hoàn toàn (người dùng mở bài này
 * trong lúc chương khác đang phát ở MiniPlayer toàn cục).
 */
function MocAudio({ ms, chapterId }: { ms: number; chapterId?: string }) {
  const engine = useAudioEngineOptional();
  const nhan = dongHo(ms / 1000);
  if (!engine || !chapterId || engine.trangThai.chapterId !== chapterId) {
    // Audio khong phai cua chuong nay (hoac khong con/trang khong co): moc
    // van la thong tin, hien tinh.
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
  chapterId,
  onTraLoi,
  onDoi,
  onXoa,
}: {
  bl: Comment;
  tra: boolean;
  tranChu: number;
  /** Chỉ có ở chế độ chương — xem `MocAudio`. */
  chapterId?: string;
  onTraLoi?: () => void;
  onDoi: (moi: Comment) => void;
  onXoa: () => void;
}) {
  const { profile } = useSession();
  const [dangSua, setDangSua] = useState(false);
  const [baoCao, setBaoCao] = useState(false);
  const [hoiXoa, setHoiXoa] = useState(false);
  const [dangXoa, setDangXoa] = useState(false);
  const [loiXoa, setLoiXoa] = useState("");
  const cuaToi = !!profile && profile.user_id === bl.author_user_id;
  const daGo = bl.state !== "visible";
  const href = hoSoHref(bl.author);
  const ten = tenHienThi(bl.author);

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
        <UserAvatar user={bl.author} className="avatar avatar-sm" link />
        {href ? (
          <Link href={href} className="binh-luan-ten">
            {ten}
          </Link>
        ) : (
          <span className="binh-luan-ten">{ten}</span>
        )}
        {bl.author?.is_author ? <AuthorBadge size="sm" /> : null}
        {bl.author?.is_author && bl.author.rank ? (
          <RankBadge rank={bl.author.rank} size="sm" />
        ) : null}
        {bl.timestamp_ms !== null && bl.timestamp_ms !== undefined ? (
          <MocAudio ms={bl.timestamp_ms} chapterId={chapterId} />
        ) : null}
        <span className="hint">
          {khiNao(bl.created_at)}
          {bl.edited ? " · đã chỉnh sửa" : null}
        </span>
      </div>

      {dangSua ? (
        <OGo
          tranChu={tranChu}
          nhan="Lưu"
          moTa="Sửa bình luận"
          giaTriDau={bl.text}
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
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setHoiXoa(true)}>
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

      {loiXoa ? (
        <p className="hint loi" role="alert">
          {loiXoa}
        </p>
      ) : null}

      {baoCao ? (
        <ReportDialog
          targetKind="comment"
          targetId={bl.comment_id}
          onClose={() => setBaoCao(false)}
        />
      ) : null}

      <ConfirmDialog
        open={hoiXoa}
        title="Xoá bình luận này?"
        body="Không hoàn tác được."
        confirmLabel="Xoá"
        danger
        busy={dangXoa}
        onCancel={() => setHoiXoa(false)}
        onConfirm={async () => {
          if (dangXoa) return;
          setDangXoa(true);
          setLoiXoa("");
          try {
            await social.deleteComment(bl.comment_id);
            setHoiXoa(false);
            onXoa();
          } catch (e) {
            setHoiXoa(false);
            setLoiXoa(e instanceof ApiError ? e.message : "Không xoá được bình luận.");
          } finally {
            setDangXoa(false);
          }
        }}
      />
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
  /** Chương VÀ tập animation đều đổi được thứ tự; bài đăng luôn cũ→mới. */
  const coTheDoiThuTu = laChuong || targetKind === "animation_episode";
  const [ds, setDs] = useState<Comment[] | null>(null);
  const [tong, setTong] = useState(0);
  const [loi, setLoi] = useState("");
  const [dangTraLoi, setDangTraLoi] = useState("");
  const [sort, setSort] = useState<"moi" | "cu">(coTheDoiThuTu ? "moi" : "cu");
  const tranChu = limits?.comment_max_chars ?? 1000;
  const goi = nguon(targetKind, postId);
  /* Bình luận BÀI ĐĂNG có spoiler/khoá idempotent chỉ khi máy chủ là bản V1
     (nó trả `capabilities`) — máy chủ cũ bỏ qua trường lạ, nút sẽ nói dối. */
  const mayChuV1 = Boolean(limits?.capabilities);
  const [loiThem, setLoiThem] = useState("");

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
    async (
      text: string,
      extras: { timestamp_ms: number | null; spoiler: boolean; client_key: string },
    ) => {
      const ra = await goi.create({
        text,
        ...(laChuong
          ? { timestamp_ms: extras.timestamp_ms, spoiler: extras.spoiler }
          : targetKind === "post" && mayChuV1
            ? { spoiler: extras.spoiler, client_key: extras.client_key }
            : {}),
      });
      // Lan gui lap lai cung khoa: may chu tra lai DUNG binh luan cu — khong them lan nua.
      if ((ds ?? []).some((x) => x.comment_id === ra.comment.comment_id)) return;
      // Chuong/tap sap MOI truoc -> len dau; bai dang cu->moi -> xuong cuoi.
      setDs((truoc) =>
        coTheDoiThuTu && sort === "moi"
          ? [{ ...ra.comment, replies: [] }, ...(truoc ?? [])]
          : [...(truoc ?? []), { ...ra.comment, replies: [] }],
      );
      setTong((t) => t + 1);
      onCountChange?.(1);
    },
    [goi, laChuong, targetKind, mayChuV1, ds, coTheDoiThuTu, sort, onCountChange],
  );

  const themTraLoi = useCallback(
    async (chaId: string, text: string, client_key: string) => {
      const ra = await goi.create({
        text,
        parent_id: chaId,
        ...(targetKind === "post" && mayChuV1 ? { client_key } : {}),
      });
      const cha = (ds ?? []).find((c) => c.comment_id === chaId);
      if (cha?.replies?.some((r) => r.comment_id === ra.comment.comment_id)) {
        setDangTraLoi("");
        return;
      }
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
    [goi, targetKind, mayChuV1, ds, onCountChange],
  );

  const taiThem = useCallback(
    async (lam: () => Promise<void>) => {
      setLoiThem("");
      try {
        await lam();
      } catch (e) {
        setLoiThem(e instanceof ApiError ? e.message : "Không tải thêm được. Thử lại nhé.");
      }
    },
    [],
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
          choSpoiler={targetKind === "post" && mayChuV1}
          chapterId={laChuong ? postId : undefined}
          onGui={themGoc}
        />
      ) : (
        <p className="hint">
          <Link href={loginHref(pathname)}>Đăng nhập</Link> để bình luận.
        </p>
      )}

      {coTheDoiThuTu && tong > 1 ? (
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
                  chapterId={laChuong ? postId : undefined}
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
                    chapterId={laChuong ? postId : undefined}
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
                  onClick={() =>
                    void taiThem(async () => {
                      const ra = await social.replies(c.comment_id, 50);
                      setDs((truoc) =>
                        (truoc ?? []).map((x) =>
                          x.comment_id === c.comment_id ? { ...x, replies: ra.items } : x,
                        ),
                      );
                    })
                  }
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
                  onGui={(text, extras) => themTraLoi(c.comment_id, text, extras.client_key)}
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
          onClick={() =>
            void taiThem(async () => {
              const ra = await goi.list(sort, 50, ds.length);
              setDs((truoc) => {
                const da = new Set((truoc ?? []).map((x) => x.comment_id));
                return [...(truoc ?? []), ...ra.items.filter((x) => !da.has(x.comment_id))];
              });
            })
          }
        >
          Xem thêm bình luận ({tong - ds.length})
        </button>
      ) : null}
      {loiThem ? (
        <p className="hint loi" role="alert">
          {loiThem}
        </p>
      ) : null}
    </div>
  );
}
