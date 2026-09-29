"use client";

/**
 * Nut goi thoai / video o dau cuoc tro chuyen — CHUA hoat dong (TRTC sau nay, xem `lib/chat/calls.ts`).
 * Vo hieu hoa + nhan "Sắp có": khong mo hop thoai gia, khong xin quyen micro/camera, khong tai SDK nao.
 */
import { callCapabilities } from "@/lib/chat/calls";

export function ChatCallButtons({ peerName }: { peerName: string }) {
  const kha = callCapabilities();
  return (
    <>
      <button type="button" className="chat-nut chat-nut-goi" disabled={!kha.voice} aria-disabled={!kha.voice}
        aria-label={`Gọi thoại cho ${peerName} — sắp có`} title="Gọi thoại — sắp có">
        <span aria-hidden="true">📞</span>
      </button>
      <button type="button" className="chat-nut chat-nut-goi" disabled={!kha.video} aria-disabled={!kha.video}
        aria-label={`Gọi video cho ${peerName} — sắp có`} title="Gọi video — sắp có">
        <span aria-hidden="true">🎥</span>
      </button>
    </>
  );
}
