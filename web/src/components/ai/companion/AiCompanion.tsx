"use client";

/**
 * Ink Scout — linh vật đi cùng Trợ lý AI (`docs/ai/INK_SCOUT_COMPANION.md`).
 *
 * Bọc runtime ĐÃ DUYỆT `ink-scout.js` (không viết lại engine): tạo MỘT instance
 * cho mỗi lần mount, `destroy()` khi unmount; trạng thái lấy từ `AiProvider`
 * qua hàm thuần `mapCompanionState`; di chuyển/trạng thái đi qua
 * `CompanionDirector` (mới nhất thắng, không cắt ngang chuyển động).
 *
 * Hai biến thể:
 *   * `floating` — desktop ≥1024px, cạnh nút mở trợ lý. Panel mở → nhảy lên mép
 *     TRÊN panel (ngoài panel: không che chữ/nút Gửi/nút Đóng), ngồi khi chỉ lắng
 *     nghe, đứng dậy khi làm việc; panel đóng → đứng dậy + về nhà. Không đủ chỗ
 *     an toàn dưới navbar → ẩn trong lúc panel mở. Không đi lang thang.
 *   * `inline` — trong trang `/assistant` (mọi bề rộng): nằm TRONG luồng nội dung
 *     nên không bao giờ đè lên ô soạn; bàn phím ảo mở (viewport thấp) → thu lại.
 *
 * Không bao giờ: phát âm thanh, nhận focus bàn phím (host `aria-hidden`, không
 * tabindex), bắt con trỏ ngoài chính nó (`pointer-events` chỉ bật ở vị trí nhà),
 * tự mở trợ lý, lật ngang nhân vật (không `scaleX(-1)` ở đâu cả).
 */
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "@/lib/session";
import { useAi } from "../AiProvider";
import { useChatDockOffset } from "../useChatDockOffset";
import { mapCompanionState } from "./companionState";
import { CompanionDirector } from "./companionDirector";
import { boundsFor, computeSeat, type Rect } from "./companionGeometry";
import { INK_SCOUT_BASE, loadInkScout, type InkScoutRuntime } from "./inkScoutLoader";
import { useCompanionPrefs, useSystemReducedMotion } from "./companionPrefs";

export type CompanionVariant = "floating" | "inline";

const SIZE_FLOATING = 96;
const SIZE_INLINE_DESKTOP = 88;
const SIZE_INLINE_MOBILE = 72;
/** Tuyến có điều khiển riêng ở góc dưới (trình đọc, tin nhắn) — linh vật không đứng "nhà" ở đó. */
const HIDE_HOME_ON = [/^\/chapters\//, /^\/messages(\/|$)/];

function useMedia(query: string): boolean {
  const [v, setV] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setV(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return v;
}

function useNetworkOffline(): boolean {
  const [off, setOff] = useState(false);
  useEffect(() => {
    const on = () => setOff(navigator.onLine === false);
    on();
    window.addEventListener("online", on);
    window.addEventListener("offline", on);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", on);
    };
  }, []);
  return off;
}

/** Bàn phím ảo mở ở `/assistant` di động: viewport nhìn thấy thấp hơn nhiều so với cửa sổ. */
function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const on = () => setOpen(vv.height < window.innerHeight * 0.72);
    on();
    vv.addEventListener("resize", on);
    return () => vv.removeEventListener("resize", on);
  }, []);
  return open;
}

function rectOf(el: Element): Rect {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
}

