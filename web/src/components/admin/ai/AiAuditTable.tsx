"use client";

/**
 * Nhật ký thay đổi cấu hình AI — mỗi dòng một TRƯỜNG. Giá trị là cấu hình
 * không bí mật (server không bao giờ ghi khoá vào audit), nên hiện nguyên văn.
 */

import type { AiAuditItem } from "@/lib/admin/aiControl";

function gio(iso: string): string {
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? iso : t.toLocaleString("vi-VN");
}

export function AiAuditTable({ items }: { items: AiAuditItem[] }) {
  if (items.length === 0) {
    return (
      <div className="card admin-khong-viec" role="status">
        Chưa có thay đổi nào được ghi — mọi lần lưu trên trang này sẽ hiện ở đây.
      </div>
    );
  }
  return (
    <div className="admin-bang-boc">
      <table className="admin-bang ai-admin-audit">
        <thead>
          <tr>
            <th scope="col">Thời điểm</th>
            <th scope="col">Người sửa</th>
            <th scope="col">Đối tượng</th>
            <th scope="col">Trường</th>
            <th scope="col">Cũ → Mới</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a, i) => (
            <tr key={`${a.at}-${a.entity}-${a.field}-${i}`}>
              <td data-nhan="Thời điểm">{gio(a.at)}</td>
              <td data-nhan="Người sửa"><code>{a.admin_id}</code></td>
              <td data-nhan="Đối tượng">{a.entity}</td>
              <td data-nhan="Trường">{a.field}</td>
              <td data-nhan="Cũ → Mới" className="ai-admin-doi">
                <span className="hint">{a.old_value || "—"}</span> → <strong>{a.new_value || "—"}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
