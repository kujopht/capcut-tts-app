"use client";

/**
 * Khu vuc tac gia: tao truyen, viet chuong, tao audio cho chuong, xuat ban.
 *
 * Kho chua cua Audio Studio bi loc ra o day — audio tao nhanh khong phai
 * truyen fanfic.
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
import { defaultVoiceId, usableVoices } from "@/lib/voices";
import { fanficOnly } from "@/lib/workspace";
import { AudioPlayer } from "@/components/AudioPlayer";
import {
  Alert,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  JobBadge,
  Loading,
  ProgressBar,
  SkeletonList,
  formatNumber,
} from "@/components/ui";

const POLL_MS = 1500;

export default function WritePage() {
  const { profile, loading: sessionLoading } = useSession();
  const toast = useToast();

  const [novels, setNovels] = useState<Novel[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [audioByChapter, setAudioByChapter] = useState<Record<string, boolean>>({});
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [novelTitle, setNovelTitle] = useState("");
  const [novelDesc, setNovelDesc] = useState("");
  const [novelTags, setNovelTags] = useState("");
  const [creatingNovel, setCreatingNovel] = useState(false);

  const [chapterTitle, setChapterTitle] = useState("");
  const [chapterText, setChapterText] = useState("");
  const [creatingChapter, setCreatingChapter] = useState(false);

  const [voiceId, setVoiceId] = useState("");
  const [job, setJob] = useState<TtsJob | null>(null);
  const [jobChapterId, setJobChapterId] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);

  /* ---------------------------------------------------------------- nap */

  // Than effect KHONG duoc goi setState dong bo — xem `load` cua Audio Studio.
  const load = useCallback(() => {
    Promise.all([api.listNovels(true), api.voices()])
      .then(([novelList, voiceList]) => {
        const mine = fanficOnly(novelList.novels);
        setNovels(mine);
        setVoices(voiceList.voices);
        setVoiceId((current) => current || defaultVoiceId(voiceList.voices));
        setSelectedId((current) => current || mine[0]?.novel_id || "");
      })
      .catch((cause) => setError(errorMessage(cause)))
      .finally(() => setLoading(false));
  }, []);

  /** Nut "Thu lai" chay tu su kien nguoi dung. */
  const retryLoad = useCallback(() => {
    setLoading(true);
    setError("");
    load();
  }, [load]);

  useEffect(() => {
    if (sessionLoading || !profile) return;
    load();
  }, [sessionLoading, profile, load]);

  const loadChapters = useCallback((novelId: string) => {
    if (!novelId) return;
    api
      .getNovel(novelId)
      .then(async (detail) => {
        setChapters(detail.chapters);
        const flags = await Promise.all(
          detail.chapters.map((chapter) =>
            api
              .getChapter(chapter.chapter_id)
              .then((r) => [chapter.chapter_id, r.audio !== null] as const)
              .catch(() => [chapter.chapter_id, false] as const),
          ),
        );
        setAudioByChapter(Object.fromEntries(flags));
      })
      .catch(() => {
        setChapters([]);
        setAudioByChapter({});
      });
  }, []);

  useEffect(() => {
    loadChapters(selectedId);
  }, [selectedId, loadChapters]);

  /* ------------------------------------------------------------ theo doi */

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const id = window.setTimeout(() => {
      api
        .getJob(job.job_id)
        .then((r) => {
          setJob(r.job);
          if (r.job.status === "completed") {
            toast.ok("Audio của chương đã sẵn sàng.");
            setAudioByChapter((current) => ({ ...current, [r.job.chapter_id]: true }));
          } else if (r.job.status === "failed") {
            toast.error("Tạo audio thất bại.");
          }
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearTimeout(id);
  }, [job, toast]);

  /* ---------------------------------------------------------------- suy */

  const selected = useMemo(
    () => novels.find((n) => n.novel_id === selectedId) ?? null,
    [novels, selectedId],
  );
  const availableVoices = useMemo(() => usableVoices(voices), [voices]);
  const published = selected?.state === "published";

  /* ------------------------------------------------------------- hanh vi */

  const createNovel = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!novelTitle.trim()) return;
      setCreatingNovel(true);
      try {
        const tags = novelTags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
          .slice(0, 6);
        const created = await api.createNovel(novelTitle.trim(), novelDesc.trim(), tags);
        setNovels((current) => [created.novel, ...current]);
        setSelectedId(created.novel.novel_id);
        setNovelTitle("");
        setNovelDesc("");
        setNovelTags("");
        toast.ok("Đã tạo truyện mới.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setCreatingNovel(false);
      }
    },
    [novelTitle, novelDesc, novelTags, toast],
  );

  const createChapter = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!selectedId || !chapterTitle.trim() || !chapterText.trim()) return;
      setCreatingChapter(true);
      try {
        const created = await api.createChapter(
          selectedId,
          chapterTitle.trim(),
          chapterText,
          chapters.length + 1,
        );
        setChapters((current) => [...current, created.chapter]);
        setChapterTitle("");
        setChapterText("");
        toast.ok("Đã thêm chương.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setCreatingChapter(false);
      }
    },
    [selectedId, chapterTitle, chapterText, chapters.length, toast],
  );

  const makeAudio = useCallback(
    async (chapterId: string) => {
      if (!voiceId) {
        toast.error("Chưa chọn giọng đọc.");
        return;
      }
      try {
        const result = await api.createJob(chapterId, voiceId);
        setJobChapterId(chapterId);
        setJob(result.job);
        toast.push("info", result.reused ? "Dùng lại audio đã tạo." : "Đang tạo audio…");
      } catch (cause) {
        toast.error(errorMessage(cause));
      }
    },
    [voiceId, toast],
  );

  const doPublish = useCallback(async () => {
    if (!selected) return;
    setPublishing(true);
    try {
      const result = await api.publishNovel(selected.novel_id);
      setNovels((current) =>
        current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
      );
      toast.ok("Đã xuất bản. Truyện hiện ra trong trang Khám phá.");
      setConfirmPublish(false);
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setPublishing(false);
    }
  }, [selected, toast]);

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
        <h1 className="page-title">Khu vực tác giả</h1>
        <EmptyState
          icon="🔐"
          title="Cần đăng nhập để viết truyện"
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
          <span className="eyebrow">Khu vực tác giả</span>
          <h1 className="page-title">Viết và xuất bản</h1>
        </div>
        <Link className="btn" href="/fanfic">
          Xem trang khám phá
        </Link>
      </header>

      {error ? (
        <ErrorState message={error} onRetry={retryLoad} />
      ) : loading ? (
        <SkeletonList count={4} />
      ) : (
        <div className="split-narrow">
          {/* --------------------------------------------- cot trai: truyen */}
          <aside className="stack">
            <section className="card stack">
              <h2 className="section-title">Truyện của tôi</h2>
              {novels.length === 0 ? (
                <p className="hint">Chưa có truyện nào. Tạo truyện đầu tiên bên dưới.</p>
              ) : (
                <div className="list">
                  {novels.map((novel) => (
                    <button
                      key={novel.novel_id}
                      type="button"
                      className="list-item"
                      aria-current={novel.novel_id === selectedId ? "true" : undefined}
                      style={{
                        textAlign: "left",
                        cursor: "pointer",
                        borderColor:
                          novel.novel_id === selectedId ? "var(--brand-line)" : undefined,
                        background:
                          novel.novel_id === selectedId ? "var(--brand-soft)" : undefined,
                      }}
                      onClick={() => setSelectedId(novel.novel_id)}
                    >
                      <span className="stack-2" style={{ flex: 1, minWidth: 0 }}>
                        <strong className="truncate" style={{ fontSize: "var(--t-sm)" }}>
                          {novel.title}
                        </strong>
                        <span
                          className={`badge ${novel.state === "published" ? "badge-ok" : ""}`}
                        >
                          {novel.state === "published" ? "Đã xuất bản" : "Bản nháp"}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <form className="card stack" onSubmit={createNovel}>
              <h2 className="section-title">Tạo truyện mới</h2>
              <div className="field">
                <label className="label" htmlFor="w-title">
                  Tiêu đề
                </label>
                <input
                  id="w-title"
                  className="input"
                  value={novelTitle}
                  onChange={(e) => setNovelTitle(e.target.value)}
                  maxLength={200}
                  required
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="w-desc">
                  Mô tả ngắn
                </label>
                <textarea
                  id="w-desc"
                  className="textarea"
                  style={{ minHeight: 90 }}
                  value={novelDesc}
                  onChange={(e) => setNovelDesc(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="w-tags">
                  Thẻ <span className="hint">(cách nhau bằng dấu phẩy)</span>
                </label>
                <input
                  id="w-tags"
                  className="input"
                  value={novelTags}
                  onChange={(e) => setNovelTags(e.target.value)}
                  placeholder="one piece, phiêu lưu"
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={creatingNovel || !novelTitle.trim()}
              >
                {creatingNovel ? <span className="spinner" aria-hidden="true" /> : null}
                Tạo truyện
              </button>
            </form>
          </aside>

          {/* -------------------------------------------- cot phai: chuong */}
          <section className="stack-5">
            {!selected ? (
              <EmptyState
                icon="✍️"
                title="Chọn hoặc tạo một truyện"
                hint="Sau khi có truyện, bạn thêm chương và tạo audio cho từng chương."
              />
            ) : (
              <>
                <section className="card stack">
                  <div className="row-between">
                    <div className="stack-2" style={{ minWidth: 0 }}>
                      <h2 className="section-title">{selected.title}</h2>
                      <span className="hint">
                        {chapters.length} chương ·{" "}
                        {published ? "đã xuất bản" : "bản nháp, chỉ mình bạn thấy"}
                      </span>
                    </div>
                    <div className="row" style={{ gap: "var(--s2)" }}>
                      <Link className="btn btn-sm" href={`/novels/${selected.novel_id}`}>
                        Xem trang truyện
                      </Link>
                      {published ? (
                        <span className="badge badge-ok">Đã xuất bản</span>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => setConfirmPublish(true)}
                          disabled={chapters.length === 0}
                        >
                          Xuất bản
                        </button>
                      )}
                    </div>
                  </div>
                  {!published && chapters.length === 0 ? (
                    <Alert kind="info">
                      Thêm ít nhất một chương trước khi xuất bản.
                    </Alert>
                  ) : null}
                </section>

                <section className="card stack">
                  <div className="row-between">
                    <h2 className="section-title">Chương</h2>
                    {availableVoices.length > 0 ? (
                      <div className="row" style={{ gap: "var(--s2)" }}>
                        <label className="hint" htmlFor="w-voice">
                          Giọng đọc
                        </label>
                        <select
                          id="w-voice"
                          className="select"
                          style={{ width: "auto", minWidth: 200 }}
                          value={voiceId}
                          onChange={(e) => setVoiceId(e.target.value)}
                        >
                          {availableVoices.map((voice) => (
                            <option key={voice.voice_id} value={voice.voice_id}>
                              {voice.display_name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ) : null}
                  </div>

                  {chapters.length === 0 ? (
                    <p className="hint">Chưa có chương nào.</p>
                  ) : (
                    <div className="list">
                      {chapters.map((chapter, index) => (
                        <div key={chapter.chapter_id} className="list-item">
                          <span className="list-index" aria-hidden="true">
                            {index + 1}
                          </span>
                          <span className="stack-2" style={{ flex: 1, minWidth: 0 }}>
                            <Link
                              href={`/chapters/${chapter.chapter_id}`}
                              className="truncate"
                              style={{ fontWeight: 600, fontSize: "var(--t-sm)" }}
                            >
                              {chapter.title}
                            </Link>
                            <span className="hint">
                              {formatNumber(chapter.char_count)} ký tự
                            </span>
                          </span>
                          {audioByChapter[chapter.chapter_id] ? (
                            <span className="badge badge-ok">Có audio</span>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={() => makeAudio(chapter.chapter_id)}
                              disabled={!voiceId || (job?.chapter_id === chapter.chapter_id &&
                                (job.status === "pending" || job.status === "running"))}
                            >
                              Tạo audio
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {job ? (
                    <div className="stack-2" aria-live="polite">
                      <div className="row-between">
                        <span className="hint">Tiến trình tạo audio</span>
                        <JobBadge status={job.status} />
                      </div>
                      {job.status === "pending" || job.status === "running" ? (
                        <ProgressBar
                          percent={job.progress || 6}
                          indeterminate={!job.total_parts}
                          label="Đang tạo audio"
                        />
                      ) : null}
                      {job.status === "failed" ? (
                        <>
                          <Alert kind="error">
                            {job.error_message || "Không rõ nguyên nhân."}
                          </Alert>
                          <div className="row">
                            <button
                              type="button"
                              className="btn btn-sm btn-primary"
                              onClick={() => makeAudio(job.chapter_id)}
                            >
                              Thử lại
                            </button>
                          </div>
                        </>
                      ) : null}
                      {job.status === "completed" && jobChapterId ? (
                        <AudioPlayer
                          chapterId={jobChapterId}
                          title={
                            chapters.find((c) => c.chapter_id === jobChapterId)?.title ??
                            "Chương"
                          }
                          compact
                        />
                      ) : null}
                    </div>
                  ) : null}
                </section>

                <form className="card stack" onSubmit={createChapter}>
                  <h2 className="section-title">Thêm chương</h2>
                  <div className="field">
                    <label className="label" htmlFor="w-ch-title">
                      Tiêu đề chương
                    </label>
                    <input
                      id="w-ch-title"
                      className="input"
                      value={chapterTitle}
                      onChange={(e) => setChapterTitle(e.target.value)}
                      maxLength={200}
                      required
                    />
                  </div>
                  <div className="field">
                    <div className="label-row">
                      <label className="label" htmlFor="w-ch-text">
                        Nội dung
                      </label>
                      <span className="counter">
                        {formatNumber(chapterText.length)} ký tự
                      </span>
                    </div>
                    <textarea
                      id="w-ch-text"
                      className="textarea textarea-tall"
                      value={chapterText}
                      onChange={(e) => setChapterText(e.target.value)}
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={creatingChapter || !chapterTitle.trim() || !chapterText.trim()}
                  >
                    {creatingChapter ? <span className="spinner" aria-hidden="true" /> : null}
                    Thêm chương
                  </button>
                </form>
              </>
            )}
          </section>
        </div>
      )}

      <ConfirmDialog
        open={confirmPublish}
        title="Xuất bản truyện này?"
        body={
          <>
            <p>
              Sau khi xuất bản, <strong>{selected?.title}</strong> sẽ hiện công
              khai trong trang Khám phá và bất kỳ ai cũng nghe được audio của
              các chương.
            </p>
            <p style={{ marginTop: "var(--s2)" }}>
              Hiện chưa có chức năng gỡ xuất bản.
            </p>
          </>
        }
        confirmLabel="Xuất bản"
        busy={publishing}
        onConfirm={doPublish}
        onCancel={() => setConfirmPublish(false)}
      />
    </div>
  );
}
