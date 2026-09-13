"use client";

/**
 * INSPECTOR — chi hien thuoc tinh cua thu DANG CHON.
 *
 * §13 noi thang: "Do not expose every possible setting simultaneously." Ban
 * Video Composer cu bay MOI o nhap cung luc — cat video, lech loi doc, hai
 * thanh am luong, mot o tat tieng — va nguoi dung phai tu doan o nao thuoc
 * ve cai gi. Chon mot clip roi doc mot bang la mot phep nho hon nhieu.
 *
 * Khong chon gi thi day KHONG bo trong: do la cho hop ly nhat de noi du an
 * nay dang co nhung gi, va la cho duy nhat con lai de bam Xuat.
 */

import type { SubtitleSegment } from "@/lib/subtitles/model";
import {
  type ClipAudio,
  type ClipVideo,
  type DangChon,
  daiAudio,
  daiVideo,
  nhanGioLe,
} from "@/lib/media/timeline";

export function Inspector({
  chon, video, audio, subs, tong,
  onVideo, onAudio, onSub, onXoaSub, onGoVideo, onGoAudio,
  tenDuAn, onXuat, dangXuat, trangThaiXuat, urlXuat, urlAudio,
}: {
  chon: DangChon | null;
  video: ClipVideo | null;
  audio: ClipAudio | null;
  subs: SubtitleSegment[];
  tong: number;
  onVideo: (c: ClipVideo) => void;
  onAudio: (c: ClipAudio) => void;
  onSub: (s: SubtitleSegment) => void;
  onXoaSub: (id: string) => void;
  onGoVideo: () => void;
  onGoAudio: () => void;
  tenDuAn: string;
  onXuat: () => void;
  dangXuat: boolean;
  trangThaiXuat: string;
  urlXuat: string;
  urlAudio: string;
}) {
  const sub = chon?.loai === "phu_de"
    ? subs.find((s) => s.id === chon.id) ?? null
    : null;

  return (
    <aside className="insp" aria-label="Thuộc tính">
      {chon?.loai === "video" && video ? (
        <VideoInsp c={video} onDoi={onVideo} onGo={onGoVideo} />
      ) : chon?.loai === "audio" && audio ? (
        <AudioInsp c={audio} onDoi={onAudio} onGo={onGoAudio} urlAudio={urlAudio} />
      ) : sub ? (
        <SubInsp s={sub} onDoi={onSub} onXoa={() => onXoaSub(sub.id)} />
      ) : (
        <TongQuan
          tenDuAn={tenDuAn}
          video={video}
          audio={audio}
          soSub={subs.length}
          tong={tong}
          onXuat={onXuat}
          dangXuat={dangXuat}
          trangThai={trangThaiXuat}
          urlXuat={urlXuat}
        />
      )}
    </aside>
  );
}

/* ============================================================== video ==== */

function VideoInsp({
  c, onDoi, onGo,
}: { c: ClipVideo; onDoi: (c: ClipVideo) => void; onGo: () => void }) {
  const het = c.catCuoi > 0 ? c.catCuoi : c.goc;
  return (
    <div className="insp-khoi">
      <h3 className="insp-ten">Video</h3>
      <p className="hint truncate">{c.nhan}</p>

      <So nhan="Cắt từ (giây)" gt={c.catDau} min={0} max={Math.max(0, het - 0.2)}
          onDoi={(v) => onDoi({ ...c, catDau: v })} />
      <So nhan="Cắt đến (giây)" gt={het} min={c.catDau + 0.2} max={c.goc}
          onDoi={(v) => onDoi({ ...c, catCuoi: v >= c.goc ? 0 : v })} />

      <Thanh nhan="Âm lượng gốc" gt={c.amLuong} tat={c.tatTiengGoc}
             onDoi={(v) => onDoi({ ...c, amLuong: v })} />
      <label className="insp-o">
        <input
          type="checkbox"
          checked={c.tatTiengGoc}
          onChange={(e) => onDoi({ ...c, tatTiengGoc: e.target.checked })}
        />
        <span>Tắt tiếng gốc của video</span>
      </label>

      <p className="hint">Dài sau khi cắt: {nhanGioLe(daiVideo(c))}</p>
      <button type="button" className="btn btn-sm btn-ghost" onClick={onGo}>
        Gỡ video khỏi dự án
      </button>
    </div>
  );
}

/* ============================================================== audio ==== */

