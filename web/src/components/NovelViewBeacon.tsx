"use client";

/**
 * Ghi MỘT lượt xem khi trang truyện được mở.
 *
 * Chỉ là một effect bắn một lần khi mount: "mở trang tính 1 lượt xem" —
 * Back/Forward cache khôi phục trang mà không mount lại nên không đếm trùng,
 * còn F5 thì mount lại và đếm thêm một lượt, đúng như og đã chốt.
 *
 * Không render gì, không chặn gì: `recordNovelView` đã tự nuốt lỗi, nên một
 * lần ghi hỏng không bao giờ làm vỡ trang truyện.
 */

import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

export function NovelViewBeacon({ novelId }: { novelId: string }) {
  const daGui = useRef(false);
  useEffect(() => {
    if (daGui.current) return;
    daGui.current = true;
    void api.recordNovelView(novelId);
  }, [novelId]);
  return null;
}
