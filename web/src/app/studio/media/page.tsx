"use client";

/**
 * MEDIA STUDIO — trinh sua video/phu de TUY CHON tren MOT duong thoi gian.
 *
 * Audio Studio la noi tao loi doc chinh. Trang nay nhan mot audio da co qua
 * `?audio=` de nguoi dung co the dat no vao video ma khong phai tai xuong va
 * tai len lai. `/studio/video` va `/studio/subtitle` chi la duong dan tuong
 * thich tro vao day.
 *
 * NGUON SU THAT: `VideoProject` o backend giu video/loi doc/phu de + cac
 * thong so cat-lech-am luong. Duong thoi gian la mot CACH NHIN cua ban ghi
 * do, khong phai mot ban sao song song — moi thao tac keo tha cuoi cung deu
 * quy ve mot `PATCH`.
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  api,
  studio,
  videoStudio,
  type TtsJob,
  type VideoProject,
  type VideoSources,
  type Voice,
} from "@/lib/api";
import { errorMessage as loiCuaApi, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { defaultVoiceId } from "@/lib/voices";
import { ensureStudioNovel } from "@/lib/workspace";
import { loginHref } from "@/lib/nav";
import { useJobTracker } from "@/lib/useJobTracker";
import { dangChayJob } from "@/lib/jobs";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import { MediaBin, type MucKho } from "@/components/media/MediaBin";
import { Preview } from "@/components/media/Preview";
import { Timeline } from "@/components/media/Timeline";
import { Inspector } from "@/components/media/Inspector";
import { TtsPanel, type YeuCauTts } from "@/components/media/TtsPanel";
import { useDongHo } from "@/components/media/useDongHo";
import {
  type ClipAudio,
  type ClipVideo,
  type DangChon,
  tongDai,
} from "@/lib/media/timeline";
import {
  type SubtitleSegment,
  nhapSrtHoacVtt,
  sapXep,
  taoPhanDoan,
  xoaPhanDoan,
  xuatSrt,
} from "@/lib/subtitles/model";

/** Cho bao lau sau lan sua cuoi moi ghi len may chu. */
const CHO_GHI_MS = 900;
/** Phu de ghi cham hon: moi lan ghi tao MOT tai san moi. */
const CHO_GHI_SUB_MS = 3000;

/**
 * Nhan doc duoc cho MOT tep video, suy tu khoa doi tuong.
 *
 * `/api/video/assets` (VideoAsset) khong co truong `label` — khac
 * `/api/studio/assets/{stage}` da tra san nhan. Khoa doi tuong do MAY CHU
 * sinh (xem `upload_session.khoa_moi`), nen phan ten trong khoa thuong la
 * mot chuoi hex vo nghia; cung logic voi `_ten_tep` o backend
 * (`studio_service.py`), chi lam lai o client vi endpoint nay khong di qua
 * lop do.
 */
function tenTuKhoa(khoa: string): string {
  const ten = khoa.split("/").pop() || khoa;
  const goc = ten.replace(/\.[^.]+$/, "");
  const laHex = goc.length >= 16 && /^[0-9a-fA-F]+$/.test(goc);
  return laHex ? "Video đã tải lên" : ten;
}

/**
 * Media la buoc thu hai sau Audio, khong phai mot TTS Studio thu hai. Khong
 * ve preview/timeline khi chua co video: day la luc nguoi dung can mot loi
 * moi ro rang, khong phai mot trinh soan day cac panel trong.
 */
