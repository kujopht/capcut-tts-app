/*
 * Giong chay tren may worker (Ngoc Huyen — `piper:ngochuyen`).
 *
 * Hai su that ve kien truc quyet dinh moi test o day:
 *
 *  1. Model Piper nam tren LAPTOP worker, con API chay tren Render. Nen truong
 *     `installed` cua API — vốn trả lời "tiến trình này có file model không" —
 *     luon la `false` cho giong cuc bo. Loc theo mot minh no thi Ngoc Huyen
 *     khong bao gio hien ra du may chu da duyet.
 *
 *  2. Laptop tat thi job nam `pending`. No KHONG hong va KHONG duoc doi sang
 *     giong khac. Nhung mot thanh tien trinh quay mai ma khong giai thich thi
 *     nguoi dung chi biet la hong.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

/* ----------------------------------------------- loc giong hien cho nguoi dung */

test("giong chay tren worker van chon duoc du API khong co model", async () => {
  const { usableVoices } = await import("../src/lib/voices.ts");

  const ngocHuyen = {
    voice_id: "piper:ngochuyen",
    installed: false, // Render khong co file .onnx nao
    runs_on_worker: true, // ...nhung may chu da duyet giong nay
  };
  const edge = {
    voice_id: "edge:vi-VN-HoaiMyNeural",
    installed: true,
    runs_on_worker: false,
  };

  const duocChon = usableVoices([ngocHuyen, edge]).map((v) => v.voice_id);
  assert.deepEqual(duocChon, ["piper:ngochuyen", "edge:vi-VN-HoaiMyNeural"]);
});

test("giong khong cai va khong chay tren worker thi bi loai", async () => {
  const { usableVoices } = await import("../src/lib/voices.ts");
  const chuaCai = {
    voice_id: "capcut:khong-dung-duoc",
    installed: false,
    runs_on_worker: false,
  };
  assert.deepEqual(usableVoices([chuaCai]), []);
});

/* --------------------------------------------------- Edge van la giong mac dinh */

test("Ngoc Huyen KHONG duoc dat lam giong mac dinh", async () => {
  const { defaultVoiceId, VERIFIED_VOICE_ID } = await import(
    "../src/lib/voices.ts"
  );

  // Ca hai deu chon duoc, nhung mac dinh phai la giong Edge da kiem chung:
  // no chay tren may chu va khong phu thuoc laptop nao dang bat.
  const chon = defaultVoiceId([
    { voice_id: "piper:ngochuyen", installed: false, runs_on_worker: true },
    { voice_id: VERIFIED_VOICE_ID, installed: true, runs_on_worker: false },
  ]);
  assert.equal(chon, VERIFIED_VOICE_ID);
});

/* ------------------------------------------- noi ro dang cho worker, khong doan */

test("trang studio noi ro job dang cho may tao giong", () => {
  const src = read("../src/app/studio/page.tsx");

  const i = src.indexOf('activeJob.status === "pending"');
  assert.ok(i > 0, "khong tim thay nhanh hien thi trang thai pending");
  const khoi = src.slice(i, i + 1200);

  assert.match(
    khoi,
    /voice_id\.startsWith\("piper:"\)/,
    "phai phan biet giong chay tren worker voi giong chay tren may chu",
  );
  assert.match(
    khoi,
    /máy/,
    "phai noi ro job dang cho MAY tao giong, khong chi 'cho toi luot'",
  );
});

test("giao dien noi ro he thong KHONG tu doi sang giong khac", () => {
  // Quy tac cung cua ca he thong (CLAUDE.md): tong hop that bai hay worker tat
  // deu khong duoc am tham doi giong. Nguoi dung phai duoc noi dieu do — neu
  // khong, ho se tuong audio nhan duoc la giong ho da chon.
  const src = read("../src/app/studio/page.tsx");

  assert.match(
    src,
    /không tự đổi sang giọng khác/,
    "trang phai noi ro he thong khong tu doi giong khi that bai",
  );
  assert.match(
    src,
    /không bị đổi sang giọng khác/,
    "trang phai noi ro job dang cho cung khong bi doi giong",
  );
});

