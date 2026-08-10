"use client";

/**
 * Dong co phat cho trang doc chuong.
 *
 * MOT the `<audio>` DUY NHAT, do context nay so huu. Trinh phat lon o dau
 * trang va thanh nho dinh o duoi deu doc cung mot trang thai va goi cung mot
 * bo dieu khien — chung KHONG phai hai trinh phat.
 *
 * Tao the `<audio>` thu hai la loi de mac nhat o cho nay: hai the cung phat
 * mot file thi nguoi dung nghe thanh tieng vong, va bam dung o thanh nay khong
 * dung thanh kia.
 *
 * The `<audio>` VAN la dong co phat — khong tu viet lai bang Web Audio API.
 * Cai duoc thay chi la lop VE: giao dien rieng thay cho bo dieu khien mac dinh
 * cua trinh duyet, con phat/dung/tua/am luong deu goi thang vao the do.
 *
 * Cach lay URL khong doi: van la `lib/audio.ts::resolveAudio`, ke ca duong R2
 * ky san lan duong stream qua backend. Xem ghi chu o tep do de biet vi sao
 * khong gan thang `/api/audio/{id}`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  audioFileName,
  resolveAudio,
  type PlayableAudio,
} from "@/lib/audio";

// Xuat lai de hai trinh phat chi phai import tu MOT cho.
export { dongHo } from "@/lib/time";
import { errorMessage } from "@/lib/session";

export interface TrangThaiAudio {
  /** Dang hoi backend URL phat. */
  dangTai: boolean;
  /** Loi khi lay URL hoac khi trinh duyet khong phat duoc. */
  loi: string;
  /** Trinh duyet da du du lieu de bat dau phat. */
  sanSang: boolean;
  dangPhat: boolean;
  /** Da tung bam phat lan nao chua — thanh nho chi hien sau lan do. */
  daBatDau: boolean;
  daXong: boolean;
  /** Giay. `0` khi chua biet thoi luong. */
  thoiDiem: number;
  thoiLuong: number;
  amLuong: number;
  tocDo: number;
  /** `null` khi chua lay duoc lien ket. */
  tep: PlayableAudio | null;
  tenTep: string;
}

export interface DieuKhienAudio {
  batTat: () => void;
  tua: (giay: number) => void;
  datAmLuong: (v: number) => void;
  datTocDo: (v: number) => void;
}

interface Hop {
  trangThai: TrangThaiAudio;
  dieuKhien: DieuKhienAudio;
  tieuDe: string;
}

const Ngu_canh = createContext<Hop | null>(null);

/** Cac toc do doc duoc — thuan client, chi dat `audio.playbackRate`. */
export const TOC_DO = [0.75, 1, 1.25, 1.5, 2];

export function useAudioEngine(): Hop {
  const hop = useContext(Ngu_canh);
  if (!hop) {
    throw new Error("useAudioEngine phai nam trong <AudioEngineProvider>");
  }
  return hop;
}

