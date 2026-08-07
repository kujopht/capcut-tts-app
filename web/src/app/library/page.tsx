"use client";

/**
 * Thu vien audio cua toi: gom ca audio tao nhanh o Audio Studio lan audio
 * cua chuong fanfic. Danh dau ro nguon de khong lan hai khu vuc.
 */

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { api, type Chapter, type Novel, type TtsJob } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { isStudioNovel } from "@/lib/workspace";
import { AudioPlayer } from "@/components/AudioPlayer";
import { NovelCover } from "@/components/NovelCover";
import {
  EmptyState,
  ErrorState,
  JobBadge,
  Loading,
  SkeletonList,
  formatDate,
  formatNumber,
} from "@/components/ui";

type Source = "all" | "studio" | "fanfic";

interface Row {
  job: TtsJob;
  chapter: Chapter;
  novel: Novel;
  fromStudio: boolean;
}

export default function LibraryPage() {
  const { profile, loading: sessionLoading } = useSession();
  const [source, setSource] = useState<Source>("all");
  const [playing, setPlaying] = useState("");

  const gather = useCallback(async (): Promise<Row[]> => {
    const [novelList, jobList] = await Promise.all([
      api.listNovels(true),
      api.listJobs(),
    ]);
    const details = await Promise.all(
      novelList.novels.map((novel) =>
        api
          .getNovel(novel.novel_id)
          .then((detail) => ({ novel, chapters: detail.chapters }))
          .catch(() => ({ novel, chapters: [] as Chapter[] })),
      ),
    );

    const index = new Map<string, { chapter: Chapter; novel: Novel }>();
    details.forEach(({ novel, chapters }) =>
      chapters.forEach((chapter) => index.set(chapter.chapter_id, { chapter, novel })),
    );

    return jobList.jobs
      .filter((job) => job.status === "completed")
      .map((job) => {
        const found = index.get(job.chapter_id);
        if (!found) return null;
        return {
          job,
          chapter: found.chapter,
          novel: found.novel,
          fromStudio: isStudioNovel(found.novel),
        };
      })
      .filter((row): row is Row => row !== null);
  }, []);

  const { data, loading, error, reload } = useAsyncData(gather, {
    enabled: Boolean(profile) && !sessionLoading,
  });
  const rows = useMemo(() => data ?? [], [data]);

  const shown = useMemo(() => {
    if (source === "studio") return rows.filter((r) => r.fromStudio);
    if (source === "fanfic") return rows.filter((r) => !r.fromStudio);
    return rows;
  }, [rows, source]);

  const counts = useMemo(
    () => ({
      all: rows.length,
      studio: rows.filter((r) => r.fromStudio).length,
      fanfic: rows.filter((r) => !r.fromStudio).length,
    }),
    [rows],
  );

  if (sessionLoading) {
    return (
      <div className="page">
        <Loading label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="page">
        <h1 className="page-title">Thư viện audio</h1>
        <EmptyState
          icon="🔐"
          title="Cần đăng nhập để xem thư viện của bạn"
          hint="Thư viện chỉ chứa audio do chính bạn tạo."
          action={
            <Link className="btn btn-primary" href="/login">
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="page">
      <header className="row-between">
        <div className="stack-2">
          <span className="eyebrow">Thư viện</span>
          <h1 className="page-title">Audio của tôi</h1>
          <p className="lead" style={{ maxWidth: 600 }}>
            Tất cả audio đã tạo, gồm cả bản tạo nhanh ở Audio Studio và audio
            của các chương fanfic.
          </p>
        </div>
        <Link className="btn btn-primary" href="/studio">
          Tạo audio mới
        </Link>
      </header>

      {!loading && !error && rows.length > 0 ? (
        <div className="seg" role="group" aria-label="Lọc theo nguồn">
          {(
            [
              ["all", `Tất cả (${counts.all})`],
              ["studio", `Audio Studio (${counts.studio})`],
              ["fanfic", `Fanfic (${counts.fanfic})`],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className="seg-item"
              aria-pressed={source === value}
              onClick={() => setSource(value)}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {loading ? (
        <SkeletonList count={5} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon="🎧"
          title="Thư viện còn trống"
          hint="Tạo audio đầu tiên ở Audio Studio, hoặc thêm audio cho chương truyện của bạn."
          action={
            <div className="row">
              <Link className="btn btn-primary" href="/studio">
                Mở Audio Studio
              </Link>
              <Link className="btn" href="/write">
                Khu vực tác giả
              </Link>
            </div>
          }
        />
      ) : shown.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="Không có audio nào trong nhóm này"
          action={
            <button type="button" className="btn" onClick={() => setSource("all")}>
              Xem tất cả
            </button>
          }
        />
      ) : (
        <div className="stack">
          <p className="hint" role="status">
            {shown.length} bản audio
          </p>
          {shown.map((row) => (
            <article key={row.job.job_id} className="card stack">
              <div className="row-between">
                <NovelCover
                  novelId={row.novel.novel_id}
                  title={row.fromStudio ? row.chapter.title : row.novel.title}
                  coverUrl={row.novel.cover_url}
                  size="thumb"
                />
                <div className="stack-2" style={{ minWidth: 0, flex: 1 }}>
                  <div className="row" style={{ gap: "var(--s2)" }}>
                    <span className={`badge ${row.fromStudio ? "badge-brand" : "badge-info"}`}>
                      {row.fromStudio ? "Audio Studio" : "Fanfic"}
                    </span>
                    <JobBadge status={row.job.status} />
                  </div>
                  <strong>{row.chapter.title}</strong>
                  <span className="hint">
                    {row.fromStudio ? (
                      <>
                        {formatNumber(row.chapter.char_count)} ký tự ·{" "}
                        {formatDate(row.job.finished_at ?? row.job.created_at)}
                      </>
                    ) : (
                      <>
                        Thuộc truyện{" "}
                        <Link href={`/novels/${row.novel.novel_id}`}>
                          {row.novel.title}
                        </Link>{" "}
                        · {formatDate(row.job.finished_at ?? row.job.created_at)}
                      </>
                    )}
                  </span>
                </div>
                <div className="row" style={{ gap: "var(--s2)" }}>
                  {!row.fromStudio ? (
                    <Link className="btn btn-sm" href={`/chapters/${row.chapter.chapter_id}`}>
                      Mở chương
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    aria-expanded={playing === row.chapter.chapter_id}
                    onClick={() =>
                      setPlaying(
                        playing === row.chapter.chapter_id ? "" : row.chapter.chapter_id,
                      )
                    }
                  >
                    {playing === row.chapter.chapter_id ? "Đóng" : "Nghe"}
                  </button>
                </div>
              </div>

              {playing === row.chapter.chapter_id ? (
                <AudioPlayer chapterId={row.chapter.chapter_id} title={row.chapter.title} />
              ) : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
