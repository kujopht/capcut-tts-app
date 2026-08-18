"use client";

/**
 * Danh sach Trusted Video Sources (Phase 5, Admin Control Center V2).
 *
 * Doc lap voi trang cong khai — day la khu XAC NHAN TIN CAY, chi ADMIN/OWNER
 * moi them/sua/xoa duoc (xem `admin_or_owner_profile` phia server); MODERATOR
 * chi xem. Xem chi tiet mot nguon o `/admin/animation/sources/[id]`.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminTrustedSourceRow, type SubscriptionStatus } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { IconLink } from "@/components/Icons";

const TRANG = 25;

const TEN_LOAI: Record<string, string> = {
  youtube_channel: "Kênh YouTube",
  youtube_playlist: "Playlist YouTube",
  youtube_video: "Video đơn lẻ",
  direct_hls: "HLS trực tiếp",
  direct_mp4: "MP4 trực tiếp",
};

/** Cung nhan/mau voi trang chi tiet nguon (`sources/[id]/page.tsx`) — dat
    lai o day de danh sach cung hien duoc trang thai WebSub gon. Khong tach
    thanh module dung chung: chi hai noi dung, cung quy uoc voi `TEN_LOAI`
    o tren (moi trang tu khai bao bang tra cuu rieng, khong import chung). */
const NHAN_DANG_KY: Record<SubscriptionStatus, { chu: string; lop: string }> = {
  none: { chu: "Chưa đăng ký", lop: "tt-trong" },
  pending: { chu: "Đang chờ xác minh", lop: "tt-cho" },
  active: { chu: "Đang hoạt động", lop: "tt-duyet" },
  expired: { chu: "Đã hết hạn", lop: "tt-treo" },
  failed: { chu: "Lỗi", lop: "tt-tuchoi" },
};

