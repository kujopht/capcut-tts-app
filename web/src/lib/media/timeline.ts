/**
 * Mo hinh DUONG THOI GIAN — thuan TypeScript, KHONG cham DOM.
 *
 * Vi sao tach ra khoi component: keo mot clip la mot phep TOAN (giay <-> pixel,
 * chan bien, hut diem moc), con ve mot clip la mot phep DOM. Tron hai thu vao
 * mot `onMouseMove` la cach chac chan nhat de khong bao gio kiem duoc phep
 * toan do — va phep toan moi la cho sai. Moi ham o day kiem duoc bang mot bai
 * test khong can trinh duyet.
 *
 * MOT CLIP AUDIO, MOT CLIP VIDEO — co y, khong phai thieu sot. Backend
 * (`VideoProject`) giu dung mot `audio_track_id` + mot `video_asset_id`. Cho
 * nguoi dung tha ba clip audio len duong thoi gian roi chi luu duoc mot la
 * mat du lieu im lang, va do la loai loi te nhat: nguoi dung KHONG thay no
 * xay ra. Phu de thi khac — no la mot tep SRT, nen nhieu phan doan la tu
 * nhien va luu duoc het.
 */

import type { SubtitleSegment } from "@/lib/subtitles/model";

/** Clip audio tren duong thoi gian. */
export interface ClipAudio {
  /** `AudioTrack.track_id` hoac `MediaAsset.asset_id`. */
  nguonId: string;
  /** Nhan NGUOI DOC duoc — khong bao gio hien `trk_9f2a…` len man hinh. */
  nhan: string;
  /** Giay tren duong thoi gian noi clip bat dau. Am = cat bot dau nguon. */
  batDau: number;
  /** Cat bot tu CUOI nguon (giay). 0 = dung het. */
  catCuoi: number;
  /** Do dai GOC cua nguon (giay). */
  goc: number;
  /** 0..2 */
  amLuong: number;
  tat: boolean;
}

/** Clip video tren duong thoi gian. */
export interface ClipVideo {
  assetId: string;
  nhan: string;
  catDau: number;
  catCuoi: number;
  goc: number;
  amLuong: number;
  tatTiengGoc: boolean;
}

export type LoaiChon = "video" | "audio" | "phu_de";

export interface DangChon {
  loai: LoaiChon;
  /** Chi dung cho phu de — id phan doan. */
  id?: string;
}

/* ============================================================ do dai ===== */

/** Do dai HIEN THI cua clip audio sau khi cat. */
export function daiAudio(c: ClipAudio): number {
  const catDau = c.batDau < 0 ? -c.batDau : 0;
  const cuoi = c.catCuoi > 0 ? Math.min(c.catCuoi, c.goc) : c.goc;
  return Math.max(0, cuoi - catDau);
}

/** Clip audio ket thuc o giay nao tren duong thoi gian. */
export function ketThucAudio(c: ClipAudio): number {
  return Math.max(0, c.batDau) + daiAudio(c);
}

export function daiVideo(c: ClipVideo): number {
  const cuoi = c.catCuoi > 0 ? Math.min(c.catCuoi, c.goc) : c.goc;
  return Math.max(0, cuoi - c.catDau);
}

/**
 * Tong do dai duong thoi gian.
 *
 * Lay MAX cua ba lan chu khong phai do dai video: nguoi dung co the day loi
 * doc vuot qua doan video, va neu thuoc do tu cat o cuoi video thi phan
 * audio thua tro nen VO HINH — khong keo nguoc lai duoc vi khong con cho de
 * bam vao.
 */
export function tongDai(
  video: ClipVideo | null, audio: ClipAudio | null, subs: SubtitleSegment[],
): number {
  const a = video ? daiVideo(video) : 0;
  const b = audio ? ketThucAudio(audio) : 0;
  const c = subs.reduce((m, s) => Math.max(m, s.end), 0);
  return Math.max(a, b, c, 1);
}

/* ====================================================== giay <-> pixel === */

/** Bao nhieu pixel cho mot giay, theo muc phong. */
export function pxMoiGiay(phong: number): number {
  return 40 * phong;
}

export function giayThanhPx(giay: number, phong: number): number {
  return giay * pxMoiGiay(phong);
}

export function pxThanhGiay(px: number, phong: number): number {
  return px / pxMoiGiay(phong);
}

/* ============================================================== keo ====== */

