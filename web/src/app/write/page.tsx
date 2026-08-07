"use client";

/**
 * Khu vuc tac gia: tao / sua / xoa truyen va chuong, tao audio, xuat ban.
 *
 * Kho chua cua Audio Studio bi loc ra o day — audio tao nhanh khong phai
 * truyen fanfic.
 *
 * Moi thao tac ghi deu: hien trang thai dang chay -> cap nhat giao dien NGAY
 * khi backend tra ve -> toast thanh cong hoac loi. Thao tac xoa co modal xac
 * nhan noi ro se mat nhung gi.
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

/** Thao tac xoa dang cho xac nhan. */
type PendingDelete =
  | { kind: "novel"; id: string; title: string }
  | { kind: "chapter"; id: string; title: string; hasAudio: boolean }
  | null;

function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .slice(0, 6);
}

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

  const [editingNovel, setEditingNovel] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editTags, setEditTags] = useState("");
  const [savingNovel, setSavingNovel] = useState(false);

  const [chapterTitle, setChapterTitle] = useState("");
  const [chapterText, setChapterText] = useState("");
  const [creatingChapter, setCreatingChapter] = useState(false);

  const [editingChapterId, setEditingChapterId] = useState("");
  const [chEditTitle, setChEditTitle] = useState("");
  const [chEditText, setChEditText] = useState("");
  const [savingChapter, setSavingChapter] = useState(false);

  const [voiceId, setVoiceId] = useState("");
  const [job, setJob] = useState<TtsJob | null>(null);
  const [jobChapterId, setJobChapterId] = useState("");
  const [confirmPublish, setConfirmPublish] = useState<"publish" | "unpublish" | null>(
    null,
  );
  const [togglingPublish, setTogglingPublish] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete>(null);
  const [deleting, setDeleting] = useState(false);

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
      .then((detail) => {
        setChapters(detail.chapters);
        // `has_audio` di kem san trong danh sach chuong. Van giu o state vi
        // cho nay con tu cap nhat khi mot job vua xong hoac chuong bi xoa.
        setAudioByChapter(
          Object.fromEntries(
            detail.chapters.map((c) => [c.chapter_id, Boolean(c.has_audio)]),
          ),
        );
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

  /* ------------------------------------------------------------- truyen */

  const createNovel = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!novelTitle.trim()) return;
      setCreatingNovel(true);
      try {
        const created = await api.createNovel(
          novelTitle.trim(),
          novelDesc.trim(),
          parseTags(novelTags),
        );
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

  const startEditNovel = useCallback(() => {
    if (!selected) return;
    setEditTitle(selected.title);
    setEditDesc(selected.description);
    setEditTags(selected.tags.join(", "));
    setEditingNovel(true);
  }, [selected]);

  const saveNovel = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!selected || !editTitle.trim()) return;
      setSavingNovel(true);
      try {
        const result = await api.updateNovel(selected.novel_id, {
          title: editTitle.trim(),
          description: editDesc.trim(),
          tags: parseTags(editTags),
        });
        setNovels((current) =>
          current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
        );
        setEditingNovel(false);
        toast.ok("Đã lưu thay đổi.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setSavingNovel(false);
      }
    },
    [selected, editTitle, editDesc, editTags, toast],
  );

  const togglePublish = useCallback(async () => {
    if (!selected || !confirmPublish) return;
    const wantPublish = confirmPublish === "publish";
    setTogglingPublish(true);
    try {
      const result = wantPublish
        ? await api.publishNovel(selected.novel_id)
        : await api.unpublishNovel(selected.novel_id);
      setNovels((current) =>
        current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
      );
      toast.ok(
        wantPublish
          ? "Đã xuất bản. Truyện hiện ra trong trang Khám phá."
          : "Đã gỡ xuất bản. Truyện trở lại bản nháp.",
      );
      setConfirmPublish(null);
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setTogglingPublish(false);
    }
  }, [selected, confirmPublish, toast]);

  /* ------------------------------------------------------------- chuong */

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

  const startEditChapter = useCallback(async (chapter: Chapter) => {
    setEditingChapterId(chapter.chapter_id);
    setChEditTitle(chapter.title);
    setChEditText("");
    try {
      const detail = await api.getChapter(chapter.chapter_id);
      setChEditText(detail.chapter.content ?? "");
    } catch {
      setChEditText("");
    }
  }, []);

  const saveChapter = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!editingChapterId || !chEditTitle.trim()) return;
      setSavingChapter(true);
      try {
        const result = await api.updateChapter(editingChapterId, {
          title: chEditTitle.trim(),
          content: chEditText,
        });
        setChapters((current) =>
          current.map((c) =>
            c.chapter_id === result.chapter.chapter_id ? result.chapter : c,
          ),
        );
        setEditingChapterId("");
        toast.ok("Đã lưu chương.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setSavingChapter(false);
      }
    },
    [editingChapterId, chEditTitle, chEditText, toast],
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

  /* --------------------------------------------------------------- xoa */

  const doDelete = useCallback(async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setDeleting(true);
    try {
      if (target.kind === "novel") {
        const result = await api.deleteNovel(target.id);
        // Tinh danh sach con lai TRUOC roi moi dat trang thai. Ham cap nhat
        // cua `setState` phai THUAN KHIET — goi mot setState khac ben trong no
        // se bi React 19 chan, va khi do ca khoi nay dung giua chung: giao dien
        // khong doi, khong toast, dau kho backend da xoa xong.
        const left = novels.filter((n) => n.novel_id !== target.id);
        setNovels(left);
        setSelectedId(left[0]?.novel_id ?? "");
        setChapters([]);
        setAudioByChapter({});
        setJob(null);
        toast.ok(
          `Đã xoá truyện cùng ${result.removed.chapters ?? 0} chương và ` +
            `${result.removed.objects} file audio.`,
        );
      } else {
        const result = await api.deleteChapter(target.id);
        setChapters((current) => current.filter((c) => c.chapter_id !== target.id));
        setAudioByChapter((current) => {
          const next = { ...current };
          delete next[target.id];
          return next;
        });
        if (jobChapterId === target.id) {
          setJob(null);
          setJobChapterId("");
        }
        if (editingChapterId === target.id) setEditingChapterId("");
        toast.ok(
          result.removed.objects > 0
            ? "Đã xoá chương và file audio của nó."
            : "Đã xoá chương.",
        );
      }
      setPendingDelete(null);
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, novels, jobChapterId, editingChapterId, toast]);

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
                  {editingNovel ? (
                    <form className="stack" onSubmit={saveNovel}>
                      <h2 className="section-title">Sửa truyện</h2>
                      <div className="field">
                        <label className="label" htmlFor="w-edit-title">
                          Tiêu đề
                        </label>
                        <input
                          id="w-edit-title"
                          className="input"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          maxLength={200}
                          required
                        />
                      </div>
                      <div className="field">
                        <label className="label" htmlFor="w-edit-desc">
                          Mô tả
                        </label>
                        <textarea
                          id="w-edit-desc"
                          className="textarea"
                          style={{ minHeight: 90 }}
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                        />
                      </div>
                      <div className="field">
                        <label className="label" htmlFor="w-edit-tags">
                          Thẻ
                        </label>
                        <input
                          id="w-edit-tags"
                          className="input"
                          value={editTags}
                          onChange={(e) => setEditTags(e.target.value)}
                        />
                      </div>
                      <div className="row">
                        <button
                          type="submit"
                          className="btn btn-primary"
                          disabled={savingNovel || !editTitle.trim()}
                        >
                          {savingNovel ? (
                            <span className="spinner" aria-hidden="true" />
                          ) : null}
                          Lưu thay đổi
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => setEditingNovel(false)}
                          disabled={savingNovel}
                        >
                          Huỷ
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <div className="row-between">
                        <div className="stack-2" style={{ minWidth: 0 }}>
                          <h2 className="section-title">{selected.title}</h2>
                          <span className="hint">
                            {chapters.length} chương ·{" "}
                            {published ? "đã xuất bản" : "bản nháp, chỉ mình bạn thấy"}
                          </span>
                          {selected.description ? (
                            <p className="hint clamp-2">{selected.description}</p>
                          ) : null}
                        </div>
                        <div className="row" style={{ gap: "var(--s2)" }}>
                          <Link
                            className="btn btn-sm"
                            href={`/novels/${selected.novel_id}`}
                          >
                            Xem trang truyện
                          </Link>
                          <button type="button" className="btn btn-sm" onClick={startEditNovel}>
                            Sửa
                          </button>
                          {published ? (
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={() => setConfirmPublish("unpublish")}
                            >
                              Gỡ xuất bản
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => setConfirmPublish("publish")}
                              disabled={chapters.length === 0}
                            >
                              Xuất bản
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            onClick={() =>
                              setPendingDelete({
                                kind: "novel",
                                id: selected.novel_id,
                                title: selected.title,
                              })
                            }
                          >
                            Xoá
                          </button>
                        </div>
                      </div>
                      {!published && chapters.length === 0 ? (
                        <Alert kind="info">
                          Thêm ít nhất một chương trước khi xuất bản.
                        </Alert>
                      ) : null}
                    </>
                  )}
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
                          className="select select-inline"
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
                      {chapters.map((chapter, index) =>
                        editingChapterId === chapter.chapter_id ? (
                          <form
                            key={chapter.chapter_id}
                            className="card card-tight stack"
                            onSubmit={saveChapter}
                          >
                            <div className="field">
                              <label className="label" htmlFor="w-ch-edit-title">
                                Tiêu đề chương
                              </label>
                              <input
                                id="w-ch-edit-title"
                                className="input"
                                value={chEditTitle}
                                onChange={(e) => setChEditTitle(e.target.value)}
                                maxLength={200}
                                required
                              />
                            </div>
                            <div className="field">
                              <div className="label-row">
                                <label className="label" htmlFor="w-ch-edit-text">
                                  Nội dung
                                </label>
                                <span className="counter">
                                  {formatNumber(chEditText.length)} ký tự
                                </span>
                              </div>
                              <textarea
                                id="w-ch-edit-text"
                                className="textarea"
                                value={chEditText}
                                onChange={(e) => setChEditText(e.target.value)}
                              />
                            </div>
                            {audioByChapter[chapter.chapter_id] ? (
                              <Alert kind="warn">
                                Chương này đã có audio. Sửa nội dung sẽ không tự
                                tạo lại audio — hãy bấm Tạo audio sau khi lưu.
                              </Alert>
                            ) : null}
                            <div className="row">
                              <button
                                type="submit"
                                className="btn btn-primary btn-sm"
                                disabled={savingChapter || !chEditTitle.trim()}
                              >
                                {savingChapter ? (
                                  <span className="spinner" aria-hidden="true" />
                                ) : null}
                                Lưu chương
                              </button>
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={() => setEditingChapterId("")}
                                disabled={savingChapter}
                              >
                                Huỷ
                              </button>
                            </div>
                          </form>
                        ) : (
                          <div key={chapter.chapter_id} className="list-item">
                            <span className="list-index" aria-hidden="true">
                              {index + 1}
                            </span>
                            <span className="stack-2" style={{ flex: 1, minWidth: 0 }}>
                              <Link
                                href={`/chapters/${chapter.chapter_id}`}
                                className="truncate list-title"
                                style={{ fontWeight: 600, fontSize: "var(--t-sm)" }}
                              >
                                {chapter.title}
                              </Link>
                              <span className="hint">
                                {formatNumber(chapter.char_count)} ký tự
                              </span>
                            </span>
                            {/* Ca nhom nut nam trong `.list-actions` de o
                                mobile chung xuong dong rieng — de chung hang
                                thi tieu de chuong bi nen con "Chuo...". */}
                            <span className="list-actions">
                              {audioByChapter[chapter.chapter_id] ? (
                                <span className="badge badge-ok">Có audio</span>
                              ) : (
                                <button
                                  type="button"
                                  className="btn btn-sm"
                                  onClick={() => makeAudio(chapter.chapter_id)}
                                  disabled={
                                    !voiceId ||
                                    (job?.chapter_id === chapter.chapter_id &&
                                      (job.status === "pending" || job.status === "running"))
                                  }
                                >
                                  Tạo audio
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn btn-sm btn-ghost"
                                onClick={() => startEditChapter(chapter)}
                                aria-label={`Sửa chương ${chapter.title}`}
                              >
                                Sửa
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-danger"
                                onClick={() =>
                                  setPendingDelete({
                                    kind: "chapter",
                                    id: chapter.chapter_id,
                                    title: chapter.title,
                                    hasAudio: Boolean(audioByChapter[chapter.chapter_id]),
                                  })
                                }
                                aria-label={`Xoá chương ${chapter.title}`}
                              >
                                Xoá
                              </button>
                            </span>
                          </div>
                        ),
                      )}
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

      {/* ------------------------------------------------ xac nhan xuat ban */}
      <ConfirmDialog
        open={confirmPublish !== null}
        title={
          confirmPublish === "unpublish"
            ? "Gỡ xuất bản truyện này?"
            : "Xuất bản truyện này?"
        }
        body={
          confirmPublish === "unpublish" ? (
            <>
              <p>
                <strong>{selected?.title}</strong> sẽ biến mất khỏi trang Khám
                phá, và audio của các chương trở lại chế độ riêng tư.
              </p>
              <p style={{ marginTop: "var(--s2)" }}>
                Nội dung không bị xoá — bạn xuất bản lại bất cứ lúc nào.
              </p>
            </>
          ) : (
            <>
              <p>
                Sau khi xuất bản, <strong>{selected?.title}</strong> sẽ hiện công
                khai trong trang Khám phá và bất kỳ ai cũng nghe được audio của
                các chương.
              </p>
              <p style={{ marginTop: "var(--s2)" }}>Bạn có thể gỡ xuất bản sau.</p>
            </>
          )
        }
        confirmLabel={confirmPublish === "unpublish" ? "Gỡ xuất bản" : "Xuất bản"}
        busy={togglingPublish}
        onConfirm={togglePublish}
        onCancel={() => setConfirmPublish(null)}
      />

      {/* ----------------------------------------------------- xac nhan xoa */}
      <ConfirmDialog
        open={pendingDelete !== null}
        danger
        title={pendingDelete?.kind === "novel" ? "Xoá cả truyện này?" : "Xoá chương này?"}
        body={
          pendingDelete?.kind === "novel" ? (
            <>
              <p>
                <strong>{pendingDelete.title}</strong> sẽ bị xoá cùng{" "}
                <strong>toàn bộ {chapters.length} chương</strong> và mọi file
                audio đã tạo.
              </p>
              <p style={{ marginTop: "var(--s2)" }}>
                Thao tác này <strong>không hoàn tác được</strong>.
              </p>
            </>
          ) : (
            <>
              <p>
                <strong>{pendingDelete?.title}</strong> sẽ bị xoá
                {pendingDelete?.hasAudio ? " cùng file audio của nó" : ""}.
              </p>
              <p style={{ marginTop: "var(--s2)" }}>
                Thao tác này <strong>không hoàn tác được</strong>.
              </p>
            </>
          )
        }
        confirmLabel="Xoá vĩnh viễn"
        busy={deleting}
        onConfirm={doDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
