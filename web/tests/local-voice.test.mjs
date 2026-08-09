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

test("giao dien KHONG con gia dinh worker chay tren may nguoi dung", () => {
  // Production chay worker 24/7 tren Google Compute Engine. Moi cau con noi
  // "máy riêng" / "máy đang tắt" / "khi máy bật lại" deu la tan du cua thoi
  // worker chay tren laptop, va deu goi y sai rang nguoi dung phai co may cua
  // rieng ho. Quet CA HAI tep vi ca hai deu tung noi cau do.
  for (const p of ["../src/app/studio/page.tsx", "../src/app/layout.tsx"]) {
    const src = read(p);
    for (const cam of ["máy riêng", "máy đang tắt", "khi máy bật lại"]) {
      assert.ok(!src.includes(cam), `${p} còn câu "${cam}"`);
    }
  }
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
  provider: voice_id.split(":")[0],
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

test("nhan giong NghiTTS CHI la ten, khong hau to gi", async () => {
  const { voiceOptionLabel } = await import("../src/lib/voices.ts");

  // Truong hop kho nhat co the dung: may chu gui DU metadata — ten bo giong,
  // co worker, nhan trang thai. Khong manh nao duoc lot vao ten hien thi.
  const nhan = voiceOptionLabel(
    voice("piper:banmai", {
      display_name: "Ban Mai",
      provider_label: "NghiTTS",
      runs_on_worker: true,
      status: "worker",
      status_label: "Chạy trên máy chủ",
    }),
  );
  assert.equal(nhan, "Ban Mai");
  for (const cam of [
    "NghiTTS",
    "Piper",
    "Piper local",
    "máy riêng",
    "Chạy trên máy chủ",
    "Chưa tải model",
    "·",
  ]) {
    assert.ok(!nhan.includes(cam), `nhãn còn chứa "${cam}"`);
  }
});

test("ke ca khi may chu gui trang thai hong, nhan NghiTTS van chi la ten", async () => {
  // `status_of()` khong con duoc goi cho giong worker, nhung mot ban may chu
  // cu (chua deploy) VAN gui "not_installed" / "Chưa tải model". Giao dien
  // khong duoc hien no ra: model nam tren may chu tong hop, khong phai may
  // nguoi dung.
  const { voiceOptionLabel } = await import("../src/lib/voices.ts");
  const nhan = voiceOptionLabel(
    voice("piper:maiphuong", {
      display_name: "Mai Phương",
      provider_label: "Piper local",
      runs_on_worker: true,
      installed: false,
      status: "not_installed",
      status_label: "Chưa tải model",
    }),
  );
  assert.equal(nhan, "Mai Phương");
});

test("CapCut va Edge VAN giu ten bo giong trong nhan", async () => {
  // Co chu dich, khong phai bo sot. Hai ben co giong TRUNG TEN nhau — chinh
  // su trung ten do tung lam trang web chon nham mot giong CapCut khi di tim
  // giong Edge "HoaiMy". Bo hau to o day la lam hai dong trong y het nhau.
  const { voiceOptionLabel } = await import("../src/lib/voices.ts");
  assert.equal(
    voiceOptionLabel(
      voice("edge:vi-VN-HoaiMyNeural", {
        display_name: "Hoài My",
        provider_label: "Edge TTS",
      }),
    ),
    "Hoài My · Edge TTS",
  );
  assert.equal(
    voiceOptionLabel(
      voice("capcut:x", { display_name: "Hoài My", provider_label: "CapCut" }),
    ),
    "Hoài My · CapCut",
  );
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

/* ------------------------------- kiem tren BAN CHUP THAT cua /api/voices */

/**
 * `voices-production.json` la ban chup `/api/voices` voi dung 25 giong ma
 * production dang bat. `server/tests/test_nghitts_web_labels.py` khoa cho no
 * khong troi khoi may chu.
 *
 * Cac test o tren dung `voice()` bia dat — tien de doc, nhung chung chi kiem
 * duoc thu ma nguoi viet test nghi ra. Phan nay chay tren du lieu THAT.
 */
const FIXTURE = JSON.parse(read("./fixtures/voices-production.json"));

const TEN_CHINH_THUC = {
  "piper:adam1": "Adam",
  "piper:banmai": "Ban Mai",
  "piper:calmwoman3688": "Nữ Điềm Đạm",
  "piper:chieuthanh": "Chiêu Thanh",
  "piper:deepman3909": "Nam Trầm",
  "piper:duyoryx3175": "Duy Oryx",
  "piper:lacphi": "Lạc Phi",
  "piper:maiphuong": "Mai Phương",
  "piper:manhdung": "Mạnh Dũng",
  "piper:minhkhang": "Minh Khang",
  "piper:minhquang": "Minh Quang",
  "piper:minhthu": "Minh Thư",
  "piper:mytam2": "Mỹ Tâm 1",
  "piper:mytam2794": "Mỹ Tâm 2",
  "piper:ngochuyen": "Ngọc Huyền",
  "piper:ngochuyennew": "Ngọc Huyền (Mới)",
  "piper:ngocngan3701": "Ngọc Ngân",
  "piper:phuongtrang": "Phương Trang",
  "piper:taian2": "Tài An 1",
  "piper:taian4": "Tài An 2",
  "piper:thanhphuong2": "Thanh Phương",
  "piper:thientam": "Thiên Tâm",
  "piper:tranthanh3870": "Trần Thanh",
  "piper:vietthao3886": "Việt Thảo",
  "piper:yannew": "Yan (Mới)",
};

test("fixture production: 24 CapCut + 2 Edge + 25 NghiTTS = 51", () => {
  const dem = {};
  for (const v of FIXTURE) dem[v.provider] = (dem[v.provider] ?? 0) + 1;
  assert.deepEqual(dem, { capcut: 24, edge: 2, piper: 25 });
  assert.equal(FIXTURE.length, 51);
});

test("fixture production: du 25 voice_id piper, dung bang ten", () => {
  const piper = Object.fromEntries(
    FIXTURE.filter((v) => v.provider === "piper").map((v) => [
      v.voice_id,
      v.display_name,
    ]),
  );
  assert.deepEqual(piper, TEN_CHINH_THUC);
});

test("fixture production: moi nhan NghiTTS chi la ten, khong hau to", async () => {
  const { voiceOptionLabel, voiceSections } = await import(
    "../src/lib/voices.ts"
  );
  const { all } = voiceSections(FIXTURE);
  assert.equal(all.length, 51, "không giọng nào bị lọc mất");

  for (const v of all.filter((x) => x.provider === "piper")) {
    const nhan = voiceOptionLabel(v);
    assert.equal(nhan, TEN_CHINH_THUC[v.voice_id]);
    for (const cam of [
      "NghiTTS",
      "Piper",
      "piper",
      "máy riêng",
      "Chưa tải model",
      "Chạy trên máy chủ",
    ]) {
      assert.ok(!nhan.includes(cam), `"${nhan}" còn chứa "${cam}"`);
    }
  }
});

test("fixture production: CapCut va Edge khong mat giong nao", async () => {
  const { voiceSections } = await import("../src/lib/voices.ts");
  const { all } = voiceSections(FIXTURE);
  assert.equal(all.filter((v) => v.provider === "capcut").length, 24);
  assert.equal(all.filter((v) => v.provider === "edge").length, 2);
});

test("fixture production: metadata provider VAN con trong API", () => {
  // Bo ten bo giong khoi NHAN HIEN THI la viec cua giao dien. API van phai
  // bao ra metadata — day la ranh gioi giua hai tang.
  for (const v of FIXTURE.filter((x) => x.provider === "piper")) {
    assert.equal(v.provider_label, "NghiTTS", v.voice_id);
    assert.equal(v.runs_on_worker, true, v.voice_id);
  }
});

/* --------------------------------------- KHONG con muc rieng cho NghiTTS */

test("voiceSections chi tra ve HAI muc", async () => {
  const { voiceSections } = await import("../src/lib/voices.ts");
  const { recommended, all, ...thua } = voiceSections([voice("edge:x")]);
  assert.ok(recommended && all);
  assert.deepEqual(
    Object.keys(thua),
    [],
    "còn mục thừa — mục NghiTTS riêng đã bị bỏ",
  );
});

test("giong NghiTTS nam trong 'Tat ca' nhu moi provider khac", async () => {
  const { voiceSections } = await import("../src/lib/voices.ts");

  const vs = [
    voice("piper:ngochuyen", { runs_on_worker: true, installed: false }),
    voice("piper:banmai", { runs_on_worker: true, installed: false }),
    voice("edge:vi-VN-HoaiMyNeural"),
    voice("capcut:BV074_streaming"),
  ];
  const { all } = voiceSections(vs);
  assert.deepEqual(
    all.map((v) => v.voice_id),
    vs.map((v) => v.voice_id),
    "mục đầy đủ phải giữ đủ 4 giọng, đúng thứ tự máy chủ trả về",
  );
});

test("NghiTTS duoc de xuat thi vao muc de xuat nhu provider khac", async () => {
  const { voiceSections } = await import("../src/lib/voices.ts");

  const vs = [
    voice("edge:x", { recommended: true, recommended_order: 1 }),
    voice("piper:ngochuyen", {
      runs_on_worker: true,
      installed: false,
      recommended: true,
      recommended_order: 0,
    }),
  ];
  const { recommended } = voiceSections(vs);
  assert.deepEqual(
    recommended.map((v) => v.voice_id),
    ["piper:ngochuyen", "edge:x"],
    "thứ tự do máy chủ cấp, không ưu tiên/hạ bậc theo provider",
  );
});

test("hai trang deu co dung HAI muc chon giong", () => {
  for (const p of ["../src/app/studio/page.tsx", "../src/app/write/page.tsx"]) {
    const src = read(p);
    assert.match(src, /optgroup label={RECOMMENDED_LABEL}/, p);
    assert.match(src, /optgroup label={ALL_VOICES_LABEL}/, p);
    // Dem THE DONG, khong dem the mo: chuoi "<optgroup" con xuat hien trong
    // chinh ghi chu giai thich viec bo muc thu ba.
    assert.equal(
      (src.match(/<\/optgroup>/g) || []).length,
      2,
      `${p} phải có đúng hai optgroup`,
    );
    assert.ok(
      !src.includes("NGHITTS_LABEL"),
      `${p} còn optgroup NghiTTS riêng`,
    );
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
