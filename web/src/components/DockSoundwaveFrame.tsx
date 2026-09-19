"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { musicStore } from "@/lib/musicStore";

interface TrackPalette {
  primary: string;
  secondary: string;
  accent: string;
  base: string;
  tip: string;
  glow: string;
  flare: string;
}

function getTrackPalette(baseColor?: string): TrackPalette {
  const c = (baseColor || "").toLowerCase();
  if (
    c.includes("06b6d4") ||
    c.includes("38bdf8") ||
    c.includes("cyan") ||
    c.includes("sky") ||
    c.includes("60a5fa")
  ) {
    return {
      primary: "#00f0ff",      // Laser Cyan
      secondary: "#38bdf8",    // Electric Sky
      accent: "#818cf8",       // Electric Indigo
      base: "rgba(0, 205, 255, 0.95)",
      tip: "#cffafe",
      glow: "rgba(0, 240, 255, 0.85)",
      flare: "rgba(129, 140, 248, 0.65)",
    };
  }
  if (
    c.includes("f59e0b") ||
    c.includes("amber") ||
    c.includes("yellow") ||
    c.includes("orange")
  ) {
    return {
      primary: "#ffb703",      // Pure Gold
      secondary: "#fb8500",    // Blaze Orange
      accent: "#ef4444",       // Crimson
      base: "rgba(245, 158, 11, 0.95)",
      tip: "#fef3c7",
      glow: "rgba(255, 183, 3, 0.85)",
      flare: "rgba(249, 115, 22, 0.65)",
    };
  }
  if (
    c.includes("a78bfa") ||
    c.includes("a855f7") ||
    c.includes("purple") ||
    c.includes("violet")
  ) {
    return {
      primary: "#c084fc",      // Electric Orchid
      secondary: "#e879f9",    // Fuchsia
      accent: "#38bdf8",       // Sky highlight
      base: "rgba(168, 85, 247, 0.95)",
      tip: "#f5d0fe",
      glow: "rgba(192, 132, 252, 0.85)",
      flare: "rgba(232, 121, 249, 0.65)",
    };
  }
  return {
    primary: "#00f0ff",
    secondary: "#38bdf8",
    accent: "#a855f7",
    base: "rgba(0, 210, 255, 0.95)",
    tip: "#cffafe",
    glow: "rgba(0, 240, 255, 0.85)",
    flare: "rgba(168, 85, 247, 0.65)",
  };
}

interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  decay: number;
  color: string;
}

