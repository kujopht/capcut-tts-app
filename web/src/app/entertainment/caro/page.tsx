"use client";

/**
 * Caro 15×15 — Social & Play V1 (gói C).
 *
 *   * LUYỆN VỚI MÁY: chạy ở client, đối thủ luôn ghi rõ "Máy (luyện tập)", không
 *     gửi gì lên máy chủ, không XP/điểm.
 *   * PHÒNG HAI NGƯỜI: hai TÀI KHOẢN khác nhau. Máy chủ giữ bàn cờ, lượt, luật,
 *     thắng/thua, quyết toán XP — trang này chỉ gửi (ô, số thứ tự nước) và vẽ lại
 *     trạng thái máy chủ trả. Kết nối lại = đọc lại phòng theo mã.
 *
 * Vận chuyển: thăm dò HTTP (không WebSocket, không hạ tầng mới). Nhịp lấy từ
 * `/api/games/config` (`poll_ms`); tab ẩn vẫn thăm dò chậm để máy chủ biết bạn
 * còn kết nối (quá `disconnect_grace_seconds` đối thủ có thể nhận thắng).
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { CaroBoard } from "@/components/games/CaroBoard";
import { useAudioEngineOptional } from "@/components/AudioEngine";
import { ApiError, games, type CaroRoom, type GamesConfig } from "@/lib/api";
import { banTrong, botChon, datQuan, doiLuot, duongThang, hetCho, type Quan } from "@/lib/caro";
import { loginHref } from "@/lib/nav";
import { useSession } from "@/lib/session";

type Tab = "may" | "phong";
const TEN_QUAN: Record<Quan, string> = { x: "X", o: "O" };
const LY_DO: Record<string, string> = {
  five: "năm quân liên tiếp",
  draw: "hết chỗ trên bàn",
  resign: "đối thủ đầu hàng",
  timeout: "đối thủ mất kết nối quá lâu",
  abandon: "cả hai rời ván",
};

/* ------------------------------------------------------------ luyện với máy */
function LuyenVoiMay() {
  const [ban, setBan] = useState(banTrong);
  const [ben, setBen] = useState<Quan>("x");
  const [luot, setLuot] = useState<Quan>("x");
  const [cuoi, setCuoi] = useState<number | null>(null);
  const [thang, setThang] = useState<{ ai: Quan | "hoa"; line: number[] } | null>(null);

  const danh = useCallback(
    (i: number, q: Quan, b: string) => {
      const moi = datQuan(b, i, q);
      setBan(moi);
      setCuoi(i);
      const d = duongThang(moi, i);
      if (d) setThang({ ai: q, line: d });
      else if (hetCho(moi)) setThang({ ai: "hoa", line: [] });
      else setLuot(doiLuot(q));
      return moi;
    },
    [],
  );

  useEffect(() => {
    if (thang || luot === ben) return;
    const t = setTimeout(() => danh(botChon(ban, luot), luot, ban), 350);
    return () => clearTimeout(t);
  }, [luot, ben, ban, thang, danh]);

  const moi = (benMoi: Quan) => {
    setBan(banTrong());
    setBen(benMoi);
    setLuot("x");
    setCuoi(null);
    setThang(null);
  };

  const nhanTrangThai = thang
    ? thang.ai === "hoa"
      ? "Hòa — hết chỗ."
      : thang.ai === ben
        ? "Bạn thắng!"
        : "Máy thắng."
    : luot === ben
      ? `Lượt bạn (${TEN_QUAN[ben]})`
      : "Máy đang nghĩ…";

  return (
    <section className="tc-khung stack-2" aria-label="Luyện với máy">
      <div className="tc-so-lieu">
        <span>
          Bạn: <strong>{TEN_QUAN[ben]}</strong>
        </span>
        <span>Đối thủ: Máy (luyện tập)</span>
        <span className="hint">Không tính XP</span>
      </div>
      <p className="tc-luot" aria-live="polite" role="status">
        {nhanTrangThai}
      </p>
      <CaroBoard
        ban={ban}
        nuocCuoi={cuoi}
        duongThang={thang?.line}
        khoa={!!thang || luot !== ben}
        onDanh={(i) => danh(i, ben, ban)}
        nhan="Bàn cờ luyện tập với máy"
      />
      <div className="tc-nut">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => moi(ben)}>
          Ván mới
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => moi(doiLuot(ben))}>
          Đổi bên (bạn cầm {TEN_QUAN[doiLuot(ben)]})
        </button>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ phòng hai người */
