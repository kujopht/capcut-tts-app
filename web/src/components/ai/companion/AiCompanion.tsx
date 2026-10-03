"use client";

/**
 * Ink Scout — linh vật đi cùng Trợ lý AI (`docs/ai/INK_SCOUT_COMPANION.md`).
 *
 * Bọc runtime ĐÃ DUYỆT v1.3.0 (`ink-scout.js` + walk-rig + physics + presence, không viết lại engine): tạo MỘT instance cho mỗi lần
 * mount, `destroy()` khi unmount (huỷ luôn physics/presence gắn vào nó); trạng thái lấy từ `AiProvider` qua hàm thuần
 * `mapCompanionState`; di chuyển/trạng thái đi qua `CompanionDirector` (mới nhất thắng, không cắt ngang chuyển động, không giật
 * linh vật khỏi tay người dùng đang kéo).
 *
 * Hai biến thể:
 *   * `floating` — desktop ≥1024px, cạnh nút mở trợ lý. Panel mở → nhảy lên mép TRÊN panel (ngoài panel: không che chữ/nút Gửi/nút
 *     Đóng), ngồi khi chỉ lắng nghe, đứng dậy khi làm việc; panel đóng → đứng dậy + về nhà. Không đủ chỗ an toàn dưới navbar → ẩn
 *     trong lúc panel mở. Không đi lang thang. NGƯỜI DÙNG kéo thả được (chuột/chạm): thả đâu hợp lệ thì đứng đó và được NHỚ; thả vào
 *     vùng cấm (panel/nút mở/Chat Dock/thanh phát) thì tự nhảy về chỗ an toàn.
 *   * `inline` — trong trang `/assistant` (mọi bề rộng): nằm TRONG luồng nội dung nên không bao giờ đè lên ô soạn; kéo thả trong dải
 *     của chính nó; bàn phím ảo mở (viewport thấp) → thu lại.
 *
 * Không bao giờ: phát âm thanh, nhận focus bàn phím (host `aria-hidden`, `tabindex=-1`), bắt con trỏ ngoài chính nó, tự mở trợ lý,
 * lật ngang nhân vật (không `scaleX(-1)` ở đâu cả). Hiệu năng: nạp LƯỜI, `physics` gắn khi trình duyệt rảnh, `presence` (vòng vẽ
 * liên tục) chỉ chạy khi có tương tác, và sau vài giây yên lặng ở trang thường linh vật DỪNG vẽ (CPU idle ≈ 0).
 */
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "@/lib/session";
import { useAi } from "../AiProvider";
import { useChatDockOffset } from "../useChatDockOffset";
import { mapCompanionState } from "./companionState";
import { CompanionDirector } from "./companionDirector";
import {
  boundsFor, computeSeat, inlineBoundsFor, judgeLanding, panelSurfaces, type Rect, type Seat,
} from "./companionGeometry";
import {
  INK_SCOUT_BASE, loadInkScout, loadInkScoutPresence, type InkScoutPhysicsLike, type InkScoutPresenceLike, type InkScoutRuntime,
  type Surface,
} from "./inkScoutLoader";
import { useCompanionPrefs, useSystemReducedMotion, writeCompanionPrefs } from "./companionPrefs";

export type CompanionVariant = "floating" | "inline";

const SIZE_FLOATING = 96;
const SIZE_INLINE_DESKTOP = 88;
const SIZE_INLINE_MOBILE = 72;
/** Tuyến có điều khiển riêng ở góc dưới (trình đọc, tin nhắn) — linh vật không đứng "nhà" ở đó. */
const HIDE_HOME_ON = [/^\/chapters\//, /^\/messages(\/|$)/];
/** Yên lặng bao lâu (panel đóng, trạng thái nghỉ, không tương tác) thì linh vật dừng vẽ — trang thường không tốn CPU. */
const IDLE_QUIET_MS = 6000;
/** Chạm/bấm nhẹ (không kéo): ngắn hơn và gần hơn ngưỡng này thì tính là "bấm vào linh vật" chứ không phải kéo thả. */
const CLICK_MAX_MS = 350;
const CLICK_MAX_PX = 6;
/** Sau khi con trỏ rời linh vật, giữ "đang tương tác" thêm bấy lâu (chống nhấp nháy bật/tắt vòng vẽ của `presence`). */
const ENGAGE_GRACE_MS = 3500;
/** Rảnh rỗi tối đa bấy lâu thì gắn `physics` dù chưa ai chạm (tải 4 ảnh tư thế ~96 KB ngoài đường tới hạn của trang). */
const PHYSICS_IDLE_TIMEOUT_MS = 3000;

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

/** Các hộp linh vật không được nằm đè lên: nút mở trợ lý, Chat Dock, thanh phát nhỏ, và (khi mở) panel. Chỉ những cái đang hiện. */
function protectedRectsNow(panel: Rect | null): Rect[] {
  const out: Rect[] = [];
  for (const sel of [".ai-launcher", ".chat-dock", ".mini"]) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const r = rectOf(el);
    if (r.width > 0 && r.height > 0) out.push(r);
  }
  if (panel && panel.width > 0 && panel.height > 0) out.push(panel);
  return out;
}

