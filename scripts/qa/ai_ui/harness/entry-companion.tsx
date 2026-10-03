/**
 * Harness QA LINH VẬT Ink Scout: dựng THẬT `AiProvider` + `AiPanel` + `AiLauncher` + `AiCompanionGate` (floating, đúng thứ tự như
 * `app/layout.tsx`) + trang `/assistant` (inline), bundle với cờ build `NEXT_PUBLIC_AI_COMPANION_ENABLED=1` và MÃ LINH VẬT THẬT
 * (không stub). Asset linh vật thật được `run_companion.mjs` phục vụ ở `/mascot/` từ `web/public/mascot/`.
 *
 * Shell giả đủ để đo va chạm với phần còn lại của site: `.site-header` (class thật → vị trí sticky thật), và `.chat-dock` / `.mini`
 * bật/tắt bằng `__qa.setDock(true)` / `__qa.setMini(true)` (xem `qaTools.ts`, dùng chung với bản dựng Next thật).
 * KHÔNG phải mã sản phẩm.
 */
import { createRoot } from "react-dom/client";
import { useSyncExternalStore } from "react";
import "../../../../web/src/app/globals.css";
import "../../../../web/src/app/chat.css";
import "../../../../web/src/components/ai/ai.css";
import AssistantPage from "@/app/assistant/page";
import { AiLauncher } from "@/components/ai/AiLauncher";
import { AiPanel } from "@/components/ai/AiPanel";
import { AiProvider } from "@/components/ai/AiProvider";
import { AiCompanionGate } from "@/components/ai/companion/AiCompanionGate";
import { installFakeServer } from "./fakeServer";
import { installQaTools } from "./qaTools";
import { qaSetProfile } from "./stubs/session";
import { setToken } from "./stubs/api";

installFakeServer();
installQaTools();

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

function FakeHeader() {
  return (
    <header className="site-header">
      <div className="wrap" style={{ display: "flex", alignItems: "center", height: 56, gap: 16, padding: "0 16px" }}>
        <strong>Fanfic World</strong>
        <a href="#/">Trang chủ</a>
        <a href="#/assistant">Trợ lý</a>
        <a href="#/chapters/1">Đọc</a>
      </div>
    </header>
  );
}

function Shell() {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash.replace(/^#/, "") || "/", () => "/");
  const onAssistant = hash.startsWith("/assistant");
  return (
    <>
      <FakeHeader />
      {onAssistant ? (
        <AssistantPage />
      ) : (
        <main className="wrap" style={{ padding: 24 }}>
          <h1>Trang giả của site</h1>
          {Array.from({ length: 40 }, (_, i) => (
            <p key={i}>Đoạn nội dung nền số {i + 1} — dùng để thử cuộn trang phía sau panel nổi và linh vật.</p>
          ))}
        </main>
      )}
      <AiLauncher />
      <AiPanel />
      <AiCompanionGate variant="floating" />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <AiProvider>
    <Shell />
  </AiProvider>,
);
