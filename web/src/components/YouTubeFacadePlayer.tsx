"use client";

/**
 * Trinh phat YouTube cua Fanfic World — facade + control bar TUY CHINH (Phan
 * Fanfic Cinema Controls, animation-player-v2-custom-controls; ke thua facade
 * goc tu overnight Phase 5, V6, Phan 5C).
 *
 * KIEN TRUC 5 GIAI DOAN (`giaiDoan`):
 * 1. "facade"    — anh dai dien tinh + nut Play cua Fanfic. CHUA co iframe
 *                  nao trong DOM — khong tai script/tracking cua YouTube
 *                  truoc khi nguoi xem THAT SU muon xem.
 * 2. "khoi-tao"  — vua bam Play, dang cho `loadYouTubeIframeApi()`. Khong co
 *                  iframe nao trong DOM o buoc nay (chi mot khung cho 16:9),
 *                  nen "trang thai dang tai" KHONG BAO GIO la mot lop phu
 *                  tren iframe — luc nay iframe chua ton tai de phu len.
 * 3. "san-sang"  — API da nap thanh cong: nhung iframe voi `controls=0`,
 *                  gan YT.Player, thanh dieu khien Fanfic (YouTubePlayerControls)
 *                  dieu khien HOAN TOAN qua API chinh thuc (playVideo/pauseVideo/
 *                  seekTo/setVolume/mute/unMute...). Day la duong "hanh phuc".
 * 4. "loi-api"   — script IFrame API khong tai duoc (mang cham/bi chan). VAN
 *                  nhung iframe nhung voi `controls=1` (dieu khien GOC cua
 *                  YouTube) de nguoi xem khong bi bo lai voi mot video khong
 *                  dieu khien duoc — controls=0 CHI an toan khi ta CHAC CHAN
 *                  co API thay the.
 * 5. "loi-video" — mot ma loi THAT tu chinh YouTube (2/5/100/101/150, xem
 *                  `thongBaoLoiVideo`) — go iframe, hien thong bao tieng Viet,
 *                  KHONG doan them chi tiet ngoai tai lieu chinh thuc.
 *
 * COMPONENT NAY TU GIU VONG DOI `YT.Player` (khac V1: truoc day trang xem tu
 * `new YT.Player(...)` ben ngoai roi truyen `iframeId` vao day). Cha CHI nhan
 * lai qua callback (`onProgress`/`onError`/`onEnded`/`onPlay`) va KHONG duoc
 * tu tao mot trinh phat thu hai tren cung iframe — day la ly do prop
 * `iframeId` da bi BO HAN: co hai noi cung `new YT.Player` tren mot iframe la
 * cach chac chan nhat de co hai bo interval bao tien do va mot trang thai
 * treo giua hai tap.
 *
 * TUAN THU CHINH SACH YOUTUBE (audit thu cong truoc khi viet, xem bao cao):
 * - CHI dung tham so player CHINH THUC: controls, enablejsapi, playsinline,
 *   origin, autoplay, rel — khong tu bay tham so nao khac.
 * - CHI dung phuong thuc IFrame API CHINH THUC (xem `lib/youtubeIframeApi.ts`).
 * - KHONG BAO GIO dat phan tu nao (bao gom `.yt-controls`) DE LEN TREN iframe —
 *   thanh dieu khien Fanfic luon nam NGOAI, ben duoi/canh khung 16:9, khong
 *   bao gio dung `position:absolute` chong len `<iframe>`.
 * - KHONG dung `youtube.com/embed` — chi `youtube-nocookie.com`.
 * - KHONG long iframe nay trong mot iframe khac (chinh sach 2026 cam nhung
 *   long nhieu cap de "che nguon" — component nay chi tao DUY NHAT mot
 *   `<iframe>` cho moi video).
 * - KHONG che logo/watermark cua YouTube bang CSS — `controls=0` la tham so
 *   CHINH THUC an nut dieu khien cua YouTube, khac hoan toan voi viec dung
 *   overlay che mot player con nguyen ven.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { IconPlay } from "@/components/Icons";
import { YOUTUBE_EMBED_ORIGIN, youtubeThumbnailUrl } from "@/lib/youtubeUrl";
import {
  loadYouTubeIframeApi,
  thongBaoLoiVideo,
  YT_PLAYER_STATE,
  type YTPlayerInstance,
} from "@/lib/youtubeIframeApi";
import { YouTubePlayerControls, type TrangThaiPhat } from "@/components/YouTubePlayerControls";

export { youtubeThumbnailUrl };

/** Bao tien do ve BACKEND moi N giay — throttle nay GIU NGUYEN tu V1, khong
    lien quan gi toi tan so cap nhat CUC BO cua thanh tien do (xem duoi). */
const KHOANG_BAO_CAO_GIAY = 10;

