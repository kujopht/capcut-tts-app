/**
 * Kiem dinh hop nhat trang thai audio (Audio Playback State Consolidation).
 *
 * Yeu cau:
 * 1. CHI CO MOT the <audio> duy nhat trong toan bo he thong (tai AudioEngineProvider trong layout).
 * 2. AudioPlayer.tsx la UI/controller tieu thu useAudioEngine(), KHONG duoc tu tao the <audio>.
 * 3. SoundwaveVisualizer chi ve tren canvas hoac style bars, khong tu tao audio stream doc lap.
 * 4. AudioEngine tu dong tam dung nhac nen khi phat loi thoai de tranh chong cheo am thanh.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const audioEngine = () => read("../src/components/AudioEngine.tsx");
const audioPlayer = () => read("../src/components/AudioPlayer.tsx");
const soundwave = () => read("../src/components/SoundwaveVisualizer.tsx");
const layout = () => read("../src/app/layout.tsx");

test("Audio Consolidation: The <audio> DUY NHAT nam o AudioEngineProvider trong layout", () => {
  const lay = layout();
  assert.match(lay, /<AudioEngineProvider>/, "Layout phai boc toan bo ung dung trong AudioEngineProvider");

  const eng = audioEngine();
  assert.match(eng, /<audio[\s\S]+?ref=\{el\}/, "AudioEngine phai so huu the <audio>");

  const ply = audioPlayer();
  assert.ok(!/<audio[\s\r\n]+[a-zA-Z]/.test(ply), "AudioPlayer KHONG duoc phep render the <audio> JSX");
});

test("Audio Consolidation: AudioPlayer tieu thu useAudioEngine de dong bo trang thai", () => {
  const ply = audioPlayer();
  assert.match(ply, /useAudioEngine\(\)/, "AudioPlayer phai goi useAudioEngine()");
  assert.match(ply, /engine\.dieuKhien\.batTat\(\)/, "AudioPlayer phai dieu khien bat/tat qua engine");
  assert.match(ply, /engine\.dieuKhien\.tua\(/, "AudioPlayer phai tua thoi gian qua engine");
  assert.match(ply, /engine\.dieuKhien\.phat\(/, "AudioPlayer phai kich hoat phat qua engine");
});

test("Audio Consolidation: SoundwaveVisualizer la visualization-only, khong tao audio element", () => {
  const snd = soundwave();
  assert.ok(!/<audio\b/.test(snd), "SoundwaveVisualizer khong duoc chua the <audio>");
  assert.match(snd, /canvasRef/, "SoundwaveVisualizer phai ve tren canvas");
  assert.match(snd, /requestAnimationFrame/, "Visualizer cap nhat animation frame muot ma");
});

test("Audio Consolidation: AudioEngine tu dong tam dung nhac ambient khi phat chuong", () => {
  /*
    Sprint doc/nghe 2026-09-24: engine khong goi thang `musicStore.pause()`
    nua — no bao "giong doc giu tieng" cho bo dieu phoi (`lib/audioFocus.ts`),
    va nhac nen dang ky la kenh uu tien thap voi hanh vi "pause". Hanh vi
    nguoi dung thay KHONG doi; hanh vi that duoc kiem o `audio-focus.test.mjs`.
  */
  const eng = audioEngine();
  assert.match(eng, /audioFocus\.yeuCau\("narration"\)/, "AudioEngine phai xin quyen tieng khi phat");
  assert.match(eng, /audioFocus\.traLai\("narration"\)/, "AudioEngine phai tra quyen tieng khi dung");
  assert.ok(!/musicStore/.test(eng.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")),
    "dong co truyen khong duoc biet ve mot kho nhac cu the");
  const nhac = read("../src/lib/musicStore.ts");
  assert.match(nhac, /audioFocus\.dangKy\("ambient"/, "nhac nen phai dang ky kenh ambient");
  assert.match(nhac, /musicStore\.pause\(\)/, "kenh ambient phai tam dung khi bi cat");
});

test("Audio Consolidation: Giu nguyen nut Tai MP3 va dinh danh file tieu chuan", () => {
  const ply = audioPlayer();
  assert.match(ply, /download=\{audioFileName\(title\)\}/, "Phai giu nguyen ten file MP3 hop le");
  assert.match(ply, /Tải MP3/, "Phai co nut Tai MP3");
});
