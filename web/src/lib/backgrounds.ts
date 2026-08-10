/**
 * Duong dan -> ten tranh nen toan trang.
 *
 * MOT TEP RIENG khong import gi ca, cung ly do voi `lib/time.ts`: Node khong
 * nap duoc `.tsx`, nen de bang anh xa nay trong component thi khong bo test
 * don vi nao cham toi duoc — chi con cach quet ma nguon bang regex.
 *
 * Cac tam nay la KHONG KHI toan trang, KHONG phai bia truyen. Bia rieng cho
 * tung truyen la mot tinh nang khac, lam sau.
 */

/**
 * Thu tu QUAN TRONG: khop tu cu the toi chung.
 *
 * `/` phai so khop CHINH XAC. Dung `startsWith("/")` thi moi trang trong site
 * deu dinh nen trang chu.
 */
const NEN: Array<[RegExp, string]> = [
  [/^\/$/, "home"],
  [/^\/fanfic/, "explore"],
  // Trang truyen dung CUNG tam voi trang kham pha: ca hai deu la buoc DUYET,
  // chua phai buoc doc. Trang doc chuong moi doi sang den trang mieu.
  [/^\/novels\//, "explore"],
  [/^\/chapters\//, "reader"],
  [/^\/studio/, "studio"],
  [/^\/write/, "write"],
  [/^\/library/, "library"],
  [/^\/account/, "account"],
  [/^\/login/, "auth"],
  [/^\/auth\//, "auth"],
];

/** Trang khong nam trong bang tren dung nen bau troi — xem README cua bo anh. */
const MAC_DINH = "auth";

export function tenNen(duong_dan: string): string {
  for (const [mau, ten] of NEN) {
    if (mau.test(duong_dan)) return ten;
  }
  return MAC_DINH;
}
