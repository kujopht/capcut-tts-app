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
  // Trang ca nhan: cung the gioi voi trang kham pha — day la cho de TIM
  // ra nguoi khac, khong phai mot cong dang nhap.
  [/^\/u\//, "explore"],
  // Dang ky tac gia: cung tam voi khu vuc tac gia.
  [/^\/creator\//, "write"],
  // Khu quan tri: dung tam TOI NHAT (`write`, phu 0.50) va co them mot
  // mang toi rieng — day la mot be mat lam viec, khong phai mot khung
  // canh. Khong khai thi no roi vao nhanh mac dinh `auth` va duoc ve
  // bang tranh cong sao kem sao bang troi qua.
  [/^\/admin/, "write"],
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

/**
 * Ten tep cua tung tam.
 *
 * Nam o day chu khong chi trong CSS vi `PageBackground` phai NAP TRUOC anh moi
 * bang `new Image()` truoc khi chuyen canh — khong nap truoc thi trinh duyet ve
 * mot khung trong trong luc tai, va nguoi dung thay mot nhay den.
 *
 * Bo test doi soat bang nay voi cac `url()` trong `globals.css`, nen hai cho
 * khong the lech nhau ma khong ai biet.
 */
const TEP: Record<string, string> = {
  home: "01-home-sunny-harbor",
  explore: "02-explore-sky-kingdom",
  reader: "03-reader-moonlit-shrine",
  studio: "04-studio-sky-workshop",
  write: "05-write-creators-room",
  library: "06-library-arcane-archive",
  account: "07-account-blossom-realm",
  auth: "08-login-starlight-gate",
};

/** Duong dan tam LON. Ban cho dien thoai do CSS chon qua media query. */
export function anhNen(ten: string): string {
  const tep = TEP[ten] ?? TEP[MAC_DINH];
  return `/artwork/fantasy-backgrounds/${tep}.webp`;
}

/**
 * Live Wallpaper — rollout V4 (2026-08), CA 8 chu de. Video do NGUOI DUNG tu
 * tao thu cong tu chinh 8 buc tranh tinh o tren (khong qua Pollinations,
 * khong AI sinh) — xem bao cao rollout cho kiem tra chat luong/vong lap day
 * du. Ban runtime (H.264, 1920x1080, 30fps, khong am thanh) nam o
 * `/artwork/fantasy-backgrounds/live/`; ban goc (master) KHONG nam trong
 * repo (giu o `Downloads/donelive`, tep goc HEVC 2560x1440 60fps qua nang
 * cho web — xem bao cao ma-hoa).
 *
 * MOT TEP MOI CHU DE — `PageBackground.tsx` doc DUY NHAT ham nay, khong tu
 * ghep chuoi duong dan `ten` -> tep o component (dac ta muc 9: "one
 * declarative mapping... Do NOT scatter route -> mp4 hardcoded strings").
 */
const VIDEO: Record<string, string> = {
  home: "01-home",
  explore: "02-explore",
  reader: "03-reader",
  studio: "04-studio",
  write: "05-write",
  library: "06-library",
  account: "07-account",
  auth: "08-auth",
};

export interface NguonVideoNen {
  mp4: string;
}

/** `undefined` = chu de chua co live wallpaper — component chi ve poster. */
export function videoNen(ten: string): NguonVideoNen | undefined {
  const tep = VIDEO[ten];
  if (!tep) return undefined;
  return { mp4: `/artwork/fantasy-backgrounds/live/${tep}.mp4` };
}
