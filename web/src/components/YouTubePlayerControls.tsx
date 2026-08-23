"use client";

/**
 * Thanh dieu khien Fanfic World TUY CHINH cho trinh phat YouTube (Phan Fanfic
 * Cinema Controls, animation-player-v2-custom-controls).
 *
 * Component nay CHI la GIAO DIEN + goi cac callback do `YouTubeFacadePlayer`
 * truyen xuong — moi loi goi API YouTube (playVideo/pauseVideo/seekTo/...)
 * nam o component cha, noi giu `YTPlayerInstance`. Tach rieng de thanh dieu
 * khien test duoc bang doc source (khong can dung DOM gia lap) va de doc.
 *
 * NAM NGOAI khung 16:9 cua iframe — khong bao gio dat de len tren video dang
 * phat, dung yeu cau "khong overlay/che player" cua chinh sach YouTube.
 *
 * HIEU UNG "TAM DIEM" LUC TAM DUNG (Phan tinh chinh UX, sau khi tu choi
 * huong overlay/filter xoa noi dung — xem lich su trao doi): CHI trang tri
 * CHINH thanh dieu khien nay (glow + nut Play dap nhip), khong dung bat ky
 * ky thuat nao tac dong len iframe de che/xoa noi dung cua no. Dim nhe iframe
 * (`filter: brightness(85%)`, KHONG blur) nam o `YouTubeFacadePlayer.tsx`.
 */

import { useState } from "react";
import { dongHo } from "@/lib/time";
import {
  IconPlay,
  IconPause,
  IconReplay,
  IconVolume,
  IconMute,
  IconExpand,
  IconCollapse,
} from "@/components/Icons";

export type TrangThaiPhat = "dang-tai" | "dang-phat" | "tam-dung" | "ket-thuc";

export function YouTubePlayerControls({
  trangThai,
  hienTai,
  doDai,
  amLuong,
  daTat,
  dangToanManHinh,
  onTogglePlay,
  onSeekPreview,
  onSeekCommit,
  onToggleMute,
  onVolumeChange,
  onToggleFullscreen,
}: {
  trangThai: TrangThaiPhat;
  hienTai: number;
  doDai: number;
  amLuong: number;
  daTat: boolean;
  dangToanManHinh: boolean;
  onTogglePlay: () => void;
  /** Goi lien tuc khi keo — CHI cap nhat hien thi cuc bo, khong seekTo. */
  onSeekPreview: (giay: number) => void;
  /** Goi MOT LAN khi tha chuot/nha phim — day moi la luc goi `seekTo`. */
  onSeekCommit: (giay: number) => void;
  onToggleMute: () => void;
  onVolumeChange: (phanTram: number) => void;
  onToggleFullscreen: () => void;
}) {
  // Nhan biet gia tri dang duoc NGUOI DUNG keo (chua tha) de khoi hien thi
  // sai lech mot nhip truoc khi `onSeekPreview` cua cha kip cap nhat `hienTai`.
  const [dangKeo, setDangKeo] = useState<number | null>(null);
  const dangTai = trangThai === "dang-tai";
  // Video dang TAM DUNG — day su chu y ve THANH nay bang glow + nut Play dap
  // nhip, thay vi cham/lam mo noi dung iframe (khong dung overlay/filter xoa
  // noi dung, chi trang tri UI CUA CHINH Fanfic).
  const dangTamDung = trangThai === "tam-dung";

  return (
    <div
      className={`yt-controls${dangTamDung ? " yt-controls-focal" : ""}`}
      role="group"
      aria-label="Điều khiển phát"
    >
      <button
        type="button"
        className={`yt-controls-btn${dangTamDung ? " yt-controls-btn-pulse" : ""}`}
        onClick={onTogglePlay}
        disabled={dangTai}
        aria-label={
          trangThai === "ket-thuc"
            ? "Phát lại"
            : trangThai === "dang-phat"
              ? "Tạm dừng"
              : "Phát"
        }
      >
        {trangThai === "ket-thuc" ? (
          <IconReplay size={20} />
        ) : trangThai === "dang-phat" ? (
          <IconPause size={20} />
        ) : (
          <IconPlay size={20} />
        )}
      </button>

      <span className="yt-controls-time mono" aria-hidden="true">
        {dongHo(dangKeo ?? hienTai)} / {dongHo(doDai)}
      </span>

      <input
        type="range"
        className="yt-controls-seek"
        aria-label="Vị trí phát"
        min={0}
        max={doDai > 0 ? doDai : 0}
        step={0.1}
        value={dangKeo ?? hienTai}
        disabled={dangTai || doDai <= 0}
        onChange={(e) => {
          const giay = Number(e.target.value);
          setDangKeo(giay);
          onSeekPreview(giay);
        }}
        onMouseUp={(e) => {
          const giay = Number((e.target as HTMLInputElement).value);
          setDangKeo(null);
          onSeekCommit(giay);
        }}
        onTouchEnd={(e) => {
          const giay = Number((e.target as HTMLInputElement).value);
          setDangKeo(null);
          onSeekCommit(giay);
        }}
        onKeyUp={(e) => {
          // Phim mui ten cung phai "tha" nhu keo chuot — neu khong seekTo chi
          // chay o lan bam DAU TIEN, cac lan sau chi doi hien thi cuc bo.
          if (
            ["ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"].includes(e.key)
          ) {
            const giay = Number((e.target as HTMLInputElement).value);
            setDangKeo(null);
            onSeekCommit(giay);
          }
        }}
      />

      <button
        type="button"
        className="yt-controls-btn"
        onClick={onToggleMute}
        disabled={dangTai}
        aria-label={daTat ? "Bật tiếng" : "Tắt tiếng"}
      >
        {daTat ? <IconMute size={18} /> : <IconVolume size={18} />}
      </button>

      <input
        type="range"
        className="yt-controls-volume"
        aria-label="Âm lượng"
        min={0}
        max={100}
        step={1}
        value={daTat ? 0 : amLuong}
        disabled={dangTai}
        onChange={(e) => onVolumeChange(Number(e.target.value))}
      />

      <button
        type="button"
        className="yt-controls-btn"
        onClick={onToggleFullscreen}
        aria-label={dangToanManHinh ? "Thoát toàn màn hình" : "Toàn màn hình"}
      >
        {dangToanManHinh ? <IconCollapse size={18} /> : <IconExpand size={18} />}
      </button>
    </div>
  );
}
