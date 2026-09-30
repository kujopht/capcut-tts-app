"use client";

/** Tổng quan hôm nay: số liệu chính + trạng thái cấu hình + hạn mức toàn cục. */

import type { AiConfig, AiOverview } from "@/lib/admin/aiControl";
import { OSo } from "@/components/AdminShell";
import { AiQuotaBar } from "./AiQuotaBar";

const CHU_TRANG_THAI: Record<AiOverview["state"], string> = {
  ok: "Bình thường",
  empty: "Chưa có cấu hình AI nào được lưu — AI đang TẮT. Thêm slot, bật loại provider rồi bật công tắc tổng để bắt đầu.",
  corrupt: "Cấu hình AI đang hỏng — AI đang tắt an toàn (fail-closed). Sửa qua ops rồi tải lại.",
  unavailable: "Không đọc được kho cấu hình AI — AI đang tắt an toàn (fail-closed).",
  stale: "Kho cấu hình tạm mất kết nối — đang dùng bản hợp lệ gần nhất (tối đa 10 phút), sau đó AI tự tắt.",
};

function gioDiaPhuong(iso: string): string {
  if (!iso) return "—";
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? iso : t.toLocaleString("vi-VN");
}

/** Ngày UTC của server (`YYYYMMDD`) → `DD/MM/YYYY`. */
export function ngayUtc(day: string): string {
  return /^\d{8}$/.test(day) ? `${day.slice(6, 8)}/${day.slice(4, 6)}/${day.slice(0, 4)}` : day;
}

function dinhDangUsd(microUsd: number): string {
  return `$${(microUsd / 1_000_000).toFixed(4)}`;
}

export function AiOverviewCards({ overview, config }: { overview: AiOverview; config: AiConfig }) {
  const canhBao = overview.state !== "ok" && overview.state !== "empty";

  return (
    <div className="stack-3">
      {overview.state !== "ok" ? (
        <div className={`card stack-2 ${canhBao ? "ai-admin-xac-nhan" : "admin-chua-cau-hinh"}`} role={canhBao ? "alert" : "status"}>
          <strong>{CHU_TRANG_THAI[overview.state]}</strong>
        </div>
      ) : null}

      <div className="stat-grid admin-luoi">
        <OSo nhan="Yêu cầu hôm nay" so={overview.requests} />
        <OSo nhan="Token đầu vào" so={overview.input_tokens} />
        <OSo nhan="Token đầu ra" so={overview.output_tokens} />
        <div className="stat admin-o">
          <span className="stat-value">{dinhDangUsd(overview.est_cost_micro_usd)}</span>
          <span className="stat-label">Chi phí ước tính</span>
          <span className="hint admin-o-ghi">Theo giá Owner nhập, không phải hoá đơn</span>
        </div>
        <OSo nhan="Người dùng AI hoạt động" so={overview.active_users} />
        <OSo nhan="Lỗi" so={overview.errors} />
        <OSo nhan="Bị giới hạn tốc độ (429)" so={overview.rate_limited} />
      </div>

      <div className="card stack-2">
        <h3 className="section-title-sm">Hạn mức toàn cục hôm nay</h3>
        <AiQuotaBar nhan="Yêu cầu" daDung={overview.requests} tran={overview.caps.global_daily_request_cap} />
        <AiQuotaBar nhan="Token" daDung={overview.input_tokens + overview.output_tokens} tran={overview.caps.global_daily_token_cap} />
        <AiQuotaBar
          nhan="Chi phí"
          daDung={overview.est_cost_micro_usd}
          tran={overview.caps.daily_cost_cap_micro_usd}
          dinhDang={dinhDangUsd}
        />
      </div>

      <div className="card stack-2">
        <h3 className="section-title-sm">Provider — khả dụng hôm nay</h3>
        <div className="stat-grid admin-luoi">
          {overview.providers.map((p) => (
            <OSo
              key={p.type}
              nhan={p.label}
              so={p.healthy_slots}
              ghi_chu={`${p.slots} slot · ${p.enabled ? "Đang bật" : "Đang tắt"}`}
            />
          ))}
        </div>
      </div>

      <div className="card stack-2">
        <h3 className="section-title-sm">Slot theo trạng thái</h3>
        {Object.keys(overview.slots_by_status).length === 0 ? (
          <p className="hint">Chưa có slot nào — xem mục Providers bên dưới để thêm.</p>
        ) : (
          <div className="stat-grid admin-luoi">
            {Object.entries(overview.slots_by_status).map(([trang, so]) => (
              <OSo key={trang} nhan={trang} so={so} />
            ))}
          </div>
        )}
      </div>

      <p className="hint">
        Phiên bản cấu hình hiện tại: {config.controls.version} · cập nhật lần cuối bởi{" "}
        {config.controls.updated_by || "—"} lúc {gioDiaPhuong(config.controls.updated_at)}.
      </p>
    </div>
  );
}
