/**
 * Dang song cua mot tep audio — tinh o TRINH DUYET.
 *
 * §9 noi ro: KHONG chay mot job backend chi de ve mot dang song. Day la mot
 * phep doc tep da nam san trong may nguoi dung; day no len may chu roi cho
 * mot hang doi tra ve mot mang so la bien mot viec 200ms thanh mot viec
 * nhieu giay VA mot dong tien.
 *
 * Ket qua duoc GHI NHO theo URL trong mot phien: keo mot clip qua lai se ve
 * lai lien tuc, va giai ma lai mot tep MP3 moi lan ve la cach de dot CPU
 * cua may khach ma khong ai nhan ra ngay.
 */

const NHO = new Map<string, number[]>();
const DANG_CHAY = new Map<string, Promise<number[]>>();

/** So cot cua dang song. Du de nhin ra nhip, du it de ve lai that nhanh. */
export const SO_COT = 240;

type CtorAudioContext = new () => AudioContext;

function layCtor(): CtorAudioContext | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    AudioContext?: CtorAudioContext;
    webkitAudioContext?: CtorAudioContext;
  };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

/**
 * `SO_COT` dinh cao 0..1.
 *
 * Tra mang RONG khi khong doc duoc — va do la mot gia tri hop le, khong phai
 * loi. Mot tep audio khong giai ma duoc (dinh dang la, CORS, trinh duyet cu)
 * KHONG duoc lam hong ca trinh soan thao; clip van keo duoc, chi la ve tron
 * thay vi ve song.
 */
export async function dinhCao(url: string): Promise<number[]> {
  if (!url) return [];
  const nho = NHO.get(url);
  if (nho) return nho;
  const dang = DANG_CHAY.get(url);
  if (dang) return dang;

  const viec = (async () => {
    try {
      const Ctor = layCtor();
      if (!Ctor) return [];
      const res = await fetch(url);
      if (!res.ok) return [];
      const buf = await res.arrayBuffer();
      const ctx = new Ctor();
      try {
        const am = await ctx.decodeAudioData(buf);
        const ra = rutGon(am);
        NHO.set(url, ra);
        return ra;
      } finally {
        // Moi `AudioContext` giu mot thiet bi audio that. Khong dong lai thi
        // Chrome dung o tran ~6 context roi tu choi tao them — luc do dang
        // song thu bay im lang ngung hoat dong.
        void ctx.close().catch(() => undefined);
      }
    } catch {
      return [];
    } finally {
      DANG_CHAY.delete(url);
    }
  })();

  DANG_CHAY.set(url, viec);
  return viec;
}

/**
 * Gop mau thanh `SO_COT` dinh.
 *
 * Dung RMS chu khong phai dinh tuyet doi: dinh tuyet doi lam moi doan noi
 * deu cham tran va dang song bien thanh mot khoi chu nhat dac. RMS giu duoc
 * nhip manh/nhe — thu duy nhat khien dang song co ich khi canh loi doc.
 */
function rutGon(am: AudioBuffer): number[] {
  const n = am.numberOfChannels;
  const dai = am.length;
  if (!dai) return [];
  const moiCot = Math.max(1, Math.floor(dai / SO_COT));
  const ra: number[] = [];
  let dinh = 0;

  for (let c = 0; c < SO_COT; c += 1) {
    const tu = c * moiCot;
    if (tu >= dai) break;
    const den = Math.min(dai, tu + moiCot);
    let tong = 0;
    let dem = 0;
    for (let k = 0; k < n; k += 1) {
      const du = am.getChannelData(k);
      // Lay mau THUA ra — doc tung mau cua mot tep 10 phut la vai chuc trieu
      // phep tinh, va mat khong nhin ra khac biet o 240 cot.
      for (let i = tu; i < den; i += 8) {
        tong += du[i] * du[i];
        dem += 1;
      }
    }
    const rms = dem ? Math.sqrt(tong / dem) : 0;
    ra.push(rms);
    if (rms > dinh) dinh = rms;
  }

  if (dinh <= 0) return ra.map(() => 0);
  return ra.map((v) => Math.min(1, v / dinh));
}

/** Duong `<path>` cho dang song, ve doi xung quanh truc giua. */
export function duongSvg(dinh: number[], rong: number, cao: number): string {
  if (dinh.length === 0) return "";
  const giua = cao / 2;
  const buoc = rong / dinh.length;
  const tren: string[] = [];
  const duoi: string[] = [];
  dinh.forEach((v, i) => {
    const x = i * buoc;
    const h = Math.max(0.5, v * giua);
    tren.push(`${x.toFixed(2)},${(giua - h).toFixed(2)}`);
    duoi.push(`${x.toFixed(2)},${(giua + h).toFixed(2)}`);
  });
  return `M${tren.join(" L")} L${duoi.reverse().join(" L")} Z`;
}
