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
 *
 * Sprint UX doc/nghe (2026-09-24) — ba thay doi, deu giu nguyen MOT the:
 *
 * 1. The `<audio>` LUON duoc mount (truoc day chi mount khi da co URL). Doi
 *    chuong chi doi `src` tren CUNG mot phan tu. Ly do: iOS Safari chi cho
 *    `play()` khong-qua-cu-chi tren mot phan tu DA TUNG duoc phat bang cu
 *    chi. Mount lai phan tu moi o moi chuong nghia la "Chương tiếp theo"
 *    (dang nghe -> sang chuong sau) bi chan tren iPhone.
 * 2. `phat()` nhan them Y DINH: bat dau tu giay nao, va co phat ngay khi san
 *    sang khong. Y dinh "phat ngay" CHI duoc truyen tu mot cu chi cua nguoi
 *    dung (bam "Tiếp tục nghe", bam "Chương sau" LUC DANG NGHE) hoac tu mot
 *    yeu cau tuong minh tren URL. Mo trang KHONG BAO GIO tu phat.
 * 3. Nhac nen khong con bi goi thang: engine chi bao "giong doc dang giu
 *    tieng" cho `lib/audioFocus.ts`, noi quyet dinh kenh thap hon lam gi.
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
  isAudioUrlExpired,
  resolveAudio,
  type PlayableAudio,
} from "@/lib/audio";
import { audioFocus } from "@/lib/audioFocus";
import {
  apKhiCoMetadata,
  apKhiSanSang,
  datViTriAnToan,
  laLoiPhatThat,
  quyetDinhKhiLoi,
  yDinhKhiLamMoi,
  type YDinhPhat,
} from "@/lib/audioReload";

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

/** Y dinh kem theo `phat()` — xem ghi chu (2) o dau tep. */
export interface TuyChonPhat {
  /** Bat dau tu giay nay (tiep tuc nghe). */
  batDauTu?: number;
  /** Phat ngay khi san sang. CHI tu cu chi cua nguoi dung. */
  tuPhat?: boolean;
  /** Cho man hinh khoa / tai nghe (Media Session). */
  tieuDeTruyen?: string;
  anhBia?: string | null;
}

export interface DieuKhienAudio {
  batTat: () => void;
  tua: (giay: number) => void;
  /** Tua tuong doi (±10 giay) — doc `currentTime` SONG cua the, khong doc
      state (state tre toi 250ms so voi the). */
  tuaTuongDoi: (giay: number) => void;
  /** Phat / tam dung TUONG MINH (tai nghe, man hinh khoa, doi che do). */
  choPhat: () => void;
  tamDung: () => void;
  datAmLuong: (v: number) => void;
  datTocDo: (v: number) => void;
  /**
   * Bien mot chuong thanh BAI DANG PHAT TOAN CUC. Goi lai voi CUNG chapterId
   * la khong-lam-gi (giu nguyen vi tri/trang thai) — an toan de goi trong
   * `useEffect` moi lan trang doc chuong duoc tham, khong so lap lai. Y dinh
   * (`tuyChon`) van duoc ap cho CUNG chapterId: "Tiếp tục nghe" tren chuong
   * da nap thi tua + phat, khong nap lai.
   */
  phat: (chapterId: string, title: string, tuyChon?: TuyChonPhat) => void;
}

interface Hop {
  trangThai: TrangThaiAudio;
  dieuKhien: DieuKhienAudio;
  /** Tieu de bai dang phat — chuoi rong khi `chapterId` la null. */
  tieuDe: string;
}

const Ngu_canh = createContext<Hop | null>(null);

/** Cac toc do doc duoc — thuan client, chi dat `audio.playbackRate`. */
export const TOC_DO = [0.75, 1, 1.25, 1.5, 1.75, 2];

