"use client";

/**
 * Memory Runes — Social & Play V1 (gói C).
 *
 * Hai chế độ, nói thẳng khác nhau ở đâu:
 *   * LUYỆN TẬP: bố cục xếp ở client, không gửi gì lên máy chủ, không XP, có tạm dừng.
 *   * TÍNH ĐIỂM (cần đăng nhập): máy chủ xếp bài và GIỮ KÍN bố cục; mỗi lần lật là
 *     một yêu cầu, máy chủ trả khóa của đúng thẻ đó. Thời gian do máy chủ đo nên
 *     không có nút tạm dừng. XP/điểm do máy chủ quyết định và hiện ở màn kết quả.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MemoryBoard } from "@/components/games/MemoryBoard";
import { useAudioEngineOptional } from "@/components/AudioEngine";
import { ApiError, games, type GamesConfig, type MemoryRunView } from "@/lib/api";
import { DO_KHO, diemMemory, dongHoGiay, xepBaiLuyenTap, type DoKho } from "@/lib/memoryRunes";
import { loginHref } from "@/lib/nav";
import { useSession } from "@/lib/session";

type CheDo = "luyen" | "diem";
const HIEN_SAI_MS = 800;

/* ------------------------------------------------------------ luyện tập */
function useLuyenTap(doKho: DoKho) {
  const [bai, setBai] = useState<string[]>(() => xepBaiLuyenTap(doKho));
  const [khop, setKhop] = useState<Set<number>>(new Set());
  const [lat, setLat] = useState<number[]>([]);
  const [luot, setLuot] = useState(0);
  const [batDau, setBatDau] = useState<number | null>(null);
  const [dung, setDung] = useState<{ tu: number; cong: number }>({ tu: 0, cong: 0 });
  const [tamDung, setTamDung] = useState(false);
  const [xong, setXong] = useState<number | null>(null);
  /** Dong ho cap nhat bang bo hen gio — render khong duoc tu goi Date.now(). */
  const [bayGio, setBayGio] = useState(0);
  const khoaTam = useRef(false);

  const choiLai = useCallback((dk: DoKho) => {
    setBai(xepBaiLuyenTap(dk));
    setKhop(new Set());
    setLat([]);
    setLuot(0);
    setBatDau(null);
    setDung({ tu: 0, cong: 0 });
    setTamDung(false);
    setXong(null);
    khoaTam.current = false;
  }, []);

  useEffect(() => {
    if (batDau === null || xong !== null || tamDung) return;
    const t = setInterval(() => setBayGio(Date.now()), 1000);
    return () => clearInterval(t);
  }, [batDau, xong, tamDung]);

  const giay = batDau === null ? 0 : Math.max(0, ((xong ?? bayGio) - batDau - dung.cong) / 1000);

  const latThe = (i: number) => {
    if (khoaTam.current || tamDung || xong !== null || khop.has(i) || lat.includes(i)) return;
    if (batDau === null) {
      const bay = Date.now();
      setBatDau(bay);
      setBayGio(bay);
    }
    if (lat.length === 0) {
      setLat([i]);
      return;
    }
    const a = lat[0];
    setLat([a, i]);
    setLuot((l) => l + 1);
    if (bai[a] === bai[i]) {
      const moi = new Set(khop);
      moi.add(a);
      moi.add(i);
      setKhop(moi);
      setLat([]);
      if (moi.size === bai.length) setXong(Date.now());
    } else {
      khoaTam.current = true;
      setTimeout(() => {
        setLat([]);
        khoaTam.current = false;
      }, HIEN_SAI_MS);
    }
  };

  const doiTamDung = () => {
    if (batDau === null || xong !== null) return;
    if (!tamDung) setDung((d) => ({ ...d, tu: Date.now() }));
    else setDung((d) => ({ tu: 0, cong: d.cong + (Date.now() - d.tu) }));
    setTamDung((p) => !p);
  };

  const ngua = new Map<number, string>();
  khop.forEach((i) => ngua.set(i, bai[i]));
  lat.forEach((i) => ngua.set(i, bai[i]));
  return { bai, khop, ngua, luot, giay, tamDung, xong, latThe, doiTamDung, choiLai, daBatDau: batDau !== null };
}

