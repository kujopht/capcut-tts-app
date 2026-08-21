"use client";

/**
 * Chuỗi ngày đọc — chỉ số gọn trên thanh điều hướng (V6, gamification).
 *
 * CÙNG triết lý với `NotificationBell`: hỏi MỘT LẦN khi có phiên và khi đổi
 * trang, KHÔNG polling định kỳ. Chuỗi ngày đọc chỉ đổi khi người dùng đọc một
 * chương — tức là khi họ rời trang đọc, đúng lúc `pathname` đổi — nên không
 * cần hỏi lại thường xuyên hơn thế.
 *
 * Ẩn hoàn toàn khi chưa đăng nhập hoặc khi chuỗi đang bằng 0 (chưa từng đọc
 * ngày nào) — một con số 0 nằm mãi trên thanh điều hướng không giúp ai.
 */

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { IconFlame } from "@/components/Icons";

export function StreakBadge() {
  const { profile } = useSession();
  const pathname = usePathname();
  const [chuoi, setChuoi] = useState(0);

  useEffect(() => {
    if (!profile) return;
    let huy = false;
    api
      .getStreak()
      .then((r) => {
        if (!huy) setChuoi(r.current_streak);
      })
      .catch(() => {});
    return () => {
      huy = true;
    };
  }, [profile, pathname]);

  if (!profile || chuoi <= 0) return null;

  return (
    <span
      className="streak-badge"
      title={`Chuỗi ${chuoi} ngày đọc liên tiếp`}
      aria-label={`Chuỗi đọc: ${chuoi} ngày`}
    >
      <IconFlame size={16} />
      {chuoi}
    </span>
  );
}
