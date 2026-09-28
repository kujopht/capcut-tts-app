"use client";

/**
 * Trang Giải trí — Social & Play V1.
 *
 * Thứ tự ưu tiên theo brief: chơi ngay (một người), phòng chơi (PR C), bảng
 * xếp hạng, thành tựu. Mỗi thẻ game nói thật chế độ, số người, thời lượng và
 * có tính XP hay không (`lib/games.ts`). Không có số "đang online" hay phòng
 * "đang mở" nào không đọc từ trạng thái sống.
 *
 * NHẠC tạm ẩn qua MỘT cờ (`lib/features.ts`): tắt thì trang không có tab/đầu
 * phát nhạc; `?mode=music` cũ rơi về đây. Mã trình phát vẫn còn nguyên ở
 * `components/entertainment/MusicSection.tsx`.
 *
 * Game 3D là trang tĩnh trong iframe: CHỈ tải khi người chơi mở, và bị gỡ hẳn
 * (giải phóng WebGL, bộ hẹn giờ, âm thanh) khi đóng. Mở game thì tạm dừng lời
 * đọc truyện đang phát — không để hai nguồn tiếng chồng lên nhau.
 */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { IconSparkles } from "@/components/Icons";
import { useAudioEngineOptional } from "@/components/AudioEngine";
import { games as gamesApi } from "@/lib/api";
import { MUSIC_ENABLED } from "@/lib/features";

import { GAMES, nhanCheDo, nhanXp, type GameInfo } from "@/lib/games";

/** Tải lười: nhạc tắt thì mã trình phát không nằm trong gói JS ban đầu của trang (đo bằng build). */
const MusicSection = dynamic(
  () => import("@/components/entertainment/MusicSection").then((m) => m.MusicSection),
  { ssr: false },
);

function TheGame({ g, onChoi, onRoiTrang, mayChuBat }: { g: GameInfo; onChoi: (g: GameInfo) => void; onRoiTrang: () => void; mayChuBat: boolean | null }) {
  return (
    <article className="ent-game-card gt-the" style={{ ["--game-color" as string]: g.color }} aria-labelledby={`gt-${g.id}`}>
      <div className="gt-the-dau">
        <span className="gt-the-icon" aria-hidden="true">
          {g.icon}
        </span>
        <h3 id={`gt-${g.id}`} className="gt-the-ten">
          {g.title}
        </h3>
      </div>
      <p className="hint gt-the-mota">{g.desc}</p>
      <dl className="gt-meta">
        <div>
          <dt>Chế độ</dt>
          <dd>{nhanCheDo(g.cheDo)}</dd>
        </div>
        <div>
          <dt>Người chơi</dt>
          <dd>{g.nguoiChoi}</dd>
        </div>
        <div>
          <dt>Thời lượng</dt>
          <dd>{g.thoiLuong}</dd>
        </div>
        <div>
          <dt>Phần thưởng</dt>
          <dd>{nhanXp(g, mayChuBat)}</dd>
        </div>
      </dl>
      <div className="gt-the-nut">
        {g.href ? (
          <Link href={g.href} className="btn btn-primary btn-sm" prefetch={false} onClick={onRoiTrang}>
            ▶ Chơi ngay
          </Link>
        ) : (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onChoi(g)}>
            ▶ Chơi ngay
          </button>
        )}
        {g.iframe ? (
          <a href={g.iframe} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm" onClick={onRoiTrang}>
            Toàn màn hình ↗
          </a>
        ) : null}
      </div>
    </article>
  );
}

function KhungGame({ g, onDong, onRoiTrang }: { g: GameInfo; onDong: () => void; onRoiTrang: () => void }) {
  return (
    <section className="stack-2 gt-khung" aria-label={`Đang chơi ${g.title}`}>
      <div className="gt-khung-dau">
        <strong>
          <span aria-hidden="true">{g.icon}</span> {g.title}
        </strong>
        <span className="hint">{g.xp ?? "Không tính XP"}</span>
        <span className="spacer" />
        {g.iframe ? (
          <a href={g.iframe} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-ghost" onClick={onRoiTrang}>
            Toàn màn hình ↗
          </a>
        ) : null}
        <button type="button" className="btn btn-sm btn-secondary" onClick={onDong}>
          ✕ Đóng game
        </button>
      </div>
      {/* Chi gan iframe KHI mo — dong la go han, trinh duyet giai phong WebGL/am thanh. */}
      <div className="gt-khung-game">
        <iframe src={g.iframe} title={g.title} allow="fullscreen; autoplay" />
      </div>
    </section>
  );
}

export default function EntertainmentPage() {
  const engine = useAudioEngineOptional();
  const [dangChoi, setDangChoi] = useState<GameInfo | null>(null);
  /** `null` = chua biet (dang hoi may chu). */
  const [mayChuBat, setMayChuBat] = useState<boolean | null>(null);
  useEffect(() => {
    gamesApi.config().then((c) => setMayChuBat(!!c.enabled)).catch(() => setMayChuBat(false));
  }, []);

  // Mot chu so huu giong doc: MOI loi mo game (nut trong trang, "Toan man hinh"
  // o tab moi, lien ket sang trang game) deu tam dung loi doc dang phat truoc.
  const tamDungLoiDoc = useCallback(() => {
    if (engine?.trangThai.dangPhat) engine.dieuKhien.tamDung();
  }, [engine]);
  const moGame = useCallback(
    (g: GameInfo) => {
      tamDungLoiDoc();
      setDangChoi(g);
    },
    [tamDungLoiDoc],
  );

  return (
    <div className="page stack-3 giai-tri" data-hero-theme="animation">
      <header className="ent-header">
        <div className="ent-header-copy">
          <div className="ent-header-eyebrow">
            <IconSparkles size={12} />
            <span>KHU GIẢI TRÍ</span>
          </div>
          <h1 className="ent-header-title">Giải trí</h1>
          <p className="ent-header-lead">Mini-game, bảng xếp hạng và thành tựu.</p>
        </div>
      </header>

      {dangChoi ? (
        <KhungGame g={dangChoi} onDong={() => setDangChoi(null)} onRoiTrang={tamDungLoiDoc} />
      ) : (
        <>
          <section className="stack-2" aria-labelledby="gt-choi-ngay">
            <h2 className="section-title" id="gt-choi-ngay">
              Chơi ngay
            </h2>
            <div className="ent-games-grid gt-luoi">
              {GAMES.map((g) => (
                <TheGame key={g.id} g={g} onChoi={moGame} onRoiTrang={tamDungLoiDoc} mayChuBat={mayChuBat} />
              ))}
            </div>
          </section>

          <section className="stack-2" aria-labelledby="gt-xep-hang">
            <h2 className="section-title" id="gt-xep-hang">
              Bảng xếp hạng &amp; thành tựu
            </h2>
            <div className="gt-lien-ket">
              <Link href="/leaderboard" className="card gt-lien-ket-the" prefetch={false}>
                <strong>Bảng xếp hạng</strong>
                <span className="hint">XP của cả tài khoản — tuần này và toàn thời gian. Điểm từ đọc, nghe, viết.</span>
              </Link>
              <Link href="/account" className="card gt-lien-ket-the" prefetch={false}>
                <strong>Thành tựu &amp; vật phẩm</strong>
                <span className="hint">Cấp độ, danh xưng, khung avatar đã mở khoá.</span>
              </Link>
            </div>
          </section>

          {MUSIC_ENABLED ? (
            <MusicSection />
          ) : (
            <p className="hint gt-nhac-sau">Âm nhạc — sẽ quay lại sau.</p>
          )}
        </>
      )}
    </div>
  );
}
