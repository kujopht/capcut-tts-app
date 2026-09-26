/**
 * TRANG THAI THU VIEN <-> URL.
 *
 * Tim kiem, bo loc, sap xep, kieu xem va trang deu nam tren URL: chia se lien
 * ket ra dung danh sach, va nut Back/Forward cua trinh duyet dua nguoi doc ve
 * dung bo loc truoc do. Gia tri MAC DINH KHONG ghi len URL — `/library` tran la
 * trang mac dinh, khong phai `/library?sort=updated&audio=all&...`.
 *
 * Tep thuan — `tests/library-query.test.mjs`.
 */

export type TabThuVien = "fanfic" | "personal" | "books";
export type LocAudio = "all" | "audio" | "read_audio" | "text" | "legacy";
export type LocTrangThai = "all" | "ongoing" | "completed";
export type SapXep = "updated" | "latest" | "chapters" | "title";
export type KieuXem = "grid" | "list";

export interface TrangThaiThuVien {
  tab: TabThuVien;
  q: string;
  fandom: string;
  audio: LocAudio;
  status: LocTrangThai;
  sort: SapXep;
  view: KieuXem;
  /** 1-based. */
  page: number;
}

export const MAC_DINH_THU_VIEN: TrangThaiThuVien = {
  tab: "fanfic",
  q: "",
  fandom: "all",
  audio: "all",
  status: "all",
  sort: "updated",
  view: "grid",
  page: 1,
};

/** Nhan tieng Viet tu nhien cho sap xep. */
export const NHAN_SAP_XEP: Record<SapXep, string> = {
  updated: "Mới cập nhật",
  latest: "Mới xuất bản",
  chapters: "Nhiều chương",
  title: "Tên truyện (A–Z)",
};

const AUDIO: readonly LocAudio[] = ["all", "audio", "read_audio", "text", "legacy"];
const STATUS: readonly LocTrangThai[] = ["all", "ongoing", "completed"];
const SORT: readonly SapXep[] = ["updated", "latest", "chapters", "title"];

interface DocDuoc {
  get(key: string): string | null;
}

/** Ten goi tat / sai hoa thuong tren lien ket -> ten chuan cua chip. */
const BI_DANH_FANDOM: Record<string, string> = {
  naruto: "Naruto",
  "one piece": "One Piece",
  onepiece: "One Piece",
  conan: "Detective Conan",
  "detective conan": "Detective Conan",
  genshin: "Genshin Impact",
  "genshin impact": "Genshin Impact",
  "fairy tail": "Fairy Tail",
};

export function chuanHoaFandom(raw: string): string {
  const s = raw.trim().slice(0, 60);
  if (!s || s === "all") return "all";
  return BI_DANH_FANDOM[s.toLowerCase()] ?? s;
}

export function docTuUrl(sp: DocDuoc): TrangThaiThuVien {
  const tabRaw = sp.get("tab");
  const tab: TabThuVien =
    tabRaw === "personal" || tabRaw === "mine" ? "personal" : tabRaw === "books" ? "books" : "fanfic";
  // Lien ket cu: `?tag=fandom:Naruto` hoac `?tag=Naruto`.
  let fandom = sp.get("fandom") ?? "";
  if (!fandom) {
    const tag = sp.get("tag");
    if (tag && tag !== "all") fandom = tag.startsWith("fandom:") ? tag.slice(7) : tag;
  }
  const audio = sp.get("audio") as LocAudio | null;
  const status = sp.get("status") as LocTrangThai | null;
  const sort = sp.get("sort") as SapXep | null;
  const page = Number.parseInt(sp.get("page") ?? "1", 10);
  return {
    tab,
    q: (sp.get("q") ?? "").slice(0, 120),
    fandom: chuanHoaFandom(fandom),
    audio: audio && AUDIO.includes(audio) ? audio : "all",
    status: status && STATUS.includes(status) ? status : "all",
    sort: sort && SORT.includes(sort) ? sort : "updated",
    view: sp.get("view") === "list" ? "list" : "grid",
    page: Number.isFinite(page) && page > 1 ? Math.min(page, 999) : 1,
  };
}

