/**
 * Quản lý focus của panel AI nổi (desktop) — hàm DOM thuần, không React, để test được bằng DOM giả.
 *
 * Panel là hộp thoại KHÔNG modal (`role="dialog" aria-modal="false"`) nhưng vẫn theo mẫu WAI-ARIA: mở ra thì focus vào
 * ô soạn (hoặc chính panel nếu ô soạn đang bị khoá vì hết lượt), đóng đi thì focus về nút mở đã mở nó. Trước đây nút mở
 * biến mất khi bấm và focus rơi về `<body>`: người dùng bàn phím/trình đọc màn hình mất vị trí.
 */

interface CoTheFocus {
  focus(opts?: { preventScroll?: boolean }): void;
}

interface GocDom {
  querySelector(selector: string): (CoTheFocus & { disabled?: boolean }) | null;
}

function docDocument(): GocDom | null {
  return typeof document === "undefined" ? null : (document as unknown as GocDom);
}

/** Focus vào ô soạn của panel nổi; ô bị khoá thì focus vào chính panel (`tabIndex=-1`). `true` nếu tìm thấy panel. */
export function focusPanelAi(goc: GocDom | null = docDocument()): boolean {
  if (!goc) return false;
  const panel = goc.querySelector(".ai-panel");
  if (!panel) return false;
  const oSoan = goc.querySelector(".ai-panel textarea.ai-o");
  const dich = oSoan && !oSoan.disabled ? oSoan : panel;
  dich.focus({ preventScroll: true });
  return true;
}

/** Trả focus về nút mở panel (sau khi đóng). `true` nếu nút đang có mặt. */
export function focusNutMoAi(goc: GocDom | null = docDocument()): boolean {
  if (!goc) return false;
  const nut = goc.querySelector(".ai-launcher");
  if (!nut) return false;
  nut.focus({ preventScroll: true });
  return true;
}

/** Chạy `fn` sau khi React đã vẽ xong thay đổi vừa đặt (panel vừa mở/đóng). */
export function sauKhiVe(fn: () => void): void {
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => fn());
  else setTimeout(fn, 0);
}