interface LayoutCache {
  home: Rect;
  seat: Seat | null;
  panel: Rect | null;
  navBottom: number;
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
  const physicsRef = useRef<InkScoutPhysicsLike | null>(null);
  const presenceRef = useRef<InkScoutPresenceLike | null>(null);
  /** Bố cục đo gần nhất (desktop nổi): `physics` đọc mặt phẳng ở MỖI khung hình, nên KHÔNG đo DOM trong callback đó. */
  const layoutRef = useRef<LayoutCache | null>(null);
  const surfacesRef = useRef<Surface[]>([]);
  const [ready, setReady] = useState(false);
  const [interactive, setInteractive] = useState(false);
  const [wanted, setWanted] = useState(false);
  const [hovering, setHovering] = useState(false);
  const [poked, setPoked] = useState(false);
  const [held, setHeld] = useState(false);
  const [engaged, setEngaged] = useState(false);
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

  // Giá trị mới nhất cho các trình xử lý chạy ngoài vòng render (kéo thả, đo bố cục, hẹn giờ).
  const latest = useRef({ open: false, homeX: null as number | null, variant, size, reduced });
  useEffect(() => {
    latest.current = { open, homeX: prefs.homeX, variant, size, reduced };
  });

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

  // `reduced` lúc TẠO runtime: đọc qua ref (effect tạo instance chỉ chạy lại theo `load`).
  const reducedRef = useRef(reduced);
  useEffect(() => { reducedRef.current = reduced; }, [reduced]);

