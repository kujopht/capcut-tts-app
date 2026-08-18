"use client";

/**
 * Trang XEM một tập Animation (overnight Phase 5, V6, Phần 5H).
 *
 * CÙNG KIẾN TRÚC với `/listen/[id]` (trang Nghe, Phase 2): điều hướng tập
 * trước/sau LUÔN hiện, chọn tập dạng danh sách gấp/mở, hai request tổng cộng
 * (tập hiện tại + series kèm mọi tập, dùng cho bộ chọn) bất kể series có bao
 * nhiêu tập — xem ghi chú ở `load()`.
 *
 * TRÌNH PHÁT là `YouTubeFacadePlayer` (facade + thanh điều khiển Fanfic Cinema
 * tuỳ chỉnh, xem docstring component đó — animation-player-v2-custom-controls).
 * Component đó tự quản lý toàn bộ vòng đời YT.Player; trang này chỉ nhận lại
 * tiến độ qua `onProgress` để ghi (`/api/progress/watch`), throttle 10s giữ
 * nguyên từ V1 — KHÔNG giữ ref/interval nào ở tầng trang nữa.
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
import { use, useCallback, useMemo, useState } from "react";
import {
  api,
  type AnimationEpisode,
  type AnimationSeries,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
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

export default function AnimationWatchPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();
  const toast = useToast();

  const [moChonTap, setMoChonTap] = useState(false);

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

  // Nhan tien do TU `YouTubeFacadePlayer` (component tu quan ly YT.Player,
  // throttle 10s, cap nhat cuc bo cho thanh tien do — xem docstring component
  // do). O day CHI ghi vao backend, VA CHI khi da dang nhap — nguoi xem chua
  // dang nhap van dieu khien duoc video day du, chi khong co "Tiep tuc xem".
  const onProgress = useCallback(
    (hienTaiGiay: number, doDaiGiay: number) => {
      if (!profile || !data) return;
      api
        .reportWatchProgress(
          data.series.series_id, data.episode.episode_id, hienTaiGiay, doDaiGiay,
        )
        .catch(() => {});
    },
    [profile, data],
  );

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
          {/* `YouTubeFacadePlayer` tu quan ly TOAN BO vong doi: facade → tai
              API → gan YT.Player → thanh dieu khien Fanfic → trang thai loi
              (video khong xem duoc HOAC API khong tai duoc). Trang nay chi
              can biet tien do de ghi backend, khong con giu ref/interval nao. */}
          <YouTubeFacadePlayer
            videoId={episode.external_id}
            title={episode.title}
            onProgress={onProgress}
          />
        </div>

        <div className="yt-cinema-foot">
          {/*
            Nguon goc (Trusted Channels) — TACH BIET voi thanh dieu khien
            Fanfic Player V2 o tren. `source_channel_title` RONG cho tap tao
            qua luong thu cong thuong (khong tu Trusted Channels) — van hien
            duong dan YouTube goc (moi tap LUON co `external_id` that), chi
            bo phan "Nguồn: <kênh>" khi khong biet kenh nao. KHONG bao gio
            bia ten kenh.
          */}
          <p className="yt-cinema-source hint">
            {episode.source_channel_title ? `Nguồn: ${episode.source_channel_title} · ` : ""}
            <a
              href={`https://www.youtube.com/watch?v=${episode.external_id}`}
              target="_blank"
              rel="noreferrer"
            >
              Xem video gốc trên YouTube ↗
            </a>
          </p>
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
