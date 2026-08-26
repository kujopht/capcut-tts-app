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
  PageHeader,
  SkeletonList,
  formatDate,
  formatNumber,
} from "@/components/ui";
import { IconLibrary , IconMic } from "@/components/Icons";
import { MotifCelestialDial } from "@/components/Ornaments";

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
    // BA request, du co bao nhieu truyen. Ban truoc goi `getNovel` cho TUNG
    // truyen chi de dung bang tra "chapter_id -> chuong + truyen": 16 truyen
    // ton 20 request, va con so do tang tuyen tinh theo so truyen.
    const [novelList, jobList, chapterList] = await Promise.all([
      api.listNovels(true),
      api.listJobs(),
      api.myChapters(),
    ]);

    const novelById = new Map(novelList.novels.map((n) => [n.novel_id, n]));
    const index = new Map<string, { chapter: Chapter; novel: Novel }>();
    chapterList.chapters.forEach((chapter) => {
      const novel = novelById.get(chapter.novel_id);
      // Chuong khong tra ra truyen thi bo qua — hang khong co ten truyen thi
      // hien ra chi lam nguoi dung boi roi.
      if (novel) index.set(chapter.chapter_id, { chapter, novel });
    });

    /*
      MOT DONG cho moi chuong, la ban HIEN HANH.

      Truoc day moi job `completed` la mot dong. Tren production da co mot
      chuong voi NAM job hoan tat cung fingerprint (nguoi dung bam nut nhieu
      lan trong 2 giay), va thu vien hien nam dong trong y het nhau — khong
      cach nao biet chung khac nhau o dau, vi chung KHONG khac nhau: ca nam
      tro ve cung mot object R2 va cung mot AudioTrack.

      Loi goc da duoc sua o backend (`create_job_once`). Nhung du lieu cu van
      con, va nguoi dung khong co loi gi de phai nhin nam dong do — nen o day
      chi giu ban moi nhat cua moi chuong.

      Doi giong hay sua noi dung roi tao lai cung roi vao day: nguoi dung thay
      ban MOI NHAT, dung thu ho vua tao. Lich su phien ban audio la mot tinh
      nang rieng, chua lam; khi lam thi no phai co giao dien noi ro tung ban
      khac nhau o dau, chu khong phai nhung dong trung nhau.
    */
    const moi_nhat = new Map<string, (typeof jobList.jobs)[number]>();
    for (const job of jobList.jobs) {
      if (job.status !== "completed") continue;
      const dang_co = moi_nhat.get(job.chapter_id);
      if (!dang_co || job.created_at > dang_co.created_at) {
        moi_nhat.set(job.chapter_id, job);
      }
    }

    return [...moi_nhat.values()]
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
      // Themed Page Hero — "Arcane Archive": navy hoang gia + ngoc bich dam
      // + vang co dien. Dung PageHeader (khong con <h1> tran) de nhat quan
      // voi nhanh da dang nhap ben duoi — cung mot he thong.
      <div className="page" data-hero-theme="library">
        <PageHeader eyebrow="Thư viện" icon={<IconLibrary />} motif={<MotifCelestialDial />} title="Thư viện audio" />
        <EmptyState
          icon="🔐"
          title="Cần đăng nhập để xem thư viện của bạn"
          hint="Thư viện chỉ chứa audio do chính bạn tạo."
          action={
            <Link className="btn btn-primary" href="/login" prefetch={false}>
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="page" data-hero-theme="library">
      <PageHeader
        eyebrow="Thư viện"
        icon={<IconLibrary />}
        motif={<MotifCelestialDial />}
        title="Audio của tôi"
        lead="Tất cả audio đã tạo, gồm cả bản tạo nhanh ở Audio Studio và audio của các chương fanfic."
        action={
          <Link className="btn btn-primary" href="/studio" prefetch={false}>
            <IconMic size={17} /> Tạo audio mới
          </Link>
        }
      />

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
              <Link className="btn btn-primary" href="/studio" prefetch={false}>
                Mở Audio Studio
              </Link>
              <Link className="btn" href="/write" prefetch={false}>
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
        // `key` doi theo tab dang chon: React thay phan tu nen hieu ung truot
        // vao tu chay lai. Danh sach van hien NGAY, khong cho hieu ung xong.
        <div className="stack doi-tab" key={source}>
          {/* `hang-muc`: dau vien vang + nhan + duong ngan. Thu vien thuong chi
              co vai ban audio, va mot dong chu tro troi giua trang doc ra nhu
              trang chua tai xong. Van la con so that — chi trinh bay co chu y. */}
          <p className="hint hang-muc" role="status">
            {shown.length} bản audio
          </p>
          {shown.map((row) => {
            const dangNghe = playing === row.chapter.chapter_id;
            return (
              <article
                key={row.job.job_id}
                className={`audio-row${dangNghe ? " audio-row-open" : ""}`}
              >
                {/* Bia kem mot dau phat mo o goc: hang nay la mot ban AUDIO,
                    khong phai mot truyen de doc. Dau nay lam ro dieu do ngay
                    truoc khi mat kip doc toi nut ben phai. */}
                <div className="audio-thumb">
                  <NovelCover
                    novelId={row.novel.novel_id}
                    title={row.fromStudio ? row.chapter.title : row.novel.title}
                    coverUrl={row.novel.cover_url}
                    size="thumb"
                  />
                  <span className="audio-thumb-mark" aria-hidden="true">
                    ▶
                  </span>
                </div>

                <div className="audio-row-body">
                  <div className="row audio-row-tags">
                    <span
                      className={`badge ${row.fromStudio ? "badge-brand" : "badge-info"}`}
                    >
                      {row.fromStudio ? "Audio Studio" : "Fanfic"}
                    </span>
                    <JobBadge status={row.job.status} />
                  </div>
                  <strong className="audio-row-title">{row.chapter.title}</strong>
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

                <div className="row audio-row-actions">
                  {!row.fromStudio ? (
                    <>
                      <Link
                        className="btn btn-sm"
                        href={`/chapters/${row.chapter.chapter_id}`}
                      >
                        Mở chương
                      </Link>
                      {/* Fanfic — dan sang trang Nghe rieng (Phan 2A), KHONG
                          con mo trinh phat ngay trong hang nay: dong nhat
                          voi trang chi tiet truyen, chi CON MOT dong-co-phat
                          toan cuc cho moi audio fanfic. */}
                      <Link
                        className="btn btn-sm btn-primary"
                        href={`/listen/${row.chapter.chapter_id}`}
                      >
                        <span aria-hidden="true">▶</span> Nghe
                      </Link>
                    </>
                  ) : (
                    // Audio Studio — ban tao nhanh, KHONG gan voi mot "truyen"
                    // de doc/nghe theo tap, nen giu trinh phat rieng tai cho.
                    <button
                      type="button"
                      className={`btn btn-sm ${dangNghe ? "" : "btn-primary"}`}
                      aria-expanded={dangNghe}
                      onClick={() =>
                        setPlaying(dangNghe ? "" : row.chapter.chapter_id)
                      }
                    >
                      <span aria-hidden="true">{dangNghe ? "✕" : "▶"}</span>
                      {dangNghe ? "Đóng" : "Nghe"}
                    </button>
                  )}
                </div>

                {/* Trinh phat chiem tron mot hang rieng ben duoi — xem
                    `.audio-row` o `globals.css`. CHI con cho Audio Studio. */}
                {row.fromStudio && dangNghe ? (
                  <div className="audio-row-player">
                    <AudioPlayer
                      chapterId={row.chapter.chapter_id}
                      title={row.chapter.title}
                    />
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
