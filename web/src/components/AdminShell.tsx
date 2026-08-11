"use client";

/**
 * Khung cua khu quan tri: dieu huong, cong chan, va cac manh dung chung.
 *
 * BA dieu dinh hinh ca khu nay:
 *
 *   1. GIAO DIEN KHONG BAO GIO LA NOI QUYET DINH. `<CongQuanTri>` khong doc mot
 *      co `isAdmin` nao ca — no goi `/api/admin/overview` va xem may chu tra ve
 *      gi. 401 -> moi dang nhap; 403 -> khong co quyen; 200 -> ve noi dung. Mot
 *      nguoi dung thuong go thang `/admin/users` cung di qua dung duong do va
 *      khong bao gio nhan duoc mot byte du lieu nao.
 *
 *   2. DAY LA MOT BE MAT LAM VIEC. Van dung he mau va he icon cua Fanfic World,
 *      nhung khong hat sang, khong tranh nen lon, khong hoa van goc. Nguoi ta o
 *      day de doc mot hang doi va ra quyet dinh, khong phai de ngam.
 *
 *   3. TRANG THAI KIEM DUYET va HANG TAC GIA duoc ve KHAC NHAU. Mot nguoi hang
 *      cao van co the dang bi treo, va nham hai thu do o mot bang quan tri la
 *      nham mot quyet dinh.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback } from "react";
import { ApiError, adminApi, type AuthorStatus } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { Loading } from "@/components/ui";
import {
  IconBook,
  IconCompass,
  IconFeather,
  IconHistory,
  IconKey,
  IconUser,
} from "@/components/Icons";

const MUC = [
  { href: "/admin", nhan: "Tổng quan", icon: IconCompass },
  { href: "/admin/authors/applications", nhan: "Đơn tác giả", icon: IconFeather },
  { href: "/admin/authors", nhan: "Tác giả", icon: IconKey },
  { href: "/admin/users", nhan: "Người dùng", icon: IconUser },
  { href: "/admin/stories", nhan: "Truyện", icon: IconBook },
  { href: "/admin/events", nhan: "Nhật ký", icon: IconHistory },
];

/**
 * Cong chan.
 *
 * Goi `/api/admin/overview` de HOI MAY CHU, khong de lay so lieu — con so that
 * duoc tung trang tu goi. Mot lan goi la du de biet nguoi nay co quyen hay
 * khong, va no la cung mot phep kiem ma moi route quan tri khac dung.
 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { profile, loading: dangTaiPhien } = useSession();

  const kiem = useCallback(async () => {
    await adminApi.overview();
    return true;
  }, []);
  const { data: duoc, loading, error } = useAsyncData<boolean>(kiem);

  if (dangTaiPhien || loading) {
    return <div className="page"><Loading /></div>;
  }

  if (!duoc) {
    return <TuChoi daDangNhap={Boolean(profile)} loi={error} />;
  }

  return (
    <div className="page admin-page">
      <header className="admin-dau">
        <span className="eyebrow eyebrow-icon">
          <IconKey size={17} /> Quản trị
        </span>
        <h1 className="page-title admin-tieu-de">Fanfic World</h1>
      </header>

      <div className="admin-khung">
        <nav className="admin-nav" aria-label="Khu quản trị">
          {MUC.map(({ href, nhan, icon: Icon }) => {
            const dang =
              href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className="admin-muc"
                aria-current={dang ? "page" : undefined}
              >
                <Icon size={17} />
                <span>{nhan}</span>
              </Link>
            );
          })}
        </nav>

        <div className="admin-than">{children}</div>
      </div>
    </div>
  );
}

/**
 * Man tu choi.
 *
 * KHONG noi "khu quan tri khong ton tai": mot nguoi quan tri that go nham tai
 * khoan can hieu vi sao ho khong vao duoc. Khu nay khong bi giau, no bi khoa.
 */
function TuChoi({ daDangNhap, loi }: { daDangNhap: boolean; loi: string }) {
  const chuaDangNhap =
    !daDangNhap || loi.includes("đăng nhập") || loi.includes("401");
  return (
    <div className="page auth-page">
      <header className="auth-head">
        <h1 className="page-title">Khu vực quản trị</h1>
        <p className="hint">
          {chuaDangNhap
            ? "Bạn cần đăng nhập bằng tài khoản có quyền quản trị."
            : "Tài khoản này không có quyền quản trị."}
        </p>
      </header>
      <div className="row" style={{ justifyContent: "center" }}>
        {chuaDangNhap ? (
          <Link className="btn btn-primary" href="/login?next=/admin">
            Đăng nhập
          </Link>
        ) : (
          <Link className="btn" href="/">
            Về trang chủ
          </Link>
        )}
      </div>
    </div>
  );
}

/* ====================================================== manh dung chung */

/**
 * Nhan TRANG THAI KIEM DUYET.
 *
 * Mau co nghia co dinh, va no KHONG bao gio dung lai cho hang tac gia: hang la
 * uy tin, trang thai la quyen. Ve chung giong nhau la moi mot nguoi doc bang
 * nham hai thu.
 */
const NHAN: Record<AuthorStatus, { chu: string; lop: string }> = {
  none: { chu: "Chưa đăng ký", lop: "tt-trong" },
  pending: { chu: "Chờ duyệt", lop: "tt-cho" },
  approved: { chu: "Đã duyệt", lop: "tt-duyet" },
  rejected: { chu: "Từ chối", lop: "tt-tuchoi" },
  suspended: { chu: "Tạm dừng", lop: "tt-treo" },
};

export function TrangThaiBadge({ status }: { status: AuthorStatus }) {
  const n = NHAN[status] ?? NHAN.none;
  return <span className={`tt ${n.lop}`}>{n.chu}</span>;
}

/** Mot o so lieu tren bang tong quan. */
export function OSo({
  nhan,
  so,
  ghi_chu,
}: {
  nhan: string;
  so: number;
  ghi_chu?: string;
}) {
  return (
    <div className="stat admin-o">
      <span className="stat-value">{so.toLocaleString("vi-VN")}</span>
      <span className="stat-label">{nhan}</span>
      {ghi_chu ? <span className="hint admin-o-ghi">{ghi_chu}</span> : null}
    </div>
  );
}

/** Ba trang thai cua mot danh sach, ve o MOT cho de khong cho nao quen cai nao. */
export function DanhSachTrangThai({
  dangTai,
  loi,
  rong,
  onThuLai,
  children,
}: {
  dangTai: boolean;
  loi: string;
  rong: boolean;
  onThuLai?: () => void;
  children: React.ReactNode;
}) {
  if (dangTai) return <Loading />;
  if (loi) {
    return (
      <div className="card stack-2" role="alert">
        <strong>Không tải được.</strong>
        <p className="hint">{loi}</p>
        {onThuLai ? (
          <div className="row">
            <button type="button" className="btn btn-sm" onClick={onThuLai}>
              Thử lại
            </button>
          </div>
        ) : null}
      </div>
    );
  }
  if (rong) {
    return (
      <div className="card admin-rong" role="status">
        Không có mục nào.
      </div>
    );
  }
  return <>{children}</>;
}

/** Thong diep loi doc duoc tu mot loi API. */
export function loiApi(cause: unknown, mac_dinh: string): string {
  return cause instanceof ApiError ? cause.message : mac_dinh;
}
