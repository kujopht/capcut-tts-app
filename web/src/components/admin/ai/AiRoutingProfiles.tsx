"use client";

/**
 * Trình sửa HỒ SƠ ĐỊNH TUYẾN. Mỗi bước là một LOẠI provider (cả pool: xếp theo
 * priority, cùng mức thì xáo có trọng số) hoặc một `slot_id` cụ thể. Thứ tự
 * bước = thứ tự thử. Server kiểm lại tất cả (`validate_profile`) — kiểm ở đây
 * chỉ để chặn sớm lỗi hiển nhiên (trùng bước, quá 12 bước), không thay server.
 *
 * Không kéo-thả: nút Lên/Xuống dùng được bằng bàn phím và trên màn 390px.
 */

import { useState } from "react";
import type { AiConfigMeta, AiProviderTypeInfo, AiRoutingProfile, AiSlot } from "@/lib/admin/aiControl";

const MAX_BUOC = 12;

const MO_TA: Record<string, string> = {
  FREE_FIRST: "Ưu tiên provider miễn phí/rẻ cho trợ lý chung.",
  QUALITY_FIRST: "Ưu tiên chất lượng câu trả lời.",
  WRITER: "Chế độ viết (Studio).",
  STORY: "Hỏi đáp trong truyện.",
  SUPPORT_SAFE: "Hỗ trợ người dùng — chỉ slot có workload support.",
  WEB_SEARCH: "Lượt có tìm web (công cụ tìm web định tuyến riêng).",
};

export function diChuyen(steps: string[], i: number, delta: -1 | 1): string[] {
  const j = i + delta;
  if (j < 0 || j >= steps.length) return steps;
  const ra = [...steps];
  [ra[i], ra[j]] = [ra[j], ra[i]];
  return ra;
}

function nhanBuoc(step: string, types: AiProviderTypeInfo[], slots: AiSlot[]): string {
  const t = types.find((x) => x.type === step);
  if (t) return `${t.label} (cả pool)`;
  const s = slots.find((x) => x.slot_id === step);
  return s ? `${s.label} · ${s.slot_id}` : `${step} (không còn tồn tại)`;
}

