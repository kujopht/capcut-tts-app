"use client";

/**
 * "Dong co" chat — noi DUY NHAT import `tencentTransport` (va qua do SDK Tencent).
 *
 * `ChatProvider` chi render component nay SAU KHI nguoi dung mo chat, qua
 * `next/dynamic(..., { ssr: false })`. `ssr: false` la cach Next CHINH THUC de
 * mot module khong bao gio vao bundle SERVER: do tren ban `cf:build`, mot
 * `import()` dong thuong o `ChatProvider` van keo SDK (~0,9 MB) vao
 * `handler.mjs` cua Worker — ma Worker chay trong tran 128 MB va nhay voi
 * thoi gian khoi dong lanh (xem `worker-cold-start-budget.test.mjs`).
 */
import { useEffect } from "react";
import { taiTencentTransport } from "@/lib/chat/tencentTransport";

export type TaiTransport = typeof taiTencentTransport;

export default function ChatEngine({ onLoaded }: { onLoaded: (tai: TaiTransport) => void }) {
  useEffect(() => {
    onLoaded(taiTencentTransport);
  }, [onLoaded]);
  return null;
}
