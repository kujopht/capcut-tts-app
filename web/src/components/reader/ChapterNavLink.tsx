"use client";

/**
 * Lien ket sang chuong khac — dung trong CAC phan cua trang chuong ma may chu
 * ve (dieu huong dau/cuoi trang), nhung biet "ban dang nghe".
 *
 * NGU NGHIA PHAT KHI DIEU HUONG CO CHU DICH:
 *   - dang PHAT chuong nay + chuong dich co audio -> chuong dich phat tiep
 *     ngay (nguoi dung da tu bam nghe; bam "Chương sau" la muon nghe tiep);
 *   - dang tam dung / chua nghe -> chi dieu huong, KHONG tu phat.
 *
 * Van la `next/link` that (`href` day du, `rel` prev/next do trang truyen
 * vao) — trinh duyet, may tim kiem va trinh doc man hinh thay mot lien ket
 * binh thuong; phan "phat tiep" chi la mot `onClick` them vao.
 */

import Link from "next/link";
import { createContext, useContext } from "react";

export interface ChuongLienKe {
  chapter_id: string;
  title: string;
  /** `undefined` = khong biet — coi nhu co, de khong chan phat tiep. */
  has_audio?: boolean;
}

export interface NguCanhChuong {
  /** Goi TRUOC khi dieu huong toi `dich`: giao audio cho chuong dich neu dang nghe. */
  giaoAudio: (dich: ChuongLienKe) => void;
}

export const ChapterContext = createContext<NguCanhChuong | null>(null);

export function useChapterContext(): NguCanhChuong | null {
  return useContext(ChapterContext);
}

export function ChapterNavLink({
  target,
  href,
  className,
  rel,
  children,
}: {
  target: ChuongLienKe;
  href: string;
  className?: string;
  rel?: string;
  children: React.ReactNode;
}) {
  const ctx = useChapterContext();
  return (
    <Link
      className={className}
      href={href}
      prefetch={false}
      rel={rel}
      onClick={(e) => {
        // Mo tab moi / tai ve: khong phai dieu huong trong trang nay.
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        ctx?.giaoAudio(target);
      }}
    >
      {children}
    </Link>
  );
}
