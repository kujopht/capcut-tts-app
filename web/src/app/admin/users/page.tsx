"use client";

/**
 * Tra cuu nguoi dung.
 *
 * Day la duong DUY NHAT trong ca san pham co `email`. Moi API cong khai —
 * `/api/users/*`, `/api/search/people` — deu khong co truong do, va mot bai test
 * o backend doi chieu hai duong canh nhau de giu dieu do.
 *
 * Tim o MAY CHU, giam nhip go: cung mot ly do voi overlay tim kiem cong khai.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminUser } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  DanhSachTrangThai,
  TrangThaiBadge,
} from "@/components/AdminShell";
import { formatNumber } from "@/components/ui";
import { IconUser } from "@/components/Icons";

export default function AdminUsers() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");

  // Giam nhip 250ms — mot cau bay chu la bay request neu khong.
  useEffect(() => {
    const hen = window.setTimeout(() => setTu(go.trim()), 250);
    return () => window.clearTimeout(hen);
  }, [go]);

  const nap = useCallback(() => adminApi.users(tu, 50), [tu]);
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds = data?.users ?? [];

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconUser size={19} /> Người dùng
      </h2>

      <div className="field">
        <label className="label" htmlFor="ad-tim">
          Tìm theo tên hiển thị hoặc tên công khai
        </label>
        <input
          id="ad-tim"
          className="input"
          type="search"
          value={go}
          onChange={(e) => setGo(e.target.value)}
          placeholder="Ví dụ: nam kujo"
          autoComplete="off"
        />
        <p className="hint">
          Chỉ tìm được người đã chọn tên công khai — người chưa chọn thì chưa có
          hồ sơ công khai nào để tra.
        </p>
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
                <th scope="col">Người dùng</th>
                <th scope="col">Email</th>
                <th scope="col">Trạng thái tác giả</th>
                <th scope="col" className="admin-so">Lượt nghe</th>
                <th scope="col" className="admin-so">Truyện</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((u: AdminUser) => (
                <tr key={u.user_id}>
                  <td>
                    <span className="admin-nguoi">
                      <span className="admin-avt" aria-hidden="true">
                        {(u.display_name || u.username).slice(0, 2).toUpperCase()}
                      </span>
                      <span className="admin-hang-chu">
                        <strong>{u.display_name}</strong>
                        <Link href={`/u/${u.username}`} className="hint mono">
                          @{u.username}
                        </Link>
                      </span>
                    </span>
                  </td>
                  {/* CHI o day. Xem ghi chu o dau tep. */}
                  <td className="mono admin-email">{u.email}</td>
                  <td>
                    <TrangThaiBadge status={u.author_status} />
                  </td>
                  <td className="admin-so mono">
                    {formatNumber(u.qualified_listens)}
                  </td>
                  <td className="admin-so mono">{u.published_novels ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DanhSachTrangThai>
    </section>
  );
}
