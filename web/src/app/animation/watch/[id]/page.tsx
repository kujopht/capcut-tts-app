"use client";

/**
 * Trang XEM một tập Animation (overnight Phase 5, V6, Phần 5H).
 *
 * CÙNG KIẾN TRÚC với `/listen/[id]` (trang Nghe, Phase 2): điều hướng tập
 * trước/sau LUÔN hiện, chọn tập dạng danh sách gấp/mở, hai request tổng cộng
 * (tập hiện tại + series kèm mọi tập, dùng cho bộ chọn) bất kể series có bao
 * nhiêu tập — xem ghi chú ở `load()`.
 *
 * TRÌNH PHÁT là `YouTubeFacadePlayer` (facade — không nhúng iframe thật cho
 * tới khi người xem bấm Play, xem docstring component đó). Tiến độ xem chỉ
 * được ghi (`/api/progress/watch`) SAU khi người xem đã bấm Play — không bao
 * giờ trước đó, vì trước Play chưa có iframe/YouTube IFrame API nào để đọc vị
 * trí thật.
 *
 * KHÔNG có mục "creator" riêng: `/novels/[id]` (trang truyện) cũng chưa hiển
 * thị tên tác giả trên trang chi tiết — theo đúng tiền lệ đó, trang này không
 * tự chế một tra cứu owner_id → hồ sơ công khai mới cho một mình nó.
 *
 * KHÔNG có "reactions" (thích/tim): chương truyện cũng chưa có cơ chế thích
 * chung nào để dùng lại (chỉ bài đăng cộng đồng có `/api/posts/{id}/like`) —
 * xây một hệ thống thích MỚI chỉ cho tập animation sẽ là "hệ thống thứ hai"
 * đúng thứ spec yêu cầu tránh cho bình luận, nên phần này để trống có chủ ý,
 * không giả một nút thích không làm gì.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type AnimationEpisode,
  type AnimationSeries,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { dongHo } from "@/lib/time";
import { loadYouTubeIframeApi, type YTPlayerInstance } from "@/lib/youtubeIframeApi";
import { YouTubeFacadePlayer } from "@/components/YouTubeFacadePlayer";
import { EpisodeComments } from "@/components/EpisodeComments";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui";
import { IconFilm } from "@/components/Icons";

interface WatchData {
  episode: AnimationEpisode;
  series: AnimationSeries;
  episodes: AnimationEpisode[];
  prevEpisodeId: string | null;
  nextEpisodeId: string | null;
}

/** Id ổn định cho iframe — chỉ một trình phát trên trang này tại một thời điểm. */
const IFRAME_ID = "anim-watch-player";

/** Báo tiến độ mỗi N giây phát — đủ mượt cho "Tiếp tục xem", không dội API
    mỗi vài trăm mili-giây như `timeupdate` của thẻ `<video>` thường làm. */
const KHOANG_BAO_CAO_GIAY = 10;

/** Ma loi cua YouTube IFrame API -> thong bao tieng Viet ro rang (Phan 3,
    animation-youtube-polish-v1). Video da xoa/rieng tu/tat nhung deu la
    loi phia CHU video, khong phai loi cua Fanfic — khong doan them chi tiet
    ngoai tai lieu chinh thuc de tranh noi sai nguyen nhan. */
function thongBaoLoiVideo(maLoi: number): string {
  switch (maLoi) {
    case 2:
      return "Đường dẫn video không hợp lệ.";
    case 5:
      return "Trình phát không hỗ trợ định dạng của video này.";
    case 100:
      return "Video này không còn tồn tại (có thể đã bị xoá hoặc đặt ở chế độ riêng tư).";
    case 101:
    case 150:
      return "Chủ video đã tắt tính năng phát trên trang khác cho video này.";
    default:
      return "Không thể phát video này lúc này.";
  }
}

