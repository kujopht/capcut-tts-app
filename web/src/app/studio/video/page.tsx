"use client";

/**
 * Video Composer V1 — ghep MOT loi doc vao MOT video.
 *
 * Xem truoc chay TRONG TRINH DUYET bang hai the `<video>`/`<audio>` chay
 * song song, dong bo bang `currentTime`. KHONG dung ffmpeg.wasm: ban xem
 * truoc phai phan hoi tuc thi khi keo con truot, con ffmpeg.wasm thi dung
 * ra mot lan ma hoa that — sai cong cu cho viec nay. Ban XUAT moi di qua
 * FFmpeg o may chu (`POST /api/video/projects/{id}/render`).
 *
 * Dong bo hai the la mot cho DE SAI, nen no duoc gom vao dung mot cho:
 * `dongBo()`. Moi lan tua/phat/dung deu goi lai no.
 */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  videoStudio,
  type VideoAsset,
  type VideoAudioChoice,
  type VideoProject,
  type VideoSources,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { StudioToolHeader } from "@/components/StudioShell";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import { IconClapper, IconMic, IconPlay } from "@/components/Icons";

const MB = 1024 * 1024;
const KICH_THUOC_TOI_DA = 200 * MB;

function giay(x: number): string {
  if (!Number.isFinite(x) || x < 0) x = 0;
  const p = Math.floor(x / 60);
  const s = Math.floor(x % 60);
  return `${p}:${String(s).padStart(2, "0")}`;
}

/** Doc mot tep thanh base64 KHONG kem tien to `data:` — backend chi nhan phan ma. */
function docBase64(tep: File): Promise<string> {
  return new Promise((ok, hong) => {
    const r = new FileReader();
    r.onerror = () => hong(new Error("Không đọc được tệp."));
    r.onload = () => {
      const s = String(r.result || "");
      const i = s.indexOf(",");
      ok(i >= 0 ? s.slice(i + 1) : s);
    };
    r.readAsDataURL(tep);
  });
}

/** Do dai video, doc tu chinh trinh duyet truoc khi tai len. */
function doThoiLuong(tep: File): Promise<number> {
  return new Promise((ok) => {
    const url = URL.createObjectURL(tep);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      ok(Number.isFinite(v.duration) ? v.duration : 0);
    };
    v.onerror = () => {
      URL.revokeObjectURL(url);
      ok(0);
    };
    v.src = url;
  });
}

/**
 * `useSearchParams` bat trang phai co ranh gioi Suspense khi Next dung san
 * trang. Thieu no thi `next build` BAO LOI chu khong phai loi luc chay —
 * cung rang buoc voi `/fanfic`, va da vap that o lan dung dau tien.
 */
export default function VideoComposerPage() {
  return (
    <Suspense fallback={<Loading />}>
      <VideoComposer />
    </Suspense>
  );
}

