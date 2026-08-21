"use client";

/**
 * Audio Studio — dan van ban bat ky, chon giong va toc do, tao MP3.
 *
 * Backend chi nhan `chapter_id` nen moi lan tao la mot chuong trong kho chua
 * rieng cua Studio (xem `lib/workspace.ts`). Kho do luon la ban nhap va bi loc
 * khoi khu vuc Fanfic, nen audio o day KHONG tu bien thanh chuong fanfic.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type Chapter,
  type Novel,
  type TtsJob,
  type Voice,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { dangChayJob } from "@/lib/jobs";
import { useJobTracker } from "@/lib/useJobTracker";
import {
  ALL_VOICES_LABEL,
  RECOMMENDED_LABEL,
  defaultVoiceId,
  usableVoices,
  voiceOptionLabel,
  voiceSections,
} from "@/lib/voices";
import { ensureStudioNovel } from "@/lib/workspace";
import { AudioPlayer } from "@/components/AudioPlayer";
import { JobProgress } from "@/components/JobProgress";
import {
  Alert,
  EmptyState,
  ErrorState,
  JobBadge,
  Loading,
  PageHeader,
  SkeletonList,
  formatDate,
  formatNumber,
} from "@/components/ui";
import { IconMic , IconHistory, IconBulb } from "@/components/Icons";
import { MotifResonanceRings } from "@/components/Ornaments";

/** Gioi han cua Studio — dat o day de tranh job chay qua lau. */
const MAX_CHARS = 20_000;
const WARN_AT = 0.85;

/** Van ban da gui di, de biet lan bam sau co phai CUNG mot noi dung khong. */
interface DaGui {
  title: string;
  text: string;
  chapterId: string;
}

const RATES = [
  { value: "0.8", label: "Chậm" },
  { value: "0.9", label: "Hơi chậm" },
  { value: "1.0", label: "Bình thường" },
  { value: "1.15", label: "Hơi nhanh" },
  { value: "1.3", label: "Nhanh" },
];

interface HistoryItem {
  job: TtsJob;
  chapter: Chapter | undefined;
}

