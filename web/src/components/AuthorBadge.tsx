/**
 * HAI huy hieu, va chung noi HAI chuyen khac nhau.
 *
 *   `<AuthorBadge/>`  da duoc duyet xuat ban cong khai. Day la MODERATION.
 *   `<RankBadge/>`    uy tin, tinh tu so luot nghe hop le. KHONG phai xac minh.
 *
 * Mot tac gia hang cao van co the bi treo. Mot tac gia moi duoc duyet van o hang
 * thap nhat. Nen hai thu phai PHAN BIET DUOC BANG MAT, khong duoc trong giong
 * nhau chi vi ca hai cung mau vang:
 *
 *   huy hieu tac gia   VIEN LIEN + ngoi but + chu "Tác giả"
 *   huy hieu hang      KHONG vien + mot dau an hinh hoc + ten hang
 *
 * Dung hang de ngu y "da duoc kiem duyet" la sai. Xem `docs/AUTHOR_RANK.md`.
 */

import type { RankProgress } from "@/lib/api";

/**
 * Huy hieu TAC GIA: mot ngoi but trong mot vien lien.
 *
 * Vien lien la tin hieu chinh — no doc ra la "co mot cai khung quanh nguoi nay",
 * tuc la co ai do da xac nhan. Huy hieu hang khong bao gio co vien lien.
 */
export function AuthorBadge({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <span
      className={`hh-tacgia${size === "sm" ? " hh-sm" : ""}`}
      title="Tác giả đã được duyệt"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        {/* Ngoi but long chim: mot net cong cho than but, mot net cho ngoi. */}
        <path
          d="M19 4.5c-6.2.6-10.4 3.9-12 8.4-.5 1.4-.7 2.9-.7 4.6M19 4.5c.5 4.6-1.2 8-4.4 9.7-1.6.9-3.5 1.2-5.6 1.1M19 4.5 6.3 17.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span>Tác giả</span>
    </span>
  );
}

/**
 * Nam dau an cho sau bac hang.
 *
 * Hinh hoc doi theo bac — khong chi doi mau. Mot he huy hieu chi khac nhau o mau
 * thi nguoi khong phan biet duoc mau se thay sau cai giong het nhau, va ke ca
 * nguoi phan biet duoc mau cung phai hoc mot bang mau truoc khi doc duoc no.
 *
 * `level` 1..6 tu `RANK_TIERS` o backend. Bac la ma OFF-BY-ONE de nhat, nen o
 * day chi so duoc kep vao khoang thay vi tin tuyet doi.
 */
const DAU_AN = [
  // 1 — Tan But: mot net don.
  <path key="1" d="M12 5.5v13" />,
  // 2 — Nguoi Ke Chuyen: hai net giao nhau.
  <path key="2" d="M12 5v14M6.5 9.5 12 5l5.5 4.5" />,
  // 3 — Ke Det Mong: mot hinh thoi.
  <path key="3" d="M12 4.5 18 12l-6 7.5L6 12z" />,
  // 4 — Bien Nien Su Gia: hinh thoi trong mot vong.
  <path key="4" d="M12 4.5 18 12l-6 7.5L6 12zM12 8.6 15.2 12 12 15.4 8.8 12z" />,
  // 5 — Huyen Thoai Di Gioi: sao sau canh.
  <path key="5" d="M12 3.5v17M4.6 7.75l14.8 8.5M19.4 7.75l-14.8 8.5" />,
  // 6 — Than But: sao sau canh trong mot vong.
  <g key="6">
    <path d="M12 3.5v17M4.6 7.75l14.8 8.5M19.4 7.75l-14.8 8.5" />
    <circle cx="12" cy="12" r="4.2" />
  </g>,
];

export function RankBadge({
  rank,
  size = "md",
}: {
  rank: RankProgress;
  size?: "sm" | "md";
}) {
  const bac = Math.min(DAU_AN.length, Math.max(1, rank.level));
  return (
    <span
      className={`hh-hang${size === "sm" ? " hh-sm" : ""}`}
      data-bac={bac}
      title={`Hạng ${rank.title} — ${rank.qualified_listens} lượt nghe hợp lệ`}
    >
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        focusable="false"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {DAU_AN[bac - 1]}
      </svg>
      <span>{rank.title}</span>
    </span>
  );
}

/**
 * Thanh tien toi hang sau.
 *
 * KHONG ve khi da o hang cao nhat: mot thanh day 100% khong noi them dieu gi, va
 * no chiem cho cua thu khac.
 */
export function RankProgressBar({ rank }: { rank: RankProgress }) {
  if (!rank.next_title) {
    return (
      <p className="hint">
        Đã ở hạng cao nhất — {rank.qualified_listens.toLocaleString("vi-VN")} lượt
        nghe hợp lệ.
      </p>
    );
  }
  return (
    <div className="stack-2">
      <div
        className="rank-thanh"
        role="progressbar"
        aria-valuenow={rank.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Tiến tới hạng ${rank.next_title}`}
      >
        <span style={{ width: `${rank.percent}%` }} />
      </div>
      <p className="hint">
        Còn <strong>{rank.remaining.toLocaleString("vi-VN")}</strong> lượt nghe
        hợp lệ nữa để lên <strong>{rank.next_title}</strong>.
      </p>
    </div>
  );
}
