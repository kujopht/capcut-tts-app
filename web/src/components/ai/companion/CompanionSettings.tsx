"use client";

/**
 * Hai điều khiển của người dùng cho linh vật Ink Scout, đặt trong popover cài
 * đặt của trợ lý (`AiControls`): Ẩn linh vật / Giảm chuyển động. Lưu theo trình
 * duyệt (`companionPrefs`). `prefers-reduced-motion` của hệ điều hành luôn áp
 * dụng dù ô "Giảm chuyển động" có được tick hay không.
 */
import { useCompanionPrefs, useSystemReducedMotion } from "./companionPrefs";

export function CompanionSettings() {
  const [prefs, setPrefs] = useCompanionPrefs();
  const systemReduced = useSystemReducedMotion();
  return (
    <>
      <div className="ai-caidat-sep" role="separator" />
      <label className="ai-caidat-dong">
        <span>Ẩn Ink Scout</span>
        <input
          type="checkbox"
          checked={prefs.hidden}
          onChange={(e) => setPrefs({ hidden: e.target.checked })}
          aria-label="Ẩn linh vật Ink Scout"
        />
      </label>
      <label className="ai-caidat-dong">
        <span>Giảm chuyển động của Ink Scout</span>
        <input
          type="checkbox"
          checked={prefs.reducedMotion || systemReduced}
          disabled={systemReduced}
          onChange={(e) => setPrefs({ reducedMotion: e.target.checked })}
          aria-label="Giảm chuyển động của linh vật Ink Scout"
        />
      </label>
      {systemReduced ? (
        <p className="hint ai-caidat-giaithich">Thiết bị đang yêu cầu giảm chuyển động — linh vật chỉ dùng ảnh tĩnh.</p>
      ) : null}
    </>
  );
}
