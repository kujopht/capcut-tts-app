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
import { useCallback, useState } from "react";
import { ApiError, adminApi, type AdminRole, type AuthorStatus } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { Loading } from "@/components/ui";
import {
  IconBook,
  IconChart,
  IconCompass,
  IconFeather,
  IconFilm,
  IconGear,
  IconHistory,
  IconInbox,
  IconKey,
  IconLink,
  IconMegaphone,
  IconShield,
  IconSparkles,
  IconUser,
} from "@/components/Icons";

interface MucDieuHuong {
  href: string;
  nhan: string;
  icon: (p: { size?: number }) => React.ReactElement;
  /**
   * Muc quan tri TOI THIEU de THAY muc nay trong sidebar — CHI la goi y hien
   * thi (Admin Control Center V2, A3). Bo trong = moi vai tro (ke ca
   * MODERATOR) deu thay. Route `/api/admin/*` phia sau VAN tu kiem quyen
   * rieng, khong phu thuoc gia tri nay — sua no bang DevTools khong mo thêm
   * duoc gi.
   */
  vaiToiThieu?: AdminRole;
}

interface NhomDieuHuong {
  /** Nhan nhom — bo trong = muc DUNG MOT MINH, khong can tieu de nhom. */
  nhom?: string;
  muc: MucDieuHuong[];
}

/**
 * Cay dieu huong Admin Control Center V2 — dung nhom (Content/Animation/
 * Moderation) de gop cac trang lien quan, giu cau truc "Dashboard/Users/
 * Content/Animation/Moderation/Analytics/AI-Credits/System/Audit Log" theo
 * dung ban ke hoach. Muc con hien PHANG duoi tieu de nhom (khong an/hien
 * bang JS) — tren mobile, `.admin-nav` da co san che do cuon ngang (xem
 * globals.css), nen day van la "dieu huong dap ung, gap gon duoc" ma khong
 * can them mot component accordion moi.
 */
const NHOM_DIEU_HUONG: NhomDieuHuong[] = [
  { muc: [{ href: "/admin", nhan: "Dashboard", icon: IconCompass }] },
  { muc: [{ href: "/admin/users", nhan: "Users", icon: IconUser, vaiToiThieu: "admin" }] },
  {
    nhom: "Content",
    muc: [
      { href: "/admin/stories", nhan: "Truyện", icon: IconBook },
      { href: "/admin/posts", nhan: "Bài đăng", icon: IconMegaphone },
      { href: "/admin/comments", nhan: "Bình luận", icon: IconFeather },
    ],
  },
  {
    nhom: "Animation",
    muc: [
      { href: "/admin/animation/series", nhan: "Series", icon: IconFilm },
      {
        href: "/admin/animation/sources", nhan: "Trusted Sources",
        icon: IconLink, vaiToiThieu: "admin",
      },
      {
        href: "/admin/animation/import-queue", nhan: "Import Queue",
        icon: IconInbox, vaiToiThieu: "admin",
      },
    ],
  },
  {
    nhom: "Moderation",
    muc: [
      { href: "/admin/reports", nhan: "Báo cáo", icon: IconShield },
      { href: "/admin/authors/applications", nhan: "Đơn tác giả", icon: IconFeather },
      { href: "/admin/authors", nhan: "Tác giả", icon: IconKey },
    ],
  },
  { muc: [{ href: "/admin/analytics", nhan: "Analytics", icon: IconChart, vaiToiThieu: "admin" }] },
  { muc: [{ href: "/admin/ai-credits", nhan: "AI / Credits", icon: IconSparkles, vaiToiThieu: "admin" }] },
  { muc: [{ href: "/admin/system", nhan: "System", icon: IconGear, vaiToiThieu: "owner" }] },
  { muc: [{ href: "/admin/audit-log", nhan: "Audit Log", icon: IconHistory, vaiToiThieu: "admin" }] },
];

/** Vai tro co du cao de thay mot muc doi hoi `vaiToiThieu`? OWNER > ADMIN >
    MODERATOR > NONE — trung khop thu bac o `Settings.admin_role_of` phia may
    chu (server/config.py), CHI dung de an/hien, khong phai kiem quyen that. */
