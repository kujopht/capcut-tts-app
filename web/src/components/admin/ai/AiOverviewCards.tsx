"use client";

/** Tổng quan hôm nay: số liệu chính + trạng thái cấu hình + hạn mức toàn cục. */

import type { AiConfig, AiOverview } from "@/lib/admin/aiControl";
import { moTaKhoTachBiet } from "@/lib/admin/aiSlotView";
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

/** Nhãn dễ hiểu của khán giả (`FAS_AI_AUDIENCE` đã phân giải). Chuỗi rỗng = cấu hình sai và AI đang tắt cho mọi người. */
export function nhanKhanGia(audience: string): string {
  switch (audience) {
    case "all":
      return "Mọi người đã đăng nhập";
    case "beta":
      return "Nhóm beta (Owner + canary + tester có tên)";
    case "canary":
      return "Chỉ Owner + canary";
    case "":
      return "KHÔNG AI (khán giả cấu hình sai)";
    default:
      return audience;
  }
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
  const khoTachBiet = overview.isolated_store ?? config.isolated_store;
  const canhBaoKho = moTaKhoTachBiet(khoTachBiet);

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
        {overview.qa ? (
          <OSo
            nhan="Lượt QA của Owner"
            so={overview.qa.requests}
            ghi_chu={`Hạn mức QA ${overview.qa.per_owner_daily_cap}/Owner/ngày · đã nằm trong số "Yêu cầu hôm nay" và trần toàn cục`}
          />
        ) : null}
        <OSo nhan="Lỗi" so={overview.errors} />
        <OSo nhan="Bị giới hạn tốc độ (429)" so={overview.rate_limited} />
      </div>

      {overview.runtime ? (
        <div className="card stack-2">
          <h3 className="section-title-sm">Ai đang dùng được · hàng đợi luồng</h3>
          <div className="stat-grid admin-luoi">
            <div className="stat admin-o">
              <span className="stat-value">{nhanKhanGia(overview.runtime.audience)}</span>
              <span className="stat-label">Đối tượng được dùng AI</span>
              <span className="hint admin-o-ghi">Đặt bằng biến môi trường, đổi cần deploy backend</span>
            </div>
            <OSo
              nhan="Luồng đang chạy"
              so={overview.runtime.streams_active}
              ghi_chu={`Tối đa ${overview.runtime.streams_max}/instance · đầy thì người dùng nhận "đang bận"`}
            />
            <OSo nhan="Giới hạn tốc độ mỗi người" so={overview.runtime.rpm_per_user} ghi_chu="lượt gửi / phút" />
          </div>
        </div>
      ) : null}

      {canhBaoKho.length > 0 ? (
        <div className="card stack-2" role="status">
          <h3 className="section-title-sm">{khoTachBiet?.title || "Vùng lưu trữ tách biệt"}</h3>
          {canhBaoKho.map((dong) => (
            <p key={dong} className="hint">
              {dong}
            </p>
          ))}
        </div>
      ) : null}

      {overview.gates && Object.keys(overview.gates).length > 0 ? (
        <div className="card stack-2">
          <h3 className="section-title-sm">Cổng cấp máy chủ</h3>
          <div className="stat-grid admin-luoi">
            {Object.entries(overview.gates).map(([loai, gate]) => (
              <div key={loai} className="stat admin-o">
                <span className="stat-value">{gate.open ? "MỞ" : "ĐÓNG"}</span>
                <span className="stat-label">
                  {config.provider_types.find((t) => t.type === loai)?.label ?? loai}
                </span>
                <span className="hint admin-o-ghi">
                  Biến môi trường {gate.env} — đóng thì không request nào tới nhà cung cấp này, dù cấu hình ở đây ra sao
                </span>
              </div>
            ))}
            <div className="stat admin-o">
              <span className="stat-value">{overview.free_quota_preference ? "BẬT" : "TẮT"}</span>
              <span className="stat-label">Ưu tiên hạn mức miễn phí sắp hết hạn</span>
              <span className="hint admin-o-ghi">Đã cài sẵn, mặc định tắt (biến môi trường, đổi cần deploy)</span>
            </div>
          </div>
        </div>
      ) : null}

      <div className="card stack-2">
        <h3 className="section-title-sm">Hạn mức toàn cục hôm nay</h3>
        <AiQuotaBar nhan="Yêu cầu" daDung={overview.requests} tran={overview.caps.global_daily_request_cap} />
        {overview.caps.global_daily_request_cap > 0 ? (
          <p className="hint">
            Còn lại hôm nay: {Math.max(0, overview.caps.global_daily_request_cap - overview.requests).toLocaleString("vi-VN")} yêu cầu
            (đặt lại lúc 00:00 UTC = 07:00 giờ Việt Nam)
          </p>
        ) : null}
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