/** Cac diem MOC de hut vao khi keo. */
export function diemMoc(
  video: ClipVideo | null, audio: ClipAudio | null, subs: SubtitleSegment[],
  boQua?: string,
): number[] {
  const ds = [0];
  if (video) ds.push(daiVideo(video));
  if (audio) ds.push(Math.max(0, audio.batDau), ketThucAudio(audio));
  for (const s of subs) {
    if (s.id === boQua) continue;
    ds.push(s.start, s.end);
  }
  return ds;
}

/**
 * Hut ve diem moc gan nhat neu du gan.
 *
 * `nguong` tinh bang GIAY chu khong phai pixel, va nguoi goi quy doi tu pixel
 * theo muc phong hien tai — nho vay hut van "cam giac" giong nhau o moi muc
 * phong, thay vi hut manh dan khi phong to.
 */
export function hut(giay: number, moc: number[], nguong: number): number {
  let tot = giay;
  let gan = nguong;
  for (const m of moc) {
    const d = Math.abs(m - giay);
    if (d < gan) {
      gan = d;
      tot = m;
    }
  }
  return tot;
}

export function chan(giay: number, thap: number, cao: number): number {
  return Math.min(cao, Math.max(thap, giay));
}

/* ======================================================= phu de tren lane */

/**
 * Doi mot phan doan phu de, GIU NGUYEN do dai.
 *
 * Khong cho lui qua 0: mot phan doan bat dau o giay am se bien mat khoi
 * duong thoi gian va khong bam lai duoc.
 */
export function doiPhanDoan(s: SubtitleSegment, batDauMoi: number): SubtitleSegment {
  const dai = s.end - s.start;
  const start = Math.max(0, batDauMoi);
  return { ...s, start, end: start + dai };
}

/** Keo MEP cua mot phan doan. Khong cho ngan hon `TOI_THIEU`. */
export const TOI_THIEU = 0.2;

export function keoMep(
  s: SubtitleSegment, mep: "start" | "end", giay: number,
): SubtitleSegment {
  if (mep === "start") {
    return { ...s, start: chan(giay, 0, s.end - TOI_THIEU) };
  }
  return { ...s, end: Math.max(s.start + TOI_THIEU, giay) };
}

/** Phan doan dang hien o giay nay (phan doan DAU tien khop). */
export function phanDoanTai(
  subs: SubtitleSegment[], giay: number,
): SubtitleSegment | null {
  return subs.find((s) => giay >= s.start && giay < s.end) ?? null;
}

/* ====================================================== dong bo phat lai */

/**
 * Thoi diem trong TEP AUDIO ung voi mot giay tren duong thoi gian.
 *
 * `null` = tai giay do clip chua bat dau hoac da het, tuc la khong nen phat.
 * Tra `null` thay vi mot so am de cho goi khong the "vo tinh" seek ra ngoai
 * tep roi im lang phat sai cho.
 */
export function giayTrongNguon(c: ClipAudio, giayTL: number): number | null {
  const batDau = Math.max(0, c.batDau);
  const catDau = c.batDau < 0 ? -c.batDau : 0;
  if (giayTL < batDau) return null;
  const trong = giayTL - batDau + catDau;
  const cuoi = c.catCuoi > 0 ? Math.min(c.catCuoi, c.goc) : c.goc;
  if (trong >= cuoi) return null;
  return trong;
}

/** Thoi diem trong TEP VIDEO ung voi mot giay tren duong thoi gian. */
export function giayTrongVideo(c: ClipVideo, giayTL: number): number | null {
  const trong = giayTL + c.catDau;
  const cuoi = c.catCuoi > 0 ? Math.min(c.catCuoi, c.goc) : c.goc;
  if (trong >= cuoi) return null;
  return trong;
}

/* ============================================================ moc gio ==== */

/** Buoc chia cua thuoc do, chon sao cho vach khong dinh vao nhau. */
export function buocThuocDo(phong: number): number {
  const px = pxMoiGiay(phong);
  for (const b of [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]) {
    if (b * px >= 64) return b;
  }
  return 600;
}

/** `75.5` -> `"1:15"`. Duoi mot gio thi KHONG hien phan gio. */
export function nhanGio(giay: number): string {
  const g = Math.max(0, Math.floor(giay));
  const gio = Math.floor(g / 3600);
  const phut = Math.floor((g % 3600) / 60);
  const s = g % 60;
  const p2 = (n: number) => String(n).padStart(2, "0");
  return gio > 0 ? `${gio}:${p2(phut)}:${p2(s)}` : `${phut}:${p2(s)}`;
}

/** Nhu `nhanGio` nhung kem phan tram giay — cho o dong ho dang phat. */
export function nhanGioLe(giay: number): string {
  const le = Math.floor((Math.max(0, giay) % 1) * 10);
  return `${nhanGio(giay)}.${le}`;
}