/** Buoc tua cua nut ±10 giay va phim J/L. */
export const BUOC_TUA = 10;

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
  const soLanLamMoi = useRef(0);
  /** Bai hien tai, doc duoc DONG BO trong `phat()` (state thi chua kip). */
  const trackRef = useRef<Track | null>(null);
  /** Y dinh cho nguon VUA doi (bai moi hoac URL moi), ap mot lan o
      `loadedmetadata` (tua) va `canplay` (phat) — xem `lib/audioReload.ts`. */
  const yDinh = useRef<YDinhPhat | null>(null);
  const thongTin = useRef<{ tieuDeTruyen?: string; anhBia?: string | null }>({});

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

  /* ------------------------------------------------------------ dieu khien */

  const lamMoiUrl = useCallback(
    async (viTriCanKhoiPhuc?: number, tuDongPhat = false): Promise<boolean> => {
      const hienTai = trackRef.current;
      if (!hienTai) return false;
      const a = el.current;
      const resumeTime = viTriCanKhoiPhuc ?? a?.currentTime ?? 0;
      try {
        const moi = await resolveAudio(hienTai.chapterId);
        // Nguoi dung doi chuong trong luc cho URL moi: bo ket qua cu.
        if (trackRef.current?.chapterId !== hienTai.chapterId) {
          moi.revoke?.();
          return false;
        }
        // KHONG tu gan `a.src`: React gan `src={tep.playUrl}` ngay sau day, va
        // gan hai lan la nap hai lan. Vi tri + trang thai phat di qua y dinh.
        yDinh.current = yDinhKhiLamMoi(resumeTime, tuDongPhat);
        thuHoi.current?.();
        thuHoi.current = moi.revoke;
        setTep(moi);
        setLoi("");
        return true;
      } catch {
        setLoi("Không tải được audio. Vui lòng kiểm tra kết nối mạng.");
        return false;
      }
    },
    [],
  );

  const choPhat = useCallback(() => {
    const a = el.current;
    if (!a || !tep) return;
    // URL ky het han trong luc tam dung lau: lay URL moi TRUOC khi phat, dung
    // de trinh duyet thu URL cu, that bai, roi moi vao nhanh `onError`.
    if (isAudioUrlExpired(tep)) {
      void lamMoiUrl(a.currentTime, true);
      return;
    }
    // `play()` tra ve Promise va CO THE bi tu choi (chinh sach tu dong phat,
    // tep hong). Nuot loi im lang se de nguoi dung bam mai khong hieu — nhung
    // `AbortError`/`NotAllowedError` KHONG phai loi cua tep (xem audioReload).
    a.play()
      .then(() => setDaBatDau(true))
      .catch((e) => {
        if (laLoiPhatThat(e)) setLoi("Trình duyệt không cho phát audio này.");
      });
  }, [tep, lamMoiUrl]);

  const tamDung = useCallback(() => {
    const a = el.current;
    if (a) a.pause();
  }, []);

  const batTat = useCallback(() => {
    const a = el.current;
    if (!a || !tep) return;
    if (a.paused) {
      choPhat();
    } else {
      a.pause();
    }
  }, [tep, choPhat]);

  const tua = useCallback(
    async (giay: number) => {
      const a = el.current;
      if (!a) return;
      if (tep && isAudioUrlExpired(tep)) {
        await lamMoiUrl(giay, !a.paused);
        return;
      }
      if (!Number.isFinite(a.duration)) return;
      a.currentTime = Math.min(Math.max(0, giay), a.duration);
      setThoiDiem(a.currentTime);
    },
    [tep, lamMoiUrl],
  );

  const tuaTuongDoi = useCallback(
    (giay: number) => {
      const a = el.current;
      if (!a) return;
      void tua(a.currentTime + giay);
    },
    [tua],
  );

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

  /* -------------------------------------------------------- doi bai dang phat */

  const phat = useCallback(
    (chapterId: string, title: string, tuyChon?: TuyChonPhat) => {
      if (tuyChon && (tuyChon.tieuDeTruyen !== undefined || tuyChon.anhBia !== undefined)) {
        thongTin.current = { tieuDeTruyen: tuyChon.tieuDeTruyen, anhBia: tuyChon.anhBia };
      }
      if (trackRef.current?.chapterId === chapterId) {
        // Bai da nap: ap y dinh ngay tren the dang co, KHONG nap lai.
        const a = el.current;
        if (tuyChon?.batDauTu !== undefined) {
          if (a && a.readyState >= 1) datViTriAnToan(a, tuyChon.batDauTu);
          else yDinh.current = { ...yDinh.current, batDauTu: tuyChon.batDauTu };
        }
        if (tuyChon?.tuPhat) {
          if (a && a.readyState >= 2) choPhat();
          else yDinh.current = { ...yDinh.current, tuPhat: true };
        }
        return;
      }
      yDinh.current = tuyChon ? { batDauTu: tuyChon.batDauTu, tuPhat: tuyChon.tuPhat } : null;
      trackRef.current = { chapterId, title };
      setTrack((hienTai) =>
        hienTai?.chapterId === chapterId ? hienTai : { chapterId, title },
      );
    },
    [choPhat],
  );

  /* --------------------------------------------------------- lay lien ket */

  // Chay lai MOI KHI `track?.chapterId` THAT SU doi — goi `phat()` voi cung
  // chapterId khong lam doi gia tri nay (xem `phat` o tren), nen effect
  // KHONG chay lai va vi tri/trang thai phat duoc giu nguyen. Than effect chi
  // khoi dong promise; moi `setState` nam trong callback — quy tac
  // `react-hooks/set-state-in-effect`.
  useEffect(() => {
    let huy = false;

    // Dung NGAY am thanh cua bai cu: the gio song lau hon moi bai, nen doi
    // chuong ma khong dung thi bai cu con keo dai cho toi khi URL moi ve.
    const a = el.current;
    if (a && a.getAttribute("src")) {
      a.pause();
      a.removeAttribute("src");
      a.load();
    }

    // Dat lai TOAN BO trang thai hien thi cho bai MOI (hoac khi khong con
    // bai nao — `track === null`) — buoc BAT BUOC moi lan chuyen chapterId.
    // Trong `queueMicrotask`, khong goi thang: quy tac
    // `react-hooks/set-state-in-effect` cam `setState` DONG BO trong than
    // effect (cung ly do da ghi o `NavIndicator.tsx`). Microtask nay CHAC
    // CHAN chay truoc bat ky `.then()` nao cua `resolveAudio` ben duoi (Promise
    // do it nhat mot vong mang that, con day la mot microtask thuan).
    queueMicrotask(() => {
      if (huy) return;
      soLanLamMoi.current = 0;
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

  /* -------------------------------------------------- nhuong tieng nhac nen */

  useEffect(() => {
    if (dangPhat) audioFocus.yeuCau("narration");
    else audioFocus.traLai("narration");
  }, [dangPhat]);

  /* ------------------------------------------ man hinh khoa / nut tai nghe */

  // Ham hanh dong doc qua ref: dang ky MOT lan, luon goi ban moi nhat.
  const hanhDong = useRef({ choPhat, tamDung, tuaTuongDoi, tua });
  useEffect(() => {
    hanhDong.current = { choPhat, tamDung, tuaTuongDoi, tua };
  }, [choPhat, tamDung, tuaTuongDoi, tua]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    const dat = (ten: MediaSessionAction, fn: MediaSessionActionHandler | null) => {
      try {
        ms.setActionHandler(ten, fn);
      } catch {
        /* Trinh duyet khong ho tro hanh dong nay. */
      }
    };
    dat("play", () => hanhDong.current.choPhat());
    dat("pause", () => hanhDong.current.tamDung());
    dat("seekbackward", (d) => hanhDong.current.tuaTuongDoi(-(d.seekOffset ?? BUOC_TUA)));
    dat("seekforward", (d) => hanhDong.current.tuaTuongDoi(d.seekOffset ?? BUOC_TUA));
    dat("seekto", (d) => {
      if (typeof d.seekTime === "number") void hanhDong.current.tua(d.seekTime);
    });
    return () => {
      for (const ten of ["play", "pause", "seekbackward", "seekforward", "seekto"] as const) {
        dat(ten, null);
      }
    };
  }, []);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    if (!track || typeof MediaMetadata === "undefined") {
      navigator.mediaSession.metadata = null;
      return;
    }
    const { tieuDeTruyen, anhBia } = thongTin.current;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        artist: tieuDeTruyen || "Fanfic World",
        album: "Fanfic World",
        artwork: anhBia ? [{ src: anhBia }] : [],
      });
    } catch {
      /* Anh bia URL la co the lam MediaMetadata nem — bo qua, khong anh huong phat. */
    }
  }, [track, tep]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    navigator.mediaSession.playbackState = !track ? "none" : dangPhat ? "playing" : "paused";
  }, [track, dangPhat]);

  const capNhatViTriPhien = useCallback(() => {
    const a = el.current;
    if (!a || typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    if (!Number.isFinite(a.duration) || a.duration <= 0) return;
    try {
      navigator.mediaSession.setPositionState({
        duration: a.duration,
        playbackRate: a.playbackRate || 1,
        position: Math.min(a.currentTime, a.duration),
      });
    } catch {
      /* bo qua */
    }
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
    () => ({ batTat, tua, tuaTuongDoi, choPhat, tamDung, datAmLuong, datTocDo, phat }),
    [batTat, tua, tuaTuongDoi, choPhat, tamDung, datAmLuong, datTocDo, phat],
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
        Giao dien nam o `<ChapterPlayer>`, `<ChapterAudioDock>` va
        `<GlobalMiniPlayer>`.

        Van giu `preload="metadata"` de biet thoi luong truoc khi bam phat —
        khong co no thi thanh thoi gian khong ve duoc gi cho toi lan phat dau.

        DUY NHAT mot the o day, va no nam NGOAI `{children}` (trong layout) —
        dieu huong giua cac trang khong lam no unmount. Tu sprint doc/nghe no
        cung KHONG unmount khi doi chuong (ghi chu (1) o dau tep).
      */}
      <audio
        ref={el}
        preload="metadata"
        src={tep?.playUrl}
        onLoadedMetadata={(e) => {
          setThoiLuong(e.currentTarget.duration || 0);
          yDinh.current = apKhiCoMetadata(e.currentTarget, yDinh.current);
          capNhatViTriPhien();
        }}
        onDurationChange={(e) => setThoiLuong(e.currentTarget.duration || 0)}
        onCanPlay={() => {
          soLanLamMoi.current = 0;
          setSanSang(true);
          const { phat: canPhat, conLai } = apKhiSanSang(yDinh.current);
          yDinh.current = conLai;
          if (canPhat) choPhat();
        }}
        onTimeUpdate={(e) => setThoiDiem(e.currentTarget.currentTime)}
        onSeeked={capNhatViTriPhien}
        onRateChange={capNhatViTriPhien}
        onPlay={() => {
          setDangPhat(true);
          setDaXong(false);
          setDaBatDau(true);
          capNhatViTriPhien();
        }}
        onPause={() => setDangPhat(false)}
        onEnded={() => {
          setDangPhat(false);
          setDaXong(true);
        }}
        onError={async () => {
          const a = el.current;
          // Loi do CHINH ta go `src` khi doi chuong — khong phai loi phat.
          if (!a || !a.getAttribute("src")) return;
          const viTri = a.currentTime ?? thoiDiem;
          const dangChay = dangPhat;
          // Tran so lan thu CO GIOI HAN (`quyetDinhKhiLoi`, toi da 2): URL moi
          // van hong thi dung han, khong lap vo tan. `onCanPlay` dat lai dem.
          const { thuLai, soLanMoi } = quyetDinhKhiLoi(soLanLamMoi.current);
          if (!thuLai) {
            console.error(`[AudioEngine] Đã thử làm mới ${soLanLamMoi.current} lần nhưng vẫn lỗi. Dừng thử lại để tránh vòng lặp vô hạn.`);
            setLoi("Không thể phát file âm thanh này sau nhiều lần thử làm mới. Vui lòng kiểm tra lại kết nối mạng hoặc thử lại sau.");
            return;
          }
          soLanLamMoi.current = soLanMoi;
          console.warn(`[AudioEngine] Gặp lỗi hoặc hết hạn URL tại ${viTri}s (lần ${soLanLamMoi.current}/2), đang tự động làm mới...`);
          const thanhCong = await lamMoiUrl(viTri, dangChay);
          if (!thanhCong) {
            setLoi("Không phát được audio. Liên kết có thể đã hết hạn.");
          }
        }}
      />
      {children}
    </Ngu_canh.Provider>
  );
}