export default function AnimationWatchPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();
  const toast = useToast();

  const [moChonTap, setMoChonTap] = useState(false);
  const [loiVideo, setLoiVideo] = useState<string | null>(null);
  // Chi de HIEN THI (thanh tien do trong khung "rap chieu") — KHONG phai
  // nguon that cho "Tiep tuc xem", van la `/api/progress/watch` o server.
  const [tienDo, setTienDo] = useState<{ viTri: number; doDai: number } | null>(null);
  const player = useRef<YTPlayerInstance | null>(null);
  const bao = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (): Promise<WatchData> => {
    const { episode, series, prev_episode_id, next_episode_id } =
      await api.getAnimationEpisode(id);
    // HAI request tong cong, khong phu thuoc so tap trong series — cung ly do
    // voi `/listen/[id]`: tap hien tai (o tren) + moi tap cua series (o day),
    // dung cho bo chon, KHONG goi lai cho tung tap khi nhay trong CUNG series
    // (trang nay re-mount moi lan doi route nen effect chi chay lai dung mot lan).
    const { episodes } = await api.getAnimationSeries(series.series_id);
    return {
      episode,
      series,
      episodes,
      prevEpisodeId: prev_episode_id,
      nextEpisodeId: next_episode_id,
    };
  }, [id]);

  const { data, loading, error, missing, reload } = useAsyncData(load);

  useEffect(() => {
    // KHONG can tu reset `loiVideo` o day: trang nay re-mount moi lan doi
    // route (xem ghi chu o `load()`), nen `useState` da tu ve gia tri dau
    // `null` cho tap moi — dat them mot `setState` dong bo trong than effect
    // se vi pham `react-hooks/set-state-in-effect` ma khong giai quyet gi hon.
    return () => {
      if (bao.current) clearInterval(bao.current);
      player.current?.destroy?.();
    };
  }, [id]);

  const guiTienDo = useCallback(() => {
    if (!player.current || !data) return;
    const viTri = player.current.getCurrentTime?.();
    const doDai = player.current.getDuration?.();
    if (typeof viTri !== "number" || Number.isNaN(viTri)) return;
    setTienDo({ viTri, doDai: doDai || 0 });
    api
      .reportWatchProgress(
        data.series.series_id, data.episode.episode_id, viTri, doDai || 0,
      )
      .catch(() => {});
  }, [data]);

  const batDauXem = useCallback(async () => {
    if (!profile) return;
    try {
      const YT = await loadYouTubeIframeApi();
      // Trinh phat facade da dung `<iframe id={IFRAME_ID}>` vao DOM luc nay
      // (nguoi xem vua bam Play) — gan YouTube IFrame API vao CHINH iframe do,
      // khong tao mot iframe thu hai.
      player.current = new YT.Player(IFRAME_ID, {
        events: {
          onReady: () => {
            guiTienDo();
            bao.current = setInterval(guiTienDo, KHOANG_BAO_CAO_GIAY * 1000);
          },
          onError: (event) => {
            if (bao.current) clearInterval(bao.current);
            setLoiVideo(thongBaoLoiVideo(event.data));
          },
        },
      });
    } catch {
      // API IFrame khong nap duoc (mang cham/bi chan) — nguoi xem VAN xem
      // duoc binh thuong qua chinh iframe YouTube, chi la "Tiep tuc xem"
      // se khong ghi duoc tien do cho lan xem nay. Khong chan phat vi chuyen
      // do.
    }
  }, [profile, guiTienDo]);

  const soThuTu = useMemo(
    () => new Map((data?.episodes ?? []).map((e, i) => [e.episode_id, i + 1])),
    [data],
  );

  const chiaSe = useCallback(async () => {
    if (!data) return;
    const url = `${window.location.origin}/animation/watch/${data.episode.episode_id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.ok("Đã chép liên kết tập phim.");
    } catch {
      toast.push("info", url);
    }
  }, [data, toast]);

  if (loading) {
    return (
      <div className="page">
        <div className="yt-cinema">
          <div className="yt-cinema-head">
            <div className="sk sk-text" style={{ width: "20%", marginBottom: 6 }} />
            <div className="sk sk-title" style={{ width: "45%" }} />
          </div>
          <div className="sk yt-cinema-stage-sk" />
        </div>
        <SkeletonList count={3} />
      </div>
    );
  }

  if (missing || (!loading && !data && !error)) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy tập này"
          hint="Tập có thể đã bị xoá, hoặc series chưa được xuất bản."
          action={
            <Link className="btn btn-primary" href="/animation">
              Về trang Animation
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được tập."} onRetry={reload} />
      </div>
    );
  }

  const { episode, series, episodes, prevEpisodeId, nextEpisodeId } = data;
  const chiSoHienTai = soThuTu.get(episode.episode_id) ?? 0;

  return (
    <div className="page">
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href={`/animation/${series.series_id}`} className="hint crumb">
          ← {series.title}
        </Link>
      </nav>

      <div className="yt-cinema">
        <header className="yt-cinema-head">
          <span className="eyebrow eyebrow-icon">
            <IconFilm size={17} /> Đang xem
          </span>
          <p className="yt-cinema-series truncate">{series.title}</p>
          <h1 className="page-title yt-cinema-title">{episode.title}</h1>
        </header>

        {/* Truoc/sau + chon tap LUON hien, giong `/listen/[id]`. */}
        <nav
          className="row row-spread listen-nav yt-cinema-toolbar"
          aria-label="Điều hướng tập"
        >
          {prevEpisodeId ? (
            <Link className="btn" href={`/animation/watch/${prevEpisodeId}`}>
              <span aria-hidden="true">←</span> Tập trước
            </Link>
          ) : (
            <span className="btn" aria-disabled="true">
              <span aria-hidden="true">←</span> Tập trước
            </span>
          )}
          <button
            type="button"
            className="btn btn-ghost"
            aria-expanded={moChonTap}
            onClick={() => setMoChonTap((v) => !v)}
          >
            Danh sách tập ({chiSoHienTai}/{episodes.length})
          </button>
          {nextEpisodeId ? (
            <Link className="btn" href={`/animation/watch/${nextEpisodeId}`}>
              Tập sau <span aria-hidden="true">→</span>
            </Link>
          ) : (
            <span className="btn" aria-disabled="true">
              Tập sau <span aria-hidden="true">→</span>
            </span>
          )}
        </nav>

        {moChonTap ? (
          <div className="listen-chon-tap" role="region" aria-label="Chọn tập để xem">
            <div className="anim-ep-list">
              {episodes.map((ep) => {
                const dangXem = ep.episode_id === episode.episode_id;
                return (
                  <Link
                    key={ep.episode_id}
                    href={`/animation/watch/${ep.episode_id}`}
                    className={`card anim-ep-row${dangXem ? " anim-ep-row-active" : ""}`}
                    aria-current={dangXem ? "true" : undefined}
                    onClick={() => setMoChonTap(false)}
                  >
                    <span className="anim-ep-row-num" aria-hidden="true">
                      {soThuTu.get(ep.episode_id)}
                    </span>
                    <span className="truncate list-title">{ep.title}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="yt-cinema-stage">
          {loiVideo ? (
            <div className="card anim-video-loi" role="alert">
              <p>{loiVideo}</p>
              <p className="hint">
                Bạn vẫn có thể chuyển sang tập khác bằng điều hướng phía trên.
              </p>
            </div>
          ) : (
            <YouTubeFacadePlayer
              videoId={episode.external_id}
              title={episode.title}
              iframeId={IFRAME_ID}
              onPlay={batDauXem}
            />
          )}
        </div>

        <div className="yt-cinema-foot">
          {tienDo ? (
            <div className="yt-cinema-progress">
              <div className="yt-cinema-progress-bar" aria-hidden="true">
                <div
                  className="yt-cinema-progress-fill"
                  style={{
                    width: `${
                      tienDo.doDai > 0
                        ? Math.min(100, (tienDo.viTri / tienDo.doDai) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
              <span className="hint yt-cinema-progress-time">
                {dongHo(tienDo.viTri)} / {dongHo(tienDo.doDai)}
              </span>
            </div>
          ) : null}

          <div className="row row-tight">
            <button type="button" className="btn btn-ghost" onClick={chiaSe}>
              <span aria-hidden="true">↗</span> Chia sẻ
            </button>
            {series.related_novel_id ? (
              <Link className="btn btn-ghost" href={`/novels/${series.related_novel_id}`}>
                Truyện gốc
              </Link>
            ) : null}
          </div>
        </div>
      </div>

      <EpisodeComments episodeId={episode.episode_id} />
    </div>
  );
}
