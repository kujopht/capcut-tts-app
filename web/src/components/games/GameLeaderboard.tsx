"use client";

/**
 * Bảng xếp hạng THEO GAME, THEO MÙA (Social & Play V1, gói C).
 *
 * Tách hẳn với bảng XP tài khoản: điểm Caro (thắng 3 / hòa 1) và điểm Memory
 * (điểm lượt tốt nhất theo độ khó) là hai thang KHÔNG so được với nhau và không
 * so được với XP — nên mỗi game một bảng, mỗi mùa (tháng UTC) một bảng, mùa cũ
 * vẫn xem lại được. Chỉ kết quả máy chủ đã xác thực mới được tính.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Avatar } from "@/components/Avatar";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui";
import { games, type GameLeaderboardItem, type GameLeaderboardPage } from "@/lib/api";
import { DO_KHO, type DoKho } from "@/lib/memoryRunes";
import { errorMessage } from "@/lib/session";

const PAGE_SIZE = 20;

function nhanMua(m: string): string {
  const [y, mo] = m.split("-");
  return y && mo ? `Tháng ${Number(mo)}/${y}` : m;
}

function Hang({ it, game, laBan }: { it: GameLeaderboardItem; game: "caro" | "memory"; laBan: boolean }) {
  const ten = it.display_name || it.username || "Ẩn danh";
  return (
    <li className={laBan ? "lb-row lb-row-you" : "lb-row"}>
      <span className="lb-rank">#{it.rank}</span>
      <Avatar name={ten} avatarUrl={it.avatar_url} className="avatar avatar-sm" />
      <span className="lb-info">
        {it.username ? (
          <Link href={`/u/${it.username}`} className="binh-luan-ten" prefetch={false}>
            {ten}
          </Link>
        ) : (
          <strong>{ten}</strong>
        )}
        <span className="hint">
          {game === "caro"
            ? `${it.wins ?? 0} thắng · ${it.draws ?? 0} hòa · ${it.losses ?? 0} thua`
            : `${it.runs ?? 0} lượt hợp lệ`}
        </span>
      </span>
      <span className="lb-xp">
        {game === "caro" ? `${(it.points ?? 0).toLocaleString("vi-VN")} điểm` : `${(it.best_score ?? 0).toLocaleString("vi-VN")} điểm`}
      </span>
    </li>
  );
}

export function GameLeaderboard({ game, viewerId }: { game: "caro" | "memory"; viewerId: string }) {
  const [mua, setMua] = useState("");
  const [doKho, setDoKho] = useState<DoKho>("normal");
  const [trang, setTrang] = useState(0);
  const [data, setData] = useState<GameLeaderboardPage | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState("");
  const [tatMayChu, setTatMayChu] = useState(false);
  const [lan, setLan] = useState(0);
  const moiNhat = useRef(0);

  const tai = useCallback(() => {
    const ve = moiNhat.current + 1;
    moiNhat.current = ve;
    setDangTai(true);
    setLoi("");
    games
      .leaderboard({ game, season: mua || undefined, difficulty: game === "memory" ? doKho : undefined, limit: PAGE_SIZE, offset: trang * PAGE_SIZE })
      .then((r) => {
        if (moiNhat.current !== ve) return;
        setData(r);
        setTatMayChu(false);
      })
      .catch((e) => {
        if (moiNhat.current !== ve) return;
        if (e?.status === 404) setTatMayChu(true);
        else setLoi(errorMessage(e));
        setData(null);
      })
      .finally(() => {
        if (moiNhat.current === ve) setDangTai(false);
      });
    // `lan` chi de ep tai lai khi bam "Thu lai".
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game, mua, doKho, trang, lan]);

  useEffect(() => {
    queueMicrotask(tai);
  }, [tai]);

  const cuoi = data ? Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1) : 0;
  const banTrongTrang = !!data?.viewer_entry && data.items.some((x) => x.user_id === data.viewer_entry?.user_id);
  const cacMua = data?.seasons?.length ? data.seasons : data?.season ? [data.season] : [];

  return (
    <div className="stack-2">
      <div className="lb-loc">
        <label className="stack-1">
          <span className="hint">Mùa</span>
          <select
            className="input"
            value={mua || data?.season || ""}
            onChange={(e) => {
              setMua(e.target.value);
              setTrang(0);
            }}
            disabled={!cacMua.length}
          >
            {cacMua.map((m) => (
              <option key={m} value={m}>
                {nhanMua(m)}
              </option>
            ))}
          </select>
        </label>
        {game === "memory" ? (
          <label className="stack-1">
            <span className="hint">Độ khó</span>
            <select
              className="input"
              value={doKho}
              onChange={(e) => {
                setDoKho(e.target.value as DoKho);
                setTrang(0);
              }}
            >
              {(Object.keys(DO_KHO) as DoKho[]).map((k) => (
                <option key={k} value={k}>
                  {DO_KHO[k].ten}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <p className="hint lb-luat">
          {game === "caro"
            ? "Điểm mùa: thắng 3, hòa 1 — chỉ ván phòng 2 người hợp lệ do máy chủ xác nhận."
            : "Điểm lượt tốt nhất ở chế độ tính điểm — máy chủ giữ bố cục và đo thời gian."}
        </p>
      </div>

      {tatMayChu ? (
        <EmptyState icon="🎲" title="Trò chơi chưa bật trên máy chủ" hint="Bảng xếp hạng theo game sẽ có khi tính năng được bật." />
      ) : loi ? (
        <ErrorState message={loi} onRetry={() => setLan((v) => v + 1)} />
      ) : dangTai && !data ? (
        <SkeletonList count={6} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={game === "caro" ? "⭕" : "🔮"}
          title="Chưa có ai trong mùa này"
          hint={game === "caro" ? "Chưa có ván phòng 2 người hợp lệ nào." : "Chưa có lượt tính điểm hợp lệ nào ở độ khó này."}
        />
      ) : data ? (
        <>
          <ul className="lb-list" aria-label={`Bảng xếp hạng ${game === "caro" ? "Caro" : "Memory Runes"} ${nhanMua(data.season)}`}>
            {data.items.map((it) => (
              <Hang key={it.user_id} it={it} game={game} laBan={it.user_id === viewerId} />
            ))}
          </ul>
          {data.viewer_entry && !banTrongTrang ? (
            <>
              <p className="lb-sep hint">Vị trí của bạn</p>
              <ul className="lb-list" aria-label="Vị trí của bạn">
                <Hang it={data.viewer_entry} game={game} laBan />
              </ul>
            </>
          ) : null}
          {data.total > PAGE_SIZE ? (
            <nav className="pager" aria-label="Phân trang">
              <button type="button" className="btn btn-sm" onClick={() => setTrang((p) => Math.max(0, p - 1))} disabled={trang === 0}>
                <span aria-hidden="true">←</span> Trang trước
              </button>
              <span className="hint" role="status">
                Trang {trang + 1} / {cuoi + 1}
              </span>
              <button type="button" className="btn btn-sm" onClick={() => setTrang((p) => Math.min(cuoi, p + 1))} disabled={trang >= cuoi}>
                Trang sau <span aria-hidden="true">→</span>
              </button>
            </nav>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
