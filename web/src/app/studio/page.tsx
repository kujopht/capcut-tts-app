"use client";

/**
 * Creator Studio - tron vong: tao novel -> tao chuong -> chon giong -> gui job
 * -> theo doi trang thai -> nghe audio.
 *
 * KHONG tu chuyen sang giong khac khi job that bai: loi duoc hien nguyen van
 * de nguoi dung tu quyet dinh.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type Chapter,
  type Novel,
  type TtsJob,
  type Voice,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { AudioPlayer } from "@/components/AudioPlayer";
import { Alert, EmptyState, JobBadge, Loading } from "@/components/states";

const POLL_MS = 1500;

export default function StudioPage() {
  const { profile, loading: sessionLoading } = useSession();

  const [novels, setNovels] = useState<Novel[]>([]);
  const [selectedNovel, setSelectedNovel] = useState<string>("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<string>("");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string>("");

  const [novelTitle, setNovelTitle] = useState("");
  const [novelDesc, setNovelDesc] = useState("");
  const [chapterTitle, setChapterTitle] = useState("");
  const [chapterContent, setChapterContent] = useState("");

  const [job, setJob] = useState<TtsJob | null>(null);
  const [reused, setReused] = useState(false);
  const [audioChapterId, setAudioChapterId] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // -- nap du lieu ban dau --------------------------------------------------

  const loadNovels = useCallback(async () => {
    const r = await api.listNovels(true);
    setNovels(r.novels);
    return r.novels;
  }, []);

  useEffect(() => {
    if (sessionLoading || !profile) {
      if (!sessionLoading) setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([loadNovels(), api.voices()])
      .then(([, voiceResult]) => {
        setVoices(voiceResult.voices);
        const usable = voiceResult.voices.find((v) => v.installed);
        if (usable) setSelectedVoice(usable.voice_id);
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [profile, sessionLoading, loadNovels]);

  // Nap chuong khi doi novel
  useEffect(() => {
    if (!selectedNovel) {
      setChapters([]);
      setSelectedChapter("");
      return;
    }
    api
      .getNovel(selectedNovel)
      .then((r) => setChapters(r.chapters))
      .catch((e) => setError(errorMessage(e)));
  }, [selectedNovel]);

  // Dung polling khi roi trang
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // -- hanh dong -------------------------------------------------------------

  async function createNovel(event: React.FormEvent) {
    event.preventDefault();
    if (!novelTitle.trim()) {
      setError("Tiểu thuyết phải có tiêu đề.");
      return;
    }
    setBusy("novel");
    setError("");
    try {
      const r = await api.createNovel(novelTitle.trim(), novelDesc.trim());
      setNovelTitle("");
      setNovelDesc("");
      await loadNovels();
      setSelectedNovel(r.novel.novel_id);
      setNotice(`Đã tạo "${r.novel.title}".`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function createChapter(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedNovel) {
      setError("Hãy chọn tiểu thuyết trước.");
      return;
    }
    if (!chapterTitle.trim() || !chapterContent.trim()) {
      setError("Chương cần có tiêu đề và nội dung.");
      return;
    }
    setBusy("chapter");
    setError("");
    try {
      const r = await api.createChapter(
        selectedNovel,
        chapterTitle.trim(),
        chapterContent,
        chapters.length + 1,
      );
      setChapterTitle("");
      setChapterContent("");
      const detail = await api.getNovel(selectedNovel);
      setChapters(detail.chapters);
      setSelectedChapter(r.chapter.chapter_id);
      setNotice(`Đã thêm chương "${r.chapter.title}".`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  function startPolling(jobId: string, chapterId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await api.getJob(jobId);
        setJob(r.job);
        if (r.job.status === "completed" || r.job.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          if (r.job.status === "completed") setAudioChapterId(chapterId);
        }
      } catch (e) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setError(errorMessage(e));
      }
    }, POLL_MS);
  }

  async function submitJob(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedChapter || !selectedVoice) {
      setError("Hãy chọn cả chương và giọng đọc.");
      return;
    }
    setBusy("job");
    setError("");
    setNotice("");
    setAudioChapterId("");
    try {
      const r = await api.createJob(selectedChapter, selectedVoice);
      setJob(r.job);
      setReused(r.reused);
      if (r.job.status === "completed") {
        setAudioChapterId(selectedChapter);
      } else {
        startPolling(r.job.job_id, selectedChapter);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  // -- hien thi --------------------------------------------------------------

  if (sessionLoading) return <Loading label="Đang kiểm tra phiên đăng nhập..." />;

  if (!profile) {
    return (
      <EmptyState
        icon="🔐"
        title="Cần đăng nhập"
        body="Creator Studio chỉ dành cho tài khoản đã đăng nhập."
        action={
          <Link href="/login" className="btn btn-primary">
            Đăng nhập
          </Link>
        }
      />
    );
  }

  if (loading) return <Loading label="Đang tải Creator Studio..." />;

  const chapter = chapters.find((c) => c.chapter_id === selectedChapter);
  const voice = voices.find((v) => v.voice_id === selectedVoice);

  return (
    <>
      <h1 className="page-title">Creator Studio</h1>
      <p className="page-sub">
        Xin chào {profile.display_name} · gói {profile.tier}
      </p>

      {error ? <Alert kind="error">{error}</Alert> : null}
      {notice ? <Alert kind="ok">{notice}</Alert> : null}

      <div
        style={{
          display: "grid",
          gap: 18,
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
        }}
      >
        {/* --- Tao novel --- */}
        <form className="card" onSubmit={createNovel}>
          <h2 style={{ fontSize: 16, marginTop: 0 }}>1 · Tạo tiểu thuyết</h2>
          <div className="field">
            <label className="label" htmlFor="novel-title">
              Tiêu đề
            </label>
            <input
              id="novel-title"
              className="input"
              value={novelTitle}
              onChange={(e) => setNovelTitle(e.target.value)}
              placeholder="Ví dụ: Hải Tặc Mũ Rơm"
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="novel-desc">
              Mô tả
            </label>
            <input
              id="novel-desc"
              className="input"
              value={novelDesc}
              onChange={(e) => setNovelDesc(e.target.value)}
              placeholder="Tuỳ chọn"
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy === "novel"}
          >
            {busy === "novel" ? "Đang tạo..." : "Tạo tiểu thuyết"}
          </button>

          <hr
            style={{
              border: 0,
              borderTop: "1px solid var(--border)",
              margin: "18px 0",
            }}
          />

          <label className="label" htmlFor="novel-select">
            Tiểu thuyết của bạn ({novels.length})
          </label>
          {novels.length === 0 ? (
            <p className="hint">Chưa có tiểu thuyết nào.</p>
          ) : (
            <select
              id="novel-select"
              className="select"
              value={selectedNovel}
              onChange={(e) => setSelectedNovel(e.target.value)}
            >
              <option value="">— Chọn tiểu thuyết —</option>
              {novels.map((n) => (
                <option key={n.novel_id} value={n.novel_id}>
                  {n.title}
                </option>
              ))}
            </select>
          )}
        </form>

        {/* --- Tao chuong --- */}
        <form className="card" onSubmit={createChapter}>
          <h2 style={{ fontSize: 16, marginTop: 0 }}>2 · Thêm chương</h2>
          {!selectedNovel ? (
            <p className="hint">Hãy chọn tiểu thuyết ở bước 1 trước.</p>
          ) : null}
          <div className="field">
            <label className="label" htmlFor="chapter-title">
              Tiêu đề chương
            </label>
            <input
              id="chapter-title"
              className="input"
              value={chapterTitle}
              onChange={(e) => setChapterTitle(e.target.value)}
              disabled={!selectedNovel}
              placeholder="Chương 1: Khởi đầu"
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="chapter-content">
              Nội dung
            </label>
            <textarea
              id="chapter-content"
              className="textarea"
              value={chapterContent}
              onChange={(e) => setChapterContent(e.target.value)}
              disabled={!selectedNovel}
              placeholder="Dán hoặc gõ nội dung chương ở đây..."
            />
            <p className="hint">
              {chapterContent.length.toLocaleString("vi-VN")} ký tự
            </p>
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!selectedNovel || busy === "chapter"}
          >
            {busy === "chapter" ? "Đang lưu..." : "Thêm chương"}
          </button>
        </form>
      </div>

      {/* --- Tao audio --- */}
      <form className="card" onSubmit={submitJob} style={{ marginTop: 18 }}>
        <h2 style={{ fontSize: 16, marginTop: 0 }}>3 · Tạo audio</h2>

        <div
          style={{
            display: "grid",
            gap: 14,
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          }}
        >
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="label" htmlFor="chapter-select">
              Chương
            </label>
            <select
              id="chapter-select"
              className="select"
              value={selectedChapter}
              onChange={(e) => setSelectedChapter(e.target.value)}
              disabled={chapters.length === 0}
            >
              <option value="">
                {chapters.length === 0 ? "— Chưa có chương —" : "— Chọn chương —"}
              </option>
              {chapters.map((c) => (
                <option key={c.chapter_id} value={c.chapter_id}>
                  #{c.order_index} · {c.title}
                </option>
              ))}
            </select>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label className="label" htmlFor="voice-select">
              Giọng đọc ({voices.length})
            </label>
            <select
              id="voice-select"
              className="select"
              value={selectedVoice}
              onChange={(e) => setSelectedVoice(e.target.value)}
            >
              {voices.map((v) => (
                <option
                  key={v.voice_id}
                  value={v.voice_id}
                  disabled={!v.installed}
                >
                  {v.display_name} · {v.provider_label}
                  {v.installed ? "" : " (chưa sẵn sàng)"}
                </option>
              ))}
            </select>
            {voice && !voice.commercial_ready ? (
              <p className="hint" style={{ color: "var(--warn)" }}>
                Giọng chạy cục bộ — chưa xác minh giấy phép, chỉ dùng để phát
                triển.
              </p>
            ) : null}
          </div>
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          style={{ marginTop: 16 }}
          disabled={!selectedChapter || !selectedVoice || busy === "job"}
        >
          {busy === "job" ? "Đang gửi..." : "Gửi yêu cầu tạo audio"}
        </button>

        {chapter ? (
          <p className="hint" style={{ marginBottom: 0 }}>
            Sẽ tạo audio cho “{chapter.title}” ·{" "}
            {chapter.char_count.toLocaleString("vi-VN")} ký tự
          </p>
        ) : null}
      </form>

      {/* --- Trang thai job --- */}
      {job ? (
        <section className="card" style={{ marginTop: 18 }} aria-live="polite">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <h2 style={{ fontSize: 16, margin: 0 }}>Trạng thái job</h2>
            <JobBadge status={job.status} />
            {reused ? (
              <span className="badge">Dùng lại job đã có</span>
            ) : null}
            {job.status === "running" || job.status === "pending" ? (
              <span className="spinner" aria-hidden="true" />
            ) : null}
          </div>

          <p className="hint" style={{ marginBottom: 6 }}>
            Giọng: {job.voice_id} · tiến trình {job.progress}%
            {job.total_parts ? ` (${job.done_parts}/${job.total_parts} phần)` : ""}
          </p>

          {reused ? (
            <Alert kind="ok">
              Nội dung, giọng và thiết lập không đổi nên hệ thống dùng lại job
              trước — không gọi lại dịch vụ tạo audio.
            </Alert>
          ) : null}

          {job.status === "failed" ? (
            <Alert kind="error">
              <strong>Tạo audio thất bại.</strong>{" "}
              {job.error_message || "Không rõ nguyên nhân."}
              {job.error_kind ? (
                <span className="hint"> (mã lỗi: {job.error_kind})</span>
              ) : null}
              <br />
              Hệ thống không tự đổi sang giọng khác — bạn hãy chọn giọng khác
              rồi gửi lại nếu muốn.
            </Alert>
          ) : null}

          {job.status === "completed" && audioChapterId ? (
            <div style={{ marginTop: 12 }}>
              <AudioPlayer
                src={api.audioUrl(audioChapterId)}
                title={chapter?.title ?? "Audio chương"}
                subtitle={`Giọng: ${voice?.display_name ?? job.voice_id}`}
              />
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
