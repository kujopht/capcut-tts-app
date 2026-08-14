"use client";

/**
 * Dong co phat TOAN CUC — song o `app/layout.tsx`, ngoai cay cua tung trang.
 *
 * MOT the `<audio>` DUY NHAT cho CA UNG DUNG. Truoc day provider nay duoc mo
 * lai o TUNG trang doc chuong (nhan `chapterId`/`title` la prop bat buoc luc
 * mount) — nghia la dieu huong sang `/fanfic`/`/community`/`/account` se THAO
 * ca provider lan the <audio>, va audio dang phat bi CAT NGANG. Da do duoc
 * that: MiniPlayer khong song xuyen route du kien truc component da co san.
 *
 * SUA: provider gio KHONG nhan chapterId/title qua prop. No mang mot BAI
 * DANG TAI (`track`, co the null) trong state cua chinh no, va cong bo mot
 * hanh dong `phat(chapterId, title)` de BAT KY trang nao (trang doc chuong,
 * hoac sau nay la mot nut "Nghe" o Thu vien) goi vao de bien mot chuong
 * thanh BAI DANG PHAT TOAN CUC. Vi provider nam NGOAI `{children}` trong
 * layout, dieu huong giua cac trang chi thay `{children}` — provider VA the
 * <audio> cua no khong bi cham toi.
 *
 * `phat()` la IDEMPOTENT theo chapterId: goi lai VOI CUNG chapterId (vi du
 * quay lai dung trang chuong dang nghe) la mot phep KHONG-LAM-GI — vi tri
 * phat, trang thai dang-phat/tam-dung deu giu nguyen. Chi khi chapterId THAT
 * SU doi thi trang thai moi duoc dat lai va audio moi moi duoc tai.
 *
 * The `<audio>` VAN la dong co phat — khong tu viet lai bang Web Audio API.
 * Cai duoc thay chi la lop VE: giao dien rieng thay cho bo dieu khien mac
 * dinh cua trinh duyet, con phat/dung/tua/am luong deu goi thang vao the do.
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
  /** Chuong dang la bai TOAN CUC hien tai, hoac `null` khi chua ai bam nghe
      gi. Cac component so sanh gia tri nay voi chapterId CUA RIENG chung de
      biet "day co phai audio cua TOI khong" — xem `CommentThread.tsx`. */
  chapterId: string | null;
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
  /**
   * Bien mot chuong thanh BAI DANG PHAT TOAN CUC. Goi lai voi CUNG chapterId
   * la khong-lam-gi (giu nguyen vi tri/trang thai) — an toan de goi trong
   * `useEffect` moi lan trang doc chuong duoc tham, khong so lap lai.
   */
  phat: (chapterId: string, title: string) => void;
}

interface Hop {
  trangThai: TrangThaiAudio;
  dieuKhien: DieuKhienAudio;
  /** Tieu de bai dang phat — chuoi rong khi `chapterId` la null. */
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

/**
 * Nhu `useAudioEngine` nhung tra `null` khi KHONG co provider.
 *
 * Provider gio la TOAN CUC (mount trong layout) nen ham nay hau nhu luon tra
 * ve mot gia tri — nhung van giu ban tuy chon nay cho cac trang render ngoai
 * cay layout thong thuong (vd mot trang loi/gioi han) va cho code cu chua
 * kip doi. Component GOI ham nay VAN PHAI tu so sanh
 * `engine.trangThai.chapterId` voi chapterId cua CHINH NO truoc khi coi day
 * la audio "cua minh" — mot provider toan cuc co the dang phat MOT CHUONG
 * KHAC voi chuong dang xem.
 */
export function useAudioEngineOptional(): Hop | null {
  return useContext(Ngu_canh);
}

interface Track {
  chapterId: string;
  title: string;
}

export function AudioEngineProvider({ children }: { children: React.ReactNode }) {
  const el = useRef<HTMLAudioElement | null>(null);
  const thuHoi = useRef<(() => void) | null>(null);

  const [track, setTrack] = useState<Track | null>(null);
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

  /* -------------------------------------------------------- doi bai dang phat */

  const phat = useCallback((chapterId: string, title: string) => {
    setTrack((hienTai) =>
      hienTai?.chapterId === chapterId ? hienTai : { chapterId, title },
    );
  }, []);

  /* --------------------------------------------------------- lay lien ket */

  // Chay lai MOI KHI `track?.chapterId` THAT SU doi — goi `phat()` voi cung
  // chapterId khong lam doi gia tri nay (xem `phat` o tren), nen effect
  // KHONG chay lai va vi tri/trang thai phat duoc giu nguyen. Than effect chi
  // khoi dong promise; moi `setState` nam trong callback — quy tac
  // `react-hooks/set-state-in-effect`.
  useEffect(() => {
    let huy = false;

    // Dat lai TOAN BO trang thai hien thi cho bai MOI (hoac khi khong con
    // bai nao — `track === null`) — buoc BAT BUOC moi lan chuyen chapterId.
    // Trong `queueMicrotask`, khong goi thang: quy tac
    // `react-hooks/set-state-in-effect` cam `setState` DONG BO trong than
    // effect (cung ly do da ghi o `NavIndicator.tsx`). Microtask nay CHAC
    // CHAN chay truoc bat ky `.then()` nao cua `resolveAudio` ben duoi (Promise
    // do it nhat mot vong mang that, con day la mot microtask thuan).
    queueMicrotask(() => {
      if (huy) return;
      setTep(null);
      setLoi("");
      setSanSang(false);
      setDangPhat(false);
      setDaBatDau(false);
      setDaXong(false);
      setThoiDiem(0);
      setThoiLuong(0);
    });

    if (!track) {
      return () => {
        huy = true;
      };
    }

    resolveAudio(track.chapterId)
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
  }, [track]);

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
      chapterId: track?.chapterId ?? null,
      dangTai: !!track && !tep && !loi,
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
      tenTep: audioFileName(track?.title ?? ""),
    }),
    [track, tep, loi, sanSang, dangPhat, daBatDau, daXong, thoiDiem,
     thoiLuong, amLuong, tocDo],
  );

  const dieuKhien = useMemo<DieuKhienAudio>(
    () => ({ batTat, tua, datAmLuong, datTocDo, phat }),
    [batTat, tua, datAmLuong, datTocDo, phat],
  );

  const hop = useMemo(
    () => ({ trangThai, dieuKhien, tieuDe: track?.title ?? "" }),
    [trangThai, dieuKhien, track],
  );

  return (
    <Ngu_canh.Provider value={hop}>
      {/*
        KHONG dat `controls`: bo dieu khien mac dinh cua trinh duyet khong ve
        gi khi thieu thuoc tinh do, nen the nay vo hinh va chi lam dong co.
        Giao dien nam o `<ChapterPlayer>` va `<MiniPlayer>`/`<GlobalMiniPlayer>`.

        Van giu `preload="metadata"` de biet thoi luong truoc khi bam phat —
        khong co no thi thanh thoi gian khong ve duoc gi cho toi lan phat dau.

        DUY NHAT mot the o day, va no nam NGOAI `{children}` (trong layout) —
        dieu huong giua cac trang khong lam no unmount.
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
