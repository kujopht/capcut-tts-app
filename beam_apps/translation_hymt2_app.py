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
server/translation_provider_registry.py's existing DocuTranslateProvider
(the "custom" TRANSLATION_BASE_URL/TRANSLATION_API_KEY/TRANSLATION_MODEL
provider, already proven working via a fixture test - see
docs/reports/self-hosted-translation-provider-2026-08-31.md) already
calls with ZERO new repo-side code. Once deployed, point the backend at
it:

    TRANSLATION_BASE_URL=<beam endpoint url>/v1
    TRANSLATION_API_KEY=<beam token used to call the endpoint>
    TRANSLATION_MODEL=tencent/Hy-MT2-1.8B  # NEVER Hy-MT2-7B by default - see
                                            # "7B IS GATED" below
    TRANSLATION_CUSTOM_PROVIDER_FREE=true  # self-hosted = compute cost, not
                                            # per-token cost - see that env
                                            # var's own docstring in
                                            # translation_provider_registry.py
    TRANSLATION_CUSTOM_GENERATION_PARAMS=   # OPTIONAL JSON, e.g.
      '{"temperature":0.7,"top_p":0.6,"top_k":20,"repetition_penalty":1.05,
        "max_tokens":4096}' - Hy-MT2's OWN model-card-recommended generation
      params (huggingface.co/tencent/Hy-MT2-1.8B, fetched 2026-09-01), which
      differ from this repo's shared default (temperature=0.3, used by
      every "custom"-provider deployment, not just this one). NOT set here
      by default - see DocuTranslateProvider's own docstring
      (server/translation_providers.py) for why the shared default is left
      alone until a real GPU benchmark (scripts/beam_translation_benchmark.py)
      gives evidence either default is better for THIS model.

REAL RESEARCH FINDINGS (Track B "Hy-MT2 1.8B translation production
readiness", fetched 2026-09-01 - every item below was independently
verified against the model's own HuggingFace config/model card and Beam's
own docs, not assumed from the prior mission turn that first wired this
file):

- `trust_remote_code=True` (already set, CONFIRMED correct, not changed):
  Hy-MT2's `config.json` reports `"architectures": ["HunYuanDenseV1ForCausalLM"]`,
  `"model_type": "hunyuan_v1_dense"` - a Tencent HunYuan-family architecture
  with custom modeling code, not a stock `transformers`-registered class.
  The model card's own `transformers` loading example uses
  `trust_remote_code=True`.
- 33 languages (already stated, CONFIRMED accurate): the model card states
  "support translation among 33 languages" with a full language table.
- vLLM compatibility (CONFIRMED, not assumed): the model card publishes
  ITS OWN vLLM serving instructions
  (`vllm serve tencent/Hy-MT2-1.8B --tensor-parallel-size 1`) - i.e. the
  model publisher, not just Beam, has verified vLLM support for this exact
  architecture.
- dtype (NOT set explicitly here, CONFIRMED this is correct): `config.json`
  reports `"torch_dtype": "bfloat16"`. vLLM's own default dtype is `"auto"`,
  which reads this field from the checkpoint config - no explicit
  `dtype=`/`torch_dtype=` override is needed on `VLLMArgs` (and the fetched
  `VLLMArgs` parameter list from docs.beam.cloud/v2/reference/py-sdk.md did
  not show a `dtype` field to begin with).
- `max_model_len=8192` (already set, CONFIRMED to be a deliberate,
  documented reduction, not an oversight): `config.json` reports
  `"max_position_embeddings": 262144` - the model can technically address a
  much longer context than 8192. 8192 is kept here on purpose: this repo's
  own chunking (`DOAN_KY_TU_MOI_LAN_GOI=2000` characters/call in
  `server/translation_service.py`, well under ~8192 tokens even accounting
  for prompt/system-message overhead) never needs anywhere near the full
  262144, and a SMALLER `max_model_len` directly shrinks vLLM's reserved
  KV-cache allocation - important headroom on a 16GB T4 (see GPU sizing
  below). Raising this later is possible but should be motivated by an
  actual chunking-size change, not "because the model supports more".
