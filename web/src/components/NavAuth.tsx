"use client";

/** Dieu huong chinh + cong cu + khu vuc tai khoan. Tach client de dung phien. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { viTri } from "@/lib/sections";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "@/lib/session";
import { NavIndicator, type BangMuc } from "@/components/NavIndicator";
import { NotificationBell } from "@/components/NotificationBell";
import { StreakBadge } from "@/components/StreakBadge";
import { Avatar } from "@/components/Avatar";

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
 *
 * "Animation" (V6, overnight Phase 5) dung NGAY SAU "Khám phá" — cùng nhịp
 * XEM/ĐỌC "tìm thứ để tiêu thụ", trước khi rẽ sang "Cộng đồng" (tương tác xã
 * hội). Đây là một sản phẩm ĐỘC LẬP với Truyện/Audio (xem docstring đầu
 * `server/animation_domain.py`) — Audio KHÔNG lên hàng đầu vì nó vẫn là một
 * CÔNG CỤ (`/studio`) chứ không phải một khu vực duyệt riêng, còn Animation
 * thì có trang chủ/series/tập của chính nó, xứng một mục điều hướng chính.
 */
const LINKS = [
  { href: "/", label: "Trang chủ" },
  { href: "/fanfic", label: "Khám phá" },
  { href: "/animation", label: "Animation" },
  { href: "/community", label: "Cộng đồng" },
  { href: "/library", label: "Thư viện" },
  { href: "/write", label: "Viết truyện", cta: true },
];

export function NavLinks() {
  const pathname = usePathname();
  /*
    `hop` de `NavIndicator` do vi tri muc dang xem. Vach nam TRONG hang nay chu
    khong o mot tang khac: no duoc dat theo toa do trong hang, va hang thi cuon
    ngang duoc o mobile.
  */
  const hop = useRef<HTMLElement | null>(null);
  /*
    Bang `href -> phan tu`, do chinh cac muc tu dang ky khi duoc gan vao DOM.

    Vien thuoc do TU BANG NAY chu khong tim bang `querySelector`: mot phep tim
    trong DOM doc trang thai ma React co the cap nhat o mot lan ve den sau, con
    bang thi duoc dien ngay o buoc gan tham chieu. Xem `NavIndicator`.

    `useRef` chu khong `useState`: dien bang khong duoc keo theo mot lan ve moi,
    va noi dung cua no on dinh sau lan gan dau tien.
  */
  const bang = useRef<BangMuc>(new Map());
  /*
    `href` cua muc dang xem — tinh MOT lan o day, dung cho ca `aria-current` lan
    vien thuoc. Truyen `pathname` roi de vien thuoc tu do DOM se dua voi chu ky
    ve cua React; da do duoc dieu do tren trinh duyet.
  */
  const dangXem =
    LINKS.find((l) =>
      l.href === "/"
        ? pathname === "/"
        : pathname === l.href || pathname.startsWith(`${l.href}/`),
    )?.href ?? "";
  return (
    <nav className="nav-links" aria-label="Điều hướng chính" ref={hop}>
      {LINKS.map((link) => {
        // "/" khop CHINH XAC, khong dung `startsWith`: neu khong thi moi trang
        // trong site deu sang muc "Trang chủ".
        const active = link.href === dangXem;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={link.cta ? "nav-link nav-cta" : "nav-link"}
            aria-current={active ? "page" : undefined}
            ref={(el) => {
              if (el) bang.current.set(link.href, el);
              else bang.current.delete(link.href);
            }}
            /* Sac cua khu vuc, cung nguon token voi vien thuoc. */
            style={
              active
                ? ({
                    ["--sac-1" as string]: `var(--sac-${viTri(link.href)}-1)`,
                    ["--sac-2" as string]: `var(--sac-${viTri(link.href)}-2)`,
                  } as React.CSSProperties)
                : undefined
            }
          >
            {link.label}
          </Link>
        );
      })}
      {/*
        MOT vach dung chung, truot tu muc cu sang muc moi. Truoc day tung muc tu
        ve vach cua no bang `::after`, nen doi trang la vach bien mat roi mot
        vach khac xuat hien — khong co gi noi hai trang thai voi nhau.
      */}
      <NavIndicator bao={hop} bang={bang} moc={dangXem} />
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
          <Link href="/image-studio" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">🖼</span> Image Studio
          </Link>
          <Link href="/translate" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">🈺</span> Dịch tiểu thuyết
          </Link>
          <Link href="/tools/subtitles" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">🎬</span> Subtitle Studio
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
        <Avatar name={name} avatarUrl={profile.avatar_url} className="avatar" />
        <span className="hint truncate account-name">{name}</span>
      </button>
      {open ? (
        <div className="menu-panel" role="menu" aria-label="Tài khoản">
          <Link href="/account" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">👤</span> Tài khoản
          </Link>
          <Link href="/leaderboard" className="menu-item" role="menuitem" onClick={close}>
            <span aria-hidden="true">👑</span> Bảng xếp hạng
          </Link>
          {/*
            Chỉ hiện khi MÁY CHỦ xác nhận (`/api/auth/me` → `is_admin`).
            Không suy từ email hay danh sách nhúng trong frontend — đây chỉ là
            lối vào; quyền thật vẫn do từng route `/api/admin/*` kiểm.
          */}
          {profile.is_admin ? (
            <Link href="/admin" className="menu-item" role="menuitem" onClick={close}>
              <span aria-hidden="true">🛡</span> Quản trị
            </Link>
          ) : null}
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
      <StreakBadge />
      {/* Chuông đứng TRƯỚC menu tài khoản: nó là thứ người ta nhìn thường
          xuyên hơn, và đặt nó sau avatar sẽ đẩy nó ra rìa màn hình ở mobile. */}
      <NotificationBell />
      <AccountMenu />
    </div>
  );
}