function duVaiTro(cua: AdminRole | undefined, toiThieu: AdminRole | undefined): boolean {
  if (!toiThieu) return true;
  const BAC: Record<AdminRole, number> = { none: 0, moderator: 1, admin: 2, owner: 3 };
  return BAC[cua ?? "none"] >= BAC[toiThieu];
}

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
  // Dieu huong mobile/tablet gap/mo — desktop luon hien (xem CSS `.admin-nav`
  // o `@media (max-width: 900px)`), nut nay chi co tac dung duoi nguong do.
  const [moDieuHuongMobile, setMoDieuHuongMobile] = useState(false);

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

  const vaiTro = profile?.admin_role;

  return (
    <div className="page admin-page">
      <header className="admin-dau row row-spread">
        <div className="stack-2">
          <span className="eyebrow eyebrow-icon">
            <IconKey size={17} /> Quản trị
            {vaiTro && vaiTro !== "none" ? (
              <span className={`badge admin-badge-vaitro admin-badge-${vaiTro}`}>
                {vaiTro.toUpperCase()}
              </span>
            ) : null}
          </span>
          <h1 className="page-title admin-tieu-de">Fanfic World</h1>
        </div>
        <button
          type="button"
          className="btn btn-ghost admin-nut-mobile"
          aria-expanded={moDieuHuongMobile}
          aria-controls="admin-dieu-huong"
          onClick={() => setMoDieuHuongMobile((v) => !v)}
        >
          {moDieuHuongMobile ? "Đóng menu" : "Menu quản trị"}
        </button>
      </header>

      <div className="admin-khung">
        <nav
          id="admin-dieu-huong"
          className={`admin-nav${moDieuHuongMobile ? " admin-nav-mo" : ""}`}
          aria-label="Khu quản trị"
        >
          {NHOM_DIEU_HUONG.map((n, i) => {
            const mucHienDuoc = n.muc.filter((m) => duVaiTro(vaiTro, m.vaiToiThieu));
            if (mucHienDuoc.length === 0) return null;
            return (
              <div className="admin-nhom" key={n.nhom ?? mucHienDuoc[0].href}>
                {n.nhom ? (
                  <span className="admin-nhom-nhan">{n.nhom}</span>
                ) : null}
                {mucHienDuoc.map(({ href, nhan, icon: Icon }) => {
                  const dang =
                    href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      className="admin-muc"
                      aria-current={dang ? "page" : undefined}
                      onClick={() => setMoDieuHuongMobile(false)}
                      prefetch={false}
                    >
                      <Icon size={17} />
                      <span>{nhan}</span>
                    </Link>
                  );
                })}
              </div>
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
          <Link className="btn btn-primary" href="/login?next=/admin" prefetch={false}>
            Đăng nhập
          </Link>
        ) : (
          <Link className="btn" href="/" prefetch={false}>
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

/**
 * Mot o so lieu tren bang tong quan.
 *
 * `so === null` nghia la CHUA CO DU LIEU (schema chua theo doi, hoac nha
 * cung cap ngoai chua cau hinh) — hien "—" kem ghi chu, KHONG bao gio hien
 * "0" cho truong hop nay (Admin Control Center V2, A1: "Do not fabricate
 * numbers" — 0 that va "chua co" la hai y nghia khac nhau).
 */
export function OSo({
  nhan,
  so,
  ghi_chu,
}: {
  nhan: string;
  so: number | null;
  ghi_chu?: string;
}) {
  return (
    <div className="stat admin-o">
      <span className="stat-value">
        {so === null ? "—" : so.toLocaleString("vi-VN")}
      </span>
      <span className="stat-label">{nhan}</span>
      {ghi_chu ? <span className="hint admin-o-ghi">{ghi_chu}</span>
        : so === null ? <span className="hint admin-o-ghi">Chưa có dữ liệu</span>
        : null}
    </div>
  );
}

/** Khoi "chua cau hinh" cho MOT muc con (Trusted Sources, Traffic Analytics
    khi chua co credential). Thay the toan bo the OSo cua muc do bang MOT
    thong bao ro rang, thay vi hien mot loat so 0 gay hieu lam. */
export function ChuaCauHinh({ tieuDe, ghiChu }: { tieuDe: string; ghiChu: string }) {
  return (
    <div className="card admin-chua-cau-hinh" role="status">
      <strong>{tieuDe}</strong>
      <p className="hint">{ghiChu}</p>
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