/** Chuoi truy van (khong co `?`), bo moi gia tri mac dinh, thu tu on dinh. */
export function veUrl(t: TrangThaiThuVien): string {
  const p = new URLSearchParams();
  if (t.tab !== "fanfic") p.set("tab", t.tab);
  if (t.q.trim()) p.set("q", t.q.trim());
  if (t.fandom !== "all") p.set("fandom", t.fandom);
  if (t.audio !== "all") p.set("audio", t.audio);
  if (t.status !== "all") p.set("status", t.status);
  if (t.sort !== "updated") p.set("sort", t.sort);
  if (t.view !== "grid") p.set("view", t.view);
  if (t.page > 1) p.set("page", String(t.page));
  return p.toString();
}

/**
 * Doi mot phan trang thai. Doi BO LOC (khong phai trang/kieu xem) thi ve
 * trang 1 — trang 3 cua mot bo loc cu khong co nghia voi bo loc moi.
 */
export function doi(t: TrangThaiThuVien, phan: Partial<TrangThaiThuVien>): TrangThaiThuVien {
  const moi = { ...t, ...phan };
  const doiLoc = (["q", "fandom", "audio", "status", "sort", "tab"] as const).some(
    (k) => k in phan && phan[k] !== t[k],
  );
  if (doiLoc && !("page" in phan)) moi.page = 1;
  return moi;
}

/** So bo loc dang bat (khong tinh tim kiem, sap xep, kieu xem). */
export function soBoLoc(t: TrangThaiThuVien): number {
  return (t.fandom !== "all" ? 1 : 0) + (t.audio !== "all" ? 1 : 0) + (t.status !== "all" ? 1 : 0);
}

/**
 * Gia tri `sort` GUI LEN backend cho tung lua chon.
 *
 * DO THAT tren production 2026-09-25 (`GET /api/novels`, kho Appwrite):
 *   - `latest` va `updated` DEU sap theo `updated_at` — ban truoc gui `latest`
 *     cho "Mới xuất bản" nen lua chon do tra ve Y HET "Mới cập nhật";
 *   - `newest` moi sap theo `created_at` (= moi xuat ban);
 *   - `chapters` bi kho Appwrite BO QUA (roi ve `updated_at`) — chi kho trong
 *     bo nho ho tro. Vi vay "Nhiều chương" sap CUC BO (xem `sapXepCucBo`).
 */
export const SAP_XEP_MAY_CHU: Record<SapXep, string> = {
  updated: "updated",
  latest: "newest",
  chapters: "chapters",
  title: "title",
};

/**
 * Hai lua chon sap CUC BO tren trinh duyet: backend khong sap dung duoc.
 * - "Nhiều chương": kho Appwrite bo qua `sort=chapters`.
 * - "Tên truyện": Appwrite so chuoi tho — "The Cold…" dung truoc "[Naruto]…"
 *   va chu co dau xep sai; nguoi doc Viet can thu tu tieng Viet, bo tien to
 *   "[Fandom]" dau ten.
 * Lay ca pham vi (toi da `TRAN_CUC_BO` truyen, tran `limit` cua backend) mot
 * lan roi sap + cat trang o day. Vuot tran thi bao ro la chi sap phan dau.
 */
export const TRAN_CUC_BO = 50;

/** Fandom ma bo loc `fandom` cua backend nhan ra (xem `appwrite_store.find_novels`). */
export const FANDOM_MAY_CHU: ReadonlySet<string> = new Set([
  "Naruto",
  "One Piece",
  "Detective Conan",
  "Genshin Impact",
  "Fairy Tail",
]);
export function sapCucBo(sort: SapXep): boolean {
  return sort === "chapters" || sort === "title";
}

