"use client";

/**
 * Games — trạng thái `FAS_GAMES_V1` + bảng xếp hạng XP CHỈ ĐỌC.
 *
 * BA nguồn thật, không hơn:
 *   - `GET /api/games/config` — trên bản API đang chạy ở nhánh này (và trên
 *     production hiện tại) route này CHƯA tồn tại (404). Trang này không
 *     đoán hình dạng phản hồi thật của nó (sẽ do PR #229/#231 quyết định) —
 *     khi có dữ liệu, mọi khoá/giá trị nhận được đều được liệt kê NGUYÊN
 *     VĂN, không đổi tên/không lọc theo một danh sách cờ định sẵn.
 *   - `GET /api/leaderboard` — ĐÃ CÓ thật, công khai, dùng lại nguyên hàm
 *     `api.getLeaderboard` mà `/leaderboard` dùng.
 *   - Cảnh báo "MULTIPLAYER PRODUCTION BLOCKED" — LUÔN hiện, không phụ thuộc
 *     kết quả gọi API nào, vì đây là sự thật vận hành hiện tại (nhiều người
 *     chơi cùng phòng chưa được duyệt lên production), không phải một cờ có
 *     thể bật/tắt từ giao diện này.
 *
 * KHÔNG có nút bật/tắt: backend không có API ghi an toàn cho cờ tính năng —
 * xem `/admin/features`.
 */

import Link from "next/link";
import { useCallback } from "react";
import { api, gamesConfig, type LeaderboardResponse } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { ChuaCauHinh, DanhSachTrangThai } from "@/components/AdminShell";
import { Loading } from "@/components/ui";
import { IconCrown, IconGamepad } from "@/components/Icons";

function GiaTri({ v }: { v: unknown }) {
  if (typeof v === "boolean") return <>{v ? "Bật" : "Tắt"}</>;
  if (v === null || v === undefined) return <span className="hint">—</span>;
  if (typeof v === "object") return <code className="mono">{JSON.stringify(v)}</code>;
  return <>{String(v)}</>;
}

function TrangThaiGamesConfig() {
  const nap = useCallback(() => gamesConfig(), []);
  const { data, loading, error, missing, reload } = useAsyncData<Record<string, unknown>>(nap);

  if (loading) return <Loading />;

  if (missing) {
    return (
      <ChuaCauHinh
        tieuDe="Chưa có API"
        ghiChu="`GET /api/games/config` trả 404 trên bản API đang chạy — mã games (FAS_GAMES_V1) chưa được triển khai. Đây KHÔNG phải lỗi, chỉ là tính năng chưa có trên bản đang chạy."
      />
    );
  }

  if (error) {
    return (
      <div className="card stack-2" role="alert">
        <strong>Không tải được.</strong>
        <p className="hint">{error}</p>
        <div className="row">
          <button type="button" className="btn btn-sm" onClick={reload}>
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  const muc = Object.entries(data ?? {});
  if (muc.length === 0) {
    return <p className="hint">API trả về một đối tượng rỗng.</p>;
  }

  return (
    <div className="admin-bang-boc">
      <table className="admin-bang">
        <caption className="sr-only">Nội dung /api/games/config</caption>
        <thead>
          <tr>
            <th scope="col">Khoá</th>
            <th scope="col">Giá trị</th>
          </tr>
        </thead>
        <tbody>
          {muc.map(([k, v]) => (
            <tr key={k}>
              <td className="mono">{k}</td>
              <td>
                <GiaTri v={v} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminGamesPage() {
  const napBxh = useCallback(() => api.getLeaderboard("all_time", 10, 0), []);
  const { data: bxh, loading: taiBxh, error: loiBxh, reload: taiLaiBxh } =
    useAsyncData<LeaderboardResponse>(napBxh);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconGamepad size={19} /> Games
      </h2>

      {/* Canh bao LUON hien — khong phu thuoc ket qua goi API nao o duoi. */}
      <div className="card admin-chua-cau-hinh" role="alert" style={{ borderColor: "#f8717155" }}>
        <strong>⚠ CHẶN Ở PRODUCTION — MULTIPLAYER PRODUCTION BLOCKED</strong>
        <p className="hint">
          Chế độ nhiều người chơi cùng phòng (real-time multiplayer) CHƯA được
          duyệt lên production. Đây là trạng thái vận hành hiện tại, không
          phải một cờ có thể bật/tắt từ trang này.
        </p>
      </div>

      <div>
        <h3 className="section-title-sm">Trạng thái FAS_GAMES_V1</h3>
        <TrangThaiGamesConfig />
      </div>

      <div>
        <h3 className="section-title-sm">
          <IconCrown size={16} /> Bảng xếp hạng XP (top 10, toàn thời gian)
        </h3>
        <DanhSachTrangThai
          dangTai={taiBxh}
          loi={loiBxh}
          rong={!!bxh && bxh.items.length === 0}
          onThuLai={taiLaiBxh}
        >
          {bxh ? (
            <div className="admin-bang-boc">
              <table className="admin-bang">
                <caption className="sr-only">Bảng xếp hạng XP</caption>
                <thead>
                  <tr>
                    <th scope="col">Hạng</th>
                    <th scope="col">Người dùng</th>
                    <th scope="col" className="admin-so">XP</th>
                  </tr>
                </thead>
                <tbody>
                  {bxh.items.map((it) => (
                    <tr key={it.user_id}>
                      <td>#{it.rank}</td>
                      <td>
                        {it.username ? (
                          <Link href={`/u/${it.username}`}>
                            {it.display_name || it.username}
                          </Link>
                        ) : (
                          it.display_name || "Ẩn danh"
                        )}
                      </td>
                      <td className="admin-so mono">{it.xp.toLocaleString("vi-VN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </DanhSachTrangThai>
        <p className="hint">
          <Link href="/leaderboard" prefetch={false}>Xem bảng xếp hạng đầy đủ</Link>
        </p>
      </div>

      <div>
        <h3 className="section-title-sm">Phòng chơi / xử lý XP (settlement)</h3>
        <ChuaCauHinh
          tieuDe="Chưa có API"
          ghiChu="Backend đang chạy chưa có route quản trị nào để đọc số phòng đang mở hay tình trạng xử lý XP theo phòng — không hiển thị số liệu bịa cho mục này."
        />
      </div>
    </section>
  );
}