export function DockSoundwaveFrame() {
  const { isPlaying, currentTrack, soundwaveStyle } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const reqRef = useRef<number | null>(null);
  const lastGlowRef = useRef<number>(0);

  // Cached dimensions — measured ONLY on resize, NEVER inside the 60fps render loop
  const dimsRef = useRef<{ w: number; h: number; dpr: number }>({ w: 0, h: 0, dpr: 1 });

  // Sync refs so animation loop never closes over stale state or gets abruptly killed
  const isPlayingRef = useRef(isPlaying);
  const currentTrackRef = useRef(currentTrack);
  const soundwaveStyleRef = useRef(soundwaveStyle);

  const isLoopRunningRef = useRef(false);
  const barHeightsRef = useRef<Float32Array | null>(null);
  const sparksRef = useRef<Spark[]>([]);
  const kickCooldownRef = useRef<number>(0);
  const topHeightsRef = useRef<Float32Array | null>(null);
  const bottomHeightsRef = useRef<Float32Array | null>(null);
  const barRisingStatesRef = useRef<Uint8Array | null>(null);
  const bottomRisingStatesRef = useRef<Uint8Array | null>(null);
  const loopStarterRef = useRef<(() => void) | null>(null);

  // Update refs & trigger loop on playback state changes
  useEffect(() => {
    isPlayingRef.current = isPlaying;
    currentTrackRef.current = currentTrack;
    soundwaveStyleRef.current = soundwaveStyle;

    const parent = containerRef.current?.parentElement;

    if (isPlaying) {
      if (parent) {
        parent.dataset.musicPlaying = "true";
        parent.style.setProperty(
          "--music-wave-color",
          currentTrack.color || "rgba(56, 189, 248, 1)",
        );
      }
      loopStarterRef.current?.();
    }
  }, [isPlaying, currentTrack, soundwaveStyle]);

  // Main canvas setup & persistent render loop (never abruptly torn down on pause!)
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const parent = container.parentElement;
    if (!parent) return;

    // Integrated directly inside parent (.site-header) with zero outer overhang
    let resizeTimer: ReturnType<typeof setTimeout> | null = null;

    const applyMeasure = () => {
      const rect = parent.getBoundingClientRect();
      const dpr = typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 2) : 1;
      const totalW = rect.width;
      const totalH = rect.height;

      dimsRef.current = { w: totalW, h: totalH, dpr };

      const targetW = Math.round(totalW * dpr);
      const targetH = Math.round(totalH * dpr);

      if (canvas.width !== targetW || canvas.height !== targetH) {
        canvas.width = targetW;
        canvas.height = targetH;
        canvas.style.width = `${totalW}px`;
        canvas.style.height = `${totalH}px`;
      }
    };

    applyMeasure();

    // Debounce during CSS transitions to avoid reallocating canvas.width on every micro-frame
    const handleResize = () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        applyMeasure();
      }, 70);
    };

    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(handleResize) : null;
    ro?.observe(parent);
    window.addEventListener("resize", handleResize, { passive: true });

    // When parent's width transition completes, immediately ensure exact pixel-perfect measure
    const handleTransitionEnd = (e: TransitionEvent) => {
      if (e.target === parent && (e.propertyName === "width" || e.propertyName === "max-width")) {
        applyMeasure();
      }
    };
    parent.addEventListener("transitionend", handleTransitionEnd);

    // 128 bins (from fftSize: 256) for rich bass and clean frequency separation
    const freqData = new Uint8Array(128);
    let frame = 0;
    let prevBass = 0;
    let avgBass = 0.2;
    let bassFlash = 0;
    let ampEnvelope = 0;
    let playHoldFrames = 0;

    const draw = () => {
      const { w: dockW, h: dockH, dpr } = dimsRef.current;
      const ctx = canvas.getContext("2d");

      if (!ctx || dockW <= 0 || dockH <= 0) {
        reqRef.current = requestAnimationFrame(draw);
        return;
      }

      frame++;
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, dockW, dockH);

      const playing = isPlayingRef.current;
      const track = currentTrackRef.current;
      const style = soundwaveStyleRef.current;

      // Choreographed appearance:
      // Khi bật nhạc: Giữ delay 14 frames (~230ms) để dock mở rộng mượt mà trước, sau đó sóng mới nhẹ nhàng vươn lên
      // Khi tắt nhạc: Hạ dần độ cao mềm mại (khoảng 350ms) chìm êm xuống sàn dock
      if (playing) {
        if (playHoldFrames < 14) {
          playHoldFrames++;
        }
      } else {
        playHoldFrames = 0;
      }

      const targetAmp = playing && playHoldFrames >= 14 ? 1 : 0;
      ampEnvelope += (targetAmp - ampEnvelope) * (playing ? 0.05 : 0.065);

      // When stopped and decay is complete, clean up and sleep animation loop
      if (!playing && ampEnvelope < 0.005) {
        ctx.restore();
        parent.style.removeProperty("--music-beat-glow");
        lastGlowRef.current = 0;
        isLoopRunningRef.current = false;
        if (reqRef.current) {
          cancelAnimationFrame(reqRef.current);
          reqRef.current = null;
        }
        return;
      }

      if (playing) {
        musicStore.getFrequencyData(freqData);
      } else {
        // Tắt nhạc: Giảm dần dữ liệu tần số mềm mại để cột sóng chìm từ từ xuống thay vì biến mất tức thì
        for (let k = 0; k < freqData.length; k++) {
          freqData[k] = Math.floor(freqData[k] * 0.94);
        }
      }

      // Sub-bass & Kick isolation (tập trung dải trầm bins 1, 2: ~40Hz đến 90Hz)
      const subBassRaw = ((freqData[1] || 0) * 0.65 + (freqData[2] || 0) * 0.35) / 255;
      const subBass = subBassRaw * ampEnvelope;

      avgBass = avgBass * 0.92 + subBass * 0.08;
      const bassDelta = subBass - prevBass;
      prevBass = subBass;

      if (kickCooldownRef.current > 0) {
        kickCooldownRef.current--;
      }

      // Đập chuẩn nhịp: Chỉ trigger khi có bước nhảy delta mạnh, vượt ngưỡng trung bình và hết cooldown
      const isKick = kickCooldownRef.current === 0 && bassDelta > 0.035 && subBass > avgBass * 1.12 && subBass > 0.28;

      const waveColor = track.color || "rgba(56, 189, 248, 1)";
      const palette = getTrackPalette(waveColor);
      const R = 14;

      if (isKick) {
        kickCooldownRef.current = 10; // Khóa nhịp ~165ms (khớp với tempo nhạc 128-140 BPM, không nhảy loạn xạ)
        bassFlash = 1.0;
      } else {
        bassFlash *= 0.86; // Snappy musical punch decay (~120ms)
      }

      // DOCK AMBIENT GLOW (chỉ kích hoạt khi sóng đã nở đủ lớn, không kích hoạt sớm lúc dock đang dãn rộng)
      if (ampEnvelope > 0.15) {
        const beatGlow = Math.min(1, (subBass * 0.72 + bassFlash * 0.6) * ampEnvelope);
        if (Math.abs(beatGlow - lastGlowRef.current) > 0.02) {
          lastGlowRef.current = beatGlow;
          parent.style.setProperty("--music-beat-glow", beatGlow.toFixed(2));
        }
      } else if (lastGlowRef.current > 0) {
        lastGlowRef.current = 0;
        parent.style.removeProperty("--music-beat-glow");
      }

      // =========================================================================
      // STYLE 1: "bottom-spectrum" (Thanh phổ đập dứt khoát, neon rực rỡ, hạt spark bay)
      // =========================================================================
      if (style === "bottom-spectrum") {
        const marginX = R + 8;
        const availableW = dockW - marginX * 2;
        const step = 4.2;
        const barWidth = 2.8;
        const barCount = Math.max(26, Math.floor(availableW / step));
        const actualGap = availableW / (barCount - 1);
        const baselineY = dockH - 1.5;
        // Chiều cao cực đại tối ưu (13px) giữ dải sóng nằm gọn ở sàn dock, không bao giờ che lấn vào chữ lyric
        const maxH = Math.min(dockH * 0.27, 13);

        if (!barHeightsRef.current || barHeightsRef.current.length < barCount) {
          barHeightsRef.current = new Float32Array(barCount + 20);
        }
        const barHeights = barHeightsRef.current;

        // Step 1: Lấy mẫu tần số liên tục (Logarithmic mapping) từ tâm ra hai cánh
        const rawArray = new Float32Array(barCount);
        for (let i = 0; i < barCount; i++) {
          const distNorm = Math.abs(i - (barCount - 1) / 2) / ((barCount - 1) / 2); // 0 ở tâm, 1 ở hai mép

          // Tâm: Sub-bass & Kick (bins 1-3); Giữa: Vocal & Synth (bins 4-20); Rìa: Hi-hats & Treble (bins 20-50)
          const binPos = Math.pow(distNorm, 1.4) * 45 + 1;
          const b0 = Math.floor(binPos);
          const b1 = Math.min(127, b0 + 1);
          const frac = binPos - b0;
          const freqVal = ((freqData[b0] || 0) * (1 - frac) + (freqData[b1] || 0) * frac) / 255;

          // Vuốt cong mép ngoài hai đầu thanh dock
          const edgeFade = Math.sin((i / (barCount - 1)) * Math.PI);
          const windowFactor = Math.pow(edgeFade, 0.65);

          // Cú đập Bass Kick đánh cao bốc lửa ở dải trầm trung tâm
          const centerPunch = Math.max(0, 1 - distNorm * 3.2) * (bassFlash * 0.85);

          const hNorm = Math.min(1, freqVal * 1.25 + centerPunch);
          rawArray[i] = hNorm * maxH * windowFactor * ampEnvelope;
        }

        // Step 2: Bộ lọc làm mượt Gaussian 3 điểm (Biến dàn sóng thành các dải âm nhạc hữu cơ)
        const smoothedArray = new Float32Array(barCount);
        for (let i = 0; i < barCount; i++) {
          const prev = rawArray[Math.max(0, i - 1)];
          const curr = rawArray[i];
          const next = rawArray[Math.min(barCount - 1, i + 1)];
          smoothedArray[i] = prev * 0.22 + curr * 0.56 + next * 0.22;
        }

        // 1. Đường ray laser neon mỏng nhẹ đáy dock
        const lineGrad = ctx.createLinearGradient(marginX, baselineY, marginX + availableW, baselineY);
        lineGrad.addColorStop(0, "rgba(0, 240, 255, 0)");
        lineGrad.addColorStop(0.12, palette.base);
        lineGrad.addColorStop(0.5, bassFlash > 0.2 ? "#ffffff" : palette.primary);
        lineGrad.addColorStop(0.88, palette.base);
        lineGrad.addColorStop(1, "rgba(0, 240, 255, 0)");

        ctx.save();
        ctx.strokeStyle = lineGrad;
        ctx.lineWidth = (1.4 + bassFlash * 1.6) * ampEnvelope;
        ctx.shadowColor = palette.glow;
        ctx.shadowBlur = (7 + bassFlash * 14) * ampEnvelope;
        ctx.globalAlpha = Math.min(1, (0.88 + bassFlash * 0.12) * ampEnvelope);
        ctx.beginPath();
        ctx.moveTo(marginX, baselineY);
        ctx.lineTo(marginX + availableW, baselineY);
        ctx.stroke();
        ctx.restore();

        // 2. THANH SÓNG NEON ĐẬM MÀU (Lên cao rực rỡ, ngọn bọc sáng)
        const barGrad = ctx.createLinearGradient(0, baselineY, 0, baselineY - maxH);
        barGrad.addColorStop(0, palette.base);
        barGrad.addColorStop(0.3, palette.primary);
        barGrad.addColorStop(0.68, palette.secondary);
        barGrad.addColorStop(0.86, palette.tip);
        barGrad.addColorStop(1, "#ffffff");

        ctx.save();
        ctx.fillStyle = barGrad;
        ctx.shadowColor = palette.glow;
        ctx.shadowBlur = (6 + bassFlash * 12) * ampEnvelope;
        ctx.globalAlpha = 0.96 * ampEnvelope;
        ctx.beginPath();

        if (!barRisingStatesRef.current || barRisingStatesRef.current.length < barCount) {
          barRisingStatesRef.current = new Uint8Array(barCount + 20);
        }
        const risingStates = barRisingStatesRef.current;

        const sparks = sparksRef.current;
        let strikesThisFrame = 0;

        for (let i = 0; i < barCount; i++) {
          const x = marginX + i * actualGap;
          const prevH = barHeights[i];
          const targetH = Math.max(1.8 * ampEnvelope, smoothedArray[i]);
          const rise = targetH - prevH;

          // Phản hồi VU meter đầm chắc, nảy cao dứt khoát:
          if (targetH > barHeights[i]) {
            barHeights[i] = barHeights[i] * 0.18 + targetH * 0.82;
          } else {
            barHeights[i] = barHeights[i] * 0.76 + targetH * 0.24;
          }

          const h = barHeights[i];
          const radius = Math.min(barWidth / 2, h / 2);

          if (h > 0) {
            if (typeof ctx.roundRect === "function") {
              ctx.roundRect(x - barWidth / 2, baselineY - h, barWidth, h, [radius, radius, 0, 0]);
            } else {
              ctx.rect(x - barWidth / 2, baselineY - h, barWidth, h);
            }
          }

          // KHI 1 CỘT BẮT ĐẦU CHUYỂN ĐỘNG / BẮT ĐẦU 1 CHU KỲ ĐẬP MỚI -> DROP 1 SPARK
          const wasRising = risingStates ? risingStates[i] : 0;
          const isStartingMotion =
            ampEnvelope > 0.18 &&
            wasRising === 0 &&
            targetH > 2.6 &&
            (rise > 0.8 || (isKick && rise > 0.5));

          if (isStartingMotion) {
            if (risingStates) risingStates[i] = 1; // Đánh dấu cột đã bước vào chu kỳ vọt lên

            if (strikesThisFrame < 6 && sparks.length < 50) {
              strikesThisFrame++;
              const spX = x + (Math.random() - 0.5) * (barWidth * 0.7);
              const spY = baselineY - prevH - 1;
              const launchSpeed = 1.3 + Math.min(2.2, rise * 0.35);
              const colorRoll = Math.random();

              sparks.push({
                x: spX,
                y: spY,
                vx: (Math.random() - 0.5) * (0.8 + Math.min(0.8, rise * 0.15)),
                vy: -launchSpeed, // Nhả (drop) 1 spark bay vút lên ngay khi cột bắt đầu chuyển động!
                size: 0.55 + Math.random() * 0.75, // Hạt bé li ti (0.55px - 1.3px)
                alpha: 1.0,
                decay: 0.016 + Math.random() * 0.014,
                color: colorRoll > 0.6 ? "#ffffff" : colorRoll > 0.3 ? palette.tip : palette.primary,
              });

              // Nếu chu kỳ này đập cực mạnh: Thả thêm 1 tia sáng phụ lấp lánh
              if (rise > 3.2 && strikesThisFrame < 6 && sparks.length < 50) {
                strikesThisFrame++;
                sparks.push({
                  x: x + (Math.random() - 0.5) * (barWidth * 0.8),
                  y: baselineY - prevH - 1,
                  vx: (Math.random() - 0.5) * 1.2,
                  vy: -(launchSpeed * 0.85 + Math.random() * 0.4),
                  size: 0.5 + Math.random() * 0.65,
                  alpha: 0.92,
                  decay: 0.018 + Math.random() * 0.014,
                  color: Math.random() > 0.4 ? "#ffffff" : palette.secondary,
                });
              }
            }
          } else if (targetH < prevH - 0.3 || targetH <= 2.2) {
            // Cột bắt đầu đi xuống hoặc chạm đáy: Reset trạng thái để sẵn sàng cho chu kỳ đập mới!
            if (risingStates) risingStates[i] = 0;
          }
        }
        ctx.fill();
        ctx.restore();

        // 3. HIỆU ỨNG BỌC TRẮNG KHI BEAT ĐÁNH CAO (White-Hot Laser Crest & Floating Peak Crowns)
        if (ampEnvelope > 0.18) {
          ctx.save();
          ctx.fillStyle = "#ffffff";
          ctx.shadowColor = "#ffffff";
          ctx.shadowBlur = (5 + bassFlash * 12) * ampEnvelope;
          ctx.globalAlpha = Math.min(1, (0.82 + bassFlash * 0.18) * ampEnvelope);
          ctx.beginPath();

          // A. Lớp bọc trắng đỉnh cho các cột sóng đánh cao (từ 4.5px trở lên)
          for (let i = 0; i < barCount; i++) {
            const h = barHeights[i];
            if (h > 4.5) {
              const x = marginX + i * actualGap;
              const capH = Math.min(2.4, Math.max(1.4, h * 0.22));
              const capRadius = Math.min(barWidth / 2, capH / 2);
              if (typeof ctx.roundRect === "function") {
                ctx.roundRect(x - barWidth / 2, baselineY - h, barWidth, capH, [capRadius, capRadius, 0, 0]);
              } else {
                ctx.rect(x - barWidth / 2, baselineY - h, barWidth, capH);
              }
            }
          }
          ctx.fill();

          // B. Mũ trắng phát quang lơ lửng trên các đỉnh sóng cao nổi bật (Floating Peak Crowns)
          ctx.beginPath();
          for (let i = 1; i < barCount - 1; i++) {
            const h = barHeights[i];
            if (h > 6.8 && h >= (barHeights[i - 1] || 0) && h >= (barHeights[i + 1] || 0)) {
              const x = marginX + i * actualGap;
              const peakY = baselineY - h - 1.2;
              if (typeof ctx.roundRect === "function") {
                ctx.roundRect(x - barWidth / 2, peakY, barWidth, 1.4, [1, 1, 1, 1]);
              } else {
                ctx.rect(x - barWidth / 2, peakY, barWidth, 1.4);
              }
            }
          }
          ctx.fill();
          ctx.restore();
        }
      }

      // =========================================================================
      // STYLE 2: "trap-nation" (Gọn gàng trên & dưới, giữ khoảng trống sạch ở giữa)
      // =========================================================================
      else if (style === "trap-nation") {
        const marginX = R + 8;
        const availableW = dockW - marginX * 2;
        const step = 4.2;
        const barWidth = 2.8;
        const barCount = Math.max(26, Math.floor(availableW / step));
        const actualGap = availableW / (barCount - 1);
        const maxSpike = Math.min(dockH * 0.20, 10);

        if (!topHeightsRef.current || topHeightsRef.current.length < barCount) {
          topHeightsRef.current = new Float32Array(barCount + 20);
          bottomHeightsRef.current = new Float32Array(barCount + 20);
        }
        const topHeights = topHeightsRef.current;
        const bottomHeights = bottomHeightsRef.current!;

        // Đường ray neon viền trên và dưới
        ctx.save();
        ctx.strokeStyle = palette.primary;
        ctx.shadowColor = palette.glow;
        ctx.shadowBlur = (6 + bassFlash * 12) * ampEnvelope;
        ctx.lineWidth = (1.3 + bassFlash * 1.0) * ampEnvelope;
        ctx.globalAlpha = Math.min(0.9, (0.6 + bassFlash * 0.35) * ampEnvelope);
        ctx.beginPath();
        ctx.moveTo(marginX, 1);
        ctx.lineTo(marginX + availableW, 1);
        ctx.moveTo(marginX, dockH - 1.5);
        ctx.lineTo(marginX + availableW, dockH - 1.5);
        ctx.stroke();
        ctx.restore();

        const topGrad = ctx.createLinearGradient(0, 0, 0, maxSpike);
        topGrad.addColorStop(0, bassFlash > 0.2 ? "#ffffff" : palette.tip);
        topGrad.addColorStop(0.3, palette.primary);
        topGrad.addColorStop(1, palette.base);

        const bottomGrad = ctx.createLinearGradient(0, dockH, 0, dockH - maxSpike);
        bottomGrad.addColorStop(0, bassFlash > 0.2 ? "#ffffff" : palette.tip);
        bottomGrad.addColorStop(0.3, palette.primary);
        bottomGrad.addColorStop(1, palette.base);

        // Mẫu tần số mượt mà
        const rawTop = new Float32Array(barCount);
        const rawBot = new Float32Array(barCount);
        for (let i = 0; i < barCount; i++) {
          const distNorm = Math.abs(i - (barCount - 1) / 2) / ((barCount - 1) / 2);
          const binPos = Math.pow(distNorm, 1.35) * 45 + 1;
          const b0 = Math.floor(binPos);
          const b1 = Math.min(127, b0 + 1);
          const frac = binPos - b0;
          const freqVal = ((freqData[b0] || 0) * (1 - frac) + (freqData[b1] || 0) * frac) / 255;
          const edgeFade = Math.sin((i / (barCount - 1)) * Math.PI);
          const windowFactor = Math.pow(edgeFade, 0.65);
          const centerPunch = Math.max(0, 1 - distNorm * 3.5) * (bassFlash * 0.5);

          const hNorm = Math.min(1, freqVal * 1.15 + centerPunch);
          const h = hNorm * maxSpike * windowFactor * ampEnvelope;
          rawTop[i] = h;
          rawBot[i] = h;
        }

        // Smooth top bars
        ctx.save();
        ctx.fillStyle = topGrad;
        ctx.shadowColor = palette.glow;
        ctx.shadowBlur = (6 + bassFlash * 12) * ampEnvelope;
        ctx.globalAlpha = 0.94 * ampEnvelope;
        ctx.beginPath();
        for (let i = 0; i < barCount; i++) {
          const x = marginX + i * actualGap;
          const prev = rawTop[Math.max(0, i - 1)];
          const curr = rawTop[i];
          const next = rawTop[Math.min(barCount - 1, i + 1)];
          const targetH = Math.max(1.5 * ampEnvelope, prev * 0.22 + curr * 0.56 + next * 0.22);

          if (targetH > topHeights[i]) {
            topHeights[i] = topHeights[i] * 0.2 + targetH * 0.8;
          } else {
            topHeights[i] = topHeights[i] * 0.75 + targetH * 0.25;
          }
          const h = topHeights[i];
          const radius = Math.min(barWidth / 2, h / 2);
          if (h > 0) {
            if (typeof ctx.roundRect === "function") {
              ctx.roundRect(x - barWidth / 2, 1, barWidth, h, [0, 0, radius, radius]);
            } else {
              ctx.rect(x - barWidth / 2, 1, barWidth, h);
            }
          }
        }
        ctx.fill();
        ctx.restore();

        // Smooth bottom bars
        ctx.save();
        ctx.fillStyle = bottomGrad;
        ctx.shadowColor = palette.glow;
        ctx.shadowBlur = (6 + bassFlash * 12) * ampEnvelope;
        ctx.globalAlpha = 0.94 * ampEnvelope;
        ctx.beginPath();
        if (!bottomRisingStatesRef.current || bottomRisingStatesRef.current.length < barCount) {
          bottomRisingStatesRef.current = new Uint8Array(barCount + 20);
        }
        const bRisingStates = bottomRisingStatesRef.current;

        const sparks = sparksRef.current;
        let strikesThisFrame = 0;

        for (let i = 0; i < barCount; i++) {
          const x = marginX + i * actualGap;
          const prev = rawBot[Math.max(0, i - 1)];
          const curr = rawBot[i];
          const next = rawBot[Math.min(barCount - 1, i + 1)];
          const prevH = bottomHeights[i];
          const targetH = Math.max(1.5 * ampEnvelope, prev * 0.22 + curr * 0.56 + next * 0.22);
          const rise = targetH - prevH;

          if (targetH > bottomHeights[i]) {
            bottomHeights[i] = bottomHeights[i] * 0.2 + targetH * 0.8;
          } else {
            bottomHeights[i] = bottomHeights[i] * 0.75 + targetH * 0.25;
          }
          const h = bottomHeights[i];
          const radius = Math.min(barWidth / 2, h / 2);
          if (h > 0) {
            if (typeof ctx.roundRect === "function") {
              ctx.roundRect(x - barWidth / 2, dockH - 1.5 - h, barWidth, h, [radius, radius, 0, 0]);
            } else {
              ctx.rect(x - barWidth / 2, dockH - 1.5 - h, barWidth, h);
            }
          }

          // KHI CỘT BẮT ĐẦU CHUYỂN ĐỘNG Ở TRAP-NATION -> DROP 1 SPARK
          const wasRising = bRisingStates ? bRisingStates[i] : 0;
          const isStartingMotion =
            ampEnvelope > 0.18 &&
            wasRising === 0 &&
            targetH > 2.4 &&
            (rise > 0.8 || (isKick && rise > 0.5));

          if (isStartingMotion) {
            if (bRisingStates) bRisingStates[i] = 1;

            if (strikesThisFrame < 6 && sparks.length < 50) {
              strikesThisFrame++;
              const spX = x + (Math.random() - 0.5) * (barWidth * 0.7);
              const spY = dockH - 1.5 - prevH - 1;
              const launchSpeed = 1.3 + Math.min(2.0, rise * 0.35);
              const colorRoll = Math.random();

              sparks.push({
                x: spX,
                y: spY,
                vx: (Math.random() - 0.5) * (0.8 + Math.min(0.8, rise * 0.15)),
                vy: -launchSpeed,
                size: 0.55 + Math.random() * 0.75,
                alpha: 1.0,
                decay: 0.016 + Math.random() * 0.014,
                color: colorRoll > 0.6 ? "#ffffff" : colorRoll > 0.3 ? palette.tip : palette.primary,
              });
            }
          } else if (targetH < prevH - 0.3 || targetH <= 2.0) {
            if (bRisingStates) bRisingStates[i] = 0;
          }
        }
        ctx.fill();
        ctx.restore();

        // Hiệu ứng bọc trắng đỉnh sóng trap-nation
        if (ampEnvelope > 0.18) {
          ctx.save();
          ctx.fillStyle = "#ffffff";
          ctx.shadowColor = "#ffffff";
          ctx.shadowBlur = (5 + bassFlash * 12) * ampEnvelope;
          ctx.globalAlpha = Math.min(1, (0.82 + bassFlash * 0.18) * ampEnvelope);
          ctx.beginPath();
          for (let i = 0; i < barCount; i++) {
            const h = bottomHeights[i];
            if (h > 4) {
              const x = marginX + i * actualGap;
              const capH = Math.min(2.8, Math.max(1.6, h * 0.25));
              const capRadius = Math.min(barWidth / 2, capH / 2);
              if (typeof ctx.roundRect === "function") {
                ctx.roundRect(x - barWidth / 2, dockH - 1.5 - h, barWidth, capH, [capRadius, capRadius, 0, 0]);
              } else {
                ctx.rect(x - barWidth / 2, dockH - 1.5 - h, barWidth, capH);
              }
            }
          }
          ctx.fill();
          ctx.restore();
        }
      }

      // =========================================================================
      // STYLE 3: "bottom-wave" (Dải sóng lụa mượt mà uốn lượn đáy Dock)
      // =========================================================================
      else if (style === "bottom-wave") {
        const startX = R + 8;
        const endX = dockW - R - 8;
        const baselineY = dockH - 4;
        const ptsCount = 48;
        const stepX = (endX - startX) / (ptsCount - 1);

        ctx.save();
        ctx.beginPath();
        for (let i = 0; i < ptsCount; i++) {
          const x = startX + i * stepX;
          const norm = i / (ptsCount - 1);
          const distNorm = Math.abs(norm - 0.5) * 2;
          const binPos = Math.pow(distNorm, 1.35) * 45 + 1;
          const b0 = Math.floor(binPos);
          const b1 = Math.min(127, b0 + 1);
          const frac = binPos - b0;
          const freqVal = ((freqData[b0] || 0) * (1 - frac) + (freqData[b1] || 0) * frac) / 255;

          const edgeFade = Math.sin(norm * Math.PI);
          const windowFactor = Math.pow(edgeFade, 0.7);
          const centerPunch = Math.max(0, 1 - distNorm * 3) * (bassFlash * 0.55);

          const waveAmp = (freqVal * 10 + centerPunch * 6) * windowFactor * ampEnvelope;
          const y = baselineY - Math.max(0.5, waveAmp);

          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }

        ctx.strokeStyle = palette.primary;
        ctx.shadowColor = palette.glow;
        ctx.shadowBlur = (8 + bassFlash * 16) * ampEnvelope;
        ctx.lineWidth = (2.2 + bassFlash * 1.5) * ampEnvelope;
        ctx.globalAlpha = 0.92 * ampEnvelope;
        ctx.stroke();

        ctx.strokeStyle = bassFlash > 0.2 ? "#ffffff" : palette.tip;
        ctx.lineWidth = 1.0 * ampEnvelope;
        ctx.globalAlpha = 0.95 * ampEnvelope;
        ctx.stroke();
        ctx.restore();

        // 3. TẠO HẠT SPARK CHO BOTTOM-WAVE KHI SÓNG CUỘN ĐÁNH LÊN
        const sparks = sparksRef.current;
        if (sparks.length < 45 && ampEnvelope > 0.18) {
          let waveStrikes = 0;
          for (let i = 2; i < ptsCount - 2; i += 3) {
            const x = startX + i * stepX;
            const norm = i / (ptsCount - 1);
            const distNorm = Math.abs(norm - 0.5) * 2;
            const binPos = Math.pow(distNorm, 1.35) * 45 + 1;
            const b0 = Math.floor(binPos);
            const freqVal = (freqData[b0] || 0) / 255;
            const isWavePeak = freqVal > 0.38 || (isKick && freqVal > 0.22);
            if (isWavePeak && waveStrikes < 4 && sparks.length < 48) {
              waveStrikes++;
              const colorRoll = Math.random();
              sparks.push({
                x: x + (Math.random() - 0.5) * 4,
                y: baselineY - 4 - Math.random() * 3,
                vx: (Math.random() - 0.5) * 0.9,
                vy: -(1.3 + Math.random() * 1.8),
                size: 0.55 + Math.random() * 0.75,
                alpha: 1.0,
                decay: 0.016 + Math.random() * 0.014,
                color: colorRoll > 0.6 ? "#ffffff" : colorRoll > 0.3 ? palette.tip : palette.primary,
              });
            }
          }
        }
      }

      // =========================================================================
      // 4. RENDER VÀ DI CHUYỂN HẠT SPARK TINH TẾ CHO TOÀN BỘ KHUNG DOCK
      // =========================================================================
      const sparks = sparksRef.current;
      if (sparks.length > 0) {
        ctx.save();
        for (let i = sparks.length - 1; i >= 0; i--) {
          const sp = sparks[i];
          sp.x += sp.vx;
          sp.y += sp.vy;
          sp.vy += 0.04; // Trọng lực cực nhẹ tạo quỹ đạo lơ lửng bồng bềnh
          sp.alpha -= sp.decay;

          if (sp.alpha <= 0.04 || sp.y > dockH + 6 || sp.y < -20) {
            sparks.splice(i, 1);
            continue;
          }

          ctx.fillStyle = sp.color;
          ctx.shadowColor = sp.color;
          ctx.shadowBlur = 3.5 * sp.alpha;
          ctx.globalAlpha = sp.alpha * ampEnvelope;
          ctx.beginPath();
          ctx.arc(sp.x, sp.y, sp.size, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }

      ctx.restore();
      reqRef.current = requestAnimationFrame(draw);
    };

    const startLoop = () => {
      if (!isLoopRunningRef.current) {
        isLoopRunningRef.current = true;
        reqRef.current = requestAnimationFrame(draw);
      }
    };

    loopStarterRef.current = startLoop;

    if (isPlayingRef.current) {
      startLoop();
    }

    return () => {
      if (reqRef.current) {
        cancelAnimationFrame(reqRef.current);
        reqRef.current = null;
      }
      if (resizeTimer) clearTimeout(resizeTimer);
      ro?.disconnect();
      window.removeEventListener("resize", handleResize);
      parent.removeEventListener("transitionend", handleTransitionEnd);
      delete parent.dataset.musicPlaying;
      parent.style.removeProperty("--music-beat-glow");
      parent.style.removeProperty("--music-wave-color");
      lastGlowRef.current = 0;
      isLoopRunningRef.current = false;
    };
  }, []); // Persistent lifecycle: never cancels frame on pause!

  return (
    <div
      ref={containerRef}
      className={`dock-soundwave-frame ${isPlaying ? "is-active" : ""}`}
      data-style={soundwaveStyle}
      aria-hidden="true"
    >
      <canvas ref={canvasRef} className="dock-soundwave-canvas" />
    </div>
  );
}
