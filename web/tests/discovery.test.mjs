import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  isInternalTag,
  formatReaderTag,
  inferFandomFromTitle,
  getReaderTags,
  FANDOM_OPTIONS,
} from "../src/lib/taxonomy.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fanficSrc = fs.readFileSync(path.join(__dirname, "../src/app/fanfic/page.tsx"), "utf-8");
const homeSrc = fs.readFileSync(path.join(__dirname, "../src/app/page.tsx"), "utf-8");

test("Discovery: bo loc trang thai gia (statusFilter) da duoc go hoan toan khoi /fanfic", () => {
  // Khong duoc co state gia vo hoat dong
  assert.ok(!/statusFilter/.test(fanficSrc), "khong duoc chua state statusFilter");
  assert.ok(!/setStatusFilter/.test(fanficSrc), "khong duoc chua setter setStatusFilter");
  // Khong co UI lua gat nguoi dung
  assert.ok(!/fanfic-status-label/.test(fanficSrc), "khong duoc co label Trang thai");
  assert.ok(!/aria-labelledby="fanfic-status-label"/.test(fanficSrc), "khong duoc co group Trang thai");
  assert.ok(!fanficSrc.includes("Hoàn thành"), "khong duoc co nut Hoan thanh gia");
  assert.ok(!fanficSrc.includes("Đang ra"), "khong duoc co nut Dang ra gia");
});

test("Discovery: khong giu trang thai the chet api.novelTags() tren /fanfic", () => {
  assert.ok(!fanficSrc.includes("api.novelTags"), "/fanfic khong goi api.novelTags() vao state chet");
});

test("Discovery: /fanfic dung .filter-chips-wrap, khong dung .chip-rail gay cuon ngang", () => {
  assert.match(fanficSrc, /filter-chips-wrap/);
  assert.ok(!fanficSrc.includes("chip-rail"), "/fanfic khong duoc chua .chip-rail");
});

test("Taxonomy: isInternalTag loc sach toan bo ma ky thuat noi bo", () => {
  assert.equal(isInternalTag("work:CAT-b45e5bef7eee"), true);
  assert.equal(isInternalTag("work:OP-6e7aeb886f"), true);
  assert.equal(isInternalTag("work-12345"), true);
  assert.equal(isInternalTag("imported"), true);
  assert.equal(isInternalTag("long_form_audio"), true);
  assert.equal(isInternalTag("fandom:Da Fandom Unresolved"), true);
  assert.equal(isInternalTag("Da Fandom Unresolved"), true);
  assert.equal(isInternalTag(""), true);

  // The hop le
  assert.equal(isInternalTag("fandom:One Piece"), false);
  assert.equal(isInternalTag("fandom:Naruto"), false);
  assert.equal(isInternalTag("One Piece"), false);
  assert.equal(isInternalTag("Action"), false);
});

test("Taxonomy: formatReaderTag tao nhan dep cho doc gia", () => {
  assert.equal(formatReaderTag("fandom:One Piece"), "One Piece");
  assert.equal(formatReaderTag("fandom:Naruto"), "Naruto");
  assert.equal(formatReaderTag("work:CAT-123"), null);
  assert.equal(formatReaderTag("imported"), null);
  assert.equal(formatReaderTag("long_form_audio"), null);
  assert.equal(formatReaderTag("fandom:Da Fandom Unresolved"), null);
});

