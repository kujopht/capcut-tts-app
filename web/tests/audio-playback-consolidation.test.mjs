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
  const eng = audioEngine();
  assert.match(eng, /musicStore\.pause\(\)/, "AudioEngine phai pause ambient music khi bat dau phat");
});

test("Audio Consolidation: Giu nguyen nut Tai MP3 va dinh danh file tieu chuan", () => {
  const ply = audioPlayer();
  assert.match(ply, /download=\{audioFileName\(title\)\}/, "Phai giu nguyen ten file MP3 hop le");
  assert.match(ply, /Tải MP3/, "Phai co nut Tai MP3");
});
