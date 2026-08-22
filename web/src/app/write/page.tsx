"use client";

/**
 * Khu vuc tac gia: tao / sua / xoa truyen va chuong, tao audio, xuat ban.
 *
 * Kho chua cua Audio Studio bi loc ra o day — audio tao nhanh khong phai
 * truyen fanfic.
 *
 * Moi thao tac ghi deu: hien trang thai dang chay -> cap nhat giao dien NGAY
 * khi backend tra ve -> toast thanh cong hoac loi. Thao tac xoa co modal xac
 * nhan noi ro se mat nhung gi.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  type Chapter,
  type Novel,
  type Voice,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { CongXuatBan, useTrangThaiCreator } from "@/components/PublishGate";
import { MAX_CHAPTER_CHARS, MAX_COVER_EDGE } from "@/lib/limits";
import {
  ALL_VOICES_LABEL,
  RECOMMENDED_LABEL,
  defaultVoiceId,
  usableVoices,
  voiceOptionLabel,
  voiceSections,
} from "@/lib/voices";
import { loginHref } from "@/lib/nav";
import { dangChayDauTien } from "@/lib/jobs";
import { useJobTracker } from "@/lib/useJobTracker";
import { fanficOnly } from "@/lib/workspace";
import { AudioPlayer } from "@/components/AudioPlayer";
import { JobProgress } from "@/components/JobProgress";
import { NovelCover } from "@/components/NovelCover";
import { xuLyAnh } from "@/lib/image";
import {
  Alert,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SkeletonList,
  formatNumber,
} from "@/components/ui";
import { IconFeather , IconBook, IconLibrary } from "@/components/Icons";
import { MotifInkFlourish } from "@/components/Ornaments";

/** Thao tac xoa dang cho xac nhan. */
type PendingDelete =
  | { kind: "novel"; id: string; title: string }
  | { kind: "chapter"; id: string; title: string; hasAudio: boolean }
  | null;

function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .slice(0, 6);
}

