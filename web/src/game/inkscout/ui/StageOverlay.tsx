"use client";

import { ENDINGS, ENDING_CHOICE, MEMORY_TEXT } from "../core/lore";
import type { SaveSettings } from "../core/save";
import type { UiSnapshot } from "../platform/runtime";

/**
 * Lớp chữ DOM phủ lên canvas (tiếng Việt, đọc được, co theo màn hình): lời thoại, hộp đọc ký ức, tạm dừng, kết thúc. Cập nhật chỉ khi `UiSnapshot`
 * đổi (rời rạc), không theo từng khung hình.
 */
export function formatTime(frames: number): string {
  const s = Math.floor(frames / 60);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

interface Props {
  ui: UiSnapshot;
  coarse: boolean;
  onTap: () => void;
  onResume: () => void;
  onQuit: () => void;
  onShake: (v: SaveSettings["shake"]) => void;
  onMute: (m: boolean) => void;
  onChoose: (i: 0 | 1) => void;
  onRestart: () => void;
}

const SHAKES: ReadonlyArray<{ v: SaveSettings["shake"]; label: string }> = [
  { v: 0, label: "Tắt" },
  { v: 0.5, label: "Nhẹ" },
  { v: 1, label: "Đủ" },
];

export function StageOverlay({ ui, coarse, onTap, onResume, onQuit, onShake, onMute, onChoose, onRestart }: Props) {
  if (ui.mode === "complete" && ui.result) {
    const r = ui.result;
    const title = ENDINGS[r.ending].title;
    return (
      <div className="isc-card isc-result" role="dialog" aria-modal="true" aria-label="Kết quả">
        <p className="isc-eyebrow">CHƯƠNG 0 HOÀN THÀNH</p>
        <h2 className="isc-h">{title}</h2>
        <dl className="isc-stats">
          <div><dt>Ký ức</dt><dd>{r.memories.length}/3</dd></div>
          <div><dt>Thời gian</dt><dd>{formatTime(r.frames)}</dd></div>
          <div><dt>Số lần ngã</dt><dd>{r.deaths}</dd></div>
          <div><dt>Nhanh nhất</dt><dd>{formatTime(r.bestFrames)}</dd></div>
        </dl>
        {r.memories.length < 3 ? <p className="isc-note">Còn {3 - r.memories.length} Ký Ức chưa tìm thấy — chúng giấu ở những nơi cần quay lại mới tới được.</p> : null}
        <div className="isc-row">
          <button type="button" className="isc-btn isc-btn-primary" onClick={onRestart}>Chơi lại từ đầu</button>
          <button type="button" className="isc-btn" onClick={onQuit}>Về menu</button>
        </div>
      </div>
    );
  }

  if (ui.paused) {
    return (
      <div className="isc-card isc-pause" role="dialog" aria-modal="true" aria-label="Tạm dừng">
        <h2 className="isc-h">Tạm dừng</h2>
        <div className="isc-row isc-row-wrap">
          <span className="isc-label" id="isc-shake-l">Rung màn hình</span>
          <div role="radiogroup" aria-labelledby="isc-shake-l" className="isc-seg">
            {SHAKES.map((s) => (
              <button key={s.v} type="button" role="radio" aria-checked={ui.settings.shake === s.v} className="isc-seg-b" onClick={() => onShake(s.v)}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="isc-row isc-row-wrap">
          <span className="isc-label" id="isc-snd-l">Âm thanh</span>
          <div role="radiogroup" aria-labelledby="isc-snd-l" className="isc-seg">
            <button type="button" role="radio" aria-checked={!ui.settings.muted} className="isc-seg-b" onClick={() => onMute(false)}>Bật</button>
            <button type="button" role="radio" aria-checked={ui.settings.muted} className="isc-seg-b" onClick={() => onMute(true)}>Tắt</button>
          </div>
        </div>
        {coarse ? null : <p className="isc-note">← → / A D đi · Space nhảy · J chém · K Pulse · Shift lướt · Esc tạm dừng</p>}
        <div className="isc-row">
          <button type="button" className="isc-btn isc-btn-primary" onClick={onResume} autoFocus>Tiếp tục</button>
          <button type="button" className="isc-btn" onClick={onQuit}>Thoát về menu</button>
        </div>
      </div>
    );
  }

  if (ui.read) {
    if (ui.read.kind === "memory") {
      const m = MEMORY_TEXT[Number(ui.read.id) as 1 | 2 | 3];
      return (
        <div className="isc-card isc-read" role="dialog" aria-modal="true" aria-label={m.title} onPointerDown={onTap}>
          <p className="isc-eyebrow">MEMORY FRAGMENT</p>
          <h2 className="isc-h isc-gold">{m.title}</h2>
          {m.lines.map((l) => (
            <p key={l} className="isc-line">{l}</p>
          ))}
          <p className="isc-boon">{m.boon}</p>
          <p className="isc-tap">{coarse ? "Chạm để tiếp tục" : "Nhấn Enter / Space để tiếp tục"}</p>
        </div>
      );
    }
    return (
      <div className="isc-card isc-read" role="dialog" aria-modal="true" aria-label="Margin Step" onPointerDown={onTap}>
        <p className="isc-eyebrow">KHẢ NĂNG MỚI</p>
        <h2 className="isc-h isc-cyan">MARGIN STEP</h2>
        <p className="isc-line">Lướt ngắn theo hướng đang giữ — có khung bất tử ở đầu cú lướt, dùng được cả trên không (một lần mỗi lần nhảy).</p>
        <p className="isc-line">Và nó cũng là lối qua những khe hở quá rộng để nhảy thường. Nhớ quay lại các nơi cũ.</p>
        <p className="isc-tap">{coarse ? "Chạm nút ⇢ để lướt — chạm để tiếp tục" : "Giữ hướng + Shift để lướt — Enter để tiếp tục"}</p>
      </div>
    );
  }

  if (ui.ending) {
    const e = ui.ending;
    if (e.stage === "choice") {
      return (
        <div className="isc-card isc-ending" role="dialog" aria-modal="true" aria-label="Lựa chọn cuối cùng">
          <p className="isc-eyebrow">LỰA CHỌN CUỐI</p>
          <p className="isc-line">{ENDING_CHOICE.prompt}</p>
          <div className="isc-row isc-choices">
            <button type="button" className={`isc-btn isc-choice ${e.choice === 0 ? "is-on" : ""}`} onClick={() => onChoose(0)}>
              <strong>{ENDING_CHOICE.erase.label}</strong>
              <span>{ENDING_CHOICE.erase.hint}</span>
            </button>
            <button type="button" className={`isc-btn isc-choice ${e.choice === 1 ? "is-on" : ""}`} onClick={() => onChoose(1)}>
              <strong>{ENDING_CHOICE.restore.label}</strong>
              <span>{ENDING_CHOICE.restore.hint}</span>
            </button>
          </div>
          <p className="isc-tap">{coarse ? "Chạm một lựa chọn rồi chạm lần nữa để xác nhận" : "← → để chọn · Enter để xác nhận"}</p>
        </div>
      );
    }
    const key = e.kind === "basic" && ui.memories.length >= 2 ? "basic2" : (e.kind ?? "basic");
    return (
      <div className="isc-card isc-ending" role="dialog" aria-modal="true" aria-label={ENDINGS[key].title} onPointerDown={onTap}>
        <p className="isc-eyebrow">{ENDINGS[key].title}</p>
        <p className="isc-line isc-big">{e.pages[e.page] ?? ""}</p>
        <p className="isc-tap">{e.page + 1}/{e.pages.length} · {coarse ? "Chạm để tiếp tục" : "Enter / Space"}</p>
      </div>
    );
  }

  return (
    <>
      {ui.caption ? (
        <div className="isc-cap" role="status" aria-live="polite">
          {ui.caption.who ? <strong className="isc-cap-who">{ui.caption.who}</strong> : null}
          <span>{ui.caption.text}</span>
        </div>
      ) : null}
      {ui.boss ? <div className="isc-boss-name" aria-hidden="true">THE REDACTOR</div> : null}
      {ui.mode === "dead" ? <div className="isc-dead" aria-live="polite">Mực cạn rồi… Quay lại Dấu Trang gần nhất.</div> : null}
    </>
  );
}
