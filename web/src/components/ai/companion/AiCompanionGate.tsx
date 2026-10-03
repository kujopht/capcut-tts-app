"use client";

/**
 * Cổng của linh vật Ink Scout. `AI_COMPANION_ENABLED` là hằng số lúc build:
 * TẮT → `loader` là `null` nên chunk linh vật KHÔNG BAO GIỜ được yêu cầu (đo:
 * Turbopack vẫn xuất tệp chunk lười ~3 KB gzip ra thư mục build, nhưng nó không
 * nằm trong script ban đầu và 0 request). BẬT → component thật (`AiCompanion`)
 * chỉ được tải khi cổng mount trên client VÀ linh vật có thể hiện.
 *
 * Một `import()` thuần trong cổng client, không `next/dynamic` (runtime ~6 KB
 * của `next/dynamic` sẽ nằm trong bundle ngay cả khi cờ tắt — đã đo ở #238).
 */
import { useEffect, useState, useSyncExternalStore, type ComponentType } from "react";
import { AI_COMPANION_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";
import { useAiSafe } from "../AiProvider";
import type { CompanionVariant } from "./AiCompanion";

type CompanionComponent = ComponentType<{ variant: CompanionVariant }>;

const loader: (() => Promise<CompanionComponent>) | null = AI_COMPANION_ENABLED
  ? () => import("./AiCompanion").then((m) => m.AiCompanion)
  : null;

/** Linh vật NỔI chỉ có ở desktop ≥1024px (CSS ẩn nút mở/panel dưới mốc này) — điện thoại không bao giờ cần chunk của nó ngoài `/assistant`. */
const DESKTOP_QUERY = "(min-width: 1024px)";
function subscribeDesktop(cb: () => void): () => void {
  const mq = window.matchMedia(DESKTOP_QUERY);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}
const isDesktopNow = () => window.matchMedia(DESKTOP_QUERY).matches;
const isDesktopServer = () => false;

export function AiCompanionGate({ variant }: { variant: CompanionVariant }) {
  const ai = useAiSafe();
  const { profile } = useSession();
  const desktop = useSyncExternalStore(subscribeDesktop, isDesktopNow, isDesktopServer);
  const [Comp, setComp] = useState<CompanionComponent | null>(null);
  // Chỉ tải mã linh vật khi nó CÓ THỂ hiện: đã đăng nhập, trợ lý bật, và (nổi)
  // màn hình desktop + nút mở trợ lý đang hiện — cùng điều kiện với `AiLauncher` (máy chủ xác nhận
  // `eligible`; `availability` `null` = chưa hỏi, vẫn hiện; `false`/`enabled:false` = ẩn).
  // `/assistant` (inline) tải cả khi không khả dụng để hiện trạng thái offline.
  const canShow = !!loader && !!ai?.enabled && !!profile &&
    (variant === "inline" ||
      (desktop && ai.eligible && ai.availability !== false && !(ai.availability && !ai.availability.enabled)));
  useEffect(() => {
    if (!loader || !canShow || Comp) return;
    let alive = true;
    loader().then((c) => {
      if (alive) setComp(() => c);
    }).catch(() => { /* không tải được linh vật — trợ lý vẫn chạy bình thường */ });
    return () => {
      alive = false;
    };
  }, [canShow, Comp]);
  if (!loader || !Comp || !canShow) return null;
  return <Comp variant={variant} />;
}