export function AiCompanion({ variant }: { variant: CompanionVariant }) {
  const ai = useAi();
  const { profile } = useSession();
  const pathname = usePathname();
  const [prefs] = useCompanionPrefs();
  const systemReduced = useSystemReducedMotion();
  const isDesktop = useMedia("(min-width: 1024px)");
  const networkOffline = useNetworkOffline();
  const keyboardOpen = useKeyboardOpen();
  const dockOffset = useChatDockOffset();

  const hostRef = useRef<HTMLDivElement | null>(null);
  const rtRef = useRef<InkScoutRuntime | null>(null);
  const dirRef = useRef<CompanionDirector | null>(null);
  const [ready, setReady] = useState(false);
  const [wanted, setWanted] = useState(false);
  const [hovering, setHovering] = useState(false);
  const [flash, setFlash] = useState<"success" | null>(null);
  const [noSeat, setNoSeat] = useState(false);

  const available = ai.availability === null ? null : !!(ai.availability && ai.availability.enabled);
  const onAssistantPage = pathname === "/assistant";
  const open = variant === "inline" ? true : ai.open;
  const reduced = prefs.reducedMotion || systemReduced;
  const size = variant === "floating" ? SIZE_FLOATING : isDesktop ? SIZE_INLINE_DESKTOP : SIZE_INLINE_MOBILE;

  // CÙNG điều kiện với `AiLauncher`: `availability` chỉ được xin khi người dùng mở
  // trợ lý, nên trước đó nó là `null` (chưa biết) — linh vật vẫn đứng cạnh nút mở
  // (trạng thái idle, KHÔNG kết luận offline); máy chủ báo tắt → ẩn như nút.
  const launcherVisible = ai.availability !== false && !(ai.availability && !ai.availability.enabled);
  const mounted =
    ai.enabled && !!profile && !prefs.hidden &&
    (variant === "inline" ? onAssistantPage : isDesktop && !onAssistantPage && launcherVisible);

  const hiddenAtHome = variant === "floating" && !ai.open && HIDE_HOME_ON.some((re) => re.test(pathname));
  const visible = mounted && !hiddenAtHome && !(variant === "floating" && ai.open && noSeat) &&
    !(variant === "inline" && keyboardOpen);

  // ---- nạp LƯỜI: panel mở / đang ở /assistant → ngay; chỉ đứng "nhà" → khi trình duyệt rảnh.
  const needNow = variant === "inline" || ai.open;
  const load = mounted && (wanted || needNow);
  useEffect(() => {
    if (!mounted || wanted || needNow) return;
    const w = window as unknown as {
      requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setWanted(true), { timeout: 4000 });
      return () => w.cancelIdleCallback?.(id);
    }
    const t = window.setTimeout(() => setWanted(true), 2500);
    return () => window.clearTimeout(t);
  }, [mounted, wanted, needNow]);

  // ---- tạo MỘT instance; huỷ khi unmount / bị ẩn hẳn (tuỳ chọn "Ẩn").
  useEffect(() => {
    if (!load) return;
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    loadInkScout()
      .then(({ Ctor, manifest }) => {
        if (cancelled || !hostRef.current) return;
        const rt = new Ctor(hostRef.current, { manifest, assetBase: INK_SCOUT_BASE, size, state: "idle" });
        rtRef.current = rt;
        const dir = new CompanionDirector(rt, () => { /* lỗi tải ảnh: runtime đã phát `mascoterror` */ });
        dirRef.current = dir;
        rt.host.addEventListener("statechange", (e) => dir.notifyRuntimeState((e as CustomEvent).detail?.state));
        rt.host.addEventListener("animationcomplete", (e) => {
          if ((e as CustomEvent).detail?.state === "success") setFlash(null);
        });
        setReady(true);
      })
      .catch(() => { /* runtime/manifest không tải được → không linh vật, trợ lý vẫn chạy */ });
    return () => {
      cancelled = true;
      dirRef.current?.destroy();
      dirRef.current = null;
      rtRef.current = null;
      setReady(false);
    };
    // `size` đổi được áp bằng setSize bên dưới — không tạo lại instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  useEffect(() => {
    rtRef.current?.setSize(size);
  }, [size, ready]);

  useEffect(() => {
    if (!ready) return;
    void rtRef.current?.setReducedMotion(reduced ? true : null);
  }, [reduced, ready]);

  // Đang ẩn (không có chỗ ngồi, tuyến có điều khiển riêng, bàn phím mở) → DỪNG
  // đồng hồ hoạt ảnh. `visibility:hidden` vẫn "giao cắt" với IntersectionObserver
  // của runtime, nên phải dừng tường minh. Tab ẩn / ngoài màn hình: runtime tự dừng.
  useEffect(() => {
    if (ready) rtRef.current?.setPaused(!visible);
  }, [visible, ready]);

  // ---- "vừa xong": sự kiện thật (stream kết thúc với status `complete`, không lỗi).
  // Điều chỉnh state KHI prop đổi, ngay trong render (mẫu React khuyến nghị) —
  // không setState đồng bộ trong effect.
  const [prevStreaming, setPrevStreaming] = useState(ai.streaming);
  if (prevStreaming !== ai.streaming) {
    setPrevStreaming(ai.streaming);
    const last = ai.messages[ai.messages.length - 1];
    if (ai.streaming) setFlash(null);
    else if (!ai.error && last?.role === "assistant" && last.status === "complete") setFlash("success");
  }

  // Giảm chuyển động: ảnh tĩnh không phát `animationcomplete` → trở lại sau một nhịp ngắn.
  useEffect(() => {
    if (flash !== "success" || !reduced) return;
    const t = window.setTimeout(() => setFlash(null), 1500);
    return () => window.clearTimeout(t);
  }, [flash, reduced]);

  const state = useMemo(
    () =>
      mapCompanionState({
        available: variant === "inline" && available === null ? null : available,
        networkOffline,
        open,
        streaming: ai.streaming,
        hasStreamText: ai.streamingText.length > 0,
        mode: ai.mode,
        errorCode: ai.error?.code ?? null,
        hovering,
        flash,
      }),
    [variant, available, networkOffline, open, ai.streaming, ai.streamingText, ai.mode, ai.error, hovering, flash],
  );

  useEffect(() => {
    if (ready) dirRef.current?.setState(state);
  }, [state, ready]);

  // ---- vị trí (chỉ floating): nhà ↔ mép panel; tính lại khi đổi bố cục.
  useEffect(() => {
    if (!ready || variant !== "floating") return;
    const dir = dirRef.current, rt = rtRef.current, host = hostRef.current;
    if (!dir || !rt || !host) return;
    let raf = 0;
    const measure = () => {
      raf = 0;
      const r = rectOf(host);
      const home: Rect = { ...r, left: r.left - rt.position.x, top: r.top - rt.position.y };
      const nav = document.querySelector(".site-header");
      const navBottom = nav ? nav.getBoundingClientRect().bottom : 0;
      rt.setBounds(boundsFor(home, window.innerWidth, navBottom));
      if (!ai.open) {
        setNoSeat(false);
        dir.goHome();
        return;
      }
      const panel = document.querySelector(".ai-panel");
      const seat = panel ? computeSeat({ home, panel: rectOf(panel), navBottom, viewportWidth: window.innerWidth, size }) : null;
      setNoSeat(!seat);
      if (!seat) dir.goHome();
      else if (dir.currentPlace.kind === "seat") dir.relocate(seat.x, seat.y);
      else dir.goSeat(seat.x, seat.y);
    };
    const schedule = () => { if (!raf) raf = requestAnimationFrame(measure); };
    schedule();
    window.addEventListener("resize", schedule);
    const ro = new ResizeObserver(schedule);
    const panel = document.querySelector(".ai-panel");
    if (panel) ro.observe(panel);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", schedule);
      ro.disconnect();
    };
  }, [ready, variant, ai.open, dockOffset, size]);

  if (!mounted) return null;

  const atHome = variant === "floating" && !ai.open;
  return (
    <div
      className={`ai-companion ai-companion-${variant}${visible ? "" : " ai-companion-an"}${atHome ? " ai-companion-nha" : ""}`}
      style={variant === "floating" && dockOffset ? ({ ["--ai-dock-offset" as string]: `${dockOffset}px` } as React.CSSProperties) : undefined}
      data-state={state}
      data-reduced={reduced ? "1" : undefined}
      aria-hidden="true"
    >
      <div
        ref={hostRef}
        className="ai-companion-host"
        onPointerEnter={atHome ? () => setHovering(true) : undefined}
        onPointerLeave={() => setHovering(false)}
      />
    </div>
  );
}
