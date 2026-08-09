"use client";

/** Dieu huong chinh + khu vuc tai khoan. Tach client de dung duoc phien. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "@/lib/session";

/**
 * Ba muc chinh, va chi ba.
 *
 * Audio Studio DA RA KHOI thanh nay. No van song o `/studio` voi nguyen ven
 * chuc nang; cho cua no bay gio la menu ben phai (xem `UserMenu`). Ly do la
 * chuyen san pham chu khong phai thu hang muc: day la nen tang doc/nghe
 * fanfic, va Audio Studio la cong cu phu manh — de no o vi tri dau tien thi
 * nguoi doc lan dau vao se tuong day la mot trang tao giong noi.
 *
 * `/fanfic` giu nguyen duong dan, chi doi NHAN thanh "Khám phá". Doi duong
 * dan se lam hong moi lien ket da chia se.
 */
const LINKS = [
  { href: "/", label: "Trang chủ" },
  { href: "/fanfic", label: "Khám phá" },
  { href: "/library", label: "Thư viện" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="nav-links" aria-label="Điều hướng chính">
      {LINKS.map((link) => {
        // "/" khop CHINH XAC, khong dung `startsWith`: neu khong thi moi trang
        // trong site deu sang muc "Trang chủ".
        const active =
          link.href === "/"
            ? pathname === "/"
            : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className="nav-link"
            aria-current={active ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * Menu ben phai: cong cu + tai khoan.
 *
 * Audio Studio LUON co mat o day, ke ca khi chua dang nhap. `/studio` tu no
 * da xu ly truong hop chua dang nhap (hien loi moi dang nhap chu khong sap),
 * nen an muc nay di chi lam nguoi dung khong tim thay cong cu chu khong bao ve
 * duoc gi.
 */
function UserMenu() {
  const { profile, loading, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      close();
      // Tra tieu diem ve nut mo — neu khong, tieu diem roi ve `<body>` va
      // nguoi dung ban phim mat cho dung.
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  if (loading) {
    return <span className="sk" style={{ width: 92, height: 30 }} aria-hidden="true" />;
  }

  const name = profile ? profile.display_name || profile.email.split("@")[0] : "";

  const toggle = () => setOpen((v) => !v);

  return (
    <div className="menu" ref={boxRef}>
      {/*
        Hai nut RIENG BIET chu khong mot nut voi `className` tinh theo dieu
        kien. Kich thuoc cua `.account-link` va `.avatar` do CSS quyet dinh —
        media query khong voi toi style inline duoc, va mot `className` ghep
        chuoi lam quy tac do kho tra nguoc khi doc.
      */}
      {profile ? (
        <button
          ref={buttonRef}
          type="button"
          className="account-link"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggle}
        >
          <span className="avatar" aria-hidden="true">
            {name.slice(0, 2).toUpperCase()}
          </span>
          <span className="hint truncate account-name">{name}</span>
        </button>
      ) : (
        <button
          ref={buttonRef}
          type="button"
          className="btn btn-ghost btn-sm"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggle}
        >
          Công cụ
        </button>
      )}

      {open ? (
        <div className="menu-panel" role="menu" aria-label="Công cụ và tài khoản">
          <Link href="/studio" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">🎙️</span> Audio Studio
          </Link>
          {profile ? (
            <>
              <Link href="/write" className="menu-item" role="menuitem" onClick={close}>
                <span aria-hidden="true">✍️</span> Khu vực tác giả
              </Link>
              <div className="menu-sep" role="separator" />
              <Link
                href="/account"
                className="menu-item"
                role="menuitem"
                onClick={close}
              >
                <span aria-hidden="true">👤</span> Tài khoản
              </Link>
              <button
                type="button"
                className="menu-item"
                role="menuitem"
                onClick={() => {
                  close();
                  signOut();
                }}
              >
                <span aria-hidden="true">↩</span> Đăng xuất
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function NavAuth() {
  const { profile, loading } = useSession();

  return (
    <div className="row nav-right">
      <UserMenu />
      {!loading && !profile ? (
        <Link className="btn btn-primary btn-sm" href="/login">
          Đăng nhập
        </Link>
      ) : null}
    </div>
  );
}
