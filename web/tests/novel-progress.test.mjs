/*
 * PRODUCT UX SPRINT 2 — nut hanh dong theo tien do (Thu vien + trang truyen)
 * va `?resume=1` o trang chuong.
 *
 * `lib/novelProgress.ts` la tep thuan: nap thang, kiem bang HANH VI.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  banGhiMoiNhat,
  daXong,
  dangDoc,
  dangNghe,
  hanhDongTruyen,
  trangThaiChuong,
} from "../src/lib/novelProgress.ts";
import { ghiTienDo, docTatCaTienDo } from "../src/lib/readerSession.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

function ban(phan) {
  return {
    chapterId: "c2",
    novelId: "n1",
    cheDo: "read",
    doan: 0,
    tongDoan: 0,
    giay: 0,
    thoiLuong: 0,
    capNhat: 1000,
    ...phan,
  };
}

test("chua co ban ghi -> 'Bắt đầu', lien ket chuong dau dung che do theo loai truyen", () => {
  const coChu = hanhDongTruyen(null, { coAudio: true, chuongDau: "c1" });
  assert.equal(coChu.kieu, "moi");
  assert.equal(coChu.nhan, "Bắt đầu");
  assert.equal(coChu.nhanDayDu, "Bắt đầu đọc");
  assert.equal(coChu.href, "/chapters/c1?mode=read_listen");
  const chiAudio = hanhDongTruyen(null, { coAudio: true, chiAudio: true, chuongDau: "c1" });
  assert.equal(chiAudio.nhanDayDu, "Bắt đầu nghe");
  assert.equal(chiAudio.href, "/chapters/c1?mode=listen");
  // Khong biet chuong dau (the Thu vien): de trang goi tu quyet.
  assert.equal(hanhDongTruyen(null, { coAudio: false }).href, null);
});

test("doc do -> 'Đọc tiếp' mo DUNG chuong va xin ap vi tri (?resume=1)", () => {
  const hd = hanhDongTruyen(ban({ doan: 12, tongDoan: 80 }), { coAudio: true });
  assert.equal(hd.kieu, "doc");
  assert.equal(hd.nhan, "Đọc tiếp");
  assert.equal(hd.href, "/chapters/c2?mode=read&resume=1");
  assert.equal(hd.chapterId, "c2");
  assert.ok(hd.tiLe > 0.15 && hd.tiLe < 0.17);
});

test("nghe do -> 'Nghe tiếp'; doc + nghe do -> 'Tiếp tục đọc & nghe'", () => {
  const nghe = hanhDongTruyen(ban({ giay: 431, thoiLuong: 1800, cheDo: "listen" }), { coAudio: true });
  assert.equal(nghe.kieu, "nghe");
  assert.equal(nghe.href, "/chapters/c2?mode=listen&resume=1");
  const caHai = hanhDongTruyen(ban({ doan: 20, tongDoan: 80, giay: 431, thoiLuong: 1800 }), { coAudio: true });
  assert.equal(caHai.kieu, "ca-hai");
  assert.equal(caHai.nhanDayDu, "Tiếp tục đọc & nghe");
  assert.equal(caHai.href, "/chapters/c2?mode=read_listen&resume=1");
  // Truyen KHONG co audio: vi tri audio (neu co, du lieu cu) khong doi nut.
  assert.equal(hanhDongTruyen(ban({ doan: 20, tongDoan: 80, giay: 431 }), { coAudio: false }).kieu, "doc");
});

test("xong mot chuong -> chuong TIEP THEO (khong 'tiếp tục' chuong da xong)", () => {
  const r = ban({ doan: 79, tongDoan: 80 });
  assert.equal(daXong(r), true);
  assert.equal(dangDoc(r), false);
  const hd = hanhDongTruyen(r, { coAudio: false, chuongSau: (id) => (id === "c2" ? "c3" : null) });
  assert.equal(hd.kieu, "xong");
  assert.equal(hd.nhanDayDu, "Đọc chương tiếp theo");
  assert.equal(hd.href, "/chapters/c3?mode=read");
  // Chuong moi nhat: khong co lien ket bia.
  const cuoi = hanhDongTruyen(r, { coAudio: false, chuongSau: () => null });
  assert.equal(cuoi.href, null);
  assert.equal(cuoi.nhanDayDu, "Đã tới chương mới nhất");
});

test("nguong: vai giay dau / doan dau khong tinh la dang do; vai giay cuoi la xong", () => {
  assert.equal(dangNghe(ban({ giay: 10, thoiLuong: 1800 })), false);
  assert.equal(dangNghe(ban({ giay: 16, thoiLuong: 1800 })), true);
  assert.equal(dangNghe(ban({ giay: 1795, thoiLuong: 1800 })), false);
  assert.equal(dangDoc(ban({ doan: 0, tongDoan: 50 })), false);
  assert.equal(dangDoc(ban({ doan: 1, tongDoan: 50 })), true);
});

test("ban ghi MOI NHAT cua dung truyen; muc luc biet chuong dang/da doc", () => {
  const ds = [
    ban({ chapterId: "c5", novelId: "n2", capNhat: 9000 }),
    ban({ chapterId: "c3", capNhat: 5000, doan: 5, tongDoan: 40 }),
    ban({ chapterId: "c2", capNhat: 3000, doan: 39, tongDoan: 40 }),
  ];
  assert.equal(banGhiMoiNhat(ds, "n1").chapterId, "c3");
  assert.equal(banGhiMoiNhat(ds, "khong-co"), null);
  const m = trangThaiChuong(ds, "n1");
  assert.equal(m.get("c3"), "dang");
  assert.equal(m.get("c2"), "xong");
  assert.equal(m.has("c5"), false);
});

test("ban ghi Sprint 2 kem ten truyen/chuong (tuy chon), ban ghi cu van doc duoc", () => {
  const luu = new Map();
  const kho = { getItem: (k) => luu.get(k) ?? null, setItem: (k, v) => luu.set(k, v) };
  ghiTienDo(kho, "c1", "n1", { doan: 3, tongDoan: 30 }, 1);
  const cu = docTatCaTienDo(kho)[0];
  assert.equal("tenTruyen" in cu, false, "không gắn trường rỗng khi không có tên");
  ghiTienDo(kho, "c1", "n1", { doan: 4, tenTruyen: "Hỏa Ảnh", tenChuong: "Chương 1" }, 2);
  ghiTienDo(kho, "c1", "n1", { giay: 40 }, 3);
  const moi = docTatCaTienDo(kho)[0];
  assert.equal(moi.tenTruyen, "Hỏa Ảnh", "tên được giữ qua các lần ghi sau");
  assert.equal(moi.tenChuong, "Chương 1");
  assert.equal(moi.doan, 4);
});

test("trang chuong ap vi tri ngay khi URL co ?resume=1 (khong hoi lai bang dai)", () => {
  const page = read("../src/app/chapters/[id]/page.tsx");
  assert.match(page, /const autoResume = sp\.resume === "1";/);
  assert.match(page, /autoResume=\{autoResume\}/);
  const exp = read("../src/components/reader/ChapterExperience.tsx");
  assert.match(exp, /autoResume = false/);
  // Tu ap: uu tien vi tri nghe, khong thi cuon toi doan da doc.
  const khoi = exp.slice(exp.indexOf("const daTuTiepTuc = useRef(false);"));
  assert.match(khoi.slice(0, 600), /if \(deXuat\.nghe\) tiepTucNghe\(\);\s*else tiepTucDoc\(\);/);
  // Bang dai "Tiếp tục đọc/nghe" khong hien khi da tu ap.
  assert.match(exp, /\{deXuat && !autoResume \? \(/);
});

test("the Thu vien va trang truyen dung CHUNG logic tien do", () => {
  const lib = read("../src/app/library/page.tsx");
  assert.match(lib, /hanhDongTruyen\(banGhi, \{ coAudio, chiAudio: cu \}\)/);
  assert.match(lib, /useReaderProgress\(\)/);
  const cta = read("../src/components/novel/NovelPrimaryCta.tsx");
  assert.match(cta, /hanhDongTruyen\(r, \{/);
  assert.match(cta, /chuongSau: \(id\) =>/);
  // HTML may chu = "chua doc" (anh chup may chu rong) -> khong loi hydrate.
  const hook = read("../src/lib/useReaderProgress.ts");
  assert.match(hook, /useSyncExternalStore\(dangKy, anhChup, \(\) => RONG\)/);
});
