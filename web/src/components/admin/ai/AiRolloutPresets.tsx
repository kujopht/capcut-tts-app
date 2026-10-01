"use client";

/**
 * Preset rollout: một bước, có audit, có `expected_version`. Preset chỉ đặt
 * HẠN MỨC — công tắc khẩn cấp (AiKillSwitch) độc lập và luôn thắng. Hiện preset
 * đang khớp ("custom" nếu đã sửa tay từng giá trị).
 */

import { useState } from "react";
import type { AiPresetName, AiRollout } from "@/lib/admin/aiControl";

const NHAN_PRESET: Record<AiPresetName, string> = {
  canary: "Canary (chỉ Owner)",
  beta: "Beta công khai",
};

const NHAN_TRUONG: Record<string, string> = {
  per_user_daily_request_cap: "yêu cầu/người/ngày",
  global_daily_request_cap: "yêu cầu toàn cục/ngày",
  per_user_daily_token_cap: "token/người/ngày",
  global_daily_token_cap: "token toàn cục/ngày",
  max_output_tokens: "token ra/lượt",
  max_context_tokens: "token ngữ cảnh/lượt",
};

export function AiRolloutPresets({
  rollout,
  laOwner,
  dangGui,
  onApDung,
}: {
  rollout: AiRollout;
  laOwner: boolean;
  dangGui: boolean;
  onApDung: (name: AiPresetName) => Promise<boolean>;
}) {
  const [cho, setCho] = useState<AiPresetName | null>(null);
  const ten = Object.keys(rollout.presets) as AiPresetName[];

  return (
    <div className="card stack-2 ai-admin-form">
      <div className="row row-spread">
        <strong>Preset rollout</strong>
        <span className="tt tt-trong">
          Đang dùng: {rollout.active_preset === "custom" ? "tuỳ chỉnh" : NHAN_PRESET[rollout.active_preset]}
        </span>
      </div>
      <p className="hint">
        Preset chỉ đặt hạn mức. Công tắc khẩn cấp ở trên độc lập và luôn tắt được ngay. Lượt kiểm slot có
        ngân sách riêng ({rollout.probe_daily_cap_per_slot} lần/slot/ngày), không trừ vào hạn mức người dùng.
      </p>
      <div className="ai-admin-2cot">
        {ten.map((n) => (
          <div key={n} className="stack-1">
            <strong>{NHAN_PRESET[n] ?? n}</strong>
            <ul className="ai-admin-ds-doi">
              {Object.entries(rollout.presets[n]).map(([k, v]) => (
                <li key={k}>{v.toLocaleString("vi-VN")} {NHAN_TRUONG[k] ?? k}</li>
              ))}
            </ul>
            {laOwner ? (
              cho === n ? (
                <div className="row row-tight">
                  <button type="button" className="btn btn-primary btn-sm" disabled={dangGui}
                    onClick={() => { void onApDung(n).then(() => setCho(null)); }}>
                    Xác nhận áp {n}
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => setCho(null)}>Huỷ</button>
                </div>
              ) : (
                <button type="button" className="btn btn-sm" disabled={dangGui || rollout.active_preset === n}
                  onClick={() => setCho(n)}>
                  {rollout.active_preset === n ? "Đang áp dụng" : `Áp preset ${n}`}
                </button>
              )
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
