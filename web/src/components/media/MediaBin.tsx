"use client";

/**
 * KHO TAI SAN — video, loi doc, phu de cua du an nay.
 *
 * §6 co mot yeu cau nho ma de vi pham: "Do not expose internal IDs such as
 * trk_9f2a...". Moi muc o day BAT BUOC co `nhan` nguoi doc duoc, va `id`
 * chi song trong thuoc tinh `key`/`value` — khong bao gio thanh van ban.
 *
 * Ban #203 da hoc dung bai nay o `StudioAssetPicker`; day la cung nguon du
 * lieu (`/api/studio/assets/{chang}`), chi khac cach bay: mot bo chon thi
 * DONG lai sau khi chon, con mot cai kho thi o lai va duoc cham nhieu lan.
 */

import { useCallback, useRef, useState } from "react";

export interface MucKho {
  id: string;
  nhan: string;
  phu: string;
  /** Da nam tren duong thoi gian chua. */
  dangDung?: boolean;
}

export function MediaBin({
  video, audio, phuDe,
  onChonVideo, onChonAudio, onChonPhuDe,
  onTaiVideo, onTaiAudio, onNhapPhuDe,
  dangTai,
}: {
  video: MucKho[];
  audio: MucKho[];
  phuDe: MucKho[];
  onChonVideo: (id: string) => void;
  onChonAudio: (id: string) => void;
  onChonPhuDe: (id: string) => void;
  onTaiVideo: (f: File) => void;
  onTaiAudio: (f: File) => void;
  onNhapPhuDe: (f: File) => void;
  dangTai: string;
}) {
  return (
    <section className="mb" aria-label="Kho tài sản">
      <Nhom
        ten="Video"
        muc={video}
        onChon={onChonVideo}
        rong="Chưa có video nào."
        nutTai="+ Tải video"
        nhan="video/mp4,video/quicktime,video/webm,video/x-matroska"
        onTai={onTaiVideo}
        dangTai={dangTai === "video"}
      />
      <Nhom
        ten="Lời đọc"
        muc={audio}
        onChon={onChonAudio}
        rong="Tạo lời đọc ở bảng bên dưới, hoặc tải tệp có sẵn."
        nutTai="+ Tải audio"
        nhan="audio/mpeg,audio/mp4,audio/aac,audio/wav,audio/ogg"
        onTai={onTaiAudio}
        dangTai={dangTai === "audio"}
      />
      <Nhom
        ten="Phụ đề"
        muc={phuDe}
        onChon={onChonPhuDe}
        rong="Chưa có phụ đề nào."
        nutTai="+ Nhập SRT/VTT"
        nhan=".srt,.vtt,text/vtt,application/x-subrip,text/plain"
        onTai={onNhapPhuDe}
        dangTai={dangTai === "phu_de"}
      />
    </section>
  );
}

function Nhom({
  ten, muc, onChon, rong, nutTai, nhan, onTai, dangTai,
}: {
  ten: string;
  muc: MucKho[];
  onChon: (id: string) => void;
  rong: string;
  nutTai: string;
  nhan: string;
  onTai: (f: File) => void;
  dangTai: boolean;
}) {
  const nhapRef = useRef<HTMLInputElement | null>(null);
  const [mo, datMo] = useState(true);

  const chonTep = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) onTai(f);
      // Xoa gia tri de chon LAI DUNG tep vua chon van kich hoat `change`.
      e.target.value = "";
    },
    [onTai],
  );

  return (
    <div className="mb-nhom">
      <button
        type="button"
        className="mb-dau"
        aria-expanded={mo}
        onClick={() => datMo((v) => !v)}
      >
        <span className="mb-ten">{ten}</span>
        <span className="mb-dem">{muc.length}</span>
      </button>

      {mo ? (
        <>
          <ul className="mb-ds">
            {muc.length === 0 ? (
              <li className="hint mb-rong">{rong}</li>
            ) : (
              muc.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    className={`mb-muc${m.dangDung ? " mb-dang-dung" : ""}`}
                    onClick={() => onChon(m.id)}
                    title={m.nhan}
                  >
                    <span className="truncate mb-muc-nhan">{m.nhan}</span>
                    <span className="hint mb-muc-phu">
                      {m.dangDung ? "đang dùng" : m.phu}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
          <button
            type="button"
            className="btn btn-sm btn-ghost mb-tai"
            onClick={() => nhapRef.current?.click()}
            disabled={dangTai}
          >
            {dangTai ? "Đang tải…" : nutTai}
          </button>
          <input
            ref={nhapRef}
            type="file"
            accept={nhan}
            className="an-hoan-toan"
            onChange={chonTep}
            tabIndex={-1}
            aria-hidden="true"
          />
        </>
      ) : null}
    </div>
  );
}
