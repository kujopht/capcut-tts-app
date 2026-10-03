"use client";

import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from "react";
import type { ButtonName, InputSource } from "../platform/input";

/**
 * Nút chạm: một vùng "đi" (trượt ngón để đổi trái/phải, không nhả giữa chừng) + các nút Nhảy / Chém / Pulse / Margin Step. Dùng Pointer Events với
 * `touch-action: none` nên giữ nút KHÔNG làm cuộn trang; mỗi nút theo dõi con trỏ riêng (chạm nhiều ngón được). Mọi nút ≥ 56 px.
 */
interface Props {
  input: InputSource;
  marginStep: boolean;
  onPause: () => void;
}

const POINTER_BASE = 7000;

function useHold(input: InputSource, button: ButtonName) {
  const down = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      e.preventDefault();
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        // một số trình duyệt từ chối khi con trỏ đã bị huỷ — bỏ qua
      }
      input.press(button, POINTER_BASE + e.pointerId);
    },
    [input, button],
  );
  const up = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      input.release(button, POINTER_BASE + e.pointerId);
    },
    [input, button],
  );
  return { onPointerDown: down, onPointerUp: up, onPointerCancel: up, onLostPointerCapture: up };
}

function HoldButton({ input, button, label, hint, className }: { input: InputSource; button: ButtonName; label: string; hint: string; className: string }) {
  const h = useHold(input, button);
  return (
    <button type="button" className={`isc-tb ${className}`} aria-label={hint} {...h} onContextMenu={(e) => e.preventDefault()}>
      <span aria-hidden="true">{label}</span>
    </button>
  );
}

export function TouchControls({ input, marginStep, onPause }: Props) {
  const pad = useRef<HTMLDivElement | null>(null);
  const side = useRef<-1 | 0 | 1>(0);

  const apply = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const el = pad.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dead = r.width * 0.08;
      const next: -1 | 0 | 1 = dx < -dead ? -1 : dx > dead ? 1 : 0;
      const id = POINTER_BASE + 100 + e.pointerId;
      if (next === side.current) return;
      if (side.current === -1) input.release("left", id);
      if (side.current === 1) input.release("right", id);
      side.current = next;
      if (next === -1) input.press("left", id);
      if (next === 1) input.press("right", id);
    },
    [input],
  );

  const padDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        // bỏ qua
      }
      apply(e);
    },
    [apply],
  );

  const padUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const id = POINTER_BASE + 100 + e.pointerId;
      input.release("left", id);
      input.release("right", id);
      side.current = 0;
    },
    [input],
  );

  return (
    <div className="isc-touch" data-testid="isc-touch">
      {/* Chạm dùng pointerup (không phụ thuộc `click` — bộ nhận dạng cử chỉ có thể nuốt click sau một cú kéo); bàn phím/đọc màn hình vẫn qua `click` (detail === 0). */}
      <button
        type="button"
        className="isc-tb isc-tb-pause"
        aria-label="Tạm dừng"
        onPointerUp={onPause}
        onClick={(e) => {
          if (e.detail === 0) onPause();
        }}
      >
        <span aria-hidden="true">❚❚</span>
      </button>
      <div
        ref={pad}
        className="isc-pad"
        role="group"
        aria-label="Đi trái / phải"
        data-testid="isc-pad"
        onPointerDown={padDown}
        onPointerMove={(e) => {
          if (e.buttons || e.pointerType === "touch") apply(e);
        }}
        onPointerUp={padUp}
        onPointerCancel={padUp}
        onLostPointerCapture={padUp}
        onContextMenu={(e) => e.preventDefault()}
      >
        <span className="isc-pad-arrow isc-pad-l" aria-hidden="true">◀</span>
        <span className="isc-pad-arrow isc-pad-r" aria-hidden="true">▶</span>
      </div>
      <div className="isc-actions">
        <HoldButton input={input} button="jump" label="⤒" hint="Nhảy" className="isc-tb-jump" />
        <HoldButton input={input} button="attack" label="⚔" hint="Chém" className="isc-tb-attack" />
        <HoldButton input={input} button="pulse" label="✦" hint="Memory Pulse" className="isc-tb-pulse" />
        {marginStep ? <HoldButton input={input} button="dash" label="⇢" hint="Margin Step" className="isc-tb-dash" /> : null}
      </div>
    </div>
  );
}
