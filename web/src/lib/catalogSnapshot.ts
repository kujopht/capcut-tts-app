/**
 * ANH CHUP KHO TRUYEN cong khai (moi dinh dang), toi da `TRAN_CUC_BO` truyen.
 *
 * Dung chung cho Thu vien (chip fandom that + loc tai cho khi ca kho nam gon
 * trong anh chup) va o tim kiem (goi y fandom / tac gia / ten truyen TUC THI,
 * truoc khi backend tra loi).
 *
 * MOT request, dung lai 5 phut, chia se giua moi noi goi — mo o tim roi vao
 * Thu vien khong tai lai. Loi thi tra `du = false` va danh sach rong: noi goi
 * tu quay ve duong may chu, khong hong gi.
 *
 * VI SAO lai tai "ca kho": kho hien co 20 truyen (7 doc duoc + 13 audio cu) —
 * nho hon mot trang ket qua cua nhieu trang web. Do that tren production
 * 2026-09-25: moi truy van loc cua backend ton tu 2 toi hon 30 giay. Kho vuot
 * tran thi `du = false` va moi thu tu dong ve lai duong may chu.
 */

import { api, type Novel } from "./api";
import { TRAN_CUC_BO } from "./libraryQuery";

export interface AnhChupKho {
  novels: Novel[];
  /** Anh chup chua CA kho (khong con truyen nao sau tran). */
  du: boolean;
}

const HAN_MS = 5 * 60 * 1000;
let _kho: { luc: number; p: Promise<AnhChupKho> } | null = null;

export function taiAnhChupKho(): Promise<AnhChupKho> {
  if (!_kho || Date.now() - _kho.luc > HAN_MS) {
    const p = api
      .browseNovels({ content_mode: "all", sort: "updated", limit: TRAN_CUC_BO, offset: 0 })
      .then((r) => ({
        novels: r.novels,
        du: !r.has_more && r.novels.length === (r.total ?? r.novels.length),
      }))
      .catch(() => {
        _kho = null;
        return { novels: [] as Novel[], du: false };
      });
    _kho = { luc: Date.now(), p };
  }
  return _kho.p;
}