/* --------------------------------- hai muc: de xuat + tat ca giong tieng Viet */

const voice = (voice_id, extra = {}) => ({
  voice_id,
  installed: true,
  runs_on_worker: false,
  recommended: false,
  recommended_order: null,
  display_name: voice_id,
  provider_label: "X",
  status: "available",
  status_label: "",
  ...extra,
});

test("muc de xuat giu dung thu tu may chu cap", async () => {
  const { voiceSections } = await import("../src/lib/voices.ts");

  // Co y xao tron: frontend KHONG duoc dua vao thu tu mang tra ve.
  const vs = [
    voice("c", { recommended: true, recommended_order: 2 }),
    voice("khong-de-xuat"),
    voice("a", { recommended: true, recommended_order: 0 }),
    voice("b", { recommended: true, recommended_order: 1 }),
  ];
  const { recommended } = voiceSections(vs);
  assert.deepEqual(
    recommended.map((v) => v.voice_id),
    ["a", "b", "c"],
  );
});

test("hai muc dung CHUNG ban ghi, khong nhan ban voice nao", async () => {
  const { voiceSections } = await import("../src/lib/voices.ts");

  const a = voice("a", { recommended: true, recommended_order: 0 });
  const b = voice("b");
  const { recommended, all } = voiceSections([a, b]);

  // Cung tham chieu -> chon o muc nao cung la cung mot voice, va khong co
  // trang thai thu hai nao de lech.
  assert.equal(recommended[0], a);
  assert.equal(all[0], a);
  assert.equal(all.length, 2, "muc day du phai chua ca giong de xuat");
});

test("giong chay tren may rieng duoc noi ro trong nhan", async () => {
  const { voiceOptionLabel } = await import("../src/lib/voices.ts");
  assert.match(
    voiceOptionLabel(voice("piper:ngochuyen", { runs_on_worker: true })),
    /máy riêng/,
  );
  assert.doesNotMatch(voiceOptionLabel(voice("edge:x")), /máy riêng/);
});

test("chi hien trang thai khi that su co van de", async () => {
  const { voiceOptionLabel } = await import("../src/lib/voices.ts");

  // Co van de -> phai noi ra.
  assert.match(
    voiceOptionLabel(
      voice("x", { status: "not_installed", status_label: "Chưa tải model" }),
    ),
    /Chưa tải model/,
  );

  // "unknown" la mac dinh cua MOI giong cho toi khi co probe that. Do tren
  // trinh duyet that: coi no la van de thi ca 27 dong deu duoi "Chưa kiểm tra",
  // mot dong nhieu lap 27 lan khong phan biet duoc giong nao that su hong.
  assert.doesNotMatch(
    voiceOptionLabel(
      voice("y", { status: "unknown", status_label: "Chưa kiểm tra" }),
    ),
    /Chưa kiểm tra/,
  );
  assert.doesNotMatch(
    voiceOptionLabel(voice("z", { status: "available", status_label: "Sẵn sàng" })),
    /Sẵn sàng/,
  );
});

test("hai trang deu co du hai muc chon giong", () => {
  for (const p of ["../src/app/studio/page.tsx", "../src/app/write/page.tsx"]) {
    const src = read(p);
    assert.match(src, /optgroup label={RECOMMENDED_LABEL}/, p);
    assert.match(src, /optgroup label={ALL_VOICES_LABEL}/, p);
    // MOT the `<select>` duy nhat -> chon o muc nay dong bo ngay voi muc kia,
    // khong co trang thai thu hai nao de lech. Dem THE DONG: chuoi "<select"
    // con xuat hien trong chinh ghi chu giai thich dieu nay.
    assert.equal(
      (src.match(/<\/select>/g) || []).length,
      1,
      `${p} phai chi co mot <select> chon giong`,
    );
  }
});
