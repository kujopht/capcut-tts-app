"use client";

/**
 * Hộp soạn bài đăng.
 *
 * Social & Play V1 — bảng tin mở đầu bằng MỘT hàng kích hoạt gọn (avatar +
 * "Bạn đang nghĩ gì?"); bấm vào mở một HỘP THOẠI (trên điện thoại là tấm
 * trượt từ dưới lên). Người chỉ đến đọc không phải cuộn qua một cái form, và
 * người đang viết có trọn màn hình cho bài của mình.
 *
 * BỐN lời hứa với người viết, mỗi lời là một lỗi từng làm mất bài:
 *
 *   1. BẢN NHÁP không mất: chữ, fandom, spoiler được lưu cục bộ theo từng người
 *      dùng; đóng hộp, tải lại trang hay rớt mạng đều còn. Chỉ xoá khi máy chủ
 *      xác nhận đã đăng. (Ảnh KHÔNG lưu vào bản nháp — quá nặng cho
 *      localStorage; hộp nói rõ điều đó.)
 *   2. KHÔNG đăng hai lần: mỗi bài mang một `client_key` sinh một lần và GIỮ
 *      qua mọi lần thử lại — yêu cầu đầu đã tới máy chủ mà trả lời bị mất thì
 *      lần bấm lại nhận về đúng bài cũ. Nút Đăng khoá trong lúc gửi.
 *   3. Enter là XUỐNG DÒNG, không phải "đăng". Chỉ Ctrl/⌘+Enter mới gửi — một
 *      thao tác cố ý.
 *   4. Nút nào máy chủ chưa hỗ trợ thì KHÔNG vẽ (`capabilities`).
 *
 * XỬ LÝ ẢNH Ở TRÌNH DUYỆT (canvas → WebP, bỏ metadata/GPS) giữ nguyên như
 * trước — máy chủ vẫn kiểm lại, đây chỉ để cú bấm thành công.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError, social, type Post, type ServerLimits } from "@/lib/api";
import { xuLyAnh, type AnhDaXuLy } from "@/lib/image";
import { useSession } from "@/lib/session";
import { useDialogFocus } from "@/lib/useDialogFocus";
import {
  docBanNhap,
  ghiBanNhap,
  taoKhoaGui,
  xoaBanNhap,
  type KhoChuoi,
} from "@/lib/communityFeed";
import { UserAvatar, tenHienThi } from "@/components/UserAvatar";

/** Cạnh dài nhất. Dùng khi máy chủ chưa trả giới hạn về. */
const CANH_DU_PHONG = 1600;

/** Ngưỡng cảnh báo số ký tự — cùng tỉ lệ với trang soạn chương. */
const CANH_BAO = 0.85;

function khoCucBo(): KhoChuoi | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function khoaMoi(): string {
  return taoKhoaGui(() =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36),
  );
}