export default function AdminTrustedSourcesList() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");
  const [trangThai, setTrangThai] = useState(0);
  const toast = useToast();
  const [dangDoiTrangThai, setDangDoiTrangThai] = useState<string | null>(null);

  useEffect(() => {
    const hen = window.setTimeout(() => setTu(go.trim()), 250);
    return () => window.clearTimeout(hen);
  }, [go]);

  const nap = useCallback(
    () => adminApi.trustedSources({ q: tu, limit: TRANG, offset: trangThai * TRANG }),
    [tu, trangThai],
  );
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds = data?.sources ?? [];
  const tong = data?.total ?? 0;

  /**
   * Tam dung/tiep tuc NGAY tren danh sach — truoc day phai vao trang chi
   * tiet moi doi duoc trang thai. Dung LAI `adminApi.setTrustedSourceEnabled`
   * da co san (cung route `admin_or_owner_profile` gac o server, xem trang
   * chi tiet), khong tu tao mot co che phan quyen rieng o day.
   */
  const datBatTat = useCallback(async (sourceId: string, enabled: boolean) => {
    setDangDoiTrangThai(sourceId);
    try {
      await adminApi.setTrustedSourceEnabled(sourceId, enabled);
      toast.ok(enabled ? "Đã tiếp tục nguồn." : "Đã tạm dừng nguồn.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không đổi được trạng thái."));
    } finally {
      setDangDoiTrangThai(null);
    }
  }, [toast, reload]);

  return (
    <section className="stack">
      <div className="row row-spread">
        <h2 className="section-title section-title-icon">
          <IconLink size={19} /> Trusted Video Sources
        </h2>
        <Link href="/admin/animation/sources/new" className="btn btn-primary btn-sm">
          + Thêm nguồn tin cậy
        </Link>
      </div>
      <p className="hint">
        <Link href="/admin/animation">← Animation</Link>
      </p>
      <p className="hint">
        Kênh/playlist/video YouTube được quản trị XÁC NHẬN tin cậy để phát
        hiện tập mới. Một video do tác giả thường nộp KHÔNG BAO GIỜ tự biến
        kênh của họ thành tin cậy — đó luôn là một quyết định quản trị riêng.
      </p>

      <div className="row">
        <input
          className="input"
          type="search"
          value={go}
          onChange={(e) => { setGo(e.target.value); setTrangThai(0); }}
          placeholder="Tìm theo tên nguồn…"
          aria-label="Tìm nguồn tin cậy"
          autoComplete="off"
        />
      </div>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={ds.length === 0} onThuLai={reload}>
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">Tên</th>
                <th scope="col">Loại</th>
                <th scope="col">Bật</th>
                <th scope="col">WebSub</th>
                <th scope="col" className="admin-so">Series ánh xạ</th>
                <th scope="col" className="admin-so">Đã nhập</th>
                <th scope="col" className="admin-so">Đã xuất bản</th>
                <th scope="col">Tự động</th>
                <th scope="col">Ngưỡng tin cậy</th>
                <th scope="col">Quét gần nhất</th>
                <th scope="col"><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {ds.map((s: AdminTrustedSourceRow) => (
                <tr key={s.source_id}>
                  <td>
                    <Link href={`/admin/animation/sources/${s.source_id}`} className="admin-nguoi">
                      {s.thumbnail_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- thumbnail kenh YouTube that, mien phi khong can toi uu Next/Image cho anh nho trang tri.
                        <img src={s.thumbnail_url} alt="" className="admin-avt admin-avt-img" width={32} height={32} />
                      ) : (
                        <span className="admin-avt" aria-hidden="true">
                          {(s.display_name || s.youtube_channel_id || "?").slice(0, 2).toUpperCase()}
                        </span>
                      )}
                      <span className="admin-hang-chu">
                        <strong>{s.display_name || "(chưa đặt tên)"}</strong>
                      </span>
                    </Link>
                  </td>
                  <td className="hint">{TEN_LOAI[s.source_type] ?? s.source_type}</td>
                  <td>
                    <span className={`tt ${s.enabled ? "tt-duyet" : "tt-trong"}`}>
                      {s.enabled ? "Đang bật" : "Đã tạm dừng"}
                    </span>
                  </td>
                  <td>
                    <span className={`tt ${NHAN_DANG_KY[s.subscription_status].lop}`}>
                      {NHAN_DANG_KY[s.subscription_status].chu}
                    </span>
                  </td>
                  <td className="admin-so mono">{s.mapping_count}</td>
                  <td className="admin-so mono">{s.imported_count}</td>
                  <td className="admin-so mono">{s.published_count}</td>
                  <td className="hint mono">
                    {[s.auto_discover && "Discover", s.auto_import && "Import",
                     s.auto_publish && "Publish"].filter(Boolean).join(" · ") || "—"}
                  </td>
                  <td className="mono">{Math.round(s.minimum_confidence * 100)}%</td>
                  <td className="hint">
                    {s.last_scan_at
                      ? new Date(s.last_scan_at).toLocaleString("vi-VN")
                      : "Chưa quét lần nào"}
                    {s.last_error_at && s.last_error_at > s.last_success_at ? (
                      <span className="tt tt-tuchoi" style={{ marginLeft: 6 }}>Lỗi</span>
                    ) : null}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={dangDoiTrangThai === s.source_id}
                      onClick={() => datBatTat(s.source_id, !s.enabled)}
                    >
                      {dangDoiTrangThai === s.source_id
                        ? "Đang lưu…"
                        : s.enabled ? "Tạm dừng" : "Tiếp tục"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="row row-spread">
          <button type="button" className="btn btn-sm" disabled={trangThai === 0}
                  onClick={() => setTrangThai((v) => Math.max(0, v - 1))}>
            ← Trang trước
          </button>
          <span className="hint">Trang {trangThai + 1} · {tong} nguồn</span>
          <button type="button" className="btn btn-sm"
                  disabled={(trangThai + 1) * TRANG >= tong}
                  onClick={() => setTrangThai((v) => v + 1)}>
            Trang sau →
          </button>
        </div>
      </DanhSachTrangThai>
    </section>
  );
}
