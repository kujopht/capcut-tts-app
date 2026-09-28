/**
 * Caro (Gomoku) 15×15, NĂM HOẶC HƠN liên tiếp là thắng — cùng luật với máy chủ
 * (`server/games_domain.py`, `caro-v1`).
 *
 * Ở client, luật này CHỈ dùng cho chế độ "Luyện với máy" (không tính điểm, không
 * gửi gì lên máy chủ). Phòng hai người KHÔNG dùng hàm thắng/thua ở đây — máy chủ
 * là trọng tài duy nhất, client chỉ vẽ lại trạng thái máy chủ trả về.
 */

export const CO = 15;
export const SO_O = CO * CO;
export type Quan = "x" | "o";
export type O = Quan | ".";

export const banTrong = (): string => ".".repeat(SO_O);
export const hangCot = (i: number) => ({ hang: Math.floor(i / CO), cot: i % CO });
export const chiSo = (hang: number, cot: number) => hang * CO + cot;
export const doiLuot = (q: Quan): Quan => (q === "x" ? "o" : "x");

const HUONG: [number, number][] = [
  [0, 1],
  [1, 0],
  [1, 1],
  [1, -1],
];

/** Dãy liên tiếp của `q` đi qua ô `i` theo hướng (dh, dc) — gồm cả ô `i`. */
function day(ban: string, i: number, q: Quan, dh: number, dc: number): number[] {
  const { hang, cot } = hangCot(i);
  const out = [i];
  for (const s of [1, -1]) {
    let h = hang + dh * s;
    let c = cot + dc * s;
    while (h >= 0 && h < CO && c >= 0 && c < CO && ban[chiSo(h, c)] === q) {
      if (s === 1) out.push(chiSo(h, c));
      else out.unshift(chiSo(h, c));
      h += dh * s;
      c += dc * s;
    }
  }
  return out;
}

/** Đường thắng (≥ 5 ô) nếu nước vừa đi ở `i` tạo ra nó, ngược lại `null`. */
export function duongThang(ban: string, i: number): number[] | null {
  const q = ban[i];
  if (q !== "x" && q !== "o") return null;
  for (const [dh, dc] of HUONG) {
    const d = day(ban, i, q, dh, dc);
    if (d.length >= 5) return d;
  }
  return null;
}

export function datQuan(ban: string, i: number, q: Quan): string {
  if (i < 0 || i >= SO_O || ban[i] !== ".") throw new Error("Ô không hợp lệ.");
  return ban.slice(0, i) + q + ban.slice(i + 1);
}

export const hetCho = (ban: string) => !ban.includes(".");

/*
 * Bot luyện tập — heuristic đơn giản, KHÔNG giả làm người: giao diện luôn gọi nó
 * là "Máy (luyện tập)". Chấm điểm mỗi ô trống gần quân đã có theo độ dài dãy và
 * số đầu mở nếu đặt quân vào đó, cho cả tấn công lẫn phòng thủ.
 */
function diemHuong(ban: string, i: number, q: Quan, dh: number, dc: number): number {
  const { hang, cot } = hangCot(i);
  let dem = 1;
  let mo = 0;
  for (const s of [1, -1]) {
    let h = hang + dh * s;
    let c = cot + dc * s;
    while (h >= 0 && h < CO && c >= 0 && c < CO && ban[chiSo(h, c)] === q) {
      dem++;
      h += dh * s;
      c += dc * s;
    }
    if (h >= 0 && h < CO && c >= 0 && c < CO && ban[chiSo(h, c)] === ".") mo++;
  }
  if (dem >= 5) return 1_000_000;
  if (mo === 0) return 0;
  const bang: Record<number, [number, number]> = { 4: [5_000, 50_000], 3: [400, 4_000], 2: [30, 200], 1: [2, 10] };
  const [dong, thoang] = bang[dem] ?? [0, 0];
  return mo === 2 ? thoang : dong;
}

function diemO(ban: string, i: number, q: Quan): number {
  let s = 0;
  for (const [dh, dc] of HUONG) s += diemHuong(ban, i, q, dh, dc);
  return s;
}

function ganQuan(ban: string, i: number): boolean {
  const { hang, cot } = hangCot(i);
  for (let dh = -2; dh <= 2; dh++)
    for (let dc = -2; dc <= 2; dc++) {
      const h = hang + dh;
      const c = cot + dc;
      if ((dh || dc) && h >= 0 && h < CO && c >= 0 && c < CO && ban[chiSo(h, c)] !== ".") return true;
    }
  return false;
}

/** Nước đi của máy. `ngauNhien` cho phép tiêm hàm ngẫu nhiên trong bài kiểm. */
export function botChon(ban: string, q: Quan, ngauNhien: () => number = Math.random): number {
  if (!ban.includes("x") && !ban.includes("o")) return chiSo(7, 7);
  const dich = doiLuot(q);
  let tot = -1;
  let ung: number[] = [];
  for (let i = 0; i < SO_O; i++) {
    if (ban[i] !== "." || !ganQuan(ban, i)) continue;
    const d = diemO(ban, i, q) + diemO(ban, i, dich) * 0.9;
    if (d > tot) {
      tot = d;
      ung = [i];
    } else if (d === tot) ung.push(i);
  }
  if (!ung.length) return ban.indexOf(".");
  return ung[Math.floor(ngauNhien() * ung.length) % ung.length];
}
