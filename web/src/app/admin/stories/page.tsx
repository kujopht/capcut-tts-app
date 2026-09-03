"use client";

/**
 * Duyet truyen — CHI DOC.
 *
 * KHONG co nut go xuong hay xoa, va do la mot quyet dinh chu khong phai mot viec
 * con thieu: backend chua co luong takedown nao an toan. Dat mot nut xoa len mot
 * luong chua thiet ke la cach nhanh nhat de mat noi dung cua nguoi khac — va noi
 * dung do la cong viec cua ho.
 *
 * Khi lam takedown, nhung thu can co TRUOC cai nut: mot trang thai `removed`
 * tach khoi `draft` (de tac gia biet no bi go chu khong phai ho tu ha xuong),
 * mot ban ghi ly do, mot duong khieu nai, va mot cach hoan tac. Xem
 * `docs/ADMIN.md`.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { adminApi } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { IconBook } from "@/components/Icons";

const TRANG_THAI = [
  { khoa: "", nhan: "Tất cả" },
  { khoa: "published", nhan: "Đã xuất bản" },
  { khoa: "draft", nhan: "Bản nháp" },
];

/**
 * Ten mien cua nguon, de o "Nguồn" doc duoc trong mot bang.
 *
 * URL day du cua Wattpad/Fandom dai hon ca o ban ghi; ten mien la phan nguoi
 * quan tri thuc su can doc nhanh, con URL day du van nam o `title` va o chinh
 * lien ket. `www.` bi bo vi no khong phan biet gi.
 *
 * URL rac thi tra ve nguyen van thay vi nem loi: mot dong bang khong duoc phep
 * lam sap ca trang quan tri.
 */
function nhanNguon(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function AdminStories() {
  const [go, setGo] = useState("");
  const [tu, setTu] = useState("");
  const [tt, setTt] = useState("");

  useEffect(() => {
    const hen = window.setTimeout(() => setTu(go.trim()), 250);
    return () => window.clearTimeout(hen);
  }, [go]);

  const nap = useCallback(() => adminApi.novels(tu, tt, 50), [tu, tt]);
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds = data?.novels ?? [];

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconBook size={19} /> Truyện
      </h2>

      <div className="row">
        <input
          className="input"
          type="search"
          value={go}
          onChange={(e) => setGo(e.target.value)}
          placeholder="Tìm theo tên truyện…"
          aria-label="Tìm truyện"
          autoComplete="off"
        />
      </div>

      <div className="seg admin-loc" role="group" aria-label="Lọc theo trạng thái">
        {TRANG_THAI.map((t) => (
          <button
            key={t.khoa || "all"}
            type="button"
            className="seg-item"
            aria-pressed={tt === t.khoa}
            onClick={() => setTt(t.khoa)}
          >
            {t.nhan}
          </button>
        ))}
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
                <th scope="col">Truyện</th>
                <th scope="col">Tác giả</th>
                <th scope="col" className="admin-so">Chương</th>
                {/* Quyet dinh xuat ban can biet audio da san sang bao nhieu. */}
                <th scope="col" className="admin-so">Audio</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">Nguồn</th>
                <th scope="col">Cập nhật</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((n) => (
                <tr key={n.novel_id}>
                  <td>
                    <Link href={`/novels/${n.novel_id}`}>{n.title}</Link>
                  </td>
                  <td>
                    {n.owner ? (
                      <Link href={`/u/${n.owner.username}`} className="hint mono">
                        @{n.owner.username}
                      </Link>
                    ) : (
                      <span className="hint">—</span>
                    )}
                  </td>
                  <td className="admin-so mono">{n.chapters}</td>
                  {/*
                    "x/y", khong phai mot dau tich. Mot truyen 3/15 chuong co
                    audio va mot truyen 15/15 deu se hien "co audio" neu chi ve
                    boolean — trong khi day dung la con so de quyet dinh xuat
                    ban hay cho.

                    `undefined` (backend cu chua tra truong nay) hien "—", KHONG
                    hien "0/15": khong biet va biet-la-khong khac nhau.
                  */}
                  <td className="admin-so mono">
                    {n.chapters_with_audio === undefined ? (
                      <span className="hint">—</span>
                    ) : (
                      <span
                        className={
                          n.chapters > 0 && n.chapters_with_audio === n.chapters
                            ? "tt tt-duyet"
                            : n.chapters_with_audio === 0
                              ? "hint"
                              : undefined
                        }
                      >
                        {n.chapters_with_audio}/{n.chapters}
                      </span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`tt ${n.state === "published" ? "tt-duyet" : "tt-trong"}`}
                    >
                      {n.state === "published" ? "Đã xuất bản" : "Bản nháp"}
                    </span>
                  </td>
                  {/*
                    Xuat xu. Voi noi dung nhap tu noi khac, "no den tu dau" la
                    dieu quan tri phai kiem duoc TRUOC khi bam xuat ban — khong
                    phai thu di tra o mot trang khac.
                  */}
                  <td>
                    {n.external_source_url ? (
                      <a
                        href={n.external_source_url}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="hint"
                        title={n.external_source_url}
                      >
                        {nhanNguon(n.external_source_url)} ↗
                      </a>
                    ) : (
                      <span className="hint">—</span>
                    )}
                  </td>
                  <td className="hint">
                    {new Date(n.updated_at).toLocaleDateString("vi-VN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="hint">
          Khu này <strong>chỉ để xem</strong>. Chưa có thao tác gỡ xuống — cần
          một trạng thái “bị gỡ” tách khỏi “bản nháp”, một bản ghi lý do, một
          đường khiếu nại và một cách hoàn tác trước khi thêm cái nút đó.
        </p>
      </DanhSachTrangThai>
    </section>
  );
}
