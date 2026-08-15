"use client";

/**
 * Bảng xếp hạng XP — CÔNG KHAI, xem được cả khi chưa đăng nhập (khi đó không
 * có hàng "vị trí của bạn").
 *
 * Hai chế độ, MÁY CHỦ tính riêng từng cái (`GET /api/leaderboard?mode=`):
 *   - "all_time": tổng XP từ trước tới giờ.
 *   - "weekly": XP kiếm được trong tuần ISO hiện tại (từ thứ Hai).
 *
 * PHÂN TRANG do máy chủ giới hạn (`limit`/`offset`, trần 100) — không tải hết
 * bảng về rồi cắt bằng JavaScript, cùng nguyên tắc với `/fanfic`. KHÔNG
 * polling: chỉ tải lại khi người dùng đổi chế độ/trang, không có
 * `setInterval` nào ở đây.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type LeaderboardEntry, type LeaderboardResponse } from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { PageHeader, SkeletonList, EmptyState, ErrorState } from "@/components/ui";
import { IconCrown } from "@/components/Icons";
import { Avatar } from "@/components/Avatar";
import { CosmeticFrame } from "@/components/cosmetics/Cosmetics";

const PAGE_SIZE = 20;

type Mode = "all_time" | "weekly";

function HangXepHang({ it }: { it: LeaderboardEntry }) {
  return (
    <li className={it.is_you ? "lb-row lb-row-you" : "lb-row"}>
      <span className="lb-rank" aria-hidden="true">
        #{it.rank}
      </span>
      <CosmeticFrame
        cosmetic={it.equipped_cosmetics.find((c) => c.slot === "avatar_frame")}
      >
        <Avatar
          name={it.display_name || it.username || "?"}
          avatarUrl={it.avatar_url}
          className="avatar avatar-sm"
        />
      </CosmeticFrame>
      <span className="lb-info">
        {it.username ? (
          <Link href={`/u/${it.username}`} className="binh-luan-ten">
            {it.display_name || it.username}
          </Link>
        ) : (
          <strong>{it.display_name || "Ẩn danh"}</strong>
        )}
        <span className="hint">{it.title}</span>
      </span>
      <span className="lb-xp">{it.xp.toLocaleString("vi-VN")} XP</span>
    </li>
  );
}

export default function LeaderboardPage() {
  const { profile } = useSession();
  const [mode, setMode] = useState<Mode>("all_time");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadTick, setReloadTick] = useState(0);
  const latest = useRef(0);

  const doiChe = useCallback((m: Mode) => {
    setMode(m);
    setPage(0);
  }, []);

  const taiLai = useCallback(() => setReloadTick((v) => v + 1), []);

  const taiTrang = useCallback(() => {
    const ticket = latest.current + 1;
    latest.current = ticket;
    setLoading(true);
    setError("");
    api
      .getLeaderboard(mode, PAGE_SIZE, page * PAGE_SIZE)
      .then((r) => {
        if (latest.current !== ticket) return;
        setData(r);
      })
      .catch((cause) => {
        if (latest.current !== ticket) return;
        setError(errorMessage(cause));
        setData(null);
      })
      .finally(() => {
        if (latest.current === ticket) setLoading(false);
      });
    // `reloadTick` khong duoc doc trong than ham — co mat trong mang phu
    // thuoc CHI de ep chay lai khi nguoi dung bam "Thu lai" (`taiLai`) ma
    // `mode`/`page` khong doi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, page, reloadTick]);

  /* `queueMicrotask`: goi `taiTrang` truc tiep trong than effect se dat
     `setLoading`/`setError` DONG BO ngay trong effect, bi quy tac
     `react-hooks/set-state-in-effect` cam — cung ly do voi `app/notifications/page.tsx`. */
  useEffect(() => {
    queueMicrotask(taiTrang);
  }, [taiTrang]);

  const lastPage = data ? Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1) : 0;
  const viewerTrongTrang =
    !!data?.viewer_entry &&
    data.items.some((it) => it.user_id === data.viewer_entry?.user_id);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Cộng đồng"
        icon={<IconCrown size={16} />}
        title="Bảng xếp hạng"
        lead="Xếp hạng theo XP — đọc, nghe và tương tác cộng đồng để lên hạng."
        id="lb-title"
      />

      <div className="tab-hang" role="tablist" aria-label="Chế độ bảng xếp hạng">
        <button
          type="button"
          role="tab"
          className={mode === "all_time" ? "tab-nut tab-chon" : "tab-nut"}
          aria-selected={mode === "all_time"}
          onClick={() => doiChe("all_time")}
        >
          Toàn thời gian
        </button>
        <button
          type="button"
          role="tab"
          className={mode === "weekly" ? "tab-nut tab-chon" : "tab-nut"}
          aria-selected={mode === "weekly"}
          onClick={() => doiChe("weekly")}
        >
          Tuần này
        </button>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={taiLai} />
      ) : loading && !data ? (
        <SkeletonList count={8} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon="👑"
          title="Chưa có ai trên bảng xếp hạng"
          hint={
            mode === "weekly"
              ? "Chưa ai kiếm XP trong tuần này."
              : "Đọc, nghe hoặc tương tác cộng đồng để kiếm XP đầu tiên."
          }
        />
      ) : data ? (
        <>
          <ul className="lb-list" aria-labelledby="lb-title">
            {data.items.map((it) => (
              <HangXepHang key={it.user_id} it={it} />
            ))}
          </ul>

          {profile && data.viewer_entry && !viewerTrongTrang ? (
            <>
              {/* KHONG dung `role="separator"`: vai tro do khong nhan ten tu
                  noi dung theo dac ta ARIA, nen trinh doc man hinh se BO QUA
                  chu "Vị trí của bạn" — dung mot the thuong (vai tro mac
                  dinh "generic") de noi dung van duoc doc binh thuong. */}
              <p className="lb-sep hint">Vị trí của bạn</p>
              <ul className="lb-list" aria-label="Vị trí của bạn">
                <HangXepHang it={data.viewer_entry} />
              </ul>
            </>
          ) : null}

          {data.total > PAGE_SIZE ? (
            <nav className="pager" aria-label="Phân trang">
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                <span aria-hidden="true">←</span> Trang trước
              </button>
              <span className="hint" role="status">
                Trang {page + 1} / {lastPage + 1}
              </span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
                disabled={page >= lastPage}
              >
                Trang sau <span aria-hidden="true">→</span>
              </button>
            </nav>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