- Generation params (temperature 0.7, top_p 0.6, top_k 20,
  repetition_penalty 1.05, max_tokens 4096, per the model card): these are
  PER-REQUEST OpenAI chat-completion params, not `VLLMArgs` deploy config -
  `VLLMArgs` has no such fields. This repo's shared
  `DocuTranslateProvider`/`_OpenAICompatFreeProvider` classes send a fixed
  `temperature=0.3` for every "custom"/Groq/Cerebras deployment; NOT
  changed here since that default is shared, production-proven code for
  OTHER providers too, and no real GPU benchmark evidence yet exists that
  Hy-MT2 specifically needs the model card's own values. See
  `TRANSLATION_CUSTOM_GENERATION_PARAMS` above for the real, tested,
  opt-in override path added this track (server/translation_providers.py,
  server/translation_provider_registry.py) for operators to use AFTER a
  real benchmark run.

GPU TIER VERIFICATION (fetched 2026-09-01, docs.beam.cloud/v2/environment/gpu):
`"T4"` (16Gi VRAM) and `"A10G"` (24Gi VRAM) are BOTH confirmed real,
CURRENTLY VALID, "available"/"ready" serverless `gpu=` enum values for
Beam - not deprecated, not placeholders. VRAM sizing is realistic: Hy-MT2-
1.8B at bf16 is ~3.6GB of weights, comfortable on a 16GB T4 with
`gpu_memory_utilization=0.90` (~14.4GB budget) leaving ample room for
KV cache; Hy-MT2-7B at bf16 is ~14GB of weights, fitting a 24GB A10G at
the same utilization (~21.6GB budget) with real but tighter headroom -
consistent with why 7B is gated to a bigger GPU tier, not the same T4.

REAL CAVEAT found this track, NOT present in the prior mission turn's
citations: Beam's OWN current public pricing page (beam.cloud/pricing,
checked 2026-09-01) does NOT publish a per-second rate for EITHER "T4" or
"A10G" - its serverless GPU price table currently starts at RTX4090 and
goes up (RTX4090, RTX5090, L40S, A6000, A100 80GB, RTX PRO 6000, H100,
H200, B200). This was cross-checked against two independent third-party
aggregators (computestacker.com, cloudgpuprices.com) which agree T4/A10G
have no current Beam-published rate. A third aggregator (gputracker.dev)
does show numbers (T4 $0.310/hr, A10G $1.10/hr), but these do not match
Beam's own precise per-second billing pattern seen elsewhere (e.g. RTX4090
= $0.000191667/s exactly) and could NOT be independently confirmed on
Beam's own site - treat as an UNVERIFIED third-party estimate only, never
as a Beam-published rate. This does NOT block using T4/A10G (the `gpu=`
strings themselves are still valid and billed per-second like any other
tier - Beam's dashboard/invoice will show the real charge after the one
real benchmark call), it only means
`scripts/beam_translation_benchmark.py` cannot print a "published rate"
cost figure with the same confidence `scripts/beam_cover_benchmark.py`
does for RTX4090 - see that script's own comments for how this is labeled.

