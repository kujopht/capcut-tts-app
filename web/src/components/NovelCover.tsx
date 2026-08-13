/**
 * Anh bia truyen.
 *
 * Co bia that (`cover_url` do backend cap) thi hien anh do. Chua co thi ve mot
 * BIA DU PHONG duoc thiet ke — khong tai anh gia tu dau ca, va KHONG dung
 * tranh nen toan trang: nhung tam do la khong khi cua site, khong phai bia cua
 * mot truyen cu the.
 *
 * CACH DUNG HAI LOP: lop duoi luon la bia du phong, lop tren la bia that dat
 * bang `background-image`. Neu URL bia hong hoac het han, lop tren khong ve gi
 * va lop duoi lo ra — khong can bat loi bang JavaScript. Dung nen thay vi the
 * anh cung giup khong vuong quy tac `no-img-element`.
 *
 * Bia du phong phai ON DINH: cung mot truyen luon ra cung mau, de nguoi dung
 * nhan ra truyen quen o moi trang. Nen mau lay tu ham bam cua `novel_id`.
 *
 * BAN TRUOC chi la mot chu cai to dat giua mot mang gradient — no doc ra la
 * "cho nay chua lam xong". Ban nay ve mot HUY HIEU: khung vien, hoa van mo o
 * nen, va chu cai nam trong do nhu mot dau an. Cung mot du lieu, nhung trong
 * ra co chu y.
 *
 * Khi backend co bia that, chi can truyen `coverUrl` — khong phai sua gi o day.
 */

import { paletteFor } from "@/lib/cover";
import { StoryCoverFallback } from "@/components/StoryCoverFallback";

export function NovelCover({
  novelId,
  title,
  coverUrl,
  size = "card",
}: {
  novelId: string;
  title: string;
  coverUrl?: string | null;
  /** `card` cho luoi truyen, `wide` cho dau trang, `thumb` cho luong nghe. */
  size?: "card" | "wide" | "thumb";
}) {
  const [from, to] = paletteFor(novelId || title);

  return (
    <div className={`cover cover-${size}`}>
      <div
        className="cover-fallback"
        style={{ background: `linear-gradient(140deg, ${from}, ${to})` }}
        aria-hidden="true"
      >
        {/* Hoa van mo o nen — CSS thuan, khong tep anh nao. */}
        <span className="cover-pattern" />
        {/* Ca bo cuc dau an — dau an lon mo phia sau, khung huy hieu, dau an nho
            ro net. Xem `StoryCoverFallback`; o day khong con thao ra tung lop. */}
        <StoryCoverFallback seed={novelId || title} />
      </div>
      {coverUrl ? (
        <div
          className="cover-image"
          style={{ backgroundImage: `url("${coverUrl}")` }}
          role="img"
          aria-label={`Ảnh bìa truyện ${title}`}
        />
      ) : null}
    </div>
  );
}
