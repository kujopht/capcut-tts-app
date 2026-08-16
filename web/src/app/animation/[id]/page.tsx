"use client";

/**
 * Chi tiet series Animation (overnight Phase 5, V6): thong tin, danh sach tap,
 * VA khu quan ly cho chu so huu (sua thong tin, them tap, xuat ban/go, xoa).
 *
 * CUNG KIEN TRUC voi `/novels/[id]` (xem file do): mot trang, hai che do hien
 * thi tuy `isOwner`, khong phai hai trang rieng.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import {
  api,
  type AnimationEpisode,
  type AnimationSeries,
  type Novel,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  EmptyState,
  ErrorState,
  SkeletonList,
  formatDate,
} from "@/components/ui";
import { NovelCover } from "@/components/NovelCover";
import { YoutubeUrlPreview } from "@/components/YoutubeUrlPreview";
import { parseYoutubeVideoId } from "@/lib/youtubeUrl";

export default function AnimationSeriesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();
  const router = useRouter();

  const fetchSeries = useCallback(() => api.getAnimationSeries(id), [id]);
  const { data, loading, error, missing, reload, setData } = useAsyncData(fetchSeries);
  const series: AnimationSeries | null = data?.series ?? null;
  const episodes: AnimationEpisode[] = data?.episodes ?? [];

  const [dangXuLy, setDangXuLy] = useState(false);
  const [thongBao, setThongBao] = useState("");

  // -- them tap --------------------------------------------------------------
  const [tenTap, setTenTap] = useState("");
  const [urlTap, setUrlTap] = useState("");
  const urlTapHopLe = !urlTap.trim() || parseYoutubeVideoId(urlTap.trim()) !== null;

  const themTap = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!series || !tenTap.trim() || !urlTap.trim() || !urlTapHopLe) return;
    setDangXuLy(true);
    setThongBao("");
    try {
      const { episode } = await api.createAnimationEpisode(
        series.series_id, tenTap, urlTap, episodes.length + 1,
      );
      setData((cur) => (cur ? { ...cur, episodes: [...cur.episodes, episode] } : cur));
      setTenTap("");
      setUrlTap("");
    } catch (cause) {
      setThongBao(errorMessage(cause));
    } finally {
      setDangXuLy(false);
    }
  };

  // -- sua tap (Phan 1, animation-youtube-polish-v1) --------------------------
  const [dangSuaTapId, setDangSuaTapId] = useState<string | null>(null);
  const [suaTenTap, setSuaTenTap] = useState("");
  const [suaUrlTap, setSuaUrlTap] = useState("");
  const [suaThuTuTap, setSuaThuTuTap] = useState(1);
  const suaUrlTapHopLe =
    !suaUrlTap.trim() || parseYoutubeVideoId(suaUrlTap.trim()) !== null;

  const moSuaTap = (ep: AnimationEpisode, thuTu: number) => {
    setDangSuaTapId(ep.episode_id);
    setSuaTenTap(ep.title);
    setSuaUrlTap("");
    setSuaThuTuTap(thuTu);
    setThongBao("");
  };

  const dongSuaTap = () => setDangSuaTapId(null);

  const luuSuaTap = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dangSuaTapId || !suaTenTap.trim() || !suaUrlTapHopLe) return;
    setDangXuLy(true);
    setThongBao("");
    try {
      await api.updateAnimationEpisode(dangSuaTapId, {
        title: suaTenTap,
        ...(suaUrlTap.trim() ? { youtube_url: suaUrlTap.trim() } : {}),
        order_index: suaThuTuTap,
      });
      setDangSuaTapId(null);
      reload();
    } catch (cause) {
      setThongBao(errorMessage(cause));
    } finally {
      setDangXuLy(false);
    }
  };

  const xoaTap = async (episodeId: string) => {
    if (!confirm("Xoá tập này? Không thể hoàn tác.")) return;
    setDangXuLy(true);
    try {
      await api.deleteAnimationEpisode(episodeId);
      setData((cur) =>
        cur
          ? { ...cur, episodes: cur.episodes.filter((e) => e.episode_id !== episodeId) }
          : cur,
      );
    } catch (cause) {
      setThongBao(errorMessage(cause));
    } finally {
      setDangXuLy(false);
    }
  };

  const xuatBan = async () => {
    if (!series) return;
    setDangXuLy(true);
    setThongBao("");
    try {
      const { series: moi } = series.state === "published"
        ? await api.unpublishAnimationSeries(series.series_id)
        : await api.publishAnimationSeries(series.series_id);
      setData((cur) => (cur ? { ...cur, series: moi } : cur));
    } catch (cause) {
      setThongBao(errorMessage(cause));
    } finally {
      setDangXuLy(false);
    }
  };

  const xoaSeries = async () => {
    if (!series) return;
    if (!confirm(`Xoá series "${series.title}" cùng mọi tập? Không thể hoàn tác.`)) return;
    setDangXuLy(true);
    try {
      await api.deleteAnimationSeries(series.series_id);
      router.push("/animation");
    } catch (cause) {
      setThongBao(errorMessage(cause));
      setDangXuLy(false);
    }
  };

  // -- sua thong tin series + gan truyen goc (Phan 4, animation-youtube-polish-v1) --
  const isOwner = profile?.user_id === series?.owner_id;
  const [dangSuaSeries, setDangSuaSeries] = useState(false);
  const [suaTieuDe, setSuaTieuDe] = useState("");
  const [suaMoTa, setSuaMoTa] = useState("");
  const [suaTruyenGoc, setSuaTruyenGoc] = useState("");
  const [danhSachTruyen, setDanhSachTruyen] = useState<Novel[] | null>(null);

  useEffect(() => {
    if (!isOwner || danhSachTruyen !== null) return;
    // CHI tai danh sach truyen CUA CHINH minh — nguoi dung khong the gan
    // series toi truyen cua nguoi khac, khop rang buoc owner_id o backend.
    api.listNovels(true).then(
      ({ novels }) => setDanhSachTruyen(novels),
      () => setDanhSachTruyen([]),
    );
  }, [isOwner, danhSachTruyen]);

  const moSuaSeries = () => {
    if (!series) return;
    setSuaTieuDe(series.title);
    setSuaMoTa(series.description);
    setSuaTruyenGoc(series.related_novel_id || "");
    setDangSuaSeries(true);
    setThongBao("");
  };

  const luuSuaSeries = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!series || !suaTieuDe.trim()) return;
    setDangXuLy(true);
    setThongBao("");
    try {
      const { series: moi } = await api.updateAnimationSeries(series.series_id, {
        title: suaTieuDe,
        description: suaMoTa,
        related_novel_id: suaTruyenGoc,
      });
      setData((cur) => (cur ? { ...cur, series: moi } : cur));
      setDangSuaSeries(false);
    } catch (cause) {
      setThongBao(errorMessage(cause));
    } finally {
      setDangXuLy(false);
    }
  };

  if (loading) {
    return (
      <div className="page">
        <div className="sk sk-title" style={{ height: 32, width: "40%" }} />
        <SkeletonList count={5} />
      </div>
    );
  }

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy series này"
          hint="Series có thể đã bị xoá hoặc chưa được xuất bản."
          action={
            <Link className="btn btn-primary" href="/animation">
              Về trang Animation
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !series) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được series."} onRetry={reload} />
      </div>
    );
  }

  return (
    <div className="page">
      <nav aria-label="Đường dẫn">
        <Link href="/animation" className="hint crumb">
          ← Animation
        </Link>
      </nav>

      <header className="novel-head">
        <div className="novel-head-cover">
          <NovelCover
            novelId={series.series_id}
            title={series.title}
            coverUrl={series.cover_url}
            size="card"
          />
        </div>

        <div className="stack-2 novel-head-body">
          <div className="row novel-head-tags">
            <span className={`badge ${series.state === "published" ? "badge-ok" : ""}`}>
              {series.state === "published" ? "Đã xuất bản" : "Bản nháp"}
            </span>
            {series.tags.map((tag) => (
              <span key={tag} className="badge">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="page-title">{series.title}</h1>
          <p className="lead lead-narrow">
            {series.description || "Chưa có mô tả."}
          </p>
          <span className="hint">
            {episodes.length} tập · cập nhật {formatDate(series.updated_at)}
          </span>

          <div className="row novel-head-actions">
            {episodes.length > 0 ? (
              <Link
                className="btn btn-primary"
                href={`/animation/watch/${episodes[0].episode_id}`}
              >
                Xem từ tập 1
              </Link>
            ) : null}
            {series.related_novel_id ? (
              <Link className="btn" href={`/novels/${series.related_novel_id}`}>
                Truyện gốc
              </Link>
            ) : null}
            {isOwner ? (
              <>
                <button type="button" className="btn" onClick={moSuaSeries}
                        disabled={dangXuLy}>
                  Sửa thông tin
                </button>
                <button type="button" className="btn" onClick={xuatBan}
                        disabled={dangXuLy}>
                  {series.state === "published" ? "Gỡ xuất bản" : "Xuất bản"}
                </button>
                <button type="button" className="btn btn-danger" onClick={xoaSeries}
                        disabled={dangXuLy}>
                  Xoá series
                </button>
              </>
            ) : null}
          </div>
          {thongBao ? (
            <p className="hint" role="alert">{thongBao}</p>
          ) : null}
        </div>
      </header>

      {isOwner && dangSuaSeries ? (
        <form
          className="card stack-2"
          aria-label="Sửa thông tin series"
          onSubmit={luuSuaSeries}
        >
          <h2 className="section-title">Sửa thông tin series</h2>
          <div className="field">
            <label className="label" htmlFor="series-title">Tên series</label>
            <input
              id="series-title"
              className="input"
              value={suaTieuDe}
              onChange={(e) => setSuaTieuDe(e.target.value)}
              maxLength={200}
              required
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="series-desc">Mô tả</label>
            <textarea
              id="series-desc"
              className="input"
              value={suaMoTa}
              onChange={(e) => setSuaMoTa(e.target.value)}
              rows={3}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="series-novel">
              Truyện gốc (không bắt buộc)
            </label>
            <select
              id="series-novel"
              className="input"
              value={suaTruyenGoc}
              onChange={(e) => setSuaTruyenGoc(e.target.value)}
            >
              <option value="">— Không gắn với truyện nào —</option>
              {(danhSachTruyen ?? []).map((novel) => (
                <option key={novel.novel_id} value={novel.novel_id}>
                  {novel.title}
                </option>
              ))}
            </select>
          </div>
          <div className="row row-tight">
            <button type="submit" className="btn btn-primary" disabled={dangXuLy}>
              Lưu
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setDangSuaSeries(false)}
              disabled={dangXuLy}
            >
              Huỷ
            </button>
          </div>
        </form>
      ) : null}

      <section className="stack" aria-label="Danh sách tập">
        <h2 className="section-title">Danh sách tập</h2>
        {episodes.length === 0 ? (
          <EmptyState icon="🎬" title="Series chưa có tập nào" />
        ) : (
          <div className="anim-ep-list">
            {episodes.map((ep, index) =>
              isOwner && dangSuaTapId === ep.episode_id ? (
                <form
                  key={ep.episode_id}
                  className="card stack-2"
                  aria-label={`Sửa tập ${ep.title}`}
                  onSubmit={luuSuaTap}
                >
                  <div className="field">
                    <label className="label" htmlFor={`ep-edit-title-${ep.episode_id}`}>
                      Tên tập
                    </label>
                    <input
                      id={`ep-edit-title-${ep.episode_id}`}
                      className="input"
                      value={suaTenTap}
                      onChange={(e) => setSuaTenTap(e.target.value)}
                      maxLength={200}
                      required
                    />
                  </div>
                  <div className="field">
                    <label className="label" htmlFor={`ep-edit-url-${ep.episode_id}`}>
                      Đường dẫn YouTube mới (bỏ trống nếu giữ nguyên video)
                    </label>
                    <input
                      id={`ep-edit-url-${ep.episode_id}`}
                      className="input"
                      value={suaUrlTap}
                      onChange={(e) => setSuaUrlTap(e.target.value)}
                      placeholder="https://www.youtube.com/watch?v=…"
                    />
                    <YoutubeUrlPreview url={suaUrlTap} />
                  </div>
                  <div className="field">
                    <label className="label" htmlFor={`ep-edit-order-${ep.episode_id}`}>
                      Số thứ tự
                    </label>
                    <input
                      id={`ep-edit-order-${ep.episode_id}`}
                      className="input"
                      type="number"
                      min={1}
                      value={suaThuTuTap}
                      onChange={(e) => setSuaThuTuTap(Number(e.target.value) || 1)}
                    />
                  </div>
                  <div className="row row-tight">
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={dangXuLy || !suaUrlTapHopLe}
                    >
                      Lưu
                    </button>
                    <button
                      type="button"
                      className="btn"
                      onClick={dongSuaTap}
                      disabled={dangXuLy}
                    >
                      Huỷ
                    </button>
                  </div>
                </form>
              ) : (
                <Link
                  key={ep.episode_id}
                  href={`/animation/watch/${ep.episode_id}`}
                  className="card row anim-ep-row"
                >
                  <span className="anim-ep-row-num" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span className="truncate list-title">{ep.title}</span>
                  {isOwner ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={(e) => {
                          e.preventDefault();
                          moSuaTap(ep, index + 1);
                        }}
                        disabled={dangXuLy}
                      >
                        Sửa
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-danger"
                        onClick={(e) => {
                          e.preventDefault();
                          xoaTap(ep.episode_id);
                        }}
                        disabled={dangXuLy}
                      >
                        Xoá
                      </button>
                    </>
                  ) : null}
                </Link>
              ),
            )}
          </div>
        )}
      </section>

      {isOwner ? (
        <section className="card stack-2" aria-label="Thêm tập mới">
          <h2 className="section-title">Thêm tập từ YouTube</h2>
          <form className="stack-2" onSubmit={themTap}>
            <div className="field">
              <label className="label" htmlFor="ep-title">Tên tập</label>
              <input
                id="ep-title"
                className="input"
                value={tenTap}
                onChange={(e) => setTenTap(e.target.value)}
                placeholder="Ví dụ: Tập 1 — Khởi đầu"
                maxLength={200}
              />
            </div>
            <div className="field">
              <label className="label" htmlFor="ep-url">Đường dẫn YouTube</label>
              <input
                id="ep-url"
                className="input"
                value={urlTap}
                onChange={(e) => setUrlTap(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=…"
              />
              <YoutubeUrlPreview url={urlTap} />
            </div>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={dangXuLy || !urlTap.trim() || !urlTapHopLe}
            >
              Thêm tập
            </button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
