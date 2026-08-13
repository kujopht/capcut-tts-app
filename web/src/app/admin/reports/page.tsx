"use client";

/**
 * Hàng đợi báo cáo nội dung.
 *
 * BA điều quyết định thiết kế màn hình này:
 *
 * 1. NỘI DUNG BỊ BÁO CÁO HIỆN NGAY TẠI ĐÂY.
 *
 *    Backend ghép sẵn nó vào (`ContentReport.content`). Nếu người kiểm duyệt phải
 *    bấm sang một trang khác để xem nội dung rồi bấm về để xử lý, họ sẽ xử lý
 *    dựa trên LÝ DO người báo cáo viết chứ không dựa trên nội dung thật — và
 *    đó chính là cách một nút Báo cáo biến thành công cụ xoá nội dung.
 *
 * 2. GỠ và ĐÓNG BÁO CÁO là HAI thao tác.
 *
 *    Một báo cáo có thể được đóng mà không gỡ gì (không vi phạm), và một nội dung
 *    có thể bị gỡ vì lý do khác. Gộp hai nút thành một sẽ khiến "đã xem, không
 *    vi phạm" không biểu đạt được.
 *
 * 3. GỠ, không XOÁ.
 *
 *    Không có nút xoá thật ở đây. Một quyết định kiểm duyệt không còn bằng chứng
 *    thì không xem lại được khi bị khiếu nại — xem `domain.ContentState`.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  adminSocial,
  type ContentReport,
} from "@/lib/api";
import { formatDate } from "@/components/ui";
import { DanhSachTrangThai } from "@/components/AdminShell";

const LOC: ReadonlyArray<{ key: string; nhan: string }> = [
  { key: "open", nhan: "Đang mở" },
  { key: "resolved", nhan: "Đã xử lý" },
  { key: "dismissed", nhan: "Đã bỏ qua" },
  { key: "all", nhan: "Tất cả" },
];

const TEN_LY_DO: Record<string, string> = {
  spam: "Spam / quảng cáo",
  harassment: "Quấy rối",
  inappropriate: "Không phù hợp",
  copyright: "Bản quyền",
  other: "Khác",
};

export default function AdminReportsPage() {
  const [loc, setLoc] = useState("open");
  const [ds, setDs] = useState<ContentReport[] | null>(null);
  const [tong, setTong] = useState(0);
  const [loi, setLoi] = useState("");
  const [dangLam, setDangLam] = useState("");

  const tai = useCallback(() => {
    setLoi("");
    setDs(null);
    adminSocial
      .reports(loc)
      .then((r) => {
        setDs(r.items);
        setTong(r.total);
      })
      .catch((e) => {
        setDs([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được hàng đợi.");
      });
  }, [loc]);

  /* `queueMicrotask`: `tai()` gọi `setState` đồng bộ, và quy tắc
     `react-hooks/set-state-in-effect` cấm điều đó trong thân effect. */
  useEffect(() => {
    queueMicrotask(tai);
  }, [tai]);

  const lamViec = useCallback(
    async (khoa: string, viec: () => Promise<unknown>) => {
      setDangLam(khoa);
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

  return (
    <div className="stack">
      <header className="stack-2">
        <h1 className="page-title">Báo cáo nội dung</h1>
        <p className="hint">
          {tong} báo cáo. Cũ nhất hiện trước — không ai bị bỏ quên.
        </p>
      </header>

      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        {LOC.map((m) => (
          <button
            key={m.key}
            type="button"
            className={loc === m.key ? "btn btn-sm" : "btn btn-ghost btn-sm"}
            aria-pressed={loc === m.key}
            onClick={() => setLoc(m.key)}
          >
            {m.nhan}
          </button>
        ))}
      </div>

      {/* BA trang thai qua MOT component dung chung — xem `AdminShell`. */}
      <DanhSachTrangThai
        dangTai={ds === null && !loi}
        loi={loi}
        rong={!!ds && ds.length === 0}
        onThuLai={tai}
      >
        <div className="stack">
          {(ds ?? []).map((bc) => {
            const nd = bc.content;
            const daGo = nd?.state === "removed";
            return (
              <article key={bc.report_id} className="card stack-2 bc-the">
                <header className="row bc-dau">
                  <span className="badge">{TEN_LY_DO[bc.reason] ?? bc.reason}</span>
                  <span className="badge">
                    {bc.target_kind === "post" ? "Bài đăng" : "Bình luận"}
                  </span>
                  <span className={daGo ? "badge" : "badge badge-ok"}>
                    {daGo ? "Đã gỡ" : "Còn hiện"}
                  </span>
                  <span className="hint">{formatDate(bc.created_at)}</span>
                </header>

                <p className="hint">
                  <strong>
                    {bc.reporter?.display_name || bc.reporter?.username || "Ai đó"}
                  </strong>{" "}
                  báo cáo nội dung của{" "}
                  {bc.target_owner?.username ? (
                    <Link href={`/u/${bc.target_owner.username}`}>
                      {bc.target_owner.display_name || bc.target_owner.username}
                    </Link>
                  ) : (
                    <strong>{bc.target_owner?.display_name || "người dùng"}</strong>
                  )}
                </p>

                {bc.detail ? (
                  <p className="bc-mo-ta">“{bc.detail}”</p>
                ) : null}

                {/* Nội dung THẬT, ngay tại đây — xem ghi chú đầu tệp. */}
                {nd ? (
                  <blockquote className="bc-noi-dung">
                    {nd.text || <em className="hint">(không có chữ)</em>}
                  </blockquote>
                ) : (
                  <p className="hint">
                    Nội dung này đã được chính chủ xoá — không còn gì để xem.
                  </p>
                )}

                <footer className="row bc-day" style={{ gap: 8, flexWrap: "wrap" }}>
                  {nd ? (
                    daGo ? (
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={dangLam === bc.report_id}
                        onClick={() =>
                          lamViec(bc.report_id, () =>
                            bc.target_kind === "post"
                              ? adminSocial.restorePost(bc.target_id)
                              : adminSocial.restoreComment(bc.target_id),
                          )
                        }
                      >
                        Phục hồi
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={dangLam === bc.report_id}
                        onClick={() =>
                          lamViec(bc.report_id, () =>
                            bc.target_kind === "post"
                              ? adminSocial.removePost(
                                  bc.target_id,
                                  TEN_LY_DO[bc.reason] ?? bc.reason,
                                )
                              : adminSocial.removeComment(
                                  bc.target_id,
                                  TEN_LY_DO[bc.reason] ?? bc.reason,
                                ),
                          )
                        }
                      >
                        Gỡ nội dung
                      </button>
                    )
                  ) : null}

                  {bc.status === "open" ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={dangLam === bc.report_id}
                        onClick={() =>
                          lamViec(bc.report_id, () =>
                            adminSocial.resolveReport(bc.report_id, false,
                                                      "Đã xử lý"),
                          )
                        }
                      >
                        Đánh dấu đã xử lý
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={dangLam === bc.report_id}
                        onClick={() =>
                          lamViec(bc.report_id, () =>
                            adminSocial.resolveReport(bc.report_id, true,
                                                      "Không vi phạm"),
                          )
                        }
                      >
                        Bỏ qua
                      </button>
                    </>
                  ) : (
                    <span className="hint">
                      {bc.status === "resolved" ? "Đã xử lý" : "Đã bỏ qua"}
                      {bc.resolution_note ? ` · ${bc.resolution_note}` : null}
                    </span>
                  )}

                  {/* Backend tinh san duong toi nguon — bai HOAC chuong. */}
                  {bc.context_url ? (
                    <Link className="btn btn-ghost btn-sm" href={bc.context_url}>
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
