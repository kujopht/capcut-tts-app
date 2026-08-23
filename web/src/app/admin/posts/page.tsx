"use client";

/**
 * Duyệt bài đăng — kèm đường gỡ/phục hồi.
 *
 * KHÁC `/admin/stories`, màn hình đó CHỈ ĐỌC. Lý do khác nhau: một truyện là
 * công trình dài của một tác giả và luồng takedown cho nó chưa được thiết kế; một
 * bài đăng là một lời nhắn ngắn, và gỡ nó là thao tác đảo lại được trong một cú
 * bấm — hàng vẫn còn, `state` đổi lại là xong.
 *
 * Cột "Báo cáo" cho biết bài nào đang có báo cáo mở, để người kiểm duyệt biết bắt
 * đầu từ đâu khi họ vào bằng cửa này thay vì qua hàng đợi.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, adminSocial, type AdminPost } from "@/lib/api";
import { ConfirmDialog, formatDate, formatNumber } from "@/components/ui";
import { DanhSachTrangThai } from "@/components/AdminShell";

export default function AdminPostsPage() {
  const [q, setQ] = useState("");
  const [tim, setTim] = useState("");
  const [ds, setDs] = useState<AdminPost[] | null>(null);
  const [tong, setTong] = useState(0);
  const [loi, setLoi] = useState("");
  const [dangLam, setDangLam] = useState("");
  const [hoiGo, setHoiGo] = useState<AdminPost | null>(null);
  const [ghiChu, setGhiChu] = useState("");

  const tai = useCallback(() => {
    setLoi("");
    setDs(null);
    adminSocial
      .posts(tim)
      .then((r) => {
        setDs(r.items);
        setTong(r.total);
      })
      .catch((e) => {
        setDs([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được danh sách.");
      });
  }, [tim]);

  /* `queueMicrotask` — xem ghi chú ở `admin/reports/page.tsx`. */
  useEffect(() => {
    queueMicrotask(tai);
  }, [tai]);

  const lamViec = useCallback(
    async (id: string, viec: () => Promise<unknown>) => {
      setDangLam(id);
      setLoi("");
      try {
        await viec();
        tai();
      } catch (e) {
        setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
      } finally {
        setDangLam("");
      }
    },
    [tai],
  );

  const goBai = useCallback(async () => {
    if (!hoiGo) return;
    const id = hoiGo.post_id;
    setDangLam(id);
    setLoi("");
    try {
      await adminSocial.removePost(id, ghiChu.trim() || "Vi phạm quy định");
      setHoiGo(null);
      setGhiChu("");
      tai();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setDangLam("");
    }
  }, [hoiGo, ghiChu, tai]);

  return (
    <div className="stack">
      <header className="stack-2">
        <h1 className="page-title">Bài đăng</h1>
        <p className="hint">{tong} bài, kể cả bài đã gỡ.</p>
      </header>

      <form
        className="row"
        style={{ gap: 8 }}
        onSubmit={(e) => {
          e.preventDefault();
          setTim(q.trim());
        }}
      >
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Tìm trong nội dung bài…"
          aria-label="Tìm bài đăng"
        />
        <button type="submit" className="btn btn-sm">
          Tìm
        </button>
      </form>

      {/*
        BA trang thai qua MOT component dung chung. Moi trang admin tu viet ba
        nhanh thi se co mot trang quen mot nhanh, va cai bi quen luon la "loi".
      */}
      <DanhSachTrangThai
        dangTai={ds === null && !loi}
        loi={loi}
        rong={!!ds && ds.length === 0}
        onThuLai={tai}
      >
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <caption className="sr-only">Danh sách bài đăng</caption>
            <thead>
              <tr>
                <th scope="col">Nội dung</th>
                <th scope="col">Tác giả</th>
                <th scope="col">Tương tác</th>
                <th scope="col">Báo cáo</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {(ds ?? []).map((b) => {
                const daGo = b.state === "removed";
                return (
                  <tr key={b.post_id}>
                    <td>
                      <Link href={`/posts/${b.post_id}`} className="admin-bai-chu">
                        {b.text
                          ? b.text.slice(0, 80) + (b.text.length > 80 ? "…" : "")
                          : "(chỉ có ảnh)"}
                      </Link>
                      <span className="hint">{formatDate(b.created_at)}</span>
                    </td>
                    <td>
                      {b.author?.username ? (
                        <Link href={`/u/${b.author.username}`}>
                          {b.author.display_name || b.author.username}
                        </Link>
                      ) : (
                        b.author?.display_name || "—"
                      )}
                    </td>
                    <td className="hint">
                      ♥ {formatNumber(b.like_count)} · 💬{" "}
                      {formatNumber(b.comment_count)}
                    </td>
                    <td>
                      {b.open_reports > 0 ? (
                        <span className="badge badge-warn">{b.open_reports}</span>
                      ) : (
                        <span className="hint">—</span>
                      )}
                    </td>
                    <td>
                      <span className={daGo ? "badge" : "badge badge-ok"}>
                        {daGo ? "Đã gỡ" : "Còn hiện"}
                      </span>
                      {daGo && b.removed_reason ? (
                        <span className="hint">{b.removed_reason}</span>
                      ) : null}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={dangLam === b.post_id}
                        onClick={() => {
                          if (daGo) {
                            lamViec(b.post_id, () =>
                              adminSocial.restorePost(b.post_id),
                            );
                          } else {
                            setGhiChu("");
                            setHoiGo(b);
                          }
                        }}
                      >
                        {daGo ? "Phục hồi" : "Gỡ"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </DanhSachTrangThai>

      {hoiGo ? (
        <ConfirmDialog
          open
          title="Gỡ bài đăng này?"
          body={
            <span className="stack-2">
              <span>
                Bài đăng sẽ ẩn khỏi công khai ngay lập tức. Có thể phục hồi
                sau bằng nút &quot;Phục hồi&quot; ngay tại đây.
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
          confirmLabel="Gỡ"
          danger
          busy={dangLam === hoiGo.post_id}
          onConfirm={goBai}
          onCancel={() => setHoiGo(null)}
        />
      ) : null}
    </div>
  );
}
