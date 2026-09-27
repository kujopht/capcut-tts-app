/**
 * API trung tam ho tro cho quan tri (`/admin/support`) — xem
 * `server/support/admin_routes.py`.
 *
 * Nam RIENG, khong o `lib/api.ts` (module dung chung cua MOI trang): Support TAT
 * co mac dinh, va chi trang `/admin/support` can tep nay.
 */
import { request } from "@/lib/api";
import type { SupportCheck, SupportFinding } from "./api";

export type SupportIncidentStatus = "new" | "open" | "ai_diagnosed" | "needs_owner" | "resolved";

export type SupportIncident = {
  incident_id: string;
  fingerprint: string;
  title: string;
  subsystem: string;
  route: string;
  severity: "low" | "medium" | "high" | "critical";
  status: SupportIncidentStatus;
  first_seen: number;
  last_seen: number;
  event_count: number;
  report_count: number;
  affected_count: number;
  builds: string[];
  browsers: Record<string, number>;
  devices: Record<string, number>;
  ai_diagnosed: boolean;
  owner_needed: boolean;
  error_signature: string;
};

export type SupportIncidentDetail = SupportIncident & {
  routes: Record<string, number>;
  builds_all: Record<string, number>;
  kinds: Record<string, number>;
  timeline: { at: number; kind: string; text: string }[];
  checks: SupportCheck[];
  findings: SupportFinding[];
  evidence: string[];
  reproduction: string[];
  reports: {
    report_id: string;
    summary: string;
    created_at: number;
    status: string;
    browser: string;
    device: string;
    build: string;
    reporter: "user" | "guest";
    reporter_user_id: string | null;
  }[];
};

export type SupportSummary = {
  open_incidents: number;
  new_reports: number;
  resolved: number;
  ai_diagnosed: number;
  needs_owner: number;
  affected_users: number;
  by_severity: Record<string, number>;
  by_subsystem: Record<string, number>;
  persistence: string;
  ai_available: boolean;
};

export type SupportIncidentFilter = {
  status?: string;
  subsystem?: string;
  severity?: string;
  build?: string;
  route?: string;
  unresolved?: boolean;
  q?: string;
};

export type SupportReportRow = {
  report_id: string;
  summary: string;
  route: string;
  subsystem: string;
  status: string;
  created_at: number;
  incident_id: string | null;
  browser: string;
  device: string;
  build: string;
  reporter: "user" | "guest";
};

export const adminSupportApi = {
  summary: () => request<SupportSummary>("/api/admin/support/summary"),
  incidents: (f: SupportIncidentFilter = {}) => {
    const q = new URLSearchParams();
    if (f.status) q.set("status_filter", f.status);
    if (f.subsystem) q.set("subsystem", f.subsystem);
    if (f.severity) q.set("severity", f.severity);
    if (f.build) q.set("build", f.build);
    if (f.route) q.set("route", f.route);
    if (f.unresolved) q.set("unresolved", "true");
    if (f.q) q.set("q", f.q);
    return request<{ total: number; items: SupportIncident[] }>(`/api/admin/support/incidents?${q.toString()}`);
  },
  incident: (id: string) => request<SupportIncidentDetail>(`/api/admin/support/incidents/${encodeURIComponent(id)}`),
  setStatus: (id: string, status: SupportIncidentStatus, note: string) =>
    request<SupportIncident>(`/api/admin/support/incidents/${encodeURIComponent(id)}/status`, {
      method: "POST",
      body: JSON.stringify({ status, note }),
    }),
  issueDraft: (id: string) =>
    request<{ title: string; body: string; labels: string[]; new_issue_url?: string }>(
      `/api/admin/support/incidents/${encodeURIComponent(id)}/issue-draft`,
    ),
  reports: () => request<{ items: SupportReportRow[] }>("/api/admin/support/reports"),
};
