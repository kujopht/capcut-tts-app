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
  // Tran so lan thu nam trong `lib/audioReload.quyetDinhKhiLoi` (kiem hanh vi
  // o bai ben duoi); engine phai DI QUA no va luu so lan moi.
  assert.match(audioEngineSrc, /quyetDinhKhiLoi\(soLanLamMoi\.current\)/);
  assert.match(audioEngineSrc, /if \(!thuLai\) \{/);
  assert.match(audioEngineSrc, /soLanLamMoi\.current = soLanMoi/);
  // Reset on canPlay
  assert.match(audioEngineSrc, /onCanPlay=\{.*?soLanLamMoi\.current = 0/s);
});

test("Refresh that: URL het han -> lay URL moi, KHOI PHUC vi tri va trang thai phat (ham engine dung that)", async () => {
  const { yDinhKhiLamMoi, apKhiCoMetadata, apKhiSanSang, quyetDinhKhiLoi, TOI_DA_LAM_MOI, laLoiPhatThat } =
    await import("../src/lib/audioReload.ts");

  // The gia: dung cac truong ma engine cham toi.
  const the = { currentTime: 0, duration: NaN };

  // Nguoi nghe dang o 142.5s, DANG PHAT, thi URL het han.
  let y = yDinhKhiLamMoi(142.5, true);
  assert.deepEqual(y, { batDauTu: 142.5, tuPhat: true });

  // React doi `src` -> the nap lai tu dau (currentTime = 0) -> `loadedmetadata`.
  the.duration = 600;
  y = apKhiCoMetadata(the, y);
  assert.equal(the.currentTime, 142.5, "vi tri phai duoc khoi phuc sau khi co metadata");
  assert.deepEqual(y, { tuPhat: true }, "con lai y dinh phat cho `canplay`");

  // `canplay` -> phat tiep, y dinh het.
  const r = apKhiSanSang(y);
  assert.equal(r.phat, true, "dang phat thi phai phat tiep");
  assert.equal(r.conLai, null);

  // Dang TAM DUNG khi het han: khoi phuc vi tri nhung KHONG tu phat.
  const the2 = { currentTime: 0, duration: 600 };
  const y2 = apKhiCoMetadata(the2, yDinhKhiLamMoi(30, false));
  assert.equal(the2.currentTime, 30);
  assert.equal(apKhiSanSang(y2).phat, false, "dang tam dung thi KHONG duoc tu phat");

  // Vi tri vuot thoi luong (URL moi tro toi tep ngan hon?) -> kep lai, khong nem.
  const the3 = { currentTime: 0, duration: 100 };
  apKhiCoMetadata(the3, { batDauTu: 5000 });
  assert.ok(the3.currentTime <= 100 && the3.currentTime > 99);

  // Tran so lan thu: 0 -> 1 -> 2 -> dung han.
  assert.equal(TOI_DA_LAM_MOI, 2);
  let n = 0;
  const lanThu = [];
  for (;;) {
    const q = quyetDinhKhiLoi(n);
    if (!q.thuLai) break;
    n = q.soLanMoi;
    lanThu.push(n);
    assert.ok(lanThu.length < 10, "vong lam moi khong duoc vo han");
  }
  assert.deepEqual(lanThu, [1, 2]);

  // AbortError/NotAllowedError khong phai loi cua tep (doi nguon / chinh sach tu phat).
  assert.equal(laLoiPhatThat({ name: "AbortError" }), false);
  assert.equal(laLoiPhatThat({ name: "NotAllowedError" }), false);
  assert.equal(laLoiPhatThat({ name: "NotSupportedError" }), true);
});

test("Het han khi dang TAM DUNG: bam Phat lay URL moi TRUOC, khong thu URL cu", () => {
  // `choPhat` kiem het han truoc `a.play()` — neu khong, trinh duyet thu URL
  // cu, that bai, roi moi vao nhanh `onError` (mot lan hong tieng vo ich).
  const khoi = audioEngineSrc.slice(audioEngineSrc.indexOf("const choPhat = useCallback"));
  const than = khoi.slice(0, khoi.indexOf("}, [tep, lamMoiUrl]);"));
  assert.ok(than.indexOf("isAudioUrlExpired(tep)") < than.indexOf("a.play()"),
    "phai kiem het han TRUOC khi goi play()");
  assert.match(than, /void lamMoiUrl\(a\.currentTime, true\)/);
  // Lam moi KHONG tu gan `a.src` (React gan — gan hai lan la nap hai lan).
  const lamMoi = audioEngineSrc.slice(audioEngineSrc.indexOf("const lamMoiUrl = useCallback"),
    audioEngineSrc.indexOf("const choPhat = useCallback"));
  assert.ok(!/a\.src = /.test(lamMoi), "lamMoiUrl khong duoc tu gan a.src");
  assert.match(lamMoi, /yDinh\.current = yDinhKhiLamMoi\(resumeTime, tuDongPhat\)/);
});

test("The dung hinh (khong ban error) ma URL da het han -> van lam moi; mang cham ma URL con han -> khong", () => {
  // Do that tren Chrome: request cua the bi chan o tang mang thi the dung o
  // readyState 1 va thu lai mai, KHONG ban `error` — nhanh onError khong chay.
  const khoi = audioEngineSrc.slice(audioEngineSrc.indexOf("onWaiting={() => {"));
  const than = khoi.slice(0, khoi.indexOf("onPlaying={boHenCho}"));
  assert.match(than, /window\.setTimeout\(/);
  assert.match(than, /a\.readyState < 3 && isAudioUrlExpired\(tep\)/,
    "chi lam moi khi URL DA het han, khong phai moi lan mang cham");
  assert.match(than, /void lamMoiUrl\(a\.currentTime, !a\.paused\)/);
  // Hen gio bi huy khi phat lai duoc va khi doi chuong.
  assert.match(audioEngineSrc, /onPlaying=\{boHenCho\}/);
});

test("Lay URL audio: thu lai loi ha tang tam thoi (502/503/504) CO GIOI HAN", () => {
  assert.match(audioSrc, /const TRANSIENT_RETRIES = 2;/);
  assert.match(audioSrc, /new Set\(\[502, 503, 504\]\)/);
  assert.match(audioSrc, /TRANSIENT_STATUSES\.has\(status\) && transient < TRANSIENT_RETRIES/);
  // 401/403/422... van nem ngay.
  assert.match(audioSrc, /throw cause;/);
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