test("Taxonomy: inferFandomFromTitle bao thu tuyet doi, tu choi tu khoa long leo", () => {
  // TU CHOI tu khoa chung chung (tranh false positive)
  assert.equal(inferFandomFromTitle("Ninja sát thủ truyền kỳ"), null, "ninja khong duoc tu suy ra Naruto");
  assert.equal(inferFandomFromTitle("Quán bar Gin và rượu Tonic"), null, "gin khong duoc tu suy ra Conan");
  assert.equal(inferFandomFromTitle("Luật sư Kisaki bảo vệ thân chủ"), null, "kisaki don doc khong duoc tu suy ra Conan");
  assert.equal(inferFandomFromTitle("Hệ thống tu tiên vô địch"), null, "he thong khong duoc suy ra fandom");
  assert.equal(inferFandomFromTitle(""), null);
  assert.equal(inferFandomFromTitle(undefined), null);

  // DUNG voi cac mau ro rang
  assert.equal(inferFandomFromTitle("Naruto Fanfic Đến Làng Lá Làm Gián Điệp"), "Naruto");
  assert.equal(inferFandomFromTitle("One Piece Fanfic Xây Dựng Đế Chế Ở Thế Giới Hải Tặc"), "One Piece");
  assert.equal(inferFandomFromTitle("Conan Fanfic Ta Sở Hữu Hệ Thống Bồi Dưỡng Để Thu Phục Mọi Mỹ Nhân"), "Conan");
  assert.equal(inferFandomFromTitle("Fairy Tail: Pháp Sư Mạnh Nhất"), "Fairy Tail");
  assert.equal(inferFandomFromTitle("Kuroko no Basket: Cầu Thủ Số 6"), "Bóng rổ");
  assert.equal(inferFandomFromTitle("Slam Dunk: Cao Thủ Bóng Rổ"), "Bóng rổ");
});

test("Taxonomy: getReaderTags khong bao gio tra ve the ky thuat", () => {
  const novelWithTechnicalTags = {
    title: "One Piece x Naruto Fanfic Ta Dịch Chuyển Cả Tộc Uchiha Đến Thế Giới Hải Tặc",
    tags: ["work:OP-6e7aeb886f", "imported", "long_form_audio", "fandom:One Piece"],
  };
  const readerTags = getReaderTags(novelWithTechnicalTags, 3);
  assert.deepEqual(readerTags, ["One Piece"]);

  // Truyen chua co the fandom backend nhung co tieu de ro rang
  const novelUnresolvedWithConanTitle = {
    title: "Conan Fanfic Luật Sư Ác Ma Đối Đầu Nữ Hoàng Phòng Xử Án",
    tags: ["work:CAT-15deb7a2804f", "imported", "long_form_audio", "fandom:Da Fandom Unresolved"],
  };
  assert.deepEqual(getReaderTags(novelUnresolvedWithConanTitle, 3), ["Conan"]);

  // Truyen khong co fandom ro rang -> tha rong chu khong gan sai
  const novelGeneric = {
    title: "Hệ Thống Đăng Nhập Mỗi Ngày",
    tags: ["work:CAT-000000000000", "imported", "long_form_audio", "fandom:Da Fandom Unresolved"],
  };
  assert.deepEqual(getReaderTags(novelGeneric, 3), []);
});

test("Homepage: dải khám phá vũ trụ lấy fandom từ DỮ LIỆU THẬT, không dẫn tới trang rỗng", () => {
  /*
    Product UX Sprint 2: ban truoc dat cung nam chip; "Fairy Tail" va "Bóng rổ"
    dan toi trang RONG (kho doc duoc khong co truyen nao cua hai vu tru do —
    do that 2026-09-25). Nay chip = fandom CO truyen (`chipFandom` tren anh
    chup kho), dan toi Thu vien da loc; mat mang thi roi ve danh sach du phong.
  */
  assert.match(homeSrc, /<FandomStrip \/>/);
  const strip = fs.readFileSync(new URL("../src/components/FandomStrip.tsx", import.meta.url), "utf8");
  assert.match(strip, /chipFandom\(/);
  assert.match(strip, /href=\{`\/library\?fandom=\$\{encodeURIComponent\(c\.ten\)\}`\}/);
  for (const f of ["Naruto", "One Piece", "Detective Conan", "Genshin Impact"]) {
    assert.ok(strip.includes(`"${f}"`), `thiếu fandom dự phòng ${f}`);
  }
  assert.ok(!homeSrc.includes("/fanfic?q=Fairy+Tail"), "chip cũ dẫn tới trang rỗng còn sót");
});
