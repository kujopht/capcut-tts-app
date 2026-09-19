"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { musicStore } from "@/lib/musicStore";

export function SoundwaveMini({ color }: { color?: string }) {
  const { isPlaying, currentTrack, soundwaveStyle } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  const styleNames: Record<string, string> = {
    "bottom-spectrum": "Dải sóng dưới đáy",
    "trap-nation": "Trap Nation Avatar",
    "bottom-wave": "Sóng lượn Neon",
  };

  const barColor = color || currentTrack.color || "rgba(56, 189, 248, 1)";

  return (
    <span
      className={`nav-soundwave ${isPlaying ? "is-playing" : ""}`}
      title={
        isPlaying
          ? `Đang phát: ${currentTrack.title} • Kiểu sóng: ${styleNames[soundwaveStyle]} (Bấm để đổi kiểu sóng)`
          : "Âm nhạc"
      }
      aria-label="Soundwave beat"
      style={{
        ["--wave-color" as string]: barColor,
        cursor: isPlaying ? "pointer" : "default",
      }}
      onClick={(e) => {
        if (isPlaying) {
          e.preventDefault();
          e.stopPropagation();
          musicStore.cycleSoundwaveStyle();
        }
      }}
    >
      <span className="wave-bar bar-1" />
      <span className="wave-bar bar-2" />
      <span className="wave-bar bar-3" />
      <span className="wave-bar bar-4" />
      <span className="wave-bar bar-5" />
    </span>
  );
}

export function SoundwavePlayer({
  height = 48,
  barsCount = 42,
}: {
  height?: number;
  barsCount?: number;
}) {
  const { isPlaying, currentTrack } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reqRef = useRef<number | null>(null);
  const barHeightsRef = useRef<Float32Array | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!barHeightsRef.current || barHeightsRef.current.length !== barsCount) {
      barHeightsRef.current = new Float32Array(barsCount);
    }
    const barHeights = barHeightsRef.current;

    const data = new Uint8Array(64);
    let frame = 0;

    const update = () => {
      frame++;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      if (isPlaying) {
        musicStore.getFrequencyData(data);
      } else {
        data.fill(0);
      }

      const barWidth = (w - (barsCount - 1) * 3) / barsCount;
      const trackColor = currentTrack.color || "rgba(245, 158, 11, 1)";

      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, trackColor);
      grad.addColorStop(1, "rgba(56, 189, 248, 0.9)");

      ctx.fillStyle = isPlaying ? grad : "rgba(255, 255, 255, 0.15)";
      ctx.beginPath();

      for (let i = 0; i < barsCount; i++) {
        const x = i * (barWidth + 3);
        // Trai deu tan so am nhac hoat dong (bins 0-24) tren toan bo 34 cot
        const normX = i / (barsCount - 1);
        const bin = Math.min(24, Math.floor(Math.pow(normX, 1.15) * 22));
        const raw = isPlaying ? data[bin] || 0 : 0;

        // Song gon tho nhe nhang (dam bao visualizer luon co nhip tho sinh dong)
        const ripple = isPlaying
          ? Math.sin(frame * 0.12 + i * 0.28) * 3 + Math.cos(frame * 0.08 - i * 0.18) * 2
          : 0;

        const dynamicH = isPlaying ? (raw / 255) * (h - 6) + ripple : 0;
        const targetH = Math.max(3.5, dynamicH);

        // Dan hoi Attack & Decay nhay nhang
        if (targetH > barHeights[i]) {
          barHeights[i] = targetH;
        } else {
          barHeights[i] = barHeights[i] * 0.76 + targetH * 0.24;
        }

        const barH = isPlaying ? barHeights[i] : 3.5;
        const y = (h - barH) / 2;
        ctx.roundRect(x, y, barWidth, barH, 2);
      }
      ctx.fill();

      if (isPlaying) {
        reqRef.current = requestAnimationFrame(update);
      }
    };

    if (isPlaying) {
      reqRef.current = requestAnimationFrame(update);
    } else {
      update();
    }

    return () => {
      if (reqRef.current) cancelAnimationFrame(reqRef.current);
    };
  }, [isPlaying, currentTrack, barsCount, height]);

  return (
    <div style={{ width: "100%", height, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <canvas
        ref={canvasRef}
        width={720}
        height={height}
        style={{ width: "100%", height: `${height}px`, display: "block" }}
      />
    </div>
  );
}

export function SoundwaveStylePicker() {
  const { soundwaveStyle } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  const styles: { id: "bottom-spectrum" | "trap-nation" | "bottom-wave"; label: string; icon: string; desc: string }[] = [
    { id: "bottom-spectrum", label: "Dải sóng dưới đáy (Khuyên dùng)", icon: "📊", desc: "64 vạch phổ âm thanh đập rực rỡ dưới đáy khung dock" },
    { id: "trap-nation", label: "Trap Nation Avatar", icon: "🔥", desc: "Sóng âm tỏa mượt mà quanh viền khung như video nhạc EDM" },
    { id: "bottom-wave", label: "Sóng lượn Neon", icon: "🌊", desc: "Dải sóng lượn mượt mà mềm mại dưới đáy khung" },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        padding: "8px 12px",
        background: "rgba(255, 255, 255, 0.03)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderRadius: "var(--r2)",
        marginTop: 6,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 14 }}>🎛️</span>
        <span className="hint" style={{ fontSize: "0.8rem", fontWeight: 600 }}>
          Kiểu sóng âm ngoài viền thanh tác vụ:
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {styles.map((s) => {
          const isActive = soundwaveStyle === s.id;
          return (
            <button
              key={s.id}
              type="button"
              className={`btn btn-xs ${isActive ? "btn-primary" : "btn-ghost"}`}
              onClick={() => musicStore.setSoundwaveStyle(s.id)}
              title={s.desc}
              style={{
                borderRadius: "var(--r2)",
                fontSize: "0.78rem",
                padding: "3px 9px",
                cursor: "pointer",
              }}
            >
              <span aria-hidden="true" style={{ marginRight: 3 }}>
                {s.icon}
              </span>
              {s.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