function TheHoSo({
  hoSo,
  meta,
  types,
  slots,
  laOwner,
  dangGui,
  dangDung,
  loiTruong,
  onLuu,
}: {
  hoSo: AiRoutingProfile;
  meta: AiConfigMeta;
  types: AiProviderTypeInfo[];
  slots: AiSlot[];
  laOwner: boolean;
  dangGui: boolean;
  dangDung: string[];
  loiTruong: { field: string; message: string }[];
  onLuu: (name: string, steps: string[], enabled: boolean) => Promise<boolean>;
}) {
  const [steps, setSteps] = useState<string[]>(hoSo.steps);
  const [enabled, setEnabled] = useState(hoSo.enabled);
  const [them, setThem] = useState("");
  const [xacNhan, setXacNhan] = useState(false);

  const doi = JSON.stringify(steps) !== JSON.stringify(hoSo.steps) || enabled !== hoSo.enabled;
  const luaChon = [
    ...meta.provider_types.map((t) => ({ gt: t, nhan: nhanBuoc(t, types, slots) })),
    ...slots.map((s) => ({ gt: s.slot_id, nhan: `Slot: ${s.label} · ${s.slot_id}` })),
  ].filter((o) => !steps.includes(o.gt));
  const loiCucBo = steps.length > MAX_BUOC ? `Tối đa ${MAX_BUOC} bước.` : "";
  const tatHoSoDangDung = !enabled && hoSo.enabled && dangDung.length > 0;

  return (
    <div className="card stack-2 ai-admin-ho-so">
      <div className="row row-spread">
        <strong>{hoSo.name}</strong>
        <span className={`tt ${hoSo.enabled ? "tt-duyet" : "tt-trong"}`}>
          {hoSo.enabled ? "Đang bật" : "Đang tắt"}
        </span>
      </div>
      <p className="hint">
        {MO_TA[hoSo.name] ?? ""}
        {dangDung.length ? ` Đang dùng cho: ${dangDung.join(", ")}.` : " Chưa chế độ nào dùng."}
      </p>

      {steps.length === 0 ? (
        <p className="hint">Hồ sơ không có bước nào — lượt dùng hồ sơ này sẽ nhận lỗi &quot;không có provider&quot;.</p>
      ) : (
        <ol className="ai-admin-buoc">
          {steps.map((st, i) => (
            <li key={st} className="row row-spread">
              <span className="min0">
                <span className="ai-admin-so">{i + 1}</span> {nhanBuoc(st, types, slots)}
              </span>
              {laOwner ? (
                <span className="row row-tight">
                  <button type="button" className="btn btn-sm" aria-label={`Đưa ${st} lên`}
                    disabled={dangGui || i === 0} onClick={() => setSteps(diChuyen(steps, i, -1))}>↑</button>
                  <button type="button" className="btn btn-sm" aria-label={`Đưa ${st} xuống`}
                    disabled={dangGui || i === steps.length - 1} onClick={() => setSteps(diChuyen(steps, i, 1))}>↓</button>
                  <button type="button" className="btn btn-sm btn-danger" aria-label={`Bỏ bước ${st}`}
                    disabled={dangGui} onClick={() => setSteps(steps.filter((x) => x !== st))}>Bỏ</button>
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      )}

      {laOwner ? (
        <div className="stack-2">
          <div className="row row-tight">
            <select className="select grow" value={them} aria-label={`Thêm bước vào ${hoSo.name}`}
              onChange={(e) => setThem(e.target.value)} disabled={dangGui || steps.length >= MAX_BUOC}>
              <option value="">— Thêm bước (loại provider hoặc slot) —</option>
              {luaChon.map((o) => <option key={o.gt} value={o.gt}>{o.nhan}</option>)}
            </select>
            <button type="button" className="btn btn-sm" disabled={!them || dangGui}
              onClick={() => { setSteps([...steps, them]); setThem(""); }}>Thêm</button>
          </div>
          <label className="row row-tight">
            <input type="checkbox" checked={enabled} disabled={dangGui} onChange={(e) => setEnabled(e.target.checked)} />
            <span>Bật hồ sơ này</span>
          </label>
          {loiCucBo ? <span className="ai-admin-loi" role="alert">{loiCucBo}</span> : null}
          {loiTruong.map((l) => (
            <span key={`${l.field}:${l.message}`} className="ai-admin-loi" role="alert">{l.message}</span>
          ))}
          {xacNhan ? (
            <div className="card ai-admin-xac-nhan stack-2" role="alertdialog" aria-label={`Xác nhận lưu ${hoSo.name}`}>
              <strong>Lưu hồ sơ {hoSo.name}?</strong>
              <p className="hint">
                Thứ tự mới: {steps.length ? steps.join(" → ") : "(trống)"}.
                {tatHoSoDangDung ? ` Hồ sơ đang dùng cho ${dangDung.join(", ")} — tắt nó làm các chế độ đó ngừng trả lời.` : ""}
                {" "}Có hiệu lực trên mọi máy chủ trong ≤15 giây.
              </p>
              <div className="row row-tight">
                <button type="button" className="btn btn-primary btn-sm" disabled={dangGui}
                  onClick={() => { void onLuu(hoSo.name, steps, enabled).then((ok) => { if (ok) setXacNhan(false); }); }}>
                  Xác nhận lưu
                </button>
                <button type="button" className="btn btn-sm" onClick={() => setXacNhan(false)}>Huỷ</button>
              </div>
            </div>
          ) : (
            <div className="row row-tight">
              <button type="button" className="btn btn-primary btn-sm" disabled={!doi || dangGui || !!loiCucBo}
                onClick={() => setXacNhan(true)}>Lưu hồ sơ</button>
              {doi ? (
                <button type="button" className="btn btn-sm" disabled={dangGui}
                  onClick={() => { setSteps(hoSo.steps); setEnabled(hoSo.enabled); }}>Hoàn tác</button>
              ) : null}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function AiRoutingProfiles({
  profiles,
  modeProfiles,
  webSearchProfile,
  meta,
  types,
  slots,
  laOwner,
  dangGui,
  loiTheoHoSo,
  onLuu,
}: {
  profiles: AiRoutingProfile[];
  modeProfiles: Record<string, string>;
  webSearchProfile: string;
  meta: AiConfigMeta;
  types: AiProviderTypeInfo[];
  slots: AiSlot[];
  laOwner: boolean;
  dangGui: boolean;
  /** Lỗi 422 của lần lưu gần nhất, theo tên hồ sơ. */
  loiTheoHoSo: Record<string, { field: string; message: string }[]>;
  onLuu: (name: string, steps: string[], enabled: boolean) => Promise<boolean>;
}) {
  if (profiles.length === 0) {
    return (
      <div className="card admin-chua-cau-hinh" role="status">
        <strong>Chưa có hồ sơ định tuyến.</strong>
        <p className="hint">Máy chủ chưa trả hồ sơ nào — kiểm tra trạng thái kho cấu hình ở phần Tổng quan.</p>
      </div>
    );
  }
  return (
    <div className="ai-admin-luoi-ho-so">
      {profiles.map((p) => {
        const dangDung = [
          ...Object.entries(modeProfiles).filter(([, v]) => v === p.name).map(([k]) => k),
          ...(webSearchProfile === p.name ? ["web_search"] : []),
        ];
        return (
          // `key` gồm cả nội dung: hồ sơ đổi trên server (lưu xong, người khác
          // lưu) thì thẻ dựng lại từ giá trị mới thay vì giữ bản nháp cũ.
          <TheHoSo key={`${p.name}:${p.enabled}:${p.steps.join(",")}`} hoSo={p} meta={meta} types={types} slots={slots} laOwner={laOwner}
            dangGui={dangGui} dangDung={dangDung} loiTruong={loiTheoHoSo[p.name] ?? []} onLuu={onLuu} />
        );
      })}
    </div>
  );
}
