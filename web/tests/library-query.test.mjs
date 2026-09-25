/*
 * PRODUCT UX SPRINT 2 — Thu vien: trang thai tren URL, sap xep/loc tai cho,
 * chip fandom that, nho vi tri cuon.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  MAC_DINH_THU_VIEN,
  SAP_XEP_MAY_CHU,
  TRAN_CUC_BO,
  catTrang,
  chipFandom,
  chuanHoaFandom,
  chuanHoaTim,
  docTuUrl,
  doi,
  locToanKho,
  sapCucBo,
  sapXepCucBo,
  soBoLoc,
  tenDeSap,
  thamSoDuyet,
  thuocPham,
  veUrl,
} from "../src/lib/libraryQuery.ts";
import { ghiViTri, layViTri, HET_HAN_CUON_MS, KHOA_CUON } from "../src/lib/scrollMemory.ts";
import { fandomCauTruc } from "../src/lib/taxonomy.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const sp = (qs) => new URLSearchParams(qs);

test("URL <-> trang thai: mac dinh KHONG ghi len URL, khu hoi duoc", () => {
  assert.equal(veUrl(MAC_DINH_THU_VIEN), "");
  const t = docTuUrl(sp("fandom=Naruto&audio=read_audio&status=completed&sort=chapters&view=list&page=2&q=hoa"));
  assert.deepEqual(t, {
    tab: "fanfic", q: "hoa", fandom: "Naruto", audio: "read_audio", status: "completed",
    sort: "chapters", view: "list", page: 2,
  });
  assert.deepEqual(docTuUrl(sp(veUrl(t))), t, "khứ hồi phải ra đúng trạng thái");
});

test("URL la / cu van hieu: gia tri la ve mac dinh, ?tag=fandom:X, tab=mine, bi danh fandom", () => {
  const t = docTuUrl(sp("audio=xyz&sort=hot&page=-3&tab=mine&tag=fandom:Naruto"));
  assert.equal(t.audio, "all");
  assert.equal(t.sort, "updated");
  assert.equal(t.page, 1);
  assert.equal(t.tab, "personal");
  assert.equal(t.fandom, "Naruto");
  assert.equal(chuanHoaFandom("conan"), "Detective Conan");
  assert.equal(chuanHoaFandom("GENSHIN"), "Genshin Impact");
  assert.equal(chuanHoaFandom("Bleach"), "Bleach");
  assert.equal(chuanHoaFandom(""), "all");
});

test("doi bo loc ve trang 1; doi trang / kieu xem thi giu", () => {
  const t = { ...MAC_DINH_THU_VIEN, page: 3 };
  assert.equal(doi(t, { fandom: "Naruto" }).page, 1);
  assert.equal(doi(t, { sort: "title" }).page, 1);
  assert.equal(doi(t, { view: "list" }).page, 3);
  assert.equal(doi(t, { page: 4 }).page, 4);
  assert.equal(soBoLoc({ ...MAC_DINH_THU_VIEN, fandom: "Naruto", audio: "text", q: "x" }), 2);
});

test("tham so may chu: dinh dang, sap xep that cua backend, fandom qua dung kenh", () => {
  const ts = (p) => thamSoDuyet({ ...MAC_DINH_THU_VIEN, ...p }, 12);
  assert.equal(ts({}).content_mode, "readable");
  assert.equal(ts({ page: 3 }).offset, 24);
  // `latest` cua backend = updated_at: "Mới xuất bản" phai gui `newest`.
  assert.equal(SAP_XEP_MAY_CHU.latest, "newest");
  // Sap cuc bo: lay ca pham vi mot lan.
  assert.equal(sapCucBo("chapters"), true);
  assert.equal(sapCucBo("updated"), false);
  assert.deepEqual([ts({ sort: "title", page: 2 }).limit, ts({ sort: "title", page: 2 }).offset], [TRAN_CUC_BO, 0]);
  // Fandom backend nhan ra -> `fandom`; fandom khac -> the `fandom:X`.
  assert.deepEqual([ts({ fandom: "Naruto" }).fandom, ts({ fandom: "Naruto" }).tag], ["Naruto", undefined]);
  assert.deepEqual([ts({ fandom: "Bleach" }).fandom, ts({ fandom: "Bleach" }).tag], [undefined, "fandom:Bleach"]);
});

test("ten truyen: thu tu tieng Viet, bo tien to [Fandom]; nhieu chuong: giam dan", () => {
  assert.equal(tenDeSap("[Naruto SI] Trọng Sinh"), "Trọng Sinh");
  assert.equal(tenDeSap("[A] [B] Tên"), "Tên");
  const ds = [
    { title: "The Cold Between Wars", external_chapter_count: 47 },
    { title: "[Naruto] Hỏa Ảnh", external_chapter_count: 99 },
    { title: "[Conan] Dưới Tàng Hoa", external_chapter_count: 16 },
    { title: "Ánh Trăng", external_chapter_count: 16 },
  ];
  assert.deepEqual(sapXepCucBo(ds, "title").map((n) => n.title), [
    "Ánh Trăng", "[Conan] Dưới Tàng Hoa", "[Naruto] Hỏa Ảnh", "The Cold Between Wars",
  ]);
  assert.deepEqual(sapXepCucBo(ds, "chapters").map((n) => n.external_chapter_count), [99, 47, 16, 16]);
  assert.deepEqual(catTrang([1, 2, 3, 4, 5], 2, 2), [3, 4]);
});

/* Du lieu gan giong kho that 2026-09-25 (rut gon). */
const KHO = [
  { novel_id: "a", title: "[Naruto] Hỏa Ảnh: Hiệu Ứng Cánh Bướm", external_author_name: "Corty", description: "", status: "completed", external_chapter_count: 99, has_audio: true, content_mode: "readable", tags: ["fandom:Naruto", "naruto"], fandom_ids: ["fan_naruto"], updated_at: "2026-09-21T10:00:00Z", created_at: "2026-09-21T10:00:00Z" },
  { novel_id: "b", title: "The Cold Between Wars (Naruto)", external_author_name: "Unknown Author", description: "Homura", status: "ongoing", external_chapter_count: 47, has_audio: true, content_mode: "readable", tags: ["Drama"], fandom_ids: ["naruto"], updated_at: "2026-09-20T10:00:00Z", created_at: "2026-09-18T10:00:00Z" },
  { novel_id: "c", title: "[Genshin Impact] Hoa Khôi", external_author_name: "Mặc Dạ", description: "", status: "completed", external_chapter_count: 15, has_audio: true, content_mode: "readable", tags: ["genshin impact"], fandom_ids: ["fan_genshin"], updated_at: "2026-09-19T10:00:00Z", created_at: "2026-09-19T10:00:00Z" },
  { novel_id: "d", title: "Conan Fanfic Ta Sở Hữu", external_author_name: "", description: "", status: "ongoing", external_chapter_count: 0, has_audio: true, content_mode: "audio_only", tags: ["work:CAT-1", "long_form_audio", "fandom:Da Fandom Unresolved"], fandom_ids: [], updated_at: "2026-09-10T10:00:00Z", created_at: "2026-09-10T10:00:00Z" },
  { novel_id: "e", title: "Naruto Fanfic Xuyên Thành", external_author_name: "", description: "", status: "ongoing", external_chapter_count: 0, has_audio: true, content_mode: "audio_only", tags: ["work:CAT-2", "long_form_audio", "fandom:Naruto"], fandom_ids: [], updated_at: "2026-09-09T10:00:00Z", created_at: "2026-09-09T10:00:00Z" },
];
const CUA = {
  co: (n) => ({ cu: n.content_mode === "audio_only", audio: !!n.has_audio, status: n.status }),
  fandom: (n) => fandomCauTruc(n),
  chu: (n) => `${n.title} ${n.external_author_name} ${n.description}`,
  capNhat: (n) => n.updated_at,
  taoLuc: (n) => n.created_at,
};
const t = (p) => ({ ...MAC_DINH_THU_VIEN, ...p });

