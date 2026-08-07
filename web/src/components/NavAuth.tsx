"use client";

/** Dieu huong chinh + khu vuc tai khoan. Tach client de dung duoc phien. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "@/lib/session";

const LINKS = [
  { href: "/studio", label: "Audio Studio" },
  { href: "/fanfic", label: "Fanfic" },
  { href: "/library", label: "Thư viện" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="nav-links" aria-label="Điều hướng chính">
      {LINKS.map((link) => {
        const active =
          pathname === link.href || pathname.startsWith(`${link.href}/`);
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

export function NavAuth() {
  const { profile, loading, signOut } = useSession();

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
    <div className="row" style={{ gap: "var(--s2)" }}>
      <Link
        href="/account"
        className="row"
        style={{ gap: "var(--s2)", textDecoration: "none", color: "inherit" }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 28,
            height: 28,
            display: "grid",
            placeItems: "center",
            borderRadius: "50%",
            background: "var(--brand-soft)",
            color: "var(--brand)",
            fontSize: 12,
            fontWeight: 700,
            border: "1px solid var(--brand-line)",
          }}
        >
          {name.slice(0, 2).toUpperCase()}
        </span>
        <span className="hint truncate" style={{ maxWidth: 110 }}>
          {name}
        </span>
      </Link>
      <button type="button" className="btn btn-ghost btn-sm" onClick={signOut}>
        Đăng xuất
      </button>
    </div>
  );
}
