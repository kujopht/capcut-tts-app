"use client";

import Link from "next/link";
import { useSession } from "@/lib/session";

export function NovelOwnerActions({ ownerId }: { ownerId: string }) {
  const { profile } = useSession();
  if (profile?.user_id !== ownerId) return null;
  return (
    <Link className="btn" href="/studio/write" prefetch={false}>
      Quản lý truyện
    </Link>
  );
}

export function OwnerAddChapterAction({ ownerId }: { ownerId: string }) {
  const { profile } = useSession();
  if (profile?.user_id !== ownerId) return null;
  return (
    <Link className="btn btn-primary" href="/studio/write" prefetch={false}>
      Thêm chương đầu tiên
    </Link>
  );
}
