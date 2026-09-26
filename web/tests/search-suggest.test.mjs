/*
 * PRODUCT UX SPRINT 2 — goi y tim kiem tuc thi (o tim o header).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { boTrungTheoId, goiYTimKiem, gopTruyen, TOI_THIEU_KY_TU } from "../src/lib/searchSuggest.ts";
import { chuanHoaTim } from "../src/lib/libraryQuery.ts";
import { fandomCauTruc } from "../src/lib/taxonomy.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

const KHO = [
  { novel_id: "a", title: "[Naruto] Hỏa Ảnh: Hiệu Ứng Cánh Bướm", external_author_name: "Corty", tags: ["fandom:Naruto"], fandom_ids: ["fan_naruto"], cu: false },
  { novel_id: "b", title: "The Cold Between Wars (Naruto)", external_author_name: "Unknown Author", tags: [], fandom_ids: ["naruto"], cu: false },
  { novel_id: "c", title: "[One Piece] Kỷ Nguyên Rocks", external_author_name: "Bạch Dạ Phong Vân", tags: ["one piece"], fandom_ids: ["fan_onepiece"], cu: false },
  { novel_id: "d", title: "Naruto Fanfic Xuyên Thành", external_author_name: "", tags: ["fandom:Naruto", "long_form_audio"], fandom_ids: [], cu: true },
];
const CACH = { fandomCua: fandomCauTruc, chuanHoa: chuanHoaTim, demFandom: (n) => !n.cu };

test("fandom khop dau tu, dem = so truyen Thu vien SE HIEN (kho doc duoc)", () => {
  const g = goiYTimKiem("nar", KHO, CACH);
  assert.deepEqual(g.fandom, [{ ten: "Naruto", so: 2 }]);
  // Ten truyen khop (ca truyen audio cu — van mo duoc trang truyen).
  assert.deepEqual(g.truyen.map((n) => n.novel_id), ["a", "d"]);
  assert.deepEqual(goiYTimKiem("piece", KHO, CACH).fandom, [{ ten: "One Piece", so: 1 }]);
});

test("tac gia: khop ten tac gia (backend khong tim theo tac gia), bo 'Unknown Author'", () => {
  const g = goiYTimKiem("corty", KHO, CACH);
  assert.deepEqual(g.tacGia, [{ ten: "Corty", so: 1 }]);
  assert.deepEqual(g.truyen.map((n) => n.novel_id), ["a"]);
  assert.deepEqual(goiYTimKiem("unknown", KHO, CACH).tacGia, []);
  assert.deepEqual(goiYTimKiem("bach da", KHO, CACH).tacGia, [{ ten: "Bạch Dạ Phong Vân", so: 1 }]);
});

test("khong phan biet dau; qua ngan thi khong goi y; khop giua tu khong tinh", () => {
  assert.deepEqual(goiYTimKiem("hoa anh", KHO, CACH).truyen.map((n) => n.novel_id), ["a"]);
  assert.equal(TOI_THIEU_KY_TU, 2);
  assert.deepEqual(goiYTimKiem("n", KHO, CACH), { fandom: [], tacGia: [], truyen: [] });
  assert.deepEqual(goiYTimKiem("aruto", KHO, CACH).fandom, []);
});

test("gop ket qua: backend truoc, them truyen chi tai cho moi thay; bo trung giua nhom", () => {
  const mayChu = [{ novel_id: "x" }, { novel_id: "a" }];
  assert.deepEqual(gopTruyen(mayChu, [{ novel_id: "a" }, { novel_id: "b" }, { novel_id: "c" }], 3).map((n) => n.novel_id), ["x", "a", "b"]);
  assert.deepEqual(gopTruyen(mayChu, [], 5).map((n) => n.novel_id), ["x", "a"]);
  assert.deepEqual(boTrungTheoId([{ novel_id: "a" }, { novel_id: "z" }], mayChu).map((n) => n.novel_id), ["z"]);
});

test("hop tim: ban phim, Enter, Escape, bam ra ngoai, giam nhip, huy request cu", () => {
  const src = read("../src/components/SearchOverlay.tsx");
  assert.match(src, /const NHIP_GO = 250;/);
  assert.match(src, /new AbortController\(\)/);
  assert.match(src, /e\.key === "Escape"/);
  assert.match(src, /e\.key === "ArrowDown"/);
  assert.match(src, /e\.key === "ArrowUp"/);
  // Enter khi CHUA chon muc nao -> tim trong Thu vien; chua chon = -1.
  assert.match(src, /useState\(-1\)/);
  assert.match(src, /router\.push\(muc \? duong\(muc\) : `\/library\?q=\$\{encodeURIComponent\(tu\)\}`\)/);
  // Enter tren mot lien ket dang giu tieu diem (Tab toi) thi de lien ket tu xu ly.
  assert.match(src, /if \(e\.target !== oNhap\.current\) return;/);
  assert.match(src, /if \(e\.target === e\.currentTarget\) onDong\(\);/);
  // Mo lai: boi den tu cu de go la thay the (khong noi "nar" + "corty").
  assert.match(src, /oNhap\.current\?\.select\(\);/);
  assert.match(src, /aria-activedescendant=\{\s*chon >= 0/);
  // Goi y fandom dan toi Thu vien loc dung fandom.
  assert.match(src, /`\/library\?fandom=\$\{encodeURIComponent\(k\.ten\)\}`/);
});

test("anh chup kho: MOT request dung chung, co han, loi thi quay ve duong may chu", () => {
  const src = read("../src/lib/catalogSnapshot.ts");
  assert.match(src, /content_mode: "all", sort: "updated", limit: TRAN_CUC_BO, offset: 0/);
  assert.match(src, /const HAN_MS = 5 \* 60 \* 1000;/);
  assert.match(src, /return \{ novels: \[\] as Novel\[\], du: false \};/);
  // Ca Thu vien va hop tim dung chung mot ham.
  assert.match(read("../src/app/library/page.tsx"), /useAsyncData\(taiAnhChupKho\)/);
  assert.match(read("../src/components/SearchOverlay.tsx"), /taiAnhChupKho\(\)\.then/);
});