test("loc toan kho = cung quy tac voi backend: mac dinh khong kho audio cu", () => {
  assert.deepEqual(locToanKho(KHO, t({}), CUA).map((n) => n.novel_id), ["a", "b", "c"]);
  assert.deepEqual(locToanKho(KHO, t({ audio: "legacy" }), CUA).map((n) => n.novel_id), ["d", "e"]);
  assert.deepEqual(locToanKho(KHO, t({ audio: "audio" }), CUA).length, 5);
  assert.deepEqual(locToanKho(KHO, t({ audio: "text" }), CUA), []);
  assert.deepEqual(locToanKho(KHO, t({ fandom: "Naruto" }), CUA).map((n) => n.novel_id), ["a", "b"]);
  assert.deepEqual(locToanKho(KHO, t({ status: "ongoing" }), CUA).map((n) => n.novel_id), ["b"]);
});

test("tim toan kho: khong phan biet dau, tim ca TAC GIA va mo ta", () => {
  assert.equal(chuanHoaTim("  Hỏa   Ảnh "), "hoa anh");
  assert.equal(chuanHoaTim("Đào"), "dao");
  assert.deepEqual(locToanKho(KHO, t({ q: "hoa anh" }), CUA).map((n) => n.novel_id), ["a"]);
  assert.deepEqual(locToanKho(KHO, t({ q: "corty" }), CUA).map((n) => n.novel_id), ["a"]);
  assert.deepEqual(locToanKho(KHO, t({ q: "homura" }), CUA).map((n) => n.novel_id), ["b"]);
});

