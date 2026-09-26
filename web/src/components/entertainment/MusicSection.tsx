"use client";

/**
 * Trinh phat nhac Fantasy — TACH NGUYEN VAN khoi trang Giai tri (Social & Play V1).
 *
 * Chi duoc render khi `MUSIC_ENABLED` (`lib/features.ts`). Ma ben duoi la ma cu, khong
 * sua hanh vi: bat lai co la co lai dung trinh phat nhu truoc.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  musicStore,
  TRACKS,
  getTrackLyric,
  getActiveLyricLine,
  formatTime,
  type MusicTrack,
} from "@/lib/musicStore";

type MoodCategory = "all" | "chill" | "fantasy" | "epic" | "lofi" | "edm" | "reading";

interface MoodChipDef {
  id: MoodCategory;
  label: string;
}

const MOOD_CHIPS: MoodChipDef[] = [
  { id: "all", label: "Tất cả" },
  { id: "chill", label: "Thư giãn" },
  { id: "fantasy", label: "Fantasy" },
  { id: "epic", label: "Epic" },
  { id: "lofi", label: "Lofi" },
  { id: "edm", label: "EDM" },
  { id: "reading", label: "Đọc truyện" },
];

function trackMatchesMood(track: MusicTrack, mood: MoodCategory): boolean {
  if (mood === "all") return true;
  const text = `${track.title} ${track.subtitle} ${track.mood}`.toLowerCase();
  switch (mood) {
    case "chill":
      return (
        text.includes("thư giãn") ||
        text.includes("thư thái") ||
        text.includes("tĩnh tâm") ||
        text.includes("tĩnh lặng") ||
        text.includes("chill")
      );
    case "fantasy":
      return (
        text.includes("fantasy") ||
        text.includes("huyền ảo") ||
        text.includes("tinh vân") ||
        text.includes("biển sao")
      );
    case "epic":
      return (
        text.includes("bùng nổ") ||
        text.includes("khám phá") ||
        text.includes("odyssey") ||
        text.includes("hành")
      );
    case "lofi":
      return text.includes("lofi") || text.includes("piano");
    case "edm":
      return (
        text.includes("edm") ||
        text.includes("trap") ||
        text.includes("electronic") ||
        text.includes("bass drop")
      );
    case "reading":
      return (
        text.includes("đọc sách") ||
        text.includes("thư viện") ||
        text.includes("tiểu thuyết") ||
        text.includes("thư thái")
      );
    default:
      return true;
  }
}

export function MusicSection() {
  const [selectedMood, setSelectedMood] = useState<MoodCategory>("all");

  const { isPlaying, currentTrackIndex, currentTrack, volume } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  const [currentTime, setCurrentTime] = useState(() => musicStore.getCurrentTime());

  useEffect(() => {
    const unsub = musicStore.subscribeTime((t) => setCurrentTime(t));
    return unsub;
  }, []);

  // Smooth scrubbing seek bar handlers
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [scrubRatio, setScrubRatio] = useState<number | null>(null);
  const seekTrackRef = useRef<HTMLDivElement | null>(null);

  const duration = musicStore.getDurationSeconds();
  const currentRatio = duration > 0 ? Math.max(0, Math.min(1, currentTime / duration)) : 0;
  const progressRatio = isScrubbing && scrubRatio !== null ? scrubRatio : currentRatio;
  const displayTime = isScrubbing && scrubRatio !== null ? scrubRatio * duration : currentTime;

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    setIsScrubbing(true);
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setScrubRatio(ratio);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isScrubbing || !seekTrackRef.current) return;
    const rect = seekTrackRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setScrubRatio(ratio);
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isScrubbing) {
      if (seekTrackRef.current) {
        const rect = seekTrackRef.current.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        musicStore.seek(ratio * duration);
      }
      setIsScrubbing(false);
      setScrubRatio(null);
    }
  };

  const filteredTracks = TRACKS.filter((t) => trackMatchesMood(t, selectedMood));

  return (
        <section className="stack-3" aria-label="Trình phát nhạc Fantasy">
          {/* Primary Now Playing Card */}
          <div
            className="ent-player-card"
            style={{ ["--track-color" as string]: currentTrack.color }}
          >
            {/* Top Row: Track Meta + Controls + Volume */}
            <div className="ent-player-top">
              {/* Artwork & Details */}
              <div className="ent-player-meta">
                <div className="ent-player-art" aria-hidden="true">
                  {currentTrack.icon}
                </div>
                <div className="ent-player-details">
                  <div className="ent-player-title">{currentTrack.title}</div>
                  <div className="ent-player-sub">
                    {currentTrack.subtitle} •{" "}
                    <span style={{ color: currentTrack.color, fontWeight: 600 }}>
                      {currentTrack.mood}
                    </span>
                  </div>
                </div>
              </div>

              {/* Controls */}
              <div className="ent-player-controls">
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  title="Bài trước"
                  aria-label="Bài trước"
                  onClick={() => musicStore.prevTrack()}
                >
                  ⏮
                </button>
                <button
                  type="button"
                  className="ent-btn-play"
                  onClick={() => musicStore.togglePlay()}
                >
                  {isPlaying ? "⏸ Tạm dừng" : "▶ Phát nhạc"}
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  title="Bài tiếp"
                  aria-label="Bài tiếp"
                  onClick={() => musicStore.nextTrack()}
                >
                  ⏭
                </button>

                {/* Volume Slider */}
                <div className="ent-volume-wrap">
                  <span style={{ fontSize: 13 }} aria-hidden="true">
                    🔊
                  </span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={volume}
                    onChange={(e) => musicStore.setVolume(parseFloat(e.target.value))}
                    style={{ width: 68, accentColor: "var(--brand)" }}
                    aria-label="Âm lượng"
                  />
                </div>
              </div>
            </div>

            {/* Middle Row: Seek / Progress Bar */}
            <div className="ent-seek-row">
              <span className="ent-time-label" style={{ textAlign: "right" }}>
                {formatTime(displayTime)}
              </span>
              <div
                ref={seekTrackRef}
                role="slider"
                aria-label="Tiến trình bài hát"
                aria-valuemin={0}
                aria-valuemax={Math.round(duration)}
                aria-valuenow={Math.round(displayTime)}
                tabIndex={0}
                className={`ent-seek-bar ${isScrubbing ? "is-scrubbing" : ""}`}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight") {
                    e.preventDefault();
                    musicStore.seek(Math.min(duration, currentTime + 5));
                  }
                  if (e.key === "ArrowLeft") {
                    e.preventDefault();
                    musicStore.seek(Math.max(0, currentTime - 5));
                  }
                }}
              >
                {/* Filled portion */}
                <div
                  className="ent-seek-fill"
                  style={{ width: `${progressRatio * 100}%` }}
                />
                {/* Seek dot */}
                <div
                  className="ent-seek-thumb"
                  style={{
                    left: `${progressRatio * 100}%`,
                    opacity: isPlaying || isScrubbing ? 1 : 0.65,
                  }}
                />
              </div>
              <span className="ent-time-label">{formatTime(duration)}</span>
            </div>

            {/* Bottom Row: Live Synchronized Lyrics */}
            {isPlaying && (() => {
              const activeLine = getActiveLyricLine(currentTrack, currentTime);
              const words = activeLine?.words;
              return (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "8px 14px",
                    borderRadius: "var(--r2)",
                    background: `color-mix(in srgb, ${currentTrack.color} 10%, rgba(0, 0, 0, 0.45))`,
                    border: `1px solid color-mix(in srgb, ${currentTrack.color} 30%, transparent)`,
                    boxShadow: `0 0 16px color-mix(in srgb, ${currentTrack.color} 14%, transparent)`,
                    overflow: "hidden",
                  }}
                >
                  <span
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      letterSpacing: "0.08em",
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: `color-mix(in srgb, ${currentTrack.color} 25%, transparent)`,
                      color: currentTrack.color,
                      border: `1px solid color-mix(in srgb, ${currentTrack.color} 50%, transparent)`,
                      flexShrink: 0,
                    }}
                  >
                    LIVE LYRICS
                  </span>
                  <div
                    key={activeLine?.text || "intro"}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.38em",
                      fontSize: "0.9rem",
                      fontWeight: 600,
                      letterSpacing: "0.01em",
                      animation: "lyric-line-enter 0.32s cubic-bezier(0.16, 1, 0.3, 1) forwards",
                      overflowX: "auto",
                      scrollbarWidth: "none",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {words && words.length > 0 ? (
                      words.map((w, idx) => {
                        const isCurrent = currentTime >= w.start && currentTime <= w.end;
                        const isPast = currentTime > w.end;
                        return (
                          <span
                            key={`${idx}-${w.word}-${w.start}`}
                            className={`lyric-word ${isCurrent ? "is-current" : isPast ? "is-past" : "is-upcoming"}`}
                          >
                            {w.word}
                          </span>
                        );
                      })
                    ) : (
                      <span className="lyric-word is-current">
                        {activeLine?.text || getTrackLyric(currentTrack, currentTime)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>

          {/* Mood / Category Chip Row */}
          <div className="ent-mood-row" role="toolbar" aria-label="Lọc theo thể loại nhạc">
            <span
              style={{
                fontSize: "0.74rem",
                fontWeight: 700,
                color: "var(--text-3)",
                letterSpacing: "0.06em",
                marginRight: 4,
                textTransform: "uppercase",
              }}
            >
              Thể loại:
            </span>
            {MOOD_CHIPS.map((chip) => (
              <button
                key={chip.id}
                type="button"
                className={`ent-mood-chip ${selectedMood === chip.id ? "is-active" : ""}`}
                onClick={() => setSelectedMood(chip.id)}
              >
                {chip.label}
              </button>
            ))}
          </div>

          {/* Playlist / Track List — Natural Streaming Music Flow */}
          <div className="ent-tracklist" role="list" aria-label="Danh sách bài hát">
            {filteredTracks.map((t) => {
              const originalIndex = TRACKS.indexOf(t);
              const isActive = originalIndex === currentTrackIndex;
              const isCurrentPlaying = isActive && isPlaying;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    musicStore.setTrackIndex(originalIndex);
                    musicStore.play();
                  }}
                  className={`ent-track-item ${isActive ? "is-active" : ""}`}
                  style={{ ["--track-color" as string]: t.color }}
                >
                  {/* Track # or Spotify EQ Bars */}
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: isCurrentPlaying ? 14 : "0.82rem",
                      fontWeight: 600,
                      color: isActive ? t.color : "var(--text-3)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {isCurrentPlaying ? (
                      <span className="music-eq-bars" style={{ ["--eq-color" as string]: t.color }}>
                        <span />
                        <span />
                        <span />
                        <span />
                      </span>
                    ) : (
                      originalIndex + 1
                    )}
                  </span>

                  {/* Artwork Icon */}
                  <span
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 8,
                      background: `color-mix(in srgb, ${t.color} 18%, rgba(0,0,0,0.3))`,
                      border: `1px solid color-mix(in srgb, ${t.color} 30%, transparent)`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 18,
                      flexShrink: 0,
                    }}
                    aria-hidden="true"
                  >
                    {t.icon}
                  </span>

                  {/* Info */}
                  <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                    <div
                      style={{
                        fontSize: "0.88rem",
                        fontWeight: isActive ? 750 : 550,
                        color: isActive ? t.color : "var(--text)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {t.title}
                    </div>
                    <div
                      style={{
                        fontSize: "0.74rem",
                        color: "var(--text-3)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {t.subtitle.split("•")[0]?.trim()} ·{" "}
                      <span style={{ color: isActive ? t.color : "inherit" }}>{t.mood}</span>
                    </div>
                  </div>

                  {/* Duration */}
                  <span
                    style={{
                      fontSize: "0.78rem",
                      fontVariantNumeric: "tabular-nums",
                      color: isActive ? t.color : "var(--text-3)",
                      fontWeight: isActive ? 600 : 400,
                      paddingRight: 4,
                    }}
                  >
                    {t.duration}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
  );
}
