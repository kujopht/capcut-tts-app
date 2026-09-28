/**
 * Cap do TAI KHOAN (XP) — MOT cach hien thi cho moi noi: trang chu, trang tai
 * khoan, ho so cong khai (Sprint 3, Phase 4).
 *
 * Truoc day cung mot cap hien ba kieu: trang chu "Lv. 1 · 9/100 XP", tai khoan
 * "Bậc 1 · …", ho so "… · Lv. 1". Chu "bậc" con de lan voi HANG TAC GIA
 * (`RankBadge`, theo luot nghe hop le) — hai he KHAC NHAU. Quy uoc:
 *
 *   cap tai khoan  -> "Lv. N" (component nay)
 *   hang tac gia   -> "Hạng …" (`RankBadge`)
 *   diem game      -> "điểm mùa" (bang xep hang tung game)
 *
 * Moi so do MAY CHU tinh (`OwnProgress`/`PublicProgress`); component chi ve,
 * khong tu cong XP. Ho so cong khai khong co XP (may chu khong tra) -> chi
 * hien cap + danh xung.
 */

import { ProgressBar } from "@/components/ui";

export function CapDoTaiKhoan({
  level,
  title,
  xp,
  nextXp,
  percent,
  kieu = "gon",
}: {
  level: number;
  title?: string | null;
  /** Vang mat o ho so cong khai. */
  xp?: number;
  nextXp?: number | null;
  percent?: number;
  /** "gon": mot dong (trang chu, ho so). "day": them dong XP + thanh tien trinh (tai khoan). */
  kieu?: "gon" | "day";
}) {
  const coXp = typeof xp === "number";
  const dongXp = coXp ? `${xp}${nextXp ? `/${nextXp}` : ""} XP` : null;
  if (kieu === "gon") {
    return (
      <span className="cap-do cap-do-gon">
        <strong className="cap-do-lv">Lv. {level}</strong>
        {title ? <span className="cap-do-danh-xung">{title}</span> : null}
        {dongXp ? <span className="cap-do-xp">{dongXp}</span> : null}
      </span>
    );
  }
  return (
    <div className="cap-do cap-do-day stack-2">
      <strong>
        <span className="cap-do-lv">Lv. {level}</span>
        {title ? <> · {title}</> : null}
      </strong>
      {coXp ? (
        <span className="hint">
          {dongXp}
          {nextXp ? ` · còn ${Math.max(0, nextXp - (xp ?? 0))} XP để lên Lv. ${level + 1}` : " · đã ở cấp cao nhất"}
        </span>
      ) : null}
      {typeof percent === "number" ? <ProgressBar percent={percent} label={`Tiến trình lên Lv. ${level + 1}`} /> : null}
    </div>
  );
}
