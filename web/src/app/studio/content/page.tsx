"use client";

/**
 * NỘI DUNG — Viết truyện va Dịch trong MOT khong gian.
 *
 * Truoc ban nay day la hai diem den o thanh ben, va nguoi dung phai tu hieu
 * rang hai cai do la hai nua cua cung mot viec. Ho khong tu hieu: bao cao tu
 * trang that noi thanh ben "boc lo qua nhieu cong cu o tang cai dat".
 *
 * Hai the nay KHONG phai hai trang duoc dan canh nhau. Chung dung chung mot
 * tham so URL (`?tab=`), nen mot lien ket gui cho nguoi khac van mo dung the
 * — va hai duong dan cu (`/studio/write`, `/studio/translate`) chuyen thang
 * vao dung the cua no thay vi do nguoi dung xuong mot trang khong quen.
 *
 * Than cua tung the la CHINH hai trang cu, khong viet lai: chung da chay
 * that, da co bo kiem rieng, va viet lai 2.400 dong de doi mot cai khung la
 * cach chac chan nhat de danh mat nhung thu chung da xu ly dung.
 */

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import VietTruyen from "@/components/studio/VietTruyen";
import DichTieuThuyet from "@/components/studio/DichTieuThuyet";
import { Loading } from "@/components/ui";

const THE = [
  { ma: "write", nhan: "Nội dung" },
  { ma: "translate", nhan: "Dịch" },
] as const;

type MaThe = (typeof THE)[number]["ma"];

function KhongGianNoiDung() {
  const router = useRouter();
  const params = useSearchParams();
  const the: MaThe = params.get("tab") === "translate" ? "translate" : "write";

  /*
    Doi the ghi vao URL bang `replace` chu khong phai `push`.

    Bam qua lai giua hai the la mot thao tac XEM, khong phai mot buoc dieu
    huong. Dung `push` thi nut Back cua trinh duyet phai di nguoc tung lan
    bam the truoc khi roi duoc khoi trang — va do la cach nhanh nhat de mot
    nguoi dung bam Back nam lan ma van thay minh o nguyen cho cu.
  */
  const doiThe = useCallback(
    (ma: MaThe) => {
      router.replace(ma === "write" ? "/studio/content" : `/studio/content?tab=${ma}`,
                     { scroll: false });
    },
    [router],
  );

  return (
    <div className="stack-4 sc">
      <div className="sc-the-hang" role="tablist" aria-label="Nội dung">
        {THE.map(({ ma, nhan }) => (
          <button
            key={ma}
            type="button"
            role="tab"
            id={`sc-tab-${ma}`}
            aria-selected={the === ma}
            aria-controls={`sc-bang-${ma}`}
            className={`sc-the${the === ma ? " sc-the-mo" : ""}`}
            onClick={() => doiThe(ma)}
          >
            {nhan}
          </button>
        ))}
      </div>

      {/*
        CA HAI the deu duoc dung, va the khong mo thi bi AN bang `hidden`.

        Thao roi gan lai se lam mat toan bo trang thai cua the kia — ban nhap
        dang go do, chuong dang chon, job dang chay. Mot nguoi liec sang tab
        Dịch roi quay lai khong duoc phep mat doan van vua viet.
      */}
      <div
        role="tabpanel"
        id="sc-bang-write"
        aria-labelledby="sc-tab-write"
        hidden={the !== "write"}
      >
        <VietTruyen />
      </div>
      <div
        role="tabpanel"
        id="sc-bang-translate"
        aria-labelledby="sc-tab-translate"
        hidden={the !== "translate"}
      >
        <DichTieuThuyet />
      </div>
    </div>
  );
}

export default function TrangNoiDung() {
  // `useSearchParams` doi mot ranh gioi Suspense khi dung o trang tinh.
  return (
    <Suspense fallback={<Loading />}>
      <KhongGianNoiDung />
    </Suspense>
  );
}
