"use client";

/**
 * Chi tiet MOT tai khoan (Phase 3, Admin Control Center V2).
 *
 * Gop BA thu co y NGHIA KHAC NHAU, ve TACH BACH tren cung mot trang:
 *   - Trang thai TAC GIA (`author_status`) — quyen XUAT BAN. Xem `/admin/authors`.
 *   - Trang thai TAI KHOAN (`account`) — CO dang nhap duoc hay khong (native
 *     Appwrite Auth). Tam dung o day KHOA dang nhap HOAN TOAN, khac han treo
 *     tac gia.
 *   - Phien dang nhap (`sessions`) — cham dut duoc TUNG phien hoac TAT CA.
 *
 * Nut tam dung/cham dut phien tu AN khi dang xem CHINH tai khoan cua nguoi
 * dang dang nhap — may chu cung tu choi (400), nhung an di o day tranh mot
 * cu bam vo ich.
 */

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { adminApi, type AdminAccountSession } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import {
  DanhSachTrangThai,
  TrangThaiBadge,
  loiApi,
} from "@/components/AdminShell";
import { RankBadge } from "@/components/AuthorBadge";
import { ConfirmDialog, formatNumber } from "@/components/ui";
import { IconHistory, IconKey, IconShield, IconUser } from "@/components/Icons";

