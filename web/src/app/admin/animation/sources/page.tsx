"use client";

import { AdminSapXayDung } from "@/components/AdminSapXayDung";

export default function AdminTrustedSources() {
  return (
    <AdminSapXayDung
      tieuDe="Trusted Sources"
      moTa="Thêm/quản lý kênh YouTube tin cậy để tự động phát hiện tập mới (B1–B4: dán URL, xác nhận kênh, ánh xạ series, cấu hình phát hiện tập)."
      giaiDoan="Phần B — Trusted Video Sources"
    />
  );
}
