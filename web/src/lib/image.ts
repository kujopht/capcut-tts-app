/**
 * Xu ly anh o TRINH DUYET truoc khi gui len may chu.
 *
 * Trich tu `PostComposer.tsx` (V3) de dung chung cho anh bia truyen (V4) —
 * cung mot ly do ton tai: mot anh chup dien thoai la 4-8 MB trong khi tran
 * may chu chi 1-2 MB, va ve lai qua `<canvas>` bỏ hết metadata (kể cả EXIF —
 * toạ độ GPS) truoc khi xuat WebP. May chu VAN kiem lai; day chi de cu bam
 * thanh cong, khong phai hang rao that.
 */

export interface AnhDaXuLy {
  base64: string;
  mime: string;
  width: number;
  height: number;
  bytes: number;
  /** URL tam de xem truoc. PHAI duoc thu hoi bang `URL.revokeObjectURL`. */
  xemTruoc: string;
}

/**
 * Ve lai mot anh ve trong gioi han va xuat WebP.
 *
 * Tra `null` khi trinh duyet khong doc duoc tep — mot tep hong hay doi duoi
 * deu roi vao day, va ca hai deu nen noi "khong doc duoc anh" thay vi lam
 * hong ca luong tai len.
 */
export async function xuLyAnh(
  tep: File,
  canhToiDa: number,
  chatLuong = 0.82,
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
      canvas.toBlob(xong, "image/webp", chatLuong),
    );
    if (!blob) return null;

    const buf = await blob.arrayBuffer();
    // `btoa` can chuoi nhi phan. Chuyen theo khoi de khong vuot tran so tham
    // so cua `String.fromCharCode` voi mot anh vai tram KB.
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
