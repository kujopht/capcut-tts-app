"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useAudioEngineOptional } from "@/components/AudioEngine";
import { VIEW_H, VIEW_W } from "../core/constants";
import { hasProgress, type SaveData, type SaveSettings } from "../core/save";
import { peekSave, LocalStorageStore } from "../platform/storage";
import type { RuntimeHandle, UiSnapshot } from "../platform/runtime";
import { StageOverlay, formatTime } from "./StageOverlay";
import { TouchControls } from "./TouchControls";
import "./inkscout.css";

/**
 * Vỏ giao diện của Ink Scout: The Lost Chapter — thẻ chi tiết/khởi chạy → phần mở đầu → màn chơi toàn màn hình. Mã runtime (canvas, mô phỏng, âm thanh)
 * CHỈ được `import()` khi người chơi bấm Chơi/Tiếp tục: không nằm trong gói JS của trang chủ hay trang Giải trí. Rời trang → `destroy()` gỡ sạch.
 */
const PORTRAIT_URL = "/mascot/ink-scout/master/states/idle.webp";

const INTRO_PAGES: readonly string[] = [
  "Dưới tầng sâu nhất của Fanfic World là một Kho Lưu Trữ — nơi cất những câu chuyện mà chưa ai viết nốt.",
  "Gần đây, một thứ tên THE REDACTOR bắt đầu xoá chúng. Từng trang. Từng chương. Không để lại gì.",
  "Ink Scout, tay thám hiểm bé nhỏ của Kho, cầm Glyph Blade đi xuống tìm Chương Bị Mất. Câu hỏi chỉ có một: một câu chuyện chưa kết thúc… có còn đáng được tồn tại?",
];

type Phase = "menu" | "intro" | "stage" | "error";

function useCoarse(): boolean {
  const [coarse, setCoarse] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(pointer: coarse)");
    const qa = new URLSearchParams(window.location.search).get("touch") === "1";
    const upd = (): void => setCoarse(mq.matches || qa);
    upd();
    mq.addEventListener?.("change", upd);
    return () => mq.removeEventListener?.("change", upd);
  }, []);
  return coarse;
}

async function patchSettings(patch: Partial<SaveSettings>): Promise<SaveData | null> {
  const store = new LocalStorageStore();
  const cur = (await store.load()) ?? (await import("../core/save")).defaultSave();
  cur.settings = { ...cur.settings, ...patch };
  await store.save(cur);
  return cur;
}

