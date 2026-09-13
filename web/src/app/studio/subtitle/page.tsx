"use client";

/** Duong dan cu — xem `components/studio/ChuyenHuong` cho ly do. */

import { Suspense } from "react";
import { ChuyenHuong } from "@/components/studio/ChuyenHuong";
import { Loading } from "@/components/ui";

export default function Trang() {
  return (
    <Suspense fallback={<Loading />}>
      <ChuyenHuong den="/studio/media?panel=subtitle" />
    </Suspense>
  );
}