function KhoiDongMedia({
  tenAudio,
  dangTai,
  onTaiVideo,
}: {
  tenAudio: string;
  dangTai: boolean;
  onTaiVideo: (file: File) => void;
}) {
  const nhapRef = useRef<HTMLInputElement | null>(null);

  return (
    <section className="media-khoi-dong card stack-3" aria-labelledby="media-khoi-dong-title">
      <span className="eyebrow">VIDEO EDITOR</span>
      <div className="stack-2">
        <h2 className="section-title" id="media-khoi-dong-title">Thêm video để bắt đầu chỉnh</h2>
        <p className="hint">
          {tenAudio
            ? <>Audio <strong>{tenAudio}</strong> đã sẵn sàng. Chọn video để mở trình chỉnh sửa.</>
            : "Chọn video trước, rồi thêm một audio có sẵn hoặc quay lại Audio Studio để tạo lời đọc."}
        </p>
      </div>
      <div className="row">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => nhapRef.current?.click()}
          disabled={dangTai}
        >
          {dangTai ? "Đang tải video…" : "+ Tải video"}
        </button>
        <Link className="btn btn-ghost" href="/studio/audio" prefetch={false}>Quay lại Audio Studio</Link>
      </div>
      <input
        ref={nhapRef}
        type="file"
        accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
        className="an-hoan-toan"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onTaiVideo(file);
          event.target.value = "";
        }}
        tabIndex={-1}
        aria-hidden="true"
      />
    </section>
  );
}