export default function InkScoutShell() {
  const engine = useAudioEngineOptional();
  const coarse = useCoarse();
  const [phase, setPhase] = useState<Phase>("menu");
  const [introPage, setIntroPage] = useState(0);
  const [launch, setLaunch] = useState<{ newGame: boolean } | null>(null);
  const [ready, setReady] = useState(false);
  const [ui, setUi] = useState<UiSnapshot | null>(null);
  // Vỏ này chỉ chạy trên trình duyệt (`ssr:false`), nên đọc localStorage ngay ở trạng thái khởi tạo là an toàn.
  const [menuSave, setMenuSave] = useState<SaveData | null>(() => (typeof window === "undefined" ? null : peekSave()));
  const [confirmNew, setConfirmNew] = useState(false);
  const [size, setSize] = useState({ w: VIEW_W, h: VIEW_H, scale: 1, portrait: false });
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const rtRef = useRef<RuntimeHandle | null>(null);
  const newGameRef = useRef(false);
  const [rt, setRt] = useState<RuntimeHandle | null>(null);

  // Khoá cuộn trang khi đang ở màn chơi/mở đầu; luôn mở khoá khi rời.
  useEffect(() => {
    if (phase !== "intro" && phase !== "stage") return;
    const root = document.documentElement;
    root.classList.add("isc-lock");
    document.body.classList.add("isc-lock");
    return () => {
      root.classList.remove("isc-lock");
      document.body.classList.remove("isc-lock");
    };
  }, [phase]);

  const pauseNarration = useCallback(() => {
    if (engine?.trangThai.dangPhat) engine.dieuKhien.tamDung();
  }, [engine]);

  // Tạo/huỷ runtime theo `launch`.
  useEffect(() => {
    if (!launch) return;
    let cancelled = false;
    let handle: RuntimeHandle | null = null;
    (async () => {
      const { createRuntime } = await import("../platform/runtime");
      if (cancelled || !canvasRef.current) return;
      handle = await createRuntime({
        canvas: canvasRef.current,
        store: new LocalStorageStore(),
        onUi: (s) => {
          if (!cancelled) setUi(s);
        },
        newGame: launch.newGame,
        portraitUrl: PORTRAIT_URL,
      });
      if (cancelled) {
        handle.destroy();
        return;
      }
      rtRef.current = handle;
      handle.unlockAudio();
      setRt(handle);
      setReady(true);
    })().catch(() => {
      if (!cancelled) setPhase("error");
    });
    return () => {
      cancelled = true;
      handle?.destroy();
      rtRef.current = null;
      setRt(null);
      setReady(false);
      setUi(null);
    };
  }, [launch]);

  // Co canvas theo vùng trống; số nguyên khi ≥ 2× để điểm ảnh sắc nét.
  useLayoutEffect(() => {
    if (phase !== "stage") return;
    const el = wrapRef.current;
    if (!el) return;
    const measure = (): void => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w <= 0 || h <= 0) return;
      let s = Math.min(w / VIEW_W, h / VIEW_H);
      if (s >= 2) s = Math.floor(s);
      setSize({ w: Math.round(VIEW_W * s), h: Math.round(VIEW_H * s), scale: s, portrait: window.innerHeight > window.innerWidth });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("orientationchange", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("orientationchange", measure);
    };
  }, [phase]);

  const startPlay = useCallback(
    (newGame: boolean) => {
      pauseNarration();
      setConfirmNew(false);
      setReady(false);
      const saved = peekSave();
      const needIntro = newGame || !saved || !hasProgress(saved);
      if (needIntro) {
        setIntroPage(0);
        setPhase("intro");
        setLaunch(null);
        newGameRef.current = newGame;
      } else {
        setPhase("stage");
        setLaunch({ newGame: false });
      }
    },
    [pauseNarration],
  );

  const beginAfterIntro = useCallback(() => {
    setPhase("stage");
    setLaunch({ newGame: newGameRef.current });
  }, []);

  const quit = useCallback(() => {
    setLaunch(null);
    setPhase("menu");
    setMenuSave(peekSave());
  }, []);

  // Một đối tượng `launch` mới ⇒ hiệu ứng huỷ runtime cũ rồi dựng runtime mới (không bao giờ có hai thể hiện).
  const restart = useCallback(() => {
    setLaunch({ newGame: true });
  }, []);

  const tapConfirm = useCallback(() => {
    const r = rtRef.current;
    if (!r) return;
    r.input.press("confirm", 9001);
    window.setTimeout(() => r.input.release("confirm", 9001), 90);
  }, []);

  // Lựa chọn cuối không thể hoàn tác: chạm lần đầu chỉ CHỌN (kể cả lựa chọn đang sáng sẵn), chạm lần hai vào cùng lựa chọn mới xác nhận.
  const armedRef = useRef<0 | 1 | null>(null);
  const choose = useCallback(
    (i: 0 | 1) => {
      const r = rtRef.current;
      if (!r) return;
      if (armedRef.current === i) {
        armedRef.current = null;
        tapConfirm();
      } else {
        armedRef.current = i;
        r.game.endingChoice = i;
      }
    },
    [tapConfirm],
  );

  const changeMenuSettings = useCallback(async (patch: Partial<SaveSettings>) => {
    setMenuSave(await patchSettings(patch));
  }, []);

  // ===================================================================== MENU
  if (phase === "menu" || phase === "error") {
    const prog = menuSave && hasProgress(menuSave) ? menuSave : null;
    const settings = menuSave?.settings ?? { shake: 1, muted: false };
    return (
      <div className="page stack-3 isc-menu" data-hero-theme="animation">
        <nav aria-label="Điều hướng" className="isc-crumb">
          <Link href="/entertainment" prefetch={false} className="btn btn-ghost btn-sm">← Về Giải trí</Link>
        </nav>
        <header className="isc-hero">
          <div className="isc-hero-art" aria-hidden="true">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={PORTRAIT_URL} alt="" width={160} height={160} decoding="async" />
          </div>
          <div className="isc-hero-copy">
            <p className="isc-eyebrow">ACTION METROIDVANIA · CHƯƠNG 0</p>
            <h1 className="isc-title">Ink Scout: The Lost Chapter</h1>
            <p className="isc-lead">Xuống Kho Lưu Trữ bị lãng quên dưới Fanfic World, gom ba Mảnh Ký Ức và đối mặt với The Redactor — kẻ xoá mọi thứ chưa hoàn chỉnh.</p>
            <div className="isc-cta">
              {prog ? (
                <>
                  <button type="button" className="btn btn-primary" onClick={() => startPlay(false)}>▶ Tiếp tục</button>
                  <button type="button" className="btn btn-secondary" onClick={() => setConfirmNew(true)}>Chơi lại từ đầu</button>
                </>
              ) : (
                <button type="button" className="btn btn-primary" onClick={() => startPlay(true)}>▶ Chơi</button>
              )}
            </div>
            {confirmNew ? (
              <div className="isc-confirm" role="alertdialog" aria-label="Xác nhận chơi lại">
                <p>Chơi lại sẽ xoá tiến trình đã lưu của game này trên trình duyệt (cài đặt và thời gian nhanh nhất được giữ). Tiếp tục?</p>
                <div className="isc-row">
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => startPlay(true)}>Xoá và chơi lại</button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmNew(false)}>Giữ tiến trình</button>
                </div>
              </div>
            ) : null}
            {prog ? (
              <p className="hint isc-progress">
                Đã lưu: {prog.memories.length}/3 Ký Ức{prog.marginStep ? " · có Margin Step" : ""}
                {prog.ending ? ` · đã thấy kết thúc "${prog.ending === "basic" ? "cơ bản" : prog.ending === "erase" ? "XOÁ" : "KHÔI PHỤC"}"` : ""}
                {prog.bestFrames ? ` · nhanh nhất ${formatTime(prog.bestFrames)}` : ""}
              </p>
            ) : null}
            {phase === "error" ? <p className="isc-error" role="alert">Không khởi động được game trên trình duyệt này. Thử tải lại trang.</p> : null}
          </div>
        </header>

        <section className="card isc-info" aria-label="Thông tin">
          <dl className="gt-meta">
            <div><dt>Chế độ</dt><dd>Chơi đơn</dd></div>
            <div><dt>Thời lượng</dt><dd>~20–35 phút</dd></div>
            <div><dt>Lưu</dt><dd>Trên trình duyệt này</dd></div>
            <div><dt>Phần thưởng</dt><dd>Không tính XP</dd></div>
          </dl>
        </section>

        <section className="card isc-info stack-2" aria-labelledby="isc-ctl">
          <h2 className="section-title" id="isc-ctl">Điều khiển</h2>
          <div className="isc-ctl-grid">
            <div>
              <h3 className="isc-h3">Bàn phím</h3>
              <ul className="isc-keys">
                <li><kbd>←</kbd> <kbd>→</kbd> hoặc <kbd>A</kbd> <kbd>D</kbd> — đi</li>
                <li><kbd>Space</kbd> — nhảy (giữ lâu nhảy cao hơn)</li>
                <li><kbd>J</kbd> — chém (bấm 3 lần liên tiếp để ra combo)</li>
                <li><kbd>K</kbd> — Memory Pulse (tốn 3 Ink; Ink tích khi chém trúng)</li>
                <li><kbd>Shift</kbd> — Margin Step (sau khi nhận được)</li>
                <li><kbd>Esc</kbd> — tạm dừng</li>
              </ul>
            </div>
            <div>
              <h3 className="isc-h3">Cảm ứng</h3>
              <ul className="isc-keys">
                <li>Vùng trái: chạm và trượt ◀ ▶ để đi</li>
                <li>⤒ nhảy · ⚔ chém · ✦ Memory Pulse · ⇢ Margin Step</li>
                <li>Nên xoay ngang màn hình để chơi thoải mái hơn</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="card isc-info stack-2" aria-labelledby="isc-set">
          <h2 className="section-title" id="isc-set">Cài đặt</h2>
          <div className="isc-row isc-row-wrap">
            <span className="isc-label" id="isc-m-shake">Rung màn hình</span>
            <div role="radiogroup" aria-labelledby="isc-m-shake" className="isc-seg">
              {([[0, "Tắt"], [0.5, "Nhẹ"], [1, "Đủ"]] as const).map(([v, l]) => (
                <button key={v} type="button" role="radio" aria-checked={settings.shake === v} className="isc-seg-b" onClick={() => void changeMenuSettings({ shake: v })}>{l}</button>
              ))}
            </div>
          </div>
          <div className="isc-row isc-row-wrap">
            <span className="isc-label" id="isc-m-snd">Âm thanh</span>
            <div role="radiogroup" aria-labelledby="isc-m-snd" className="isc-seg">
              <button type="button" role="radio" aria-checked={!settings.muted} className="isc-seg-b" onClick={() => void changeMenuSettings({ muted: false })}>Bật</button>
              <button type="button" role="radio" aria-checked={settings.muted} className="isc-seg-b" onClick={() => void changeMenuSettings({ muted: true })}>Tắt</button>
            </div>
          </div>
          <p className="hint">Hình ảnh trong game là sprite tạm do mã vẽ (đồ hoạ nguyên bản, sẽ được thay bằng bản hoàn thiện). Âm thanh tổng hợp bằng Web Audio, không dùng tệp có bản quyền.</p>
        </section>
      </div>
    );
  }

  // ===================================================================== MỞ ĐẦU
  if (phase === "intro") {
    const last = introPage >= INTRO_PAGES.length - 1;
    return (
      <div className="isc-stage isc-intro" role="dialog" aria-modal="true" aria-label="Mở đầu">
        <div className="isc-intro-box">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={PORTRAIT_URL} alt="" width={120} height={120} className="isc-intro-art" decoding="async" />
          <p className="isc-line isc-big">{INTRO_PAGES[introPage]}</p>
          <div className="isc-row">
            <button type="button" className="isc-btn isc-btn-primary" autoFocus onClick={() => (last ? beginAfterIntro() : setIntroPage((p) => p + 1))}>
              {last ? "Xuống Kho ▶" : "Tiếp →"}
            </button>
            {last ? null : <button type="button" className="isc-btn" onClick={beginAfterIntro}>Bỏ qua</button>}
            <button type="button" className="isc-btn" onClick={quit}>Quay lại</button>
          </div>
          <p className="isc-tap">{introPage + 1}/{INTRO_PAGES.length}</p>
        </div>
      </div>
    );
  }

  // ===================================================================== MÀN CHƠI
  return (
    <div className="isc-stage" data-portrait={size.portrait ? "true" : "false"} data-testid="isc-stage">
      <div className="isc-wrap" ref={wrapRef}>
        <div className="isc-view" style={{ width: size.w, height: size.h, ["--u" as string]: `${size.scale}px` }} data-testid="isc-view">
          <canvas ref={canvasRef} className="isc-canvas" width={VIEW_W} height={VIEW_H} role="img" aria-label="Màn hình game Ink Scout: The Lost Chapter" data-testid="isc-canvas" />
          {ui && ready ? (
            <StageOverlay
              ui={ui}
              coarse={coarse}
              onTap={tapConfirm}
              onResume={() => rt?.resume()}
              onQuit={quit}
              onShake={(v) => rt?.setShake(v)}
              onMute={(m) => rt?.setMuted(m)}
              onChoose={choose}
              onRestart={restart}
            />
          ) : null}
          {ready && ui && ui.saveFailed ? <div className="isc-savefail" role="status">Không lưu được tiến trình (trình duyệt chặn lưu trữ).</div> : null}
          {!ready ? <div className="isc-loading" role="status">Đang tải…</div> : null}
          {ready && !coarse ? (
            <button type="button" className="isc-pause-btn" aria-label="Tạm dừng (Esc)" onClick={() => rt?.pause()}>
              ❚❚
            </button>
          ) : null}
        </div>
      </div>
      {coarse && ready && rt && ui && !ui.paused && (ui.mode === "play" || ui.mode === "dead") ? <TouchControls input={rt.input} marginStep={ui.marginStep} onPause={() => rt.pause()} /> : null}
      {coarse && size.portrait ? <p className="isc-orient" style={{ top: size.h + 6 }}>Xoay ngang màn hình để chơi thoải mái hơn.</p> : null}
    </div>
  );
}