export function AudioEngineProvider({
  chapterId,
  title,
  children,
}: {
  chapterId: string;
  title: string;
  children: React.ReactNode;
}) {
  const el = useRef<HTMLAudioElement | null>(null);
  const thuHoi = useRef<(() => void) | null>(null);

  const [tep, setTep] = useState<PlayableAudio | null>(null);
  const [loi, setLoi] = useState("");
  const [sanSang, setSanSang] = useState(false);
  const [dangPhat, setDangPhat] = useState(false);
  const [daBatDau, setDaBatDau] = useState(false);
  const [daXong, setDaXong] = useState(false);
  const [thoiDiem, setThoiDiem] = useState(0);
  const [thoiLuong, setThoiLuong] = useState(0);
  const [amLuong, setAmLuongState] = useState(1);
  const [tocDo, setTocDoState] = useState(1);

  /* --------------------------------------------------------- lay lien ket */

  // Than effect chi khoi dong promise; moi `setState` nam trong callback —
  // quy tac `react-hooks/set-state-in-effect`.
  useEffect(() => {
    let huy = false;
    resolveAudio(chapterId)
      .then((xong) => {
        if (huy) {
          xong.revoke?.();
          return;
        }
        thuHoi.current = xong.revoke;
        setTep(xong);
      })
      .catch((cause) => {
        if (!huy) setLoi(errorMessage(cause));
      });
    return () => {
      huy = true;
      thuHoi.current?.();
      thuHoi.current = null;
    };
  }, [chapterId]);

  /* ------------------------------------------------------------ dieu khien */

  const batTat = useCallback(() => {
    const a = el.current;
    if (!a || !tep) return;
    if (a.paused) {
      // `play()` tra ve Promise va CO THE bi tu choi (chinh sach tu dong phat,
      // tep hong). Nuot loi im lang se de nguoi dung bam mai khong hieu.
      a.play()
        .then(() => setDaBatDau(true))
        .catch(() => setLoi("Trình duyệt không cho phát audio này."));
    } else {
      a.pause();
    }
  }, [tep]);

  const tua = useCallback((giay: number) => {
    const a = el.current;
    if (!a || !Number.isFinite(a.duration)) return;
    a.currentTime = Math.min(Math.max(0, giay), a.duration);
    setThoiDiem(a.currentTime);
  }, []);

  const datAmLuong = useCallback((v: number) => {
    const a = el.current;
    const clamp = Math.min(1, Math.max(0, v));
    if (a) a.volume = clamp;
    setAmLuongState(clamp);
  }, []);

  const datTocDo = useCallback((v: number) => {
    const a = el.current;
    if (a) a.playbackRate = v;
    setTocDoState(v);
  }, []);

  /* ---------------------------------------------------------------- ghep */

  const trangThai = useMemo<TrangThaiAudio>(
    () => ({
      dangTai: !tep && !loi,
      loi,
      sanSang,
      dangPhat,
      daBatDau,
      daXong,
      thoiDiem,
      thoiLuong,
      amLuong,
      tocDo,
      tep,
      tenTep: audioFileName(title),
    }),
    [tep, loi, sanSang, dangPhat, daBatDau, daXong, thoiDiem, thoiLuong,
     amLuong, tocDo, title],
  );

  const dieuKhien = useMemo<DieuKhienAudio>(
    () => ({ batTat, tua, datAmLuong, datTocDo }),
    [batTat, tua, datAmLuong, datTocDo],
  );

  const hop = useMemo(
    () => ({ trangThai, dieuKhien, tieuDe: title }),
    [trangThai, dieuKhien, title],
  );

  return (
    <Ngu_canh.Provider value={hop}>
      {/*
        KHONG dat `controls`: bo dieu khien mac dinh cua trinh duyet khong ve
        gi khi thieu thuoc tinh do, nen the nay vo hinh va chi lam dong co.
        Giao dien nam o `<ChapterPlayer>` va `<MiniPlayer>`.

        Van giu `preload="metadata"` de biet thoi luong truoc khi bam phat —
        khong co no thi thanh thoi gian khong ve duoc gi cho toi lan phat dau.
      */}
      {tep ? (
        <audio
          ref={el}
          preload="metadata"
          src={tep.playUrl}
          onLoadedMetadata={(e) => setThoiLuong(e.currentTarget.duration || 0)}
          onDurationChange={(e) => setThoiLuong(e.currentTarget.duration || 0)}
          onCanPlay={() => setSanSang(true)}
          onTimeUpdate={(e) => setThoiDiem(e.currentTarget.currentTime)}
          onPlay={() => {
            setDangPhat(true);
            setDaXong(false);
            setDaBatDau(true);
          }}
          onPause={() => setDangPhat(false)}
          onEnded={() => {
            setDangPhat(false);
            setDaXong(true);
          }}
          onError={() =>
            setLoi("Không phát được audio. Liên kết có thể đã hết hạn.")
          }
        />
      ) : null}
      {children}
    </Ngu_canh.Provider>
  );
}

