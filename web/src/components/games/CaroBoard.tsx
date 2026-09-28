"use client";

/**
 * Bàn Caro 15×15 dùng chung cho "Luyện với máy" và phòng hai người.
 *
 * Chỉ VẼ trạng thái được đưa vào (`ban`) — không tự quyết thắng/thua. Mỗi ô là
 * một <button> thật (chạm/bấm/Enter), phím mũi tên di chuyển giữa các ô (một ô
 * duy nhất có tabIndex=0). X và O khác HÌNH, không chỉ khác màu.
 */

import { useCallback, useRef, useState } from "react";
import { CO, SO_O, hangCot } from "@/lib/caro";

interface Props {
  ban: string;
  onDanh?: (i: number) => void;
  khoa?: boolean;
  nuocCuoi?: number | null;
  duongThang?: number[];
  nhan: string;
}

function QuanCo({ q }: { q: string }) {
  if (q === "x")
    return (
      <svg viewBox="0 0 24 24" className="caro-quan caro-quan-x" aria-hidden="true" focusable="false">
        <path d="M6 6 L18 18 M18 6 L6 18" />
      </svg>
    );
  if (q === "o")
    return (
      <svg viewBox="0 0 24 24" className="caro-quan caro-quan-o" aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="6.5" />
      </svg>
    );
  return null;
}

const TEN = { x: "quân X", o: "quân O", ".": "trống" } as Record<string, string>;

export function CaroBoard({ ban, onDanh, khoa, nuocCuoi, duongThang = [], nhan }: Props) {
  const [tieuDiem, setTieuDiem] = useState(() => (nuocCuoi ?? 112));
  const luoi = useRef<HTMLDivElement>(null);
  const thang = new Set(duongThang);

  const diToi = useCallback((i: number) => {
    setTieuDiem(i);
    luoi.current?.querySelector<HTMLButtonElement>(`[data-o="${i}"]`)?.focus();
  }, []);

  const phim = (e: React.KeyboardEvent, i: number) => {
    const { hang, cot } = hangCot(i);
    const di: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const d = di[e.key];
    if (d) {
      e.preventDefault();
      const h = Math.min(CO - 1, Math.max(0, hang + d[0]));
      const c = Math.min(CO - 1, Math.max(0, cot + d[1]));
      diToi(h * CO + c);
    } else if (e.key === "Home") {
      e.preventDefault();
      diToi(hang * CO);
    } else if (e.key === "End") {
      e.preventDefault();
      diToi(hang * CO + CO - 1);
    }
  };

  return (
    <div className="caro-khung">
      <div ref={luoi} className="caro-ban" role="group" aria-label={nhan}>
        {Array.from({ length: SO_O }, (_, i) => {
          const q = ban[i] ?? ".";
          const { hang, cot } = hangCot(i);
          const trong = q === ".";
          return (
            <button
              key={i}
              type="button"
              data-o={i}
              className={`caro-o${thang.has(i) ? " is-thang" : ""}${nuocCuoi === i ? " is-cuoi" : ""}`}
              tabIndex={i === tieuDiem ? 0 : -1}
              aria-label={`Hàng ${hang + 1}, cột ${cot + 1}: ${TEN[q]}${thang.has(i) ? ", đường thắng" : ""}${nuocCuoi === i ? ", nước vừa đi" : ""}`}
              aria-disabled={!trong || khoa || !onDanh}
              onFocus={() => setTieuDiem(i)}
              onKeyDown={(e) => phim(e, i)}
              onClick={() => {
                if (trong && !khoa && onDanh) onDanh(i);
              }}
            >
              <QuanCo q={q} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
