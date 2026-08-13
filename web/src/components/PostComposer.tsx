"use client";

/**
 * Hộp soạn bài đăng.
 *
 * V3 — mở bằng MỘT hàng kích hoạt quen thuộc (avatar + "Bạn đang nghĩ gì?"):
 * bảng tin không mở đầu bằng một textarea to trống trải, và người chỉ đến đọc
 * không phải cuộn qua một cái form. Bấm vào hàng là composer thật mở ra và
 * textarea nhận tiêu điểm.
 *
 * V3 — tối đa BỐN ảnh. Mỗi ảnh qua cùng đường xử lý canvas; trần số ảnh và
 * tổng dung lượng đọc từ `/api/limits`, máy chủ vẫn là nơi cưỡng chế.
 *
 * XỬ LÝ ẢNH Ở TRÌNH DUYỆT, và đó là quyết định đáng giải thích nhất ở đây.
 *
 * Ảnh được vẽ lại qua `<canvas>` rồi xuất ra WebP TRƯỚC KHI gửi. Ba lý do, theo
 * thứ tự quan trọng:
 *
 *   1. Một ảnh chụp từ điện thoại là 4–8 MB. Trần của máy chủ là 1 MB. Gửi thẳng
 *      thì người dùng chờ hết đường truyền rồi nhận một lỗi — trải nghiệm tệ
 *      nhất có thể, vì công sức đã bỏ ra hết rồi mới biết là vô ích.
 *   2. Vẽ lại qua canvas BỎ HẾT metadata, kể cả EXIF. Ảnh chụp từ điện thoại
 *      thường mang TOẠ ĐỘ GPS, và một người đăng ảnh góc làm việc của mình không
 *      hề có ý công bố nơi mình sống. Đây là lý do bảo vệ quyền riêng tư, và nó
 *      đắt hơn cả lý do băng thông.
 *   3. WebP nhỏ hơn JPEG cùng chất lượng, nên ảnh tải nhanh hơn cho người đọc.
 *
 * MÁY CHỦ VẪN KIỂM LẠI. Việc xử lý ở đây chỉ để cú bấm thành công; nó không phải
 * hàng rào. Trần thật nằm ở `server/social.py`.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, social, type Post, type ServerLimits } from "@/lib/api";
import { useSession } from "@/lib/session";

/** Cạnh dài nhất và chất lượng nén. Dùng khi máy chủ chưa trả giới hạn về. */
const CANH_DU_PHONG = 1600;
const CHAT_LUONG = 0.82;

/** Ngưỡng cảnh báo số ký tự — cùng tỉ lệ với trang soạn chương. */
const CANH_BAO = 0.85;

interface AnhDaXuLy {
  base64: string;
  mime: string;
  width: number;
  height: number;
  bytes: number;
  /** URL tạm để xem trước. PHẢI được thu hồi — xem `useEffect` dọn dẹp. */
  xemTruoc: string;
}

/**
 * Vẽ lại một ảnh về trong giới hạn và xuất WebP.
 *
 * Trả `null` khi trình duyệt không đọc được tệp — một tệp `.webp` hỏng hay một
 * tệp đổi đuôi đều rơi vào đây, và cả hai đều nên nói "không đọc được ảnh" thay
 * vì làm hỏng cả hộp soạn.
 */
async function xuLyAnh(
  tep: File,
  canhToiDa: number,
): Promise<AnhDaXuLy | null> {
  const nguon = URL.createObjectURL(tep);
  try {
    const anh = await new Promise<HTMLImageElement | null>((xong) => {
      const el = new Image();
      el.onload = () => xong(el);
      el.onerror = () => xong(null);
      el.src = nguon;
    });
    if (!anh) return null;

    const canh = Math.max(anh.naturalWidth, anh.naturalHeight) || 1;
    const ti = Math.min(1, canhToiDa / canh);
    const w = Math.max(1, Math.round(anh.naturalWidth * ti));
    const h = Math.max(1, Math.round(anh.naturalHeight * ti));

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(anh, 0, 0, w, h);

    const blob = await new Promise<Blob | null>((xong) =>
      canvas.toBlob(xong, "image/webp", CHAT_LUONG),
    );
    if (!blob) return null;

    const buf = await blob.arrayBuffer();
    // `btoa` cần chuỗi nhị phân. Chuyển theo khối để không vượt trần số tham số
    // của `String.fromCharCode` với một ảnh vài trăm KB.
    const bytes = new Uint8Array(buf);
    let nhi = "";
    for (let i = 0; i < bytes.length; i += 8192) {
      nhi += String.fromCharCode(...bytes.subarray(i, i + 8192));
    }
    return {
      base64: btoa(nhi),
      mime: "image/webp",
      width: w,
      height: h,
      bytes: blob.size,
      xemTruoc: URL.createObjectURL(blob),
    };
  } finally {
    URL.revokeObjectURL(nguon);
  }
}

