/**
 * MUC DIEU HUONG CHINH nao dang "sang" cho mot duong dan (Product UX Sprint 2).
 *
 * Ban truoc chi so `pathname` voi `href` cua bon muc: dang doc mot truyen
 * (`/novels/*`) hay mot chuong (`/chapters/*`) thi KHONG muc nao sang — nguoi
 * doc mat dau moc "minh dang o dau" dung luc sau nhat trong site. Truyen va
 * chuong thuoc Thu vien; bai dang va trang ca nhan thuoc Cong dong; Animation
 * nam trong Giai tri.
 *
 * Tep thuan, khong import — `tests/nav-active.test.mjs`.
 */

const BANG: ReadonlyArray<readonly [RegExp, string]> = [
  [/^\/community(\/|$)/, "/community"],
  [/^\/posts\//, "/community"],
  [/^\/u\//, "/community"],
  [/^\/library(\/|$)/, "/library"],
  [/^\/novels\//, "/library"],
  [/^\/chapters\//, "/library"],
  [/^\/fanfic(\/|$)/, "/library"],
  [/^\/entertainment(\/|$)/, "/entertainment"],
  [/^\/animation(\/|$)/, "/entertainment"],
];

/** `href` cua muc chinh dang sang, hoac chuoi rong (vd `/studio`, `/account`). */
export function mucDangXem(pathname: string): string {
  // "/" khop CHINH XAC: `startsWith("/")` thi moi trang deu sang "Trang chủ".
  if (pathname === "/") return "/";
  for (const [mau, href] of BANG) if (mau.test(pathname)) return href;
  return "";
}