export default function StudioPage() {
  const { profile, loading: sessionLoading } = useSession();
  const toast = useToast();

  const [workspace, setWorkspace] = useState<Novel | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState("");

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [rate, setRate] = useState("1.0");

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [activeChapterId, setActiveChapterId] = useState("");
  const [daGui, setDaGui] = useState<DaGui | null>(null);

  /*
    CUNG mot vong theo doi voi `/write` — xem `lib/useJobTracker.ts`.

    Truoc day trang nay tu viet lay: chi theo doi DUNG MOT job, va ve tien do
    bang `percent={activeJob.progress || 8}` — mot con so 8% khong den tu dau
    ca. Cac ban va cua `/write` khong bao gio toi day duoc vi khong co gi dung
    chung de sua mot lan.
  */
  const { jobs, khoiPhuc: khoiPhucJob, theoDoi: theoDoiJob } = useJobTracker({
    onCompleted: () => toast.ok("Audio đã sẵn sàng."),
    onFailed: () => toast.error("Tạo audio thất bại. Xem chi tiết bên dưới."),
  });
  const activeJob = activeChapterId ? (jobs[activeChapterId] ?? null) : null;

  /* ---------------------------------------------------------- nap du lieu */

  const bootstrap = useCallback(async () => {
    const novel = await ensureStudioNovel();
    const [detail, voiceList, jobList] = await Promise.all([
      api.getNovel(novel.novel_id),
      api.voices(),
      api.listJobs(),
    ]);
    return { novel, detail, voiceList, jobList };
  }, []);

  // Than effect KHONG duoc goi setState dong bo (react-hooks/set-state-in-effect):
  // moi setState o day deu nam trong callback cua promise.
  const load = useCallback(() => {
    bootstrap()
      .then(({ novel, detail, voiceList, jobList }) => {
        setWorkspace(novel);
        setChapters(detail.chapters);
        setVoices(voiceList.voices);
        setVoiceId((current) => current || defaultVoiceId(voiceList.voices));
        /*
          KHOI PHUC SAU F5 — va sau ca khi nguoi dung roi trang roi quay lai.

          KHO MOI LA NGUON SU THAT: `listJobs()` la mot request cho TAT CA job,
          khong doc `job_id` tu localStorage. Job dang chay tu mot phien truoc
          duoc nap thang vao vong theo doi, nen tien do chay tiep va khi xong
          thi tu cap nhat — khong can F5 lan nua.
        */
        khoiPhucJob(jobList.jobs);
        const dangChay = jobList.jobs.filter(dangChayJob);
        if (dangChay.length > 0) {
          // Cai chay lau nhat truoc: no gan xong nhat.
          const som_nhat = dangChay.reduce((a, b) =>
            a.created_at <= b.created_at ? a : b,
          );
          setActiveChapterId((current) => current || som_nhat.chapter_id);
        }
      })
      .catch((cause) => setBootError(errorMessage(cause)))
      .finally(() => setBooting(false));
  }, [bootstrap, khoiPhucJob]);

  /** Nut "Thu lai" — chay tu su kien nguoi dung nen dat trang thai truc tiep duoc. */
  const retryBoot = useCallback(() => {
    setBooting(true);
    setBootError("");
    load();
  }, [load]);

  useEffect(() => {
    if (sessionLoading || !profile) return;
    load();
  }, [sessionLoading, profile, load]);

  /* ------------------------------------------------------------- dan xuat */

  const availableVoices = useMemo(() => usableVoices(voices), [voices]);
  // Hai muc, cung mot bo ban ghi. Xem `voiceSections`.
  const voiceGroups = useMemo(() => voiceSections(voices), [voices]);

  const chapterById = useMemo(() => {
    const map = new Map<string, Chapter>();
    chapters.forEach((c) => map.set(c.chapter_id, c));
    return map;
  }, [chapters]);

  /*
    Lich su lay thang tu vong theo doi, nen no tu cap nhat o moi nhip poll:
    khung "Tien trinh" va the trong "Lich su audio" khong con noi hai dieu khac
    nhau ve cung mot job, va khi job xong thi ca hai doi cung luc — khong can F5.

    Mot dong moi CHUONG, khong phai moi job: bam "Thu lai" tao job moi cho cung
    chuong do, va hai dong cho cung mot doan van la thu nguoi dung khong hieu.
  */
  const history = useMemo<HistoryItem[]>(() => {
    const own = new Set(chapters.map((c) => c.chapter_id));
    return Object.values(jobs)
      .filter((job) => own.has(job.chapter_id))
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
      .map((job) => ({ job, chapter: chapterById.get(job.chapter_id) }));
  }, [jobs, chapters, chapterById]);

  const chars = text.length;
  const over = chars > MAX_CHARS;
  const nearLimit = chars > MAX_CHARS * WARN_AT;

  /*
    CHONG TAO TRUNG.

    Moi lan bam la Studio tao mot CHUONG moi, nen khoa van tay o backend
    (`job_locks`, theo `owner + chapter + content_hash`) khong the nhan ra hai
    lan bam la cung mot noi dung: chuong khac nhau thi van tay khac nhau. Bam
    hai lan la ra hai chuong va hai job that.

    Nen o day phai nho lai chuong da tao cho DUNG noi dung nay. Bam lai ma
    chua sua gi thi dung lai chuong cu, va luc do backend moi nhin thay cung
    mot van tay va tra ve chinh job dang chay. Backend van la trong tai cuoi.
  */
  const khongDoi =
    daGui !== null && daGui.title === title.trim() && daGui.text === text;
  const dangChoJobNay = Boolean(activeJob && dangChayJob(activeJob) && khongDoi);

  const canSubmit =
    !submitting &&
    !dangChoJobNay &&
    chars > 0 &&
    !over &&
    Boolean(voiceId) &&
    Boolean(workspace);

  /* --------------------------------------------------------------- hanh vi */

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!workspace || !canSubmit) return;
      setSubmitting(true);
      setFormError("");
      try {
        const ten = title.trim();
        /*
          Noi dung khong doi thi DUNG LAI chuong cu thay vi tao chuong moi —
          day la thu cho phep khoa van tay o backend nhan ra hai lan bam la mot.
          Doi mot chu thoi la sang chuong moi, va do la dung: audio khac thi
          ban ghi khac.
        */
        let chapterId = khongDoi ? daGui.chapterId : "";
        if (!chapterId) {
          const name =
            ten || `${text.trim().slice(0, 40)}${text.trim().length > 40 ? "…" : ""}`;
          const created = await api.createChapter(
            workspace.novel_id,
            name,
            text,
            chapters.length + 1,
          );
          chapterId = created.chapter.chapter_id;
          setChapters((current) => [...current, created.chapter]);
        }
        const result = await api.createJob(chapterId, voiceId, rate);
        setDaGui({ title: ten, text, chapterId });
        setActiveChapterId(chapterId);
        theoDoiJob(result.job);
        toast.push(
          "info",
          result.reused ? "Dùng lại audio đã tạo." : "Đã đưa vào hàng đợi.",
        );
      } catch (cause) {
        setFormError(errorMessage(cause));
        toast.error("Không tạo được audio.");
      } finally {
        setSubmitting(false);
      }
    },
    [
      workspace,
      canSubmit,
      khongDoi,
      daGui,
      title,
      text,
      chapters.length,
      voiceId,
      rate,
      theoDoiJob,
      toast,
    ],
  );

  const retry = useCallback(
    async (job: TtsJob) => {
      try {
        const result = await api.createJob(job.chapter_id, job.voice_id, job.rate);
        setActiveChapterId(job.chapter_id);
        theoDoiJob(result.job);
        toast.push("info", "Đang thử lại…");
      } catch (cause) {
        toast.error(errorMessage(cause));
      }
    },
    [theoDoiJob, toast],
  );

  const reset = useCallback(() => {
    setActiveChapterId("");
    setDaGui(null);
    setTitle("");
    setText("");
  }, []);

  /* --------------------------------------------------------------- render */

  if (sessionLoading) {
    return (
      <div className="page">
        <Loading label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="page" data-hero-theme="audio">
        <PageHeader eyebrow="Audio Studio" icon={<IconMic />} motif={<MotifResonanceRings />} title="Audio Studio" />
        <EmptyState
          icon="🔐"
          title="Cần đăng nhập để tạo audio"
          hint="Audio bạn tạo là riêng tư và gắn với tài khoản của bạn."
          action={
            <Link className="btn btn-primary" href="/login">
              Đăng nhập hoặc tạo tài khoản
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="page" data-hero-theme="audio">
      <PageHeader
        eyebrow="Audio Studio"
        icon={<IconMic />}
        motif={<MotifResonanceRings />}
        title="Tạo audio từ văn bản"
        lead="Dán đoạn văn bất kỳ, chọn giọng đọc và tốc độ. Audio tạo ở đây là riêng tư và không trở thành chương fanfic."
        action={
          <Link className="btn" href="/library">
            Thư viện audio của tôi
          </Link>
        }
      />

      {bootError ? (
        <ErrorState message={bootError} onRetry={retryBoot} />
      ) : (
        <div className="split page-lam-viec">
          {/* ------------------------------------------------ cot chinh */}
          <section className="stack-5">
            <form className="card stack" onSubmit={submit}>
              <div className="field">
                <label className="label" htmlFor="studio-title">
                  Tên audio <span className="hint">(để trống sẽ tự đặt)</span>
                </label>
                <input
                  id="studio-title"
                  className="input"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Ví dụ: Chương mở đầu"
                  maxLength={200}
                />
              </div>

              <div className="field">
                <div className="label-row">
                  <label className="label" htmlFor="studio-text">
                    Nội dung cần đọc
                  </label>
                  <span
                    className={`counter${over ? " counter-over" : nearLimit ? " counter-warn" : ""}`}
                    role="status"
                  >
                    {formatNumber(chars)} / {formatNumber(MAX_CHARS)} ký tự
                  </span>
                </div>
                <textarea
                  id="studio-text"
                  className="textarea textarea-tall"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Dán hoặc gõ văn bản tiếng Việt vào đây…"
                  aria-describedby="studio-text-hint"
                  aria-invalid={over}
                />
                <p className="hint" id="studio-text-hint">
                  {over
                    ? `Vượt quá ${formatNumber(MAX_CHARS)} ký tự. Hãy cắt bớt hoặc chia thành nhiều phần.`
                    : "Văn bản dài hơn sẽ mất nhiều thời gian xử lý hơn."}
                </p>
              </div>

              <div className="grid-2">
                <div className="field">
                  <label className="label" htmlFor="studio-voice">
                    Giọng đọc
                  </label>
                  {booting ? (
                    <div className="sk" style={{ height: 42 }} aria-hidden="true" />
                  ) : availableVoices.length === 0 ? (
                    // Nguoi dung KHONG sua duoc cau hinh may chu, nen bao ho di
                    // "kiem tra lai cau hinh backend" la mot loi khuyen vo dung.
                    // Noi dieu ho lam duoc: thu lai, va bao neu van vay.
                    <Alert kind="warn">
                      Hiện chưa có giọng đọc nào sẵn sàng. Hãy tải lại trang sau
                      ít phút; nếu vẫn vậy thì máy chủ giọng đọc đang bảo trì.
                    </Alert>
                  ) : (
                    <select
                      id="studio-voice"
                      className="select"
                      value={voiceId}
                      onChange={(e) => setVoiceId(e.target.value)}
                    >
                      {/*
                        Hai mục, MỘT `<select>`. Bảy giọng đề xuất xuất hiện
                        lại trong "Tất cả giọng tiếng Việt" — đó là chủ ý: hai
                        cách trình bày cùng một bộ bản ghi, không nhân bản
                        voice nào. Vì cùng một `value`, chọn ở mục này đồng bộ
                        ngay với mục kia mà không cần trạng thái thứ hai.

                        Đã từng có mục thứ ba dành riêng cho NghiTTS; bỏ đi
                        theo yêu cầu sản phẩm. Giọng NghiTTS nằm trong "Tất cả
                        giọng tiếng Việt" như mọi provider khác.
                      */}
                      <optgroup label={RECOMMENDED_LABEL}>
                        {voiceGroups.recommended.map((voice) => (
                          <option
                            key={`goi-y-${voice.voice_id}`}
                            value={voice.voice_id}
                          >
                            {voiceOptionLabel(voice)}
                          </option>
                        ))}
                      </optgroup>
                      <optgroup label={ALL_VOICES_LABEL}>
                        {voiceGroups.all.map((voice) => (
                          <option key={voice.voice_id} value={voice.voice_id}>
                            {voiceOptionLabel(voice)}
                          </option>
                        ))}
                      </optgroup>
                    </select>
                  )}
                </div>

                <div className="field">
                  <span className="label" id="studio-rate-label">
                    Tốc độ đọc
                  </span>
                  <div
                    className="seg seg-wrap"
                    role="group"
                    aria-labelledby="studio-rate-label"
                                      >
                    {RATES.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        className="seg-item"
                        aria-pressed={rate === option.value}
                        onClick={() => setRate(option.value)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {formError ? <Alert kind="error">{formError}</Alert> : null}

              <div className="row">
                <button
                  type="submit"
                  className="btn btn-primary btn-lg"
                  disabled={!canSubmit}
                >
                  {submitting || dangChoJobNay ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : null}
                  {dangChoJobNay ? "Đang tạo audio…" : "Tạo audio"}
                </button>
                {text ? (
                  <button type="button" className="btn btn-ghost" onClick={reset}>
                    Xoá nội dung
                  </button>
                ) : null}
              </div>
            </form>

            {/* trang thai job dang chay */}
            {activeJob ? (
              // KHONG boc them mot `.card` nua: `<JobProgress>` da la mot khung
              // co vien roi, va the long the trong nhu mot loi bo cuc.
              <section className="stack-2" aria-labelledby="studio-tien-trinh">
                <h2 className="section-title" id="studio-tien-trinh">
                  Tiến trình
                </h2>

                {/*
                  CUNG mot khung tien do voi `/write` — xem
                  `components/JobProgress.tsx`. Truoc day cho nay tu ve lay: mot
                  thanh vo dinh voi 6% hoac 8% bia ra, va khong bao gio hien
                  phan tram that du backend da bao du `done_parts`/`total_parts`.
                */}
                <JobProgress
                  job={activeJob}
                  tieuDe="Tiến trình tạo audio"
                  ghiChu={
                    <>
                      {activeJob.status === "pending" ? (
                        /*
                          Giọng NghiTTS tổng hợp trên máy chủ riêng, và máy đó
                          xử lý MỘT job tại một thời điểm (khoá `_PIPER_LOCK` ở
                          cấp job — xem `docs/GCE-WORKER-CAPACITY.md`). Nên chờ
                          là chuyện bình thường chứ không phải hỏng, và một
                          thanh tiến trình quay mãi mà không giải thích thì
                          người dùng chỉ biết là hỏng.

                          KHÔNG hứa thời gian: máy chủ có thể quá tải hoặc chết
                          thật, và job dài thì hàng đợi dài theo.
                        */
                        <p className="hint">
                          {activeJob.voice_id.startsWith("piper:")
                            ? "Đã nhận yêu cầu và đang xếp hàng chờ máy chủ tạo giọng. Máy chủ xử lý lần lượt từng bản nên có thể phải chờ; bản của bạn vẫn được giữ nguyên và không bị đổi sang giọng khác. Bạn có thể đóng trang này."
                            : "Đã nhận yêu cầu, đang chờ tới lượt xử lý."}
                        </p>
                      ) : null}

                      {activeJob.status === "completed" && activeChapterId ? (
                        <>
                          <AudioPlayer
                            chapterId={activeChapterId}
                            title={chapterById.get(activeChapterId)?.title ?? "Audio"}
                          />
                          <div className="row">
                            <button type="button" className="btn" onClick={reset}>
                              Tạo audio khác
                            </button>
                          </div>
                        </>
                      ) : null}

                      {activeJob.status === "failed" ? (
                        <>
                          <Alert kind="error">
                            {activeJob.error_message || "Không rõ nguyên nhân."}
                            {activeJob.error_kind ? (
                              <span className="hint">
                                {" "}
                                (mã: {activeJob.error_kind})
                              </span>
                            ) : null}
                          </Alert>
                          <p className="hint">
                            Hệ thống không tự đổi sang giọng khác. Bạn có thể thử
                            lại với cùng giọng, hoặc chọn giọng khác rồi tạo lại.
                          </p>
                          <div className="row">
                            <button
                              type="button"
                              className="btn btn-primary"
                              onClick={() => retry(activeJob)}
                            >
                              Thử lại
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={reset}
                            >
                              Bỏ qua
                            </button>
                          </div>
                        </>
                      ) : null}
                    </>
                  }
                />
              </section>
            ) : null}
          </section>

          {/* ------------------------------------------------ cot phu */}
          <aside className="stack sticky-side">
            <section className="card stack">
              <h2 className="section-title section-title-icon">
                <IconHistory size={20} /> Lịch sử audio
              </h2>
              {booting ? (
                <SkeletonList count={3} />
              ) : history.length === 0 ? (
                <p className="hint">
                  Chưa có audio nào. Audio bạn tạo sẽ hiện ở đây.
                </p>
              ) : (
                <div className="list">
                  {history.slice(0, 8).map(({ job, chapter }) => (
                    <div
                      key={job.job_id}
                      className={`hist-item${
                        job.chapter_id === activeChapterId ? " hist-item-on" : ""
                      }`}
                    >
                      <strong className="truncate hist-title">
                        {chapter?.title ?? "Audio"}
                      </strong>
                      <span className="hint">{formatDate(job.created_at)}</span>
                      <div className="row hist-actions">
                        <JobBadge status={job.status} />
                        {job.status === "completed" ? (
                          <button
                            type="button"
                            className="btn btn-sm btn-ghost"
                            // `activeJob` duoc suy ra tu `activeChapterId`,
                            // nen chi can tro toi chuong la du.
                            onClick={() => setActiveChapterId(job.chapter_id)}
                          >
                            Nghe lại
                          </button>
                        ) : null}
                        {job.status === "failed" ? (
                          <button
                            type="button"
                            className="btn btn-sm"
                            onClick={() => retry(job)}
                          >
                            Thử lại
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {history.length > 8 ? (
                <Link className="btn btn-block" href="/library">
                  Xem tất cả ({history.length})
                </Link>
              ) : null}
            </section>

            <section className="card stack-2">
              <h2 className="section-title section-title-icon">
                <IconBulb size={20} /> Mẹo
              </h2>
              <p className="hint">
                Văn bản có dấu câu rõ ràng sẽ cho giọng đọc tự nhiên hơn.
              </p>
              <p className="hint">
                Cùng một nội dung, cùng giọng và cùng tốc độ sẽ dùng lại audio
                đã tạo trước đó thay vì tạo mới.
              </p>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
