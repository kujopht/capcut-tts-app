/**
 * Bộ tách khung SSE cho Fanfic AI Assistant — CÙNG thuật toán với
 * `lib/chat/fanficProtocol.ts::tachKhungSse` (không phát minh cách tách
 * khung mới), nhưng KHÔNG import file đó: `lib/chat/**` là vùng cấm sửa/kéo
 * theo của Chat V1 (xem CLAUDE.md frontend), nên AI Assistant giữ một bản
 * độc lập của riêng nó.
 *
 * Nhịp tim `: ping` (dòng bắt đầu bằng `:`) bị bỏ qua ngay ở bước tách dòng —
 * không bao giờ sinh ra một khung rỗng.
 */
import type { AiCitation, AiErrorCode, AiStreamEvent } from "./types";

interface KhungTho {
  event: string;
  data: string;
}

export function tachKhungSse(boDem: string): { khung: KhungTho[]; conLai: string } {
  const chuan = boDem.replace(/\r\n/g, "\n");
  const phan = chuan.split("\n\n");
  const conLai = phan.pop() ?? "";
  const khung: KhungTho[] = [];
  for (const p of phan) {
    let event = "message";
    const data: string[] = [];
    for (const dong of p.split("\n")) {
      if (!dong || dong.startsWith(":")) continue; // nhịp tim `: ping`
      const i = dong.indexOf(":");
      const ten = i < 0 ? dong : dong.slice(0, i);
      const giaTri = i < 0 ? "" : dong.slice(i + 1).replace(/^ /, "");
      if (ten === "event") event = giaTri;
      else if (ten === "data") data.push(giaTri);
    }
    if (data.length) khung.push({ event, data: data.join("\n") });
  }
  return { khung, conLai };
}

const MA_LOI_HOP_LE: ReadonlySet<string> = new Set<AiErrorCode>([
  "ai_not_enabled",
  "ai_no_provider",
  "ai_rate_limited",
  "ai_budget_exhausted",
  "ai_busy",
  "ai_context_too_large",
  "ai_provider_unavailable",
  "ai_provider_interrupted",
  "ai_forbidden",
  "ai_not_found",
  "network_error",
]);

function toErrorCode(code: unknown): AiErrorCode {
  return typeof code === "string" && MA_LOI_HOP_LE.has(code) ? (code as AiErrorCode) : "ai_provider_unavailable";
}

/** Diễn dịch một khung thô thành `AiStreamEvent` — `null` nếu không nhận ra (bỏ qua, không ném lỗi). */
export function dienDichKhungAi(k: KhungTho): AiStreamEvent | null {
  let d: Record<string, unknown>;
  try {
    d = JSON.parse(k.data) as Record<string, unknown>;
  } catch {
    return null;
  }
  switch (k.event) {
    case "meta":
      return { type: "meta", message_id: String(d.message_id ?? ""), conversation_id: String(d.conversation_id ?? "") };
    case "delta":
      return { type: "delta", text: String(d.text ?? "") };
    case "citations":
      return { type: "citations", items: Array.isArray(d.items) ? (d.items as AiCitation[]) : [] };
    case "usage":
      return {
        type: "usage",
        input_tokens: Number(d.input_tokens ?? 0),
        output_tokens: Number(d.output_tokens ?? 0),
        used_today: typeof d.used_today === "number" ? d.used_today : null,
      };
    case "done":
      return { type: "done", status: (d.status === "stopped" || d.status === "error") ? d.status : "complete" };
    case "error":
      return {
        type: "error",
        code: toErrorCode(d.code),
        message: String(d.message ?? "Có lỗi khi tạo phản hồi."),
        reset_at: typeof d.reset_at === "string" ? d.reset_at : null,
      };
    default:
      return null;
  }
}
