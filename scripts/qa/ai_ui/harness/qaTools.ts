/**
 * Công cụ QA dùng chung cho harness (`entry-companion.tsx`) VÀ bản dựng Next THẬT (`real/inject.ts`): không phụ thuộc React hay mã sản phẩm,
 * chỉ quan sát/ghi DOM. Định nghĩa trên `window.__qa`:
 *
 *   traceStart() / traceStop() / trace()   dòng thời gian trạng thái linh vật — cả trạng thái được ÁNH XẠ (`data-state` của `.ai-companion`)
 *                                          lẫn trạng thái runtime THỰC SỰ (sự kiện `statechange` của `.ai-companion-host`)
 *   setDock(on)                            bật/tắt một `.chat-dock` giả (cửa sổ Chat V1) — class thật nên CSS thật + `useChatDockOffset` thật phản ứng
 *   setMini(on)                            bật/tắt một `.mini` giả (thanh phát nhạc đáy màn hình)
 *
 * Dock/mini được chèn thẳng vào `<body>` (ngoài cây React) — đúng kiểu tiện ích trình duyệt vẫn làm; React không đụng tới chúng.
 */
interface TraceEvent {
  t: number;
  kind: "mapped" | "runtime" | "mount" | "unmount";
  state: string;
}

export function installQaTools(): void {
  const qa = ((window as unknown as { __qa?: Record<string, unknown> }).__qa ??= {}) as Record<string, unknown>;

  // ------------------------------------------------------------------------------------------- dòng thời gian trạng thái
  const trace: TraceEvent[] = [];
  let on = false;
  let t0 = 0;
  const push = (kind: TraceEvent["kind"], state: string) => {
    if (on) trace.push({ t: Math.round(performance.now() - t0), kind, state });
  };
  qa.traceStart = () => {
    trace.length = 0;
    t0 = performance.now();
    on = true;
    const w = document.querySelector(".ai-companion");
    if (w) push("mapped", w.getAttribute("data-state") ?? "");
  };
  qa.traceStop = () => {
    on = false;
    return trace.slice();
  };
  qa.trace = () => trace.slice();

  let hostListening: Element | null = null;
  const onRuntimeState = (e: Event) => push("runtime", String((e as CustomEvent).detail?.state ?? ""));
  let lastMapped = "";
  const sweep = () => {
    const wrap = document.querySelector(".ai-companion");
    const host = document.querySelector(".ai-companion-host");
    if (host !== hostListening) {
      hostListening?.removeEventListener("statechange", onRuntimeState);
      hostListening = host;
      if (host) {
        host.addEventListener("statechange", onRuntimeState);
        push("mount", wrap?.className ?? "");
      } else push("unmount", "");
    }
    const now = wrap?.getAttribute("data-state") ?? "";
    if (now !== lastMapped) {
      lastMapped = now;
      if (now) push("mapped", now);
    }
  };
  // `document` (không phải `documentElement`): script có thể chạy ngay lúc tạo tài liệu, khi `<html>` chưa tồn tại.
  new MutationObserver(sweep).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-state"] });

  // ------------------------------------------------------------------------------------------- Chat Dock / thanh phát giả
  const toggle = (id: string, on2: boolean, html: string) => {
    const old = document.querySelector(`[data-qa-fake="${id}"]`);
    if (!on2) {
      old?.remove();
      return;
    }
    if (old) return;
    const div = document.createElement("div");
    div.dataset.qaFake = id;
    div.className = id === "dock" ? "chat-dock" : "mini";
    div.innerHTML = html;
    document.body.appendChild(div);
  };
  qa.setDock = (on2: boolean) =>
    toggle("dock", on2, `<div style="width:336px;height:480px;background:#181a20;border:1px solid #444;border-radius:12px">Cửa sổ Chat V1</div>`);
  qa.setMini = (on2: boolean) => toggle("mini", on2, `<div class="mini-wrap"><span class="mini-title">Thanh phát nhạc giả</span></div>`);
}
