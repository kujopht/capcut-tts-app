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
import { adminApi, type AdminTrustedSourceRow } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconLink } from "@/components/Icons";

const TRANG = 25;

const TEN_LOAI: Record<string, string> = {
  youtube_channel: "Kênh YouTube",
  youtube_playlist: "Playlist YouTube",
  youtube_video: "Video đơn lẻ",
  direct_hls: "HLS trực tiếp",
  direct_mp4: "MP4 trực tiếp",
};

export default function AdminTrustedSourcesList() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");
  const [trangThai, setTrangThai] = useState(0);

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
                <th scope="col" className="admin-so">Series ánh xạ</th>
                <th scope="col">Tự động</th>
                <th scope="col">Ngưỡng tin cậy</th>
                <th scope="col">Quét gần nhất</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((s: AdminTrustedSourceRow) => (
                <tr key={s.source_id}>
                  <td>
                    <Link href={`/admin/animation/sources/${s.source_id}`}>
                      {s.display_name || "(chưa đặt tên)"}
                    </Link>
                  </td>
                  <td className="hint">{TEN_LOAI[s.source_type] ?? s.source_type}</td>
                  <td>
                    <span className={`tt ${s.enabled ? "tt-duyet" : "tt-trong"}`}>
                      {s.enabled ? "Đang bật" : "Đã tắt"}
                    </span>
                  </td>
                  <td className="admin-so mono">{s.mapping_count}</td>
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
