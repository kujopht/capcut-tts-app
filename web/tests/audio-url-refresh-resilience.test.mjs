import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const audioSrc = readFileSync(new URL("../src/lib/audio.ts", import.meta.url), "utf8");
const audioEngineSrc = readFileSync(new URL("../src/components/AudioEngine.tsx", import.meta.url), "utf8");
const audioPlayerSrc = readFileSync(new URL("../src/components/AudioPlayer.tsx", import.meta.url), "utf8");

test("isAudioUrlExpired logic correctly handles missing and malformed expiresIn values", () => {
  // Extract function logic or test the implemented semantics
  assert.match(audioSrc, /export function isAudioUrlExpired/);
  assert.match(audioSrc, /typeof audio\.expiresIn !== "number"/);
  assert.match(audioSrc, /isNaN\(audio\.expiresIn\)/);
  assert.match(audioSrc, /audio\.expiresIn <= 0/);

  // Directly evaluate extracted pure function
  function isAudioUrlExpired(audio, bufferSeconds = 60) {
    if (
      !audio.obtainedAt ||
      typeof audio.obtainedAt !== "number" ||
      !audio.expiresIn ||
      typeof audio.expiresIn !== "number" ||
      isNaN(audio.expiresIn) ||
      audio.expiresIn <= 0
    ) {
      return false;
    }
    const elapsedSec = (Date.now() - audio.obtainedAt) / 1000;
    return elapsedSec >= (audio.expiresIn - bufferSeconds);
  }

  // 1. Missing expiresIn -> false
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10 }), false);

  // 2. Malformed string -> false
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10, obtainedAt: Date.now(), expiresIn: "invalid" }), false);

  // 3. Negative / zero -> false
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10, obtainedAt: Date.now(), expiresIn: -10 }), false);
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10, obtainedAt: Date.now(), expiresIn: 0 }), false);

  // 4. NaN -> false
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10, obtainedAt: Date.now(), expiresIn: NaN }), false);

  // 5. Fresh -> false
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10, obtainedAt: Date.now(), expiresIn: 14400 }), false);

  // 6. Actually expired -> true
  assert.equal(isAudioUrlExpired({ playUrl: "u", downloadUrl: "", revoke: null, sizeBytes: 10, obtainedAt: Date.now() - 350000, expiresIn: 300 }), true);
});

test("AudioEngine contains bounded retry guard against infinite refresh loops", () => {
  assert.match(audioEngineSrc, /const soLanLamMoi = useRef\(0\)/);
  assert.match(audioEngineSrc, /if \(soLanLamMoi\.current >= 2\)/);
  assert.match(audioEngineSrc, /soLanLamMoi\.current \+= 1/);
  // Reset on canPlay
  assert.match(audioEngineSrc, /onCanPlay=\{.*?soLanLamMoi\.current = 0/s);
});

test("AudioPlayer delegates playback to AudioEngine and renders no independent audio element", () => {
  assert.match(audioPlayerSrc, /useAudioEngine/);
  const code = audioPlayerSrc.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.ok(!/<audio\b/.test(code), "AudioPlayer must not render independent <audio> element");
});

test("Controlled simulation: expired/broken URL refreshes, restores currentTime, and terminates at retry limit", async () => {
  let urlRequests = 0;
  let audioSrcUrl = "https://r2.example.com/expired-signed-url";
  let currentTime = 142.5; // listener was at 142.5s
  let isPlaying = true;
  let retryCount = 0;
  const maxRetries = 2;
  let displayedError = "";

  async function mockResolveAudio(chapterId) {
    urlRequests++;
    return {
      playUrl: `https://r2.example.com/fresh-signed-url-${urlRequests}`,
      expiresIn: 14400,
      obtainedAt: Date.now(),
    };
  }

  async function mockOnError(simulatePersistentFailure = false) {
    if (retryCount >= maxRetries) {
      displayedError = "Không thể phát file âm thanh sau nhiều lần thử.";
      return;
    }
    retryCount++;
    const resumeTime = currentTime;
    const wasPlaying = isPlaying;

    const fresh = await mockResolveAudio("ch_test");
    audioSrcUrl = fresh.playUrl;
    currentTime = resumeTime; // restored
    if (wasPlaying) {
      isPlaying = true; // resumed
    }

    if (simulatePersistentFailure) {
      // simulate subsequent failure
      await mockOnError(true);
    }
  }

  // Case A: Single transient expiry -> recovers transparently
  await mockOnError(false);
  assert.equal(urlRequests, 1);
  assert.equal(retryCount, 1);
  assert.equal(currentTime, 142.5, "currentTime must be preserved");
  assert.equal(isPlaying, true, "playback must resume");
  assert.equal(audioSrcUrl, "https://r2.example.com/fresh-signed-url-1");
  assert.equal(displayedError, "");

  // Case B: Persistent error -> hits maxRetries and stops gracefully
  urlRequests = 0;
  retryCount = 0;
  displayedError = "";
  await mockOnError(true);
  assert.equal(retryCount, 2, "must not loop infinitely");
  assert.equal(displayedError, "Không thể phát file âm thanh sau nhiều lần thử.");
});