function AudioInsp({
  c, onDoi, onGo, urlAudio,
}: {
  c: ClipAudio; onDoi: (c: ClipAudio) => void; onGo: () => void; urlAudio: string;
}) {
  const catDau = c.batDau < 0 ? -c.batDau : 0;
  const het = c.catCuoi > 0 ? c.catCuoi : c.goc;
  return (
    <div className="insp-khoi">
      <h3 className="insp-ten">Lời đọc</h3>
      <p className="hint truncate">{c.nhan}</p>

      <So nhan="Bắt đầu tại (giây)" gt={Math.max(0, c.batDau)} min={0} max={36000}
          onDoi={(v) => onDoi({ ...c, batDau: v })} />
      <So nhan="Cắt bớt đầu (giây)" gt={catDau} min={0} max={Math.max(0, het - 0.2)}
          onDoi={(v) => onDoi({ ...c, batDau: v > 0 ? -v : Math.max(0, c.batDau) })} />
      <So nhan="Cắt đến (giây)" gt={het} min={catDau + 0.2} max={c.goc}
          onDoi={(v) => onDoi({ ...c, catCuoi: v >= c.goc ? 0 : v })} />

      <Thanh nhan="Âm lượng" gt={c.amLuong} tat={c.tat}
             onDoi={(v) => onDoi({ ...c, amLuong: v })} />
      <label className="insp-o">
        <input
          type="checkbox"
          checked={c.tat}
          onChange={(e) => onDoi({ ...c, tat: e.target.checked })}
        />
        <span>Tắt tiếng lời đọc</span>
      </label>

      <p className="hint">Dài sau khi cắt: {nhanGioLe(daiAudio(c))}</p>
      <div className="row insp-nut">
        {urlAudio ? (
          <a className="btn btn-sm btn-ghost" href={urlAudio} download>
            Tải xuống
          </a>
        ) : null}
        <button type="button" className="btn btn-sm btn-ghost" onClick={onGo}>
          Gỡ khỏi dòng thời gian
        </button>
      </div>
    </div>
  );
}

/* ============================================================= phu de ==== */

function SubInsp({
  s, onDoi, onXoa,
}: { s: SubtitleSegment; onDoi: (s: SubtitleSegment) => void; onXoa: () => void }) {
  return (
    <div className="insp-khoi">
      <h3 className="insp-ten">Phụ đề</h3>

      <label className="field">
        <span className="field-nhan">Nội dung</span>
        <textarea
          className="input"
          rows={4}
          value={s.text}
          onChange={(e) => onDoi({ ...s, text: e.target.value })}
          placeholder="Lời thoại…"
        />
      </label>

      <div className="insp-cap">
        <So nhan="Bắt đầu" gt={s.start} min={0} max={Math.max(0, s.end - 0.2)}
            onDoi={(v) => onDoi({ ...s, start: v })} />
        <So nhan="Kết thúc" gt={s.end} min={s.start + 0.2} max={36000}
            onDoi={(v) => onDoi({ ...s, end: v })} />
      </div>

      <p className="hint">Dài: {nhanGioLe(Math.max(0, s.end - s.start))}</p>
      <button type="button" className="btn btn-sm btn-ghost" onClick={onXoa}>
        Xoá phụ đề này
      </button>
    </div>
  );
}

/* ============================================================ tong quan == */

function TongQuan({
  tenDuAn, video, audio, soSub, tong, onXuat, dangXuat, trangThai, urlXuat,
}: {
  tenDuAn: string;
  video: ClipVideo | null;
  audio: ClipAudio | null;
  soSub: number;
  tong: number;
  onXuat: () => void;
  dangXuat: boolean;
  trangThai: string;
  urlXuat: string;
}) {
  return (
    <div className="insp-khoi">
      <h3 className="insp-ten">{tenDuAn || "Dự án media"}</h3>
      <p className="hint">Chọn một clip trên dòng thời gian để sửa nó.</p>

      <dl className="insp-tom">
        <div><dt>Video</dt><dd>{video ? video.nhan : "—"}</dd></div>
        <div><dt>Lời đọc</dt><dd>{audio ? audio.nhan : "—"}</dd></div>
        <div><dt>Phụ đề</dt><dd>{soSub > 0 ? `${soSub} đoạn` : "—"}</dd></div>
        <div><dt>Tổng dài</dt><dd>{nhanGioLe(tong)}</dd></div>
      </dl>

      {/*
        Xuat MP4 doi co VIDEO. Che do chi-audio khong xuat MP4 — nguoi dung
        tai thang tep loi doc o bang Lời đọc. Noi ro thay vi de mot nut hong.
      */}
      {video ? (
        <>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onXuat}
            disabled={dangXuat}
          >
            {dangXuat ? "Đang xuất…" : "Xuất MP4"}
          </button>
          {trangThai ? <p className="hint">{trangThai}</p> : null}
          {urlXuat ? (
            <a className="btn btn-sm" href={urlXuat} download>Tải MP4</a>
          ) : null}
        </>
      ) : (
        <p className="hint">
          Thêm video để xuất MP4. Chỉ cần lời đọc thì tải thẳng tệp audio ở
          bảng bên trái.
        </p>
      )}
    </div>
  );
}

/* ================================================================ o nhap = */

function So({
  nhan, gt, min, max, onDoi,
}: {
  nhan: string; gt: number; min: number; max: number; onDoi: (v: number) => void;
}) {
  return (
    <label className="field">
      <span className="field-nhan">{nhan}</span>
      <input
        className="input"
        type="number"
        step={0.1}
        min={min}
        max={max}
        value={Number.isFinite(gt) ? Number(gt.toFixed(2)) : 0}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) onDoi(Math.min(max, Math.max(min, v)));
        }}
      />
    </label>
  );
}

function Thanh({
  nhan, gt, tat, onDoi,
}: { nhan: string; gt: number; tat: boolean; onDoi: (v: number) => void }) {
  return (
    <label className="field">
      <span className="field-nhan">
        {nhan} — {tat ? "đang tắt" : `${Math.round(gt * 100)}%`}
      </span>
      <input
        type="range"
        min={0}
        max={2}
        step={0.05}
        value={gt}
        disabled={tat}
        onChange={(e) => onDoi(Number(e.target.value))}
      />
    </label>
  );
}
