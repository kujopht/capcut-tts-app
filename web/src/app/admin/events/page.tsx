"use client";

/**
 * Nhat ky kiem duyet. CHI DOC, va chi THEM o phia may chu.
 *
 * Ton tai vi ban ghi don chi giu trang thai CUOI CUNG — no bi ghi de moi lan co
 * quyet dinh moi. Sau ba thang, "vi sao nguoi nay bi treo roi duoc phuc hoi" chi
 * con o day.
 */

import { useCallback } from "react";
import { adminApi, type ModerationEvent } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconHistory } from "@/components/Icons";

const NHAN: Record<ModerationEvent["action"], { chu: string; lop: string }> = {
  author_approved: { chu: "Duyệt tác giả", lop: "tt-duyet" },
  author_rejected: { chu: "Từ chối đơn", lop: "tt-tuchoi" },
  author_suspended: { chu: "Tạm dừng", lop: "tt-treo" },
  author_restored: { chu: "Phục hồi", lop: "tt-duyet" },
};

export default function AdminEvents() {
  const nap = useCallback(() => adminApi.events(100), []);
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds = data?.events ?? [];

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconHistory size={19} /> Nhật ký kiểm duyệt
      </h2>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={ds.length === 0}
        onThuLai={reload}
      >
        <ul className="admin-nhat-ky">
          {ds.map((e) => {
            const n = NHAN[e.action];
            return (
              <li key={e.event_id} className="admin-su-kien">
                <span className={`tt ${n.lop}`}>{n.chu}</span>
                <span className="admin-hang-chu">
                  <span className="mono">{e.target_user_id}</span>
                  {e.note ? <span className="hint">{e.note}</span> : null}
                </span>
                <span className="hint admin-luc">
                  {new Date(e.created_at).toLocaleString("vi-VN")}
                </span>
              </li>
            );
          })}
        </ul>

        <p className="hint">
          Nhật ký chỉ được thêm, không sửa và không xoá — ở mọi tầng. Nội dung
          này không bao giờ ra API công khai.
        </p>
      </DanhSachTrangThai>
    </section>
  );
}
