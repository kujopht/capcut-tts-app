"use client";

/**
 * Hộp soạn bài đăng.
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
  const [chu, setChu] = useState("");
  const [truyenId, setTruyenId] = useState("");
  const [anh, setAnh] = useState<AnhDaXuLy | null>(null);
  const [dangXuLyAnh, setDangXuLyAnh] = useState(false);
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState("");
  const oTep = useRef<HTMLInputElement | null>(null);

  const tranChu = limits?.post_max_chars ?? 2000;
  const canhToiDa = limits?.image?.post?.max_edge ?? CANH_DU_PHONG;
  const tranByte = limits?.image?.post?.max_bytes ?? 1024 * 1024;

  /* Thu hồi URL xem trước khi ảnh bị thay hoặc thành phần biến mất. Không thu
     hồi thì blob nằm lại trong bộ nhớ của tab cho tới khi tải lại trang. */
  useEffect(() => {
    const url = anh?.xemTruoc;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [anh?.xemTruoc]);

  const chonTep = useCallback(
    async (tep: File | undefined) => {
      if (!tep) return;
      setLoi("");
      setDangXuLyAnh(true);
      try {
        const ra = await xuLyAnh(tep, canhToiDa);
        if (!ra) {
          setLoi("Không đọc được ảnh này. Hãy thử một tệp khác.");
          return;
        }
        if (ra.bytes > tranByte) {
          // Đã nén hết cỡ mà vẫn vượt trần: nói rõ con số thật thay vì để máy
          // chủ từ chối sau khi người dùng đã chờ hết đường truyền.
          setLoi(
            `Ảnh vẫn còn ${(ra.bytes / 1024 / 1024).toFixed(1)} MB sau khi nén ` +
              `(trần ${(tranByte / 1024 / 1024).toFixed(1)} MB). Hãy chọn ảnh nhỏ hơn.`,
          );
          URL.revokeObjectURL(ra.xemTruoc);
          return;
        }
        setAnh(ra);
      } finally {
        setDangXuLyAnh(false);
        // Xoá giá trị ô tệp để chọn LẠI CÙNG một tệp vẫn kích hoạt `onChange`.
        if (oTep.current) oTep.current.value = "";
      }
    },
    [canhToiDa, tranByte],
  );

  const gui = useCallback(async () => {
    const noiDung = chu.trim();
    if (!noiDung && !anh) {
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
        image_base64: anh?.base64,
        image_mime: anh?.mime,
        image_width: anh?.width,
        image_height: anh?.height,
      });
      setChu("");
      setTruyenId("");
      setAnh(null);
      onPosted(ra.post);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không đăng được bài.");
    } finally {
      setDangGui(false);
    }
  }, [chu, truyenId, anh, onPosted]);

  const conLai = tranChu - chu.length;
  const gan = chu.length >= tranChu * CANH_BAO;

  return (
    <section className="card soan-bai" aria-labelledby="soan-bai-tieu-de">
      <h2 id="soan-bai-tieu-de" className="sr-only">
        Đăng bài mới
      </h2>
      <textarea
        className="input soan-bai-o"
        rows={3}
        maxLength={tranChu}
        value={chu}
        onChange={(e) => setChu(e.target.value)}
        placeholder="Bạn đang đọc gì? Chia sẻ vài dòng…"
        aria-label="Nội dung bài đăng"
      />

      {anh ? (
        <div className="soan-bai-anh">
          {/* `<img>` thuần, không phải `next/image`: đây là một blob cục bộ,
              không có gì để tối ưu và `next/image` không nhận blob URL. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={anh.xemTruoc} alt="Ảnh sẽ đăng kèm" />
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setAnh(null)}
          >
            Bỏ ảnh
          </button>
          <span className="hint">
            {anh.width}×{anh.height} · {(anh.bytes / 1024).toFixed(0)} KB · WebP
          </span>
        </div>
      ) : null}

      <div className="soan-bai-day">
        <label className="btn btn-ghost btn-sm soan-bai-tep">
          {dangXuLyAnh ? "Đang xử lý…" : "🖼 Thêm ảnh"}
          <input
            ref={oTep}
            type="file"
            accept={(limits?.image?.post?.mime ?? ["image/*"]).join(",")}
            onChange={(e) => void chonTep(e.target.files?.[0])}
            disabled={dangXuLyAnh || !!anh}
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
        (kể cả toạ độ GPS) trước khi gửi. Tối đa {limits?.post_max_images ?? 1}{" "}
        ảnh mỗi bài.
      </p>
    </section>
  );
}
