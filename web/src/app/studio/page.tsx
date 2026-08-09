"use client";

/**
 * Audio Studio — dan van ban bat ky, chon giong va toc do, tao MP3.
 *
 * Backend chi nhan `chapter_id` nen moi lan tao la mot chuong trong kho chua
 * rieng cua Studio (xem `lib/workspace.ts`). Kho do luon la ban nhap va bi loc
 * khoi khu vuc Fanfic, nen audio o day KHONG tu bien thanh chuong fanfic.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Chapter,
  type Novel,
  type TtsJob,
  type Voice,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
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
import {
  Alert,
  EmptyState,
  ErrorState,
  JobBadge,
  Loading,
  ProgressBar,
  SkeletonList,
  formatDate,
  formatNumber,
} from "@/components/ui";

/** Gioi han cua Studio — dat o day de tranh job chay qua lau. */
const MAX_CHARS = 20_000;
const WARN_AT = 0.85;
const POLL_MS = 1500;

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
  const [jobs, setJobs] = useState<TtsJob[]>([]);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState("");

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [rate, setRate] = useState("1.0");

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [activeJob, setActiveJob] = useState<TtsJob | null>(null);
  const [activeChapterId, setActiveChapterId] = useState("");

  const pollTimer = useRef<number | null>(null);

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
        setJobs(jobList.jobs);
        setVoiceId((current) => current || defaultVoiceId(voiceList.voices));
        // Job con dang chay tu MOT PHIEN TRANG TRUOC. Khong nap lai no vao
        // `activeJob` thi vong poll o duoi thoat ngay (`if (!activeJob) return`),
        // va the trong "Lich su audio" se dung im o "Dang xu ly" mai mai — job
        // da xong tu lau ma nguoi dung phai tu tai lai trang moi thay.
        const dangChay = jobList.jobs.find(
          (j) => j.status === "pending" || j.status === "running",
        );
        if (dangChay) {
          setActiveJob((current) => current ?? dangChay);
          setActiveChapterId((current) => current || dangChay.chapter_id);
        }
      })
      .catch((cause) => setBootError(errorMessage(cause)))
      .finally(() => setBooting(false));
  }, [bootstrap]);

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

  /* ------------------------------------------------------------- theo doi */

  useEffect(() => {
    if (!activeJob || activeJob.status === "completed" || activeJob.status === "failed") {
      return;
    }
    const id = window.setTimeout(() => {
      api
        .getJob(activeJob.job_id)
        .then((r) => {
          setActiveJob(r.job);
          // Dong bo lich su o MOI vong poll, khong chi khi job ket thuc.
          // Truoc day khung "Tien trinh" da hien "Dang xu ly" ma the trong
          // "Lich su audio" van con "Dang xep hang" — hai cho noi hai dieu khac
          // nhau ve cung mot job.
          setJobs((current) => [
            r.job,
            ...current.filter((j) => j.job_id !== r.job.job_id),
          ]);
          // Toast thi CHI o trang thai ket thuc, neu khong se keu moi vong poll
          if (r.job.status === "completed") toast.ok("Audio đã sẵn sàng.");
          else if (r.job.status === "failed") {
            toast.error("Tạo audio thất bại. Xem chi tiết bên dưới.");
          }
        })
        .catch(() => {
          /* mang chap chon — vong sau thu lai */
        });
    }, POLL_MS);
    pollTimer.current = id;
    return () => window.clearTimeout(id);
  }, [activeJob, toast]);

  /* ------------------------------------------------------------- dan xuat */

  const availableVoices = useMemo(() => usableVoices(voices), [voices]);
  // Hai muc, cung mot bo ban ghi. Xem `voiceSections`.
  const voiceGroups = useMemo(() => voiceSections(voices), [voices]);

  const chapterById = useMemo(() => {
    const map = new Map<string, Chapter>();
    chapters.forEach((c) => map.set(c.chapter_id, c));
    return map;
  }, [chapters]);

  const history = useMemo<HistoryItem[]>(() => {
    const own = new Set(chapters.map((c) => c.chapter_id));
    return jobs
      .filter((job) => own.has(job.chapter_id))
      .map((job) => ({ job, chapter: chapterById.get(job.chapter_id) }));
  }, [jobs, chapters, chapterById]);

  const chars = text.length;
  const over = chars > MAX_CHARS;
  const nearLimit = chars > MAX_CHARS * WARN_AT;
  const canSubmit =
    !submitting && chars > 0 && !over && Boolean(voiceId) && Boolean(workspace);

  /* --------------------------------------------------------------- hanh vi */

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!workspace || !canSubmit) return;
      setSubmitting(true);
      setFormError("");
      try {
        const name =
          title.trim() ||
          `${text.trim().slice(0, 40)}${text.trim().length > 40 ? "…" : ""}`;
        const created = await api.createChapter(
          workspace.novel_id,
          name,
          text,
          chapters.length + 1,
        );
        const result = await api.createJob(
          created.chapter.chapter_id,
          voiceId,
          rate,
        );
        setChapters((current) => [...current, created.chapter]);
        setActiveChapterId(created.chapter.chapter_id);
        setActiveJob(result.job);
        setJobs((current) => [result.job, ...current]);
        toast.push("info", "Đã đưa vào hàng đợi.");
      } catch (cause) {
        setFormError(errorMessage(cause));
        toast.error("Không tạo được audio.");
      } finally {
        setSubmitting(false);
      }
    },
    [workspace, canSubmit, title, text, chapters.length, voiceId, rate, toast],
  );

  const retry = useCallback(
    async (job: TtsJob) => {
      try {
        const result = await api.createJob(job.chapter_id, job.voice_id, job.rate);
        setActiveChapterId(job.chapter_id);
        setActiveJob(result.job);
        setJobs((current) => [result.job, ...current]);
        toast.push("info", "Đang thử lại…");
      } catch (cause) {
        toast.error(errorMessage(cause));
      }
    },
    [toast],
  );

  const reset = useCallback(() => {
    setActiveJob(null);
    setActiveChapterId("");
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
      <div className="page">
        <h1 className="page-title">Audio Studio</h1>
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
    <div className="page">
      <header className="row-between">
        <div className="stack-2">
          <span className="eyebrow">Audio Studio</span>
          <h1 className="page-title">Tạo audio từ văn bản</h1>
          <p className="lead" style={{ maxWidth: 620 }}>
            Dán đoạn văn bất kỳ, chọn giọng đọc và tốc độ. Audio tạo ở đây là
            riêng tư và không trở thành chương fanfic.
          </p>
        </div>
        <Link className="btn" href="/library">
          Thư viện audio của tôi
        </Link>
      </header>

      {bootError ? (
        <ErrorState message={bootError} onRetry={retryBoot} />
      ) : (
        <div className="split">
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
                    <Alert kind="warn">
                      Chưa có giọng đọc nào sẵn sàng. Kiểm tra lại cấu hình
                      backend rồi tải lại trang.
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
                    className="seg"
                    role="group"
                    aria-labelledby="studio-rate-label"
                    style={{ flexWrap: "wrap" }}
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
                  {submitting ? <span className="spinner" aria-hidden="true" /> : null}
                  Tạo audio
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
              <section className="card stack" aria-live="polite">
                <div className="row-between">
                  <h2 className="section-title">Tiến trình</h2>
                  <JobBadge status={activeJob.status} />
                </div>

                {activeJob.status === "pending" ? (
                  <>
                    <ProgressBar percent={6} indeterminate label="Đang xếp hàng" />
                    {/*
                      Giọng NghiTTS tổng hợp trên máy chủ riêng, và máy đó xử
                      lý MỘT job tại một thời điểm (khoá `_PIPER_LOCK` ở cấp
                      job — xem `docs/GCE-WORKER-CAPACITY.md`). Nên chờ là
                      chuyện bình thường chứ không phải hỏng, và một thanh tiến
                      trình quay mãi mà không giải thích thì người dùng chỉ
                      biết là hỏng.

                      Câu cũ nói giọng này xử lý trên máy cá nhân và có thể
                      đang không bật. Đúng khi worker còn chạy trên laptop chủ
                      dự án; production chạy 24/7 trên Google Compute Engine
                      nên nó không còn đúng. Vẫn KHÔNG hứa thời gian: máy chủ
                      có thể quá tải hoặc chết thật, và job dài thì hàng đợi
                      dài theo.
                    */}
                    <p className="hint">
                      {activeJob.voice_id.startsWith("piper:")
                        ? "Job đã nhận và đang xếp hàng chờ máy chủ tạo giọng. Máy chủ xử lý lần lượt từng job nên có thể phải chờ; job vẫn được giữ nguyên và không bị đổi sang giọng khác. Bạn có thể đóng trang này."
                        : "Job đã nhận, đang chờ tới lượt xử lý."}
                    </p>
                  </>
                ) : null}

                {activeJob.status === "running" ? (
                  <>
                    <ProgressBar
                      percent={activeJob.progress || 8}
                      indeterminate={!activeJob.total_parts}
                      label="Đang tổng hợp giọng đọc"
                    />
                    <p className="hint">
                      {activeJob.total_parts
                        ? `Đã xong ${activeJob.done_parts}/${activeJob.total_parts} đoạn`
                        : "Đang chuẩn bị…"}
                    </p>
                  </>
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
                        <span className="hint"> (mã: {activeJob.error_kind})</span>
                      ) : null}
                    </Alert>
                    <p className="hint">
                      Hệ thống không tự đổi sang giọng khác. Bạn có thể thử lại
                      với cùng giọng, hoặc chọn giọng khác rồi tạo lại.
                    </p>
                    <div className="row">
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => retry(activeJob)}
                      >
                        Thử lại
                      </button>
                      <button type="button" className="btn btn-ghost" onClick={reset}>
                        Bỏ qua
                      </button>
                    </div>
                  </>
                ) : null}
              </section>
            ) : null}
          </section>

          {/* ------------------------------------------------ cot phu */}
          <aside className="stack sticky-side">
            <section className="card stack">
              <h2 className="section-title">Lịch sử audio</h2>
              {booting ? (
                <SkeletonList count={3} />
              ) : history.length === 0 ? (
                <p className="hint">
                  Chưa có audio nào. Audio bạn tạo sẽ hiện ở đây.
                </p>
              ) : (
                <div className="list">
                  {history.slice(0, 8).map(({ job, chapter }) => (
                    <div key={job.job_id} className="list-item" style={{ alignItems: "flex-start" }}>
                      <div className="stack-2" style={{ flex: 1, minWidth: 0 }}>
                        <strong className="truncate" style={{ fontSize: "var(--t-sm)" }}>
                          {chapter?.title ?? "Audio"}
                        </strong>
                        <span className="hint">{formatDate(job.created_at)}</span>
                        <div className="row" style={{ gap: "var(--s2)" }}>
                          <JobBadge status={job.status} />
                          {job.status === "completed" ? (
                            <button
                              type="button"
                              className="btn btn-sm btn-ghost"
                              onClick={() => {
                                setActiveChapterId(job.chapter_id);
                                setActiveJob(job);
                              }}
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
              <h2 className="section-title">Mẹo</h2>
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
