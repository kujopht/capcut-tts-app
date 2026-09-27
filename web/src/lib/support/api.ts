/**
 * API cua Fanfic AI Support V1 — xem `server/support/`.
 *
 * Nam RIENG o day, khong o `lib/api.ts`: `lib/api.ts` vao bundle cua MOI trang,
 * con Support TAT co mac dinh — de o do la bat moi trang tai ma cua mot tinh
 * nang dang tat (do that tren ban build). Chi cac module Support import tep nay.
 */
import { request } from "@/lib/api";

export type SupportCheck = {
  tool: string;
  status: "ok" | "warn" | "fail" | "unknown" | "denied";
  summary: string;
};

export type SupportFinding = {
  code: string;
  subsystem: string;
  severity: string;
  text: string;
  next: string;
  owner_needed: boolean;
};

export type SupportAskResponse = {
  answer: string;
  mode: "qa" | "report";
  ai_mode: "ai" | "diagnostic_only";
  ai_available: boolean;
  diagnostic_id: string;
  checks: SupportCheck[];
  findings: SupportFinding[];
  denied: string[];
  can_escalate: boolean;
  suggest_escalate: boolean;
};

export type SupportStatus = { enabled: boolean; ai_available: boolean; persistence: string; modes: string[] };

export type SupportAskIn = {
  mode: "qa" | "report";
  message: string;
  session_id: string;
  context: Record<string, unknown>;
};

export const supportApi = {
  status: () => request<SupportStatus>("/api/support/status"),
  ask: (body: SupportAskIn) =>
    request<SupportAskResponse>("/api/support/ask", { method: "POST", body: JSON.stringify(body) }),
  report: (body: { summary: string; session_id: string; context: Record<string, unknown>; diagnostic_id?: string }) =>
    request<{ report_id: string; status: string; message: string }>("/api/support/reports", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reportStatus: (reportId: string, sessionId: string) =>
    request<{ report_id: string; status: string; summary: string; route: string; created_at: number }>(
      `/api/support/reports/${encodeURIComponent(reportId)}`,
      { headers: { "X-Support-Session": sessionId } },
    ),
};