function VideoComposer() {
  const { profile, loading: dangNapPhien } = useSession();
  const params = useSearchParams();

  const [duAn, datDuAn] = useState<VideoProject | null>(null);
  const [nguon, datNguon] = useState<VideoSources | null>(null);
  const [dsDuAn, datDsDuAn] = useState<VideoProject[]>([]);
  const [dsAsset, datDsAsset] = useState<VideoAsset[]>([]);
  const [dsAudio, datDsAudio] = useState<VideoAudioChoice[]>([]);
  const [dangNap, datDangNap] = useState(true);
  const [loi, datLoi] = useState("");
  const [dangLuu, datDangLuu] = useState(false);
  const [dangTai, datDangTai] = useState(false);

  const video = useRef<HTMLVideoElement | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [dangPhat, datDangPhat] = useState(false);
  const [viTri, datViTri] = useState(0);

  /*
    Nguon PHAT duoc, da giai xong.

    Kho R2 cho URL ky dung thang duoc; kho cuc bo thi phai tai qua backend
    kem token roi goi thanh blob (the media khong gui duoc header). Giu rieng
    khoi `nguon` vi hai thu nay co vong doi khac nhau: `nguon` den tu mot lan
    goi API, con blob thi phai THU HOI khi doi tep — quen thu hoi la ro bo
    nho dung bang kich thuoc tep video.
  */
  const [src, datSrc] = useState<{ video: string; audio: string }>({
    video: "", audio: "",
  });

  useEffect(() => {
    if (!nguon) return;
    let huy = false;
    const don: Array<() => void> = [];
    (async () => {
      const [v, a] = await Promise.all([
        videoStudio.resolveMedia(nguon.video_url, nguon.video_stream),
        videoStudio.resolveMedia(nguon.audio_url, nguon.audio_stream),
      ]);
      don.push(v.revoke, a.revoke);
      if (huy) {
        v.revoke();
        a.revoke();
        return;
      }
      datSrc({ video: v.src, audio: a.src });
    })();
    return () => {
      huy = true;
      for (const f of don) f();
    };
  }, [nguon]);

  /* ------------------------------------------------------------- nap --- */

  const napDanhSach = useCallback(async () => {
    const [p, a, t] = await Promise.all([
      videoStudio.listProjects(),
      videoStudio.listAssets(),
      videoStudio.audioLibrary().catch(() => ({ tracks: [] })),
    ]);
    datDsDuAn(p.projects);
    datDsAsset(a.assets);
    datDsAudio(t.tracks);
  }, []);

  const moDuAn = useCallback(async (id: string) => {
    const r = await videoStudio.getProject(id);
    datDuAn(r.project);
    datNguon(r.sources);
  }, []);

  useEffect(() => {
    let huy = false;
    (async () => {
      /*
        Dat trang thai TRONG ham bat dong bo, khong o than hieu ung: goi
        `setState` thang trong than hieu ung tao mot chu ky ve noi tiep, va
        React 19 canh bao dung dieu do.
      */
      if (!profile) {
        if (!huy) datDangNap(false);
        return;
      }
      try {
        const [p, a, t] = await Promise.all([
          videoStudio.listProjects(),
          videoStudio.listAssets(),
          videoStudio.audioLibrary().catch(() => ({ tracks: [] })),
        ]);
        if (huy) return;
        datDsDuAn(p.projects);
        datDsAsset(a.assets);
        datDsAudio(t.tracks);

        /*
          "Dùng trong Video" den day theo mot trong hai cach:

            ?audio=<track_id>      — biet dich xac ban nao
            ?chapter=<chapter_id>  — chi biet chuong (trang Thư viện chi co
                                     chuong trong tay)

          Giai `?chapter=` o DAY chu khong mo them mot tham so cho API: danh
          sach audio vua nap ve da mang ca hai id, nen tra cuu la mot phep
          tim trong bo nho chu khong phai mot vong goi mang nua.
        */
        const tuChuong = params.get("chapter");
        const tuAudio =
          params.get("audio") ||
          (tuChuong
            ? t.tracks.find((x) => x.chapter_id === tuChuong)?.track_id || ""
            : "");
        const moId = params.get("project");
        if (huy) return;
        if (tuAudio) {
          const r = await videoStudio.createProject("Dự án video mới", tuAudio);
          if (huy) return;
          await moDuAn(r.project.project_id);
          await napDanhSach();
        } else if (moId) {
          await moDuAn(moId);
        }
      } catch (e) {
        if (!huy) datLoi(e instanceof Error ? e.message : "Không tải được.");
      } finally {
        if (!huy) datDangNap(false);
      }
    })();
    return () => {
      huy = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  /* ------------------------------------------------------------ luu --- */

  const luu = useCallback(
    async (patch: Parameters<typeof videoStudio.patchProject>[1]) => {
      if (!duAn) return;
      datDangLuu(true);
      datLoi("");
      try {
        const r = await videoStudio.patchProject(duAn.project_id, patch);
        datDuAn(r.project);
        datNguon(r.sources);
      } catch (e) {
        datLoi(e instanceof Error ? e.message : "Không lưu được.");
      } finally {
        datDangLuu(false);
      }
    },
    [duAn],
  );

  /* -------------------------------------------------------- xem truoc --- */

  /*
    MOT cho duy nhat dong bo hai the.

    `audio_offset` duong = loi doc bat dau MUON hon video. Nen o thoi diem
    `t` cua video, loi doc phai o `t - offset`; truoc moc do thi no chua bat
    dau, va ta tam dung no thay vi tua ve so am.
  */
  const dongBo = useCallback(() => {
    const v = video.current;
    const a = audio.current;
    if (!v || !duAn) return;
    const t = v.currentTime;
    datViTri(t);
    if (!a || !src.audio) return;
    const muc = t - duAn.audio_offset;
    if (muc < 0) {
      if (!a.paused) a.pause();
      return;
    }
    if (Math.abs(a.currentTime - muc) > 0.25) a.currentTime = muc;
    if (!v.paused && a.paused) void a.play().catch(() => undefined);
  }, [duAn, src]);

  const phat = useCallback(() => {
    const v = video.current;
    if (!v) return;
    if (v.paused) {
      void v.play().catch(() => undefined);
      datDangPhat(true);
    } else {
      v.pause();
      audio.current?.pause();
      datDangPhat(false);
    }
  }, []);

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const dung = () => {
      audio.current?.pause();
      datDangPhat(false);
    };
    v.addEventListener("timeupdate", dongBo);
    v.addEventListener("seeked", dongBo);
    v.addEventListener("pause", dung);
    v.addEventListener("ended", dung);
    return () => {
      v.removeEventListener("timeupdate", dongBo);
      v.removeEventListener("seeked", dongBo);
      v.removeEventListener("pause", dung);
      v.removeEventListener("ended", dung);
    };
  }, [dongBo]);

  // Am luong + tat tieng goc phai ap NGAY vao the dang phat, khong doi luu.
  useEffect(() => {
    if (video.current && duAn) {
      video.current.volume = duAn.mute_original_audio ? 0 : duAn.video_volume;
      video.current.muted = duAn.mute_original_audio;
    }
    if (audio.current && duAn) audio.current.volume = duAn.audio_volume;
  }, [duAn]);

  /* ----------------------------------------------------------- tai len --- */

  const taiLen = useCallback(
    async (tep: File | undefined) => {
      if (!tep || !duAn) return;
      if (tep.size > KICH_THUOC_TOI_DA) {
        datLoi(`Video vượt quá ${KICH_THUOC_TOI_DA / MB} MB.`);
        return;
      }
      datDangTai(true);
      datLoi("");
      try {
        const [b64, dai] = await Promise.all([docBase64(tep), doThoiLuong(tep)]);
        const r = await videoStudio.uploadAsset(
          tep.name, tep.type || "video/mp4", b64, dai);
        await luu({ video_asset_id: r.asset.asset_id });
        await napDanhSach();
      } catch (e) {
        datLoi(e instanceof Error ? e.message : "Không tải lên được.");
      } finally {
        datDangTai(false);
      }
    },
    [duAn, luu, napDanhSach],
  );

  /* ------------------------------------------------------------ render --- */

  const xuat = useCallback(async () => {
    if (!duAn) return;
    datLoi("");
    try {
      const r = await videoStudio.render(duAn.project_id);
      datDuAn(r.project);
    } catch (e) {
      datLoi(e instanceof Error ? e.message : "Không xuất được.");
    }
  }, [duAn]);

  /*
    Hoi lai trang thai trong luc render — 2s mot lan, va CHI khi con dang
    chay. Mot vong hoi mai mai la mot vong hoi se bi quen mat.
  */
  useEffect(() => {
    if (!duAn) return;
    const chay = duAn.render_state === "queued" || duAn.render_state === "rendering";
    if (!chay) return;
    const id = window.setInterval(async () => {
      try {
        const r = await videoStudio.getProject(duAn.project_id);
        datDuAn(r.project);
        datNguon(r.sources);
      } catch {
        /* mat mang mot nhip thi thu lai o nhip sau */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [duAn]);

  const taiVe = useCallback(async () => {
    if (!duAn) return;
    try {
      const r = await videoStudio.output(duAn.project_id);
      const { src: s } = await videoStudio.resolveMedia(r.url, r.stream_url);
      if (s) window.open(s, "_blank", "noopener");
      // KHONG thu hoi blob ngay: tab vua mo con dang doc no. Trinh duyet tu
      // giai phong khi tab do dong.
    } catch (e) {
      datLoi(e instanceof Error ? e.message : "Chưa có bản render.");
    }
  }, [duAn]);

  /* ------------------------------------------------------------- ve --- */

  const dsVideo = useMemo(
    () => dsAsset.filter((a) => a.media_type === "video"),
    [dsAsset],
  );
  const dsPhuDe = useMemo(
    () => dsAsset.filter((a) => a.media_type === "subtitles"),
    [dsAsset],
  );

  if (dangNapPhien) return <Loading />;

  if (!profile) {
    return (
      <div className="studio-tool">
        <StudioToolHeader />
        <EmptyState
          icon="🎬"
          title="Đăng nhập để dùng Video Composer"
          hint="Dự án video gắn với tài khoản của bạn."
          action={
            <Link className="btn btn-primary" href="/login?next=/studio/video" prefetch={false}>
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  const dai = nguon?.video_duration || 0;
  const dangRender =
    duAn?.render_state === "queued" || duAn?.render_state === "rendering";

  return (
    <div className="studio-tool vc">
      <StudioToolHeader
        action={
          duAn ? (
            <div className="row vc-dau-nut">
              {dangLuu ? <span className="hint">Đang lưu…</span> : null}
              <button
                type="button"
                className="btn btn-primary"
                onClick={xuat}
                disabled={dangRender || !duAn.video_asset_id}
              >
                {dangRender ? "Đang xuất…" : "Xuất MP4"}
              </button>
              {duAn.has_output ? (
                <button type="button" className="btn" onClick={taiVe}>
                  Tải bản MP4
                </button>
              ) : null}
            </div>
          ) : undefined
        }
      />

      {loi ? <ErrorState message={loi} onRetry={() => datLoi("")} /> : null}

      {dangNap ? (
        <Loading />
      ) : !duAn ? (
        <DanhSachDuAn
          duAn={dsDuAn}
          onMo={moDuAn}
          onTao={async (ten) => {
            const r = await videoStudio.createProject(ten);
            await moDuAn(r.project.project_id);
            await napDanhSach();
          }}
        />
      ) : (
        <>
          <div className="vc-khung">
            {/* ---------------------------------------------- xem truoc --- */}
            <section className="vc-xem" aria-label="Xem trước">
              <div className="vc-khung-video">
                {src.video ? (
                  <video
                    ref={video}
                    src={src.video}
                    className="vc-video"
                    playsInline
                    preload="metadata"
                  />
                ) : (
                  <div className="vc-trong">
                    <IconClapper size={40} />
                    <p>Chọn một video để bắt đầu</p>
                  </div>
                )}
                {src.audio ? (
                  <audio ref={audio} src={src.audio} preload="metadata" />
                ) : null}
              </div>

              <div className="vc-dieu-khien">
                <button
                  type="button"
                  className="btn btn-primary vc-phat"
                  onClick={phat}
                  disabled={!src.video}
                  aria-label={dangPhat ? "Tạm dừng" : "Phát"}
                >
                  {dangPhat ? "❚❚" : <IconPlay size={16} />}
                </button>
                <span className="hint vc-dong-ho">
                  {giay(viTri)} / {giay(dai)}
                </span>
                <input
                  type="range"
                  className="vc-tua"
                  min={0}
                  max={Math.max(dai, 0.1)}
                  step={0.05}
                  value={Math.min(viTri, dai || 0)}
                  disabled={!src.video}
                  aria-label="Tua"
                  onChange={(e) => {
                    const t = Number(e.target.value);
                    if (video.current) video.current.currentTime = t;
                    datViTri(t);
                  }}
                />
              </div>
            </section>

            {/* ---------------------------------------------- inspector --- */}
            <aside className="vc-inspector" aria-label="Thuộc tính">
              <Nhom ten="Video">
                <label className="field">
                  <span className="label">Tệp video</span>
                  <select
                    value={duAn.video_asset_id}
                    onChange={(e) => luu({ video_asset_id: e.target.value })}
                  >
                    <option value="">— chưa chọn —</option>
                    {dsVideo.map((a) => (
                      <option key={a.asset_id} value={a.asset_id}>
                        {a.object_key.split("/").pop()} · {giay(a.duration_seconds)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="btn vc-tai-len">
                  {dangTai ? "Đang tải lên…" : "Tải video lên"}
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
                    hidden
                    disabled={dangTai}
                    onChange={(e) => void taiLen(e.target.files?.[0])}
                  />
                </label>
                <ThanhTruot
                  ten="Âm lượng gốc"
                  min={0}
                  max={2}
                  buoc={0.05}
                  gia_tri={duAn.video_volume}
                  tat={duAn.mute_original_audio}
                  onDoi={(v) => luu({ video_volume: v })}
                />
                <label className="vc-o-chon">
                  <input
                    type="checkbox"
                    checked={duAn.mute_original_audio}
                    onChange={(e) => luu({ mute_original_audio: e.target.checked })}
                  />
                  <span>Tắt tiếng gốc của video</span>
                </label>
                <div className="vc-cap">
                  <SoGiay
                    ten="Cắt từ"
                    gia_tri={duAn.video_trim_start}
                    onDoi={(v) => luu({ video_trim_start: v })}
                  />
                  <SoGiay
                    ten="Cắt đến"
                    gia_tri={duAn.video_trim_end}
                    goi_y="0 = hết"
                    onDoi={(v) => luu({ video_trim_end: v })}
                  />
                </div>
              </Nhom>

              <Nhom ten="Lời đọc">
                <label className="field">
                  <span className="label">Bản audio</span>
                  <select
                    value={duAn.audio_track_id}
                    onChange={(e) => luu({ audio_track_id: e.target.value })}
                  >
                    <option value="">— chưa chọn —</option>
                    {dsAudio.map((t) => (
                      <option key={t.track_id} value={t.track_id}>
                        {t.chapter_title} · {giay(t.duration_seconds)}
                      </option>
                    ))}
                  </select>
                </label>
                {dsAudio.length === 0 ? (
                  <p className="hint">
                    Chưa có bản audio nào.{" "}
                    <Link href="/studio/audio" prefetch={false}>
                      Tạo ở Audio Studio
                    </Link>
                    .
                  </p>
                ) : null}
                <ThanhTruot
                  ten="Âm lượng lời đọc"
                  min={0}
                  max={2}
                  buoc={0.05}
                  gia_tri={duAn.audio_volume}
                  onDoi={(v) => luu({ audio_volume: v })}
                />
                <SoGiay
                  ten="Bắt đầu ở giây"
                  gia_tri={duAn.audio_offset}
                  goi_y="âm = trước video"
                  onDoi={(v) => luu({ audio_offset: v })}
                />
              </Nhom>

              <Nhom ten="Phụ đề">
                <label className="field">
                  <span className="label">Tệp phụ đề</span>
                  <select
                    value={duAn.subtitle_asset_id}
                    onChange={(e) => luu({ subtitle_asset_id: e.target.value })}
                  >
                    <option value="">— không dùng —</option>
                    {dsPhuDe.map((a) => (
                      <option key={a.asset_id} value={a.asset_id}>
                        {a.object_key.split("/").pop()}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="btn vc-tai-len">
                  Tải .srt / .vtt
                  <input
                    type="file"
                    accept=".srt,.vtt,text/vtt,application/x-subrip"
                    hidden
                    onChange={(e) => void taiLen(e.target.files?.[0])}
                  />
                </label>
              </Nhom>

              {duAn.render_error ? (
                <p className="vc-loi-render">{duAn.render_error}</p>
              ) : null}
            </aside>
          </div>

          <Timeline
            dai={dai}
            viTri={viTri}
            duAn={duAn}
            audioDai={nguon?.audio_duration || 0}
            onTua={(t) => {
              if (video.current) video.current.currentTime = t;
              datViTri(t);
            }}
            onLech={(v) => luu({ audio_offset: v })}
          />
        </>
      )}
    </div>
  );
}

/* ===================================================== thanh phan nho === */

function Nhom({ ten, children }: { ten: string; children: React.ReactNode }) {
  return (
    <section className="vc-nhom">
      <h3 className="vc-nhom-ten">{ten}</h3>
      {children}
    </section>
  );
}

function ThanhTruot({
  ten, min, max, buoc, gia_tri, tat, onDoi,
}: {
  ten: string; min: number; max: number; buoc: number;
  gia_tri: number; tat?: boolean; onDoi: (v: number) => void;
}) {
  return (
    <label className="field vc-truot">
      <span className="label">
        {ten} <span className="hint">{Math.round(gia_tri * 100)}%</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={buoc}
        value={gia_tri}
        disabled={tat}
        onChange={(e) => onDoi(Number(e.target.value))}
      />
    </label>
  );
}

function SoGiay({
  ten, gia_tri, goi_y, onDoi,
}: {
  ten: string; gia_tri: number; goi_y?: string; onDoi: (v: number) => void;
}) {
  /*
    Giu MOT trang thai cuc bo trong luc go: gui thang tung ky tu len may chu
    se ban mot request cho moi phim, va "-" (dang go so am) se bi tu choi
    ngay truoc khi nguoi dung kip go chu so.
  */
  const [tho, datTho] = useState(String(gia_tri));
  /*
    Dong bo lai khi gia tri THAT doi (vd sau khi keo lan loi doc tren duong
    thoi gian) — bang mau "chinh trang thai trong lúc ve" cua React, khong
    bang `useEffect`.

    `useEffect` o day se la mot lan ve thua moi lan gia tri doi, va bo lint
    canh bao dung noi dung do. So sanh voi gia tri TRUOC chu khong voi `tho`:
    nguoi dung dang go "1." la mot trang thai hop le ma ta khong duoc dam len.
  */
  const [truoc, datTruoc] = useState(gia_tri);
  if (truoc !== gia_tri) {
    datTruoc(gia_tri);
    datTho(String(gia_tri));
  }
  return (
    <label className="field vc-so">
      <span className="label">
        {ten} {goi_y ? <span className="hint">{goi_y}</span> : null}
      </span>
      <input
        type="number"
        step={0.1}
        value={tho}
        onChange={(e) => datTho(e.target.value)}
        onBlur={() => {
          const v = Number(tho);
          if (Number.isFinite(v)) onDoi(v);
          else datTho(String(gia_tri));
        }}
      />
    </label>
  );
}

function DanhSachDuAn({
  duAn, onMo, onTao,
}: {
  duAn: VideoProject[];
  onMo: (id: string) => void | Promise<void>;
  onTao: (ten: string) => void | Promise<void>;
}) {
  const [ten, datTen] = useState("");
  return (
    <div className="stack vc-danh-sach">
      <form
        className="row vc-tao"
        onSubmit={(e) => {
          e.preventDefault();
          const t = ten.trim();
          if (t) void onTao(t);
          datTen("");
        }}
      >
        <input
          className="input"
          placeholder="Tên dự án video…"
          value={ten}
          onChange={(e) => datTen(e.target.value)}
          aria-label="Tên dự án video"
        />
        <button type="submit" className="btn btn-primary" disabled={!ten.trim()}>
          Tạo dự án
        </button>
      </form>

      {duAn.length === 0 ? (
        <EmptyState
          icon="🎬"
          title="Chưa có dự án video nào"
          hint="Tạo một dự án, chọn video, rồi ghép lời đọc bạn đã tạo ở Audio Studio."
        />
      ) : (
        <div className="list list-gon">
          {duAn.map((d) => (
            <div key={d.project_id} className="list-item">
              <span className="stack-2 list-main">
                <button
                  type="button"
                  className="list-title vc-mo"
                  onClick={() => void onMo(d.project_id)}
                >
                  {d.title}
                </button>
                <span className="hint">
                  <TrangThai t={d.render_state} />
                </span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TrangThai({ t }: { t: VideoProject["render_state"] }) {
  const nhan: Record<VideoProject["render_state"], string> = {
    draft: "Bản nháp",
    queued: "Đang xếp hàng",
    rendering: "Đang xuất",
    ready: "Đã xuất xong",
    failed: "Xuất thất bại",
  };
  return <span className={`vc-tt vc-tt-${t}`}>{nhan[t]}</span>;
}

/**
 * Duong thoi gian — BA lan, mot thuoc do, mot dau phat.
 *
 * Keo lan LOI DOC de doi `audio_offset`. Day la thao tac hay dung nhat cua
 * ca man hinh (can lai loi doc cho khop hinh), nen no phai keo duoc chu
 * khong chi go so.
 */
function Timeline({
  dai, viTri, duAn, audioDai, onTua, onLech,
}: {
  dai: number; viTri: number; duAn: VideoProject; audioDai: number;
  onTua: (t: number) => void; onLech: (v: number) => void;
}) {
  const ray = useRef<HTMLDivElement | null>(null);
  const [keo, datKeo] = useState<null | { x: number; goc: number }>(null);

  const tong = Math.max(dai, duAn.audio_offset + audioDai, 1);
  const pc = (x: number) => `${Math.max(0, Math.min(100, (x / tong) * 100))}%`;

  useEffect(() => {
    if (!keo) return;
    const di = (e: PointerEvent) => {
      const r = ray.current?.getBoundingClientRect();
      if (!r || r.width === 0) return;
      const dx = ((e.clientX - keo.x) / r.width) * tong;
      onLech(Math.round((keo.goc + dx) * 10) / 10);
    };
    const thoi = () => datKeo(null);
    window.addEventListener("pointermove", di);
    window.addEventListener("pointerup", thoi);
    return () => {
      window.removeEventListener("pointermove", di);
      window.removeEventListener("pointerup", thoi);
    };
  }, [keo, tong, onLech]);

  const moc = useMemo(() => {
    const buoc = tong <= 30 ? 5 : tong <= 120 ? 15 : 60;
    const ra: number[] = [];
    for (let t = 0; t <= tong; t += buoc) ra.push(t);
    return ra;
  }, [tong]);

  return (
    <section className="vc-timeline" aria-label="Dòng thời gian">
      <div className="vc-thuoc" aria-hidden="true">
        {moc.map((t) => (
          <span key={t} className="vc-moc" style={{ left: pc(t) }}>
            {giay(t)}
          </span>
        ))}
      </div>

      <div
        className="vc-ray"
        ref={ray}
        onPointerDown={(e) => {
          // Bam vao khoang trong = tua toi do.
          if ((e.target as HTMLElement).closest(".vc-clip-audio")) return;
          const r = ray.current?.getBoundingClientRect();
          if (!r || r.width === 0) return;
          onTua(((e.clientX - r.left) / r.width) * tong);
        }}
      >
        <Lan ten="Video">
          {dai > 0 ? (
            <span
              className="vc-clip vc-clip-video"
              style={{
                left: pc(duAn.video_trim_start),
                width: pc((duAn.video_trim_end || dai) - duAn.video_trim_start),
              }}
            />
          ) : null}
        </Lan>

        <Lan ten="Lời đọc">
          {audioDai > 0 ? (
            <span
              className="vc-clip vc-clip-audio"
              style={{ left: pc(duAn.audio_offset), width: pc(audioDai) }}
              onPointerDown={(e) => {
                e.stopPropagation();
                datKeo({ x: e.clientX, goc: duAn.audio_offset });
              }}
              role="slider"
              tabIndex={0}
              aria-label="Vị trí lời đọc"
              aria-valuenow={Math.round(duAn.audio_offset * 10) / 10}
              aria-valuemin={-3600}
              aria-valuemax={3600}
              onKeyDown={(e) => {
                // Ban phim phai keo duoc: chuot khong phai thiet bi duy nhat.
                if (e.key === "ArrowLeft") onLech(Math.round((duAn.audio_offset - 0.5) * 10) / 10);
                if (e.key === "ArrowRight") onLech(Math.round((duAn.audio_offset + 0.5) * 10) / 10);
              }}
            />
          ) : null}
        </Lan>

        <Lan ten="Phụ đề">
          {duAn.subtitle_asset_id ? (
            <span className="vc-clip vc-clip-sub" style={{ left: 0, width: "100%" }} />
          ) : null}
        </Lan>

        <span className="vc-dau-phat" style={{ left: pc(viTri) }} aria-hidden="true" />
      </div>
    </section>
  );
}

function Lan({ ten, children }: { ten: string; children: React.ReactNode }) {
  return (
    <div className="vc-lan">
      <span className="vc-lan-ten">{ten}</span>
      <div className="vc-lan-ray">{children}</div>
    </div>
  );
}
