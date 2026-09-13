"use client";

/**
 * XEM TRUOC — video + loi doc + phu de chong len nhau, MOT dong ho.
 *
 * Cho de sai nhat o day khong phai viec ve, ma la dong bo `<audio>` voi
 * duong thoi gian. Loi doc co the bat dau o giay 12, bi cat mat 3 giay dau,
 * va bi tat tieng — nen "giay thu 20 cua duong thoi gian" khong phai "giay
 * thu 20 cua tep". `giayTrongNguon` lam phep doi do, va o day ta chi sua
 * `currentTime` khi no LECH qua mot nguong: gan lai moi khung hinh se lam
 * chinh trinh duyet giat va phat ra tieng lach tach.
 */

import { useEffect, useRef } from "react";
import {
  type ClipAudio,
  type ClipVideo,
  giayTrongNguon,
  giayTrongVideo,
  nhanGioLe,
  phanDoanTai,
} from "@/lib/media/timeline";
import type { SubtitleSegment } from "@/lib/subtitles/model";

/** Lech bao nhieu giay thi moi keo `<audio>` ve dung cho. */
const NGUONG_LECH = 0.25;

export function Preview({
  video, audio, subs, urlVideo, urlAudio,
  giay, tong, dangPhat, onBatTat, onNhay, datVideo,
}: {
  video: ClipVideo | null;
  audio: ClipAudio | null;
  subs: SubtitleSegment[];
  urlVideo: string;
  urlAudio: string;
  giay: number;
  tong: number;
  dangPhat: boolean;
  onBatTat: () => void;
  onNhay: (g: number) => void;
  datVideo: (el: HTMLVideoElement | null) => void;
}) {
  const vRef = useRef<HTMLVideoElement | null>(null);
  const aRef = useRef<HTMLAudioElement | null>(null);
  const sub = phanDoanTai(subs, giay);

  /* ------------------------------------------------------------- video --- */

  useEffect(() => {
    const el = vRef.current;
    if (!el || !video) return;
    el.volume = video.tatTiengGoc ? 0 : Math.min(1, video.amLuong);
    el.muted = video.tatTiengGoc;
  }, [video]);

  useEffect(() => {
    const el = vRef.current;
    if (!el || !video) return;
    const dich = giayTrongVideo(video, giay);
    if (dich === null) {
      if (!el.paused) el.pause();
      return;
    }
    if (Math.abs(el.currentTime - dich) > NGUONG_LECH) {
      try {
        el.currentTime = dich;
      } catch {
        /* chua nap xong metadata */
      }
    }
    if (dangPhat && el.paused) void el.play().catch(() => undefined);
    if (!dangPhat && !el.paused) el.pause();
  }, [dangPhat, giay, video]);

  /* ------------------------------------------------------------- audio --- */

  useEffect(() => {
    const el = aRef.current;
    if (!el || !audio) return;
    el.volume = audio.tat ? 0 : Math.min(1, audio.amLuong);
    el.muted = audio.tat;
  }, [audio]);

  useEffect(() => {
    const el = aRef.current;
    if (!el || !audio) return;
    const dich = giayTrongNguon(audio, giay);
    if (dich === null) {
      // Ngoai pham vi clip — dung han. Khong `currentTime = 0` o day: lam vay
      // se lam moi lan keo qua mep phat lai mot tieng "pop" tu dau tep.
      if (!el.paused) el.pause();
      return;
    }
    if (Math.abs(el.currentTime - dich) > NGUONG_LECH) {
      try {
        el.currentTime = dich;
      } catch {
        /* chua nap xong metadata */
      }
    }
    if (dangPhat && el.paused) void el.play().catch(() => undefined);
    if (!dangPhat && !el.paused) el.pause();
  }, [audio, dangPhat, giay]);

  const chiAudio = !video || !urlVideo;

  return (
    <section className="mp" aria-label="Xem trước">
      <div className={`mp-khung${chiAudio ? " mp-chi-audio" : ""}`}>
        {video && urlVideo ? (
          <video
            ref={(el) => {
              vRef.current = el;
              datVideo(el);
            }}
            src={urlVideo}
            className="mp-video"
            playsInline
            // Dong ho cua ta dieu khien viec phat; `controls` cua trinh duyet
            // se la mot nguon dieu khien THU HAI va hai cai se danh nhau.
            controls={false}
            preload="metadata"
          />
        ) : (
          <div className="mp-rong">
            <span className="mp-rong-icon" aria-hidden="true">🎧</span>
            <p className="hint">
              {audio
                ? "Chế độ chỉ âm thanh — thêm video bất cứ lúc nào, lời đọc vẫn giữ nguyên."
                : "Tạo lời đọc hoặc thêm video để bắt đầu."}
            </p>
          </div>
        )}

        {sub ? <div className="mp-phu-de"><span>{sub.text}</span></div> : null}
      </div>

      {/* `<audio>` khong bao gio hien — no la mot thiet bi phat, khong phai
          mot dieu khien. Moi nut deu o thanh duoi. */}
      {audio && urlAudio ? (
        <audio ref={aRef} src={urlAudio} preload="metadata" />
      ) : null}

      <div className="mp-dieu-khien">
        <button
          type="button"
          className="btn btn-primary mp-phat"
          onClick={onBatTat}
          aria-label={dangPhat ? "Tạm dừng" : "Phát"}
        >
          {dangPhat ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          className="mp-thanh"
          min={0}
          max={Math.max(0.1, tong)}
          step={0.05}
          value={Math.min(giay, tong)}
          onChange={(e) => onNhay(Number(e.target.value))}
          aria-label="Vị trí phát"
        />
        <span className="mp-gio">
          {nhanGioLe(giay)} / {nhanGioLe(tong)}
        </span>
      </div>
    </section>
  );
}
