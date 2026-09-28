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
import { useCallback, useEffect, useMemo, useState } from "react";
import { adminApi, type AdminRole, type AdminUser } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  DanhSachTrangThai,
  TrangThaiBadge,
} from "@/components/AdminShell";
import { formatNumber } from "@/components/ui";
import { IconUser } from "@/components/Icons";

const NHAN_VAI_TRO: Record<AdminRole, string> = {
  none: "Không phải quản trị",
  moderator: "Moderator",
  admin: "Admin",
  owner: "Owner",
};

/** Loc VAI TRO chi tren TRANG dang tai — backend `/api/admin/users` khong co
 * tham so loc theo vai tro (chi `q`/`limit`/`offset`), nen day KHONG PHAI
 * phan trang lai theo may chu, chi la loc them tren du lieu THAT da co san
 * (moi hang van mang `admin_role` may chu tinh, khong bia gi ca). */
const LOC_VAI_TRO: ReadonlyArray<{ key: "" | AdminRole; nhan: string }> = [
  { key: "", nhan: "Mọi vai trò" },
  { key: "owner", nhan: "Owner" },
  { key: "admin", nhan: "Admin" },
  { key: "moderator", nhan: "Moderator" },
  { key: "none", nhan: "Không phải quản trị" },
];

export default function AdminUsers() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");
  const [locVaiTro, setLocVaiTro] = useState<"" | AdminRole>("");

  // Giam nhip 250ms — mot cau bay chu la bay request neu khong.
  useEffect(() => {
    const hen = window.setTimeout(() => setTu(go.trim()), 250);
    return () => window.clearTimeout(hen);
  }, [go]);

  const nap = useCallback(() => adminApi.users(tu, 50), [tu]);
  const { data, loading, error, reload } = useAsyncData(nap);
  const dsLoc = useMemo(() => {
    const ds = data?.users ?? [];
    return locVaiTro ? ds.filter((u) => (u.admin_role ?? "none") === locVaiTro) : ds;
  }, [data, locVaiTro]);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconUser size={19} /> Người dùng
      </h2>

      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
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

        <div className="field">
          <label className="label" htmlFor="ad-vai-tro">
            Vai trò quản trị
          </label>
          <select
            id="ad-vai-tro"
            className="input"
            value={locVaiTro}
            onChange={(e) => setLocVaiTro(e.target.value as "" | AdminRole)}
          >
            {LOC_VAI_TRO.map((m) => (
              <option key={m.key} value={m.key}>
                {m.nhan}
              </option>
            ))}
          </select>
        </div>
      </div>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={dsLoc.length === 0}
        onThuLai={reload}
      >
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">Người dùng</th>
                <th scope="col">Email</th>
                <th scope="col">Vai trò quản trị</th>
                <th scope="col">Trạng thái tác giả</th>
                <th scope="col">Trạng thái tài khoản</th>
                <th scope="col" className="admin-so">Lượt nghe</th>
                <th scope="col" className="admin-so">Truyện</th>
              </tr>
            </thead>
            <tbody>
              {dsLoc.map((u: AdminUser) => (
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
                    {u.admin_role && u.admin_role !== "none" ? (
                      <span className={`badge admin-badge-vaitro admin-badge-${u.admin_role}`}>
                        {NHAN_VAI_TRO[u.admin_role]}
                      </span>
                    ) : (
                      <span className="hint">—</span>
                    )}
                  </td>
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
