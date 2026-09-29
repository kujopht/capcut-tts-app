/**
 * Cắt/phóng ảnh cho trình sửa hồ sơ (Social & Play V1): avatar vuông, ảnh bìa
 * 3:1.
 *
 * Phần TOÁN (khung nhìn, phóng, kéo, kẹp biên) là thuần — kiểm bằng
 * `tests/profile-image.test.mjs`. Phần vẽ `<canvas>` chỉ chạy ở trình duyệt.
 *
 * Trình duyệt chỉ cắt để người dùng THẤY đúng cái sẽ lưu và để gửi đi một ảnh
 * nhỏ. MÁY CHỦ vẫn giải mã lại, kẹp kích thước, mã hoá lại và bỏ metadata —
 * đây không phải hàng rào.
 */

export interface KhungCat {
  /** Kích thước ảnh gốc (px). */
  anhW: number;
  anhH: number;
  /** Kích thước khung nhìn trên màn hình (px). */
  khungW: number;
  khungH: number;
  /** Hệ số phóng >= 1 (1 = vừa phủ kín khung). */
  phong: number;
  /** Vị trí góc trên-trái của ảnh ĐÃ PHÓNG so với khung (px, <= 0). */
  x: number;
  y: number;
}

export const PHONG_TOI_DA = 4;

/** Tỉ lệ để ảnh PHỦ KÍN khung (kiểu `object-fit: cover`). */
export function tiLePhu(k: Pick<KhungCat, "anhW" | "anhH" | "khungW" | "khungH">): number {
  if (k.anhW <= 0 || k.anhH <= 0) return 1;
  return Math.max(k.khungW / k.anhW, k.khungH / k.anhH);
}

/** Kẹp vị trí để ảnh luôn phủ kín khung — không bao giờ lộ nền trống. */
export function kepViTri(k: KhungCat): KhungCat {
  const phong = Math.min(PHONG_TOI_DA, Math.max(1, Number.isFinite(k.phong) ? k.phong : 1));
  const s = tiLePhu(k) * phong;
  const w = k.anhW * s;
  const h = k.anhH * s;
  const x = Math.min(0, Math.max(k.khungW - w, k.x));
  const y = Math.min(0, Math.max(k.khungH - h, k.y));
  return { ...k, phong, x, y };
}

/** Khung ban đầu: phủ kín, căn giữa. */
export function khungDau(anhW: number, anhH: number, khungW: number, khungH: number): KhungCat {
  const s = tiLePhu({ anhW, anhH, khungW, khungH });
  return kepViTri({
    anhW,
    anhH,
    khungW,
    khungH,
    phong: 1,
    x: (khungW - anhW * s) / 2,
    y: (khungH - anhH * s) / 2,
  });
}

/**
 * Phóng quanh TÂM khung (không nhảy về góc): điểm ảnh đang ở giữa khung vẫn ở
 * giữa sau khi phóng.
 */
export function doiPhong(k: KhungCat, phongMoi: number): KhungCat {
  const s0 = tiLePhu(k) * k.phong;
  const p = Math.min(PHONG_TOI_DA, Math.max(1, phongMoi));
  const s1 = tiLePhu(k) * p;
  const cx = (k.khungW / 2 - k.x) / s0;
  const cy = (k.khungH / 2 - k.y) / s0;
  return kepViTri({ ...k, phong: p, x: k.khungW / 2 - cx * s1, y: k.khungH / 2 - cy * s1 });
}

export function keo(k: KhungCat, dx: number, dy: number): KhungCat {
  return kepViTri({ ...k, x: k.x + dx, y: k.y + dy });
}

/** Vùng NGUỒN (toạ độ ảnh gốc) tương ứng với khung đang thấy. */
export function vungNguon(k: KhungCat): { sx: number; sy: number; sw: number; sh: number } {
  const s = tiLePhu(k) * k.phong;
  return {
    sx: Math.max(0, -k.x / s),
    sy: Math.max(0, -k.y / s),
    sw: Math.min(k.anhW, k.khungW / s),
    sh: Math.min(k.anhH, k.khungH / s),
  };
}

// ------------------------------------------------------------ chi trinh duyet

export interface AnhCat {
  base64: string;
  mime: string;
  bytes: number;
  /** URL blob để xem trước — người gọi phải `URL.revokeObjectURL`. */
  xemTruoc: string;
}

export function taiAnh(tep: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(tep);
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Không đọc được ảnh này."));
    };
    img.src = url;
  });
}

/** Vẽ vùng đã chọn ra `outW×outH` WebP — vẽ lại qua canvas nên bỏ hết metadata. */
export async function xuatAnhCat(img: HTMLImageElement, k: KhungCat, outW: number, outH: number): Promise<AnhCat> {
  const c = document.createElement("canvas");
  c.width = outW;
  c.height = outH;
  const ctx = c.getContext("2d");
  if (!ctx) throw new Error("Trình duyệt không vẽ được ảnh.");
  const v = vungNguon(k);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, v.sx, v.sy, v.sw, v.sh, 0, 0, outW, outH);
  const blob: Blob | null = await new Promise((r) => c.toBlob(r, "image/webp", 0.88));
  if (!blob) throw new Error("Không xuất được ảnh.");
  const buf = new Uint8Array(await blob.arrayBuffer());
  let nhiPhan = "";
  for (let i = 0; i < buf.length; i += 0x8000) {
    nhiPhan += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  }
  return {
    base64: btoa(nhiPhan),
    mime: blob.type || "image/webp",
    bytes: blob.size,
    xemTruoc: URL.createObjectURL(blob),
  };
}