function MediaStudio() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { profile, loading: dangNapPhien } = useSession();

  const [duAn, datDuAn] = useState<VideoProject | null>(null);
  const [nguon, datNguon] = useState<VideoSources | null>(null);
  const [subs, datSubs] = useState<SubtitleSegment[]>([]);
  const [chon, datChon] = useState<DangChon | null>(null);
  const [voices, datVoices] = useState<Voice[]>([]);
  const [giong, datGiong] = useState("");
  const [khoAudio, datKhoAudio] = useState<MucKho[]>([]);
  const [khoVideo, datKhoVideo] = useState<MucKho[]>([]);
  const [khoSub, datKhoSub] = useState<MucKho[]>([]);
  const [srcVideo, datSrcVideo] = useState("");
  const [srcAudio, datSrcAudio] = useState("");
  const [dangNap, datDangNap] = useState(true);
  const [loi, datLoi] = useState("");
  const [dangTai, datDangTai] = useState("");
  const [dangTaoTts, datDangTaoTts] = useState(false);
  const [moTaoAudio, datMoTaoAudio] = useState(false);
  const [loiTts, datLoiTts] = useState("");
  const [dangXuat, datDangXuat] = useState(false);
  const [trangThaiXuat, datTrangThaiXuat] = useState("");
  const [urlXuat, datUrlXuat] = useState("");

  const studioId = params.get("studio") || "";

  /*
    Ban chup du an cho cac callback chay NGOAI vong render (job xong, poll).

    Dua thang `duAn` vao dependency cua chung se tao mot vong: job tracker
    goi nguoc vao mot ham phu thuoc `duAn`, con ham do lai `datDuAn`. Mot ref
    cat vong do ma khong lam mat tinh dung — thu ta can o day la "du an NAO
    dang mo NGAY LUC NAY", chinh xac la thu ref giu.
  */
  const duAnRef = useRef<VideoProject | null>(null);
  useEffect(() => {
    duAnRef.current = duAn;
  }, [duAn]);

  /* ================================================== clip tu ban ghi ==== */

  const video: ClipVideo | null = useMemo(() => {
    if (!duAn?.video_asset_id || !nguon) return null;
    return {
      assetId: duAn.video_asset_id,
      nhan: khoVideo.find((m) => m.id === duAn.video_asset_id)?.nhan || "Video",
      catDau: duAn.video_trim_start,
      catCuoi: duAn.video_trim_end,
      goc: nguon.video_duration || 0,
      amLuong: duAn.video_volume,
      tatTiengGoc: duAn.mute_original_audio,
    };
  }, [duAn, khoVideo, nguon]);

  const audio: ClipAudio | null = useMemo(() => {
    if (!duAn?.audio_track_id || !nguon) return null;
    return {
      nguonId: duAn.audio_track_id,
      nhan: khoAudio.find((m) => m.id === duAn.audio_track_id)?.nhan || "Lời đọc",
      batDau: duAn.audio_offset,
      catCuoi: duAn.audio_trim_end,
      goc: nguon.audio_duration || 0,
      amLuong: duAn.audio_volume,
      tat: duAn.audio_volume === 0,
    };
  }, [duAn, khoAudio, nguon]);

  const tong = useMemo(() => tongDai(video, audio, subs), [video, audio, subs]);
  const dongHo = useDongHo(tong);
  const { nhay, datVideo: ganVideoEl } = dongHo;

  /* ========================================================= nap kho ===== */

  const napKho = useCallback(async () => {
    /*
      Video KHONG di qua `studio.assets("video", ...)`.

      Chang "video" cua Studio Project (#203) liet ke `VideoProject` — CA MOT
      du an Composer, dung cho luong "gan mot ban video DA XONG vao du an
      Studio". Media Bin can thu KHAC HAN: tep MP4 THO de dat len lane video
      cua duong thoi gian nay, dung `MediaAsset.asset_id` — chinh xac hinh
      dang ma `video_asset_id` cua `VideoProject` doi hoi. Nguon dung la
      `/api/video/assets` (cung API videoStudio.listAssets da dung tu ban
      Video Composer V1), loc theo `media_type === "video"`.
    */
    const [a, va, s] = await Promise.all([
      studio.assets("audio", studioId).catch(() => ({ assets: [] })),
      videoStudio.listAssets().catch(() => ({ assets: [] })),
      studio.assets("phu_de", studioId).catch(() => ({ assets: [] })),
    ]);
    const v = va.assets
      .filter((x) => x.media_type === "video")
      .map((x) => ({
        id: x.asset_id,
        label: tenTuKhoa(x.object_key),
        detail: x.duration_seconds > 0 ? `${Math.round(x.duration_seconds)}s` : "",
      }));
    return { a: a.assets, v, s: s.assets };
  }, [studioId]);

  const veKho = useCallback(
    (
      ds: { id: string; label: string; detail: string }[],
      dangDung: string,
    ): MucKho[] =>
      ds.map((x) => ({
        id: x.id,
        nhan: x.label,
        phu: x.detail,
        dangDung: x.id === dangDung,
      })),
    [],
  );

  /* ====================================================== nap du an ====== */

  const moDuAn = useCallback(
    async (id: string) => {
      const r = await videoStudio.getProject(id);
      datDuAn(r.project);
      datNguon(r.sources);

      const [v, a] = await Promise.all([
        videoStudio.resolveMedia(r.sources.video_url, r.sources.video_stream),
        videoStudio.resolveMedia(r.sources.audio_url, r.sources.audio_stream),
      ]);
      datSrcVideo(v.src);
      datSrcAudio(a.src);

      // Phu de: doc tep SRT/VTT roi bien thanh phan doan de sua tren lane.
      if (r.sources.subtitle_url || r.sources.subtitle_stream) {
        try {
          const { src } = await videoStudio.resolveMedia(
            r.sources.subtitle_url, r.sources.subtitle_stream);
          if (src) {
            const txt = await (await fetch(src)).text();
            datSubs(nhapSrtHoacVtt(txt));
          }
        } catch {
          // Phu de hong KHONG duoc chan ca trinh soan — video va loi doc van
          // sua duoc, va nguoi dung nhap lai mot tep khac la xong.
          datSubs([]);
        }
      } else {
        datSubs([]);
      }
      return r.project;
    },
    [],
  );

  /* ============================================================ TTS ====== */

  /*
    Job TTS di qua `useJobTracker` — CUNG mot vong theo doi ma `/studio/content`
    dung, khong phai mot vong `setTimeout` rieng.

    Hai dieu duoc bao toan tu ban Audio Studio cu, va ca hai la nhung thu
    nguoi dung nhan ra ngay khi mat:

      * RoI TRANG ROI QUAY LAI van thay job dang chay. Khoi phuc bang cach
        hoi `listJobs()` MOT lan luc nap, khong phai bang `localStorage` —
        mot job song o may chu, va trinh duyet khong phai nguon su that ve no.
      * Tien do ve bang `<JobProgress>`, khong tu ve mot thanh khac. Hai
        thanh tien do trong mot san pham la hai cho ke chuyen khac nhau.

    Khai bao TRUOC hieu ung khoi dong: hieu ung do goi `khoiPhuc` ngay khi
    nap trang.
  */
  /** Job xong -> track moi vao kho VA len thang duong thoi gian. */
  const ganTrackMoi = useCallback(
    async (j: TtsJob) => {
      try {
        const kho = await napKho();
        const moi = kho.a[0];
        datKhoAudio(veKho(kho.a, moi?.id || ""));
        const id = duAnRef.current?.project_id;
        if (!moi || !id) return;
        const p = await videoStudio.patchProject(id, { audio_track_id: moi.id });
        datDuAn(p.project);
        datNguon(p.sources);
        const a = await videoStudio.resolveMedia(
          p.sources.audio_url, p.sources.audio_stream);
        datSrcAudio(a.src);
        datChon({ loai: "audio" });
        toast.push("info", "Đã tạo lời đọc.");
      } catch (e) {
        datLoiTts(loiCuaApi(e));
      } finally {
        datDangTaoTts(false);
      }
    },
    [napKho, toast, veKho],
  );

  const jobs = useJobTracker({
    onCompleted: (j) => void ganTrackMoi(j),
    onFailed: (j) => {
      datLoiTts(j.error_message || "Tạo lời đọc thất bại.");
      datDangTaoTts(false);
    },
  });
  const { khoiPhuc, theoDoi } = jobs;

  /* ========================================================== khoi dong == */

  const daKhoiDong = useRef(false);

  useEffect(() => {
    if (dangNapPhien || !profile || daKhoiDong.current) return;
    daKhoiDong.current = true;

    void (async () => {
      try {
        const [ds, gs, kho, js, al] = await Promise.all([
          videoStudio.listProjects(),
          api.voices().catch(() => ({ voices: [] as Voice[], count: 0 })),
          napKho(),
          api.listJobs().catch(() => ({ jobs: [] as TtsJob[], count: 0 })),
          videoStudio.audioLibrary().catch(() => ({ tracks: [] })),
        ]);
        datVoices(gs.voices);
        datGiong(defaultVoiceId(gs.voices));
        /*
          Khoi phuc job dang chay TU BACKEND — day la duong duy nhat "roi
          trang roi quay lai" van thay dung job. Job xong trong luc vang mat
          se tu goi `onCompleted` (xem `useJobTracker`), dung nhu vua tao no.
        */
        khoiPhuc(js.jobs);
        if (js.jobs.some(dangChayJob)) datDangTaoTts(true);

        /*
          "Dùng trong Video" den tu MOT trong hai duong:

            ?audio=<track_id>      — biet dich xac ban nao ("Nghe" cua Audio
                                      Studio cu di duong nay).
            ?chapter=<chapter_id>  — chi biet chuong (thu vien chi co chuong
                                      trong tay, khong biet track_id).

          Giai `?chapter=` o DAY, khong mo them tham so cho API: danh sach
          audio vua nap ve (`al.tracks`) da mang ca hai id, nen tra cuu la
          mot phep tim trong bo nho chu khong phai mot lan goi mang nua.
        */
        const tuChuong = params.get("chapter");
        const tuAudio =
          params.get("audio") ||
          (tuChuong
            ? al.tracks.find((x) => x.chapter_id === tuChuong)?.track_id || ""
            : "");

        const moId = params.get("project");
        let hienTai: VideoProject | null = null;

        if (moId) {
          hienTai = await moDuAn(moId);
        } else if (tuAudio || studioId || ds.projects.length === 0) {
          /*
            Tao MOT du an, roi doi URL sang `?project=<id>` ngay.

            `?studio=`/`?audio=`/`?chapter=` la MOT MENH LENH ("mo mot du an
            media moi cho thu nay"), con URL thi o lai tren thanh dia chi.
            Khong doi thi mot lan bam F5 la them mot du an rong nua — dung
            khuyet tat da sua o #203.
          */
          const r = await videoStudio.createProject("Dự án media", tuAudio);
          if (studioId) {
            await studio
              .attach(studioId, "video", r.project.project_id)
              .catch(() => undefined);
          }
          hienTai = await moDuAn(r.project.project_id);
          window.history.replaceState(
            null, "",
            `${window.location.pathname}?project=${encodeURIComponent(r.project.project_id)}`,
          );
        } else {
          hienTai = await moDuAn(ds.projects[0].project_id);
        }

        datKhoAudio(veKho(kho.a, hienTai?.audio_track_id || ""));
        datKhoVideo(veKho(kho.v, hienTai?.video_asset_id || ""));
        datKhoSub(veKho(kho.s, hienTai?.subtitle_asset_id || ""));
      } catch (e) {
        datLoi(loiCuaApi(e));
      } finally {
        datDangNap(false);
      }
    })();
  }, [dangNapPhien, khoiPhuc, moDuAn, napKho, params, profile, studioId, veKho]);

  /* ======================================================= ghi ban va ==== */

  const hoGhi = useRef<ReturnType<typeof setTimeout> | null>(null);

  const ghi = useCallback(
    (va: Parameters<typeof videoStudio.patchProject>[1]) => {
      const id = duAn?.project_id;
      if (!id) return;
      if (hoGhi.current) clearTimeout(hoGhi.current);
      hoGhi.current = setTimeout(() => {
        void videoStudio
          .patchProject(id, va)
          .then((r) => {
            datDuAn(r.project);
            datNguon(r.sources);
          })
          .catch((e) => toast.error(loiCuaApi(e)));
      }, CHO_GHI_MS);
    },
    [duAn?.project_id, toast],
  );

  /* ------------------------------------------- clip -> ban va -> may chu */

  const doiAudio = useCallback(
    (c: ClipAudio) => {
      datDuAn((d) =>
        d ? {
          ...d,
          audio_offset: c.batDau,
          audio_trim_end: c.catCuoi,
          audio_volume: c.tat ? 0 : c.amLuong,
        } : d);
      ghi({
        audio_offset: c.batDau,
        audio_trim_end: c.catCuoi,
        audio_volume: c.tat ? 0 : c.amLuong,
      });
    },
    [ghi],
  );

  const doiVideo = useCallback(
    (c: ClipVideo) => {
      datDuAn((d) =>
        d ? {
          ...d,
          video_trim_start: c.catDau,
          video_trim_end: c.catCuoi,
          video_volume: c.amLuong,
          mute_original_audio: c.tatTiengGoc,
        } : d);
      ghi({
        video_trim_start: c.catDau,
        video_trim_end: c.catCuoi,
        video_volume: c.amLuong,
        mute_original_audio: c.tatTiengGoc,
      });
    },
    [ghi],
  );

  /* ========================================================= phu de ====== */

  const srtDaGhi = useRef("");
  const hoGhiSub = useRef<ReturnType<typeof setTimeout> | null>(null);

  const ghiPhuDe = useCallback(
    (ds: SubtitleSegment[]) => {
      const id = duAn?.project_id;
      if (!id) return;
      if (hoGhiSub.current) clearTimeout(hoGhiSub.current);
      hoGhiSub.current = setTimeout(() => {
        const srt = xuatSrt(ds);
        // MOI lan ghi tao mot `MediaAsset` moi, nen chi ghi khi NOI DUNG doi.
        // Khong co phep so sanh nay thi keo mot phan doan qua lai se de lai
        // hang chuc tai san giong het nhau.
        if (!srt.trim() || srt === srtDaGhi.current) return;
        srtDaGhi.current = srt;
        void (async () => {
          try {
            const f = new File([srt], "phu-de.srt", { type: "application/x-subrip" });
            const r = await studio.upload(f, "subtitles");
            const p = await videoStudio.patchProject(id, {
              subtitle_asset_id: r.asset.asset_id,
            });
            datDuAn(p.project);
            datNguon(p.sources);
          } catch (e) {
            toast.error(loiCuaApi(e));
          }
        })();
      }, CHO_GHI_SUB_MS);
    },
    [duAn?.project_id, toast],
  );

  const doiSub = useCallback(
    (s: SubtitleSegment) => {
      datSubs((ds) => {
        const moi = sapXep(ds.map((x) => (x.id === s.id ? s : x)));
        ghiPhuDe(moi);
        return moi;
      });
    },
    [ghiPhuDe],
  );

  const themSub = useCallback(() => {
    datSubs((ds) => {
      const moi = sapXep([...ds, taoPhanDoan(dongHo.giay, dongHo.giay + 2, "")]);
      ghiPhuDe(moi);
      return moi;
    });
  }, [dongHo.giay, ghiPhuDe]);

  const boSub = useCallback(
    (id: string) => {
      datSubs((ds) => {
        const moi = xoaPhanDoan(ds, id);
        ghiPhuDe(moi);
        return moi;
      });
      datChon(null);
    },
    [ghiPhuDe],
  );

  /* ============================================================ TTS ====== */

  /*
    Nho LAN GUI GAN NHAT — cung ly do da co o Audio Studio cu.

    Khoa van tay o backend la `owner + chapter + content_hash`: no nhan ra
    hai lan bam la MOT chi khi ca `chapter_id` LAN noi dung deu trung. Tao
    mot chuong MOI moi lan bam se pha khoa do — hai lan bam CUNG mot doan
    van se tao hai chuong, hai job, ton gap doi hang doi TTS. Nho lai chuong
    vua tao cho DUNG noi dung nay la thu duy nhat giu khoa do co tac dung.
  */
  const daGuiTts = useRef<{ tieuDe: string; vanBan: string; chapterId: string } | null>(null);

  const taoTts = useCallback(
    async (y: YeuCauTts) => {
      datDangTaoTts(true);
      datLoiTts("");
      try {
        const truoc = daGuiTts.current;
        const khongDoi =
          truoc !== null && truoc.tieuDe === y.tieuDe && truoc.vanBan === y.vanBan;
        let chapterId = khongDoi ? truoc.chapterId : "";
        if (!chapterId) {
          /*
            §5 Flow A (CHỈ ÂM THANH) khong doi hoi mot truyen fanfic co san —
            "paste text -> chọn giọng -> tạo TTS -> nghe -> tải xuống", cham
            het. `ensureStudioNovel()` lay-hoac-tao mot kho chua AN cho dung
            viec nay (tag `audio-studio`), giong het Audio Studio cu: kho do
            bi loc khoi moi danh sach fanfic (`fanficOnly`) nen khong lo lan
            vao trang kham pha hay "Nội dung".
          */
          const kho = await ensureStudioNovel();
          const ten =
            y.tieuDe ||
            `${y.vanBan.trim().slice(0, 40)}${y.vanBan.trim().length > 40 ? "…" : ""}`;
          const ch = await api.createChapter(kho.novel_id, ten, y.vanBan, 1);
          chapterId = ch.chapter.chapter_id;
        }
        const jr = await api.createJob(chapterId, y.giong, y.tocDo);
        daGuiTts.current = { tieuDe: y.tieuDe, vanBan: y.vanBan, chapterId };
        theoDoi(jr.job);
        // `reused` den TU BACKEND — frontend chi noi lai, khong tu suy ra da
        // trung hay chua.
        toast.push(
          "info",
          jr.reused ? "Dùng lại audio đã tạo." : "Đã đưa vào hàng đợi.",
        );
      } catch (e) {
        datLoiTts(loiCuaApi(e));
        datDangTaoTts(false);
      }
    },
    [theoDoi, toast],
  );

  /* ========================================================= tai len ===== */

  const taiLen = useCallback(
    async (f: File, loai: "video" | "audio" | "subtitles") => {
      if (!duAn) return;
      datDangTai(loai === "subtitles" ? "phu_de" : loai);
      try {
        if (loai === "subtitles") {
          // Phu de NHAP vao duoc doc thang o trinh duyet roi bay len lane —
          // khong phai tai len roi tai ve.
          const txt = await f.text();
          const ds = nhapSrtHoacVtt(txt);
          datSubs(ds);
          ghiPhuDe(ds);
          toast.push("info", `Đã nhập ${ds.length} đoạn phụ đề.`);
          return;
        }
        const r = await studio.upload(f, loai);
        const kho = await napKho();
        if (loai === "video") {
          const p = await videoStudio.patchProject(duAn.project_id, {
            video_asset_id: r.asset.asset_id,
          });
          datDuAn(p.project);
          datNguon(p.sources);
          const v = await videoStudio.resolveMedia(
            p.sources.video_url, p.sources.video_stream);
          datSrcVideo(v.src);
          datKhoVideo(veKho(kho.v, r.asset.asset_id));
          datChon({ loai: "video" });
        } else {
          datKhoAudio(veKho(kho.a, duAn.audio_track_id));
        }
        toast.push("info", "Đã thêm vào kho.");
      } catch (e) {
        toast.error(loiCuaApi(e));
      } finally {
        datDangTai("");
      }
    },
    [duAn, ghiPhuDe, napKho, toast, veKho],
  );

  const chonTuKho = useCallback(
    async (loai: "video" | "audio" | "phu_de", id: string) => {
      if (!duAn) return;
      try {
        const va =
          loai === "video" ? { video_asset_id: id }
            : loai === "audio" ? { audio_track_id: id }
              : { subtitle_asset_id: id };
        const p = await videoStudio.patchProject(duAn.project_id, va);
        datDuAn(p.project);
        datNguon(p.sources);
        if (loai === "video") {
          const v = await videoStudio.resolveMedia(
            p.sources.video_url, p.sources.video_stream);
          datSrcVideo(v.src);
          datKhoVideo((k) => k.map((m) => ({ ...m, dangDung: m.id === id })));
          datChon({ loai: "video" });
        } else if (loai === "audio") {
          const a = await videoStudio.resolveMedia(
            p.sources.audio_url, p.sources.audio_stream);
          datSrcAudio(a.src);
          datKhoAudio((k) => k.map((m) => ({ ...m, dangDung: m.id === id })));
          datChon({ loai: "audio" });
        } else {
          const { src } = await videoStudio.resolveMedia(
            p.sources.subtitle_url, p.sources.subtitle_stream);
          if (src) datSubs(nhapSrtHoacVtt(await (await fetch(src)).text()));
          datKhoSub((k) => k.map((m) => ({ ...m, dangDung: m.id === id })));
        }
      } catch (e) {
        toast.error(loiCuaApi(e));
      }
    },
    [duAn, toast],
  );

  /* =========================================================== xuat ====== */

  const xuat = useCallback(async () => {
    if (!duAn) return;
    datDangXuat(true);
    datTrangThaiXuat("Đang đưa vào hàng đợi…");
    try {
      await videoStudio.render(duAn.project_id);
      for (let i = 0; i < 400; i += 1) {
        await new Promise((r) => setTimeout(r, 2000));
        const r = await videoStudio.getProject(duAn.project_id);
        datDuAn(r.project);
        if (r.project.render_state === "ready") {
          const o = await videoStudio.output(duAn.project_id);
          const { src } = await videoStudio.resolveMedia(o.url, o.stream_url);
          datUrlXuat(src);
          datTrangThaiXuat("Xong.");
          return;
        }
        if (r.project.render_state === "failed") {
          throw new Error(r.project.render_error || "Xuất video thất bại.");
        }
        datTrangThaiXuat(
          r.project.render_state === "rendering" ? "Đang dựng…" : "Đang chờ…");
      }
      throw new Error("Quá lâu — thử lại sau.");
    } catch (e) {
      datTrangThaiXuat("");
      toast.error(loiCuaApi(e));
    } finally {
      datDangXuat(false);
    }
  }, [duAn, toast]);

  /* ============================================================= ve ====== */

  if (dangNapPhien) return <Loading />;
  if (!profile) {
    return (
      <EmptyState
        icon="🎬"
        title="Đăng nhập để mở Media Studio"
        hint="Media Studio là nơi ghép video, lời đọc và phụ đề. Bạn cần đăng nhập để tải lên video hoặc chỉnh sửa dự án."
        action={
          <div className="row" style={{ gap: "0.5rem", justifyContent: "center", flexWrap: "wrap" }}>
            <Link className="btn btn-primary" href={loginHref("/studio/media")} prefetch={false}>
              Đăng nhập
            </Link>
            <Link className="btn btn-ghost" href="/studio/audio" prefetch={false}>
              Quay lại Audio Studio
            </Link>
          </div>
        }
      />
    );
  }
  if (dangNap) return <Loading />;
  if (loi) return <ErrorState message={loi} onRetry={() => window.location.reload()} />;

  if (!video) {
    return (
      <KhoiDongMedia
        tenAudio={audio?.nhan || ""}
        dangTai={dangTai === "video"}
        onTaiVideo={(file) => void taiLen(file, "video")}
      />
    );
  }

  return (
    <div className="ms">
      <div className="ms-tren">
        <div className="ms-trai">
          <MediaBin
            video={khoVideo}
            audio={khoAudio}
            phuDe={khoSub}
            onChonVideo={(id) => void chonTuKho("video", id)}
            onChonAudio={(id) => void chonTuKho("audio", id)}
            onChonPhuDe={(id) => void chonTuKho("phu_de", id)}
            onTaiVideo={(f) => void taiLen(f, "video")}
            onTaiAudio={(f) => void taiLen(f, "audio")}
            onNhapPhuDe={(f) => void taiLen(f, "subtitles")}
            dangTai={dangTai}
          />
          <button className="btn btn-sm ms-audio-moi-nut" type="button" onClick={() => datMoTaoAudio(true)}>
            + Tạo audio mới
          </button>
          {moTaoAudio ? (
            <div className="ms-audio-moi" role="dialog" aria-modal="true" aria-label="Tạo audio mới">
              <div className="ms-audio-moi-dau">
                <strong>Tạo audio mới</strong>
                <button className="btn btn-sm" type="button" onClick={() => datMoTaoAudio(false)}>Đóng</button>
              </div>
              <div className="ms-audio-moi-than">
            <TtsPanel voices={voices} giong={giong} onGiong={datGiong} dangTao={dangTaoTts} loi={loiTts} onTao={(y) => void taoTts(y)} job={jobs.dangChay[0] ?? null} />
              </div>
            </div>
          ) : null}
        </div>

        <div className="ms-giua">
          <Preview
            video={video}
            audio={audio}
            subs={subs}
            urlVideo={srcVideo}
            urlAudio={srcAudio}
            giay={dongHo.giay}
            tong={tong}
            dangPhat={dongHo.dangPhat}
            onBatTat={dongHo.batTat}
            onNhay={nhay}
            datVideo={ganVideoEl}
          />
        </div>

        <Inspector
          chon={chon}
          video={video}
          audio={audio}
          subs={subs}
          tong={tong}
          onVideo={doiVideo}
          onAudio={doiAudio}
          onSub={doiSub}
          onXoaSub={boSub}
          onGoVideo={() => void chonTuKho("video", "")}
          onGoAudio={() => void chonTuKho("audio", "")}
          tenDuAn={duAn?.title || ""}
          onXuat={() => void xuat()}
          dangXuat={dangXuat}
          trangThaiXuat={trangThaiXuat}
          urlXuat={urlXuat}
          urlAudio={srcAudio}
        />
      </div>

      <Timeline
        video={video}
        audio={audio}
        subs={subs}
        urlAudio={srcAudio}
        giay={dongHo.giay}
        tong={tong}
        chon={chon}
        onChon={datChon}
        onNhay={nhay}
        onAudio={doiAudio}
        onSub={doiSub}
        onThemSub={themSub}
        onXoaSub={boSub}
      />
    </div>
  );
}

export default function TrangMedia() {
  return (
    <Suspense fallback={<Loading />}>
      <MediaStudio />
    </Suspense>
  );
}