test("sap toan kho: moi cap nhat / moi xuat ban la hai thu tu KHAC nhau", () => {
  assert.deepEqual(locToanKho(KHO, t({ sort: "updated" }), CUA).map((n) => n.novel_id), ["a", "b", "c"]);
  assert.deepEqual(locToanKho(KHO, t({ sort: "latest" }), CUA).map((n) => n.novel_id), ["a", "c", "b"]);
});

test("chip fandom: chi fandom CO truyen trong pham vi, fandom suy tu tieu de KHONG tinh", () => {
  const macDinh = chipFandom(KHO, CUA.fandom, CUA.co, t({}));
  assert.deepEqual(macDinh, [{ ten: "Naruto", so: 2 }, { ten: "Genshin Impact", so: 1 }]);
  // "Conan Fanfic…" chi co "Da Fandom Unresolved": bo loc backend khong khop
  // no, nen chip Conan KHONG duoc hua mot ket qua may chu khong tra.
  const coAudio = chipFandom(KHO, CUA.fandom, CUA.co, t({ audio: "audio" }));
  assert.deepEqual(coAudio.map((c) => c.ten), ["Naruto", "Genshin Impact"]);
  assert.equal(coAudio[0].so, 3);
  // Fandom dang chon (tu URL) luon co mat de bo chon duoc.
  assert.ok(chipFandom(KHO, CUA.fandom, CUA.co, t({ fandom: "Bleach" })).some((c) => c.ten === "Bleach" && c.so === 0));
  assert.equal(thuocPham(t({ audio: "read_audio" }), { cu: true, audio: true, status: "x" }), false);
});

test("nho vi tri cuon: dung URL, dung mot lan, het han sau 30 phut", () => {
  const luu = new Map();
  const kho = { getItem: (k) => luu.get(k) ?? null, setItem: (k, v) => luu.set(k, v), removeItem: (k) => luu.delete(k) };
  ghiViTri(kho, "/library?fandom=Naruto", 912.4, 1000);
  assert.equal(layViTri(kho, "/library", 1001), null, "URL khác (bộ lọc khác) thì không cuộn");
  assert.equal(layViTri(kho, "/library?fandom=Naruto", 1002), 912);
  assert.equal(layViTri(kho, "/library?fandom=Naruto", 1003), null, "chỉ dùng MỘT lần");
  ghiViTri(kho, "/library", 500, 0);
  assert.equal(layViTri(kho, "/library", HET_HAN_CUON_MS + 1), null, "quá hạn");
  assert.equal(luu.has(KHOA_CUON), false);
  // Kho bi chan / hong khong lam hong trang.
  const hong = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); }, removeItem() {} };
  assert.doesNotThrow(() => ghiViTri(hong, "/library", 1, 1));
  assert.equal(layViTri(hong, "/library", 1), null);
  assert.equal(layViTri(null, "/library", 1), null);
});

test("trang Thu vien: khung xuong khi dang tai (KHONG hien 'khong tim thay'), tra vi tri cuon", () => {
  const src = read("../src/app/library/page.tsx");
  // Thu tu nhanh render: loi -> chua co du lieu (khung xuong) -> rong -> ket qua.
  const i = (s) => src.indexOf(s);
  assert.ok(i("<ErrorState message={loi}") < i(") : !coDuLieu ? (") && i(") : !coDuLieu ? (") < i("<KhungXuong kieu={t.view} />"));
  assert.ok(i("<KhungXuong kieu={t.view} />") < i("hienThi.length === 0 ?"), "trạng thái rỗng chỉ sau khi có dữ liệu");
  assert.match(src, /ghiViTri\(khoPhien\(\), urlHienTai, window\.scrollY, Date\.now\(\)\)/);
  assert.match(src, /layViTri\(khoPhien\(\), urlHienTai, Date\.now\(\)\)/);
  // Ket qua cu duoc giu (mo di) trong luc doi bo loc — khong nhay ve khung xuong.
  assert.match(src, /lib-results\$\{dangTai \? " is-stale" : ""\}/);
});