export default function WritePage() {
  const router = useRouter();
  const { profile, loading: sessionLoading } = useSession();
  const toast = useToast();
  /*
    Trang thai tac gia, nap MOT lan cho ca trang. Chi nut xuat ban doc toi no —
    xem `components/PublishGate.tsx`.
  */
  const { trangThai: creator } = useTrangThaiCreator(Boolean(profile));

  const [novels, setNovels] = useState<Novel[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [audioByChapter, setAudioByChapter] = useState<Record<string, boolean>>({});
  /**
   * Chuong nao co audio CO THE khong con khop noi dung (M4). Giu o state rieng
   * vi cho nay con tu cap nhat ngay sau khi luu chuong hoac tao lai audio, chu
   * khong doi lan tai lai danh sach.
   */
  const [staleByChapter, setStaleByChapter] = useState<Record<string, boolean>>({});
  /** Dang luu thu tu chuong len backend (M3) — chan bam lien tuc. */
  const [savingOrder, setSavingOrder] = useState(false);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [novelTitle, setNovelTitle] = useState("");
  const [novelDesc, setNovelDesc] = useState("");
  const [novelTags, setNovelTags] = useState("");
  const [creatingNovel, setCreatingNovel] = useState(false);

  const [editingNovel, setEditingNovel] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editTags, setEditTags] = useState("");
  const [savingNovel, setSavingNovel] = useState(false);
  const [savingCover, setSavingCover] = useState(false);

  const [chapterTitle, setChapterTitle] = useState("");
  const [chapterText, setChapterText] = useState("");
  const [creatingChapter, setCreatingChapter] = useState(false);

  const [editingChapterId, setEditingChapterId] = useState("");
  const [chEditTitle, setChEditTitle] = useState("");
  const [chEditText, setChEditText] = useState("");
  const [savingChapter, setSavingChapter] = useState(false);

  const [voiceId, setVoiceId] = useState("");
  /*
    Job theo TUNG CHUONG, khong phai mot job toan cuc.

    Truoc day `/write` giu dung mot `job` trong state. Hai chuong cung xep
    hang thi cai sau de len cai truoc, va nguoi dung mat dau vet cua chuong
    dau — trong khi backend cho toi `MAX_ACTIVE_JOBS` job mot luc.

    `focusChapterId` chi quyet dinh khung "Tien trinh" o duoi dang noi ve
    chuong nao. No la chuyen TRINH BAY; `jobs` moi la trang thai that.
  */
  const {
    jobs,
    khoiPhuc: khoiPhucJob,
    theoDoi: theoDoiJob,
    quenChuong: quenJobCuaChuong,
    quenHet: quenHetJob,
  } = useJobTracker({
    onCompleted: (moi) => {
      toast.ok("Audio của chương đã sẵn sàng.");
      setAudioByChapter((current) => ({ ...current, [moi.chapter_id]: true }));
      // Vua tao lai xong thi audio khop noi dung hien tai -> tat canh bao
      setStaleByChapter((current) => ({ ...current, [moi.chapter_id]: false }));
    },
    onFailed: () => toast.error("Tạo audio thất bại."),
  });
  const [focusChapterId, setFocusChapterId] = useState("");
  const job = focusChapterId ? (jobs[focusChapterId] ?? null) : null;
  const [confirmPublish, setConfirmPublish] = useState<"publish" | "unpublish" | null>(
    null,
  );
  const [togglingPublish, setTogglingPublish] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete>(null);
  const [deleting, setDeleting] = useState(false);

  /* ---------------------------------------------------------------- nap */

  // Than effect KHONG duoc goi setState dong bo — xem `load` cua Audio Studio.
  const load = useCallback(() => {
    /*
      `listJobs()` la request THU BA, va no la cach khoi phuc job sau khi tai
      lai trang.

      MOT request cho TAT CA chuong, khong phai mot request moi chuong: duong
      `/api/chapters/{id}/jobs/latest` co ton tai va huu ich khi chi can hoi ve
      dung mot chuong, nhung goi no trong vong lap la N+1 —
      `tests/correctness-scale.test.mjs` dang khoa lai chinh cho do.

      KHO MOI LA NGUON SU THAT. Khong doc `job_id` tu localStorage: trinh duyet
      co the bi xoa du lieu, mo o may khac, hoac giu mot `job_id` da bi worker
      khac thay the sau khi lease chet.
    */
    Promise.all([api.listNovels(true), api.voices(), api.listJobs()])
      .then(([novelList, voiceList, jobList]) => {
        const mine = fanficOnly(novelList.novels);
        setNovels(mine);
        setVoices(voiceList.voices);
        setVoiceId((current) => current || defaultVoiceId(voiceList.voices));
        setSelectedId((current) => current || mine[0]?.novel_id || "");
        khoiPhucJob(jobList.jobs);
        setFocusChapterId((current) => current || dangChayDauTien(jobList.jobs));
      })
      .catch((cause) => setError(errorMessage(cause)))
      .finally(() => setLoading(false));
  }, [khoiPhucJob]);

  /** Nut "Thu lai" chay tu su kien nguoi dung. */
  const retryLoad = useCallback(() => {
    setLoading(true);
    setError("");
    load();
  }, [load]);

  useEffect(() => {
    if (sessionLoading || !profile) return;
    load();
  }, [sessionLoading, profile, load]);

  /*
    Chua dang nhap -> sang thang trang dang nhap, KEM noi can quay lai.

    "Viết truyện" la mot muc dieu huong chinh nen khach vang lai VAN thay va
    VAN bam duoc — no khong bi an di. Cai khac la sau khi dang nhap ho quay
    lai dung `/write` chu khong bi tha ve trang chu.

    `router.replace` chu khong phai `push`: nut Back phai dua nguoi dung ve
    trang truoc do, khong phai ve mot trang se lai day ho sang dang nhap.
  */
  useEffect(() => {
    if (sessionLoading || profile) return;
    router.replace(loginHref("/write"));
  }, [sessionLoading, profile, router]);

  const loadChapters = useCallback((novelId: string) => {
    if (!novelId) return;
    api
      .getNovel(novelId)
      .then((detail) => {
        setChapters(detail.chapters);
        // `has_audio` di kem san trong danh sach chuong. Van giu o state vi
        // cho nay con tu cap nhat khi mot job vua xong hoac chuong bi xoa.
        setAudioByChapter(
          Object.fromEntries(
            detail.chapters.map((c) => [c.chapter_id, Boolean(c.has_audio)]),
          ),
        );
        setStaleByChapter(
          Object.fromEntries(
            detail.chapters.map((c) => [c.chapter_id, Boolean(c.audio_outdated)]),
          ),
        );
      })
      .catch(() => {
        setChapters([]);
        setAudioByChapter({});
        setStaleByChapter({});
      });
  }, []);

  useEffect(() => {
    loadChapters(selectedId);
  }, [selectedId, loadChapters]);

  /*
    Vong theo doi nam o `useJobTracker` — dung MOT ban cho ca `/write` va
    `/studio`. Truoc day moi trang tu viet lay, va do la ly do `/studio` khong
    duoc huong cac ban va ve tien do cua trang nay.

    Hook theo doi MOI job dang chay, khong chi cai dang duoc nhin: backend cho
    toi `MAX_ACTIVE_JOBS` job mot luc.
  */

  /* ---------------------------------------------------------------- suy */

  const selected = useMemo(
    () => novels.find((n) => n.novel_id === selectedId) ?? null,
    [novels, selectedId],
  );
  const availableVoices = useMemo(() => usableVoices(voices), [voices]);
  // Hai muc, cung mot bo ban ghi. Xem `voiceSections`.
  const voiceGroups = useMemo(() => voiceSections(voices), [voices]);
  const published = selected?.state === "published";

  /* ------------------------------------------------------------- truyen */

  const createNovel = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!novelTitle.trim()) return;
      setCreatingNovel(true);
      try {
        const created = await api.createNovel(
          novelTitle.trim(),
          novelDesc.trim(),
          parseTags(novelTags),
        );
        setNovels((current) => [created.novel, ...current]);
        setSelectedId(created.novel.novel_id);
        setNovelTitle("");
        setNovelDesc("");
        setNovelTags("");
        toast.ok("Đã tạo truyện mới.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setCreatingNovel(false);
      }
    },
    [novelTitle, novelDesc, novelTags, toast],
  );

  const startEditNovel = useCallback(() => {
    if (!selected) return;
    setEditTitle(selected.title);
    setEditDesc(selected.description);
    setEditTags(selected.tags.join(", "));
    setEditingNovel(true);
  }, [selected]);

  const saveNovel = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!selected || !editTitle.trim()) return;
      setSavingNovel(true);
      try {
        const result = await api.updateNovel(selected.novel_id, {
          title: editTitle.trim(),
          description: editDesc.trim(),
          tags: parseTags(editTags),
        });
        setNovels((current) =>
          current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
        );
        setEditingNovel(false);
        toast.ok("Đã lưu thay đổi.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setSavingNovel(false);
      }
    },
    [selected, editTitle, editDesc, editTags, toast],
  );

  const togglePublish = useCallback(async () => {
    if (!selected || !confirmPublish) return;
    const wantPublish = confirmPublish === "publish";
    setTogglingPublish(true);
    try {
      const result = wantPublish
        ? await api.publishNovel(selected.novel_id)
        : await api.unpublishNovel(selected.novel_id);
      setNovels((current) =>
        current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
      );
      toast.ok(
        wantPublish
          ? "Đã xuất bản. Truyện hiện ra trong trang Khám phá."
          : "Đã gỡ xuất bản. Truyện trở lại bản nháp.",
      );
      setConfirmPublish(null);
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setTogglingPublish(false);
    }
  }, [selected, confirmPublish, toast]);

  /* --------------------------------------------------------------- bia */

  const chonAnhBia = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const tep = event.target.files?.[0];
      event.target.value = ""; // cho chon lai CUNG tep lan nua
      if (!tep || !selected) return;
      setSavingCover(true);
      try {
        const anh = await xuLyAnh(tep, MAX_COVER_EDGE);
        if (!anh) {
          toast.error("Không đọc được ảnh này.");
          return;
        }
        const result = await api.setNovelCover(selected.novel_id, {
          base64: anh.base64,
          mime: anh.mime,
          width: anh.width,
          height: anh.height,
        });
        URL.revokeObjectURL(anh.xemTruoc); // chi dung de xem truoc tam thoi
        setNovels((current) =>
          current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
        );
        toast.ok("Đã cập nhật ảnh bìa.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setSavingCover(false);
      }
    },
    [selected, toast],
  );

  const xoaAnhBia = useCallback(async () => {
    if (!selected) return;
    setSavingCover(true);
    try {
      const result = await api.removeNovelCover(selected.novel_id);
      setNovels((current) =>
        current.map((n) => (n.novel_id === result.novel.novel_id ? result.novel : n)),
      );
      toast.ok("Đã gỡ ảnh bìa.");
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setSavingCover(false);
    }
  }, [selected, toast]);

  /* ------------------------------------------------------------- chuong */

  const createChapter = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!selectedId || !chapterTitle.trim() || !chapterText.trim()) return;
      setCreatingChapter(true);
      try {
        const created = await api.createChapter(
          selectedId,
          chapterTitle.trim(),
          chapterText,
          chapters.length + 1,
        );
        setChapters((current) => [...current, created.chapter]);
        setChapterTitle("");
        setChapterText("");
        toast.ok("Đã thêm chương.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setCreatingChapter(false);
      }
    },
    [selectedId, chapterTitle, chapterText, chapters.length, toast],
  );

  const startEditChapter = useCallback(async (chapter: Chapter) => {
    setEditingChapterId(chapter.chapter_id);
    setChEditTitle(chapter.title);
    setChEditText("");
    try {
      const detail = await api.getChapter(chapter.chapter_id);
      setChEditText(detail.chapter.content ?? "");
    } catch {
      setChEditText("");
    }
  }, []);

  const saveChapter = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!editingChapterId || !chEditTitle.trim()) return;
      setSavingChapter(true);
      try {
        const result = await api.updateChapter(editingChapterId, {
          title: chEditTitle.trim(),
          content: chEditText,
        });
        setChapters((current) =>
          current.map((c) =>
            c.chapter_id === result.chapter.chapter_id ? result.chapter : c,
          ),
        );
        setEditingChapterId("");
        // M4: sua noi dung xong thi audio cu CO THE khong con khop. Danh dau
        // ngay, khong doi lan tai lai danh sach — de nguoi dung thay canh bao
        // dung luc ho vua bam Luu, khong phai mai sau moi biet.
        if (audioByChapter[editingChapterId]) {
          setStaleByChapter((current) => ({ ...current, [editingChapterId]: true }));
          toast.push(
            "info",
            "Đã lưu chương. Audio hiện tại được giữ nguyên nhưng có thể không còn khớp.",
          );
        } else {
          toast.ok("Đã lưu chương.");
        }
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setSavingChapter(false);
      }
    },
    [editingChapterId, chEditTitle, chEditText, audioByChapter, toast],
  );

  /* ------------------------------------------------------- M3: doi thu tu */

  /**
   * Doi cho mot chuong voi chuong lien ke, roi luu CA thu tu len backend.
   *
   * Dung nut len/xuong chu khong phai keo-tha: keo-tha bang HTML5 khong hoat
   * dong tren man hinh cam ung ma khong co polyfill, con tu viet bang pointer
   * event thi vua nhieu ma vua kho dung duoc bang ban phim. Nut len/xuong chay
   * y nhu nhau tren desktop, mobile va ban phim.
   *
   * Cap nhat giao dien truoc cho phan hoi nhanh, nhung neu backend tu choi thi
   * TRA LAI thu tu cu — khong de giao dien noi mot dieu ma kho noi dieu khac.
   */
  const moveChapter = useCallback(
    async (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (savingOrder || target < 0 || target >= chapters.length) return;

      const before = chapters;
      const next = [...chapters];
      [next[index], next[target]] = [next[target], next[index]];
      setChapters(next);
      setSavingOrder(true);
      try {
        const result = await api.reorderChapters(
          selectedId,
          next.map((c) => c.chapter_id),
        );
        setChapters(result.chapters);
      } catch (cause) {
        setChapters(before);
        toast.error(errorMessage(cause));
      } finally {
        setSavingOrder(false);
      }
    },
    [chapters, selectedId, savingOrder, toast],
  );

  const makeAudio = useCallback(
    async (chapterId: string) => {
      if (!voiceId) {
        toast.error("Chưa chọn giọng đọc.");
        return;
      }
      try {
        const result = await api.createJob(chapterId, voiceId);
        theoDoiJob(result.job);
        setFocusChapterId(chapterId);
        toast.push("info", result.reused ? "Dùng lại audio đã tạo." : "Đang tạo audio…");
      } catch (cause) {
        toast.error(errorMessage(cause));
      }
    },
    [voiceId, theoDoiJob, toast],
  );

  /* --------------------------------------------------------------- xoa */

  const doDelete = useCallback(async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setDeleting(true);
    try {
      if (target.kind === "novel") {
        const result = await api.deleteNovel(target.id);
        // Tinh danh sach con lai TRUOC roi moi dat trang thai. Ham cap nhat
        // cua `setState` phai THUAN KHIET — goi mot setState khac ben trong no
        // se bi React 19 chan, va khi do ca khoi nay dung giua chung: giao dien
        // khong doi, khong toast, dau kho backend da xoa xong.
        const left = novels.filter((n) => n.novel_id !== target.id);
        setNovels(left);
        setSelectedId(left[0]?.novel_id ?? "");
        setChapters([]);
        setAudioByChapter({});
        quenHetJob();
        setFocusChapterId("");
        toast.ok(
          `Đã xoá truyện cùng ${result.removed.chapters ?? 0} chương và ` +
            `${result.removed.objects} file audio.`,
        );
      } else {
        const result = await api.deleteChapter(target.id);
        setChapters((current) => current.filter((c) => c.chapter_id !== target.id));
        setAudioByChapter((current) => {
          const next = { ...current };
          delete next[target.id];
          return next;
        });
        quenJobCuaChuong(target.id);
        if (focusChapterId === target.id) setFocusChapterId("");
        if (editingChapterId === target.id) setEditingChapterId("");
        toast.ok(
          result.removed.objects > 0
            ? "Đã xoá chương và file audio của nó."
            : "Đã xoá chương.",
        );
      }
      setPendingDelete(null);
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDeleting(false);
    }
  }, [
    pendingDelete,
    novels,
    focusChapterId,
    editingChapterId,
    quenHetJob,
    quenJobCuaChuong,
    toast,
  ]);

  /* --------------------------------------------------------------- render */

  if (sessionLoading) {
    return (
      <div className="page">
        <Loading label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  }

  if (!profile) {
    /*
      Da dieu huong sang `/login?next=/write` o effect ben tren. Man hinh nay
      chi la thu nguoi dung thay trong khoanh khac chuyen trang.

      KHONG dung `EmptyState` kem nut "Đăng nhập" nhu truoc: sau khi dang nhap
      no dua nguoi dung ve trang chu, va ho phai tu tim duong quay lai day.
      "Viết truyện" nay la mot muc dieu huong chinh — bam vao no ma phai di hai
      chang moi toi noi thi no khong con giong mot khu vuc san pham.
    */
    return (
      <div className="page">
        <Loading label="Đang chuyển tới trang đăng nhập…" />
      </div>
    );
  }

  return (
    <div className="page" data-hero-theme="write">
      <PageHeader
        eyebrow="Khu vực tác giả"
        icon={<IconFeather />}
        motif={<MotifInkFlourish />}
        title="Viết và xuất bản"
        lead="Tạo truyện, thêm chương, tạo audio cho từng chương. Truyện nằm ở bản nháp cho tới khi bạn tự xuất bản."
        action={
          <>
            {/* Trang nay tao MOT chuong moi lan. Voi mot bo 50-500 chuong thi
                do la 50-500 lan bam nut, nen loi vao "nhap hang loat" phai nam
                ngay day chu khong an trong menu. */}
            <Link className="btn" href="/write/import">
              Nhập nhiều chương
            </Link>
            <Link className="btn" href="/fanfic">
              Xem trang khám phá
            </Link>
          </>
        }
      />

      {error ? (
        <ErrorState message={error} onRetry={retryLoad} />
      ) : loading ? (
        <SkeletonList count={4} />
      ) : (
        <div className="split-narrow page-lam-viec">
          {/* --------------------------------------------- cot trai: truyen */}
          <aside className="stack">
            <section className="card stack">
              <h2 className="section-title section-title-icon">
                <IconBook size={19} /> Truyện của tôi
              </h2>
              {novels.length === 0 ? (
                <p className="hint">Chưa có truyện nào. Tạo truyện đầu tiên bên dưới.</p>
              ) : (
                <div className="list">
                  {novels.map((novel) => (
                    // Mau va trang thai dang chon do CSS quyet dinh, khong con
                    // `style` inline: media query khong voi toi style inline,
                    // va ba dong mau lap lai o day la ba cho de lech.
                    <button
                      key={novel.novel_id}
                      type="button"
                      className="novel-pick"
                      aria-current={novel.novel_id === selectedId ? "true" : undefined}
                      onClick={() => setSelectedId(novel.novel_id)}
                    >
                      <strong className="truncate novel-pick-title">
                        {novel.title}
                      </strong>
                      <span
                        className={`badge ${novel.state === "published" ? "badge-ok" : ""}`}
                      >
                        {novel.state === "published" ? "Đã xuất bản" : "Bản nháp"}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <form className="card stack" onSubmit={createNovel}>
              <h2 className="section-title">Tạo truyện mới</h2>
              <div className="field">
                <label className="label" htmlFor="w-title">
                  Tiêu đề
                </label>
                <input
                  id="w-title"
                  className="input"
                  value={novelTitle}
                  onChange={(e) => setNovelTitle(e.target.value)}
                  maxLength={200}
                  required
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="w-desc">
                  Mô tả ngắn
                </label>
                <textarea
                  id="w-desc"
                  className="textarea textarea-short"
                  value={novelDesc}
                  onChange={(e) => setNovelDesc(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="w-tags">
                  Thẻ <span className="hint">(cách nhau bằng dấu phẩy)</span>
                </label>
                <input
                  id="w-tags"
                  className="input"
                  value={novelTags}
                  onChange={(e) => setNovelTags(e.target.value)}
                  placeholder="one piece, phiêu lưu"
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={creatingNovel || !novelTitle.trim()}
              >
                {creatingNovel ? <span className="spinner" aria-hidden="true" /> : null}
                Tạo truyện
              </button>
            </form>
          </aside>

          {/* -------------------------------------------- cot phai: chuong */}
          <section className="stack-5">
            {!selected ? (
              <EmptyState
                icon="✍️"
                title="Chọn hoặc tạo một truyện"
                hint="Sau khi có truyện, bạn thêm chương và tạo audio cho từng chương."
              />
            ) : (
              <>
                <section className="card stack">
                  {editingNovel ? (
                    <form className="stack" onSubmit={saveNovel}>
                      <h2 className="section-title">Sửa truyện</h2>
                      <div className="field">
                        <label className="label" htmlFor="w-edit-title">
                          Tiêu đề
                        </label>
                        <input
                          id="w-edit-title"
                          className="input"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          maxLength={200}
                          required
                        />
                      </div>
                      <div className="field">
                        <label className="label" htmlFor="w-edit-desc">
                          Mô tả
                        </label>
                        <textarea
                          id="w-edit-desc"
                          className="textarea textarea-short"
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                        />
                      </div>
                      <div className="field">
                        <label className="label" htmlFor="w-edit-tags">
                          Thẻ
                        </label>
                        <input
                          id="w-edit-tags"
                          className="input"
                          value={editTags}
                          onChange={(e) => setEditTags(e.target.value)}
                        />
                      </div>
                      <div className="row">
                        <button
                          type="submit"
                          className="btn btn-primary"
                          disabled={savingNovel || !editTitle.trim()}
                        >
                          {savingNovel ? (
                            <span className="spinner" aria-hidden="true" />
                          ) : null}
                          Lưu thay đổi
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => setEditingNovel(false)}
                          disabled={savingNovel}
                        >
                          Huỷ
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <div className="row-between">
                        <div className="row row-tight min0">
                          {/*
                            Bia + nut doi/go ngay canh tieu de — cho tu nhien
                            nhat de tim thay, vi day la khu vuc "day la truyen
                            cua toi" chu khong phai mot trang cai dat rieng.
                          */}
                          <label
                            className="min0"
                            style={{ cursor: savingCover ? "wait" : "pointer" }}
                            title="Đổi ảnh bìa"
                          >
                            <NovelCover
                              novelId={selected.novel_id}
                              title={selected.title}
                              coverUrl={selected.cover_url}
                              size="thumb"
                            />
                            <input
                              type="file"
                              accept="image/*"
                              hidden
                              disabled={savingCover}
                              onChange={chonAnhBia}
                            />
                          </label>
                          <div className="stack-2 min0">
                            <h2 className="section-title">{selected.title}</h2>
                            <span className="hint">
                              {chapters.length} chương ·{" "}
                              {published ? "đã xuất bản" : "bản nháp, chỉ mình bạn thấy"}
                            </span>
                            {selected.description ? (
                              <p className="hint clamp-2">{selected.description}</p>
                            ) : null}
                            {selected.cover_url ? (
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={xoaAnhBia}
                                disabled={savingCover}
                                style={{ alignSelf: "flex-start" }}
                              >
                                {savingCover ? (
                                  <span className="spinner" aria-hidden="true" />
                                ) : null}
                                Gỡ ảnh bìa
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="row row-tight">
                          <Link
                            className="btn btn-sm"
                            href={`/novels/${selected.novel_id}`}
                          >
                            Xem trang truyện
                          </Link>
                          <button type="button" className="btn btn-sm" onClick={startEditNovel}>
                            Sửa
                          </button>
                          {published ? (
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={() => setConfirmPublish("unpublish")}
                            >
                              Gỡ xuất bản
                            </button>
                          ) : (
                            /*
                              CONG CHAN XUAT BAN. Chi NUT nay doi theo trang thai
                              tac gia — tao truyen, sua truyen, them chuong, tao
                              audio deu khong di qua day. Ai cung viet duoc, chi
                              khong ai cung dua ra cong khai duoc.
                            */
                            <CongXuatBan
                              trangThai={creator}
                              coTheXuatBan={chapters.length > 0}
                              onXuatBan={() => setConfirmPublish("publish")}
                            />
                          )}
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            onClick={() =>
                              setPendingDelete({
                                kind: "novel",
                                id: selected.novel_id,
                                title: selected.title,
                              })
                            }
                          >
                            Xoá
                          </button>
                        </div>
                      </div>
                      {!published && chapters.length === 0 ? (
                        <Alert kind="info">
                          Thêm ít nhất một chương trước khi xuất bản.
                        </Alert>
                      ) : null}
                    </>
                  )}
                </section>

                <section className="card stack">
                  <div className="row-between">
                    <h2 className="section-title section-title-icon">
                      <IconLibrary size={19} /> Chương
                    </h2>
                    {availableVoices.length > 0 ? (
                      <div className="row row-tight">
                        <label className="hint" htmlFor="w-voice">
                          Giọng đọc
                        </label>
                        <select
                          id="w-voice"
                          className="select select-inline"
                          value={voiceId}
                          onChange={(e) => setVoiceId(e.target.value)}
                        >
                          {/* Hai mục, MỘT `<select>` — xem `voiceSections`. */}
                          <optgroup label={RECOMMENDED_LABEL}>
                            {voiceGroups.recommended.map((voice) => (
                              <option
                                key={`goi-y-${voice.voice_id}`}
                                value={voice.voice_id}
                              >
                                {voiceOptionLabel(voice)}
                              </option>
                            ))}
                          </optgroup>
                          <optgroup label={ALL_VOICES_LABEL}>
                            {voiceGroups.all.map((voice) => (
                              <option
                                key={voice.voice_id}
                                value={voice.voice_id}
                              >
                                {voiceOptionLabel(voice)}
                              </option>
                            ))}
                          </optgroup>
                        </select>
                      </div>
                    ) : null}
                  </div>

                  {chapters.length === 0 ? (
                    <p className="hint">Chưa có chương nào.</p>
                  ) : (
                    <div className="list">
                      {chapters.map((chapter, index) =>
                        editingChapterId === chapter.chapter_id ? (
                          <form
                            key={chapter.chapter_id}
                            className="card card-tight stack"
                            onSubmit={saveChapter}
                          >
                            <div className="field">
                              <label className="label" htmlFor="w-ch-edit-title">
                                Tiêu đề chương
                              </label>
                              <input
                                id="w-ch-edit-title"
                                className="input"
                                value={chEditTitle}
                                onChange={(e) => setChEditTitle(e.target.value)}
                                maxLength={200}
                                required
                              />
                            </div>
                            <div className="field">
                              <div className="label-row">
                                <label className="label" htmlFor="w-ch-edit-text">
                                  Nội dung
                                </label>
                                <span
                                  className="counter"
                                  style={
                                    chEditText.length > MAX_CHAPTER_CHARS
                                      ? { color: "var(--danger, #f66)" }
                                      : undefined
                                  }
                                >
                                  {formatNumber(chEditText.length)} /{" "}
                                  {formatNumber(MAX_CHAPTER_CHARS)} ký tự
                                </span>
                              </div>
                              <textarea
                                id="w-ch-edit-text"
                                className="textarea"
                                value={chEditText}
                                onChange={(e) => setChEditText(e.target.value)}
                              />
                            </div>
                            {audioByChapter[chapter.chapter_id] ? (
                              <Alert kind="warn">
                                <span>
                                  <strong>Chương này đã có audio.</strong> Lưu nội
                                  dung mới sẽ <strong>không</strong> tự tạo lại
                                  audio, và audio hiện tại{" "}
                                  <strong>không bị xoá</strong>. Bạn chọn: giữ
                                  audio đang có, hoặc bấm <em>Tạo lại audio</em>{" "}
                                  sau khi lưu để audio khớp nội dung mới.
                                </span>
                              </Alert>
                            ) : null}
                            <div className="row">
                              <button
                                type="submit"
                                className="btn btn-primary btn-sm"
                                disabled={savingChapter || !chEditTitle.trim()}
                              >
                                {savingChapter ? (
                                  <span className="spinner" aria-hidden="true" />
                                ) : null}
                                Lưu chương
                              </button>
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={() => setEditingChapterId("")}
                                disabled={savingChapter}
                              >
                                Huỷ
                              </button>
                            </div>
                          </form>
                        ) : (
                          <div key={chapter.chapter_id} className="list-item">
                            {/* M3: nut len/xuong. `.list-move` nam ngoai
                                `.list-actions` de o mobile no o lai canh so thu
                                tu — day la dieu khien vi tri, khong phai hanh
                                dong tren noi dung chuong. */}
                            <span className="list-move">
                              <button
                                type="button"
                                className="btn btn-sm btn-ghost btn-icon"
                                onClick={() => moveChapter(index, -1)}
                                disabled={index === 0 || savingOrder}
                                aria-label={`Di chuyển ${chapter.title} lên trên`}
                              >
                                <span aria-hidden="true">↑</span>
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-ghost btn-icon"
                                onClick={() => moveChapter(index, 1)}
                                disabled={index === chapters.length - 1 || savingOrder}
                                aria-label={`Di chuyển ${chapter.title} xuống dưới`}
                              >
                                <span aria-hidden="true">↓</span>
                              </button>
                            </span>
                            <span className="list-index" aria-hidden="true">
                              {index + 1}
                            </span>
                            <span className="stack-2 grow">
                              <Link
                                href={`/chapters/${chapter.chapter_id}`}
                                className="truncate list-title"
                              >
                                {chapter.title}
                              </Link>
                              <span className="hint">
                                {formatNumber(chapter.char_count)} ký tự
                              </span>
                            </span>
                            {/* Ca nhom nut nam trong `.list-actions` de o
                                mobile chung xuong dong rieng — de chung hang
                                thi tieu de chuong bi nen con "Chuo...". */}
                            <span className="list-actions">
                              {!audioByChapter[chapter.chapter_id] ? (
                                <button
                                  type="button"
                                  className="btn btn-sm"
                                  onClick={() => makeAudio(chapter.chapter_id)}
                                  disabled={
                                    !voiceId ||
                                    (job?.chapter_id === chapter.chapter_id &&
                                      (job.status === "pending" || job.status === "running"))
                                  }
                                >
                                  Tạo audio
                                </button>
                              ) : staleByChapter[chapter.chapter_id] ? (
                                // M4: audio con nguyen nhung co the khong khop.
                                // Badge noi ro, va nut ngay ben canh de tao lai.
                                <>
                                  <span className="badge badge-warn" title="Chương đã sửa sau khi tạo audio">
                                    <span aria-hidden="true">⚠</span> Audio cũ
                                  </span>
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-primary"
                                    onClick={() => makeAudio(chapter.chapter_id)}
                                    disabled={
                                      !voiceId ||
                                      (job?.chapter_id === chapter.chapter_id &&
                                        (job.status === "pending" || job.status === "running"))
                                    }
                                  >
                                    Tạo lại audio
                                  </button>
                                </>
                              ) : (
                                <span className="badge badge-ok">Có audio</span>
                              )}
                              <button
                                type="button"
                                className="btn btn-sm btn-ghost"
                                onClick={() => startEditChapter(chapter)}
                                aria-label={`Sửa chương ${chapter.title}`}
                              >
                                Sửa
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-danger"
                                onClick={() =>
                                  setPendingDelete({
                                    kind: "chapter",
                                    id: chapter.chapter_id,
                                    title: chapter.title,
                                    hasAudio: Boolean(audioByChapter[chapter.chapter_id]),
                                  })
                                }
                                aria-label={`Xoá chương ${chapter.title}`}
                              >
                                Xoá
                              </button>
                            </span>
                          </div>
                        ),
                      )}
                    </div>
                  )}

                  {job ? (
                    <JobProgress
                      job={job}
                      tieuDe={
                        <>
                          Tiến trình tạo audio
                          {focusChapterId
                            ? ` · ${
                                chapters.find((c) => c.chapter_id === focusChapterId)
                                  ?.title ?? "Chương"
                              }`
                            : ""}
                        </>
                      }
                      ghiChu={
                        <>
                          {job.status === "failed" ? (
                            <>
                              <Alert kind="error">
                                {job.error_message || "Không rõ nguyên nhân."}
                              </Alert>
                              <div className="row">
                                <button
                                  type="button"
                                  className="btn btn-sm btn-primary"
                                  onClick={() => makeAudio(job.chapter_id)}
                                >
                                  Thử lại
                                </button>
                              </div>
                            </>
                          ) : null}
                          {job.status === "completed" && focusChapterId ? (
                            <AudioPlayer
                              chapterId={focusChapterId}
                              title={
                                chapters.find((c) => c.chapter_id === focusChapterId)
                                  ?.title ?? "Chương"
                              }
                              compact
                            />
                          ) : null}
                        </>
                      }
                    />
                  ) : null}
                </section>

                <form className="card stack" onSubmit={createChapter}>
                  <h2 className="section-title section-title-icon">
                    <IconFeather size={19} /> Thêm chương
                  </h2>
                  <div className="field">
                    <label className="label" htmlFor="w-ch-title">
                      Tiêu đề chương
                    </label>
                    <input
                      id="w-ch-title"
                      className="input"
                      value={chapterTitle}
                      onChange={(e) => setChapterTitle(e.target.value)}
                      maxLength={200}
                      required
                    />
                  </div>
                  <div className="field">
                    <div className="label-row">
                      <label className="label" htmlFor="w-ch-text">
                        Nội dung
                      </label>
                      <span
                        className="counter"
                        style={
                          chapterText.length > MAX_CHAPTER_CHARS
                            ? { color: "var(--danger, #f66)" }
                            : undefined
                        }
                      >
                        {formatNumber(chapterText.length)} /{" "}
                        {formatNumber(MAX_CHAPTER_CHARS)} ký tự
                      </span>
                    </div>
                    <textarea
                      id="w-ch-text"
                      className="textarea textarea-tall"
                      value={chapterText}
                      onChange={(e) => setChapterText(e.target.value)}
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={creatingChapter || !chapterTitle.trim() || !chapterText.trim()}
                  >
                    {creatingChapter ? <span className="spinner" aria-hidden="true" /> : null}
                    Thêm chương
                  </button>
                </form>
              </>
            )}
          </section>
        </div>
      )}

      {/* ------------------------------------------------ xac nhan xuat ban */}
      <ConfirmDialog
        open={confirmPublish !== null}
        title={
          confirmPublish === "unpublish"
            ? "Gỡ xuất bản truyện này?"
            : "Xuất bản truyện này?"
        }
        body={
          confirmPublish === "unpublish" ? (
            <>
              <p>
                <strong>{selected?.title}</strong> sẽ biến mất khỏi trang Khám
                phá, và audio của các chương trở lại chế độ riêng tư.
              </p>
              <p className="mt-2">
                Nội dung không bị xoá — bạn xuất bản lại bất cứ lúc nào.
              </p>
            </>
          ) : (
            <>
              <p>
                Sau khi xuất bản, <strong>{selected?.title}</strong> sẽ hiện công
                khai trong trang Khám phá và bất kỳ ai cũng nghe được audio của
                các chương.
              </p>
              <p className="mt-2">Bạn có thể gỡ xuất bản sau.</p>
            </>
          )
        }
        confirmLabel={confirmPublish === "unpublish" ? "Gỡ xuất bản" : "Xuất bản"}
        busy={togglingPublish}
        onConfirm={togglePublish}
        onCancel={() => setConfirmPublish(null)}
      />

      {/* ----------------------------------------------------- xac nhan xoa */}
      <ConfirmDialog
        open={pendingDelete !== null}
        danger
        title={pendingDelete?.kind === "novel" ? "Xoá cả truyện này?" : "Xoá chương này?"}
        body={
          pendingDelete?.kind === "novel" ? (
            <>
              <p>
                <strong>{pendingDelete.title}</strong> sẽ bị xoá cùng{" "}
                <strong>toàn bộ {chapters.length} chương</strong> và mọi file
                audio đã tạo.
              </p>
              <p className="mt-2">
                Thao tác này <strong>không hoàn tác được</strong>.
              </p>
            </>
          ) : (
            <>
              <p>
                <strong>{pendingDelete?.title}</strong> sẽ bị xoá
                {pendingDelete?.hasAudio ? " cùng file audio của nó" : ""}.
              </p>
              <p className="mt-2">
                Thao tác này <strong>không hoàn tác được</strong>.
              </p>
            </>
          )
        }
        confirmLabel="Xoá vĩnh viễn"
        busy={deleting}
        onConfirm={doDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
