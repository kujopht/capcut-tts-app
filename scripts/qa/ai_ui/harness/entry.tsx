/**
 * Harness QA giao diện Trợ lý AI: dựng THẬT `AiProvider` + `AiPanel` + `AiLauncher` + trang `/assistant` của web (không
 * sao chép), với `@/lib/api`, `@/lib/session`, `next/*` và linh vật được thay bằng bản giả (xem build.mjs), và một máy
 * chủ giả trong trang (fakeServer.ts). Mục đích: đo bố cục thật ở nhiều cỡ màn hình + chạy các luồng người dùng bằng
 * Chrome headless (run.mjs). KHÔNG phải mã sản phẩm và không được import từ `web/`.
 */
import { createRoot } from "react-dom/client";
import { useSyncExternalStore } from "react";
import "../../../../web/src/app/globals.css";
import "../../../../web/src/components/ai/ai.css";
import AssistantPage from "@/app/assistant/page";
import { AiLauncher } from "@/components/ai/AiLauncher";
import { AiPanel } from "@/components/ai/AiPanel";
import { AiProvider } from "@/components/ai/AiProvider";
import { installFakeServer } from "./fakeServer";
import { qaSetProfile } from "./stubs/session";
import { setToken } from "./stubs/api";

installFakeServer();

const qaWin = window as unknown as { __qa: Record<string, unknown> };
qaWin.__qa.setUser = (id: string | null) => {
  if (!id) {
    setToken(null);
    qaSetProfile(null);
    return;
  }
  setToken(`tok_${id}`);
  qaSetProfile({ user_id: id, email: `${id}@qa.local`, display_name: id, tier: "free" });
};

function subscribe(cb: () => void): () => void {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}

function Shell() {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash.replace(/^#/, "") || "/", () => "/");
  if (hash.startsWith("/assistant")) return <AssistantPage />;
  return (
    <>
      <main className="wrap" style={{ padding: 24 }}>
        <h1>Trang giả của site</h1>
        {Array.from({ length: 30 }, (_, i) => (
          <p key={i}>Đoạn nội dung nền số {i + 1} — dùng để thử cuộn trang phía sau panel nổi.</p>
        ))}
      </main>
      <AiLauncher />
      <AiPanel />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <AiProvider>
    <Shell />
  </AiProvider>,
);
