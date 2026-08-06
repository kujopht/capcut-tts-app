"use client";

/**
 * Trinh phat audio.
 *
 * Dung the <audio> co san cua trinh duyet - khong them thu vien nao. Da co
 * san play/pause, tua, thoi luong va am luong; phan ben tren chi bo sung
 * nhan de doc man hinh va trang thai loi bang tieng Viet.
 */

import { useEffect, useRef, useState } from "react";

interface Props {
  src: string;
  title: string;
  subtitle?: string;
}

export function AudioPlayer({ src, title, subtitle }: Props) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setError("");
    setReady(false);
  }, [src]);

  return (
    <section className="player" aria-label={`Trình phát: ${title}`}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          aria-hidden="true"
          style={{
            width: 46,
            height: 46,
            borderRadius: 12,
            background: "linear-gradient(135deg,#7c5cff,#4f8dff)",
            display: "grid",
            placeItems: "center",
            fontSize: 20,
            flexShrink: 0,
          }}
        >
          ♪
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700 }}>{title}</div>
          {subtitle ? <div className="hint">{subtitle}</div> : null}
        </div>
      </div>

      {error ? (
        <p className="alert alert-error" role="alert" style={{ marginTop: 12 }}>
          {error}
        </p>
      ) : null}

      <audio
        ref={ref}
        src={src}
        controls
        preload="metadata"
        aria-label={`Audio của ${title}`}
        onCanPlay={() => setReady(true)}
        onError={() =>
          setError(
            "Không phát được audio. File có thể chưa được tạo xong hoặc đã bị xoá.",
          )
        }
      >
        Trình duyệt của bạn không hỗ trợ phát audio.
      </audio>

      {!ready && !error ? (
        <p className="hint" style={{ marginTop: 8 }} role="status">
          Đang tải audio...
        </p>
      ) : null}
    </section>
  );
}
