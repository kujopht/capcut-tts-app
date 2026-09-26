/*
 * TIEP TUC DOC / NGHE + lua chon che do. Chay CHINH `src/lib/readerSession.ts`
 * voi mot kho luu gia (Map) — va mot kho NEM loi, vi cua so rieng tu / trinh
 * duyet chan luu tru la chuyen co that.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  cheDoKhiMo,
  chuoiGhiCookie,
  deXuatTiepTuc,
  docTienDo,
  ghiTienDo,
  giaiMaCookie,
  HET_HAN_MS,
  KHOA_TIEN_DO,
  maHoaCookie,
  TOI_DA_BAN_GHI,
  TUY_CHON_MAC_DINH,
} from "../src/lib/readerSession.ts";

function khoGia() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), _m: m };
}
const khoHong = {
  getItem() {
    throw new Error("SecurityError");
  },
  setItem() {
    throw new Error("QuotaExceededError");
  },
};

test("che do khi mo trang: URL > cookie > mac dinh 'read_listen'; audio/chu quyet dinh truoc het", () => {
  assert.equal(cheDoKhiMo({ coAudio: true, coChu: true }), "read_listen", "mac dinh: MOT trai nghiem doc+nghe");
  assert.equal(cheDoKhiMo({ daLuu: "listen", coAudio: true, coChu: true }), "listen");
  assert.equal(cheDoKhiMo({ tuUrl: "read", daLuu: "listen", coAudio: true, coChu: true }), "read");
  // Gia tri URL rac -> bo qua, dung cookie.
  assert.equal(cheDoKhiMo({ tuUrl: "<script>", daLuu: "listen", coAudio: true, coChu: true }), "listen");
  assert.equal(cheDoKhiMo({ tuUrl: "listen", coAudio: false, coChu: true }), "read");
  assert.equal(cheDoKhiMo({ tuUrl: "read", coAudio: true, coChu: false }), "listen");
});

test("cookie che do: ma hoa/giai ma khu hoi, gia tri hong -> mac dinh, khong nem", () => {
  const t = { cheDo: "listen", khungChu: "closed", thuNho: true, theoGiong: false };
  assert.deepEqual(giaiMaCookie(maHoaCookie(t)), t);
  assert.deepEqual(giaiMaCookie(encodeURIComponent(maHoaCookie(t))), t);
  const t2 = { cheDo: null, khungChu: "open", thuNho: false, theoGiong: null };
  assert.deepEqual(giaiMaCookie(maHoaCookie(t2)), t2);
  for (const rac of [undefined, null, "", "v2.listen.open.0.1", "garbage", "v1.hack.???.9.9"]) {
    const r = giaiMaCookie(rac);
    assert.ok(r.cheDo === null || ["read", "read_listen", "listen"].includes(r.cheDo));
    assert.ok(["open", "collapsed", "closed"].includes(r.khungChu));
  }
  assert.deepEqual(giaiMaCookie("v2.x"), TUY_CHON_MAC_DINH);
  // Khung chu mac dinh o che do Nghe: thu gon (thay doan dang doc, khong ca chuong).
  assert.equal(TUY_CHON_MAC_DINH.khungChu, "collapsed");
});

test("cookie ghi: Path=/, SameSite=Lax, 1 nam, Secure khi https; khong chua gi ca nhan", () => {
  const s = chuoiGhiCookie({ cheDo: "read", khungChu: "open", thuNho: false, theoGiong: true }, true);
  assert.match(s, /^fas_doc_chedo=v1\.read\.open\.0\.1; Path=\/; Max-Age=31536000; SameSite=Lax; Secure$/);
  assert.ok(!/Secure/.test(chuoiGhiCookie(TUY_CHON_MAC_DINH, false)));
});

test("tien do: ghi GOP — cuon trang khong xoa vi tri audio va nguoc lai", () => {
  const kho = khoGia();
  ghiTienDo(kho, "c1", "n1", { doan: 12, tongDoan: 80, cheDo: "read" }, 1000);
  ghiTienDo(kho, "c1", "n1", { giay: 431.5, thoiLuong: 1800 }, 2000);
  const r = docTienDo(kho, "c1");
  assert.equal(r.doan, 12);
  assert.equal(r.tongDoan, 80);
  assert.equal(r.giay, 431.5);
  assert.equal(r.thoiLuong, 1800);
  assert.equal(r.cheDo, "read");
  assert.equal(r.capNhat, 2000);
  assert.equal(docTienDo(kho, "khong-co"), null);
});

test("tien do: moi nhat len dau, giu toi da N chuong", () => {
  const kho = khoGia();
  for (let i = 0; i < TOI_DA_BAN_GHI + 15; i++) ghiTienDo(kho, `c${i}`, "n", { doan: i }, i);
  const d = JSON.parse(kho.getItem(KHOA_TIEN_DO));
  assert.equal(d.ds.length, TOI_DA_BAN_GHI);
  assert.equal(d.ds[0].chapterId, `c${TOI_DA_BAN_GHI + 14}`);
  assert.equal(docTienDo(kho, "c0"), null, "chuong cu nhat bi day ra");
});

test("tien do: kho HONG hoac du lieu rac -> khong nem, coi nhu chua co", () => {
  assert.equal(docTienDo(khoHong, "c1"), null);
  assert.doesNotThrow(() => ghiTienDo(khoHong, "c1", "n", { doan: 3 }, 1));
  assert.equal(docTienDo(null, "c1"), null);
  const kho = khoGia();
  kho.setItem(KHOA_TIEN_DO, "{not json");
  assert.equal(docTienDo(kho, "c1"), null);
  kho.setItem(KHOA_TIEN_DO, JSON.stringify({ v: 1, ds: [{ chapterId: "c1", doan: "x" }, null, 5] }));
  assert.equal(docTienDo(kho, "c1"), null, "ban ghi sai kieu bi loc");
});

test("de xuat: 'Tiếp tục đọc' + 'Tiếp tục nghe' khi co vi tri dang ke", () => {
  const r = { chapterId: "c", novelId: "n", cheDo: "read_listen", doan: 34, tongDoan: 120, giay: 751, thoiLuong: 1800, capNhat: 0 };
  const dx = deXuatTiepTuc(r, { coAudio: true, soDoan: 120, bayGio: 1000 });
  assert.deepEqual(dx.doc, { doan: 34, tongDoan: 120 });
  assert.deepEqual(dx.nghe, { giay: 751, thoiLuong: 1800 });
});

test("de xuat: KHONG moi khi vi tri chua dang ke, da xong, qua cu, hoac khong co audio", () => {
  const goc = { chapterId: "c", novelId: "n", cheDo: "read", doan: 1, tongDoan: 120, giay: 8, thoiLuong: 1800, capNhat: 0 };
  assert.equal(deXuatTiepTuc(goc, { coAudio: true, soDoan: 120, bayGio: 1 }), null, "vai doan dau + 8 giay: chua dang ke");
  // Da doc toi doan cuoi + nghe gan het -> can "chương sau", khong phai "tiếp tục".
  assert.equal(deXuatTiepTuc({ ...goc, doan: 119, giay: 1795 }, { coAudio: true, soDoan: 120, bayGio: 1 }), null);
  // Qua 30 ngay.
  assert.equal(deXuatTiepTuc({ ...goc, doan: 50 }, { coAudio: true, soDoan: 120, bayGio: HET_HAN_MS + 5 }), null);
  // Chuong khong con audio: chi moi doc.
  const dx = deXuatTiepTuc({ ...goc, doan: 50, giay: 600 }, { coAudio: false, soDoan: 120, bayGio: 1 });
  assert.equal(dx.nghe, null);
  assert.deepEqual(dx.doc, { doan: 50, tongDoan: 120 });
  assert.equal(deXuatTiepTuc(null, { coAudio: true, soDoan: 1, bayGio: 1 }), null);
});

test("trang chuong: 'Tiếp tục nghe' chi phat SAU KHI BAM; khong moi khi dang nghe song chuong nay", () => {
  const src = readFileSync(new URL("../src/components/reader/ChapterExperience.tsx", import.meta.url), "utf8");
  // Phat tu vi tri da luu nam TRONG ham xu ly nut, khong trong effect mo trang.
  const tiepTucNghe = src.slice(src.indexOf("const tiepTucNghe = useCallback"));
  assert.match(tiepTucNghe.slice(0, 400), /batDauTu: giay, tuPhat: true/);
  assert.match(src, /onClick=\{tiepTucNghe\}/);
  assert.match(src, /nghe: dangNghe \? null : dx\.nghe/);
  assert.match(src, /Tiếp tục đọc/);
  assert.match(src, /Tiếp tục nghe/);
  // Luu tien do: vi tri doc (theo doan) + vi tri audio (moi 5s va khi dung).
  // Sprint 2: ban ghi kem them ten truyen/chuong (tuy chon) cho dai "Đang đọc
  // dở" o Thu vien — loi goi xuong dong, nen cho phep khoang trang.
  assert.match(src, /ghiTienDo\(\s*khoLuu\(\),\s*chapterId,\s*novelId,\s*\{ doan, tongDoan: ps\.length, cheDo: mode/);
  assert.match(src, /Math\.abs\(giay - giayDaLuu\.current\) < 5/);
});
