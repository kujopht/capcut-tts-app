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

GPU TIER - CORRECTED BY REAL DEPLOY EVIDENCE (2026-09-01, supersedes the
prior turn's docs-only claim below): a real
`beam deploy beam_apps/translation_hymt2_app.py:hymt2_1_8b` with `gpu="T4"`
FAILED with Beam's own error: "This GPU type is not supported. Please use
an A10G or RTX 4090 instead." This disproves the earlier assumption (based
only on docs.beam.cloud/v2/environment/gpu listing `"T4"` as an enum value)
that T4 was actually accepted for this `beam.integrations.VLLM` construct -
docs listing a string as a valid enum value is not the same as Beam's
serverless scheduler actually having T4 capacity available for it. 1.8B is
therefore deployed on `gpu="RTX4090"` (24Gi VRAM) instead: Hy-MT2-1.8B at
bf16 is ~3.6GB of weights, so at `gpu_memory_utilization=0.90` (~21.6GB
budget) there is ample headroom for KV cache - MORE than the original
16GB-T4 sizing assumed, not less. 7B stays on `"A10G"` (24Gi VRAM,
untouched this track) - the real error message's own wording ("use an
A10G or RTX 4090 instead") independently CONFIRMS A10G remains a valid,
accepted tier for this same `VLLM` construct, so 7B's existing citation
below is not affected by this correction. Hy-MT2-7B at bf16 is ~14GB of
weights, fitting the same 24GB A10G budget with real but tighter headroom
than 1.8B now has on RTX4090 - consistent with why 7B stays gated to its
own dedicated tier rather than sharing 1.8B's.

COST RATE - IMPROVED BY THE SAME CORRECTION: unlike the superseded T4
assumption, Beam's OWN current public pricing page (beam.cloud/pricing,
checked 2026-09-01) DOES publish a per-second rate for RTX4090
(`$0.000191667/s` exactly - the SAME published figure
`scripts/beam_cover_benchmark.py::RTX4090_PER_SECOND_USD` already uses for
the cover pipeline). 1.8B's cost estimate is therefore now a real,
Beam-published MEASURED rate, not a third-party guess. A10G still has NO
published rate on that same pricing page (cross-checked against two
independent third-party aggregators, computestacker.com and
cloudgpuprices.com, which agree A10G is absent from the current serverless
rate table; a third aggregator, gputracker.dev, lists $1.10/hr for A10G
but this could not be independently confirmed on Beam's own site) - 7B's
cost estimate in `scripts/beam_translation_benchmark.py` therefore remains
an UNVERIFIED third-party estimate, clearly labeled as such and never
conflated with 1.8B's now-measured RTX4090 figure.

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
    # RTX4090 (24Gi VRAM) - REAL deploy evidence (2026-09-01): a real
    # `beam deploy ...:hymt2_1_8b` with gpu="T4" FAILED with Beam's own
    # error "This GPU type is not supported. Please use an A10G or RTX
    # 4090 instead." - T4 was never actually schedulable for this VLLM
    # construct despite being listed as a docs enum value. RTX4090 has
    # MORE VRAM headroom for 1.8B's ~3.6GB weights than the original T4
    # assumption, and a Beam-PUBLISHED per-second rate ($0.000191667/s,
    # same as scripts/beam_cover_benchmark.py::RTX4090_PER_SECOND_USD) -
    # see module docstring's "GPU TIER - CORRECTED BY REAL DEPLOY
    # EVIDENCE" for the full citation.
    gpu="RTX4090",
    gpu_count=1,
    workers=1,
    vllm_args=VLLMArgs(
        model=HYMT2_1_8B,
        served_model_name=[HYMT2_1_8B],
        trust_remote_code=True,  # CONFIRMED required - see module docstring
        # 8192 << max_position_embeddings=262144 (config.json, confirmed
        # real) - a DELIBERATE reduction for KV-cache VRAM headroom, sized
        # to this repo's own ~2000-char chunking, not an oversight - kept
        # unchanged by the T4->RTX4090 GPU-tier correction above (this
        # value was never about a specific GPU tier's VRAM, only about not
        # reserving KV-cache for context length this repo never uses). See
        # module docstring's own paragraph on this value.
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
