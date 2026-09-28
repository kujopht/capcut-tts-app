"use client";

/**
 * Lưới thẻ Memory Runes — chỉ VẼ. Thẻ nào ngửa và khóa rune của nó do trang
 * quyết định (luyện tập: client; tính điểm: máy chủ trả về từng lần lật).
 * Mỗi thẻ là <button>; mũi tên di chuyển; tên rune luôn in chữ dưới hình.
 */

import { useRef, useState } from "react";
import { RuneGlyph } from "@/components/games/RuneGlyph";
import { runeCua } from "@/lib/memoryRunes";

interface Props {
  rows: number;
  cols: number;
  /** index -> rune key cho các thẻ đang NGỬA (đã khớp hoặc đang lật). */
  ngua: Map<number, string>;
  daKhop: Set<number>;
  onLat: (i: number) => void;
  khoa?: boolean;
}

export function MemoryBoard({ rows, cols, ngua, daKhop, onLat, khoa }: Props) {
  const [tieuDiem, setTieuDiem] = useState(0);
  const luoi = useRef<HTMLDivElement>(null);
  const tong = rows * cols;

  const diToi = (i: number) => {
    setTieuDiem(i);
    luoi.current?.querySelector<HTMLButtonElement>(`[data-the="${i}"]`)?.focus();
  };

  const phim = (e: React.KeyboardEvent, i: number) => {
    const d: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -cols, ArrowDown: cols };
    if (e.key in d) {
      e.preventDefault();
      const j = i + d[e.key];
      if (j >= 0 && j < tong) diToi(j);
    }
  };

  return (
    <div
      ref={luoi}
      className="mr-luoi"
      role="group"
      aria-label={`Lưới ${rows} hàng × ${cols} cột`}
      style={{ ["--mr-cot" as string]: cols, ["--mr-hang" as string]: rows }}
    >
      {Array.from({ length: tong }, (_, i) => {
        const key = ngua.get(i);
        const khop = daKhop.has(i);
        const hang = Math.floor(i / cols) + 1;
        const cot = (i % cols) + 1;
        const r = key ? runeCua(key) : null;
        return (
          <button
            key={i}
            type="button"
            data-the={i}
            className={`mr-the${key ? " is-ngua" : ""}${khop ? " is-khop" : ""}`}
            tabIndex={i === tieuDiem ? 0 : -1}
            aria-label={`Hàng ${hang}, cột ${cot}: ${r ? `${r.ten}${khop ? " (đã khớp)" : ""}` : "thẻ úp"}`}
            aria-disabled={!!key || khoa}
            onFocus={() => setTieuDiem(i)}
            onKeyDown={(e) => phim(e, i)}
            onClick={() => {
              if (!key && !khoa) onLat(i);
            }}
          >
            {r ? (
              <span className="mr-mat">
                <RuneGlyph runeKey={r.key} />
                <span className="mr-ten">{r.ten}</span>
              </span>
            ) : (
              <span className="mr-lung" aria-hidden="true" />
            )}
          </button>
        );
      })}
    </div>
  );
}
