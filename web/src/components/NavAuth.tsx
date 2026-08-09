"use client";

/** Dieu huong chinh + cong cu + khu vuc tai khoan. Tach client de dung phien. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "@/lib/session";

/**
 * Bon muc chinh, DUNG THU TU NAY.
 *
 * "Viết truyện" (`/write`) la mot khu vuc san pham ngang hang voi "Khám phá"
 * va "Thư viện", khong phai mot muc trong menu tai khoan. Giau no di la noi
 * rang viet truyen la viec phu — trong khi khong co tac gia thi khong co gi
 * de doc.
 *
 * Audio Studio KHONG nam o day. No la mot CONG CU rieng (`/studio`): dan van
 * ban bat ky, chon giong, tai MP3 — khong lien quan den viec quan ly truyen.
 * Cho cua no la menu "Công cụ".
 *
 * `/fanfic` giu nguyen duong dan, chi mang nhan "Khám phá": doi duong dan se
 * lam hong moi lien ket da chia se.
 *
 * `cta` KHONG doi thu tu hay cau truc — no chi doi CACH VE. "Viết truyện" van
 * la muc thu tu trong danh sach nay; no duoc ve thanh mot nut co vien tim thay
 * vi mot lien ket tron, de nguoi luot qua thay ngay rang ho tu viet duoc.
 */
const LINKS = [
  { href: "/", label: "Trang chủ" },
  { href: "/fanfic", label: "Khám phá" },
  { href: "/library", label: "Thư viện" },
  { href: "/write", label: "Viết truyện", cta: true },
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
            className={link.cta ? "nav-link nav-cta" : "nav-link"}
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
 * Menu bat/tat dung duoc bang ban phim.
 *
 * Tach thanh hook vi header co HAI menu — "Công cụ" va tai khoan — va ca hai
 * can dung mot hanh vi: Escape dong VA tra tieu diem ve nut mo (neu khong,
 * tieu diem roi ve `<body>` va nguoi dung ban phim mat cho dung), bam ra
 * ngoai cung dong.
 */
function useMenu() {
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
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  return { open, setOpen, close, boxRef, buttonRef };
}

/**
 * Menu "Công cụ".
 *
 * LUON co mat, ke ca khi chua dang nhap. `/studio` tu no da xu ly truong hop
 * chua dang nhap; an muc nay di chi lam nguoi dung khong tim thay cong cu chu
 * khong bao ve duoc gi.
 */
function ToolsMenu() {
  const { open, setOpen, close, boxRef, buttonRef } = useMenu();

  return (
    <div className="menu" ref={boxRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn-ghost btn-sm"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        Công cụ
      </button>
      {open ? (
        <div className="menu-panel" role="menu" aria-label="Công cụ">
          <Link href="/studio" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">🎙</span> Audio Studio
          </Link>
        </div>
      ) : null}
    </div>
  );
}

/** Menu tai khoan. Chi hien khi da dang nhap; con lai la nut "Đăng nhập". */
function AccountMenu() {
  const { profile, loading, signOut } = useSession();
  const { open, setOpen, close, boxRef, buttonRef } = useMenu();

  if (loading) {
    return <span className="sk" style={{ width: 92, height: 30 }} aria-hidden="true" />;
  }

  if (!profile) {
    return (
      <Link className="btn btn-primary btn-sm" href="/login">
        Đăng nhập
      </Link>
    );
  }

  const name = profile.display_name || profile.email.split("@")[0];

  return (
    <div className="menu" ref={boxRef}>
      {/*
        Kich thuoc cua `.account-link` va `.avatar` do CSS quyet dinh — media
        query khong voi toi style inline duoc.
      */}
      <button
        ref={buttonRef}
        type="button"
        className="account-link"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="avatar" aria-hidden="true">
          {name.slice(0, 2).toUpperCase()}
        </span>
        <span className="hint truncate account-name">{name}</span>
      </button>
      {open ? (
        <div className="menu-panel" role="menu" aria-label="Tài khoản">
          <Link href="/account" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">👤</span> Tài khoản
          </Link>
          <div className="menu-sep" role="separator" />
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
        </div>
      ) : null}
    </div>
  );
}

export function NavAuth() {
  return (
    <div className="row nav-right">
      <ToolsMenu />
      <AccountMenu />
    </div>
  );
}
