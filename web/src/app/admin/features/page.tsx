"use client";

/**
 * Features — trạng thái cờ tính năng CHỈ ĐỌC. KHÔNG có nút bật/tắt: backend
 * không có API ghi an toàn nào cho cờ tính năng, nên giao diện không được
 * giả vờ có thể đổi cờ production từ đây (mọi thay đổi thật vẫn cần deploy).
 *
 * Ba nguồn:
 *   - `GET /api/limits` → `capabilities` — `undefined` trên bản đang chạy ở
 *     nhánh này (chưa có PR #229/#231), có thể là `null`/object khi triển
 *     khai. Không đoán tên khoá cụ thể (SOCIAL schema/XP atomic/games…) —
 *     liệt kê nguyên văn khoá/giá trị THẬT nhận được.
 *   - `GET /api/games/config` — cờ games riêng, xem `/admin/games`.
 *   - `NEXT_PUBLIC_MUSIC_ENABLED` (biến môi trường lúc BUILD, đọc qua
 *     `lib/features.ts`) — giá trị này biết ngay, không cần gọi mạng.
 */

import { useCallback } from "react";
import { gamesConfig, social, type ServerLimits } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { CHAT_V1_ENABLED, MUSIC_ENABLED } from "@/lib/features";
import { Loading } from "@/components/ui";
import { IconSliders } from "@/components/Icons";

type TrangThaiCo = "on" | "off" | "unknown";

const NHAN_CO: Record<TrangThaiCo, string> = {
  on: "Bật",
  off: "Tắt",
  unknown: "Không xác định — mã API đang chạy chưa có cờ này",
};

const LOP_CO: Record<TrangThaiCo, string> = {
  on: "tt-duyet",
  off: "tt-trong",
  unknown: "tt-cho",
};

function HangCo({ nhan, trangThai, ghiChu }: { nhan: string; trangThai: TrangThaiCo; ghiChu?: string }) {
  return (
    <div className="row row-spread admin-hang">
      <span>{nhan}</span>
      <span className="stack-2" style={{ alignItems: "flex-end" }}>
        <span className={`tt ${LOP_CO[trangThai]}`}>{NHAN_CO[trangThai]}</span>
        {ghiChu ? <span className="hint">{ghiChu}</span> : null}
      </span>
    </div>
  );
}

/** `capabilities` là object thật -> liệt kê nguyên văn khoá/giá trị nhận
 * được, KHÔNG lọc theo danh sách cờ định sẵn (tên khoá thật do PR #229/#231
 * quyết định, chưa tồn tại trong mã ở đây). */
function DanhSachCapabilities({ capabilities }: { capabilities: Record<string, boolean> }) {
  const muc = Object.entries(capabilities);
  if (muc.length === 0) {
    return <p className="hint">`capabilities` là một đối tượng rỗng.</p>;
  }
  return (
    <div className="stack-2">
      {muc.map(([k, v]) => (
        <HangCo key={k} nhan={k} trangThai={v ? "on" : "off"} />
      ))}
    </div>
  );
}

export default function AdminFeaturesPage() {
  const napLimits = useCallback(() => social.limits(), []);
  const { data: limits, loading: taiLimits, error: loiLimits, reload: taiLaiLimits } =
    useAsyncData<ServerLimits>(napLimits);

  const napGames = useCallback(() => gamesConfig(), []);
  const { data: games, loading: taiGames, missing: gamesChuaCo, error: loiGames } =
    useAsyncData<Record<string, unknown>>(napGames);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconSliders size={19} /> Features
      </h2>
      <p className="hint">
        Chỉ đọc — trang này không có khả năng bật/tắt cờ production, vì backend
        chưa có API ghi an toàn cho việc đó. Đổi cờ thật vẫn cần deploy.
      </p>

      <div className="card stack-2">
        <h3 className="section-title-sm">SOCIAL schema / XP atomic (từ /api/limits)</h3>
        {taiLimits ? (
          <Loading />
        ) : loiLimits ? (
          <div className="row row-spread">
            <span className="hint">{loiLimits}</span>
            <button type="button" className="btn btn-sm" onClick={taiLaiLimits}>
              Thử lại
            </button>
          </div>
        ) : limits && limits.capabilities ? (
          <DanhSachCapabilities capabilities={limits.capabilities} />
        ) : (
          <HangCo
            nhan="capabilities (từ /api/limits)"
            trangThai="unknown"
            ghiChu={
              limits
                ? "`/api/limits` trả về, nhưng trường `capabilities` là null/không có — PR #229/#231 chưa triển khai trên bản đang chạy."
                : undefined
            }
          />
        )}
      </div>

      <div className="card stack-2">
        <h3 className="section-title-sm">Games (từ /api/games/config)</h3>
        {taiGames ? (
          <Loading />
        ) : gamesChuaCo ? (
          <HangCo
            nhan="FAS_GAMES_V1"
            trangThai="unknown"
            ghiChu="`GET /api/games/config` trả 404 — mã games chưa triển khai trên bản đang chạy. Xem /admin/games."
          />
        ) : loiGames ? (
          <span className="hint">{loiGames}</span>
        ) : games ? (
          <DanhSachCapabilities
            capabilities={Object.fromEntries(
              Object.entries(games).filter(
                (kv): kv is [string, boolean] => typeof kv[1] === "boolean",
              ),
            )}
          />
        ) : null}
      </div>

      <div className="card stack-2">
        <h3 className="section-title-sm">Music (biến môi trường build NEXT_PUBLIC_MUSIC_ENABLED)</h3>
        <HangCo nhan="Nhạc nền / playlist" trangThai={MUSIC_ENABLED ? "on" : "off"} />
      </div>

      <div className="card stack-2">
        {/* Ten bien cua co nam o `lib/features.ts` (mot cho duy nhat). May chu con can FAS_CHAT_V1=1. */}
        <h3 className="section-title-sm">Tin nhắn Chat V1 (cờ build, xem lib/features.ts)</h3>
        <HangCo nhan="Nút Tin nhắn · /messages · Nhắn tin ở hồ sơ" trangThai={CHAT_V1_ENABLED ? "on" : "off"} />
      </div>
    </section>
  );
}
