"use client";

/**
 * "Dong co" chat — noi DUY NHAT import transport (`fanficTransport`: API Fanfic, du lieu + Realtime
 * o Appwrite). Tencent Chat khong con duoc dung cho tin nhan chu.
 *
 * `ChatProvider` chi render component nay SAU KHI nguoi dung mo chat, qua
 * `next/dynamic(..., { ssr: false })`: doc/nghe truyen khong tai byte nao cua dong co, khong mo luong
 * nao — va chunk nay khong bao gio vao bundle SERVER cua Worker (xem `worker-cold-start-budget.test.mjs`).
 */
import { useEffect } from "react";
import { taiFanficTransport } from "@/lib/chat/fanficTransport";

export type TaiTransport = typeof taiFanficTransport;

export default function ChatEngine({ onLoaded }: { onLoaded: (tai: TaiTransport) => void }) {
  useEffect(() => {
    onLoaded(taiFanficTransport);
  }, [onLoaded]);
  return null;
}
