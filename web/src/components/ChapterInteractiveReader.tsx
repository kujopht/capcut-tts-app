"use client";

import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { ReaderPrefs, ReaderProgress } from "@/components/ReaderPrefs";
import { MAC_DINH, type TuyChonDoc } from "@/lib/readerPrefs";

const ReaderContext = createContext<(d: TuyChonDoc) => void>(() => {});

export function ChapterInteractiveReader({
  novelId,
  chapterId,
  children,
}: {
  novelId: string;
  chapterId: string;
  children: React.ReactNode;
}) {
  const { profile } = useSession();
  const [tuyChon, datTuyChon] = useState<TuyChonDoc>(MAC_DINH);

  useEffect(() => {
    if (!profile) return;
    api.reportReadProgress(novelId, chapterId).catch(() => {});
  }, [profile?.user_id, novelId, chapterId]);

  return (
    <ReaderContext.Provider value={datTuyChon}>
      <div className="page" data-doc-co={tuyChon.coChu} data-doc-ngang={tuyChon.beNgang}>
        <ReaderProgress />
        {children}
      </div>
    </ReaderContext.Provider>
  );
}

export function ChapterReaderPrefsControl() {
  const datTuyChon = useContext(ReaderContext);
  return <ReaderPrefs onDoi={datTuyChon} />;
}

export function ChapterOwnerAudioAction({ ownerId }: { ownerId: string }) {
  const { profile } = useSession();
  if (profile?.user_id !== ownerId) return null;
  return (
    <Link className="btn btn-sm btn-ghost" href="/studio/write" prefetch={false}>
      <span aria-hidden="true">🎙️</span> Tạo audio cho chương
    </Link>
  );
}
