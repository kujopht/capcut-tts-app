"use client";

/**
 * DUONG THOI GIAN — ba lan, mot thuoc do, mot dau phat.
 *
 * Moi phep TOAN o day deu goi sang `@/lib/media/timeline` va kiem duoc khong
 * can trinh duyet. Tep nay chi lam ba viec: ve, bat chuot, va goi nguoc len.
 *
 * KEO dung Pointer Events chu khong phai `mousedown/mousemove`: `setPointer
 * Capture` giu duoc con tro ke ca khi no roi khoi phan tu, nen keo nhanh ra
 * ngoai lane khong lam clip "tuot tay" giua chung. No cung cho cam ung chay
 * cung mot duong ma khong can nhanh `touchstart` rieng.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { SubtitleSegment } from "@/lib/subtitles/model";
import {
  type ClipAudio,
  type ClipVideo,
  type DangChon,
  buocThuocDo,
  chan,
  daiAudio,
  daiVideo,
  diemMoc,
  doiPhanDoan,
  giayThanhPx,
  hut,
  keoMep,
  nhanGio,
  pxMoiGiay,
  pxThanhGiay,
  TOI_THIEU,
} from "@/lib/media/timeline";
import { duongSvg, dinhCao } from "@/lib/media/waveform";

type Keo =
  | { loai: "audio-di"; batDau0: number }
  | { loai: "audio-mep-trai" }
  | { loai: "audio-mep-phai" }
  | { loai: "sub-di"; id: string; start0: number }
  | { loai: "sub-mep"; id: string; mep: "start" | "end" }
  | { loai: "dau-phat" };

export interface TimelineProps {
  video: ClipVideo | null;
  audio: ClipAudio | null;
  subs: SubtitleSegment[];
  urlAudio: string;
  giay: number;
  tong: number;
  chon: DangChon | null;
  onChon: (c: DangChon | null) => void;
  onNhay: (giay: number) => void;
  onAudio: (c: ClipAudio) => void;
  onSub: (s: SubtitleSegment) => void;
  onThemSub: () => void;
  onXoaSub: (id: string) => void;
}

export function Timeline({
  video, audio, subs, urlAudio, giay, tong, chon,
  onChon, onNhay, onAudio, onSub, onThemSub, onXoaSub,
}: TimelineProps) {
  const [phong, datPhong] = useState(1);
  const [song, datSong] = useState<number[]>([]);
  const khung = useRef<HTMLDivElement | null>(null);
  const keo = useRef<Keo | null>(null);

  const px = pxMoiGiay(phong);
  const rong = Math.max(320, giayThanhPx(tong, phong) + 48);

  /* --------------------------------------------------------- dang song --- */

  useEffect(() => {
    let huy = false;
    /*
      CA HAI nhanh di qua duong bat dong bo, ke ca nhanh "khong co audio".

      Goi `datSong([])` THANG trong than effect la mot lan dat state dong bo
      ngay sau render, tuc mot vong render noi tiep — `react-hooks/
      set-state-in-effect` chan dung cho nay. Cho no vao cung mot IIFE giu
      duoc mot duong duy nhat va bo luon cai bay do.
    */
    void (async () => {
      const d = urlAudio ? await dinhCao(urlAudio) : [];
      if (!huy) datSong(d);
    })();
    return () => { huy = true; };
  }, [urlAudio]);

  /* -------------------------------------------------------------- keo ---- */

  const giayTaiX = useCallback(
    (clientX: number) => {
      const el = khung.current;
      if (!el) return 0;
      const r = el.getBoundingClientRect();
      return pxThanhGiay(clientX - r.left + el.scrollLeft, phong);
    },
    [phong],
  );

  const batDauKeo = useCallback(
    (e: React.PointerEvent, k: Keo) => {
      e.preventDefault();
      e.stopPropagation();
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      keo.current = k;
    },
    [],
  );

  const dangKeo = useCallback(
    (e: React.PointerEvent) => {
      const k = keo.current;
      if (!k) return;
      const g = giayTaiX(e.clientX);
      // Nguong hut tinh theo GIAY tu mot khoang pixel co dinh, nen cam giac
      // hut khong doi khi phong to/thu nho.
      const nguong = pxThanhGiay(7, phong);

      if (k.loai === "dau-phat") {
        onNhay(Math.max(0, g));
        return;
      }
      if (!audio && k.loai.startsWith("audio")) return;

      if (k.loai === "audio-di" && audio) {
        const moc = diemMoc(video, null, subs);
        onAudio({ ...audio, batDau: hut(g, moc, nguong) });
        return;
      }
      if (k.loai === "audio-mep-trai" && audio) {
        // Mep trai = cat bot DAU nguon. `batDau` am chinh la phan bi cat,
        // nen keo sang phai qua diem 0 se cat chu khong day clip di.
        const cuoi = audio.catCuoi > 0 ? audio.catCuoi : audio.goc;
        const catToiDa = cuoi - TOI_THIEU;
        const moi = chan(g, -catToiDa, cuoi - TOI_THIEU);
        onAudio({ ...audio, batDau: moi });
        return;
      }
      if (k.loai === "audio-mep-phai" && audio) {
        const catDau = audio.batDau < 0 ? -audio.batDau : 0;
        const trong = g - Math.max(0, audio.batDau) + catDau;
        onAudio({
          ...audio,
          catCuoi: chan(trong, catDau + TOI_THIEU, audio.goc),
        });
        return;
      }
      if (k.loai === "sub-di") {
        const s = subs.find((x) => x.id === k.id);
        if (!s) return;
        const moc = diemMoc(video, audio, subs, k.id);
        onSub(doiPhanDoan(s, hut(g, moc, nguong)));
        return;
      }
      if (k.loai === "sub-mep") {
        const s = subs.find((x) => x.id === k.id);
        if (!s) return;
        const moc = diemMoc(video, audio, subs, k.id);
        onSub(keoMep(s, k.mep, hut(g, moc, nguong)));
      }
    },
    [audio, giayTaiX, onAudio, onNhay, onSub, phong, subs, video],
  );

  const thoiKeo = useCallback((e: React.PointerEvent) => {
    const el = e.currentTarget as HTMLElement;
    if (el.hasPointerCapture?.(e.pointerId)) el.releasePointerCapture(e.pointerId);
    keo.current = null;
  }, []);

  /* ------------------------------------------------------- ban phim ------ */

  const phimClip = useCallback(
    (e: React.KeyboardEvent, apDung: (delta: number) => void) => {
      // Shift = buoc lon. Khong co Shift thi 0.1s — du min de canh loi doc
      // vao mot khau hinh, va do chinh la viec nguoi ta dung ban phim de lam.
      const buoc = e.shiftKey ? 1 : 0.1;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        apDung(-buoc);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        apDung(buoc);
      }
    },
    [],
  );

  /* ------------------------------------------------------------- ve ------ */

  const buoc = buocThuocDo(phong);
  const vach: number[] = [];
  for (let t = 0; t <= tong + buoc; t += buoc) vach.push(t);

  const chonAudio = chon?.loai === "audio";
  const chonVideo = chon?.loai === "video";

  return (
    <section className="tl" aria-label="Dòng thời gian">
      <div className="tl-thanh">
        <div className="row tl-nut">
          <button type="button" className="btn btn-sm" onClick={onThemSub}>
            + Phụ đề tại đầu phát
          </button>
        </div>
        <div className="row tl-phong">
          <label className="hint" htmlFor="tl-phong">Phóng</label>
          <input
            id="tl-phong"
            type="range"
            min={0.25}
            max={6}
            step={0.25}
            value={phong}
            onChange={(e) => datPhong(Number(e.target.value))}
            aria-label="Mức phóng dòng thời gian"
          />
        </div>
      </div>

      {/*
        CUON NGANG NAM O DAY, khong o trang. §14 noi ro: duong thoi gian tu
        cuon ngang, con trang thi khong bao gio duoc tran ngang.
      */}
      <div className="tl-cuon" ref={khung}>
        <div className="tl-trong" style={{ width: rong }}>
          {/* ---------------------------------------------------- thuoc do */}
          <div
            className="tl-thuoc"
            onPointerDown={(e) => {
              batDauKeo(e, { loai: "dau-phat" });
              onNhay(Math.max(0, giayTaiX(e.clientX)));
            }}
            onPointerMove={dangKeo}
            onPointerUp={thoiKeo}
            onPointerCancel={thoiKeo}
            role="presentation"
          >
            {vach.map((t) => (
              <span key={t} className="tl-vach" style={{ left: t * px }}>
                <i />
                <b>{nhanGio(t)}</b>
              </span>
            ))}
          </div>

          {/* -------------------------------------------------- lane VIDEO */}
          <Lane nhan="Video">
            {video ? (
              <button
                type="button"
                className={`tl-clip tl-clip-video${chonVideo ? " tl-chon" : ""}`}
                style={{ left: 0, width: Math.max(8, daiVideo(video) * px) }}
                onClick={() => onChon({ loai: "video" })}
                aria-label={`Video ${video.nhan}`}
                aria-pressed={chonVideo}
              >
                <span className="tl-ten">{video.nhan}</span>
              </button>
            ) : (
              <span className="tl-trong-lane hint">Chưa có video</span>
            )}
          </Lane>

          {/* -------------------------------------------------- lane AUDIO */}
          <Lane nhan="Lời đọc">
            {audio ? (
              <div
                className={`tl-clip tl-clip-audio${chonAudio ? " tl-chon" : ""}${audio.tat ? " tl-tat" : ""}`}
                style={{
                  left: Math.max(0, audio.batDau) * px,
                  width: Math.max(12, daiAudio(audio) * px),
                }}
                /*
                  `role="slider"`: clip nay THUC CHAT la mot dieu khien mot
                  gia tri (diem bat dau tren duong thoi gian) ma nguoi dung
                  keo hoac bam mui ten de doi — dung dinh nghia cua slider,
                  hon la mot nut bam thuong. `aria-valuenow` phai la GIAY,
                  khong phai pixel: gia tri do la thu co y nghia doc lap voi
                  muc phong hien tai.
                */
                role="slider"
                tabIndex={0}
                aria-label={`Lời đọc ${audio.nhan}`}
                aria-valuemin={0}
                aria-valuemax={audio.goc}
                aria-valuenow={Math.max(0, audio.batDau)}
                aria-valuetext={`Bắt đầu ${nhanGio(Math.max(0, audio.batDau))}`}
                onPointerDown={(e) => {
                  onChon({ loai: "audio" });
                  batDauKeo(e, { loai: "audio-di", batDau0: audio.batDau });
                }}
                onPointerMove={dangKeo}
                onPointerUp={thoiKeo}
                onPointerCancel={thoiKeo}
                onKeyDown={(e) => {
                  onChon({ loai: "audio" });
                  phimClip(e, (d) => onAudio({ ...audio, batDau: audio.batDau + d }));
                }}
              >
                {song.length > 0 ? (
                  <svg
                    className="tl-song"
                    viewBox={`0 0 ${song.length} 40`}
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <path d={duongSvg(song, song.length, 40)} />
                  </svg>
                ) : null}
                <span className="tl-ten">{audio.nhan}</span>
                <i
                  className="tl-tay tl-tay-trai"
                  onPointerDown={(e) => batDauKeo(e, { loai: "audio-mep-trai" })}
                  onPointerMove={dangKeo}
                  onPointerUp={thoiKeo}
                  onPointerCancel={thoiKeo}
                  role="presentation"
                />
                <i
                  className="tl-tay tl-tay-phai"
                  onPointerDown={(e) => batDauKeo(e, { loai: "audio-mep-phai" })}
                  onPointerMove={dangKeo}
                  onPointerUp={thoiKeo}
                  onPointerCancel={thoiKeo}
                  role="presentation"
                />
              </div>
            ) : (
              <span className="tl-trong-lane hint">Chưa có lời đọc</span>
            )}
          </Lane>

          {/* ------------------------------------------------- lane PHU DE */}
          <Lane nhan="Phụ đề">
            {subs.length === 0 ? (
              <span className="tl-trong-lane hint">Chưa có phụ đề</span>
            ) : (
              subs.map((s) => {
                const dang = chon?.loai === "phu_de" && chon.id === s.id;
                return (
                  <div
                    key={s.id}
                    className={`tl-clip tl-clip-sub${dang ? " tl-chon" : ""}`}
                    style={{
                      left: s.start * px,
                      width: Math.max(10, (s.end - s.start) * px),
                    }}
                    role="button"
                    tabIndex={0}
                    aria-label={`Phụ đề: ${s.text || "(trống)"}`}
                    aria-pressed={dang}
                    onPointerDown={(e) => {
                      onChon({ loai: "phu_de", id: s.id });
                      batDauKeo(e, { loai: "sub-di", id: s.id, start0: s.start });
                    }}
                    onPointerMove={dangKeo}
                    onPointerUp={thoiKeo}
                    onPointerCancel={thoiKeo}
                    onKeyDown={(e) => {
                      onChon({ loai: "phu_de", id: s.id });
                      if (e.key === "Delete" || e.key === "Backspace") {
                        e.preventDefault();
                        onXoaSub(s.id);
                        return;
                      }
                      phimClip(e, (d) => onSub(doiPhanDoan(s, s.start + d)));
                    }}
                  >
                    <span className="tl-ten">{s.text || "(trống)"}</span>
                    <i
                      className="tl-tay tl-tay-trai"
                      onPointerDown={(e) =>
                        batDauKeo(e, { loai: "sub-mep", id: s.id, mep: "start" })}
                      onPointerMove={dangKeo}
                      onPointerUp={thoiKeo}
                      onPointerCancel={thoiKeo}
                      role="presentation"
                    />
                    <i
                      className="tl-tay tl-tay-phai"
                      onPointerDown={(e) =>
                        batDauKeo(e, { loai: "sub-mep", id: s.id, mep: "end" })}
                      onPointerMove={dangKeo}
                      onPointerUp={thoiKeo}
                      onPointerCancel={thoiKeo}
                      role="presentation"
                    />
                  </div>
                );
              })
            )}
          </Lane>

          {/* ----------------------------------------------------- dau phat */}
          <div className="tl-dau-phat" style={{ left: giay * px }} aria-hidden="true">
            <i />
          </div>
        </div>
      </div>
    </section>
  );
}

function Lane({ nhan, children }: { nhan: string; children: React.ReactNode }) {
  return (
    <div className="tl-lane">
      <span className="tl-lane-nhan">{nhan}</span>
      <div className="tl-lane-than">{children}</div>
    </div>
  );
}