export function PostComposer({
  limits,
  storyOptions = [],
  onPosted,
}: {
  /** Giới hạn của MÁY CHỦ. `null` = chưa tải được; hộp vẫn dùng được. */
  limits: ServerLimits | null;
  /** Truyện đã xuất bản của chính mình — để đăng "cập nhật truyện". Rỗng với
      người chưa là tác giả đã duyệt. */
  storyOptions?: ReadonlyArray<{ novel_id: string; title: string }>;
  onPosted: (post: Post) => void;
}) {
  const { profile } = useSession();
  const [moRong, setMoRong] = useState(false);
  const [chu, setChu] = useState("");
  const [truyenId, setTruyenId] = useState("");
  const [anhDs, setAnhDs] = useState<AnhDaXuLy[]>([]);
  const [dangXuLyAnh, setDangXuLyAnh] = useState(false);
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState("");
  const oTep = useRef<HTMLInputElement | null>(null);
  const oChu = useRef<HTMLTextAreaElement | null>(null);

  const tranChu = limits?.post_max_chars ?? 2000;
  const canhToiDa = limits?.image?.post?.max_edge ?? CANH_DU_PHONG;
  const tranByte = limits?.image?.post?.max_bytes ?? 1024 * 1024;
  const tranSoAnh = limits?.post_max_images ?? 4;
  const tranTongByte = limits?.post_total_media_bytes ?? 3 * 1024 * 1024;

  /* Thu hồi MỌI URL xem trước khi danh sách đổi hoặc thành phần biến mất.
     Không thu hồi thì blob nằm lại trong bộ nhớ tab tới khi tải lại trang. */
  useEffect(() => {
    const urls = anhDs.map((a) => a.xemTruoc);
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [anhDs]);

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
            // Nói rõ con số thật thay vì để máy chủ từ chối sau khi người
            // dùng đã chờ hết đường truyền.
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
        // Xoá giá trị ô tệp để chọn LẠI CÙNG một tệp vẫn kích hoạt `onChange`.
        if (oTep.current) oTep.current.value = "";
      }
    },
    [anhDs, canhToiDa, tranByte, tranSoAnh, tranTongByte],
  );

  const gui = useCallback(async () => {
    const noiDung = chu.trim();
    if (!noiDung && !anhDs.length) {
      setLoi("Hãy viết gì đó, hoặc chọn một ảnh.");
      return;
    }
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
      });
      setChu("");
      setTruyenId("");
      setAnhDs([]);
      setMoRong(false);
      onPosted(ra.post);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không đăng được bài.");
    } finally {
      setDangGui(false);
    }
  }, [chu, truyenId, anhDs, onPosted]);

  const conLai = tranChu - chu.length;
  const gan = chu.length >= tranChu * CANH_BAO;
  const tenToi = profile?.display_name || profile?.username || "?";

  /*
    HANG KICH HOAT — bang tin khong mo dau bang mot form trong trai. Day la
    mot <button> that: Enter/Space mo duoc, va tieu diem chay vao textarea
    ngay sau khi composer hien ra.
  */
  if (!moRong) {
    return (
      <section className="card soan-bai-moi" aria-label="Đăng bài mới">
        <span className="avatar" aria-hidden="true">
          {tenToi.slice(0, 2).toUpperCase()}
        </span>
        <button
          type="button"
          className="soan-bai-kich-hoat"
          onClick={() => {
            setMoRong(true);
            queueMicrotask(() => oChu.current?.focus());
          }}
        >
          Bạn đang nghĩ gì?
        </button>
      </section>
    );
  }

  return (
    <section className="card soan-bai" aria-labelledby="soan-bai-tieu-de">
      <h2 id="soan-bai-tieu-de" className="sr-only">
        Đăng bài mới
      </h2>
      <textarea
        ref={oChu}
        className="input soan-bai-o"
        rows={3}
        maxLength={tranChu}
        value={chu}
        onChange={(e) => setChu(e.target.value)}
        placeholder="Bạn đang nghĩ gì?"
        aria-label="Nội dung bài đăng"
      />

      {anhDs.length ? (
        <div className="soan-bai-anh">
          {anhDs.map((a, i) => (
            <figure key={a.xemTruoc} className="soan-bai-anh-o">
              {/* `<img>` thuần: blob cục bộ, `next/image` không nhận blob URL. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={a.xemTruoc} alt={`Ảnh ${i + 1} sẽ đăng kèm`} />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label={`Bỏ ảnh ${i + 1}`}
                onClick={() =>
                  setAnhDs((ds) => ds.filter((x) => x !== a))
                }
              >
                ✕
              </button>
              <figcaption className="hint">
                {(a.bytes / 1024).toFixed(0)} KB
              </figcaption>
            </figure>
          ))}
        </div>
      ) : null}

      <div className="soan-bai-day">
        <label className="btn btn-ghost btn-sm soan-bai-tep">
          {dangXuLyAnh
            ? "Đang xử lý…"
            : `🖼 Thêm ảnh (${anhDs.length}/${tranSoAnh})`}
          <input
            ref={oTep}
            type="file"
            multiple
            accept={(limits?.image?.post?.mime ?? ["image/*"]).join(",")}
            onChange={(e) => void chonTep(e.target.files)}
            disabled={dangXuLyAnh || anhDs.length >= tranSoAnh}
          />
        </label>

        {storyOptions.length > 0 ? (
          <label className="hint soan-bai-truyen">
            Gắn truyện
            <select
              className="input"
              value={truyenId}
              onChange={(e) => setTruyenId(e.target.value)}
            >
              <option value="">— Bài thường —</option>
              {storyOptions.map((t) => (
                <option key={t.novel_id} value={t.novel_id}>
                  {t.title}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <span className={gan ? "hint loi" : "hint"} aria-live="polite">
          {conLai} ký tự
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setMoRong(false)}
        >
          Thu gọn
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={dangGui || dangXuLyAnh}
          onClick={gui}
        >
          {dangGui ? "Đang đăng…" : "Đăng"}
        </button>
      </div>

      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}

      {/* Nói rõ rằng ảnh bị vẽ lại. Người dùng có quyền biết dữ liệu vị trí
          trong ảnh của họ không đi ra ngoài. */}
      <p className="hint soan-bai-ghi-chu">
        Ảnh được nén lại trong trình duyệt và <strong>bỏ hết metadata</strong>{" "}
        (kể cả toạ độ GPS) trước khi gửi. Tối đa {tranSoAnh} ảnh mỗi bài.
      </p>
    </section>
  );
}
