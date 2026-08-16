"use client";

/**
 * Tra cuu tai khoan.
 *
 * Day la duong DUY NHAT trong ca san pham co `email`. Moi API cong khai —
 * `/api/users/*`, `/api/search/people` — deu khong co truong do, va mot bai test
 * o backend doi chieu hai duong canh nhau de giu dieu do.
 *
 * Tim o MAY CHU, giam nhip go: cung mot ly do voi overlay tim kiem cong khai.
 *
 * Nguon la Appwrite Users API (native, Phase 3) — hien CA tai khoan chua
 * chon username, khac ban Phase 2 chi thay nguoi da co ho so cong khai. Bam
 * vao mot hang de sang trang chi tiet (`/admin/users/[user_id]`), noi co
 * thao tac tam dung tai khoan / cham dut phien.
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
          Tìm theo email, tên hiển thị hoặc tên công khai
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
                <th scope="col">Trạng thái tài khoản</th>
                <th scope="col" className="admin-so">Lượt nghe</th>
                <th scope="col" className="admin-so">Truyện</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((u: AdminUser) => (
                <tr key={u.user_id}>
                  <td>
                    <Link href={`/admin/users/${u.user_id}`} className="admin-nguoi">
                      <span className="admin-avt" aria-hidden="true">
                        {(u.display_name || u.username || u.email)
                          .slice(0, 2).toUpperCase()}
                      </span>
                      <span className="admin-hang-chu">
                        <strong>{u.display_name || "(chưa đặt tên)"}</strong>
                        <span className="hint mono">
                          {u.username ? `@${u.username}` : "chưa chọn tên công khai"}
                        </span>
                      </span>
                    </Link>
                  </td>
                  {/* CHI o day. Xem ghi chu o dau tep. */}
                  <td className="mono admin-email">{u.email}</td>
                  <td>
                    <TrangThaiBadge status={u.author_status} />
                  </td>
                  <td>
                    <span className={`tt ${u.account_enabled === false ? "tt-treo" : "tt-duyet"}`}>
                      {u.account_enabled === false ? "Đã tạm dừng" : "Hoạt động"}
                    </span>
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
