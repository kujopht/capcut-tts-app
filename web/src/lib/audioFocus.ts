/**
 * DIEU PHOI TIENG — ai duoc phat khi hai nguon am thanh cung muon len tieng.
 *
 * Hien co hai kenh:
 *   - "narration": giong doc chuong (`AudioEngine`, the `<audio>` DUY NHAT cua
 *     truyen);
 *   - "ambient":   nhac nen cua site (`lib/musicStore.ts`, co the audio rieng
 *     cua no — do la nhac, khong phai chuong truyen).
 *
 * LUAT: giong doc truyen > nhac nen. Khi giong doc bat dau, moi kenh uu tien
 * THAP HON nhan lenh "pause" (hanh vi hom nay) hoac "duck" (ha am luong — da
 * co san duong di, chua bat). Sprint nay KHONG lam san pham nhac day du; tep
 * nay chi la cai khop noi de lam sau khoi phai sua `AudioEngine` lan nua:
 * truoc day engine goi thang `musicStore.pause()`, tuc la dong co truyen phai
 * biet ve mot kho nhac cu the.
 *
 * Tep thuan, khong DOM — bai kiem Node chay thang (`tests/audio-focus.test.mjs`).
 */

export type KenhAm = "narration" | "ambient";
export type KieuNhuong = "pause" | "duck";

export interface DangKyKenh {
  /** So LON hon thang. */
  uuTien: number;
  /** Bi mot kenh uu tien cao hon cat ngang. Phai la no-op neu dang im. */
  khiBiCat: (kieu: KieuNhuong) => void;
  /** Kenh cao hon da tra lai quyen. Chi goi cho kenh da bi "duck". */
  khiDuocTraLai?: () => void;
}

export const UU_TIEN: Record<KenhAm, number> = { narration: 100, ambient: 10 };

/**
 * Kenh thap bi xu ly THE NAO khi kenh cao len tieng. "pause" cho nhac nen la
 * lua chon an toan hom nay: nghe truyen co nhac chen vao la mot phan nan co
 * that. Doi sang "duck" la doi MOT dong o day.
 */
export const CHINH_SACH: Record<KenhAm, KieuNhuong> = { narration: "pause", ambient: "pause" };

export class DieuPhoiAm {
  private kenh = new Map<KenhAm, DangKyKenh>();
  private dangGiu = new Set<KenhAm>();
  private biDuck = new Set<KenhAm>();

  dangKy(ten: KenhAm, dk: DangKyKenh): () => void {
    this.kenh.set(ten, dk);
    return () => {
      if (this.kenh.get(ten) === dk) this.kenh.delete(ten);
      this.dangGiu.delete(ten);
      this.biDuck.delete(ten);
    };
  }

  /** Kenh `ten` bat dau phat. Cat moi kenh uu tien thap hon. */
  yeuCau(ten: KenhAm): void {
    this.dangGiu.add(ten);
    const cua = this.kenh.get(ten)?.uuTien ?? UU_TIEN[ten];
    const kieu = CHINH_SACH[ten];
    for (const [khac, dk] of this.kenh) {
      if (khac === ten || dk.uuTien >= cua) continue;
      try {
        dk.khiBiCat(kieu);
        if (kieu === "duck") this.biDuck.add(khac);
      } catch {
        /* Mot kenh hong khong duoc chan giong doc. */
      }
    }
  }

  /** Kenh `ten` dung/het. Kenh bi "duck" duoc tra lai am luong; kenh bi
      "pause" KHONG tu phat lai — tu dung nhac len khi nguoi dung khong bam
      gi la bat ngo. */
  traLai(ten: KenhAm): void {
    if (!this.dangGiu.delete(ten)) return;
    for (const khac of [...this.biDuck]) {
      const dk = this.kenh.get(khac);
      this.biDuck.delete(khac);
      try {
        dk?.khiDuocTraLai?.();
      } catch {
        /* bo qua */
      }
    }
  }

  /** Kenh uu tien cao nhat dang phat, hoac null. */
  kenhDangGiu(): KenhAm | null {
    let tot: KenhAm | null = null;
    let diem = -Infinity;
    for (const ten of this.dangGiu) {
      const u = this.kenh.get(ten)?.uuTien ?? UU_TIEN[ten];
      if (u > diem) {
        diem = u;
        tot = ten;
      }
    }
    return tot;
  }
}

/** MOT bo dieu phoi cho ca trang. */
export const audioFocus = new DieuPhoiAm();
