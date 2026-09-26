/**
 * Sprint 3 — video nen: nhe hon, tai SAU noi dung, khong tai tren thiet bi cam ung / mang cham, giai phong khi go.
 *
 * Do tren fanfic.world (2026-09-27, 1440px, khach): nen chiem 4,2-7,2 MB moi trang (73-95% tong byte), request
 * video bat dau TRUOC LCP. Xem docs/reports/UX_PERF_SPRINT3_OVERNIGHT.md.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const LIVE = new URL("../public/artwork/fantasy-backgrounds/live/", import.meta.url);
const TEP = ["01-home", "02-explore", "03-reader", "04-studio", "05-write", "06-library", "07-account", "08-auth"];

test("ban v2 du 8 chu de, nhe hon ban goc it nhat 60%, ban goc van con", () => {
  let goc = 0;
  let av1 = 0;
  let h264 = 0;
  for (const t of TEP) {
    const g = new URL(`${t}.mp4`, LIVE);
    const a = new URL(`v2/${t}-900-av1.mp4`, LIVE);
    const h = new URL(`v2/${t}-720-h264.mp4`, LIVE);
    assert.ok(existsSync(g), `mất bản gốc ${t}.mp4 (không được xoá)`);
    assert.ok(existsSync(a) && existsSync(h), `thiếu bản v2 của ${t}`);
    goc += statSync(g).size;
    av1 += statSync(a).size;
    h264 += statSync(h).size;
    assert.ok(statSync(a).size < 2.4 * 1024 * 1024, `${t}-900-av1.mp4 quá nặng`);
    assert.ok(statSync(h).size < 2.4 * 1024 * 1024, `${t}-720-h264.mp4 quá nặng`);
    // Chu ky MP4 + dung codec: 'ftyp' o dau tep, hop 'av01' / 'avc1' trong mo ta mau.
    const ba = readFileSync(a);
    assert.equal(ba.subarray(4, 8).toString("latin1"), "ftyp");
    assert.ok(ba.includes(Buffer.from("av01")), `${t}-900-av1.mp4 không phải AV1`);
    assert.ok(readFileSync(h).includes(Buffer.from("avc1")), `${t}-720-h264.mp4 không phải H.264`);
  }
  assert.ok(av1 < goc * 0.4, `AV1 ${Math.round(av1 / 1024)} KB không nhẹ hơn đủ so với gốc ${Math.round(goc / 1024)} KB`);
  assert.ok(h264 < goc * 0.4, `H.264 dự phòng ${Math.round(h264 / 1024)} KB không nhẹ hơn đủ`);
});

test("videoNen tro toi v2: AV1 + H.264 du phong, van trong live/", () => {
  const lib = read("../src/lib/backgrounds.ts");
  assert.match(lib, /av1: `\/artwork\/fantasy-backgrounds\/live\/v2\/\$\{tep\}-900-av1\.mp4`/);
  assert.match(lib, /mp4: `\/artwork\/fantasy-backgrounds\/live\/v2\/\$\{tep\}-720-h264\.mp4`/);
});

test("<source> AV1 dung TRUOC mp4 va khai bao codecs (trinh duyet khong co AV1 bo qua khong tai)", () => {
  const s = read("../src/components/LiveBackground.tsx");
  assert.match(s, /export const AV1_TYPE = 'video\/mp4; codecs="av01\.0\.08M\.08"';/);
  const iAv1 = s.indexOf("<source src={video.av1} type={AV1_TYPE} />");
  const iMp4 = s.indexOf('<source src={video.mp4} type="video/mp4" />');
  assert.ok(iAv1 > 0 && iMp4 > iAv1, "nguồn AV1 phải đứng trước H.264");
});

test("video chi mount SAU: tab hien + load + moc toi thieu + trinh duyet ranh", () => {
  const s = read("../src/components/LiveBackground.tsx");
  const m = s.match(/const TOI_THIEU_MS = (\d+);/);
  assert.ok(m && Number(m[1]) >= 2000, "cần mốc tối thiểu >= 2 s — `load` đến trước khi dữ liệu API về");
  assert.match(s, /document\.readyState === "complete"/);
  assert.match(s, /addEventListener\("load", choRanh, \{ once: true \}\)/);
  assert.match(s, /requestIdleCallback\(xong, \{ timeout: 2000 \}\)/);
  assert.match(s, /if \(document\.hidden\) document\.addEventListener\("visibilitychange", khiHien\)/);
  // Lan tinh DAU TIEN cua eligibility chi chay khi toi moc; doi media query truoc do KHONG mo video som.
  assert.match(s, /let daToiMoc = false;/);
  assert.match(s, /if \(!daToiMoc\) return;/);
  assert.ok(!/queueMicrotask\(tinhLai\)/.test(s), "không được còn đường mount video ngay sau render đầu");
});

test("khong video tren thiet bi cam ung (ca tablet ngang) va mang cham", () => {
  const s = read("../src/components/LiveBackground.tsx");
  assert.match(s, /window\.matchMedia\("\(hover: none\) and \(pointer: coarse\)"\)/);
  assert.match(s, /&& \(!qCamUng\.matches \|\| mobileVideo\)/);
  assert.match(s, /\["slow-2g", "2g", "3g"\]\.includes\(conn\?\.effectiveType \?\? ""\)/);
  assert.match(s, /conn\?\.addEventListener\?\.\("change", tinhLai\)/);
});

test("mot <source> hong KHONG giet video khi con nguon du phong (AV1 hong -> H.264)", () => {
  const s = read("../src/components/LiveBackground.tsx");
  const than = s.slice(s.indexOf("const xuLyLoiVideo = () => {"), s.indexOf("setLoi(true);"));
  assert.match(than, /if \(el && !el\.error && el\.networkState !== HTMLMediaElement\.NETWORK_NO_SOURCE\) return;/);
  assert.ok(than.indexOf("NETWORK_NO_SOURCE") < than.indexOf("el.load();"), "phải bỏ qua lỗi-nguồn TRƯỚC khi load() lại từ đầu");
});

test("go video thi huy tai + tra bo giai ma ngay", () => {
  const s = read("../src/components/LiveBackground.tsx");
  const than = s.slice(s.indexOf("GIAI PHONG"), s.indexOf("}, [hienVideo]);"));
  assert.match(than, /el\.pause\(\);/);
  assert.match(than, /querySelectorAll\("source"\)\.forEach\(\(s\) => s\.removeAttribute\("src"\)\)/);
  assert.match(than, /el\.load\(\);/);
});