/**
 * Tham so goi `api.browseNovels` tu trang thai URL.
 *
 * Bon lua chon dinh dang KHAC NHAU that (ban truoc "Có Audio" va "Đọc & Nghe"
 * tra ve y het nhau trong kho doc duoc):
 *   - "Tất cả"      : kho DOC DUOC (mac dinh — kho audio cu khong tu hien)
 *   - "Có audio"    : moi thu nghe duoc, KE CA kho audio cu (nguoi doc chon)
 *   - "Đọc & nghe"  : co chu VA co audio
 *   - "Chỉ chữ"     : co chu, chua co audio
 *   - "Kho audio cũ": chi truyen audio dai tap nhap tu kho cu
 */
export function thamSoDuyet(t: TrangThaiThuVien, kichThuocTrang: number) {
  const content_mode: "audio_only" | "readable" | "all" =
    t.audio === "legacy" ? "audio_only" : t.audio === "audio" ? "all" : "readable";
  const cucBo = sapCucBo(t.sort);
  const coFandom = t.fandom !== "all";
  // Backend co nhanh rieng cho nam fandom nay (so ca `fandom_ids` lan the
  // "fandom:X"); fandom khac chi khop khi gui dung the "fandom:X" qua `tag`.
  const quaFandom = coFandom && FANDOM_MAY_CHU.has(t.fandom);
  return {
    query: t.q,
    fandom: quaFandom ? t.fandom : undefined,
    tag: coFandom && !quaFandom ? `fandom:${t.fandom}` : undefined,
    status: t.status === "all" ? undefined : t.status,
    audio: t.audio === "audio" || t.audio === "read_audio" ? true : t.audio === "text" ? false : undefined,
    sort: SAP_XEP_MAY_CHU[t.sort],
    limit: cucBo ? TRAN_CUC_BO : kichThuocTrang,
    offset: cucBo ? 0 : (t.page - 1) * kichThuocTrang,
    content_mode,
  };
}

/** Ten de SAP theo chu cai: bo tien to "[Naruto] " / "[Naruto SI] " dau ten. */
export function tenDeSap(title: string): string {
  return title.replace(/^\s*(\[[^\]]{1,40}\]\s*)+/, "").trim() || title;
}

const soSanhViet = new Intl.Collator("vi", { sensitivity: "base", numeric: true });

interface CoTen {
  title: string;
  external_chapter_count?: number | null;
}

/** Sap cuc bo (khong doi mang goc). Lua chon khac giu nguyen thu tu may chu. */
export function sapXepCucBo<T extends CoTen>(ds: readonly T[], sort: SapXep): T[] {
  if (sort === "title") {
    return [...ds].sort((a, b) => soSanhViet.compare(tenDeSap(a.title), tenDeSap(b.title)));
  }
  if (sort === "chapters") {
    return [...ds].sort(
      (a, b) =>
        (b.external_chapter_count ?? 0) - (a.external_chapter_count ?? 0) ||
        soSanhViet.compare(tenDeSap(a.title), tenDeSap(b.title)),
    );
  }
  return [...ds];
}

/* ------------------------------------------------------ chip fandom that */

export interface CoCo {
  /** Truyen audio dai tap nhap tu kho cu (`isLegacyAudioOnly`). */
  cu: boolean;
  /** Co audio (`novelHasAudio`). */
  audio: boolean;
  status: string;
}

/**
 * Truyen co thuoc PHAM VI dinh dang/trang thai dang chon khong — cung quy tac
 * voi `thamSoDuyet` (khong tinh fandom va tim kiem).
 */
export function thuocPham(t: TrangThaiThuVien, c: CoCo): boolean {
  if (t.status !== "all" && c.status !== t.status) return false;
  switch (t.audio) {
    case "legacy":
      return c.cu;
    case "audio":
      return c.audio;
    case "read_audio":
      return !c.cu && c.audio;
    case "text":
      return !c.cu && !c.audio;
    default:
      return !c.cu;
  }
}

