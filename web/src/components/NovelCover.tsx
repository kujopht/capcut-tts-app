/**
 * Anh bia truyen.
 *
 * Co bia that (`cover_url` do backend cap) thi hien anh do. Chua co thi dung
 * anh du phong SINH RA TU CHINH TEN TRUYEN — khong tai anh gia tu dau ca.
 *
 * CACH DUNG HAI LOP: lop duoi luon la anh du phong, lop tren la bia that dat
 * bang `background-image`. Neu URL bia hong hoac het han, lop tren khong ve gi
 * va lop duoi lo ra — khong can bat loi bang JavaScript. Dung nen thay vi the
 * anh cung giup khong vuong quy tac `no-img-element`.
 *
 * Anh du phong phai ON DINH: cung mot truyen luon ra cung mau, de nguoi dung
 * nhan ra truyen quen o moi trang. Nen mau lay tu ham bam cua `novel_id`.
 */

import { coverInitial, paletteFor } from "@/lib/cover";

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
        <span className="cover-initial">{coverInitial(title)}</span>
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
