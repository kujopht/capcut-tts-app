"use client";

/** Mot hang trong danh sach phan doan — Subtitle Studio (Phan 4D). */

import type { SubtitleSegment } from "@/lib/subtitles/model";

function dinhDangGio(giay: number): string {
  const s = Math.max(0, giay);
  const phut = Math.floor(s / 60);
  const conLai = (s % 60).toFixed(2).padStart(5, "0");
  return `${String(phut).padStart(2, "0")}:${conLai}`;
}

export function SegmentRow({
  segment,
  dangHoatDong,
  onSeek,
  onSuaVanBan,
  onSuaThoiGian,
  onTach,
  onGop,
  onXoa,
  coTheGop,
}: {
  segment: SubtitleSegment;
  dangHoatDong: boolean;
  onSeek: (giay: number) => void;
  onSuaVanBan: (text: string) => void;
  onSuaThoiGian: (truong: "start" | "end", giay: number) => void;
  onTach: () => void;
  onGop: () => void;
  onXoa: () => void;
  coTheGop: boolean;
}) {
  return (
    <div
      className={`card sub-row${dangHoatDong ? " sub-row-active" : ""}`}
      role="group"
      aria-label={`Đoạn ${dinhDangGio(segment.start)}`}
    >
      <div className="row row-tight sub-row-times">
        <button
          type="button"
          className="btn btn-sm btn-ghost mono"
          onClick={() => onSeek(segment.start)}
          title="Tua tới đầu đoạn này"
        >
          ▶ {dinhDangGio(segment.start)}
        </button>
        <span className="hint" aria-hidden="true">→</span>
        <input
          className="input input-mini mono"
          type="number"
          step={0.1}
          min={segment.start}
          value={Number(segment.end.toFixed(2))}
          onChange={(e) => onSuaThoiGian("end", Number(e.target.value))}
          aria-label="Thời điểm kết thúc (giây)"
        />
      </div>
      <textarea
        className="input sub-row-text"
        value={segment.text}
        onChange={(e) => onSuaVanBan(e.target.value)}
        placeholder="Nhập lời thoại…"
        rows={2}
      />
      <div className="row row-tight sub-row-actions">
        <button type="button" className="btn btn-sm" onClick={onTach}
                title="Tách đoạn tại vị trí đang phát">
          Tách
        </button>
        <button type="button" className="btn btn-sm" onClick={onGop}
                disabled={!coTheGop} title="Gộp với đoạn kế tiếp">
          Gộp ↓
        </button>
        <button type="button" className="btn btn-sm btn-danger" onClick={onXoa}>
          Xoá
        </button>
      </div>
    </div>
  );
}
