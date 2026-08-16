"use client";

/**
 * Nhat ky kiem duyet — /admin/audit-log (Admin Control Center V2, A5).
 *
 * CHI DOC, va chi THEM o phia may chu (bang `moderation_events`, xem
 * docs/ADMIN.md muc 5). Ton tai vi ban ghi don chi giu trang thai CUOI CUNG
 * — no bi ghi de moi lan co quyet dinh moi; sau ba thang, "vi sao nguoi nay
 * bi treo roi duoc phuc hoi" chi con o day.
 *
 * Loc theo `target_type`/`action`/`target_user_id` — ca ba deu la truy van
 * EQUAL o may chu (khong tim mo), phan trang qua `offset`.
 */

import { useCallback, useState } from "react";
import { adminApi, type AdminAuditAction, type ModerationEvent } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconHistory } from "@/components/Icons";

const TRANG = 50;

/** Nhan hien thi cho HANH DONG da biet — action la string mo (backend co the
    mo rong them), nen dung fallback ve chinh chuoi action khi chua co nhan. */
const NHAN: Partial<Record<AdminAuditAction, { chu: string; lop: string }>> = {
  author_approved: { chu: "Duyệt tác giả", lop: "tt-duyet" },
  author_rejected: { chu: "Từ chối đơn", lop: "tt-tuchoi" },
  author_suspended: { chu: "Tạm dừng tác giả", lop: "tt-treo" },
  author_restored: { chu: "Phục hồi tác giả", lop: "tt-duyet" },
  post_removed: { chu: "Gỡ bài đăng", lop: "tt-treo" },
  post_restored: { chu: "Phục hồi bài đăng", lop: "tt-duyet" },
  comment_removed: { chu: "Gỡ bình luận", lop: "tt-treo" },
  comment_restored: { chu: "Phục hồi bình luận", lop: "tt-duyet" },
  report_resolved: { chu: "Xử lý báo cáo", lop: "tt-duyet" },
  report_dismissed: { chu: "Bỏ qua báo cáo", lop: "tt-trong" },
  user_suspend: { chu: "Treo người dùng", lop: "tt-treo" },
  user_unsuspend: { chu: "Gỡ treo người dùng", lop: "tt-duyet" },
  user_session_terminate: { chu: "Kết thúc phiên", lop: "tt-treo" },
  user_role_change: { chu: "Đổi vai trò", lop: "tt-cho" },
  user_delete: { chu: "Xoá tài khoản", lop: "tt-treo" },
  content_unpublish: { chu: "Gỡ xuất bản nội dung", lop: "tt-treo" },
  content_restore: { chu: "Phục hồi nội dung", lop: "tt-duyet" },
  trusted_source_add: { chu: "Thêm nguồn tin cậy", lop: "tt-duyet" },
  trusted_source_disable: { chu: "Tắt nguồn tin cậy", lop: "tt-treo" },
  trusted_source_enable: { chu: "Bật nguồn tin cậy", lop: "tt-duyet" },
  youtube_mapping_create: { chu: "Tạo ánh xạ YouTube", lop: "tt-duyet" },
  youtube_mapping_update: { chu: "Sửa ánh xạ YouTube", lop: "tt-cho" },
  auto_import_approve: { chu: "Duyệt tự động nhập", lop: "tt-duyet" },
  auto_import_reject: { chu: "Từ chối tự động nhập", lop: "tt-tuchoi" },
  auto_publish_toggle: { chu: "Đổi tự động xuất bản", lop: "tt-cho" },
};

function nhanHanhDong(action: string): { chu: string; lop: string } {
  return NHAN[action as AdminAuditAction] ?? { chu: action, lop: "tt-trong" };
}

export default function AdminAuditLog() {
  const [trangThai, setTrangThai] = useState(0);
  const [locHanhDong, setLocHanhDong] = useState("");
  const [locLoaiDoiTuong, setLocLoaiDoiTuong] = useState("");
  const [locNguoiDung, setLocNguoiDung] = useState("");

  const nap = useCallback(
    () => adminApi.events(TRANG, {
      offset: trangThai * TRANG,
      action: locHanhDong,
      targetType: locLoaiDoiTuong,
      targetUserId: locNguoiDung.trim(),
    }),
    [trangThai, locHanhDong, locLoaiDoiTuong, locNguoiDung],
  );
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds: ModerationEvent[] = data?.events ?? [];
  const tong = data?.total ?? 0;

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconHistory size={19} /> Audit Log
      </h2>

      <form
        className="row row-tight admin-loc"
        onSubmit={(e) => { e.preventDefault(); setTrangThai(0); reload(); }}
      >
        <div className="field">
          <label className="label" htmlFor="loc-hanh-dong">Hành động</label>
          <select
            id="loc-hanh-dong"
            className="input"
            value={locHanhDong}
            onChange={(e) => { setLocHanhDong(e.target.value); setTrangThai(0); }}
          >
            <option value="">— Tất cả —</option>
            {Object.keys(NHAN).map((a) => (
              <option key={a} value={a}>{nhanHanhDong(a).chu}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="loc-loai">Loại đối tượng</label>
          <select
            id="loc-loai"
            className="input"
            value={locLoaiDoiTuong}
            onChange={(e) => { setLocLoaiDoiTuong(e.target.value); setTrangThai(0); }}
          >
            <option value="">— Tất cả —</option>
            <option value="novel">Truyện</option>
            <option value="animation_series">Series Animation</option>
            <option value="trusted_source">Nguồn tin cậy</option>
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="loc-nguoi">Tìm theo user_id</label>
          <input
            id="loc-nguoi"
            className="input"
            value={locNguoiDung}
            onChange={(e) => setLocNguoiDung(e.target.value)}
            placeholder="usr_..."
          />
        </div>
        <button type="submit" className="btn">Lọc</button>
      </form>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={ds.length === 0}
        onThuLai={reload}
      >
        <ul className="admin-nhat-ky">
          {ds.map((e) => {
            const n = nhanHanhDong(e.action);
            return (
              <li key={e.event_id} className="admin-su-kien">
                <span className={`tt ${n.lop}`}>{n.chu}</span>
                <span className="admin-hang-chu">
                  <span className="mono">
                    {e.target_type ? `${e.target_type}:` : ""}
                    {e.target_id || e.target_user_id}
                  </span>
                  {e.actor_role ? (
                    <span className="hint">bởi {e.actor_role}</span>
                  ) : null}
                  {e.note ? <span className="hint">{e.note}</span> : null}
                </span>
                <span className="hint admin-luc">
                  {new Date(e.created_at).toLocaleString("vi-VN")}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="row row-spread">
          <button
            type="button"
            className="btn btn-sm"
            disabled={trangThai === 0}
            onClick={() => setTrangThai((v) => Math.max(0, v - 1))}
          >
            ← Trang trước
          </button>
          <span className="hint">
            Trang {trangThai + 1} · {tong} bản ghi
          </span>
          <button
            type="button"
            className="btn btn-sm"
            disabled={(trangThai + 1) * TRANG >= tong}
            onClick={() => setTrangThai((v) => v + 1)}
          >
            Trang sau →
          </button>
        </div>

        <p className="hint">
          Nhật ký chỉ được thêm, không sửa và không xoá — ở mọi tầng. Nội dung
          này không bao giờ ra API công khai.
        </p>
      </DanhSachTrangThai>
    </section>
  );
}
