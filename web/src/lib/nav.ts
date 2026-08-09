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
