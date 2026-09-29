/*
 * SOCIAL & PLAY V1 — logic thuan cua bang tin Cong dong: bo loc tren URL, gop
 * trang khong trung, "co N bai moi", anh chup de Back ve dung cho, ban nhap +
 * khoa idempotent.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  HET_HAN_ANH_CHUP_MS,
  HET_HAN_BAN_NHAP_MS,
  KHOA_ANH_CHUP,
  TRAN_BAI_ANH_CHUP,
  chuoiTruyVanFeed,
  demBaiMoi,
  docBanNhap,
  docTruyVanFeed,
  ghiAnhChup,
  ghiBanNhap,
  gopTrang,
  hoSoHref,
  khoaBanNhap,
  layAnhChup,
  nhanBaiMoi,
  taoKhoaGui,
  urlFeed,
  xoaAnhChup,
  xoaBanNhap,
} from "../src/lib/communityFeed.ts";

function khoGia() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => void m.set(k, String(v)),
    removeItem: (k) => void m.delete(k),
    _m: m,
  };
}

const bai = (id, t) => ({ post_id: id, created_at: t });

test("truy van feed: doc/ghi URL, mac dinh bi bo, slug la bi loai", () => {
  assert.deepEqual(docTruyVanFeed(""), { scope: "latest", fandom: "" });
  assert.deepEqual(docTruyVanFeed("?tab=following&fandom=one-piece"), { scope: "following", fandom: "one-piece" });
  assert.deepEqual(docTruyVanFeed("?tab=xyz&fandom=<script>"), { scope: "latest", fandom: "" });
  assert.equal(chuoiTruyVanFeed({ scope: "latest", fandom: "" }), "");
  assert.equal(urlFeed({ scope: "following", fandom: "naruto" }), "/community?tab=following&fandom=naruto");
  // khu hoi: ghi ra roi doc lai ra dung truy van
  for (const q of [{ scope: "latest", fandom: "conan" }, { scope: "following", fandom: "" }]) {
    assert.deepEqual(docTruyVanFeed(chuoiTruyVanFeed(q)), q);
  }
});

test("gop trang: khong trung post_id, giu thu tu, bai vua dang khong hien hai lan", () => {
  const cu = [bai("p3", "3"), bai("p2", "2")];
  const moi = [bai("p2", "2"), bai("p1", "1")];
  assert.deepEqual(gopTrang(cu, moi).map((x) => x.post_id), ["p3", "p2", "p1"]);
  assert.deepEqual(gopTrang([], moi).map((x) => x.post_id), ["p2", "p1"]);
  // trang moi tu trung lap trong chinh no
  assert.deepEqual(gopTrang([], [bai("a", "1"), bai("a", "1")]).map((x) => x.post_id), ["a"]);
});

test("dem bai moi: chi bai moi hon dau danh sach, khong dem bai da co", () => {
  const dangHien = [bai("p3", "2026-09-26T10:00:00Z"), bai("p2", "2026-09-26T09:00:00Z")];
  const dau = [bai("p5", "2026-09-26T10:05:00Z"), bai("p4", "2026-09-26T10:01:00Z"), bai("p3", "2026-09-26T10:00:00Z")];
  assert.equal(demBaiMoi(dangHien, dau), 2);
  assert.equal(demBaiMoi([], dau), 0);
  // bai cu (thoi diem nho hon moc) khong tinh la moi du chua co trong danh sach
  assert.equal(demBaiMoi(dangHien, [bai("x", "2026-09-26T08:00:00Z")]), 0);
  assert.equal(nhanBaiMoi(0, 20), "");
  assert.equal(nhanBaiMoi(3, 20), "Có 3 bài mới");
  assert.equal(nhanBaiMoi(20, 20), "Có 20+ bài mới");
});

test("anh chup: dung mot lan, dung khoa, het han, tran so bai", () => {
  const kho = khoGia();
  const items = Array.from({ length: 5 }, (_, i) => bai(`p${i}`, String(i)));
  ghiAnhChup(kho, { khoa: "?tab=following", items, nextCursor: "c1", depthCapped: false, moBinhLuan: ["p1"], y: 900, t: 1000 });
  assert.equal(layAnhChup(kho, "", 1000), null, "sai khoa (bo loc khac) -> khong khoi phuc");
  ghiAnhChup(kho, { khoa: "?tab=following", items, nextCursor: "c1", depthCapped: false, moBinhLuan: ["p1"], y: 900, t: 1000 });
  const a = layAnhChup(kho, "?tab=following", 2000);
  assert.equal(a.items.length, 5);
  assert.equal(a.nextCursor, "c1");
  assert.deepEqual(a.moBinhLuan, ["p1"]);
  assert.equal(a.y, 900);
  assert.equal(layAnhChup(kho, "?tab=following", 2000), null, "da dung roi");
  ghiAnhChup(kho, { khoa: "", items, nextCursor: null, depthCapped: false, moBinhLuan: [], y: 1, t: 0 });
  assert.equal(layAnhChup(kho, "", HET_HAN_ANH_CHUP_MS + 1), null, "het han");
  // qua tran so bai: cat bot va bo cursor (tai tiep se bat dau lai)
  const nhieu = Array.from({ length: TRAN_BAI_ANH_CHUP + 5 }, (_, i) => bai(`q${i}`, String(i)));
  ghiAnhChup(kho, { khoa: "", items: nhieu, nextCursor: "c9", depthCapped: false, moBinhLuan: [], y: 0, t: 5 });
  const b = layAnhChup(kho, "", 6);
  assert.equal(b.items.length, TRAN_BAI_ANH_CHUP);
  assert.equal(b.nextCursor, null);
  assert.ok(kho._m.has(KHOA_ANH_CHUP) === false);
});

test("anh chup: doc KHONG xoa (xoa=false) song sot qua effect chay hai lan, roi tu xoa", () => {
  const kho = khoGia();
  const items = [bai("p1", "1")];
  ghiAnhChup(kho, { khoa: "", items, nextCursor: null, depthCapped: false, moBinhLuan: ["p1"], y: 640, t: 10 });
  const lan1 = layAnhChup(kho, "", 11, false);
  const lan2 = layAnhChup(kho, "", 12, false);
  assert.equal(lan1.y, 640);
  assert.equal(lan2.y, 640, "lan chay thu hai (StrictMode) van thay anh chup");
  xoaAnhChup(kho);
  assert.equal(layAnhChup(kho, "", 13, false), null);
  // sai khoa hoac het han thi van bi don di ngay ca khi xoa=false
  ghiAnhChup(kho, { khoa: "?tab=following", items, nextCursor: null, depthCapped: false, moBinhLuan: [], y: 1, t: 0 });
  assert.equal(layAnhChup(kho, "", 1, false), null);
  assert.equal(kho.getItem(KHOA_ANH_CHUP), null);
});

test("anh chup: kho loi / JSON hong khong lam sap trang", () => {
  const hong = { getItem: () => "{khong-phai-json", setItem: () => { throw new Error("day"); }, removeItem: () => {} };
  assert.equal(layAnhChup(hong, "", 0), null);
  assert.equal(ghiAnhChup(hong, { khoa: "", items: [], nextCursor: null, depthCapped: false, moBinhLuan: [], y: 0, t: 0 }), false);
  assert.equal(layAnhChup(null, "", 0), null);
});

test("ban nhap: luu theo nguoi dung, rong thi xoa, het han, du lieu la bi bo", () => {
  const kho = khoGia();
  ghiBanNhap(kho, "usr_a", { text: "chao", fandom: "naruto", spoiler: true, novelId: "", khoaGui: "k12345678", t: 10 });
  assert.equal(docBanNhap(kho, "usr_b", 11), null, "nguoi khac khong thay ban nhap");
  const b = docBanNhap(kho, "usr_a", 11);
  assert.equal(b.text, "chao");
  assert.equal(b.spoiler, true);
  assert.equal(b.khoaGui, "k12345678");
  ghiBanNhap(kho, "usr_a", { text: "   ", fandom: "", spoiler: false, novelId: "", khoaGui: "", t: 12 });
  assert.equal(kho.getItem(khoaBanNhap("usr_a")), null, "ban nhap rong bi xoa");
  ghiBanNhap(kho, "usr_a", { text: "x", fandom: "", spoiler: false, novelId: "", khoaGui: "", t: 0 });
  assert.equal(docBanNhap(kho, "usr_a", HET_HAN_BAN_NHAP_MS + 1), null, "het han");
  kho.setItem(khoaBanNhap("usr_a"), JSON.stringify({ text: 5 }));
  assert.equal(docBanNhap(kho, "usr_a", 1), null);
  ghiBanNhap(kho, "usr_a", { text: "y", fandom: "", spoiler: false, novelId: "", khoaGui: "", t: 1 });
  xoaBanNhap(kho, "usr_a");
  assert.equal(docBanNhap(kho, "usr_a", 2), null);
});

test("khoa gui: chi ky tu an toan, 8..64, may chu chap nhan", () => {
  const re = /^[A-Za-z0-9_-]{8,64}$/;
  assert.match(taoKhoaGui(() => "550e8400-e29b-41d4-a716-446655440000"), re);
  assert.match(taoKhoaGui(() => "ab"), re);
  assert.match(taoKhoaGui(() => "x".repeat(200)), re);
});

test("ho so: username truoc, user_id bat bien khi chua co username", () => {
  assert.equal(hoSoHref({ username: "qa_lan", user_id: "usr_1" }), "/u/qa_lan");
  assert.equal(hoSoHref({ username: "", user_id: "usr_1" }), "/u/usr_1");
  assert.equal(hoSoHref(null), "");
});