/**
 * Chip fandom tu DU LIEU THAT: chi fandom CO truyen trong pham vi dang chon,
 * nhieu truyen xep truoc. Ban truoc dat cung bay chip ("Sci-Fi / Warhammer",
 * "Thể thao / Bóng rổ"…) — phan lon bam vao ra trang rong.
 * Fandom dang chon (vd tu URL) LUON co mat, ke ca khi mau khong co.
 */
export function chipFandom<T>(
  mau: readonly T[],
  fandomCua: (n: T) => string,
  coCua: (n: T) => CoCo,
  t: TrangThaiThuVien,
): { ten: string; so: number }[] {
  const dem = new Map<string, number>();
  for (const n of mau) {
    if (!thuocPham(t, coCua(n))) continue;
    const f = fandomCua(n);
    if (!f || f === "Fanfic") continue;
    dem.set(f, (dem.get(f) ?? 0) + 1);
  }
  if (t.fandom !== "all" && !dem.has(t.fandom)) dem.set(t.fandom, 0);
  return [...dem.entries()]
    .map(([ten, so]) => ({ ten, so }))
    .sort((a, b) => b.so - a.so || soSanhViet.compare(a.ten, b.ten));
}

/* ------------------------------------------- loc TOAN KHO tren trinh duyet */

/** Chuoi de so khop tim kiem: chu thuong, BO DAU ("hoa anh" khop "Hỏa Ảnh"). */
export function chuanHoaTim(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

export interface CuaTruyen<T> {
  co: (n: T) => CoCo;
  fandom: (n: T) => string;
  /** Van ban de tim: ten + tac gia + mo ta. */
  chu: (n: T) => string;
  capNhat: (n: T) => string;
  taoLuc: (n: T) => string;
}

/**
 * DUONG NHANH: khi CA KHO nam trong mau (<= `TRAN_CUC_BO` truyen), loc + sap
 * ngay tren trinh duyet — cung quy tac voi backend (`thamSoDuyet`):
 * pham vi dinh dang/trang thai (`thuocPham`), fandom co cau truc, tim kiem
 * (khong phan biet dau), bon cach sap.
 *
 * VI SAO: do that tren production 2026-09-25, mot bo loc fandom mat hang chuc
 * giay (backend quet toan bo kho + dem audio tung truyen cho moi truy van),
 * trong khi danh sach mac dinh < 1s. Kho con nho thi khong co ly do bat nguoi
 * doc cho. Kho lon hon tran thi trang tu quay ve duong may chu.
 */
export function locToanKho<T extends CoTen>(ds: readonly T[], t: TrangThaiThuVien, cua: CuaTruyen<T>): T[] {
  const kim = chuanHoaTim(t.q);
  const loc = ds.filter((n) => {
    if (!thuocPham(t, cua.co(n))) return false;
    if (t.fandom !== "all" && cua.fandom(n) !== t.fandom) return false;
    if (kim && !chuanHoaTim(cua.chu(n)).includes(kim)) return false;
    return true;
  });
  if (t.sort === "updated" || t.sort === "latest") {
    const moc = t.sort === "updated" ? cua.capNhat : cua.taoLuc;
    // ISO 8601 cung dinh dang: so chuoi = so thoi gian. Moi -> cu.
    return [...loc].sort((a, b) => {
      const x = moc(a) || "";
      const y = moc(b) || "";
      return x < y ? 1 : x > y ? -1 : 0;
    });
  }
  return sapXepCucBo(loc, t.sort);
}

/** Mot trang cua ket qua da sap cuc bo (trang 1-based). */
export function catTrang<T>(ds: readonly T[], trang: number, kichThuocTrang: number): T[] {
  const bd = (Math.max(1, trang) - 1) * kichThuocTrang;
  return ds.slice(bd, bd + kichThuocTrang);
}
