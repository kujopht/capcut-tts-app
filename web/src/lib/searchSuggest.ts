/**
 * GOI Y TIM KIEM TUC THI (o tim o header) tu anh chup kho truyen.
 *
 * Backend (`GET /api/novels?q=`) chi so TEN va MO TA, va do that tren
 * production moi truy van ton vai giay. Nen trong luc cho, o tim goi y ngay
 * tu anh chup (`lib/catalogSnapshot.ts`, <= 50 truyen):
 *   - FANDOM khop (go "nar" -> "Naruto", 4 truyen) -> mo Thu vien loc fandom;
 *   - TAC GIA khop (go "corty" -> "Corty") — backend KHONG tim theo tac gia;
 *   - TEN truyen khop, khong phan biet dau ("hoa anh" -> "Hỏa Ảnh").
 * Ket qua DAY DU van la cua backend; day chi la loi tat.
 *
 * Tep thuan, KHONG import luc chay (bai kiem Node nap thang tep .ts): ham chuan
 * hoa chu (`chuanHoaTim` cua `libraryQuery.ts`) va ham doc fandom deu duoc
 * TRUYEN VAO — `tests/search-suggest.test.mjs`.
 */

export interface TruyenGoiY {
  novel_id: string;
  title: string;
  external_author_name?: string;
}

export interface KetQuaGoiY<T extends TruyenGoiY> {
  fandom: { ten: string; so: number }[];
  tacGia: { ten: string; so: number }[];
  truyen: T[];
}

/** Tu khoa phai co it nhat chung nay ky tu (sau khi bo dau) moi goi y. */
export const TOI_THIEU_KY_TU = 2;

function khop(chuoi: string, kim: string, chuanHoa: (s: string) => string): boolean {
  if (!chuoi) return false;
  const c = chuanHoa(chuoi);
  // Khop dau mot tu ("nar" khop "Naruto", "piece" khop "One Piece") —
  // khop giua tu ("aru") gay nhieu hon co ich.
  return c.startsWith(kim) || c.includes(` ${kim}`) || c.includes(`[${kim}`);
}

function tacGiaThat(raw?: string): string | null {
  const s = (raw ?? "").trim();
  if (!s || /^(unknown|unknown author|anonymous|n\/a)$/i.test(s)) return null;
  return s;
}

export function goiYTimKiem<T extends TruyenGoiY>(
  tu: string,
  ds: readonly T[],
  cach: {
    fandomCua: (n: T) => string;
    chuanHoa: (s: string) => string;
    /**
     * Truyen nao duoc DEM cho goi y fandom. Bam goi y mo Thu vien o pham vi
     * mac dinh (kho doc duoc), nen so dem phai la so truyen trang do se hien —
     * khong thi "Naruto · 8 truyện" dan toi mot trang co 4.
     */
    demFandom?: (n: T) => boolean;
  },
  toiDa = { fandom: 3, tacGia: 3, truyen: 5 },
): KetQuaGoiY<T> {
  const { fandomCua, chuanHoa, demFandom } = cach;
  const kim = chuanHoa(tu);
  if (kim.length < TOI_THIEU_KY_TU) return { fandom: [], tacGia: [], truyen: [] };

  const demFandomMap = new Map<string, number>();
  const demTacGia = new Map<string, number>();
  const truyen: T[] = [];
  for (const n of ds) {
    const f = fandomCua(n);
    if (f && khop(f, kim, chuanHoa) && (!demFandom || demFandom(n))) {
      demFandomMap.set(f, (demFandomMap.get(f) ?? 0) + 1);
    }
    const tg = tacGiaThat(n.external_author_name);
    const khopTacGia = !!tg && khop(tg, kim, chuanHoa);
    if (tg && khopTacGia) demTacGia.set(tg, (demTacGia.get(tg) ?? 0) + 1);
    if (khop(n.title, kim, chuanHoa) || khopTacGia) truyen.push(n);
  }
  const xep = (m: Map<string, number>, max: number) =>
    [...m.entries()]
      .map(([ten, so]) => ({ ten, so }))
      .sort((a, b) => b.so - a.so || a.ten.localeCompare(b.ten, "vi"))
      .slice(0, max);
  return {
    fandom: xep(demFandomMap, toiDa.fandom),
    tacGia: xep(demTacGia, toiDa.tacGia),
    truyen: truyen.slice(0, toiDa.truyen),
  };
}

/**
 * Bo khoi `ds` nhung truyen DA hien o nhom khac (vd nhom "Audio" lap lai y
 * nguyen nhom "Truyện" khi xem "Tất cả" — nam dong trung nhau vo ich).
 */
export function boTrungTheoId<T extends { novel_id: string }>(ds: readonly T[], daCo: readonly { novel_id: string }[]): T[] {
  const co = new Set(daCo.map((n) => n.novel_id));
  const ra: T[] = [];
  for (const n of ds) if (!co.has(n.novel_id)) ra.push(n);
  return ra;
}

/**
 * Gop ket qua truyen cua backend voi goi y tai cho: backend TRUOC (no la ket
 * qua day du), roi them truyen chi tai cho moi thay (vd khop theo tac gia).
 */
export function gopTruyen<T extends { novel_id: string }>(mayChu: readonly T[], taiCho: readonly T[], toiDa: number): T[] {
  const co = new Set(mayChu.map((n) => n.novel_id));
  const ra = [...mayChu];
  for (const n of taiCho) {
    if (ra.length >= toiDa) break;
    if (!co.has(n.novel_id)) {
      co.add(n.novel_id);
      ra.push(n);
    }
  }
  return ra.slice(0, Math.max(toiDa, mayChu.length));
}
