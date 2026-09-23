"use client";

/**
 * Trình phát audio + nút tải MP3.
 *
 * Tiêu thụ trực tiếp động cơ âm thanh toàn cục (AudioEngineProvider),
 * KHÔNG tạo thêm thẻ <audio> riêng biệt để tránh xung đột hoặc trùng lặp stream.
 */

import { useEffect, useState } from "react";
import { audioFileName, resolveAudio, type PlayableAudio } from "@/lib/audio";
import { useAudioEngine, dongHo } from "./AudioEngine";
import { errorMessage } from "@/lib/session";
import { formatBytes } from "./ui";

export function AudioPlayer({
  chapterId,
  title,
  compact = false,
}: {
  chapterId: string;
  title: string;
  compact?: boolean;
}) {
  const [downloadInfo, setDownloadInfo] = useState<PlayableAudio | null>(null);
  const [fetchError, setFetchError] = useState("");

  const engine = useAudioEngine();
  const isThisTrack = engine?.trangThai?.chapterId === chapterId;

  const isPlaying = isThisTrack && (engine?.trangThai?.dangPhat ?? false);
  const currentTime = isThisTrack ? (engine?.trangThai?.thoiDiem ?? 0) : 0;
  const duration = isThisTrack ? (engine?.trangThai?.thoiLuong ?? 0) : 0;
  const isReady = isThisTrack && (engine?.trangThai?.sanSang ?? false);
  const isLoading = isThisTrack && (engine?.trangThai?.dangTai ?? false);
  const error = isThisTrack ? (engine?.trangThai?.loi || fetchError) : fetchError;

  // Lấy thông tin kích thước và liên kết tải MP3
  useEffect(() => {
    let cancelled = false;
    resolveAudio(chapterId)
      .then((resolved) => {
        if (!cancelled) setDownloadInfo(resolved);
      })
      .catch((cause) => {
        if (!cancelled) setFetchError(errorMessage(cause));
      });

    return () => {
      cancelled = true;
    };
  }, [chapterId]);

  const handlePlayToggle = () => {
    if (!engine) return;
    if (isThisTrack) {
      engine.dieuKhien.batTat();
    } else {
      engine.dieuKhien.phat(chapterId, title);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!engine) return;
    const target = Number(e.target.value);
    if (!isThisTrack) {
      engine.dieuKhien.phat(chapterId, title);
    }
    engine.dieuKhien.tua(target);
  };

  if (error) {
    return (
      <div className="alert alert-error" role="alert">
        <span aria-hidden="true">⛔</span>
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="player">
      {!compact ? (
        <div className="row-between">
          <span className="row row-tight">
            <span aria-hidden="true">🎧</span>
            <strong className="player-title">{title}</strong>
          </span>
          {downloadInfo ? (
            <span className="hint">{formatBytes(downloadInfo.sizeBytes)}</span>
          ) : null}
        </div>
      ) : null}

      <div className="player-custom-controls" style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "8px" }}>
        <div className="row" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={handlePlayToggle}
            aria-label={isPlaying ? `Tạm dừng audio: ${title}` : `Phát audio: ${title}`}
            style={{ minWidth: "90px", padding: "6px 12px" }}
          >
            {isPlaying ? "⏸ Tạm dừng" : "▶ Phát"}
          </button>
          <input
            type="range"
            min={0}
            max={duration > 0 ? duration : 100}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            disabled={!isThisTrack && !isPlaying}
            aria-label={`Tiến trình audio: ${title}`}
            style={{ flex: 1, cursor: "pointer" }}
          />
          <span className="hint" style={{ fontSize: "0.8rem", minWidth: "85px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
            {dongHo(currentTime)} / {duration > 0 ? dongHo(duration) : "--:--"}
          </span>
        </div>

        <div className="row row-spread" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="hint" role="status" aria-label="Nghe audio" style={{ fontSize: "0.85rem" }}>
            {isLoading ? "Đang chuẩn bị…" : isPlaying ? "Đang phát…" : isReady ? "Sẵn sàng" : "Nghe"}
          </span>
          {downloadInfo ? (
            <a
              className="btn btn-sm"
              href={downloadInfo.downloadUrl}
              download={audioFileName(title)}
              aria-label={`Tải xuống audio MP3: ${title}`}
            >
              <span aria-hidden="true">⬇</span> Tải MP3
            </a>
          ) : (
            <span className="hint" style={{ fontSize: "0.8rem" }}>Đang lấy thông tin…</span>
          )}
        </div>
      </div>
    </div>
  );
}
