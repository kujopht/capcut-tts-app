"use client";

/**
 * Khoi "sap xay dung" dung chung cho cac trang quan tri MOI TRONG SIDEBAR
 * nhung CHUA co logic nghiep vu (Admin Control Center V2, Phase 2 — cau
 * truc dieu huong xong truoc, tung trang duoc lap day o cac giai doan sau).
 *
 * KHONG gia du lieu: day la mot thong bao ro rang ve TRANG THAI, khong phai
 * mot trang rong bo quen.
 */

import { IconGear } from "@/components/Icons";

export function AdminSapXayDung({
  tieuDe,
  moTa,
  giaiDoan,
}: {
  tieuDe: string;
  moTa: string;
  /** Vi du "Phần B — Trusted Video Sources". */
  giaiDoan: string;
}) {
  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconGear size={19} /> {tieuDe}
      </h2>
      <div className="card stack-2" role="status">
        <strong>Sắp xây dựng</strong>
        <p className="hint">{moTa}</p>
        <p className="hint">Sẽ triển khai ở: {giaiDoan}.</p>
      </div>
    </section>
  );
}
