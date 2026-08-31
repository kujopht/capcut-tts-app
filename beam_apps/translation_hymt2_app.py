"""
Beam Cloud GPU endpoint — Tencent Hy-MT2 translation, via Beam's built-in
VLLM integration (real, documented at docs.beam.cloud/v2/examples/vllm).

Deployed TO Beam. Deploy ONE of these (pick by available VRAM/budget):

    beam deploy beam_apps/translation_hymt2_app.py:hymt2_1_8b
    beam deploy beam_apps/translation_hymt2_app.py:hymt2_7b

Both `tencent/Hy-MT2-1.8B` and `tencent/Hy-MT2-7B` are real, open-weight
models on HuggingFace (released 2026-05-21, 33-language translation,
confirmed via real research - not assumed). VLLM serves a STANDARD
OpenAI-compatible /v1/chat/completions API, which is EXACTLY what
server/translation_provider_registry.py's existing _OpenAICompatFreeProvider
(the "custom" TRANSLATION_BASE_URL/TRANSLATION_API_KEY/TRANSLATION_MODEL
provider, already proven working via a fixture test - see
docs/reports/self-hosted-translation-provider-2026-08-31.md) already
calls with ZERO new repo-side code. Once deployed, point the backend at
it:

    TRANSLATION_BASE_URL=<beam endpoint url>/v1
    TRANSLATION_API_KEY=<beam token used to call the endpoint>
    TRANSLATION_MODEL=tencent/Hy-MT2-7B   # or Hy-MT2-1.8B
    TRANSLATION_CUSTOM_PROVIDER_FREE=true  # self-hosted = compute cost, not
                                            # per-token cost - see that env
                                            # var's own docstring in
                                            # translation_provider_registry.py
"""
from beam.integrations import VLLM, VLLMArgs

HYMT2_1_8B = "tencent/Hy-MT2-1.8B"
HYMT2_7B = "tencent/Hy-MT2-7B"

hymt2_1_8b = VLLM(
    name="hymt2-1-8b",
    cpu=4,
    memory="16Gi",
    gpu="T4",  # smallest real GPU tier - 1.8B fits comfortably even at fp16
    gpu_count=1,
    workers=1,
    vllm_args=VLLMArgs(
        model=HYMT2_1_8B,
        served_model_name=[HYMT2_1_8B],
        trust_remote_code=True,
        max_model_len=8192,
        gpu_memory_utilization=0.90,
    ),
)

hymt2_7b = VLLM(
    name="hymt2-7b",
    cpu=8,
    memory="24Gi",
    gpu="A10G",  # 24GB - real headroom for a 7B model at fp16/bf16
    gpu_count=1,
    workers=1,
    vllm_args=VLLMArgs(
        model=HYMT2_7B,
        served_model_name=[HYMT2_7B],
        trust_remote_code=True,
        max_model_len=8192,
        gpu_memory_utilization=0.90,
    ),
)
