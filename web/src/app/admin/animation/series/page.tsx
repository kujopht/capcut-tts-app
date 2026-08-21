"use client";

/**
 * Danh sach series Animation cho khu quan tri (Phase 4, Admin Control Center V2).
 *
 * KHAC ban cong khai (`/animation`): thay MOI chu so huu (khong chi cua
 * rieng minh), phan trang/tim kiem/loc/sap xep o phia MAY CHU — khong bao
 * gio tai het roi cat o trinh duyet. Xem `SocialService.admin_animation_series`.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminAnimationSeriesRow } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconFilm } from "@/components/Icons";

const TRANG_THAI: ReadonlyArray<{ khoa: "" | "draft" | "published"; nhan: string }> = [
  { khoa: "", nhan: "Tất cả" },
  { khoa: "published", nhan: "Đã xuất bản" },
  { khoa: "draft", nhan: "Bản nháp" },
];

const TRANG = 25;

export default function AdminAnimationSeriesList() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");
  const [tt, setTt] = useState<"" | "draft" | "published">("");
  const [sap, setSap] = useState<"newest" | "oldest">("newest");
  const [trangThai, setTrangThai] = useState(0);

  useEffect(() => {
    const hen = window.setTimeout(() => setTu(go.trim()), 250);
    return () => window.clearTimeout(hen);
  }, [go]);

  const nap = useCallback(
    () => adminApi.animationSeries({
      q: tu, state: tt, sort: sap, limit: TRANG, offset: trangThai * TRANG,
    }),
    [tu, tt, sap, trangThai],
  );
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds = data?.series ?? [];
  const tong = data?.total ?? 0;

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconFilm size={19} /> Series Animation
      </h2>
      <p className="hint">
        <Link href="/admin/animation">← Animation</Link>
      </p>

      <div className="row">
        <input
          className="input"
          type="search"
          value={go}
          onChange={(e) => { setGo(e.target.value); setTrangThai(0); }}
          placeholder="Tìm theo tên series…"
          aria-label="Tìm series"
          autoComplete="off"
        />
      </div>

      <div className="row row-spread row-tight">
        <div className="seg" role="group" aria-label="Lọc theo trạng thái">
          {TRANG_THAI.map((t) => (
            <button
              key={t.khoa || "all"}
              type="button"
              className="seg-item"
              aria-pressed={tt === t.khoa}
              onClick={() => { setTt(t.khoa); setTrangThai(0); }}
            >
              {t.nhan}
            </button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Sắp xếp">
          <button type="button" className="seg-item" aria-pressed={sap === "newest"}
                  onClick={() => setSap("newest")}>
            Mới nhất
          </button>
          <button type="button" className="seg-item" aria-pressed={sap === "oldest"}
                  onClick={() => setSap("oldest")}>
            Cũ nhất
          </button>
        </div>
      </div>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={ds.length === 0}
        onThuLai={reload}
      >
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">Series</th>
                <th scope="col">Chủ sở hữu</th>
                <th scope="col">Truyện liên kết</th>
                <th scope="col" className="admin-so">Tập</th>
                <th scope="col">Xuất bản</th>
                <th scope="col">Kiểm duyệt</th>
                <th scope="col">Cập nhật</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((s: AdminAnimationSeriesRow) => (
                <tr key={s.series_id}>
                  <td>
                    <Link href={`/admin/animation/series/${s.series_id}`}>
                      {s.title}
                    </Link>
                  </td>
                  <td>
                    {s.owner?.username ? (
                      <Link href={`/u/${s.owner.username}`} className="hint mono">
                        @{s.owner.username}
                      </Link>
                    ) : s.owner ? (
                      <span className="hint">{s.owner.display_name} (chưa chọn tên công khai)</span>
                    ) : (
                      <span className="hint">—</span>
                    )}
                  </td>
                  <td>
                    {s.related_novel ? (
                      <Link href={`/novels/${s.related_novel.novel_id}`} className="hint">
                        {s.related_novel.title}
                      </Link>
                    ) : (
                      <span className="hint">—</span>
                    )}
                  </td>
                  <td className="admin-so mono">{s.episode_count}</td>
                  <td>
                    <span className={`tt ${s.state === "published" ? "tt-duyet" : "tt-trong"}`}>
                      {s.state === "published" ? "Đã xuất bản" : "Bản nháp"}
                    </span>
                  </td>
                  <td>
                    <span className={`tt ${s.moderation_state === "removed" ? "tt-treo" : "tt-duyet"}`}>
                      {s.moderation_state === "removed" ? "Đã gỡ" : "Bình thường"}
                    </span>
                  </td>
                  <td className="hint">
                    {new Date(s.updated_at).toLocaleDateString("vi-VN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

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
            Trang {trangThai + 1} · {tong} series
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
      </DanhSachTrangThai>
    </section>
  );
}
