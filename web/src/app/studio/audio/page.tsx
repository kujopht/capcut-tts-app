"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { TtsPanel } from "@/components/media/TtsPanel";
import { RecentAudioCard } from "@/components/studio/RecentAudioCard";
import { api, getToken, videoStudio, type Profile, type TtsJob, type VideoAudioChoice, type Voice } from "@/lib/api";
import { useSession } from "@/lib/session";
import { tieuDeTuVanBan } from "@/lib/tieuDe";
import { defaultVoiceId } from "@/lib/voices";
import { ensureStudioNovel } from "@/lib/workspace";
import { useJobTracker } from "@/lib/useJobTracker";
import { loginHref } from "@/lib/nav";

interface AudioDraft {
  tieuDe?: string;
  vanBan?: string;
  giong?: string;
  tocDo?: string;
}

let initialDraftCached: AudioDraft | null = null;
let initialDraftLoaded = false;

function getInitialDraft(): AudioDraft | null {
  if (typeof window === "undefined") return null;
  if (initialDraftLoaded) return initialDraftCached;
  initialDraftLoaded = true;
  try {
    const raw = sessionStorage.getItem("fanfic_audio_draft");
    if (raw) {
      sessionStorage.removeItem("fanfic_audio_draft");
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        initialDraftCached = parsed as AudioDraft;
        return initialDraftCached;
      }
    }
  } catch {
    // ignore
  }
  initialDraftCached = null;
  return null;
}

const emptySubscribe = () => () => {};
const getServerSnapshot = () => null;

/** Audio is deliberately a focused primary surface. Media is an opt-in next step. */
export default function AudioStudio() {
  const router = useRouter();
  const { profile, loading: sessionLoading } = useSession();

  const draft = useSyncExternalStore(
    emptySubscribe,
    getInitialDraft,
    getServerSnapshot,
  );

  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState(() => draft?.giong ?? "");
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState(() => (draft ? "Đã khôi phục bản nháp của bạn." : ""));
  const [recent, setRecent] = useState<VideoAudioChoice[]>([]);

  const sessionWaiters = useRef<Array<(p: Profile | null) => void>>([]);
  /**
   * CHONG TAO TRUNG (Social & Play V1):
   *   * `dangGui` khoa ngay trong cung nhip bam — `setCreating` cua React chua kip
   *     ve lai thi cu bam thu hai da chay qua phan dau cua ham;
   *   * `lanTruoc` giu CHUONG da tao cho dung (tieu de, van ban, giong, toc do) do: bam lai / thu
   *     lai sau that bai dung LAI chuong do, va may chu tra lai dung job dang
   *     cho/dang chay (dau van tay noi dung) thay vi tong hop giong LAN HAI tren
   *     mot chuong moi. Job `failed` thi may chu cho tao job moi — dung y "Thử lại".
   */
  const dangGui = useRef(false);
  const lanTruoc = useRef<{ khoa: string; chapterId: string } | null>(null);

  useEffect(() => {
    if (!sessionLoading) {
      while (sessionWaiters.current.length > 0) {
        const resolve = sessionWaiters.current.shift();
        resolve?.(profile);
      }
    }
  }, [sessionLoading, profile]);

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
      setVoice((curr) => curr || draft?.giong || defaultVoiceId(v.voices));
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
  }, [profile, khoiPhuc, draft]);

  const create = async ({ tieuDe, vanBan, giong, tocDo }: { tieuDe: string; vanBan: string; giong: string; tocDo: string }) => {
    if (dangGui.current) return;
    dangGui.current = true;
    try {
      await taoThat({ tieuDe, vanBan, giong, tocDo });
    } finally {
      dangGui.current = false;
    }
  };

  const taoThat = async ({ tieuDe, vanBan, giong, tocDo }: { tieuDe: string; vanBan: string; giong: string; tocDo: string }) => {
    let activeProfile = profile;
    if (sessionLoading) {
      setCreating(true);
      activeProfile = await new Promise<Profile | null>((resolve) => {
        if (typeof window !== "undefined" && !getToken()) {
          resolve(null);
          return;
        }
        const timer = setTimeout(() => {
          resolve(profile);
        }, 5000);
        sessionWaiters.current.push((p) => {
          clearTimeout(timer);
          resolve(p);
        });
      });
    }

    if (!activeProfile) {
      setCreating(false);
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
      const tieuDeThat = tieuDe || tieuDeTuVanBan(vanBan);
      // Khoa gom CA giong + toc do (review cheo PR B): the "Audio gan day" phat/tai
      // theo chapter_id, nen doi giong/toc do voi cung van ban phai ra CHUONG MOI —
      // chi bam lai / thu lai y het moi dung lai chuong cu.
      const khoa = [tieuDeThat, vanBan, giong, tocDo].join("␟");
      let chapterId = lanTruoc.current?.khoa === khoa ? lanTruoc.current.chapterId : "";
      if (!chapterId) {
        const novel = await ensureStudioNovel();
        const chapter = await api.createChapter(novel.novel_id, tieuDeThat, vanBan, 1);
        chapterId = chapter.chapter.chapter_id;
        lanTruoc.current = { khoa, chapterId };
      }
      const r = await api.createJob(chapterId, giong, tocDo);
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
          key={draft ? "restored-draft" : "fresh"}
          voices={voices}
          giong={voice || draft?.giong || ""}
          onGiong={setVoice}
          dangTao={creating}
          loi={notice || (draft ? "Đã khôi phục bản nháp của bạn." : "")}
          onTao={create}
          job={jobs.dangChay[0] ?? null}
          initialDraft={draft}
        />
      </div>
      <section className="audio-recent">
        <div className="audio-recent-head">
          <h2>Audio gần đây</h2>
          <p className="hint">Nghe, tải xuống hoặc mở một bản có sẵn trong Media Editor.</p>
        </div>
        <div className="audio-recent-list">
          {sessionLoading ? (
            <div className="card stack-2" style={{ padding: "var(--s3)", marginTop: "var(--s2)", textAlign: "center" }}>
              <p className="hint">Đang tải danh sách audio…</p>
            </div>
          ) : !profile ? (
            <div className="card stack-2" style={{ padding: "var(--s3)", marginTop: "var(--s2)", textAlign: "center" }}>
              <p className="hint">Đăng nhập để xem và quản lý danh sách audio bạn đã tạo.</p>
              <Link className="btn btn-sm btn-primary" href={loginHref("/studio/audio")} prefetch={false} style={{ alignSelf: "center" }}>
                Đăng nhập
              </Link>
            </div>
          ) : recent.length === 0 ? (
            /* Trong THAT: khong dung mot trinh phat gia 0:00 / --:--. */
            <p className="hint audio-gan-day-trong">Chưa có bản audio nào. Bản bạn tạo xong sẽ hiện ở đây.</p>
          ) : (
            recent.map((a) => <RecentAudioCard key={a.track_id} a={a} voices={voices} />)
          )}
        </div>
      </section>
    </section>
  );
}
