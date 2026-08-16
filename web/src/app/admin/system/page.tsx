"use client";

/**
 * System — Admin Control Center V2, Phase 2. CHI OWNER (xem AdminShell/A3:
 * cai dat ha tang khong thuoc pham vi ADMIN).
 */

import { useCallback } from "react";
import { adminApi, type AdminOverview } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconGear } from "@/components/Icons";

function TrangThaiHang({
  nhan,
  gia_tri,
  tot,
}: {
  nhan: string;
  gia_tri: string;
  tot: boolean | null;
}) {
  return (
    <div className="row row-spread admin-hang">
      <span>{nhan}</span>
      <span className={`tt ${tot === null ? "tt-trong" : tot ? "tt-duyet" : "tt-treo"}`}>
        {gia_tri}
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
            <TrangThaiHang
              nhan="Backend"
              gia_tri={data.system.backend === "ok" ? "Đang chạy" : data.system.backend}
              tot={data.system.backend === "ok"}
            />
            <TrangThaiHang
              nhan="Kho dữ liệu"
              gia_tri={data.system.data_backend}
              tot={data.system.data_backend === "appwrite"}
            />
            <TrangThaiHang
              nhan="Appwrite"
              gia_tri={
                !data.system.appwrite_configured
                  ? "Chưa cấu hình"
                  : data.system.appwrite_healthy
                    ? "Khoẻ"
                    : "Không phản hồi"
              }
              tot={data.system.appwrite_configured ? data.system.appwrite_healthy : null}
            />
            <TrangThaiHang
              nhan="Worker TTS"
              gia_tri={data.system.inline_worker ? "Trong tiến trình web" : "Tiến trình riêng"}
              tot={null}
            />
            <TrangThaiHang
              nhan="Provider dịch thuật"
              gia_tri={data.system.translation_provider_configured ? "Đã cấu hình" : "Chưa cấu hình"}
              tot={data.system.translation_provider_configured}
            />
            <TrangThaiHang
              nhan="Image Studio Shared Premium"
              gia_tri={
                data.system.image_studio_shared_premium_configured
                  ? "Đã cấu hình"
                  : "Chưa cấu hình"
              }
              tot={data.system.image_studio_shared_premium_configured}
            />
            <p className="hint">
              Trạng thái đọc trực tiếp từ tiến trình backend đang chạy — không
              lưu bản sao riêng, không thể lệch với thực tế.
            </p>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
