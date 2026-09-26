/*
 * SOCIAL & PLAY V1 — goi C (frontend): luat Caro cho che do luyen tap, bot,
 * rune Memory, the game noi that, va cac bat bien "client khong phai trong tai".
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CO, SO_O, banTrong, botChon, chiSo, datQuan, duongThang, hetCho } from "../src/lib/caro.ts";
import { DO_KHO, KHOA_RUNE, RUNES, diemMemory, dongHoGiay, xepBaiLuyenTap } from "../src/lib/memoryRunes.ts";
import { GAMES, nhanCheDo, nhanXp } from "../src/lib/games.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const chiMa = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

function dat(ban, o) {
  let b = ban;
  for (const [h, c, q] of o) b = datQuan(b, chiSo(h, c), q);
  return b;
}

test("caro: ban 15x15, nam lien tiep ngang/doc/cheo deu thang, tra ve ca duong", () => {
  assert.equal(CO, 15);
  assert.equal(SO_O, 225);
  const ngang = dat(banTrong(), [0, 1, 2, 3, 4].map((c) => [7, c + 3, "x"]));
  assert.deepEqual(duongThang(ngang, chiSo(7, 5)), [3, 4, 5, 6, 7].map((c) => chiSo(7, c)));
  const doc = dat(banTrong(), [0, 1, 2, 3, 4].map((h) => [h, 0, "o"]));
  assert.equal(duongThang(doc, chiSo(4, 0)).length, 5);
  const cheo = dat(banTrong(), [0, 1, 2, 3, 4].map((k) => [k + 2, k + 2, "x"]));
  assert.ok(duongThang(cheo, chiSo(4, 4)));
  const cheoNguoc = dat(banTrong(), [0, 1, 2, 3, 4].map((k) => [k, 10 - k, "o"]));
  assert.ok(duongThang(cheoNguoc, chiSo(2, 8)));
});

test("caro: sau quan (overline) van thang; bon quan va bi chan giua thi khong", () => {
  const sau = dat(banTrong(), [0, 1, 2, 3, 4, 5].map((c) => [1, c, "x"]));
  assert.equal(duongThang(sau, chiSo(1, 2)).length, 6);
  const bon = dat(banTrong(), [0, 1, 2, 3].map((c) => [1, c, "x"]));
  assert.equal(duongThang(bon, chiSo(1, 3)), null);
  const chan = dat(banTrong(), [[1, 0, "x"], [1, 1, "x"], [1, 2, "o"], [1, 3, "x"], [1, 4, "x"], [1, 5, "x"]]);
  assert.equal(duongThang(chan, chiSo(1, 5)), null);
  // Khong noi vong qua mep ban (cot 14 -> cot 0 hang sau).
  const mep = dat(banTrong(), [[0, 12, "x"], [0, 13, "x"], [0, 14, "x"], [1, 0, "x"], [1, 1, "x"]]);
  assert.equal(duongThang(mep, chiSo(1, 1)), null);
});

test("caro: o da co quan hoac ngoai ban bi tu choi; het cho = hoa", () => {
  const b = datQuan(banTrong(), 0, "x");
  assert.throws(() => datQuan(b, 0, "o"));
  assert.throws(() => datQuan(b, 225, "o"));
  assert.throws(() => datQuan(b, -1, "o"));
  assert.equal(hetCho(banTrong()), false);
  assert.equal(hetCho("x".repeat(225)), true);
});

test("bot luyen tap: di giua khi ban trong, chan nuoc bon cua doi thu, tu thang khi co the", () => {
  assert.equal(botChon(banTrong(), "o"), chiSo(7, 7));
  // X co 4 quan thoang o hang 5 (cot 3..6) -> O phai chan o cot 2 hoac 7.
  const doa = dat(banTrong(), [3, 4, 5, 6].map((c) => [5, c, "x"]).concat([[9, 9, "o"], [10, 10, "o"], [11, 12, "o"]]));
  const chanO = botChon(doa, "o", () => 0);
  assert.ok([chiSo(5, 2), chiSo(5, 7)].includes(chanO), `bot đi ${chanO}`);
  // O co 4 quan -> O di nuoc thang thay vi chan.
  const thang = dat(banTrong(), [3, 4, 5, 6].map((c) => [5, c, "x"]).concat([0, 1, 2, 3].map((c) => [9, c, "o"])));
  const nuoc = botChon(thang, "o", () => 0);
  assert.ok(duongThang(datQuan(thang, nuoc, "o"), nuoc), "bot phải đi nước thắng");
});

test("memory runes: 12 rune co ten, do kho dung kich thuoc, bo luyen tap du cap", () => {
  assert.equal(KHOA_RUNE.length, 12);
  for (const k of KHOA_RUNE) assert.ok(RUNES[k].ten.length > 0, k);
  for (const [k, d] of Object.entries(DO_KHO)) {
    assert.equal(d.rows * d.cols, d.pairs * 2, k);
    const bai = xepBaiLuyenTap(k);
    assert.equal(bai.length, d.pairs * 2);
    const dem = {};
    for (const x of bai) dem[x] = (dem[x] ?? 0) + 1;
    assert.ok(Object.values(dem).every((n) => n === 2), k);
  }
  // Cong thuc diem giong may chu, khong am.
  assert.equal(diemMemory(8, 8, 30), 770);
  assert.equal(diemMemory(8, 40, 900), 0);
  assert.equal(dongHoGiay(125.7), "2:05");
});

test("the game: Memory + Caro co trang rieng, XP noi theo cau hinh song cua may chu", () => {
  const mr = GAMES.find((g) => g.id === "memory-runes");
  const caro = GAMES.find((g) => g.id === "caro");
  assert.equal(mr.href, "/entertainment/memory");
  assert.equal(caro.href, "/entertainment/caro");
  assert.equal(nhanCheDo(caro.cheDo), "Với máy · Phòng 2 người");
  assert.equal(nhanXp(mr, false), "Không tính XP (máy chủ chưa bật)");
  assert.equal(nhanXp(mr, true), mr.xp);
  assert.equal(nhanXp(GAMES.find((g) => g.iframe), true), "Không tính XP");
  const hub = read("../src/app/entertainment/page.tsx");
  assert.match(hub, /<dd>\{nhanXp\(g, mayChuBat\)\}<\/dd>/);
  assert.match(hub, /gamesApi\.config\(\)\.then\(\(c\) => setMayChuBat\(!!c\.enabled\)\)\.catch\(\(\) => setMayChuBat\(false\)\)/);
});

test("client KHONG phai trong tai: khong gui diem/XP/nguoi thang len may chu", () => {
  const api = read("../src/lib/api.ts");
  const khoi = api.slice(api.indexOf("export const games = {"));
  const tatCaBody = [...khoi.matchAll(/post\(\{([^}]*)\}\)/g)].map((m) => m[1]).join(" ");
  for (const cam of ["score", "xp", "winner", "points", "result", "board"]) {
    assert.ok(!new RegExp(`\\b${cam}\\b`).test(tatCaBody), `không được gửi "${cam}"`);
  }
  // Phong 2 nguoi chi gui (o, move_no); thang/thua doc tu may chu.
  const caro = chiMa(read("../src/app/entertainment/caro/page.tsx"));
  assert.match(caro, /games\.move\(room\.code, i, room\.move_no\)/);
  const phong = caro.slice(caro.indexOf("function PhongHaiNguoi"));
  assert.ok(!/duongThang\(|hetCho\(|botChon\(/.test(phong), "phòng 2 người không tự tính thắng/thua");
  // Doi thu may luon ghi ro la may.
  assert.match(caro, /Đối thủ: Máy \(luyện tập\)/);
  // Memory tinh diem: khong co bo cuc o client.
  const mem = chiMa(read("../src/app/entertainment/memory/page.tsx"));
  const diem = mem.slice(mem.indexOf("const batDauTinhDiem"));
  assert.ok(!/xepBaiLuyenTap/.test(diem), "chế độ tính điểm không tự xếp bài");
});

test("vao game thi tam dung loi doc; the/o co nhan doc duoc (khong chi mau)", () => {
  for (const f of ["../src/app/entertainment/memory/page.tsx", "../src/app/entertainment/caro/page.tsx"]) {
    assert.match(read(f), /if \(engine\?\.trangThai\.dangPhat\) engine\.dieuKhien\.tamDung\(\);/, f);
  }
  assert.match(read("../src/components/games/CaroBoard.tsx"), /aria-label=\{`Hàng \$\{hang \+ 1\}, cột \$\{cot \+ 1\}: \$\{TEN\[q\]\}/);
  const mb = read("../src/components/games/MemoryBoard.tsx");
  assert.match(mb, /<span className="mr-ten">\{r\.ten\}<\/span>/);
});

test("ban caro: 15 hang deu nhau, hang co quan khong cao hon hang trong", () => {
  const css = read("../src/app/globals.css");
  const dau = css.indexOf(".caro-ban {");
  const ban = css.slice(dau, css.indexOf("}", dau));
  assert.match(ban, /grid-template-columns: repeat\(15, minmax\(0, 1fr\)\);/);
  assert.match(ban, /grid-template-rows: repeat\(15, minmax\(0, 1fr\)\);/, "hang ngam auto lam hang co quan cao gap doi");
  const dauO = css.indexOf(".caro-o {");
  assert.match(css.slice(dauO, css.indexOf("}", dauO)), /min-height: 0;/);
});
