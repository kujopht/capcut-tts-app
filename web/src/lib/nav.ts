/**
 * Kiem tra tham so `next` cua trang dang nhap.
 *
 * VI SAO CAN: sau khi dang nhap, trang se dieu huong toi gia tri nay. Neu
 * nhan bat ky chuoi nao thi `?next=https://vi-du-lua-dao.tld` bien trang dang
 * nhap that cua Fanfic World thanh mot buoc trung gian dang tin cua mot trang
 * lua dao — nguoi dung go mat khau o dung ten mien that, roi bi day sang cho
 * khac. Do la open redirect, va no dac biet nguy hiem o TRANG DANG NHAP.
 *
 * Chi nhan duong dan NOI BO. Cac dang bi tu choi, moi dang vi mot ly do:
 *
 *   `https://x.tld`   — tuyet doi, ra ngoai mien
 *   `//x.tld`         — "protocol-relative": trinh duyet hieu la mien khac
 *   `/\x.tld`         — mot so trinh duyet chuan hoa `\` thanh `/`, thanh `//`
 *   `javascript:...`  — khong phai dieu huong, la thuc thi ma
 *   `write`           — thieu `/` dau: khong ro rang, va de ghep nham
 *
 * BEN BACKEND CUNG PHAI KIEM. Ham nay chay o trinh duyet, va trinh duyet thi
 * khong phai hang rao — `/api/auth/oauth/google?next=...` nhan `next` truc
 * tiep tu URL, khong qua ma nay.
 */

/** Noi ve khi khong co `next` hop le. Trang chu, khong phai `/studio`. */
export const DEFAULT_NEXT = "/";

export function safeNext(raw: string | null | undefined): string {
  const value = (raw ?? "").trim();
  if (!value) return DEFAULT_NEXT;
  if (!value.startsWith("/")) return DEFAULT_NEXT;
  if (value.startsWith("//")) return DEFAULT_NEXT;
  if (value.includes("\\")) return DEFAULT_NEXT;
  // `/login` -> `/login` la mot vong lap: dang nhap xong lai ve trang dang nhap.
  if (value === "/login" || value.startsWith("/login?")) return DEFAULT_NEXT;
  return value;
}

/** Duong toi trang dang nhap kem noi can quay lai. */
export function loginHref(next: string): string {
  const target = safeNext(next);
  return target === DEFAULT_NEXT
    ? "/login"
    : `/login?next=${encodeURIComponent(target)}`;
}

/**
 * Khoa dieu huong dang xem TU NGU NGHIA, khong chi tu pathname tho.
 *
 * LOI DA XAY RA (Navigation Motion Correction V3): khach bam "Viết truyện"
 * o trang chu -> `/write` tu doi huong phia client sang
 * `/login?next=%2Fwrite` (xem `write/page.tsx`). Vien thuoc dua hoan toan
 * vao `pathname` tho thi thay `/login` KHONG khop muc nao trong thanh dieu
 * huong -> an di -> roi tai xuat hien tu vi tri "Viết truyện" cu (hinh hoc
 * an cu) khi nguoi dung dieu huong tiep — trong khi ve mat nguoi dung ho
 * VAN dang o giua luong "Viết truyện", chua roi khoi no.
 *
 * CACH SUA: `/login`/`/register` VOI `next=` tro toi mot khu vuc dieu huong
 * duoc coi la CHINH khu vuc do, khong phai "khong co gi". Dung lai
 * `safeNext` (da co, da kiem open-redirect) de doc `next` — mot cong hai
 * viec thay vi mot ham rieng.
 *
 * CHI /login, /register: day la HAI trang trung gian xac thuc DUY NHAT
 * trong san pham dung tham so `next` theo dung quy uoc cua `loginHref`.
 */
export function resolveNavHref(
  pathname: string,
  next: string | null | undefined,
  hrefs: readonly string[],
): string {
  const khop = (path: string): string =>
    hrefs.find((h) =>
      h === "/" ? path === "/" : path === h || path.startsWith(`${h}/`),
    ) ?? "";

  const truc_tiep = khop(pathname);
  if (truc_tiep) return truc_tiep;

  if (pathname === "/login" || pathname === "/register") {
    const dich = safeNext(next);
    if (dich !== DEFAULT_NEXT) {
      return khop(dich.split("?")[0].split("#")[0]);
    }
  }
  return "";
}
