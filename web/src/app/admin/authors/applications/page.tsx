"use client";

/**
 * Hang doi don tac gia — phan quan trong nhat cua khu quan tri.
 *
 * MOT trang, khong phai hai: danh sach o trai, chi tiet o phai. Mot trang chi
 * tiet rieng bat nguoi duyet bam vao, doc, quyet dinh, roi bam Back — va lam
 * mat cho trong hang doi. Duyet mot loat don la mot cong viec LAP, va giao dien
 * phai giu duoc nhip do.
 *
 * MOI thao tac di qua may chu. Nut o day chi goi API va ve lai theo ket qua;
 * khong co trang thai nao duoc doan truoc.
 */

import Link from "next/link";
import { useCallback, useState } from "react";
import { adminApi, type AdminApplication, type AuthorStatus } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import {
  DanhSachTrangThai,
  TrangThaiBadge,
  loiApi,
} from "@/components/AdminShell";
import { ConfirmDialog } from "@/components/ui";
import { IconFeather } from "@/components/Icons";

const LOC: Array<{ khoa: string; nhan: string }> = [
  { khoa: "pending", nhan: "Chờ duyệt" },
  { khoa: "approved", nhan: "Đã duyệt" },
  { khoa: "rejected", nhan: "Từ chối" },
  { khoa: "suspended", nhan: "Tạm dừng" },
  { khoa: "", nhan: "Tất cả" },
];

export default function AdminApplications() {
  const toast = useToast();
  const [loc, setLoc] = useState("pending");
  const [chon, setChon] = useState<string>("");
  const [ghiChu, setGhiChu] = useState("");
  const [dangGui, setDangGui] = useState(false);
  /** `null` = khong hoi gi. Xac nhan la BAT BUOC cho thao tac han che. */
  const [hoi, setHoi] = useState<null | "tu-choi">(null);

  const nap = useCallback(() => adminApi.applications(loc), [loc]);
  const { data, loading, error, reload } = useAsyncData(nap);

  const ds = data?.applications ?? [];
  const dang = ds.find((a) => a.user_id === chon) ?? ds[0] ?? null;

  async function duyet(app: AdminApplication) {
    setDangGui(true);
    try {
      await adminApi.approve(app.user_id, ghiChu.trim());
      toast.ok(`Đã duyệt ${app.pen_name}.`);
      setGhiChu("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không duyệt được."));
    } finally {
      setDangGui(false);
    }
  }

  async function tuChoi(app: AdminApplication) {
    setDangGui(true);
    try {
      await adminApi.reject(app.user_id, ghiChu.trim());
      toast.ok("Đã từ chối và gửi ghi chú cho người nộp.");
      setGhiChu("");
      setHoi(null);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không từ chối được."));
    } finally {
      setDangGui(false);
    }
  }

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconFeather size={19} /> Đơn tác giả
      </h2>

      <div className="seg admin-loc" role="group" aria-label="Lọc theo trạng thái">
        {LOC.map((l) => (
          <button
            key={l.khoa || "all"}
            type="button"
            className="seg-item"
            aria-pressed={loc === l.khoa}
            onClick={() => {
              setLoc(l.khoa);
              setChon("");
            }}
          >
            {l.nhan}
          </button>
        ))}
      </div>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={ds.length === 0}
        onThuLai={reload}
      >
        <div className="admin-doi">
          <ul className="admin-ds" aria-label="Danh sách đơn">
            {ds.map((a) => (
              <li key={a.user_id}>
                <button
                  type="button"
                  className="admin-hang"
                  aria-current={dang?.user_id === a.user_id ? "true" : undefined}
                  onClick={() => {
                    setChon(a.user_id);
                    setGhiChu("");
                  }}
                >
                  <span className="admin-avt" aria-hidden="true">
                    {(a.pen_name || "?").slice(0, 2).toUpperCase()}
                  </span>
                  <span className="admin-hang-chu">
                    <strong>{a.pen_name}</strong>
                    <span className="hint mono">
                      @{a.user?.username || "chưa có tên"}
                    </span>
                  </span>
                  <TrangThaiBadge status={a.status as AuthorStatus} />
                </button>
              </li>
            ))}
          </ul>

          {dang ? (
            <article className="card stack admin-chi-tiet">
              <header className="stack-2">
                <div className="row row-spread">
                  <h3 className="section-title">{dang.pen_name}</h3>
                  <TrangThaiBadge status={dang.status as AuthorStatus} />
                </div>
                {dang.user ? (
                  <p className="hint">
                    <Link href={`/u/${dang.user.username}`} className="mono">
                      @{dang.user.username}
                    </Link>
                    {" · "}
                    {/* Email CHI o duong quan tri — khong bao gio ra API công khai. */}
                    <span className="mono">{dang.user.email}</span>
                  </p>
                ) : null}
                <p className="hint">
                  Nộp lúc {new Date(dang.created_at).toLocaleString("vi-VN")}
                  {dang.attempts > 1 ? ` · lần thứ ${dang.attempts}` : ""}
                </p>
              </header>

              {dang.genres.length ? (
                <div className="the-chon">
                  {dang.genres.map((g) => (
                    <span key={g} className="chip">
                      {g}
                    </span>
                  ))}
                </div>
              ) : null}

              {dang.bio ? (
                <div className="stack-2">
                  <span className="label">Giới thiệu ngắn</span>
                  <p>{dang.bio}</p>
                </div>
              ) : null}

              <div className="stack-2">
                <span className="label">Lời giới thiệu</span>
                <p className="admin-van">{dang.intro}</p>
              </div>

              {dang.reviewer_note ? (
                <div className="stack-2">
                  <span className="label">Ghi chú lần duyệt trước</span>
                  <blockquote className="ghi-chu-duyet">
                    {dang.reviewer_note}
                  </blockquote>
                </div>
              ) : null}

              {dang.status === "pending" ? (
                <>
                  <div className="field">
                    <label className="label" htmlFor="ad-ghi-chu">
                      Ghi chú{" "}
                      <span className="hint">
                        (bắt buộc khi từ chối — người nộp sẽ đọc được)
                      </span>
                    </label>
                    <textarea
                      id="ad-ghi-chu"
                      className="textarea textarea-sm"
                      value={ghiChu}
                      onChange={(e) => setGhiChu(e.target.value)}
                      maxLength={1000}
                      rows={3}
                    />
                  </div>
                  <div className="row">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={dangGui}
                      onClick={() => duyet(dang)}
                    >
                      Duyệt
                    </button>
                    {/*
                      Tu choi la thao tac HAN CHE: no dong mot canh cua trong ba
                      ngay. Phai xac nhan, va phai co ghi chu.
                    */}
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      disabled={dangGui || !ghiChu.trim()}
                      onClick={() => setHoi("tu-choi")}
                    >
                      Từ chối
                    </button>
                  </div>
                </>
              ) : (
                <p className="hint">
                  Đơn này đã được xử lý. Thao tác tạm dừng / phục hồi nằm ở mục{" "}
                  <Link href="/admin/authors">Tác giả</Link>.
                </p>
              )}
            </article>
          ) : null}
        </div>
      </DanhSachTrangThai>

      {hoi === "tu-choi" && dang ? (
        <ConfirmDialog
          open
          title={`Từ chối đơn của ${dang.pen_name}?`}
          body="Người nộp sẽ đọc được ghi chú của bạn và có thể gửi lại đơn sau 3 ngày."
          confirmLabel="Từ chối"
          danger
          busy={dangGui}
          onConfirm={() => tuChoi(dang)}
          onCancel={() => setHoi(null)}
        />
      ) : null}
    </section>
  );
}
