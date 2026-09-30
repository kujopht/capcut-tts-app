"use client";

/**
 * Hạn mức toàn cục + ánh xạ chế độ → hồ sơ. Gửi kèm `expected_version`: hai
 * Owner cùng sửa thì người lưu sau nhận 409 thay vì âm thầm ghi đè người kia.
 *
 * Trần chi phí nhập bằng USD cho dễ đọc, gửi đi bằng micro-USD (số nguyên —
 * đúng kiểu server lưu). 0 = không giới hạn ở mọi trần, TRỪ hai trần kỹ thuật
 * `max_output_tokens`/`max_context_tokens` luôn phải có giá trị.
 */

import { useState } from "react";
import type { AiControls, AiGlobalPatch, AiMode } from "@/lib/admin/aiControl";

type SoTruong =
  | "global_daily_request_cap"
  | "global_daily_token_cap"
  | "per_user_daily_request_cap"
  | "per_user_daily_token_cap"
  | "max_output_tokens"
  | "max_context_tokens";

const TRUONG_SO: { k: SoTruong; nhan: string; min: number; max?: number }[] = [
  { k: "global_daily_request_cap", nhan: "Trần yêu cầu toàn cục / ngày", min: 0 },
  { k: "global_daily_token_cap", nhan: "Trần token toàn cục / ngày", min: 0 },
  { k: "per_user_daily_request_cap", nhan: "Trần yêu cầu mỗi người / ngày", min: 0 },
  { k: "per_user_daily_token_cap", nhan: "Trần token mỗi người / ngày", min: 0 },
  { k: "max_output_tokens", nhan: "Token đầu ra tối đa / lượt", min: 64, max: 8000 },
  { k: "max_context_tokens", nhan: "Token ngữ cảnh tối đa / lượt", min: 512, max: 32000 },
];

const NHAN_CHE_DO: Record<AiMode, string> = {
  general: "Trợ lý chung",
  story: "Trong truyện",
  writer: "Viết (Studio)",
  support: "Hỗ trợ",
};

function loiCua(loi: { field: string; message: string }[], f: string) {
  const m = loi.find((l) => l.field === f)?.message;
  return m ? <span className="ai-admin-loi" role="alert">{m}</span> : null;
}