  // ---- tạo MỘT instance; huỷ khi unmount / bị ẩn hẳn (tuỳ chọn "Ẩn").
  useEffect(() => {
    if (!load) return;
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    let off: (() => void) | null = null;
    loadInkScout()
      .then(async ({ Ctor, Physics, manifest }) => {
        if (cancelled || !hostRef.current) return;
        const rt = new Ctor(hostRef.current, { manifest, assetBase: INK_SCOUT_BASE, size, state: "idle" });
        rtRef.current = rt;
        const dir = new CompanionDirector(rt, () => { /* lỗi tải ảnh: runtime đã phát `mascoterror` */ });
        dirRef.current = dir;

        const onState = (e: Event) => dir.notifyRuntimeState((e as CustomEvent).detail?.state);
        const onDone = (e: Event) => { if ((e as CustomEvent).detail?.state === "success") setFlash(null); };
        rt.host.addEventListener("statechange", onState);
        rt.host.addEventListener("animationcomplete", onDone);

        // ---- kéo thả (physics): người dùng cầm → director đứng yên; thả → phán xử nơi đáp rồi áp lại trạng thái mới nhất.
        let pickupAt: { t: number; x: number; y: number } | null = null;
        let watchdog = 0;
        const release = () => {
          window.clearInterval(watchdog);
          watchdog = 0;
          pickupAt = null;
          setHeld(false);
          dir.hold(false);
        };
        const onPickup = () => {
          dir.hold(true);
          setHeld(true);
          pickupAt = { t: performance.now(), x: rt.position.x, y: rt.position.y };
          // Lưới an toàn: nếu runtime bỏ cuộc (đổi giảm chuyển động, huỷ…) mà không phát `movementcomplete`, đừng kẹt "đang cầm".
          window.clearInterval(watchdog);
          watchdog = window.setInterval(() => { if (!physicsRef.current?.mode) release(); }, 400);
        };
        const onMoved = (e: Event) => {
          if ((e as CustomEvent).detail?.name !== "drop") return;
          const start = pickupAt;
          const moved = start ? Math.hypot(rt.position.x - start.x, rt.position.y - start.y) : Infinity;
          const quick = start ? performance.now() - start.t < CLICK_MAX_MS : false;
          settleAfterDrop();
          release();
          if (quick && moved < CLICK_MAX_PX) poke();
        };
        rt.host.addEventListener("pickup", onPickup);
        rt.host.addEventListener("movementcomplete", onMoved);

        const settleAfterDrop = () => {
          const { variant: v } = latest.current;
          if (v !== "floating") {
            dir.settle({ kind: "free" });
            return;
          }
          const L = layoutRef.current;
          if (!L) {
            dir.settle({ kind: "free" });
            return;
          }
          const verdict = judgeLanding({
            x: rt.position.x, y: rt.position.y, size: rt.size, home: L.home, seat: L.seat,
            protectedRects: protectedRectsNow(L.panel),
          });
          if (verdict.kind === "seat") {
            dir.settle({ kind: "seat", x: rt.position.x, y: rt.position.y });
          } else if (verdict.kind === "floor") {
            const x = Math.min(0, verdict.x);
            rt.home = { x, y: 0 };
            dir.settle({ kind: "home" });
            writeCompanionPrefs({ homeX: x === 0 ? null : x });
          } else {
            // Vùng cấm: tới chỗ ngồi (panel đang mở và có chỗ) hoặc về nhà. `settle` "free" để mọi đích đều thật sự di chuyển.
            dir.settle({ kind: "free" });
            if (verdict.to === "seat" && L.seat) dir.goSeat(L.seat.x, L.seat.y);
            else dir.goHome();
          }
        };

        // ---- phản ứng khi bấm/chạm nhẹ: xoa đầu (presence) nếu đang nghỉ, không thì vẫy tay (hover) — cả hai do bộ gói định nghĩa.
        const poke = () => {
          const p = presenceRef.current;
          if (p && p.enabled) {
            p.pat().then((ok) => { if (!ok) setPoked(true); }).catch(() => setPoked(true));
          } else setPoked(true);
        };

        // ---- gắn physics (kéo thả). Màn hình cảm ứng/panel mở: ngay. Còn lại: khi trình duyệt rảnh.
        const attachPhysics = () => {
          if (cancelled || physicsRef.current || !Physics) return;
          const p = new Physics(rt, { surfaces: () => surfacesRef.current });
          physicsRef.current = p;
          // `physics` tự đặt tabIndex=0 + aria-label lên host. Linh vật là TRANG TRÍ (`aria-hidden`): GỠ HẲN cả hai — không vào thứ tự Tab,
          // không nhận focus kể cả khi bấm hay gọi `.focus()` (tabindex=-1 vẫn là "focus được bằng chương trình/chuột" trên một phần tử
          // ẩn khỏi cây trợ năng — review Codex #3), không nhãn đọc màn hình.
          rt.host.removeAttribute("tabindex");
          rt.host.removeAttribute("aria-label");
          setInteractive(true);
        };
        const w = window as unknown as {
          requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
          cancelIdleCallback?: (id: number) => void;
        };
        let idleId = 0;
        const coarse = window.matchMedia("(pointer: coarse)").matches;
        if (latest.current.variant === "inline" || latest.current.open || coarse) attachPhysics();
        else if (w.requestIdleCallback) idleId = w.requestIdleCallback(attachPhysics, { timeout: PHYSICS_IDLE_TIMEOUT_MS });
        else idleId = window.setTimeout(attachPhysics, PHYSICS_IDLE_TIMEOUT_MS);

        // Gỡ đúng listener của instance NÀY khi huỷ (review Codex #4: host là div React, sống lâu hơn runtime).
        off = () => {
          window.clearInterval(watchdog);
          if (idleId) {
            if (w.cancelIdleCallback) w.cancelIdleCallback(idleId);
            window.clearTimeout(idleId);
          }
          rt.host.removeEventListener("statechange", onState);
          rt.host.removeEventListener("animationcomplete", onDone);
          rt.host.removeEventListener("pickup", onPickup);
          rt.host.removeEventListener("movementcomplete", onMoved);
        };
        // Giảm chuyển động áp TRƯỚC khi hiện (Codex #3): runtime gọi setState trong constructor
        // theo media query hệ điều hành, chưa biết tuỳ chọn "Giảm chuyển động" của người dùng.
        if (reducedRef.current) await rt.setReducedMotion(true);
        if (cancelled) return;
        setReady(true);
      })
      .catch(() => { /* runtime/manifest không tải được → không linh vật, trợ lý vẫn chạy */ });
    return () => {
      cancelled = true;
      off?.();
      dirRef.current?.destroy(); // destroy() của runtime huỷ luôn physics/presence đã gắn vào instance
      dirRef.current = null;
      rtRef.current = null;
      physicsRef.current = null;
      presenceRef.current = null;
      layoutRef.current = null;
      surfacesRef.current = [];
      setReady(false);
      setInteractive(false);
      setHeld(false);
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

  // ---- tương tác với CHÍNH linh vật: con trỏ vào → vẫy tay (hover) + bật `presence`; rời → tắt sau một nhịp ân hạn.
  useEffect(() => {
    if (!ready || !interactive) return;
    const host = hostRef.current;
    if (!host) return;
    let graceTimer = 0;
    let disposed = false;
    const enter = () => {
      window.clearTimeout(graceTimer);
      setEngaged(true);
      setHovering(true);
      if (!presenceRef.current) {
        void loadInkScoutPresence().then((Presence) => {
          const rt = rtRef.current;
          if (disposed || !Presence || !rt || presenceRef.current) return;
          // `stage` = khung bao nhỏ của linh vật (sự kiện chỉ tới đây khi con trỏ ở trên linh vật): không nghe cả trang.
          presenceRef.current = new Presence(rt, { stage: host.parentElement ?? host, physics: physicsRef.current });
        });
      } else {
        presenceRef.current.enabled = true;
        presenceRef.current.start(); // vòng vẽ của presence chỉ khởi động lại theo sự kiện — gọi tường minh khi được bật lại
      }
    };
    const leave = () => {
      setHovering(false);
      window.clearTimeout(graceTimer);
      graceTimer = window.setTimeout(() => {
        setEngaged(false);
        const p = presenceRef.current;
        if (p) {
          p.enabled = false; // vòng vẽ liên tục của presence dừng; trả canvas về khung gốc
          p.stop();
          p.reset();
        }
      }, ENGAGE_GRACE_MS);
    };
    host.addEventListener("pointerenter", enter);
    host.addEventListener("pointerleave", leave);
    return () => {
      disposed = true;
      window.clearTimeout(graceTimer);
      host.removeEventListener("pointerenter", enter);
      host.removeEventListener("pointerleave", leave);
      setEngaged(false);
      setHovering(false);
    };
  }, [ready, interactive]);

  // "Bấm vào linh vật" mà không có presence: vẫy tay một nhịp rồi thôi (không treo ở trạng thái hover).
  useEffect(() => {
    if (!poked) return;
    const t = window.setTimeout(() => setPoked(false), 1300);
    return () => window.clearTimeout(t);
  }, [poked]);

  // ---- YÊN LẶNG: panel đóng + nghỉ + không tương tác một lúc → dừng vẽ. Mọi thứ đánh thức đều làm `quietEligible` sai → vẽ lại ngay.
  const quietEligible = variant === "floating" && !ai.open && !engaged && !hovering && !poked && !held && !flash && !ai.streaming;
  const [quietKey, setQuietKey] = useState(0);
  const [prevEligible, setPrevEligible] = useState(quietEligible);
  if (prevEligible !== quietEligible) {
    setPrevEligible(quietEligible);
    setQuietKey((k) => k + 1);
  }
  const [firedKey, setFiredKey] = useState(-1);
  useEffect(() => {
    if (!quietEligible || !ready) return;
    const t = window.setTimeout(() => setFiredKey(quietKey), IDLE_QUIET_MS);
    return () => window.clearTimeout(t);
  }, [quietEligible, quietKey, ready]);
  const quiet = quietEligible && firedKey === quietKey;

  // Đang ẩn (không có chỗ ngồi, tuyến có điều khiển riêng, bàn phím mở) hoặc yên lặng → DỪNG đồng hồ hoạt ảnh.
  // `visibility:hidden` vẫn "giao cắt" với IntersectionObserver của runtime, nên phải dừng tường minh.
  // Tab ẩn / ngoài màn hình: runtime tự dừng.
  useEffect(() => {
    if (ready) rtRef.current?.setPaused(!visible || quiet);
  }, [visible, quiet, ready]);

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
        responseStarted: ai.responseStarted,
        mode: ai.mode,
        errorCode: ai.error?.code ?? null,
        hovering: hovering || poked,
        flash,
      }),
    [variant, available, networkOffline, open, ai.streaming, ai.streamingText, ai.responseStarted, ai.mode, ai.error,
      hovering, poked, flash],
  );

