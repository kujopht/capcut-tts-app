/**
 * Mo hinh du lieu phu de + SRT/VTT — thuan TypeScript, KHONG dung DOM.
 *
 * BAN QUYEN: module nay la code CUA FANFIC, viet doc lap. Khong sao chep/
 * vendor/dich code tu bat ky du an tham khao nao (vi du subvid.app, giay
 * phep PolyForm Noncommercial — chi dung lam THAM KHAO HANH VI SAN PHAM,
 * khong dung lam nguon code).
 */

export interface SubtitleSegment {
  id: string;
  /** Giay, co the co phan thap phan. */
  start: number;
  end: number;
  text: string;
}

let demTamThoi = 0;

/** Id tam thoi, DUY NHAT trong phien lam viec — khong can ben vung/UUID
    that, chi can khac nhau de React `key` va thao tac splice/merge dung. */
export function idPhanDoanMoi(): string {
  demTamThoi += 1;
  return `seg_${demTamThoi}_${Math.random().toString(36).slice(2, 8)}`;
}

export function taoPhanDoan(start: number, end: number, text = ""): SubtitleSegment {
  return { id: idPhanDoanMoi(), start, end, text };
}

/** Sap xep theo `start` — moi thao tac tra ve danh sach da sap, tranh phu
    de hien thi lon xon sau khi tach/gop/sua gio. */
export function sapXep(segments: SubtitleSegment[]): SubtitleSegment[] {
  return [...segments].sort((a, b) => a.start - b.start);
}

/**
 * Tach MOT phan doan tai `taiGiay` thanh HAI — chi hop le khi diem tach nam
 * NGHIEM NGAT giua start/end (khong tach duoc o mep, se tao doan rong).
 * Van ban duoc GIU NGUYEN o phan doan dau, phan doan sau de trong — nguoi
 * dung go lai (khong the tu doan cau bi cat o dau).
 */
export function tachPhanDoan(
  segments: SubtitleSegment[], id: string, taiGiay: number,
): SubtitleSegment[] {
  const idx = segments.findIndex((s) => s.id === id);
  if (idx === -1) return segments;
  const goc = segments[idx];
  if (taiGiay <= goc.start || taiGiay >= goc.end) return segments;

  const truoc: SubtitleSegment = { ...goc, end: taiGiay };
  const sau: SubtitleSegment = taoPhanDoan(taiGiay, goc.end, "");
  const ra = [...segments];
  ra.splice(idx, 1, truoc, sau);
  return ra;
}

/** Gop mot phan doan VOI PHAN DOAN NGAY SAU NO (theo thu tu mang, khong
    phai theo thoi gian — goi sau `sapXep` neu can dung thu tu thoi gian).
    Van ban noi bang mot dau cach. */
export function gopVoiPhanDoanSau(
  segments: SubtitleSegment[], id: string,
): SubtitleSegment[] {
  const idx = segments.findIndex((s) => s.id === id);
  if (idx === -1 || idx === segments.length - 1) return segments;
  const a = segments[idx];
  const b = segments[idx + 1];
  const gop: SubtitleSegment = {
    id: a.id, start: a.start, end: b.end,
    text: [a.text.trim(), b.text.trim()].filter(Boolean).join(" "),
  };
  const ra = [...segments];
  ra.splice(idx, 2, gop);
  return ra;
}

export function xoaPhanDoan(
  segments: SubtitleSegment[], id: string,
): SubtitleSegment[] {
  return segments.filter((s) => s.id !== id);
}

export function suaVanBan(
  segments: SubtitleSegment[], id: string, text: string,
): SubtitleSegment[] {
  return segments.map((s) => (s.id === id ? { ...s, text } : s));
}

export function suaThoiGian(
  segments: SubtitleSegment[], id: string,
  truong: "start" | "end", giay: number,
): SubtitleSegment[] {
  return segments.map((s) => (s.id === id ? { ...s, [truong]: giay } : s));
}

/* ==================================================== dinh dang thoi gian */

/** `12.345` -> `"00:00:12,345"` (SRT — dau phay). */
export function giayThanhSrt(giay: number): string {
  return giayThanhMa(giay, ",");
}

/** `12.345` -> `"00:00:12.345"` (VTT — dau cham). */
export function giayThanhVtt(giay: number): string {
  return giayThanhMa(giay, ".");
}

function giayThanhMa(giayGoc: number, phanCach: "," | "."): string {
  const giay = Math.max(0, giayGoc);
  const gio = Math.floor(giay / 3600);
  const phut = Math.floor((giay % 3600) / 60);
  const conLaiGiay = Math.floor(giay % 60);
  const ms = Math.round((giay - Math.floor(giay)) * 1000);
  const p2 = (n: number) => String(n).padStart(2, "0");
  const p3 = (n: number) => String(n).padStart(3, "0");
  return `${p2(gio)}:${p2(phut)}:${p2(conLaiGiay)}${phanCach}${p3(ms)}`;
}

/* ============================================================== SRT/VTT */

export function xuatSrt(segments: SubtitleSegment[]): string {
  const daSap = sapXep(segments).filter((s) => s.text.trim());
  return daSap
    .map((s, i) =>
      `${i + 1}\n${giayThanhSrt(s.start)} --> ${giayThanhSrt(s.end)}\n${s.text.trim()}\n`)
    .join("\n");
}

export function xuatVtt(segments: SubtitleSegment[]): string {
  const daSap = sapXep(segments).filter((s) => s.text.trim());
  const than = daSap
    .map((s) => `${giayThanhVtt(s.start)} --> ${giayThanhVtt(s.end)}\n${s.text.trim()}\n`)
    .join("\n");
  return `WEBVTT\n\n${than}`;
}

/** Doc CA hai dinh dang gio-phut-giay-mili (dau phay HOAC dau cham). */
function maThanhGiay(ma: string): number {
  const m = ma.trim().match(/(\d+):(\d{2}):(\d{2})[.,](\d{1,3})/);
  if (!m) return 0;
  const [, gio, phut, giay, ms] = m;
  return (
    Number(gio) * 3600 + Number(phut) * 60 + Number(giay) +
    Number(ms.padEnd(3, "0")) / 1000
  );
}

/**
 * Nhap MOT tep SRT hoac VTT co san — day la duong vao CHINH cua Subtitle
 * Studio (Phan 4A/4D): thay vi bat buoc phai co phien nhan dien giong noi
 * (chua lam trong dot nay, xem `NANG_CAP.md`/bao cao overnight), nguoi dung
 * co the sua/dich mot phu de DA CO san.
 */
export function nhapSrtHoacVtt(noiDung: string): SubtitleSegment[] {
  const sach = noiDung.replace(/\r\n/g, "\n").trim();
  if (!sach) return [];

  const khoi = sach
    .replace(/^WEBVTT.*\n+/i, "")
    .split(/\n\s*\n/)
    .map((k) => k.trim())
    .filter(Boolean);

  const ra: SubtitleSegment[] = [];
  for (const k of khoi) {
    const dong = k.split("\n");
    // SRT co dong so thu tu o dau (thuan so) — VTT thi khong. Bo qua neu co.
    const batDauODong0 = /-->/.test(dong[0]);
    const dongMoc = batDauODong0 ? dong[0] : dong[1];
    if (!dongMoc || !dongMoc.includes("-->")) continue;
    const [moc1, moc2] = dongMoc.split("-->");
    const text = dong.slice(batDauODong0 ? 1 : 2).join("\n").trim();
    ra.push(taoPhanDoan(maThanhGiay(moc1), maThanhGiay(moc2), text));
  }
  return sapXep(ra);
}