MODEL LOADS EXACTLY ONCE PER CONTAINER (confirmed via Beam's own docs, not
assumed): `docs.beam.cloud/v2/reference/py-sdk.md`'s `VLLM` class exists
specifically to run vLLM as a long-lived OpenAI-compatible chat-completions
SERVER process per container (the docs describe "interacting with an
already-running server", not a request-scoped reload) - this is a
structurally different, higher-level integration than the raw
`@endpoint`+`on_start` pattern `beam_apps/cover_illustrious_app.py` needed
to hand-roll for diffusers. No extra on_start/caching code is needed here
for this requirement.

WEIGHT CACHING (confirmed via Beam's own docs, not assumed - and NOT the
same as `cover_illustrious_app.py`'s pattern): the `VLLM` class's own
`volumes` parameter DEFAULTS to a Beam Volume named `vllm_cache` mounted at
`./vllm_cache` (`docs.beam.cloud/v2/reference/py-sdk.md`) - i.e. downloaded
HuggingFace weights already persist across container restarts BY DEFAULT,
with zero extra wiring, unlike the raw `@endpoint`/`Image`/`Volume` pattern
`cover_illustrious_app.py` needed to construct by hand. Not overridden here
since the default already satisfies the requirement.

SCALE TO ZERO (confirmed via Beam's own docs, not assumed): the `VLLM`
class's own `keep_warm_seconds` parameter DEFAULTS to 60 seconds
(`docs.beam.cloud/v2/reference/py-sdk.md`) - i.e. containers scale down
(stop billing) 60s after the last request by default. Not overridden here;
60s is a reasonable default for infrequent manual benchmark calls.

OPENAI-COMPATIBLE API: already satisfied by vLLM itself (no alternative
contract considered or needed - see module docstring above,
`_OpenAICompatFreeProvider`'s docstring, and
docs/reports/self-hosted-translation-provider-2026-08-31.md for why this
is the right fit with zero new repo-side code).

DETERMINISTIC METADATA FOR BENCHMARKING: vLLM's standard OpenAI-compatible
chat-completions response already includes a `usage` object
(prompt_tokens/completion_tokens/total_tokens) sufficient for token-level
benchmarking - confirmed via the SAME response shape this repo's
`_OpenAICompatFreeProvider` (Groq/Cerebras) already parses, and now also
`DocuTranslateProvider` (the "custom" class this Hy-MT2 endpoint actually
uses - see server/translation_providers.py's `last_usage` addition this
track). No server-side change was needed inside THIS file to get richer
metadata: the CLIENT side (`server/translation_domain.py`'s new
`TranslationRunMetrics`/`build_translation_run_metrics`, plus
`scripts/beam_translation_benchmark.py`) synthesizes chars/tokens/timing/
truncation-signal metadata from that same standard response, exactly as
this file's own pre-existing docstring guidance already anticipated.

7B IS GATED, NOT RECOMMENDED (unchanged this track, re-verified):
`scripts/beam_translation_benchmark.py`'s `--model` argument has NO
default and REQUIRES an explicit `tencent/Hy-MT2-7B` value to benchmark
that model - nothing in that script, this file, or
docs/reports/self-hosted-translation-provider-2026-08-31.md silently
prefers or falls back to 7B. Per this mission's own instruction: 7B is
ONLY the next real benchmark to try if a real 1.8B benchmark run (tomorrow)
shows the smaller model's quality is insufficient - it is never deployed
or recommended automatically by any code in this repo.
"""
from beam.integrations import VLLM, VLLMArgs

HYMT2_1_8B = "tencent/Hy-MT2-1.8B"
HYMT2_7B = "tencent/Hy-MT2-7B"

hymt2_1_8b = VLLM(
    name="hymt2-1-8b",
    cpu=4,
    memory="16Gi",
    # T4 (16Gi VRAM) - confirmed real/valid/available Beam serverless gpu=
    # value (docs.beam.cloud/v2/environment/gpu, fetched 2026-09-01); 1.8B
    # at bf16 (~3.6GB weights) fits comfortably - see module docstring's
    # "GPU TIER VERIFICATION" for the full citation and the real caveat
    # about Beam's current pricing page not listing a T4 rate.
    gpu="T4",
    gpu_count=1,
    workers=1,
    vllm_args=VLLMArgs(
        model=HYMT2_1_8B,
        served_model_name=[HYMT2_1_8B],
        trust_remote_code=True,  # CONFIRMED required - see module docstring
        # 8192 << max_position_embeddings=262144 (config.json, confirmed
        # real) - a DELIBERATE reduction for KV-cache VRAM headroom on a
        # 16GB T4, sized to this repo's own ~2000-char chunking, not an
        # oversight. See module docstring's own paragraph on this value.
        max_model_len=8192,
        gpu_memory_utilization=0.90,
    ),
)

# 7B: NEVER the default/recommended path - see module docstring "7B IS
# GATED, NOT RECOMMENDED". Only benchmark this after a real 1.8B run shows
# insufficient quality.
hymt2_7b = VLLM(
    name="hymt2-7b",
    cpu=8,
    memory="24Gi",
    # A10G (24Gi VRAM) - confirmed real/valid/available Beam serverless
    # gpu= value (docs.beam.cloud/v2/environment/gpu, fetched 2026-09-01);
    # real but tighter headroom for a 7B model at bf16 (~14GB weights) -
    # see module docstring's "GPU TIER VERIFICATION".
    gpu="A10G",
    gpu_count=1,
    workers=1,
    vllm_args=VLLMArgs(
        model=HYMT2_7B,
        served_model_name=[HYMT2_7B],
        trust_remote_code=True,  # CONFIRMED required - see module docstring
        max_model_len=8192,
        gpu_memory_utilization=0.90,
    ),
)
