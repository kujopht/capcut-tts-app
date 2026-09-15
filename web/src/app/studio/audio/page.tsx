"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TtsPanel } from "@/components/media/TtsPanel";
import { AudioPlayer } from "@/components/AudioPlayer";
import { api, videoStudio, type TtsJob, type VideoAudioChoice, type Voice } from "@/lib/api";
import { useSession } from "@/lib/session";
import { defaultVoiceId } from "@/lib/voices";
import { ensureStudioNovel } from "@/lib/workspace";
import { useJobTracker } from "@/lib/useJobTracker";
import { loginHref } from "@/lib/nav";

function layBanNhap(): { tieuDe?: string; vanBan?: string; giong?: string; tocDo?: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const saved = sessionStorage.getItem("fanfic_audio_draft");
    if (saved) {
      sessionStorage.removeItem("fanfic_audio_draft");
      const parsed = JSON.parse(saved);
      if (parsed && typeof parsed === "object") return parsed;
    }
  } catch {
    // ignore storage access errors
  }
  return null;
}

/** Audio is deliberately a focused primary surface. Media is an opt-in next step. */
export default function AudioStudio() {
  const router = useRouter();
  const { profile } = useSession();
  const [draft] = useState(layBanNhap);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState(() => draft?.giong ?? "");
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState(() => (draft ? "Đã khôi phục bản nháp của bạn." : ""));
  const [recent, setRecent] = useState<VideoAudioChoice[]>([]);

  const refresh = async () => {
    const r = await videoStudio.audioLibrary().catch(() => ({ tracks: [] }));
    setRecent(r.tracks);
  };

  const jobs = useJobTracker({
    onCompleted: async () => {
      setCreating(false);
      setNotice("Đã tạo lời đọc.");
      await refresh();
    },
    onFailed: (j: TtsJob) => {
      setCreating(false);
      setNotice(j.error_message || "Tạo lời đọc thất bại.");
    },
  });
  const { khoiPhuc, theoDoi } = jobs;

  // Fetch public voices unconditionally; fetch user jobs/tracks if authenticated
  useEffect(() => {
    let mounted = true;
    void (async () => {
      const v = await api.voices().catch(() => ({ voices: [] as Voice[] }));
      if (!mounted) return;
      setVoices(v.voices);
      setVoice((curr) => curr || defaultVoiceId(v.voices));
      if (profile) {
        await refresh();
        const j = await api.listJobs().catch(() => ({ jobs: [] as TtsJob[] }));
        if (!mounted) return;
        khoiPhuc(j.jobs);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [profile, khoiPhuc]);

  const create = async ({ tieuDe, vanBan, giong, tocDo }: { tieuDe: string; vanBan: string; giong: string; tocDo: string }) => {
    if (!profile) {
      try {
        sessionStorage.setItem("fanfic_audio_draft", JSON.stringify({ tieuDe, vanBan, giong, tocDo }));
      } catch {
        // ignore storage quota/access errors
      }
      router.push(loginHref("/studio/audio"));
      return;
    }

    try {
      setCreating(true);
      setNotice("");
      const novel = await ensureStudioNovel();
      const chapter = await api.createChapter(novel.novel_id, tieuDe || vanBan.slice(0, 40), vanBan, 1);
      const r = await api.createJob(chapter.chapter.chapter_id, giong, tocDo);
      theoDoi(r.job);
    } catch (e) {
      setCreating(false);
      setNotice(e instanceof Error ? e.message : "Không tạo được audio.");
    }
  };

  return (
    <section className="audio-studio" aria-label="Audio Studio">
      <div className="audio-studio-intro">
        <div>
          <p className="eyebrow">AUDIO STUDIO</p>
          <h2>Tạo lời đọc</h2>
          <p className="hint">Dán văn bản, chọn giọng, nghe và tải audio. Video chỉ là lựa chọn tiếp theo khi bạn cần nó.</p>
        </div>
        <Link className="btn btn-sm" href="/studio/media" prefetch={false}>
          + Thêm video để chỉnh
        </Link>
      </div>
      <div className="audio-create-pane">
        <TtsPanel
          voices={voices}
          giong={voice}
          onGiong={setVoice}
          dangTao={creating}
          loi={notice}
          onTao={create}
          job={jobs.dangChay[0] ?? null}
          initialDraft={draft}
        />
      </div>
      <section className="audio-recent">
        <h2>Audio gần đây</h2>
        <p className="hint">Nghe, tải xuống hoặc mở một bản có sẵn trong Media Editor.</p>
        {!profile ? (
          <div className="card stack-2" style={{ padding: "var(--s3)", marginTop: "var(--s2)", textAlign: "center" }}>
            <p className="hint">Đăng nhập để xem và quản lý danh sách audio bạn đã tạo.</p>
            <Link className="btn btn-sm btn-primary" href={loginHref("/studio/audio")} prefetch={false} style={{ alignSelf: "center" }}>
              Đăng nhập
            </Link>
          </div>
        ) : recent.length === 0 ? (
          <p className="hint" style={{ marginTop: "var(--s2)" }}>Chưa có bản audio nào.</p>
        ) : (
          recent.map((a) => (
            <article className="audio-item" key={a.track_id}>
              <AudioPlayer chapterId={a.chapter_id} title={a.chapter_title} compact />
              <Link className="btn btn-sm" href={`/studio/media?audio=${encodeURIComponent(a.track_id)}`} prefetch={false}>
                Chỉnh với video
              </Link>
            </article>
          ))
        )}
      </section>
    </section>
  );
}