/** Cap nhat hien thi CUC BO (thoi gian/thanh tien do) — chi doc `getCurrentTime()`
    ngay trong trinh duyet, KHONG goi mang, nen tan so cao hon nhieu so
    `KHOANG_BAO_CAO_GIAY` la an toan va can thiet de thanh tien do muot. */
const KHOANG_CAP_NHAT_CUC_BO_MS = 250;

type GiaiDoan = "facade" | "khoi-tao" | "san-sang" | "loi-api" | "loi-video";

interface GoiLaiCha {
  onPlay?: () => void;
  onProgress?: (hienTaiGiay: number, doDaiGiay: number) => void;
  onError?: (thongDiep: string) => void;
  onEnded?: () => void;
}

export function YouTubeFacadePlayer({
  videoId,
  title,
  autoPlay = true,
  onPlay,
  onProgress,
  onError,
  onEnded,
}: {
  videoId: string;
  title: string;
  /** Tu phat NGAY sau khi nguoi dung bam Play (khong tu phat truoc do). */
  autoPlay?: boolean;
  onPlay?: () => void;
  /** Goi moi ~10s trong luc phat — noi goi day THUONG la `api.reportWatchProgress`
      o trang xem, giu nguyen nhip bao cao cua V1, khong tang tan so. */
  onProgress?: (hienTaiGiay: number, doDaiGiay: number) => void;
  /** Video KHONG xem duoc (xoa/rieng tu/tat nhung/loi dinh dang) — component
      nay DA TU hien UI loi day du; cha co the dung callback nay them (vi du
      ghi log) nhung khong bat buoc phai xu ly gi ca. */
  onError?: (thongDiep: string) => void;
  onEnded?: () => void;
}) {
  // `useId()` cua React 19 tra ve dang `:r0:` — hop le voi
  // `document.getElementById` (dung ham YouTube IFrame API su dung) nhung
  // KHONG hop le trong mot CSS selector. Loc lai de `id` cua iframe an toan
  // cho ca hai cach tra cuu va khong phu thuoc dinh dang `useId` cua tung
  // phien ban React.
  const idGoc = useId();
  const iframeId = `yt-player-${idGoc.replace(/[^A-Za-z0-9_-]/g, "")}`;

  const [giaiDoan, setGiaiDoan] = useState<GiaiDoan>("facade");
  const [trangThai, setTrangThai] = useState<TrangThaiPhat>("dang-tai");
  const [hienTai, setHienTai] = useState(0);
  const [doDai, setDoDai] = useState(0);
  const [amLuong, setAmLuong] = useState(100);
  const [daTat, setDaTat] = useState(false);
  const [dangToanManHinh, setDangToanManHinh] = useState(false);
  const [thongDiepLoi, setThongDiepLoi] = useState("");

  const player = useRef<YTPlayerInstance | null>(null);
  const baoTienDo = useRef<ReturnType<typeof setInterval> | null>(null);
  const capNhatCucBo = useRef<ReturnType<typeof setInterval> | null>(null);
  const khungRef = useRef<HTMLDivElement>(null);
  /** Da thao component chua — xem khoi cleanup duoi de biet vi sao can. */
  const daHuy = useRef(false);
  /** Handle `requestAnimationFrame` dang cho, de huy neu thao component. */
  const khungCho = useRef<number | null>(null);

  // Cac interval va cac su kien cua `YT.Player` song ca buoi xem, nhung chung
  // DONG BANG closure cua chinh minh o thoi diem `onReady`. Goi thang prop se
  // giu lai closure CU khi cha render lai (vi du `data` cua trang xem doi) —
  // tuc bao tien do cho TAP SAI. Vi vay moi callback cua cha di qua mot ref
  // luon duoc cap nhat sau moi lan render.
  const goiLai = useRef<GoiLaiCha>({});
  useEffect(() => {
    goiLai.current = { onPlay, onProgress, onError, onEnded };
  }, [onPlay, onProgress, onError, onEnded]);

  useEffect(() => {
    // Dat lai `false` ngay trong than effect: o che do StrictMode (dev) React
    // chay mount -> cleanup -> mount, va lan cleanup do da dat `true`. Neu
    // khong dat lai thi trinh phat khong bao gio khoi tao duoc trong dev.
    daHuy.current = false;
    return () => {
      daHuy.current = true;
      if (khungCho.current !== null) cancelAnimationFrame(khungCho.current);
      if (baoTienDo.current) clearInterval(baoTienDo.current);
      if (capNhatCucBo.current) clearInterval(capNhatCucBo.current);
      // `destroy()` co the nem: React da thao `<iframe>` khoi DOM o pha
      // mutation, con cleanup nay chay SAU do. Mot ngoai le o day se lam vo ca
      // qua trinh thao component (React khong hoan tat commit) — dung luc
      // nguoi xem dang chuyen tap, ket qua la trang treo. Bat lai va bo qua:
      // trinh phat dang bien mat, khong con gi de cuu.
      try {
        player.current?.destroy?.();
      } catch {
        // Khong lam gi — xem ghi chu ngay tren.
      }
      player.current = null;
    };
  }, []);

  // Theo doi toan man hinh qua CHINH API chuan cua trinh duyet (Fullscreen
  // API) — khong tu "gia" trang thai nay, luon doc tu `document.fullscreenElement`.
  useEffect(() => {
    const onFsChange = () => {
      setDangToanManHinh(document.fullscreenElement === khungRef.current);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const guiTienDoNgay = useCallback(() => {
    const p = player.current;
    if (!p) return;
    const vt = p.getCurrentTime?.();
    const dd = p.getDuration?.();
    if (typeof vt !== "number" || Number.isNaN(vt)) return;
    goiLai.current.onProgress?.(vt, dd || 0);
  }, []);

  const batDauXem = useCallback(async () => {
    setGiaiDoan("khoi-tao");
    goiLai.current.onPlay?.();
    let YT;
    try {
      YT = await loadYouTubeIframeApi();
    } catch {
      // API IFrame khong nap duoc (mang cham/bi chan) — chuyen sang nhung
      // iframe voi `controls=1` de nguoi xem VAN dieu khien duoc bang dieu
      // khien GOC cua YouTube, thay vi bi bo lai voi mot video cau cam
      // (controls=0 nhung khong co gi thay the).
      setGiaiDoan("loi-api");
      return;
    }
    // Nguoi xem co the DA roi trang (bam sang tap khac) trong luc cho script
    // IFrame API ve. Cleanup thao component da chay xong o thoi diem nay, nen
    // mot trinh phat tao SAU do se khong bao gio duoc huy — dung dinh nghia
    // cua ro ri: hai bo interval bao tien do va mot iframe mo coi.
    if (daHuy.current) return;
    setGiaiDoan("san-sang");
    // `new YT.Player` can phan tu <iframe id={iframeId}> DA CO trong DOM —
    // doi mot khung hinh (sau khi React commit + trinh duyet ve xong iframe
    // vua duoc dua vao qua setGiaiDoan o tren) roi moi gan API vao.
    khungCho.current = requestAnimationFrame(() => {
      khungCho.current = null;
      if (daHuy.current) return;
      player.current = new YT.Player(iframeId, {
        events: {
          onReady: (e) => {
            // Component co the da bi thao ngay trong khoang cho `onReady` —
            // dung dat interval moi, se khong con ai don chung.
            if (daHuy.current) return;
            setDoDai(e.target.getDuration() || 0);
            setAmLuong(e.target.getVolume());
            setDaTat(e.target.isMuted());
            setTrangThai(
              e.target.getPlayerState() === YT_PLAYER_STATE.PLAYING
                ? "dang-phat"
                : "tam-dung",
            );
            guiTienDoNgay();
            baoTienDo.current = setInterval(guiTienDoNgay, KHOANG_BAO_CAO_GIAY * 1000);
            capNhatCucBo.current = setInterval(() => {
              const hienTaiPlayer = player.current;
              if (!hienTaiPlayer) return;
              const vt = hienTaiPlayer.getCurrentTime?.();
              if (typeof vt === "number" && !Number.isNaN(vt)) setHienTai(vt);
            }, KHOANG_CAP_NHAT_CUC_BO_MS);
          },
          onStateChange: (e) => {
            switch (e.data) {
              case YT_PLAYER_STATE.PLAYING:
                setTrangThai("dang-phat");
                break;
              case YT_PLAYER_STATE.PAUSED:
                setTrangThai("tam-dung");
                break;
              case YT_PLAYER_STATE.BUFFERING:
                setTrangThai("dang-tai");
                break;
              case YT_PLAYER_STATE.ENDED:
                setTrangThai("ket-thuc");
                goiLai.current.onEnded?.();
                break;
              default:
                break;
            }
          },
          onError: (e) => {
            if (baoTienDo.current) clearInterval(baoTienDo.current);
            if (capNhatCucBo.current) clearInterval(capNhatCucBo.current);
            const thongDiep = thongBaoLoiVideo(e.data);
            setThongDiepLoi(thongDiep);
            setGiaiDoan("loi-video");
            goiLai.current.onError?.(thongDiep);
          },
        },
      });
    });
  }, [iframeId, guiTienDoNgay]);

  const togglePlay = useCallback(() => {
    const p = player.current;
    if (!p) return;
    if (trangThai === "ket-thuc") {
      p.seekTo(0, true);
      p.playVideo();
      return;
    }
    if (trangThai === "dang-phat") p.pauseVideo();
    else p.playVideo();
  }, [trangThai]);

  const seekPreview = useCallback((giay: number) => setHienTai(giay), []);

  const seekCommit = useCallback((giay: number) => {
    player.current?.seekTo(giay, true);
    setHienTai(giay);
  }, []);

  const toggleMute = useCallback(() => {
    const p = player.current;
    if (!p) return;
    if (p.isMuted()) {
      p.unMute();
      setDaTat(false);
    } else {
      p.mute();
      setDaTat(true);
    }
  }, []);

  const volumeChange = useCallback(
    (v: number) => {
      const p = player.current;
      if (!p) return;
      p.setVolume(v);
      setAmLuong(v);
      if (v === 0) {
        p.mute();
        setDaTat(true);
      } else if (daTat) {
        p.unMute();
        setDaTat(false);
      }
    },
    [daTat],
  );

  const toggleFullscreen = useCallback(() => {
    const el = khungRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      el.requestFullscreen?.();
    }
  }, []);

  if (giaiDoan === "facade") {
    return (
      // `.yt-facade` PHAI la mot phan tu RIENG bao ngoai `.yt-facade-play`,
      // khong duoc gop chung mot the: xem docstring lich su o CSS (V1).
      <div className="yt-facade">
        <button
          type="button"
          className="yt-facade-play"
          onClick={batDauXem}
          aria-label={`Phát ${title}`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- anh tu YouTube,
              khong phai asset cua Fanfic. */}
          <img src={youtubeThumbnailUrl(videoId)} alt="" />
          <span className="yt-facade-play-icon">
            <IconPlay size={28} />
          </span>
          <span className="yt-facade-title truncate">{title}</span>
        </button>
      </div>
    );
  }

  if (giaiDoan === "khoi-tao") {
    return <div className="sk yt-cinema-stage-sk" aria-label="Đang tải trình phát…" />;
  }

  if (giaiDoan === "loi-video") {
    return (
      <div className="card anim-video-loi" role="alert">
        <p>{thongDiepLoi}</p>
        <p className="hint">Bạn vẫn có thể chuyển sang tập khác bằng điều hướng phía trên.</p>
      </div>
    );
  }

  // "san-sang" hoac "loi-api": iframe da/dang nhung. `controls` khac nhau
  // giua hai truong hop — xem docstring dau file.
  const goc = typeof window !== "undefined" ? window.location.origin : "";
  const params = new URLSearchParams({
    autoplay: autoPlay ? "1" : "0",
    rel: "0",
    playsinline: "1",
    enablejsapi: "1",
    controls: giaiDoan === "san-sang" ? "0" : "1",
    ...(goc ? { origin: goc } : {}),
  });

  return (
    <div className="yt-cinema-fsframe" ref={khungRef}>
      {/* Chi HIEN o che do toan man hinh (CSS `:fullscreen`) — khong lap lai
          tieu de tap da co o dau trang trong che do thuong. */}
      <p className="yt-cinema-fs-title truncate">{title}</p>
      {/*
        "Dim nhe" luc tam dung (Phan tinh chinh UX): CHI mot filter sang/toi
        RAT NHE tren CHINH iframe cua Fanfic (`filter: brightness(85%)`,
        KHONG blur, KHONG che/xoa noi dung) — tao cam giac "da dung hinh"
        dien anh, khong nham muc dich lam mo/an branding cua YouTube. Da tu
        choi huong overlay/filter-manh o nhung lan trao doi truoc vi vi pham
        chinh sach "khong duoc che player" — muc do nay van giu MOI THU
        trong iframe hoan toan doc/nhin ro duoc, chi la sang do hon 15%.
      */}
      <div className={`yt-facade${giaiDoan === "san-sang" && trangThai === "tam-dung" ? " yt-facade-paused" : ""}`}>
        <iframe
          id={iframeId}
          src={`${YOUTUBE_EMBED_ORIGIN}/embed/${videoId}?${params.toString()}`}
          title={title}
          // `allow="fullscreen"` la cach hien dai duy nhat can — them
          // `allowFullScreen` (thuoc tinh cu) se khien trinh duyet canh bao
          // "Allow attribute will take precedence over allowfullscreen".
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
        />
      </div>
      {giaiDoan === "loi-api" ? (
        <p className="hint yt-controls-fallback-notice">
          Bộ điều khiển tuỳ chỉnh không tải được — dùng điều khiển gốc của YouTube phía trên.
        </p>
      ) : (
        <YouTubePlayerControls
          trangThai={trangThai}
          hienTai={hienTai}
          doDai={doDai}
          amLuong={amLuong}
          daTat={daTat}
          dangToanManHinh={dangToanManHinh}
          onTogglePlay={togglePlay}
          onSeekPreview={seekPreview}
          onSeekCommit={seekCommit}
          onToggleMute={toggleMute}
          onVolumeChange={volumeChange}
          onToggleFullscreen={toggleFullscreen}
        />
      )}
    </div>
  );
}
