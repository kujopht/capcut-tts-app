"use client";

/**
 * Image Studio V1 — sinh anh minh hoa cho fanfic, ba che do doc lap:
 *
 *   Quick Free      — an danh, khong dang nhap, KHONG chon duoc model
 *                      ("Auto model" — xem canh bao duoi).
 *   Cộng đồng Free   — model CONG DONG Pollinations dang bao gia 0 pollen
 *                      NGAY BAY GIO (co the la danh sach RONG that su — xem
 *                      canh bao duoi). Van can dang nhap: sinh anh van goi
 *                      Unified API co xac thuc server-side (KHAC Quick Free).
 *   Fanfic Credits   — dang nhap, tru vi noi bo, chon model/chat luong.
 *   My Pollinations  — dang nhap + ket noi Pollinations ca nhan (BYOP),
 *                      dung Pollen cua chinh nguoi dung, KHONG cham vi.
 *
 * QUAN TRONG: Quick Free KHONG BAO GIO hien mot ten model rieng le (vd
 * "Free Flux"). Cuoc do tham `chore/pollinations-anonymous-probe` da chung
 * minh endpoint an danh bo qua/chuan hoa tham so model — hien "Free Flux"
 * se la mot loi quang cao sai. Nhan hien thi CO DINH la "Quick Free"/"Auto
 * model", dung theo dung nhan backend tra ve.
 *
 * QUAN TRONG #2: "Cộng đồng Free" (gia 0 pollen do Pollinations cong bo)
 * KHAC HOAN TOAN "Quick Free" (an danh, khong biet model) — xem ADDENDUM
 * "FREE POLLINATIONS COMMUNITY IMAGE MODELS". Danh sach nay co the RONG
 * THAT SU (da xac minh 2026-08-15: chua model anh nao dang gia 0) — day la
 * trang thai HOP LE, khong phai loi, va KHONG duoc tu dong chuyen sang
 * Fanfic Credits khi rong/khi mot model bi ru khoi danh sach.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  imageStudio,
  type CommunityFreeImageModel,
  type ImageGenerationResult,
  type ImageModelInfo,
  type SavedImageEntry,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import {
  Alert,
  EmptyState,
  PageHeader,
  SkeletonList,
  formatDate,
} from "@/components/ui";
import { IconSparkles, IconHistory, IconKey } from "@/components/Icons";
import { MotifInkBloom } from "@/components/Ornaments";

type Mode = "quick_free" | "community_free" | "shared_premium" | "byop";

const ASPECT_RATIOS = ["1:1", "16:9", "9:16", "3:4", "4:3"] as const;

/** Goi y phong cach cho fanfic — CHI la mot doan them vao prompt, KHONG bat
    buoc chon, khong khoa nguoi dung vao mot model/che do nao. */
const PRESETS: { key: string; label: string; hint: string }[] = [
  { key: "fantasy", label: "Fantasy", hint: "fantasy art style, epic, detailed" },
  { key: "anime", label: "Anime", hint: "anime style, vibrant colors, clean lineart" },
  { key: "realistic", label: "Realistic", hint: "photorealistic, cinematic lighting" },
  { key: "cover", label: "Bìa truyện", hint: "novel cover art, dramatic composition, title space" },
  { key: "portrait", label: "Chân dung nhân vật", hint: "character portrait, detailed face, upper body" },
  { key: "scene", label: "Minh hoạ cảnh", hint: "scene illustration, wide shot, atmospheric" },
];

function microToCredit(micro: number): string {
  return (micro / 100).toFixed(2);
}

