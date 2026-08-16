"use client";

import { AdminSapXayDung } from "@/components/AdminSapXayDung";

export default function AdminImportQueue() {
  return (
    <AdminSapXayDung
      tieuDe="Import Queue"
      moTa="Hàng đợi tập được WebSub phát hiện tự động — chờ duyệt thủ công khi độ tin cậy chưa đủ để tự động nhập (B4–B6)."
      giaiDoan="Phần B — Trusted Video Sources / YouTube Auto-Sync"
    />
  );
}
