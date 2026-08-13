"use client";

/**
 * Quan ly tac gia: ai dang co quyen xuat ban, va ai vua bi dung.
 *
 * CA HAI o cung mot cho co y — tach thanh hai trang bat nguoi quan tri nho mot
 * cai trang thai nay nam o dau.
 *
 * TREO KHONG XOA GI CA. Dong chu duoi bang noi ro dieu do, vi day la thu de bi
 * hieu nham nhat va hau qua cua viec hieu nham la khong sua duoc.
 */

import Link from "next/link";
import { useCallback, useState } from "react";
import { adminApi, type AdminUser } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { RankBadge } from "@/components/AuthorBadge";
import {
  DanhSachTrangThai,
  TrangThaiBadge,
  loiApi,
} from "@/components/AdminShell";
import { ConfirmDialog, formatNumber } from "@/components/ui";
import { IconKey } from "@/components/Icons";

export default function AdminAuthors() {
  const toast = useToast();
  const nap = useCallback(() => adminApi.authors(50), []);
  const { data, loading, error, reload } = useAsyncData(nap);
  const [hoi, setHoi] = useState<AdminUser | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [dangGui, setDangGui] = useState(false);

  const ds = data?.authors ?? [];

  async function treo(u: AdminUser) {
    setDangGui(true);
    try {
      await adminApi.suspend(u.user_id, ghiChu.trim() || "Tạm dừng để rà soát.");
      toast.ok(`Đã tạm dừng quyền xuất bản của ${u.display_name}.`);
      setHoi(null);
      setGhiChu("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không tạm dừng được."));
    } finally {
      setDangGui(false);
    }
  }

  async function phucHoi(u: AdminUser) {
    setDangGui(true);
    try {
      await adminApi.restore(u.user_id, "Phục hồi sau rà soát.");
      toast.ok(`Đã phục hồi ${u.display_name}.`);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không phục hồi được."));
    } finally {
      setDangGui(false);
    }
  }

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconKey size={19} /> Tác giả
      </h2>

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
                <th scope="col">Tác giả</th>
                <th scope="col">Hạng</th>
                <th scope="col" className="admin-so">Lượt nghe</th>
                <th scope="col" className="admin-so">Truyện</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">
                  <span className="sr-only">Thao tác</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {ds.map((u) => (
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
                  <td>{u.rank ? <RankBadge rank={u.rank} size="sm" /> : "—"}</td>
                  <td className="admin-so mono">
                    {formatNumber(u.qualified_listens)}
                  </td>
                  <td className="admin-so mono">{u.published_novels ?? 0}</td>
                  <td>
                    <TrangThaiBadge status={u.author_status} />
                  </td>
                  <td>
                    <span className="row admin-thao-tac">
                      <Link className="btn btn-sm" href={`/u/${u.username}`}>
                        Xem
                      </Link>
                      {u.author_status === "suspended" ? (
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={dangGui}
                          onClick={() => phucHoi(u)}
                        >
                          Phục hồi
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          disabled={dangGui}
                          onClick={() => {
                            setHoi(u);
                            setGhiChu("");
                          }}
                        >
                          Tạm dừng
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="hint">
          <strong>Tạm dừng chỉ chặn xuất bản mới.</strong> Truyện đã xuất bản vẫn
          công khai và người đọc vẫn nghe được; bản nháp, chương và audio đều
          không bị xoá.
        </p>
      </DanhSachTrangThai>

      {hoi ? (
        <ConfirmDialog
          open
          title={`Tạm dừng quyền xuất bản của ${hoi.display_name}?`}
          body={
            <span className="stack-2">
              <span>
                Họ sẽ không xuất bản truyện mới được. Truyện đã đăng vẫn công
                khai, bản nháp và audio không bị xoá.
              </span>
              <textarea
                className="textarea textarea-sm"
                placeholder="Lý do (ghi vào nhật ký kiểm duyệt)"
                value={ghiChu}
                onChange={(e) => setGhiChu(e.target.value)}
                maxLength={1000}
                rows={2}
              />
            </span>
          }
          confirmLabel="Tạm dừng"
          danger
          busy={dangGui}
          onConfirm={() => treo(hoi)}
          onCancel={() => setHoi(null)}
        />
      ) : null}
    </section>
  );
}
