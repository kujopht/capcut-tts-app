"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { TtsPanel } from "@/components/media/TtsPanel";
import { AudioPlayer } from "@/components/AudioPlayer";
import { api, videoStudio, type TtsJob, type VideoAudioChoice, type Voice } from "@/lib/api";
import { useSession } from "@/lib/session";
import { defaultVoiceId } from "@/lib/voices";
import { ensureStudioNovel } from "@/lib/workspace";
import { useJobTracker } from "@/lib/useJobTracker";
import { EmptyState } from "@/components/ui";

/** Audio is deliberately a focused primary surface. Media is an opt-in next step. */
export default function AudioStudio() {
  const { profile } = useSession();
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState("");
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");
  const [recent, setRecent] = useState<VideoAudioChoice[]>([]);
  const refresh = async () => { const r = await videoStudio.audioLibrary().catch(() => ({ tracks: [] })); setRecent(r.tracks); };
  const jobs = useJobTracker({ onCompleted: async () => { setCreating(false); setNotice("Đã tạo lời đọc."); await refresh(); }, onFailed: (j: TtsJob) => { setCreating(false); setNotice(j.error_message || "Tạo lời đọc thất bại."); } });
  const { khoiPhuc, theoDoi } = jobs;
  useEffect(() => { if (!profile) return; void (async () => { const v = await api.voices().catch(() => ({ voices: [] as Voice[] })); setVoices(v.voices); setVoice(defaultVoiceId(v.voices)); await refresh(); const j = await api.listJobs().catch(() => ({ jobs: [] as TtsJob[] })); khoiPhuc(j.jobs); })(); }, [profile, khoiPhuc]);
  const create = async ({ tieuDe, vanBan, giong, tocDo }: { tieuDe: string; vanBan: string; giong: string; tocDo: string }) => { try { setCreating(true); setNotice(""); const novel = await ensureStudioNovel(); const chapter = await api.createChapter(novel.novel_id, tieuDe || vanBan.slice(0, 40), vanBan, 1); const r = await api.createJob(chapter.chapter.chapter_id, giong, tocDo); theoDoi(r.job); } catch (e) { setCreating(false); setNotice(e instanceof Error ? e.message : "Không tạo được audio."); } };
  if (!profile) return <EmptyState icon="🎧" title="Đăng nhập để tạo lời đọc" action={<Link className="btn btn-primary" href="/login?next=/studio/audio" prefetch={false}>Đăng nhập</Link>} />;
  return <section className="audio-studio" aria-label="Audio Studio">
    <div className="audio-studio-intro"><div><p className="eyebrow">AUDIO STUDIO</p><h2>Tạo lời đọc</h2><p className="hint">Dán văn bản, chọn giọng, nghe và tải audio. Video chỉ là lựa chọn tiếp theo khi bạn cần nó.</p></div><Link className="btn btn-sm" href="/studio/media" prefetch={false}>+ Thêm video để chỉnh</Link></div>
    <div className="audio-create-pane"><TtsPanel voices={voices} giong={voice} onGiong={setVoice} dangTao={creating} loi={notice} onTao={create} job={jobs.dangChay[0] ?? null} /></div>
    <section className="audio-recent"><h2>Audio gần đây</h2><p className="hint">Nghe, tải xuống hoặc mở một bản có sẵn trong Media Editor.</p>{recent.map((a) => <article className="audio-item" key={a.track_id}><AudioPlayer chapterId={a.chapter_id} title={a.chapter_title} compact /><Link className="btn btn-sm" href={`/studio/media?audio=${encodeURIComponent(a.track_id)}`} prefetch={false}>Chỉnh với video</Link></article>)}</section>
  </section>;
}
