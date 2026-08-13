"use client";

/**
 * Trinh phat audio + nut tai MP3.
 *
 * Dung the <audio controls> co san cua trinh duyet (dieu khien ban phim,
 * doc man hinh, tua — deu co san va dung chuan) nhung ep ve dark theme bang
 * `color-scheme: dark` trong globals.css.
 *
 * URL phat KHONG phai la `/api/audio/{id}` — xem `lib/audio.ts` de biet vi sao.
 */

import { useEffect, useRef, useState } from "react";
import { audioFileName, resolveAudio, type PlayableAudio } from "@/lib/audio";
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
  const [audio, setAudio] = useState<PlayableAudio | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const revoke = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;

    resolveAudio(chapterId)
      .then((resolved) => {
        if (cancelled) {
          resolved.revoke?.();
          return;
        }
        revoke.current = resolved.revoke;
        setAudio(resolved);
      })
      .catch((cause) => {
        if (!cancelled) setError(errorMessage(cause));
      });

    return () => {
      cancelled = true;
      revoke.current?.();
      revoke.current = null;
    };
  }, [chapterId]);

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
          {audio ? (
            <span className="hint">{formatBytes(audio.sizeBytes)}</span>
          ) : null}
        </div>
      ) : null}

      {audio ? (
        <>
          {/* Audio do chinh nguoi dung tao tu van ban ho nhap; "phu de" chinh
              la van ban do va da hien ngay tren trang, nen khong can track. */}
          <audio
            controls
            preload="metadata"
            src={audio.playUrl}
            aria-label={`Trình phát audio: ${title}`}
            onCanPlay={() => setReady(true)}
            onError={() =>
              setError("Không phát được audio. File có thể đã hết hạn liên kết.")
            }
          >
            Trình duyệt của bạn không hỗ trợ phát audio.
          </audio>

          <div className="row row-spread">
            <span className="hint" role="status">
              {ready ? "Sẵn sàng phát" : "Đang chuẩn bị…"}
            </span>
            <a
              className="btn btn-sm"
              href={audio.downloadUrl}
              download={audioFileName(title)}
            >
              <span aria-hidden="true">⬇</span> Tải MP3
            </a>
          </div>
        </>
      ) : (
        <div className="row" role="status">
          <span className="spinner" aria-hidden="true" />
          <span className="hint">Đang lấy liên kết audio…</span>
        </div>
      )}
    </div>
  );
}
