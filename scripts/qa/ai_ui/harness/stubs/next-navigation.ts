/** Thay `next/navigation` trong harness QA: đường dẫn lấy từ location.hash ("#/assistant" -> "/assistant"). */
import { useSyncExternalStore } from "react";

function subscribe(cb: () => void): () => void {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.hash.replace(/^#/, "") || "/", () => "/");
}

export function useRouter() {
  return {
    back: () => window.history.back(),
    push: (href: string) => {
      window.location.hash = href;
    },
    replace: (href: string) => {
      window.location.hash = href;
    },
    prefetch: () => {},
    refresh: () => {},
  };
}
