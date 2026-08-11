"use client";

/**
 * Khong khi song cua tung khu vuc — vai dom sang troi rat cham.
 *
 * BA rang buoc dinh hinh ca thiet ke nay:
 *
 *   1. KHONG khung particle, khong canvas, khong WebGL. Mot bo may hat cho vai
 *      dom sang la mot thu viec chay lien tuc tren CPU cua nguoi doc de doi lay
 *      mot thu ho khong nhin thang vao.
 *   2. TOI DA 10 phan tu moi trang, va phan lon la khong. Cac dom sang nen la
 *      lop `radial-gradient` tren MOT the (`.hat`), khong phai vai tram `<div>`.
 *      Cac the o day chi danh cho thu KHONG ve bang gradient duoc: mot ngoi sao
 *      bang di qua, mot canh hoa roi.
 *   3. KHONG mot thu gi chuyen dong sau mot doan van dai. Trang doc chuong chi
 *      duoc phep co vai dom sang QUANH khoi nghe, va tuyet doi khong o phia sau
 *      cac doan van.
 *
 * `prefers-reduced-motion` tat het — xem cuoi `globals.css`.
 *
 * Vi sao mot component chu khong phai CSS thuan: so luong va do tre cua tung
 * phan tu can duoc VIET RA de doc lai duoc, va mot mang `map()` noi dieu do ro
 * han muoi quy tac `:nth-child`.
 */

import { viTri, type ViTri } from "@/lib/sections";

/** Mot hat trang tri: vi tri (%), kich thuoc (px), do tre va nhip (giay). */
type Hat = { t: number; l: number; co: number; tre: number; nhip: number };

/**
 * Canh hoa dao roi o `/account`, va sao bang o `/login`.
 *
 * Cac con so o day duoc VIET TAY chu khong sinh ngau nhien: mot mang ngau nhien
 * doi moi lan ve lai, va tren Next thi ban may chu va ban trinh duyet se ra hai
 * ket qua khac nhau — React se bao "hydration mismatch". Viet tay cung de nhin
 * vao la biet co bao nhieu phan tu.
 */
const CANH_HOA: Hat[] = [
  { t: -6, l: 12, co: 11, tre: 0, nhip: 19 },
  { t: -8, l: 34, co: 8, tre: 6.5, nhip: 23 },
  { t: -5, l: 58, co: 13, tre: 12, nhip: 21 },
  { t: -9, l: 78, co: 9, tre: 3.5, nhip: 26 },
  { t: -7, l: 91, co: 10, tre: 15, nhip: 24 },
];

/**
 * Sao bang o trang dang nhap.
 *
 * THUA la ca dieu quan trong: mot vet sang lap lien tuc doc ra nhu mot cai den
 * bao, khong phai nhu bau troi. Ba vet, moi vet mot nhip dai va mot do tre
 * khac nhau, nen khoang cach giua hai lan thay duoc la 12-25 giay va khong bao
 * gio deu dan.
 */
const SAO_BANG: Hat[] = [
  { t: 8, l: 62, co: 150, tre: 3, nhip: 17 },
  { t: 22, l: 28, co: 110, tre: 11, nhip: 23 },
  { t: 5, l: 84, co: 130, tre: 19, nhip: 29 },
];

/** Dom sang am quanh khoi nghe o trang doc chuong. */
const DOM_NGHE: Hat[] = [
  { t: 18, l: 8, co: 3, tre: 0, nhip: 13 },
  { t: 62, l: 4, co: 2, tre: 4, nhip: 17 },
  { t: 34, l: 94, co: 3, tre: 8, nhip: 15 },
  { t: 78, l: 88, co: 2, tre: 2, nhip: 19 },
];

function style(h: Hat): React.CSSProperties {
  return {
    top: `${h.t}%`,
    left: `${h.l}%`,
    // `--co` di qua bien de CSS dung cho ca chieu rong lan chieu cao, va de mot
    // hinh dai (sao bang) chi phai khai mot con so.
    ["--co" as string]: `${h.co}px`,
    ["--tre" as string]: `${h.tre}s`,
    ["--nhip" as string]: `${h.nhip}s`,
  };
}

/**
 * Lop khong khi cua mot khu vuc.
 *
 * Dat o `layout.tsx`, ben trong lop nen. `pointer-events: none` va
 * `aria-hidden` — day la thu de nhin, khong phai thu de dung.
 */
export function AmbientScene({ duongDan }: { duongDan: string }) {
  const noi: ViTri = viTri(duongDan);

  /*
    CHI ba noi co the trang tri. Cac khu lam viec — `/studio`, `/write`,
    `/library`, `/fanfic` — khong co gi chuyen dong ca: dom sang cua chung da
    nam o lop `.hat` (CSS thuan) hoac khong co, va mot thu dang troi ben canh
    mot o soan thao la thu lam met mat sau nam phut.
  */
  if (noi === "account") {
    return (
      <div className="canh-troi" aria-hidden="true">
        {CANH_HOA.map((h, i) => (
          <span key={i} className="canh-hoa" style={style(h)} />
        ))}
      </div>
    );
  }

  if (noi === "ngoai") {
    return (
      <div className="canh-troi" aria-hidden="true">
        {SAO_BANG.map((h, i) => (
          <span key={i} className="sao-bang" style={style(h)} />
        ))}
      </div>
    );
  }

  if (noi === "long" && duongDan.startsWith("/chapters/")) {
    return (
      <div className="canh-troi canh-nghe" aria-hidden="true">
        {DOM_NGHE.map((h, i) => (
          <span key={i} className="dom-nghe" style={style(h)} />
        ))}
      </div>
    );
  }

  return null;
}
