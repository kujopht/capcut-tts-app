"use client";

/**
 * System — Admin Control Center V2, Phase 2 + Phase 7. CHI OWNER (xem
 * AdminShell/A3: cai dat ha tang khong thuoc pham vi ADMIN).
 *
 * Phase 7: them YouTube Data API/WebSub/Doi chieu — dung CHUNG mot vocab
 * bon trang thai (HEALTHY/DEGRADED/ERROR/NOT_CONFIGURED, xem
 * `server/main.py::_trang_thai_he_thong`) thay vi suy boolean rieng le.
 */

import { useCallback } from "react";
import { adminApi, type AdminOverview, type TrangThaiHeThong } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconGear } from "@/components/Icons";

const NHAN_TRANG_THAI: Record<TrangThaiHeThong, string> = {
  healthy: "Khoẻ",
  degraded: "Suy giảm",
  error: "Lỗi",
  not_configured: "Chưa cấu hình",
};

const LOP_TRANG_THAI: Record<TrangThaiHeThong, string> = {
  healthy: "tt-duyet",
  degraded: "tt-cho",
  error: "tt-tuchoi",
  not_configured: "tt-trong",
};

function TrangThaiHang({
  nhan,
  trang_thai,
  ghi_chu,
}: {
  nhan: string;
  trang_thai: TrangThaiHeThong;
  ghi_chu?: string;
}) {
  return (
    <div className="row row-spread admin-hang">
      <span>{nhan}</span>
      <span className="stack-2" style={{ alignItems: "flex-end" }}>
        <span className={`tt ${LOP_TRANG_THAI[trang_thai]}`}>
          {NHAN_TRANG_THAI[trang_thai]}
        </span>
        {ghi_chu ? <span className="hint">{ghi_chu}</span> : null}
      </span>
    </div>
  );
}

export default function AdminSystem() {
  const nap = useCallback(() => adminApi.overview(), []);
  const { data, loading, error, reload } = useAsyncData<AdminOverview>(nap);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconGear size={19} /> System
      </h2>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!data} onThuLai={reload}>
        {data ? (
          <div className="card stack-2">
            <TrangThaiHang nhan="Backend" trang_thai={data.system.statuses.backend} />
            <TrangThaiHang
              nhan="Kho dữ liệu"
              trang_thai={data.system.statuses.appwrite}
              ghi_chu={data.system.data_backend}
            />
            <TrangThaiHang
              nhan="Worker / hàng đợi"
              trang_thai={data.system.statuses.workers}
              ghi_chu={data.system.inline_worker ? "Trong tiến trình web" : "Tiến trình riêng"}
            />
            <TrangThaiHang
              nhan="Provider dịch thuật"
              trang_thai={data.system.statuses.translation_provider}
            />
            <TrangThaiHang nhan="TTS" trang_thai={data.system.statuses.tts} />
            <TrangThaiHang
              nhan="Image Studio Shared Premium"
              trang_thai={data.system.statuses.image_studio}
            />
            <TrangThaiHang
              nhan="YouTube Data API"
              trang_thai={data.system.statuses.youtube_data_api}
            />
            <TrangThaiHang
              nhan="YouTube WebSub"
              trang_thai={data.system.statuses.youtube_websub}
              ghi_chu={
                !data.system.youtube_websub_configured
                  ? "Cần backend công khai qua HTTPS — xem Trusted Video Sources"
                  : undefined
              }
            />
            <TrangThaiHang
              nhan="Đối chiếu định kỳ (reconciliation)"
              trang_thai={data.system.statuses.reconciliation}
              ghi_chu={
                data.trusted_sources.reconciliation_last_run_at
                  ? `Lần chạy gần nhất: ${new Date(
                      data.trusted_sources.reconciliation_last_run_at,
                    ).toLocaleString("vi-VN")}`
                  : "Chưa từng chạy"
              }
            />
            <p className="hint">
              Trạng thái đọc trực tiếp từ tiến trình backend đang chạy — không
              lưu bản sao riêng, không thể lệch với thực tế. &quot;Worker /
              hàng đợi&quot; không có giám sát riêng (không có tín hiệu độc
              lập để phát hiện worker chết) — dựa theo tình trạng Appwrite.
            </p>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