  useEffect(() => {
    if (ready) dirRef.current?.setState(state);
  }, [state, ready]);

  // ---- vị trí (floating): nhà ↔ mép panel; đo lại khi đổi bố cục. Cũng nuôi `physics` (mặt phẳng) và bộ phán xử nơi thả.
  useEffect(() => {
    if (!ready || variant !== "floating") return;
    const dir = dirRef.current, rt = rtRef.current, host = hostRef.current;
    if (!dir || !rt || !host) return;
    let raf = 0;
    const measure = () => {
      raf = 0;
      // "Nhà" = hộp của khung bao `.ai-companion-floating` (cố định, KHÔNG bao
      // giờ bị dịch; host nằm ở góc trên-trái của nó, cùng kích thước). Không
      // suy từ `hộp host − runtime.position`: hai giá trị đó lệch nhau trong
      // một khoảnh khắc (panel mở sẵn lúc tải trang, giảm chuyển động) là chỗ
      // ngồi bị nhân đôi — đo được ở QA Lightning lượt 2 (translate(-428,-1188)).
      const wrap = host.parentElement ?? host;
      const home: Rect = rectOf(wrap);
      const nav = document.querySelector(".site-header");
      const navBottom = nav ? nav.getBoundingClientRect().bottom : 0;
      const bounds = boundsFor(home, window.innerWidth, navBottom);
      rt.setBounds(bounds);
      // Vị trí nhà người dùng đã đặt: luôn kẹp theo bố cục HIỆN TẠI (cửa sổ thu nhỏ, đổi bề rộng) — giá trị lưu không bao giờ đưa
      // linh vật ra khỏi màn hình hay sang phải nút mở.
      const wantedX = Math.max(bounds.left, Math.min(0, latest.current.homeX ?? 0));
      rt.home = { x: wantedX, y: 0 };
      const isOpen = latest.current.open;
      const panelEl = isOpen ? document.querySelector(".ai-panel") : null;
      const panel = panelEl ? rectOf(panelEl) : null;
      const seat = panel ? computeSeat({ home, panel, navBottom, viewportWidth: window.innerWidth, size }) : null;
      layoutRef.current = { home, seat, panel, navBottom };
      surfacesRef.current = panelSurfaces(seat, panel, home);
      if (!isOpen) {
        setNoSeat(false);
        // Đang đứng nhà mà nhà vừa đổi (khôi phục vị trí đã nhớ, thu nhỏ cửa sổ, "Đặt lại vị trí"): dời NGAY, không hoạt ảnh — kể cả khi
        // director đang bận áp trạng thái đầu tiên (dời ngay khi rảnh). Đang ở chỗ khác: `goHome` đi tới nhà mới.
        dir.rehome();
        dir.goHome();
        return;
      }
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
  }, [ready, variant, ai.open, dockOffset, size, prefs.homeX]);

  // ---- vị trí (inline): biên theo dải nội dung của chính nó — kéo ngang cả bề rộng, nhấc lên một đoạn ngắn.
  useEffect(() => {
    if (!ready || variant !== "inline") return;
    const rt = rtRef.current, host = hostRef.current;
    if (!rt || !host) return;
    const stage = host.parentElement;
    if (!stage) return;
    const apply = () => rt.setBounds(inlineBoundsFor(rectOf(stage), size));
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(stage);
    return () => ro.disconnect();
  }, [ready, variant, size]);

  // ---- "hover": con trỏ trên NÚT MỞ TRỢ LÝ ngay cạnh (sự kiện thật của UI). Con trỏ trên CHÍNH linh vật: xem effect tương tác ở trên.
  const atHomeNow = variant === "floating" && !ai.open;
  useEffect(() => {
    if (!ready || !atHomeNow) return;
    const btn = document.querySelector(".ai-launcher");
    if (!btn) return;
    const on = () => setHovering(true);
    const offHover = () => setHovering(false);
    btn.addEventListener("pointerenter", on);
    btn.addEventListener("pointerleave", offHover);
    return () => {
      btn.removeEventListener("pointerenter", on);
      btn.removeEventListener("pointerleave", offHover);
      setHovering(false);
    };
  }, [ready, atHomeNow]);

  if (!mounted) return null;

  const atHome = atHomeNow;
  return (
    <div
      className={`ai-companion ai-companion-${variant}${visible ? "" : " ai-companion-an"}${atHome ? " ai-companion-nha" : ""}${ready ? "" : " ai-companion-cho"}${interactive && visible ? " ai-companion-live" : ""}${held ? " ai-companion-giu" : ""}`}
      style={variant === "floating" && dockOffset ? ({ ["--ai-dock-offset" as string]: `${dockOffset}px` } as React.CSSProperties) : undefined}
      data-state={state}
      data-reduced={reduced ? "1" : undefined}
      data-quiet={quiet ? "1" : undefined}
      aria-hidden="true"
    >
      <div ref={hostRef} className="ai-companion-host" />
    </div>
  );
}
