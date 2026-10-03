"use client";

/** Bật/tắt riêng từng LOẠI provider (cả pool, không phải một slot). */

import { useState } from "react";
import type { AiProviderTypeInfo, AiProviderType } from "@/lib/admin/aiControl";

export function AiProviderTypes({
  providerTypes,
  trangThai,
  laOwner,
  onDoi,
}: {
  providerTypes: AiProviderTypeInfo[];
  /** `controls.provider_types` — nguồn SỰ THẬT về bật/tắt (danh sách
   *  `provider_types` chỉ cho nhãn + số slot). */
  trangThai: Record<AiProviderType, boolean>;
  laOwner: boolean;
  onDoi: (type: AiProviderType, enabled: boolean) => Promise<void>;
}) {
  const [dangGui, setDangGui] = useState<AiProviderType | null>(null);

  const bam = async (type: AiProviderType, enabled: boolean) => {
    setDangGui(type);
    try {
      await onDoi(type, enabled);
    } finally {
      setDangGui(null);
    }
  };

  return (
    <div className="card stack-2">
      <h3 className="section-title-sm">Loại provider</h3>
      {!laOwner ? <p className="hint">Chỉ Owner mới bật/tắt được.</p> : null}
      <div className="stack-2">
        {providerTypes.map((p) => {
          const enabled = trangThai[p.type] ?? false;
          return (
            <div key={p.type} className="row row-spread admin-hang">
              <span>
                {p.label} <span className="hint">({p.slot_count} slot)</span>
                {p.gate ? (
                  <>
                    {" "}
                    <span className={`tt ${p.gate.open ? "tt-duyet" : "tt-tuchoi"}`}>
                      {p.gate.open ? "Cổng máy chủ mở" : "Cổng máy chủ ĐÓNG"}
                    </span>
                    {!p.gate.open ? (
                      <span className="hint">
                        {" "}
                        · không có request nào tới nhà cung cấp này cho tới khi đặt <code>{p.gate.env}=1</code> ở máy chủ
                        và khởi động lại (bật ở đây không thay thế được)
                      </span>
                    ) : null}
                  </>
                ) : null}
              </span>
              <label className="row row-tight" style={{ gap: 6 }}>
                <input
                  type="checkbox"
                  checked={enabled}
                  disabled={!laOwner || dangGui === p.type}
                  aria-label={`Bật/tắt ${p.label}`}
                  onChange={(e) => void bam(p.type, e.target.checked)}
                />
                <span className={`tt ${enabled ? "tt-duyet" : "tt-trong"}`}>
                  {enabled ? "Bật" : "Tắt"}
                </span>
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