export default function AdminUserDetail({
  params,
}: {
  params: Promise<{ user_id: string }>;
}) {
  const { user_id: userId } = use(params);
  const { profile } = useSession();
  const toast = useToast();

  const nap = useCallback(() => adminApi.user(userId), [userId]);
  const { data, loading, error, reload } = useAsyncData(nap);
  const u = data?.user;

  const [hoiTamDung, setHoiTamDung] = useState(false);
  const [hoiChamDutTatCa, setHoiChamDutTatCa] = useState(false);
  const [ghiChu, setGhiChu] = useState("");
  const [dangGui, setDangGui] = useState(false);

  const laChinhMinh = profile?.user_id === userId;

  async function tamDung() {
    setDangGui(true);
    try {
      await adminApi.suspendAccount(userId, ghiChu.trim() || "Tạm dừng để rà soát.");
      toast.ok("Đã tạm dừng tài khoản — người này không đăng nhập được nữa.");
      setHoiTamDung(false);
      setGhiChu("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không tạm dừng được tài khoản."));
    } finally {
      setDangGui(false);
    }
  }

  async function boTamDung() {
    setDangGui(true);
    try {
      await adminApi.unsuspendAccount(userId, "Đã xác minh, cho phép đăng nhập lại.");
      toast.ok("Đã bỏ tạm dừng — tài khoản đăng nhập được bình thường.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không bỏ tạm dừng được."));
    } finally {
      setDangGui(false);
    }
  }

  async function chamDutMotPhien(s: AdminAccountSession) {
    setDangGui(true);
    try {
      await adminApi.terminateSession(userId, s.session_id);
      toast.ok("Đã chấm dứt phiên đăng nhập đó.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không chấm dứt được phiên này."));
    } finally {
      setDangGui(false);
    }
  }

  async function chamDutTatCaPhien() {
    setDangGui(true);
    try {
      const r = await adminApi.terminateAllSessions(userId, ghiChu.trim() || "Chấm dứt toàn bộ phiên.");
      toast.ok(`Đã chấm dứt ${r.terminated_count} phiên đăng nhập.`);
      setHoiChamDutTatCa(false);
      setGhiChu("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không chấm dứt được các phiên."));
    } finally {
      setDangGui(false);
    }
  }

  return (
    <section className="stack">
      <p className="hint">
        <Link href="/admin/users">← Về danh sách người dùng</Link>
      </p>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!u} onThuLai={reload}>
        {u ? (
          <div className="stack">
            <header className="row row-spread">
              <span className="admin-nguoi">
                <span className="admin-avt" aria-hidden="true">
                  {(u.display_name || u.username || u.email).slice(0, 2).toUpperCase()}
                </span>
                <span className="admin-hang-chu">
                  <strong className="page-title" style={{ fontSize: "1.2rem" }}>
                    {u.display_name || "(chưa đặt tên)"}
                  </strong>
                  <span className="hint mono">
                    {u.username ? `@${u.username}` : "chưa chọn tên công khai"}
                    {" · "}{u.email}
                  </span>
                </span>
              </span>
              {u.admin_role && u.admin_role !== "none" ? (
                <span className={`badge admin-badge-vaitro admin-badge-${u.admin_role}`}>
                  {u.admin_role.toUpperCase()}
                </span>
              ) : null}
            </header>

            <div className="bento-grid">
              <div className="card stack-2">
                <h3 className="section-title section-title-icon">
                  <IconUser size={17} /> Tác giả
                </h3>
                <TrangThaiBadge status={u.author_status} />
                {u.rank ? <RankBadge rank={u.rank} size="sm" /> : null}
                <p className="hint">
                  {formatNumber(u.qualified_listens)} lượt nghe hợp lệ ·{" "}
                  {u.published_novels ?? 0} truyện đã xuất bản
                </p>
                <p className="hint">
                  Đây là quyền XUẤT BẢN — quản lý riêng ở{" "}
                  <Link href="/admin/authors">trang Tác giả</Link>, không đổi
                  ở đây.
                </p>
              </div>

              <div className="card stack-2">
                <h3 className="section-title section-title-icon">
                  <IconKey size={17} /> Tài khoản
                </h3>
                {u.account ? (
                  <>
                    <span className={`tt ${u.account.enabled ? "tt-duyet" : "tt-treo"}`}>
                      {u.account.enabled ? "Hoạt động" : "Đã tạm dừng"}
                    </span>
                    <p className="hint">
                      Email {u.account.email_verified ? "đã xác minh" : "chưa xác minh"} ·
                      Đăng ký {u.account.registered_at
                        ? new Date(u.account.registered_at).toLocaleString("vi-VN")
                        : "—"}
                    </p>
                    <p className="hint">
                      <strong>Tạm dừng ở đây khoá đăng nhập HOÀN TOÀN</strong> —
                      khác với tạm dừng tác giả, chỉ chặn xuất bản mới.
                    </p>
                    {laChinhMinh ? (
                      <p className="hint">
                        Không thể tự thao tác trên chính tài khoản đang đăng nhập.
                      </p>
                    ) : u.account.enabled ? (
                      <button type="button" className="btn btn-sm btn-danger"
                              disabled={dangGui}
                              onClick={() => { setHoiTamDung(true); setGhiChu(""); }}>
                        Tạm dừng tài khoản
                      </button>
                    ) : (
                      <button type="button" className="btn btn-sm" disabled={dangGui}
                              onClick={boTamDung}>
                        Bỏ tạm dừng
                      </button>
                    )}
                  </>
                ) : (
                  <p className="hint">Không đọc được trạng thái tài khoản.</p>
                )}
              </div>
            </div>

            <div className="stack-2">
              <h3 className="section-title section-title-icon">
                <IconShield size={17} /> Phiên đăng nhập
              </h3>
              {u.sessions && u.sessions.length > 0 ? (
                <>
                  <div className="admin-bang-boc">
                    <table className="admin-bang">
                      <thead>
                        <tr>
                          <th scope="col">Thiết bị</th>
                          <th scope="col">IP</th>
                          <th scope="col">Quốc gia</th>
                          <th scope="col">Bắt đầu</th>
                          <th scope="col"><span className="sr-only">Thao tác</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {u.sessions.map((s) => (
                          <tr key={s.session_id}>
                            <td>{s.device_name || s.client_name || s.provider || "—"}</td>
                            <td className="mono">{s.ip || "—"}</td>
                            <td>{s.country_name || "—"}</td>
                            <td className="hint">
                              {s.created_at
                                ? new Date(s.created_at).toLocaleString("vi-VN")
                                : "—"}
                            </td>
                            <td>
                              {laChinhMinh ? null : (
                                <button type="button" className="btn btn-sm"
                                        disabled={dangGui}
                                        onClick={() => chamDutMotPhien(s)}>
                                  Chấm dứt
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {laChinhMinh ? null : (
                    <div className="row">
                      <button type="button" className="btn btn-sm btn-danger"
                              disabled={dangGui}
                              onClick={() => { setHoiChamDutTatCa(true); setGhiChu(""); }}>
                        Chấm dứt tất cả phiên
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <p className="hint">Không có phiên đăng nhập nào đang mở.</p>
              )}
            </div>

            {u.events && u.events.length > 0 ? (
              <div className="stack-2">
                <h3 className="section-title section-title-icon">
                  <IconHistory size={17} /> Nhật ký liên quan
                </h3>
                <ul className="admin-nhat-ky">
                  {u.events.map((e) => (
                    <li key={e.event_id} className="admin-su-kien">
                      <span className="mono">{e.action}</span>
                      {e.note ? <span className="hint">{e.note}</span> : null}
                      <span className="hint admin-luc">
                        {new Date(e.created_at).toLocaleString("vi-VN")}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </DanhSachTrangThai>

      {hoiTamDung ? (
        <ConfirmDialog
          open
          title={`Tạm dừng tài khoản của ${u?.display_name || u?.email}?`}
          body={
            <span className="stack-2">
              <span>
                Họ sẽ KHÔNG đăng nhập được nữa ở bất kỳ đường nào (email lẫn
                OAuth), cho tới khi được bỏ tạm dừng. Đây khác với tạm dừng
                tác giả — người này có thể không phải tác giả.
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
          onConfirm={tamDung}
          onCancel={() => setHoiTamDung(false)}
        />
      ) : null}

      {hoiChamDutTatCa ? (
        <ConfirmDialog
          open
          title="Chấm dứt tất cả phiên đăng nhập?"
          body={
            <span className="stack-2">
              <span>Người này sẽ bị đăng xuất khỏi mọi thiết bị ngay lập tức.</span>
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
          confirmLabel="Chấm dứt tất cả"
          danger
          busy={dangGui}
          onConfirm={chamDutTatCaPhien}
          onCancel={() => setHoiChamDutTatCa(false)}
        />
      ) : null}
    </section>
  );
}