export function AiGlobalCaps({
  controls,
  profiles,
  modes,
  laOwner,
  dangGui,
  loiTruong,
  onLuu,
}: {
  controls: AiControls;
  profiles: string[];
  modes: AiMode[];
  laOwner: boolean;
  dangGui: boolean;
  loiTruong: { field: string; message: string }[];
  onLuu: (patch: AiGlobalPatch) => Promise<boolean>;
}) {
  const tuControls = () => ({
    so: Object.fromEntries(TRUONG_SO.map(({ k }) => [k, controls[k]])) as Record<SoTruong, number>,
    usd: controls.daily_cost_cap_micro_usd / 1_000_000,
    modeProfiles: { ...controls.mode_profiles },
    webSearch: controls.web_search_profile,
  });
  const [f, setF] = useState(tuControls);
  const [xacNhan, setXacNhan] = useState(false);

  // Đổi phiên bản -> trang cha đổi `key={controls.version}` nên form DỰNG LẠI
  // từ giá trị mới; không sao chép prop vào state bằng effect.

  const patch: AiGlobalPatch = {
    ...f.so,
    daily_cost_cap_micro_usd: Math.round((Number.isFinite(f.usd) ? f.usd : 0) * 1_000_000),
    mode_profiles: f.modeProfiles,
    web_search_profile: f.webSearch,
    expected_version: controls.version,
  };
  const thayDoi: string[] = [];
  for (const { k, nhan } of TRUONG_SO) if (f.so[k] !== controls[k]) thayDoi.push(`${nhan}: ${controls[k]} → ${f.so[k]}`);
  if (patch.daily_cost_cap_micro_usd !== controls.daily_cost_cap_micro_usd) {
    thayDoi.push(`Trần chi phí/ngày: $${controls.daily_cost_cap_micro_usd / 1_000_000} → $${f.usd}`);
  }
  for (const m of modes) {
    if (f.modeProfiles[m] !== controls.mode_profiles[m]) {
      thayDoi.push(`${NHAN_CHE_DO[m]}: ${controls.mode_profiles[m]} → ${f.modeProfiles[m]}`);
    }
  }
  if (f.webSearch !== controls.web_search_profile) thayDoi.push(`Tìm web: ${controls.web_search_profile} → ${f.webSearch}`);

  return (
    <form className="card stack-3 ai-admin-form" noValidate onSubmit={(e) => { e.preventDefault(); if (thayDoi.length) setXacNhan(true); }}>
      <fieldset className="stack-2" disabled={!laOwner || dangGui}>
        <legend className="section-title-sm">Hạn mức</legend>
        <div className="ai-admin-2cot">
          {TRUONG_SO.map(({ k, nhan, min, max }) => (
            <label key={k} className="field">
              <span className="label">{nhan}</span>
              <input className="input" type="number" min={min} max={max} value={f.so[k]}
                onChange={(e) => setF({ ...f, so: { ...f.so, [k]: Number(e.target.value) } })} />
              {loiCua(loiTruong, k)}
            </label>
          ))}
          <label className="field">
            <span className="label">Trần chi phí ước tính / ngày (USD, 0 = không giới hạn)</span>
            <input className="input" type="number" min={0} step={0.01} value={f.usd}
              onChange={(e) => setF({ ...f, usd: Number(e.target.value) })} />
            {loiCua(loiTruong, "daily_cost_cap_micro_usd")}
          </label>
        </div>
        <p className="hint">0 = không giới hạn. Chạm trần: bỏ qua provider đó và thử provider dự phòng được phép; hết thì trả lỗi thân thiện, không thử lại vô hạn.</p>
      </fieldset>

      <fieldset className="stack-2" disabled={!laOwner || dangGui}>
        <legend className="section-title-sm">Chế độ → hồ sơ định tuyến</legend>
        <div className="ai-admin-2cot">
          {modes.map((m) => (
            <label key={m} className="field">
              <span className="label">{NHAN_CHE_DO[m] ?? m}</span>
              <select className="select" value={f.modeProfiles[m] ?? ""}
                onChange={(e) => setF({ ...f, modeProfiles: { ...f.modeProfiles, [m]: e.target.value } })}>
                {profiles.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          ))}
          <label className="field">
            <span className="label">Lượt có tìm web</span>
            <select className="select" value={f.webSearch} onChange={(e) => setF({ ...f, webSearch: e.target.value })}>
              {profiles.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            {loiCua(loiTruong, "web_search_profile")}
          </label>
        </div>
        {loiCua(loiTruong, "mode_profiles")}
      </fieldset>

      {!laOwner ? <p className="hint">Chỉ Owner mới sửa được hạn mức.</p> : xacNhan ? (
        <div className="card ai-admin-xac-nhan stack-2" role="alertdialog" aria-label="Xác nhận lưu hạn mức">
          <strong>Lưu {thayDoi.length} thay đổi?</strong>
          <ul className="ai-admin-ds-doi">{thayDoi.map((t) => <li key={t}>{t}</li>)}</ul>
          <div className="row row-tight">
            <button type="button" className="btn btn-primary btn-sm" disabled={dangGui}
              onClick={() => { void onLuu(patch).then((ok) => { if (!ok) setXacNhan(false); }); }}>
              Xác nhận lưu
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setXacNhan(false)}>Huỷ</button>
          </div>
        </div>
      ) : (
        <div className="row row-tight">
          <button type="submit" className="btn btn-primary btn-sm" disabled={!thayDoi.length || dangGui}>
            Lưu hạn mức
          </button>
          {thayDoi.length ? (
            <button type="button" className="btn btn-sm" onClick={() => setF(tuControls())}>Hoàn tác</button>
          ) : <span className="hint">Chưa có thay đổi.</span>}
        </div>
      )}
    </form>
  );
}