export function PostComposer({
  limits,
  storyOptions = [],
  onPosted,
  defaultFandom = "",
}: {
  /** Giới hạn của MÁY CHỦ. `null` = chưa tải được; hộp vẫn dùng được. */
  limits: ServerLimits | null;
  /** Truyện đã xuất bản của chính mình — để đăng "cập nhật truyện". Rỗng với
      người chưa là tác giả đã duyệt. */
  storyOptions?: ReadonlyArray<{ novel_id: string; title: string }>;
  onPosted: (post: Post) => void;
  /** Fandom đang lọc trên bảng tin — gợi ý sẵn cho bài mới. */
  defaultFandom?: string;
}) {
  const { profile } = useSession();
  const uid = profile?.user_id ?? "";
  const [mo, setMo] = useState(false);
  const [chu, setChu] = useState("");
  const [truyenId, setTruyenId] = useState("");
  const [fandom, setFandom] = useState("");
  const [spoiler, setSpoiler] = useState(false);
  const [xemTruoc, setXemTruoc] = useState(false);
  const [anhDs, setAnhDs] = useState<AnhDaXuLy[]>([]);
  const [dangXuLyAnh, setDangXuLyAnh] = useState(false);
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState("");
  const [daKhoiPhuc, setDaKhoiPhuc] = useState(false);
  const khoaGui = useRef("");
  const oTep = useRef<HTMLInputElement | null>(null);
  const hop = useRef<HTMLDivElement | null>(null);
  const nutMo = useRef<HTMLButtonElement | null>(null);

  const cap = limits?.capabilities ?? {};
  const fandoms = limits?.community_fandoms ?? [];
  const tranChu = limits?.post_max_chars ?? 2000;
  const canhToiDa = limits?.image?.post?.max_edge ?? CANH_DU_PHONG;
  const tranByte = limits?.image?.post?.max_bytes ?? 1024 * 1024;
  const tranSoAnh = limits?.post_max_images ?? 4;
  const tranTongByte = limits?.post_total_media_bytes ?? 3 * 1024 * 1024;

  /* Thu hồi MỌI URL xem trước khi danh sách đổi hoặc thành phần biến mất. */
  useEffect(() => {
    const urls = anhDs.map((a) => a.xemTruoc);
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [anhDs]);

  /* Lưu bản nháp (trễ nhẹ để không ghi localStorage ở từng phím). */
  useEffect(() => {
    if (!mo || !uid) return;
    const h = window.setTimeout(() => {
      ghiBanNhap(khoCucBo(), uid, {
        text: chu,
        fandom,
        spoiler,
        novelId: truyenId,
        khoaGui: khoaGui.current,
        t: Date.now(),
      });
    }, 400);
    return () => window.clearTimeout(h);
  }, [mo, uid, chu, fandom, spoiler, truyenId]);

  const moHop = useCallback(() => {
    setLoi("");
    const b = docBanNhap(khoCucBo(), uid, Date.now());
    if (b && !chu) {
      setChu(b.text);
      setFandom(b.fandom);
      setSpoiler(b.spoiler);
      setTruyenId(b.novelId);
      khoaGui.current = b.khoaGui || khoaMoi();
      setDaKhoiPhuc(true);
    } else {
      if (!khoaGui.current) khoaGui.current = khoaMoi();
      if (!chu && defaultFandom) setFandom(defaultFandom);
    }
    setMo(true);
  }, [uid, chu, defaultFandom]);

  const dongHop = useCallback(() => {
    if (dangGui) return; // dang gui thi khong dong giua chung
    setMo(false);
    setXemTruoc(false);
  }, [dangGui]);

  useDialogFocus(hop, dongHop, mo);

  const boBanNhap = useCallback(() => {
    xoaBanNhap(khoCucBo(), uid);
    setChu("");
    setFandom("");
    setSpoiler(false);
    setTruyenId("");
    setAnhDs([]);
    setDaKhoiPhuc(false);
    khoaGui.current = khoaMoi();
  }, [uid]);

  const chonTep = useCallback(
    async (danhSach: FileList | null) => {
      if (!danhSach?.length) return;
      setLoi("");
      setDangXuLyAnh(true);
      try {
        const chua = tranSoAnh - anhDs.length;
        const tep = [...danhSach].slice(0, Math.max(0, chua));
        if (danhSach.length > chua) {
          setLoi(`Tối đa ${tranSoAnh} ảnh mỗi bài — chỉ nhận ${chua} ảnh nữa.`);
        }
        const moi: AnhDaXuLy[] = [];
        for (const t of tep) {
          const ra = await xuLyAnh(t, canhToiDa);
          if (!ra) {
            setLoi("Không đọc được một trong các ảnh. Hãy thử tệp khác.");
            continue;
          }
          if (ra.bytes > tranByte) {
            setLoi(
              `Ảnh còn ${(ra.bytes / 1024 / 1024).toFixed(1)} MB sau khi nén ` +
                `(trần ${(tranByte / 1024 / 1024).toFixed(1)} MB) — đã bỏ qua.`,
            );
            URL.revokeObjectURL(ra.xemTruoc);
            continue;
          }
          moi.push(ra);
        }
        if (moi.length) {
          const tongMoi = [...anhDs, ...moi];
          const tong = tongMoi.reduce((t, a) => t + a.bytes, 0);
          if (tong > tranTongByte) {
            setLoi(
              `Tổng dung lượng ảnh vượt ${(tranTongByte / 1024 / 1024).toFixed(0)} MB. ` +
                "Hãy bớt hoặc nén ảnh.",
            );
            moi.forEach((a) => URL.revokeObjectURL(a.xemTruoc));
          } else {
            setAnhDs(tongMoi);
          }
        }
      } finally {
        setDangXuLyAnh(false);
        if (oTep.current) oTep.current.value = "";
      }
    },
    [anhDs, canhToiDa, tranByte, tranSoAnh, tranTongByte],
  );

  const gui = useCallback(async () => {
    if (dangGui) return;
    const noiDung = chu.trim();
    if (!noiDung && !anhDs.length) {
      setLoi("Hãy viết gì đó, hoặc chọn một ảnh.");
      return;
    }
    if (!khoaGui.current) khoaGui.current = khoaMoi();
    setDangGui(true);
    setLoi("");
    try {
      const ra = await social.createPost({
        text: noiDung,
        kind: truyenId ? "story_update" : "post",
        novel_id: truyenId,
        images: anhDs.map((a) => ({
          base64: a.base64,
          mime: a.mime,
          width: a.width,
          height: a.height,
        })),
        client_key: khoaGui.current,
        ...(cap.post_spoiler ? { spoiler } : {}),
        ...(cap.post_fandom && fandom ? { fandom_id: fandom } : {}),
      });
      // CHI xoa khi may chu da xac nhan.
      xoaBanNhap(khoCucBo(), uid);
      khoaGui.current = "";
      setChu("");
      setTruyenId("");
      setFandom("");
      setSpoiler(false);
      setAnhDs([]);
      setDaKhoiPhuc(false);
      setXemTruoc(false);
      setMo(false);
      onPosted(ra.post);
    } catch (e) {
      // GIU NGUYEN moi thu — chu, anh, khoa gui — de bam lai la dung bai do.
      setLoi(
        e instanceof ApiError
          ? `${e.message} Bài của bạn vẫn còn ở đây — bấm Đăng để thử lại.`
          : "Mất kết nối. Bài của bạn vẫn còn ở đây — bấm Đăng để thử lại.",
      );
    } finally {
      setDangGui(false);
    }
  }, [dangGui, chu, anhDs, truyenId, cap.post_spoiler, cap.post_fandom, spoiler, fandom, uid, onPosted]);

  const conLai = tranChu - chu.length;
  const gan = chu.length >= tranChu * CANH_BAO;
  const ten = tenHienThi(profile, "?");
  const tenFandom = fandoms.find((f) => f.id === fandom)?.label ?? "";

  return (
    <>
      {/*
        HANG KICH HOAT — mot <button> that: Enter/Space mo duoc hop thoai.
      */}
      <section className="card soan-bai-moi" aria-label="Đăng bài mới">
        <UserAvatar user={profile} className="avatar" />
        <button
          ref={nutMo}
          type="button"
          className="soan-bai-kich-hoat"
          aria-haspopup="dialog"
          onClick={moHop}
        >
          {chu.trim() ? "Tiếp tục bản nháp…" : "Bạn đang nghĩ gì?"}
        </button>
      </section>

      {/* Portal ra `document.body`: `.page` co `transform` nen `fixed` ben trong
          no khong phu duoc man hinh (tam truot ho day trang tren dien thoai). */}
      {mo ? createPortal(
        <div
          className="lop-phu soan-lop-phu"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) dongHop();
          }}
        >
          <div
            ref={hop}
            className="hop-thoai soan-hop"
            role="dialog"
            aria-modal="true"
            aria-labelledby="soan-bai-tieu-de"
            tabIndex={-1}
          >
            <header className="soan-hop-dau">
              <h2 id="soan-bai-tieu-de" className="h3">
                Tạo bài viết
              </h2>
              <button
                type="button"
                className="btn btn-ghost btn-sm soan-hop-dong"
                aria-label="Đóng (bản nháp được giữ lại)"
                onClick={dongHop}
                disabled={dangGui}
              >
                ✕
              </button>
            </header>

            <div className="soan-hop-than">
              <div className="soan-hop-nguoi">
                <UserAvatar user={profile} className="avatar" />
                <strong>{ten}</strong>
              </div>

              {daKhoiPhuc ? (
                <p className="hint soan-hop-khoi-phuc" role="status">
                  Đã khôi phục bản nháp chưa đăng.{" "}
                  <button type="button" className="link-btn" onClick={boBanNhap}>
                    Bỏ bản nháp
                  </button>
                </p>
              ) : null}

              {xemTruoc ? (
                <div className="soan-xem-truoc" aria-label="Xem trước bài viết">
                  {tenFandom ? <span className="chip chip-sm">{tenFandom}</span> : null}
                  {spoiler ? (
                    <p className="hint">Bài sẽ bị che dưới nhãn “Có spoiler” cho tới khi người đọc bấm hiện.</p>
                  ) : null}
                  <p className="bai-chu">{chu.trim() || <em className="hint">(chưa có chữ)</em>}</p>
                  {anhDs.length ? (
                    <p className="hint">Kèm {anhDs.length} ảnh.</p>
                  ) : null}
                </div>
              ) : (
                <textarea
                  data-autofocus
                  className="input soan-bai-o"
                  rows={5}
                  maxLength={tranChu}
                  value={chu}
                  onChange={(e) => setChu(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      void gui();
                    }
                  }}
                  placeholder="Bạn đang nghĩ gì?"
                  aria-label="Nội dung bài đăng"
                  aria-describedby="soan-bai-dem"
                />
              )}

              {anhDs.length ? (
                <div className="soan-bai-anh">
                  {anhDs.map((a, i) => (
                    <figure key={a.xemTruoc} className="soan-bai-anh-o">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={a.xemTruoc} alt={`Ảnh ${i + 1} sẽ đăng kèm`} />
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        aria-label={`Bỏ ảnh ${i + 1}`}
                        onClick={() => setAnhDs((ds) => ds.filter((x) => x !== a))}
                      >
                        ✕
                      </button>
                      <figcaption className="hint">{(a.bytes / 1024).toFixed(0)} KB</figcaption>
                    </figure>
                  ))}
                </div>
              ) : null}

              <div className="soan-hop-tuy-chon">
                <label className="btn btn-ghost btn-sm soan-bai-tep">
                  {dangXuLyAnh ? "Đang xử lý…" : `🖼 Ảnh (${anhDs.length}/${tranSoAnh})`}
                  <input
                    ref={oTep}
                    type="file"
                    multiple
                    accept={(limits?.image?.post?.mime ?? ["image/*"]).join(",")}
                    onChange={(e) => void chonTep(e.target.files)}
                    disabled={dangXuLyAnh || anhDs.length >= tranSoAnh}
                  />
                </label>

                {cap.post_fandom && fandoms.length ? (
                  <label className="soan-hop-chon">
                    <span className="hint">Fandom</span>
                    <select className="input" value={fandom} onChange={(e) => setFandom(e.target.value)}>
                      <option value="">— Không gắn —</option>
                      {fandoms.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                {storyOptions.length > 0 ? (
                  <label className="soan-hop-chon">
                    <span className="hint">Gắn truyện</span>
                    <select className="input" value={truyenId} onChange={(e) => setTruyenId(e.target.value)}>
                      <option value="">— Bài thường —</option>
                      {storyOptions.map((t) => (
                        <option key={t.novel_id} value={t.novel_id}>
                          {t.title}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                {cap.post_spoiler ? (
                  <label className="soan-hop-spoiler">
                    <input type="checkbox" checked={spoiler} onChange={(e) => setSpoiler(e.target.checked)} />
                    <span>Có spoiler</span>
                  </label>
                ) : null}
              </div>

              {loi ? (
                <p className="hint loi" role="alert">
                  {loi}
                </p>
              ) : null}

              <p className="hint soan-bai-ghi-chu">
                Ảnh được nén lại trong trình duyệt và <strong>bỏ hết metadata</strong> (kể cả toạ độ GPS).
                Chữ được giữ làm bản nháp trên máy này; ảnh thì không.
              </p>
            </div>

            <footer className="soan-hop-day">
              <span id="soan-bai-dem" className={gan ? "hint loi" : "hint"} aria-live="polite">
                {conLai} ký tự
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-pressed={xemTruoc}
                onClick={() => setXemTruoc((v) => !v)}
              >
                {xemTruoc ? "Sửa tiếp" : "Xem trước"}
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={dangGui || dangXuLyAnh}
                aria-busy={dangGui}
                onClick={() => void gui()}
              >
                {dangGui ? "Đang đăng…" : "Đăng"}
              </button>
            </footer>
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
