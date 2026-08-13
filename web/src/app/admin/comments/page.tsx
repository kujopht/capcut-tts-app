"use client";

/**
 * Duyệt bình luận toàn hệ thống — TÁCH được hai loại:
 *
 *   Bình luận bài đăng   → nguồn là /posts/{id}
 *   Bình luận chương     → nguồn là /chapters/{id} (bình luận audio)
 *
 * Người kiểm duyệt cần biết mình đang nhìn gì: một câu "hay quá!" dưới một
 * chương truyện và dưới một bài quảng cáo là hai ngữ cảnh khác nhau. Backend
 * tính sẵn `context_url` — giao diện không tự suy đường dẫn.
 *
 * Gỡ/phục hồi dùng CÙNG đường với mọi bình luận (một lõi bình luận, một đường
 * kiểm duyệt); mọi thao tác vẫn vào nhật ký chung.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, adminSocial, type AdminComment } from "@/lib/api";
import { formatDate } from "@/components/ui";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { dongHo } from "@/lib/time";

const LOAI: ReadonlyArray<{ key: "" | "chapter"; nhan: string }> = [
  { key: "", nhan: "Bình luận bài đăng" },
  { key: "chapter", nhan: "Bình luận chương (audio)" },
];

export default function AdminCommentsPage() {
  const [loai, setLoai] = useState<"" | "chapter">("");
  const [ds, setDs] = useState<AdminComment[] | null>(null);
  const [tong, setTong] = useState(0);
  const [loi, setLoi] = useState("");
  const [dangLam, setDangLam] = useState("");

  const tai = useCallback(() => {
    setLoi("");
    setDs(null);
    adminSocial
      .browseComments(loai)
      .then((r) => {
        setDs(r.items);
        setTong(r.total);
      })
      .catch((e) => {
        setDs([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được danh sách.");
      });
  }, [loai]);

  /* `queueMicrotask` — xem ghi chú ở `admin/reports/page.tsx`. */
  useEffect(() => {
    queueMicrotask(tai);
  }, [tai]);

  const doiTrangThai = useCallback(
    async (bl: AdminComment) => {
      setDangLam(bl.comment_id);
      setLoi("");
      try {
        if (bl.state === "removed") {
          await adminSocial.restoreComment(bl.comment_id);
        } else {
          await adminSocial.removeComment(bl.comment_id, "Vi phạm quy định");
        }
        tai();
      } catch (e) {
        setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
      } finally {
        setDangLam("");
      }
    },
    [tai],
  );

  return (
    <div className="stack">
      <header className="stack-2">
        <h1 className="page-title">Bình luận</h1>
        <p className="hint">{tong} bình luận, mới nhất trước.</p>
      </header>

      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        {LOAI.map((m) => (
          <button
            key={m.key}
            type="button"
            className={loai === m.key ? "btn btn-sm" : "btn btn-ghost btn-sm"}
            aria-pressed={loai === m.key}
            onClick={() => setLoai(m.key)}
          >
            {m.nhan}
          </button>
        ))}
      </div>

      <DanhSachTrangThai
        dangTai={ds === null && !loi}
        loi={loi}
        rong={!!ds && ds.length === 0}
        onThuLai={tai}
      >
        <div className="stack">
          {(ds ?? []).map((bl) => {
            const daGo = bl.state === "removed";
            return (
              <article key={bl.comment_id} className="card stack-2">
                <header className="row bc-dau">
                  <span className="badge">
                    {bl.target_kind === "chapter" ? "Chương" : "Bài đăng"}
                  </span>
                  {bl.timestamp_ms !== null && bl.timestamp_ms !== undefined ? (
                    <span className="badge">
                      ⏱ {dongHo(bl.timestamp_ms / 1000)}
                    </span>
                  ) : null}
                  {bl.spoiler ? <span className="badge">Spoiler</span> : null}
                  <span className={daGo ? "badge" : "badge badge-ok"}>
                    {daGo ? "Đã gỡ" : "Còn hiện"}
                  </span>
                  {bl.open_reports > 0 ? (
                    <span className="badge badge-warn">
                      {bl.open_reports} báo cáo
                    </span>
                  ) : null}
                  <span className="hint">{formatDate(bl.created_at)}</span>
                </header>

                <p className="hint">
                  {bl.author?.username ? (
                    <Link href={`/u/${bl.author.username}`}>
                      {bl.author.display_name || bl.author.username}
                    </Link>
                  ) : (
                    <strong>{bl.author?.display_name || "Người dùng"}</strong>
                  )}
                </p>

                <blockquote className="bc-noi-dung">
                  {bl.text || <em className="hint">(đã gỡ nội dung)</em>}
                </blockquote>

                <footer className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={dangLam === bl.comment_id}
                    onClick={() => doiTrangThai(bl)}
                  >
                    {daGo ? "Phục hồi" : "Gỡ"}
                  </button>
                  {bl.context_url ? (
                    <Link className="btn btn-ghost btn-sm" href={bl.context_url}>
                      Xem nguồn
                    </Link>
                  ) : null}
                </footer>
              </article>
            );
          })}
        </div>
      </DanhSachTrangThai>
    </div>
  );
}
