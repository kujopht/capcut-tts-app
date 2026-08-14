/**
 * Khu vuc cua the gioi, va HUONG di giua chung.
 *
 * VAN DE DA CO: doi trang la mot tam mo ra, mot tam hien vao — dung cho, nhung
 * doc ra nhu doi mot tam anh, khong nhu di qua mot the gioi lien mach. Nguoi
 * dung khong co cam giac minh dang o dau trong site.
 *
 * CACH LAM: cac khu vuc chinh nam tren MOT TRUC, theo dung thu tu ma nguoi dung
 * di qua chung:
 *
 *     Trang chu -> Kham pha -> Thu vien -> Viet -> Studio -> Tai khoan
 *      doc     ->  tim     ->  nghe    -> tao ->  tao   ->  minh
 *
 * Di sang PHAI trong danh sach thi may quay truot sang phai. Di ve TRAI thi
 * nguoc lai. Nho vay mot cu bam "Quay lai" cua trinh duyet cung tra ve dung
 * huong ma khong phai luu them trang thai nao.
 *
 * Module nay la TypeScript thuan va khong import gi tu duong dan khong duoi:
 * `node --test` chay duoc no truc tiep — xem `lib/backgrounds.ts` de biet vi sao
 * rang buoc do ton tai.
 */

/**
 * Truc chinh. Thu tu o day la mot quyet dinh SAN PHAM, khong phai thu tu tinh co
 * cua mot cai menu: no la hanh trinh cua nguoi dung tu "doc truyen cua nguoi
 * khac" toi "lam truyen cua minh" roi toi "chinh minh".
 */
export const TRUC = [
  "home",
  "explore",
  // Animation (V6, overnight Phase 5) nam NGAY SAU "Kham pha" — cung mot nhip
  // XEM/DOC, truoc khi re sang "Cong dong". Day la mot san pham DOC LAP voi
  // Truyen/Audio (xem docstring dau `server/animation_domain.py`), nhung tren
  // TRUC dieu huong no dung canh "Kham pha" vi ca hai deu la "tim thu de
  // tieu thu", khac voi "Cong dong" (tuong tac xa hoi).
  "animation",
  // "Cộng đồng" nằm giữa "Khám phá" và "Thư viện", không phải ở cuối trục.
  //
  // Trục này là hành trình đọc → nghe → viết, và bảng tin thuộc về nửa ĐỌC:
  // người ta ghé cộng đồng để biết có gì mới của người mình theo dõi, rồi từ đó
  // đi vào truyện. Đặt nó sau `write`/`studio` sẽ khiến một cú bấm từ "Khám phá"
  // sang "Cộng đồng" quay máy đi qua cả khu sáng tác — sai nhịp so với việc
  // người dùng thực sự đang làm.
  "community",
  "library",
  "write",
  "studio",
  "account",
] as const;

export type KhuVuc = (typeof TRUC)[number];

/**
 * Cac trang KHONG nam tren truc.
 *
 *   `long`  trang con cua mot khu vuc — `/novels/*`, `/chapters/*`. Chung khong
 *           phai mot the gioi rieng, chi la mot cho ben trong mot khu vuc, nen
 *           chuyen canh phai NHE han: dich ngang mot chut cong mo dan.
 *   `ngoai` dang nhap / callback. Dung o ngoai truc han.
 */
export type ViTri = KhuVuc | "long" | "ngoai";

/** `-1` lui, `1` tien, `0` khong co huong (trang long, hoac cung mot cho). */
export type Huong = -1 | 0 | 1;

const BANG: ReadonlyArray<readonly [RegExp, ViTri]> = [
  [/^\/$/, "home"],
  [/^\/fanfic/, "explore"],
  [/^\/animation/, "animation"],
  [/^\/community/, "community"],
  [/^\/library/, "library"],
  [/^\/write/, "write"],
  [/^\/studio/, "studio"],
  [/^\/account/, "account"],
  // Trang truyen va trang doc chuong: BEN TRONG the gioi, khong phai mot khu
  // vuc rieng. Xem `Huong` va `viTri`.
  [/^\/novels\//, "long"],
  [/^\/chapters\//, "long"],
  // Trang ca nhan va dang ky tac gia deu la trang BEN TRONG mot khu vuc,
  // khong phai mot khu vuc rieng tren truc.
  [/^\/u\//, "long"],
  [/^\/creator\//, "long"],
  // Mot bai dang le, va trang thong bao: ben TRONG khu cong dong.
  [/^\/posts\//, "long"],
  [/^\/notifications/, "long"],
  // `/admin` KHONG nam tren truc: no khong phai mot khu vuc cua the gioi
  // truyen, va mot cu quay may khi vao khu quan tri la sai nhip.
  [/^\/admin/, "long"],
  [/^\/login/, "ngoai"],
  [/^\/auth\//, "ngoai"],
];

/** Khu vuc cua mot duong dan. Duong la thi coi nhu `ngoai`. */
export function viTri(duongDan: string): ViTri {
  const duong = (duongDan || "/").split("?")[0].split("#")[0];
  for (const [mau, ten] of BANG) {
    if (mau.test(duong)) return ten;
  }
  return "ngoai";
}

/**
 * Huong di giua hai duong dan.
 *
 * Tra `0` khi mot trong hai dau KHONG nam tren truc: mot trang long hay trang
 * dang nhap khong co "ben phai" hay "ben trai" nao co nghia, va bia ra mot huong
 * cho chung se lam nguoi dung hoc sai ban do.
 */
export function huongDi(tu: string, den: string): Huong {
  const a = viTri(tu);
  const b = viTri(den);
  if (a === b) return 0;
  const i = TRUC.indexOf(a as KhuVuc);
  const j = TRUC.indexOf(b as KhuVuc);
  if (i === -1 || j === -1) return 0;
  return j > i ? 1 : -1;
}

/**
 * Ten hieu ung de dat vao `data-huong` cho CSS doc.
 *
 * Dat ten thay vi so: mot `data-huong="1"` bat CSS phai viet `[data-huong="1"]`,
 * va sau sau thang khong ai con nho `1` la tien hay lui.
 */
export function tenHuong(huong: Huong): "tien" | "lui" | "nhe" {
  if (huong === 1) return "tien";
  if (huong === -1) return "lui";
  return "nhe";
}

/**
 * Chi so cua khu vuc tren truc, de giao dien danh dau muc dang xem.
 *
 * `-1` cho trang khong nam tren truc.
 */
export function chiSoTruc(duongDan: string): number {
  return TRUC.indexOf(viTri(duongDan) as KhuVuc);
}
