"use client";

/**
 * Nut hanh dong CHINH cua trang truyen — doi theo tien do that cua nguoi doc
 * (Product UX Sprint 2).
 *
 *   chua doc          -> "Bắt đầu đọc" / "Bắt đầu nghe" (+ "Đọc & nghe")
 *   doc do            -> "Đọc tiếp"            (dung chuong, dung doan)
 *   nghe do           -> "Nghe tiếp"           (dung chuong, dung giay)
 *   doc + nghe do     -> "Tiếp tục đọc & nghe"
 *   xong mot chuong   -> "Đọc/Nghe chương tiếp theo"
 *
 * Lien ket "tiếp" mang `?resume=1`: trang chuong AP vi tri da luu ngay, khong
 * hoi lai (`ChapterExperience.autoResume`).
 *
 * HTML may chu luon ve trang thai "chua doc" (may chu khong biet
 * `localStorage`); sau hydrate moi doi — `useReaderProgress` dung anh chup
 * may chu RONG nen hai lan ve dau khop nhau, khong loi hydrate.
 */

import Link from "next/link";
import { useMemo } from "react";
import { IconBook, IconHeadphones } from "@/components/Icons";
import { useReaderProgress } from "@/lib/useReaderProgress";
import { banGhiMoiNhat, hanhDongTruyen } from "@/lib/novelProgress";

export interface LienKetBatDau {
  href: string;
  nhan: string;
  nghe: boolean;
}

export function NovelPrimaryCta({
  novelId,
  coAudio,
  chiAudio,
  chuong,
  batDau,
  phu,
}: {
  novelId: string;
  coAudio: boolean;
  chiAudio: boolean;
  /** Muc luc theo DUNG thu tu backend (id + ten), de biet "chương tiếp theo". */
  chuong: { id: string; tieuDe: string }[];
  /** Lien ket bat dau (may chu dung san, dung tham so trang chuong hieu). */
  batDau: LienKetBatDau;
  /** Lien ket bat dau phu (vd "Đọc & nghe") — chi hien khi chua doc. */
  phu?: LienKetBatDau | null;
}) {
  const banGhi = useReaderProgress();
  const viTri = useMemo(() => new Map(chuong.map((c, i) => [c.id, i])), [chuong]);

  const r = banGhiMoiNhat(banGhi, novelId);
  const hd = hanhDongTruyen(r, {
    coAudio,
    chiAudio,
    chuongDau: chuong[0]?.id ?? null,
    chuongSau: (id) => {
      const i = viTri.get(id);
      return i === undefined ? null : (chuong[i + 1]?.id ?? null);
    },
  });

  // Chua doc, hoac da doc het chuong moi nhat: ve nut bat dau cua may chu.
  if (hd.kieu === "moi" || !hd.href) {
    return (
      <>
        <Link className="btn btn-primary" href={batDau.href}>
          {batDau.nghe ? <IconHeadphones size={16} /> : <IconBook size={16} />} {batDau.nhan}
        </Link>
        {phu ? (
          <Link className="btn btn-outline" href={phu.href}>
            {phu.nghe ? <IconHeadphones size={16} /> : <IconBook size={16} />} {phu.nhan}
          </Link>
        ) : null}
        {hd.kieu === "xong" ? (
          <span className="novel-cta-note hint">Bạn đã tới chương mới nhất.</span>
        ) : null}
      </>
    );
  }

  const nghe = hd.kieu === "nghe" || hd.kieu === "ca-hai" || hd.nhanDayDu.startsWith("Nghe");
  const tenChuong = hd.chapterId
    ? (chuong[viTri.get(hd.chapterId) ?? -1]?.tieuDe ?? r?.tenChuong ?? null)
    : null;
  const pct = hd.tiLe !== null && hd.kieu !== "xong" ? Math.max(1, Math.round(hd.tiLe * 100)) : null;

  return (
    <>
      <Link className="btn btn-primary" href={hd.href}>
        {nghe ? <IconHeadphones size={16} /> : <IconBook size={16} />} {hd.nhanDayDu}
      </Link>
      <Link className="btn btn-ghost" href={batDau.href}>
        Từ chương đầu
      </Link>
      {tenChuong ? (
        <span className="novel-cta-note hint">
          {hd.kieu === "xong" ? "Tiếp theo: " : "Đang ở: "}
          <strong>{tenChuong}</strong>
          {pct !== null ? ` · ${pct}%` : ""}
        </span>
      ) : null}
    </>
  );
}
