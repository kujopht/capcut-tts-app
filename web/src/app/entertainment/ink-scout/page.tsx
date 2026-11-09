import type { Metadata } from "next";
import Link from "next/link";
import InkScoutLoader from "@/game/inkscout/ui/InkScoutLoader";
import { GAME_INK_SCOUT_ENABLED } from "@/lib/features";

/**
 * Route game "Ink Scout: The Lost Chapter" (`/entertainment/ink-scout`). Cờ build `GAME_INK_SCOUT_ENABLED` TẮT mặc định: tắt thì trang này chỉ là
 * một thông báo tĩnh và không tải mã game. Bật: thẻ chi tiết/khởi chạy (client, tải lười) → phần mở đầu → màn chơi toàn màn hình.
 */
export const metadata: Metadata = {
  title: "Ink Scout: The Lost Chapter",
  description: "Hành động 2D kiểu metroidvania trong vũ trụ Fanfic World — Chương 0: Kho Lưu Trữ bị lãng quên.",
  robots: { index: false, follow: false },
};

export default function InkScoutPage() {
  if (!GAME_INK_SCOUT_ENABLED) {
    return (
      <div className="page stack-3">
        <h1>Ink Scout: The Lost Chapter</h1>
        <p className="hint">Game này chưa mở. Quay lại sau nhé.</p>
        <p>
          <Link href="/entertainment" prefetch={false} className="btn btn-secondary btn-sm">
            ← Về Giải trí
          </Link>
        </p>
      </div>
    );
  }
  return <InkScoutLoader />;
}
