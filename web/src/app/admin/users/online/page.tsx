"use client";

/**
 * Trang quan tri "User online".
 *
 * Danh sach user kem moc hien dien (`last_seen_at`, `is_online` do may chu
 * tinh — moc trong 5 phut qua). Sap xep (online len dau, roi theo last_seen
 * moi nhat) do MAY CHU lam trong trang da lay.
 *
 * Tim o MAY CHU, giam nhip go (giong `/admin/users`). Tu dong tai lai
 * 60s/lan de cham online khong cu; "2 phut truoc" tick 30s/lan o client
 * ma khong goi API. Nut "Tai them" mo rong cua so (50 user/trang) thay vi
 * phan trang co dinh — voi luong user hien tai mot cua so bao het.
 *
 * Email CHI o day va `/admin/users` (ca hai deu sau `Depends`
 * admin) — khong mot API cong khai nao co truong do.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminUserOnline } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  DanhSachTrangThai,
} from "@/components/AdminShell";
import { formatDateTimeSG, formatNumber, formatRelative } from "@/lib/format";
import { IconUser } from "@/components/Icons";

const GIOI_HAN_TRANG = 50;

export default function AdminUsersOnline() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");
  const [soTrang, setSoTrang] = useState(1);
  const [bayGio, setBayGio] = useState(() => Date.now());

  // Giam nhip 250ms — mot cau bay chu la bay request neu khong.
  useEffect(() => {
    const hen = window.setTimeout(() => setTu(go.trim()), 250);
    return () => window.clearTimeout(hen);
  }, [go]);

  // "2 phut truoc" phai gia theo thoi gian that — tick 30s/lan, khong goi API.
  useEffect(() => {
    const hen = window.setInterval(() => setBayGio(Date.now()), 30_000);
    return () => window.clearInterval(hen);
  }, []);

  // `useAsyncData` GIU data cu trong luc nap lai, nen lan tai lai dinh ky
  // va "Tai them" khong lam ca bang nhay ve trang thai dang tai.
  const nap = useCallback(
    () => adminApi.usersOnline(tu, GIOI_HAN_TRANG * soTrang, 0),
    [tu, soTrang],
  );
  const { data, loading, error, reload, setData } = useAsyncData(nap);

  // Tu dong tai lai 60s/lan de cham online khong cu — chi khi tab dang hien.
  // Dung `setData` (khong dung `reload()`) de khong bat co `loading` lam
  // ca bang nhay ve man hinh dang tai; loi mang duoc nuot im.
  useEffect(() => {
    const hen = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      adminApi.usersOnline(tu, GIOI_HAN_TRANG * soTrang, 0)
        .then((d) => setData(() => d))
        .catch(() => {});
    }, 60_000);
    return () => window.clearInterval(hen);
  }, [tu, soTrang, setData]);
  const ds: AdminUserOnline[] = data?.users ?? [];
  const dangOnline = ds.filter((u) => u.is_online).length;
  const conThem = (data?.total ?? 0) > ds.length;

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconUser size={19} /> User online
      </h2>

      <p className="hint">
        Đang online: <strong>{formatNumber(dangOnline)}</strong>
        {" / "}
        {formatNumber(data?.total ?? 0)} tài khoản
        {" — "}
        moc trong 5 phút qua tính là đang online.
      </p>

      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="field">
          <label className="label" htmlFor="ad-tim-online">
            Tìm theo email, tên hiển thị hoặc tên công khai
          </label>
          <input
            id="ad-tim-online"
            className="input"
            type="search"
            value={go}
            onChange={(e) => {
              setGo(e.target.value);
              setSoTrang(1);
            }}
            placeholder="Ví dụ: nam kujo"
            autoComplete="off"
          />
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
                <th scope="col">Người dùng</th>
                <th scope="col">Email</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">Lần online gần nhất</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((u) => (
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
                  {/* CHI o day va `/admin/users`. Xem ghi chu o dau tep. */}
                  <td className="mono admin-email">{u.email}</td>
                  <td>
                    {u.is_online ? (
                      <span className="tt tt-duyet">
                        <span
                          className="dot dot-pulse"
                          style={{ color: "#4ade80", marginRight: 6 }}
                          aria-hidden="true"
                        />
                        Đang online
                      </span>
                    ) : (
                      <span className="hint">Ngoại tuyến</span>
                    )}
                  </td>
                  <td>
                    <span className="admin-hang-chu">
                      <strong>{formatRelative(u.last_seen_at, bayGio)}</strong>
                      <span className="hint mono">
                        {u.last_seen_at
                          ? formatDateTimeSG(u.last_seen_at)
                          : "—"}
                      </span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {conThem ? (
          <div className="row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setSoTrang((s) => s + 1)}
            >
              Tải thêm ({formatNumber(ds.length)}/
              {formatNumber(data?.total ?? 0)})
            </button>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
