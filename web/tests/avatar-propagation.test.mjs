/**
 * V4 Phase 6 (tiep) — avatar phai lan toa het cac be mat hien tac gia/nguoi
 * dung, khong chi /account va menu avatar.
 *
 * Backend: `SocialService._the_nguoi` (dung chung cho bai dang/binh luan/
 * tra loi/thong bao) va `CreatorService.search_people` deu da duoc kiem
 * o `server/tests/test_social_service.py::AvatarLanTruyenTest`. O day chi
 * kiem phia FRONTEND thuc su hien avatar do ra, khong con ve chu cai suong.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const postCard = () => read("../src/components/PostCard.tsx");
const commentThread = () => read("../src/components/CommentThread.tsx");
const searchOverlay = () => read("../src/components/SearchOverlay.tsx");
const publicProfile = () => read("../src/app/u/[username]/page.tsx");
const postComposer = () => read("../src/components/PostComposer.tsx");
const communitySidebar = () => read("../src/components/CommunitySidebar.tsx");
const api = () => read("../src/lib/api.ts");

test("AuthorCard (kieu dung chung cho bai/binh luan/tim kiem) co avatar_url", () => {
  const src = api();
  const at = src.indexOf("interface AuthorCard");
  const than = src.slice(at, src.indexOf("}", at));
  assert.match(than, /avatar_url/);
});

/*
  Social & Play V1: moi be mat hien mot NGUOI di qua `UserAvatar` (avatar +
  khung dang trang bi) thay vi tu ghep `<Avatar>`/`<CosmeticFrame>` — nen bat
  bien "hien avatar THAT" gio co hai nua: (1) be mat truyen DUNG doi tuong
  nguoi (co `avatar_url`) vao `UserAvatar`, (2) `UserAvatar` chuyen
  `avatar_url` do xuong `<Avatar>` va gan khung dang deo.
*/
const userAvatar = () => read("../src/components/UserAvatar.tsx");

test("UserAvatar chuyen avatar_url that xuong Avatar va gan khung dang deo", () => {
  const src = userAvatar();
  assert.match(src, /<Avatar name=\{ten\} avatarUrl=\{user\?\.avatar_url\}/);
  assert.match(src, /<CosmeticFrame cosmetic=\{khung\}>/);
  assert.match(src, /slot === "avatar_frame"/);
});

test("PostCard hien avatar that cua tac gia bai dang", () => {
  const src = postCard();
  assert.match(src, /<UserAvatar user=\{bai\.author\}/);
});

test("CommentThread hien avatar cho binh luan/tra loi (dung chung mot component)", () => {
  const src = commentThread();
  // Hang binh luan da render (khong phai o soan) phai lay avatar tu bl.author.
  assert.match(src, /<UserAvatar user=\{bl\.author\}/);
});

test("SearchOverlay hien avatar cho ca ket qua NGUOI va BAI VIET", () => {
  const src = searchOverlay();
  assert.match(src, /avatarUrl=\{p\.avatar_url\}/);
  assert.match(src, /avatarUrl=\{b\.author\?\.avatar_url\}/);
});

test("Trang ho so cong khai (/u/[username]) hien avatar that", () => {
  // `{...p, …}` mang `p.avatar_url` vao UserAvatar, kem khung cong khai.
  const src = publicProfile();
  assert.match(src, /<UserAvatar user=\{\{ \.\.\.p, equipped_cosmetics: gam\?\.equipped_cosmetics \?\? \[\] \}\}/);
});

/*
  Hai be mat nay bi bo sot khi <Avatar> ra doi (thay <span> tu ve tay o moi
  noi) — QA that phat hien: hang kich hoat cua PostComposer va danh sach
  "Tác giả nổi bật" cua CommunitySidebar VAN con ve chu cai suong du profile
  DA co avatar_url that. Kiem rieng vi ca hai deu KHONG nam trong "5 be mat"
  ma phien lam avatar ban dau da liet ke.
*/
test("PostComposer hien avatar that o hang kich hoat (khong chi luc mo rong)", () => {
  const src = postComposer();
  const hang = src.slice(src.indexOf('className="card soan-bai-moi"'));
  assert.match(hang, /^[^]*?<UserAvatar user=\{profile\}/);
  assert.ok(hang.indexOf("<UserAvatar user={profile}") < hang.indexOf("soan-bai-kich-hoat"),
    "avatar phai nam TRONG hang kich hoat, truoc nut mo");
});

test("CommunitySidebar (Tác giả nổi bật) hien avatar that cua tung nguoi", () => {
  const src = communitySidebar();
  assert.match(
    src,
    /avatarUrl=\{p\.avatar_url\}/,
    "danh sách tác giả nổi bật không đọc avatar_url",
  );
});

test("CommunitySidebar loc bo ho so thieu username (ke ca toan khoang trang) truoc khi hien noi bat", () => {
  /*
    QA that phat hien tren production: mot tai khoan seed/test co
    author_status=approved nhung username rong lot vao danh sach "noi bat",
    link ho so dung thang `/u/${username}` nen ra `/u/` roi 404. Phai loc
    TRUOC khi sap xep/cat top 5, khong phai an sau khi da hien. Dung `.trim()`
    de mot username toan khoang trang cung khong lot qua duoc.
  */
  const src = communitySidebar();
  assert.match(
    src,
    /\.filter\(\s*\(p\)\s*=>\s*!!p\.username\?\.trim\(\)\s*\)/,
    "phải lọc bỏ hồ sơ có username rỗng/toàn khoảng trắng trước khi hiện danh sách nổi bật",
  );
});

test("khong con noi nao trong 6 be mat nay tu ve chu cai bang slice(0, 2)", () => {
  /*
    Rao chan chong hoi quy: neu ai do sau nay quay lai kieu cu (chep tay
    span+slice thay vi dung <Avatar>), bai nay do duoc ngay.
  */
  for (const src of [postCard(), commentThread(), searchOverlay(), publicProfile(),
                     postComposer(), communitySidebar()]) {
    assert.doesNotMatch(src, /\.slice\(0,\s*2\)\.toUpperCase\(\)/);
  }
});