/* ------------------------------------------------------------ trang */
export default function MemoryRunesPage() {
  const { profile, loading } = useSession();
  const engine = useAudioEngineOptional();
  const [cfg, setCfg] = useState<GamesConfig | null>(null);
  const [cheDo, setCheDo] = useState<CheDo>("luyen");
  const [doKho, setDoKho] = useState<DoKho>("normal");
  const luyen = useLuyenTap(doKho);

  // --- tính điểm
  const [run, setRun] = useState<MemoryRunView | null>(null);
  const [tamNgua, setTamNgua] = useState<Map<number, string>>(new Map());
  const [loi, setLoi] = useState("");
  const [dangGoi, setDangGoi] = useState(false);
  const ban = useRef(false);
  const [moc, setMoc] = useState<{ giay: number; luc: number } | null>(null);
  const [nhip, setNhip] = useState(0);

  useEffect(() => {
    games.config().then(setCfg).catch(() => setCfg({ enabled: false }));
  }, []);

  // Một chủ sở hữu giọng đọc: vào chơi thì tạm dừng lời đọc đang phát.
  useEffect(() => {
    if (engine?.trangThai.dangPhat) engine.dieuKhien.tamDung();
    // chi luc vao trang
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const coTinhDiem = !!cfg?.enabled;

  useEffect(() => {
    if (!run || run.status !== "active") return;
    const t = setInterval(() => setNhip(Date.now()), 1000);
    return () => clearInterval(t);
  }, [run]);

  const capNhatRun = (r: MemoryRunView) => {
    const bay = Date.now();
    setRun(r);
    setMoc({ giay: r.elapsed_seconds, luc: bay });
    setNhip(bay);
  };

  const batDauTinhDiem = async () => {
    setLoi("");
    setDangGoi(true);
    try {
      const r = await games.startMemory(doKho);
      setTamNgua(new Map());
      capNhatRun(r.run);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không bắt đầu được lượt chơi.");
    } finally {
      setDangGoi(false);
    }
  };

  const dongBo = async (id: string) => {
    try {
      const r = await games.memoryRun(id);
      setTamNgua(new Map());
      capNhatRun(r.run);
    } catch {
      /* giu trang thai cu, loi da hien */
    }
  };

  const latTinhDiem = async (i: number) => {
    if (!run || run.status !== "active" || ban.current) return;
    ban.current = true;
    setLoi("");
    try {
      const r = await games.flip(run.run_id, i, run.seq);
      capNhatRun(r.run);
      const f = r.flip;
      if (f.first_index === undefined || f.first_index === null) {
        setTamNgua(new Map([[f.index, f.key]]));
        ban.current = false;
      } else if (f.matched) {
        setTamNgua(new Map());
        ban.current = false;
      } else {
        setTamNgua(new Map([[f.first_index, f.first_key ?? ""], [f.index, f.key]]));
        setTimeout(() => {
          setTamNgua(new Map());
          ban.current = false;
        }, HIEN_SAI_MS);
      }
      if (r.run.status === "completed" && !r.run.result) {
        // Quyet toan dang xu ly — doc lai mot lan.
        setTimeout(() => void dongBo(r.run.run_id), 1200);
      }
    } catch (e) {
      ban.current = false;
      if (e instanceof ApiError && e.status === 429) setLoi("Lật chậm lại một chút.");
      else if (e instanceof ApiError && e.status === 409) {
        setLoi(e.message);
        await dongBo(run.run_id);
      } else setLoi(e instanceof Error ? e.message : "Không lật được thẻ.");
    }
  };

  const boLuot = async () => {
    if (!run) return;
    try {
      const r = await games.abandonMemory(run.run_id);
      capNhatRun(r.run);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không bỏ được lượt.");
    }
  };

  const nguaTinhDiem = useMemo(() => {
    const m = new Map<number, string>();
    run?.matched.forEach((x) => m.set(x.index, x.key));
    if (run?.open) m.set(run.open.index, run.open.key);
    tamNgua.forEach((k, i) => m.set(i, k));
    return m;
  }, [run, tamNgua]);
  const khopTinhDiem = useMemo(() => new Set(run?.matched.map((x) => x.index) ?? []), [run]);

  const giayTinhDiem = run
    ? run.status === "active" && moc
      ? moc.giay + Math.max(0, nhip - moc.luc) / 1000
      : run.elapsed_seconds
    : 0;

  const meta = DO_KHO[doKho];
  const dangChoiDiem = run?.status === "active";

  return (
    <div className="page stack-3 tro-choi" data-hero-theme="animation">
      <header className="ent-header">
        <div className="ent-header-copy">
          <p className="eyebrow">
            <Link href="/entertainment" prefetch={false}>
              Giải trí
            </Link>{" "}
            / Memory Runes
          </p>
          <h1 className="ent-header-title">Memory Runes</h1>
          <p className="ent-header-lead">Lật hai thẻ, tìm cặp rune giống nhau. Ít lượt và nhanh thì điểm cao.</p>
        </div>
      </header>

      <div className="tc-thanh" role="tablist" aria-label="Chế độ chơi">
        <button
          type="button"
          role="tab"
          aria-selected={cheDo === "luyen"}
          className={`tc-tab${cheDo === "luyen" ? " is-on" : ""}`}
          onClick={() => setCheDo("luyen")}
          disabled={dangChoiDiem}
        >
          Luyện tập
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={cheDo === "diem"}
          className={`tc-tab${cheDo === "diem" ? " is-on" : ""}`}
          onClick={() => setCheDo("diem")}
        >
          Tính điểm
        </button>
        <label className="tc-do-kho">
          <span>Độ khó</span>
          <select
            className="input"
            value={doKho}
            disabled={dangChoiDiem}
            onChange={(e) => {
              const dk = e.target.value as DoKho;
              setDoKho(dk);
              luyen.choiLai(dk);
            }}
          >
            {(Object.keys(DO_KHO) as DoKho[]).map((k) => (
              <option key={k} value={k}>
                {DO_KHO[k].ten} — {DO_KHO[k].pairs} cặp
              </option>
            ))}
          </select>
        </label>
      </div>

      {cheDo === "luyen" ? (
        <section className="tc-khung stack-2" aria-label="Luyện tập">
          <div className="tc-so-lieu" aria-live="polite">
            <span>Lượt: {luyen.luot}</span>
            <span>Thời gian: {dongHoGiay(luyen.giay)}</span>
            <span>
              Cặp: {luyen.khop.size / 2}/{meta.pairs}
            </span>
            <span className="hint">Luyện tập — không tính XP</span>
          </div>
          <div className="tc-ban-wrap">
            <MemoryBoard
              rows={meta.rows}
              cols={meta.cols}
              ngua={luyen.ngua}
              daKhop={luyen.khop}
              onLat={luyen.latThe}
              khoa={luyen.tamDung || luyen.xong !== null}
            />
            {luyen.tamDung ? <div className="tc-phu">Đang tạm dừng</div> : null}
          </div>
          <div className="tc-nut">
            <button type="button" className="btn btn-secondary btn-sm" onClick={luyen.doiTamDung} disabled={!luyen.daBatDau || luyen.xong !== null}>
              {luyen.tamDung ? "Tiếp tục" : "Tạm dừng"}
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => luyen.choiLai(doKho)}>
              Chơi lại
            </button>
          </div>
          {luyen.xong !== null ? (
            <div className="tc-ket-qua card" role="status">
              <h2>Hoàn thành!</h2>
              <p>
                {luyen.luot} lượt · {dongHoGiay(luyen.giay)} · điểm luyện tập{" "}
                <strong>{diemMemory(meta.pairs, luyen.luot, luyen.giay)}</strong>
              </p>
              <p className="hint">Chế độ luyện tập không gửi kết quả lên máy chủ và không tính XP.</p>
            </div>
          ) : null}
        </section>
      ) : (
        <section className="tc-khung stack-2" aria-label="Tính điểm">
          {loading ? (
            <p className="hint">Đang kiểm tra đăng nhập…</p>
          ) : !profile ? (
            <div className="card tc-chan">
              <p>Đăng nhập để chơi tính điểm và nhận XP. Khách vẫn luyện tập được.</p>
              <Link className="btn btn-primary btn-sm" href={loginHref("/entertainment/memory")} prefetch={false}>
                Đăng nhập
              </Link>
            </div>
          ) : !coTinhDiem ? (
            <div className="card tc-chan">
              <p>Máy chủ chưa bật chế độ tính điểm. Bạn vẫn luyện tập được.</p>
            </div>
          ) : !run || run.status === "abandoned" || run.status === "expired" ? (
            <div className="card tc-chan stack-2">
              {run?.status === "expired" ? <p role="alert">Lượt trước đã hết giờ (tối đa 15 phút).</p> : null}
              <p>
                Máy chủ giữ kín bố cục và đo thời gian. Hoàn thành hợp lệ: <strong>+{cfg?.rewards?.run_completed ?? 2} XP</strong>{" "}
                (tối đa {cfg?.caps?.runs_per_day ?? 5} lượt/ngày, chung giới hạn {cfg?.caps?.daily_game_xp ?? 30} XP trò chơi/ngày).
                Không có tạm dừng.
              </p>
              <button type="button" className="btn btn-primary" onClick={batDauTinhDiem} disabled={dangGoi} aria-busy={dangGoi}>
                Bắt đầu — {meta.ten}
              </button>
            </div>
          ) : (
            <>
              <div className="tc-so-lieu" aria-live="polite">
                <span>Lượt: {run.moves}</span>
                <span>Thời gian: {dongHoGiay(giayTinhDiem)}</span>
                <span>
                  Cặp: {run.matched.length / 2}/{run.pairs}
                </span>
                <span className="hint">Tính điểm — thời gian do máy chủ đo</span>
              </div>
              <div className="tc-ban-wrap">
                <MemoryBoard
                  rows={run.rows}
                  cols={run.cols}
                  ngua={nguaTinhDiem}
                  daKhop={khopTinhDiem}
                  onLat={latTinhDiem}
                  khoa={run.status !== "active"}
                />
              </div>
              {run.status === "active" ? (
                <div className="tc-nut">
                  <button type="button" className="btn btn-ghost btn-sm" onClick={boLuot}>
                    Bỏ lượt (không tính điểm)
                  </button>
                </div>
              ) : null}
              {run.status === "completed" ? (
                <div className="tc-ket-qua card" role="status">
                  <h2>Hoàn thành!</h2>
                  <p>
                    {run.moves} lượt · {dongHoGiay(run.elapsed_seconds)} · điểm <strong>{run.score}</strong>
                  </p>
                  {run.result ? (
                    <>
                      <p className="tc-xp">
                        {run.result.xp_awarded > 0 ? `+${run.result.xp_awarded} XP` : "Không cộng XP lượt này"}
                      </p>
                      {run.result.reasons.length ? (
                        <ul className="tc-ly-do">
                          {run.result.reasons.map((r) => (
                            <li key={r}>{r}</li>
                          ))}
                        </ul>
                      ) : null}
                    </>
                  ) : (
                    <p className="hint">Đang quyết toán điểm…</p>
                  )}
                  <div className="tc-nut">
                    <button type="button" className="btn btn-primary btn-sm" onClick={batDauTinhDiem}>
                      Chơi lượt mới
                    </button>
                    <Link className="btn btn-ghost btn-sm" href="/leaderboard?view=memory" prefetch={false}>
                      Bảng xếp hạng
                    </Link>
                  </div>
                </div>
              ) : null}
            </>
          )}
          {loi ? (
            <p className="trang-thai-loi" role="alert">
              {loi}
            </p>
          ) : null}
        </section>
      )}

      <section className="card tc-luat stack-2" aria-labelledby="mr-luat">
        <h2 id="mr-luat">Luật chơi</h2>
        <ul>
          <li>Lật một thẻ, rồi lật thẻ thứ hai. Cùng rune thì cặp ở lại ngửa; khác thì úp lại.</li>
          <li>Điểm = số cặp × 100 − (lượt thừa × 15) − số giây.</li>
          <li>Bàn phím: phím mũi tên để di chuyển, Enter hoặc Space để lật.</li>
        </ul>
      </section>
    </div>
  );
}