function resultDataUrl(result: ImageGenerationResult): string {
  return `data:${result.content_type};base64,${result.image_base64}`;
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `imggen-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ImageStudioPage() {
  const { profile, loading: sessionLoading } = useSession();
  const toast = useToast();

  const [mode, setMode] = useState<Mode>("quick_free");
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<string>("1:1");
  const [model, setModel] = useState("");
  const [quality, setQuality] = useState("standard");

  const [models, setModels] = useState<ImageModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [sharedAvailable, setSharedAvailable] = useState(false);

  const [walletMicro, setWalletMicro] = useState<number | null>(null);
  const [estimateMicro, setEstimateMicro] = useState<number | null>(null);

  const [byopConnected, setByopConnected] = useState(false);
  const [byopChecking, setByopChecking] = useState(true);

  const [communityModels, setCommunityModels] = useState<CommunityFreeImageModel[]>([]);
  const [communityAvailable, setCommunityAvailable] = useState(true);
  const [communityError, setCommunityError] = useState("");
  const [communityLoading, setCommunityLoading] = useState(false);
  const [communityModel, setCommunityModel] = useState("");

  const [result, setResult] = useState<ImageGenerationResult | null>(null);
  const [lastMode, setLastMode] = useState<Mode>("quick_free");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [library, setLibrary] = useState<SavedImageEntry[] | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const idemRef = useRef<string>(newIdempotencyKey());

  // ------------------------------------------------------------- nap du lieu

  useEffect(() => {
    imageStudio
      .imageModels()
      .then((res) => {
        setModels(res.models);
        setSharedAvailable(res.shared_premium_available);
        setModel((current) => current || res.models[0]?.model_id || "");
      })
      .catch((cause) => toast.error(errorMessage(cause)))
      .finally(() => setModelsLoading(false));
  }, [toast]);

  const refreshWallet = useCallback(() => {
    if (!profile) return;
    imageStudio.imageWallet().then((w) => setWalletMicro(w.available_micro)).catch(() => {});
  }, [profile]);

  const refreshByopStatus = useCallback(() => {
    if (!profile) return;
    // KHONG dat `setByopChecking(true)` o day: goi truc tiep tu than effect
    // se bi `react-hooks/set-state-in-effect` cham (setState dong bo trong
    // effect) — chi setState ben trong .then()/.catch()/.finally().
    imageStudio
      .imageByopStatus()
      .then((s) => setByopConnected(s.connected))
      .catch(() => setByopConnected(false))
      .finally(() => setByopChecking(false));
  }, [profile]);

  const refreshCommunityFree = useCallback(() => {
    // KHONG goi `setCommunityLoading(true)` truc tiep o day (setState dong
    // bo trong than effect, khi ham nay duoc goi truc tiep tu effect ben
    // duoi) — hoan lai mot nhip qua Promise, cung tinh than voi
    // `estimateMicro`/`doi()` o tren.
    Promise.resolve().then(() => setCommunityLoading(true));
    imageStudio
      .imageCommunityFreeModels()
      .then((r) => {
        setCommunityAvailable(r.available);
        setCommunityError(r.error);
        setCommunityModels(r.models);
        setCommunityModel((current) => current || r.models[0]?.model_id || "");
      })
      .catch((cause) => {
        setCommunityAvailable(false);
        setCommunityError(errorMessage(cause));
      })
      .finally(() => setCommunityLoading(false));
  }, []);

  useEffect(() => {
    if (mode === "shared_premium") refreshWallet();
    if (mode === "byop") refreshByopStatus();
    if (mode === "community_free") refreshCommunityFree();
  }, [mode, refreshWallet, refreshByopStatus, refreshCommunityFree]);

  // Uoc tinh chi phi — chi cho Fanfic Credits, cap nhat khi doi model/chat luong.
  useEffect(() => {
    if (mode !== "shared_premium" || !model || !profile) {
      // KHONG goi `setEstimateMicro(null)` truc tiep o day (setState dong bo
      // trong than effect) — hoan lai mot nhip qua Promise de nam ngoai
      // luong dong bo cua effect, cung tinh than voi `doi()` o
      // `app/auth/callback/page.tsx`.
      let huy = false;
      Promise.resolve().then(() => {
        if (!huy) setEstimateMicro(null);
      });
      return () => {
        huy = true;
      };
    }
    let huy = false;
    imageStudio
      .imageSharedPremiumEstimate(model, quality)
      .then((r) => {
        if (!huy) setEstimateMicro(r.estimated_credit_micro);
      })
      .catch(() => {
        if (!huy) setEstimateMicro(null);
      });
    return () => {
      huy = true;
    };
  }, [mode, model, quality, profile]);

  const modelInfo = useMemo(
    () => models.find((m) => m.model_id === model),
    [models, model],
  );

  const applyPreset = useCallback((hint: string) => {
    setPrompt((current) => (current.trim() ? `${current.trim()}, ${hint}` : hint));
  }, []);

  // -------------------------------------------------------------- BYOP connect

  const connectByop = useCallback(async () => {
    try {
      const { authorize_url } = await imageStudio.imageByopConnect();
      window.location.href = authorize_url;
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  }, [toast]);

  const disconnectByop = useCallback(async () => {
    try {
      await imageStudio.imageByopDisconnect();
      setByopConnected(false);
      toast.push("info", "Đã ngắt kết nối Pollinations cá nhân.");
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  }, [toast]);

  // ------------------------------------------------------------------- sinh anh

  const canGenerate =
    prompt.trim().length > 0 &&
    !generating &&
    (mode !== "shared_premium" || Boolean(model)) &&
    (mode !== "byop" || (byopConnected && Boolean(model))) &&
    (mode !== "community_free" || (communityAvailable && Boolean(communityModel)));

  const generate = useCallback(async () => {
    setError("");
    setGenerating(true);
    setResult(null);
    const controller = new AbortController();
    abortRef.current = controller;
    idemRef.current = newIdempotencyKey();
    try {
      let ket_qua: ImageGenerationResult;
      if (mode === "quick_free") {
        ket_qua = await imageStudio.imageQuickFree(prompt.trim(), aspectRatio, controller.signal);
      } else if (mode === "community_free") {
        ket_qua = await imageStudio.imageCommunityFree(
          {
            prompt: prompt.trim(), negativePrompt: negativePrompt.trim(),
            model: communityModel, aspectRatio, quality,
            idempotencyKey: idemRef.current,
          },
          controller.signal,
        );
      } else if (mode === "shared_premium") {
        ket_qua = await imageStudio.imageSharedPremium(
          {
            prompt: prompt.trim(), negativePrompt: negativePrompt.trim(),
            model, aspectRatio, quality, idempotencyKey: idemRef.current,
          },
          controller.signal,
        );
        refreshWallet();
      } else {
        ket_qua = await imageStudio.imageByop(
          { prompt: prompt.trim(), negativePrompt: negativePrompt.trim(), model, aspectRatio, quality },
          controller.signal,
        );
      }
      setResult(ket_qua);
      setLastMode(mode);
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") {
        toast.push("info", "Đã huỷ.");
      } else if (mode === "community_free" && cause instanceof ApiError && cause.status === 409) {
        // ADDENDUM: model bi ru khoi danh sach mien phi giua chung — bao ro
        // rang, KHONG tu chuyen sang Fanfic Credits, va lam moi danh sach.
        setError(errorMessage(cause));
        refreshCommunityFree();
      } else {
        setError(errorMessage(cause));
      }
    } finally {
      setGenerating(false);
      abortRef.current = null;
    }
  }, [
    mode, prompt, negativePrompt, aspectRatio, model, quality, communityModel,
    refreshWallet, refreshCommunityFree, toast,
  ]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retry = useCallback(() => {
    void generate();
  }, [generate]);

  const download = useCallback(() => {
    if (!result) return;
    const a = document.createElement("a");
    a.href = resultDataUrl(result);
    a.download = `image-studio-${Date.now()}.jpg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, [result]);

  const save = useCallback(async () => {
    if (!result) return;
    setSaving(true);
    try {
      await imageStudio.imageLibrarySave({
        generationId: result.generation_id ?? "",
        prompt: prompt.trim(), negativePrompt: negativePrompt.trim(),
        model: mode === "quick_free" ? "" : mode === "community_free" ? communityModel : model,
        mode: lastMode, aspectRatio, imageBase64: result.image_base64,
      });
      toast.ok("Đã lưu vào thư viện.");
      setLibrary(null); // buoc tai lai lan sau mo tab thu vien
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  }, [result, prompt, negativePrompt, model, communityModel, mode, lastMode, aspectRatio, toast]);

  const loadLibrary = useCallback(() => {
    imageStudio.imageLibraryList().then((r) => setLibrary(r.images)).catch(() => setLibrary([]));
  }, []);

  // --------------------------------------------------------------------- render

  if (sessionLoading) {
    return (
      <div className="page" data-hero-theme="image-studio">
        <PageHeader
          eyebrow="Image Studio"
          icon={<IconSparkles />}
          motif={<MotifInkBloom />}
          title="Tạo ảnh minh hoạ cho fanfic"
          lead="Đang kiểm tra phiên đăng nhập…"
        />
      </div>
    );
  }

  return (
    // Themed Page Hero V1 — "Creation Bloom": tim dam + cyan + hong anh dao
    // chon loc.
    <div className="page" data-hero-theme="image-studio">
      <PageHeader
        eyebrow="Image Studio"
        icon={<IconSparkles />}
        motif={<MotifInkBloom />}
        title="Tạo ảnh minh hoạ cho fanfic"
        lead="Quick Free miễn phí không cần đăng nhập. Fanfic Credits và My Pollinations cần đăng nhập."
      />

      <div className="split page-lam-viec">
        <section className="stack-5">
          {/* --------------------------------------------------- chon che do */}
          <div className="seg seg-wrap" role="tablist" aria-label="Chế độ tạo ảnh">
            <button
              type="button" className="seg-item" role="tab"
              aria-selected={mode === "quick_free"}
              onClick={() => setMode("quick_free")}
            >
              Quick Free
            </button>
            <button
              type="button" className="seg-item" role="tab"
              aria-selected={mode === "community_free"}
              onClick={() => setMode("community_free")}
            >
              Cộng đồng Free
            </button>
            <button
              type="button" className="seg-item" role="tab"
              aria-selected={mode === "shared_premium"}
              onClick={() => setMode("shared_premium")}
            >
              Fanfic Credits
            </button>
            <button
              type="button" className="seg-item" role="tab"
              aria-selected={mode === "byop"}
              onClick={() => setMode("byop")}
            >
              My Pollinations
            </button>
          </div>

          {mode === "quick_free" ? (
            <Alert kind="info">
              Miễn phí, không cần đăng nhập. Hệ thống tự chọn model phía nhà
              cung cấp (&quot;Auto model&quot;) — bạn không chọn được model cụ thể ở
              chế độ này.
            </Alert>
          ) : null}

          {mode === "community_free" && !profile ? (
            <Alert kind="warn">Cần đăng nhập để dùng Cộng đồng Free.</Alert>
          ) : null}
          {mode === "community_free" && profile && communityLoading ? (
            <Alert kind="info">Đang kiểm tra model cộng đồng đang miễn phí…</Alert>
          ) : null}
          {mode === "community_free" && profile && !communityLoading && !communityAvailable ? (
            <Alert kind="warn">
              Không lấy được danh sách model cộng đồng lúc này
              {communityError ? `: ${communityError}` : "."} Quick Free và
              Fanfic Credits vẫn dùng được — vui lòng thử lại sau.
            </Alert>
          ) : null}
          {mode === "community_free" && profile && !communityLoading
            && communityAvailable && communityModels.length === 0 ? (
            <Alert kind="info">
              Hiện chưa có model cộng đồng nào đang được Pollinations công bố
              giá 0 — danh sách này kiểm tra định kỳ và sẽ tự xuất hiện ngay
              khi có model đủ điều kiện. Quick Free và Fanfic Credits vẫn
              dùng được trong lúc chờ.
            </Alert>
          ) : null}

          {mode === "shared_premium" && !profile ? (
            <Alert kind="warn">Cần đăng nhập để dùng Fanfic Credits.</Alert>
          ) : null}
          {mode === "shared_premium" && profile && !sharedAvailable ? (
            <Alert kind="warn">
              Fanfic Credits hiện chưa mở — máy chủ chưa cấu hình hoặc đã tạm
              khoá. Quick Free và My Pollinations vẫn dùng được.
            </Alert>
          ) : null}

          {mode === "byop" && !profile ? (
            <Alert kind="warn">Cần đăng nhập để kết nối Pollinations cá nhân.</Alert>
          ) : null}
          {mode === "byop" && profile && !byopChecking && !byopConnected ? (
            <div className="card stack-2">
              <p className="hint">
                Kết nối tài khoản Pollinations của riêng bạn — ảnh sẽ dùng
                Pollen của bạn, không trừ Fanfic Credits.
              </p>
              <button type="button" className="btn btn-primary" onClick={connectByop}>
                <IconKey /> Kết nối Pollinations
              </button>
            </div>
          ) : null}
          {mode === "byop" && byopConnected ? (
            <div className="row" style={{ justifyContent: "space-between" }}>
              <Alert kind="ok">Đã kết nối Pollinations cá nhân.</Alert>
              <button type="button" className="btn btn-ghost btn-sm" onClick={disconnectByop}>
                Ngắt kết nối
              </button>
            </div>
          ) : null}

          {/* ---------------------------------------------------------- form */}
          <div className="card stack">
            <div className="field">
              <label className="label" htmlFor="img-prompt">Mô tả ảnh</label>
              <textarea
                id="img-prompt" className="textarea textarea-tall"
                value={prompt} onChange={(e) => setPrompt(e.target.value)}
                placeholder="Ví dụ: một hiệp sĩ đứng trước lâu đài cổ lúc hoàng hôn…"
                maxLength={2000}
              />
            </div>

            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              {PRESETS.map((p) => (
                <button
                  key={p.key} type="button" className="btn btn-sm btn-ghost"
                  onClick={() => applyPreset(p.hint)}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {mode !== "quick_free" ? (
              <div className="field">
                <label className="label" htmlFor="img-negative">
                  Mô tả cần tránh <span className="hint">(tuỳ chọn)</span>
                </label>
                <input
                  id="img-negative" className="input" value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  placeholder="Ví dụ: mờ, biến dạng, chữ ký"
                  maxLength={1000}
                />
              </div>
            ) : null}

            <div className="field">
              <span className="label" id="img-ratio-label">Tỷ lệ khung hình</span>
              <div className="seg seg-wrap" role="group" aria-labelledby="img-ratio-label">
                {ASPECT_RATIOS.map((ar) => (
                  <button
                    key={ar} type="button" className="seg-item"
                    aria-pressed={aspectRatio === ar}
                    onClick={() => setAspectRatio(ar)}
                  >
                    {ar}
                  </button>
                ))}
              </div>
            </div>

            {mode === "shared_premium" || mode === "byop" ? (
              <div className="grid-2">
                <div className="field">
                  <label className="label" htmlFor="img-model">Model</label>
                  {modelsLoading ? (
                    <div className="sk" style={{ height: 42 }} aria-hidden="true" />
                  ) : (
                    <select
                      id="img-model" className="select" value={model}
                      onChange={(e) => setModel(e.target.value)}
                    >
                      {models.map((m) => (
                        <option key={m.model_id} value={m.model_id}>
                          {m.display_name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                {modelInfo && modelInfo.quality_levels.length > 1 ? (
                  <div className="field">
                    <label className="label" htmlFor="img-quality">Chất lượng</label>
                    <select
                      id="img-quality" className="select" value={quality}
                      onChange={(e) => setQuality(e.target.value)}
                    >
                      {modelInfo.quality_levels.map((q) => (
                        <option key={q} value={q}>{q}</option>
                      ))}
                    </select>
                  </div>
                ) : null}
              </div>
            ) : null}

            {mode === "community_free" && communityModels.length > 0 ? (
              <div className="field">
                <label className="label" htmlFor="img-community-model">
                  Model cộng đồng (miễn phí)
                </label>
                <select
                  id="img-community-model" className="select" value={communityModel}
                  onChange={(e) => setCommunityModel(e.target.value)}
                >
                  {communityModels.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.display_name}
                      {m.provider_badge ? ` · ${m.provider_badge}` : ""}
                    </option>
                  ))}
                </select>
                {(() => {
                  const chon = communityModels.find((m) => m.model_id === communityModel);
                  if (!chon) return null;
                  return (
                    <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                      <span className="badge badge-ok">Free / 0 Pollen</span>
                      {chon.provider_badge ? (
                        <span className="badge">{chon.provider_badge}</span>
                      ) : (
                        <span className="badge">Chính thức</span>
                      )}
                      {chon.alpha_hint ? <span className="badge badge-warn">Alpha</span> : null}
                      {typeof chon.per_user_rpm === "number" ? (
                        <span className="hint">Giới hạn: {chon.per_user_rpm} yêu cầu/phút</span>
                      ) : null}
                      {chon.alpha_hint ? <span className="hint">{chon.alpha_hint}</span> : null}
                    </div>
                  );
                })()}
              </div>
            ) : null}

            {mode === "shared_premium" && profile ? (
              <div className="hint">
                Số dư: {walletMicro !== null ? microToCredit(walletMicro) : "…"} Fanfic Credit
                {estimateMicro !== null ? (
                  <> — Ước tính lần này: {microToCredit(estimateMicro)} Fanfic Credit</>
                ) : null}
              </div>
            ) : null}

            {error ? <Alert kind="error">{error}</Alert> : null}

            <div className="row">
              <button
                type="button" className="btn btn-primary btn-lg"
                disabled={!canGenerate} onClick={() => void generate()}
              >
                {generating ? <span className="spinner" aria-hidden="true" /> : null}
                {generating ? "Đang tạo ảnh…" : "Tạo ảnh"}
              </button>
              {generating ? (
                <button type="button" className="btn btn-ghost" onClick={cancel}>
                  Huỷ
                </button>
              ) : null}
            </div>
          </div>

          {/* -------------------------------------------------------- ket qua */}
          {result ? (
            <section className="card stack-2" aria-labelledby="img-result-title">
              <h2 className="section-title" id="img-result-title">Kết quả</h2>
              <img
                src={resultDataUrl(result)} alt={prompt.trim() || "Ảnh vừa tạo"}
                style={{ maxWidth: "100%", borderRadius: 12 }}
              />
              <div className="row" style={{ flexWrap: "wrap" }}>
                <button type="button" className="btn" onClick={retry} disabled={generating}>
                  Thử lại
                </button>
                <button type="button" className="btn" onClick={download}>
                  Tải xuống
                </button>
                {profile ? (
                  <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={saving}>
                    {saving ? "Đang lưu…" : "Lưu vào thư viện"}
                  </button>
                ) : null}
              </div>
            </section>
          ) : null}
        </section>

        {/* ---------------------------------------------------------- thu vien */}
        <aside className="stack sticky-side">
          <section className="card stack">
            <h2 className="section-title section-title-icon">
              <IconHistory size={20} /> Thư viện ảnh đã lưu
            </h2>
            {!profile ? (
              <p className="hint">Đăng nhập để xem thư viện ảnh đã lưu.</p>
            ) : library === null ? (
              <button type="button" className="btn btn-sm" onClick={loadLibrary}>
                Tải thư viện
              </button>
            ) : library.length === 0 ? (
              <EmptyState icon="🖼" title="Chưa có ảnh nào đã lưu" hint="Ảnh bạn lưu sẽ hiện ở đây." />
            ) : (
              <div className="list">
                {library.map((img) => (
                  <div key={img.image_id} className="hist-item">
                    <img
                      src={img.url} alt={img.prompt || "Ảnh đã lưu"}
                      style={{ width: "100%", borderRadius: 8 }}
                    />
                    <span className="hint">{formatDate(img.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