function PhongHaiNguoi({ cfg }: { cfg: GamesConfig | null }) {
  const { profile, loading } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [room, setRoom] = useState<CaroRoom | null>(null);
  const [nhapMa, setNhapMa] = useState(() => (params.get("room") ?? "").toUpperCase());
  const [loi, setLoi] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [daChep, setDaChep] = useState(false);
  const guiRef = useRef(false);
  const maRef = useRef<string>("");

  const datPhong = useCallback(
    (r: CaroRoom) => {
      setRoom(r);
      if (maRef.current !== r.code) {
        maRef.current = r.code;
        router.replace(`/entertainment/caro?tab=phong&room=${r.code}`, { scroll: false });
      }
    },
    [router],
  );

  const goi = async (fn: () => Promise<{ room: CaroRoom }>) => {
    if (guiRef.current) return;
    guiRef.current = true;
    setDangGui(true);
    setLoi("");
    try {
      const r = await fn();
      datPhong(r.room);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Thao tác không thành công.");
      if (e instanceof ApiError && e.status === 409 && maRef.current) {
        // Trang thai da doi o may chu — doc lai de khop.
        games.room(maRef.current).then((r) => datPhong(r.room)).catch(() => {});
      }
    } finally {
      guiRef.current = false;
      setDangGui(false);
    }
  };

  // Vao tu lien ket ?room=CODE -> tham gia (hoac ket noi lai neu da ngoi san).
  const daThuVao = useRef(false);
  useEffect(() => {
    const ma = (params.get("room") ?? "").toUpperCase();
    if (!profile || !cfg?.enabled || !ma || daThuVao.current) return;
    daThuVao.current = true;
    void goi(() => games.joinRoom(ma));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile, cfg?.enabled]);

  // Van vua bat dau (lobby -> playing, ke ca dau lai): dua ban co vao tam nhin MOT lan.
  const trangThaiTruoc = useRef<string>("");
  useEffect(() => {
    const st = room?.status ?? "";
    const vuaBatDau = st === "playing" && trangThaiTruoc.current !== "playing";
    trangThaiTruoc.current = st;
    if (vuaBatDau) {
      requestAnimationFrame(() =>
        document.querySelector(".caro-khung")?.scrollIntoView({ block: "nearest", behavior: "smooth" }),
      );
    }
  }, [room?.status, room?.match_no]);

  // Tham do trang thai.
  useEffect(() => {
    if (!room || room.status === "closed") return;
    let huy = false;
    let t: ReturnType<typeof setTimeout>;
    const nhip = () => {
      const an = typeof document !== "undefined" && document.visibilityState === "hidden";
      const co = room.status === "playing" ? cfg?.poll_ms?.playing ?? 1000 : cfg?.poll_ms?.lobby ?? 2500;
      return an ? Math.max(co, 3000) : co;
    };
    const vong = async () => {
      try {
        const r = await games.room(room.code);
        if (!huy) setRoom(r.room);
      } catch {
        /* mat mang tam thoi: thu lai o nhip sau */
      }
      if (!huy) t = setTimeout(vong, nhip());
    };
    t = setTimeout(vong, nhip());
    return () => {
      huy = true;
      clearTimeout(t);
    };
  }, [room?.code, room?.status, cfg?.poll_ms?.playing, cfg?.poll_ms?.lobby]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="hint">Đang kiểm tra đăng nhập…</p>;
  if (!profile)
    return (
      <div className="card tc-chan">
        <p>Phòng hai người cần hai tài khoản đăng nhập khác nhau. Bạn vẫn có thể luyện với máy.</p>
        <Link className="btn btn-primary btn-sm" href={loginHref("/entertainment/caro?tab=phong")} prefetch={false}>
          Đăng nhập
        </Link>
      </div>
    );
  if (!cfg?.enabled)
    return (
      <div className="card tc-chan">
        <p>Máy chủ chưa bật phòng chơi. Bạn vẫn có thể luyện với máy.</p>
      </div>
    );

  if (!room || room.status === "closed" || room.you === null) {
    return (
      <section className="tc-khung stack-2" aria-label="Vào phòng">
        {room?.status === "closed" ? <p role="status">Phòng đã đóng.</p> : null}
        <div className="tc-vao">
          <div className="card stack-2">
            <h2>Tạo phòng riêng</h2>
            <p className="hint">Nhận mã 6 ký tự và liên kết để gửi cho bạn bè. Không có ghép trận ngẫu nhiên.</p>
            <button type="button" className="btn btn-primary" onClick={() => goi(games.createRoom)} disabled={dangGui}>
              Tạo phòng
            </button>
          </div>
          <form
            className="card stack-2"
            onSubmit={(e) => {
              e.preventDefault();
              const ma = nhapMa.trim().toUpperCase();
              if (ma) void goi(() => games.joinRoom(ma));
            }}
          >
            <h2>Vào bằng mã</h2>
            <label className="stack-1">
              <span className="hint">Mã phòng</span>
              <input
                className="input tc-ma"
                value={nhapMa}
                onChange={(e) => setNhapMa(e.target.value.toUpperCase())}
                maxLength={6}
                autoCapitalize="characters"
                autoComplete="off"
                spellCheck={false}
                placeholder="VD: K7PQ2M"
              />
            </label>
            <button type="submit" className="btn btn-secondary" disabled={dangGui || nhapMa.trim().length < 6}>
              Vào phòng
            </button>
          </form>
        </div>
        {loi ? (
          <p className="trang-thai-loi" role="alert">
            {loi}
          </p>
        ) : null}
      </section>
    );
  }

  const toi = room.you;
  const dich = toi === "x" ? "o" : "x";
  const nguoiToi = room.players[toi];
  const nguoiDich = room.players[dich];
  const lienKet = typeof window !== "undefined" ? `${window.location.origin}/entertainment/caro?tab=phong&room=${room.code}` : "";
  const cuoi = room.moves.length ? room.moves[room.moves.length - 1][0] : null;
  const thuong = profile ? room.rewards?.[profile.user_id] : undefined;
  const sanSang = toi === "x" ? room.ready_x : room.ready_o;
  const dichSanSang = toi === "x" ? room.ready_o : room.ready_x;
  const daXinDauLai = toi === "x" ? room.rematch_x : room.rematch_o;
  const dichXinDauLai = toi === "x" ? room.rematch_o : room.rematch_x;

  let trangThai = "";
  if (room.status === "lobby") trangThai = nguoiDich ? (dichSanSang ? "Đối thủ đã sẵn sàng." : "Chờ đối thủ sẵn sàng…") : "Chờ người thứ hai vào phòng…";
  else if (room.status === "playing") trangThai = room.turn === toi ? `Lượt bạn (${TEN_QUAN[toi]})` : `Lượt đối thủ (${TEN_QUAN[dich]})`;
  else if (room.status === "finished")
    trangThai =
      room.winner === "draw"
        ? "Hòa."
        : room.winner === toi
          ? `Bạn thắng — ${LY_DO[room.end_reason] ?? ""}.`
          : room.winner
            ? `Bạn thua — ${room.end_reason === "resign" ? "bạn đã đầu hàng" : room.end_reason === "timeout" ? "bạn mất kết nối quá lâu" : LY_DO[room.end_reason] ?? ""}.`
            : "Ván kết thúc, không có người thắng.";

  const chep = async () => {
    try {
      await navigator.clipboard.writeText(lienKet);
      setDaChep(true);
      setTimeout(() => setDaChep(false), 2000);
    } catch {
      setDaChep(false);
    }
  };

  return (
    <section className="tc-khung stack-2" aria-label={`Phòng ${room.code}`}>
      <div className="tc-phong-dau">
        <div>
          <span className="hint">Mã phòng</span>
          <strong className="tc-ma-hien">{room.code}</strong>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={chep}>
          {daChep ? "Đã chép liên kết" : "Chép liên kết mời"}
        </button>
        <span className="spacer" />
        <span className="hint">Ván {room.match_no}</span>
      </div>

      <div className="tc-ghe">
        {(["x", "o"] as Quan[]).map((s) => {
          const p = room.players[s];
          const laToi = s === toi;
          const ketNoi = laToi ? true : room.opponent_connected;
          return (
            <div key={s} className={`tc-ghe-cho${room.status === "playing" && room.turn === s ? " is-luot" : ""}`}>
              <span className={`tc-quan tc-quan-${s}`} aria-hidden="true">
                {TEN_QUAN[s]}
              </span>
              <span className="tc-ghe-ten">
                {p ? `${p.display_name || p.username}${laToi ? " (bạn)" : ""}` : "Ghế trống"}
              </span>
              {p && !laToi ? <span className={`tc-ket-noi${ketNoi ? " is-on" : ""}`}>{ketNoi ? "đang kết nối" : "mất kết nối"}</span> : null}
              {room.status === "lobby" && p ? (
                <span className="hint">{(s === "x" ? room.ready_x : room.ready_o) ? "sẵn sàng" : "chưa sẵn sàng"}</span>
              ) : null}
            </div>
          );
        })}
      </div>

      <p className="tc-luot" aria-live="polite" role="status">
        {trangThai}
      </p>

      {room.status !== "lobby" ? (
        <CaroBoard
          ban={room.board}
          nuocCuoi={cuoi}
          duongThang={room.win_line}
          khoa={room.status !== "playing" || room.turn !== toi || dangGui}
          onDanh={(i) => goi(() => games.move(room.code, i, room.move_no))}
          nhan={`Bàn cờ phòng ${room.code}`}
        />
      ) : null}

      {room.status === "finished" ? (
        <div className="tc-ket-qua card" role="status">
          {room.settlement !== "settled" ? (
            <p className="hint">Đang quyết toán điểm…</p>
          ) : thuong ? (
            <>
              <p className="tc-xp">{thuong.xp > 0 ? `+${thuong.xp} XP` : "Không cộng XP ván này"}{thuong.points ? ` · +${thuong.points} điểm mùa` : ""}</p>
              {thuong.reasons.length ? (
                <ul className="tc-ly-do">
                  {thuong.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="hint">Ván này không tính điểm.</p>
          )}
        </div>
      ) : null}

      <div className="tc-nut">
        {room.status === "lobby" && nguoiDich && nguoiToi ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => goi(() => games.ready(room.code, !sanSang))} disabled={dangGui}>
            {sanSang ? "Huỷ sẵn sàng" : "Sẵn sàng"}
          </button>
        ) : null}
        {room.status === "playing" && room.can_claim_timeout ? (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => goi(() => games.claimTimeout(room.code))} disabled={dangGui}>
            Đối thủ mất kết nối — nhận thắng
          </button>
        ) : null}
        {room.status === "playing" ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => goi(() => games.resign(room.code))} disabled={dangGui}>
            Đầu hàng
          </button>
        ) : null}
        {room.status === "finished" && nguoiDich ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => goi(() => games.rematch(room.code))} disabled={dangGui || daXinDauLai}>
            {daXinDauLai ? (dichXinDauLai ? "Đang bắt đầu…" : "Chờ đối thủ đồng ý…") : dichXinDauLai ? "Đối thủ muốn đấu lại — Đồng ý" : "Đấu lại"}
          </button>
        ) : null}
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => goi(() => games.leave(room.code))} disabled={dangGui}>
          {room.status === "playing" ? "Rời phòng (tính là đầu hàng)" : "Rời phòng"}
        </button>
      </div>
      {loi ? (
        <p className="trang-thai-loi" role="alert">
          {loi}
        </p>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------ trang */
function CaroNoiDung() {
  const params = useSearchParams();
  const engine = useAudioEngineOptional();
  const [tab, setTab] = useState<Tab>(() => (params.get("tab") === "phong" || params.get("room") ? "phong" : "may"));
  const [cfg, setCfg] = useState<GamesConfig | null>(null);

  useEffect(() => {
    games.config().then(setCfg).catch(() => setCfg({ enabled: false }));
    if (engine?.trangThai.dangPhat) engine.dieuKhien.tamDung();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page stack-3 tro-choi" data-hero-theme="animation">
      <header className="ent-header">
        <div className="ent-header-copy">
          <p className="eyebrow">
            <Link href="/entertainment" prefetch={false}>
              Giải trí
            </Link>{" "}
            / Caro
          </p>
          <h1 className="ent-header-title">Caro 15×15</h1>
          <p className="ent-header-lead">Ai xếp được năm quân (hoặc hơn) liên tiếp theo hàng, cột hay đường chéo trước thì thắng.</p>
        </div>
      </header>

      <div className="tc-thanh" role="tablist" aria-label="Chế độ chơi">
        <button type="button" role="tab" aria-selected={tab === "may"} className={`tc-tab${tab === "may" ? " is-on" : ""}`} onClick={() => setTab("may")}>
          Luyện với máy
        </button>
        <button type="button" role="tab" aria-selected={tab === "phong"} className={`tc-tab${tab === "phong" ? " is-on" : ""}`} onClick={() => setTab("phong")}>
          Phòng 2 người
        </button>
      </div>

      {tab === "may" ? <LuyenVoiMay /> : <PhongHaiNguoi cfg={cfg} />}

      <section className="card tc-luat stack-2" aria-labelledby="caro-luat">
        <h2 id="caro-luat">Luật & điểm</h2>
        <ul>
          <li>Bàn 15×15. X đi trước. Năm quân trở lên liên tiếp là thắng; kín bàn mà không ai thắng là hòa.</li>
          <li>Phòng 2 người: máy chủ giữ bàn cờ và phán thắng thua. Mất kết nối quá {cfg?.disconnect_grace_seconds ?? 45} giây, đối thủ được quyền nhận thắng.</li>
          <li>
            Ván hợp lệ (đủ 10 nước, hoặc thắng/hòa bằng luật): mỗi người +{cfg?.rewards?.match_completed ?? 2} XP, người thắng thêm +{cfg?.rewards?.match_won ?? 3} XP;
            điểm mùa: thắng 3, hòa 1. Tối đa {cfg?.caps?.per_pair_per_day ?? 3} ván tính điểm với cùng một đối thủ mỗi ngày, tối đa {cfg?.caps?.daily_game_xp ?? 30} XP trò chơi mỗi ngày.
          </li>
          <li>Luyện với máy không tính XP hay điểm.</li>
        </ul>
      </section>
    </div>
  );
}

export default function CaroPage() {
  return (
    <Suspense fallback={null}>
      <CaroNoiDung />
    </Suspense>
  );
}
