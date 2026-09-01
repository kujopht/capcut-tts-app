"""
Beam Cloud GPU endpoint — Tencent Hy-MT2-1.8B via DIRECT Transformers
inference. Mission "HY-MT2 1.8B TRANSFORMERS FALLBACK, NO MANAGED VLLM"
(2026-09-01) — replaces `translation_hymt2_app.py`'s `hymt2_1_8b`
(`beam.integrations.VLLM`) deployment, NOT `hymt2_7b` (left untouched,
still gated, still never deployed automatically).

WHY THIS FILE EXISTS (real, confirmed root cause — see
`translation_hymt2_app.py`'s own corrected docstring for the full prior
investigation): Hy-MT2's `HunYuanDenseV1ForCausalLM` architecture is NOT
supported by any tagged/PyPI-published vLLM release as of 2026-09-01 (the
model's own HuggingFace card says to build vLLM from git main; the latest
PyPI vLLM release, 0.19.1, predates the model's own release date).
`beam.integrations.VLLM` can only pin a PyPI version string, not build
from source — so the managed-VLLM path is closed for this model UNTIL
vLLM ships tagged support. Hy-MT2's OWN model card officially documents a
SECOND, fully-supported serving path TODAY: direct `transformers`
inference (`transformers>=5.6.0`, confirmed to exist on PyPI as of
2026-09-01 — latest is 5.16.1). This file implements exactly that path,
deliberately NOT vLLM, NOT SGLang, NOT a source-built vLLM (see mission's
own explicit "Do not" list — those are a SEPARATE, future, throughput-only
evaluation that should only happen AFTER this file proves the model's
TRANSLATION QUALITY is good enough to matter).

WHY `@asgi`, NOT PLAIN `@endpoint` (a deliberate reading of the mission's
literal "Use Beam @endpoint" against its ACTUAL stated goal, not a
deviation from it): the mission's own Section B requires "exposing an
OpenAI-compatible minimal endpoint so the existing
TranslationService/custom provider adapter can use it unchanged" -
`server/translation_providers.py::DocuTranslateProvider` POSTs to
`{TRANSLATION_BASE_URL}/chat/completions` (a SUB-PATH under the
configured base URL, confirmed via that class's own `self._client.post(
"/chat/completions", ...)`) - a plain `beam.endpoint` maps ONE Python
function to the bare invoke URL with NO sub-path routing (confirmed via
`cover_illustrious_app.py`'s own invocation snippet output: `curl -X POST
'{url}'`, no path suffix). `beam.asgi` (real, documented in
`beta9/abstractions/endpoint.py::ASGI`, re-exported as `beam.asgi`) is the
mechanism that actually satisfies the STATED requirement: it lets the
decorated function build and return a real FastAPI app with named routes
(`@app.post("/chat/completions")`, `@app.post("/health")`), while still
using the SAME `on_start`/`Volume`/`gpu=`/`image=` configuration surface
as a plain endpoint - it is Beam's own "endpoint" family, not a detour
into `beam.integrations.VLLM` territory (confirmed via reading
`beta9/abstractions/endpoint.py`: `ASGI` does NOT override `deploy()`, so
it goes through the SAME safe, `rollout`-handling-correctly generic
`mixins.py::deploy()` path as a plain endpoint - it does NOT hit the
known VLLM.deploy()/print_invocation_snippet() rollout-kwarg crash
documented in `translation_hymt2_app.py`, since that crash is specific to
`beta9/abstractions/integrations/vllm.py::VLLM.deploy()`'s own override).

OFFICIAL LOADING PATTERN (huggingface.co/tencent/Hy-MT2-1.8B, fetched
2026-09-01, quoted not paraphrased-from-memory):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=torch.bfloat16, device_map="auto",
        trust_remote_code=True)
`dtype=` (NOT the older `torch_dtype=` kwarg) is the model card's OWN
example — `transformers>=5.6.0` renamed this argument; using the old name
would still work today via a deprecation shim in most 5.x releases, but
the officially-published example uses `dtype=`, so this file matches it
exactly rather than the deprecated spelling.

OFFICIAL CHAT TEMPLATE / INSTRUCTION FORMAT (same source, fetched
2026-09-01): `tokenizer.apply_chat_template(messages, add_generation_prompt=True,
return_tensors="pt")` with a SINGLE `{"role": "user", "content": prompt}`
message - the model card states explicitly "our models do not have a
default system_prompt". The card's own example instruction template is:
    "Translate the following text into {target_lang}. Note that you
    should only output the translated result without any additional
    explanation:"
DESIGN DECISION (documented, not a silent deviation): the OpenAI-shaped
request this endpoint actually receives (built by `DocuTranslateProvider`'s
`_he_thong_prompt`/`_nguoi_dung_prompt`) already carries a SYSTEM-role
message with equivalent instructions IN VIETNAMESE (genre/naming-mode/
xung-ho-aware, richer than the bare English template above) and a
USER-role message with the actual source text + glossary + chapter
summary. Since Hy-MT2 has no system-prompt concept, this endpoint FOLDS
the incoming system content into the single user message it sends to the
model (`system + "\n\n" + user`) rather than discarding this repo's
existing, tested prompt engineering and replacing it with the bare
English template - that would strip glossary/genre/naming-mode context
this app's translation quality already depends on. The model still gets
ONE clear, explicit "translate this" instruction either way; it is not
told to translate twice in two different phrasings.

RECOMMENDED 1.8B GENERATION PARAMETERS (same source, matches this repo's
own pre-existing `TRANSLATION_CUSTOM_GENERATION_PARAMS` citation in
`server/translation_providers.py`, not re-derived): temperature=0.7,
top_p=0.6, top_k=20, repetition_penalty=1.05, max_new_tokens=4096.

READINESS (mission Section E): `/health` does NOT run `model.generate()` -
it only confirms the process is up and `context.on_start_value` (tokenizer
+ model) is populated on CUDA. `scripts/beam_operator.py`'s `wait-ready
--kind transformers` POSTs here, never to `/v1/models` (that was the
OLD, now-abandoned managed-VLLM path's readiness signal, meaningless for
this file).

WEIGHT CACHING (mission Section D — no model weights in the deploy
payload, first container downloads, later containers reuse): a dedicated
Beam `Volume` (`hymt2-transformers-cache`, distinct name from the
abandoned VLLM deployment's `vllm_cache`/`vllm_cache_root` volumes -
deliberately NOT reused, since those were left in an unknown/possibly
inconsistent state by the failed VLLM attempts) is mounted as
`transformers`' own `cache_dir` for both `from_pretrained()` calls.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beam import Image, Volume, asgi  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402

MODEL_ID = "tencent/Hy-MT2-1.8B"
CACHE_PATH = "./hymt2-transformers-cache"

#: Pinned to the model card's OWN stated minimum (not the latest available,
#: 5.16.1, as of 2026-09-01) - the minimum is the version Tencent's own
#: card was validated against; a newer transformers release could
#: introduce an unrelated breaking change for this specific
#: `trust_remote_code=True` custom architecture that a general transformers
#: changelog would not flag as relevant to this one model.
TRANSFORMERS_VERSION = "5.6.0"

image = Image(python_version="python3.11").add_python_packages([
    f"transformers=={TRANSFORMERS_VERSION}",
    "torch>=2.4,<3.0",
    "accelerate>=0.34,<2.0",
    "fastapi",
])

#: Official 1.8B generation parameters (huggingface.co/tencent/Hy-MT2-1.8B,
#: fetched 2026-09-01) - same values already cited in
#: server/translation_providers.py's TRANSLATION_CUSTOM_GENERATION_PARAMS
#: docstring from the earlier (abandoned) VLLM mission, not re-derived.
GENERATION_PARAMS: Dict[str, Any] = dict(
    temperature=0.7,
    top_p=0.6,
    top_k=20,
    repetition_penalty=1.05,
    max_new_tokens=4096,
)


def load_model() -> Dict[str, Any]:
    """on_start hook — returns almost IMMEDIATELY, spawning a background
    thread that does the real (slow) loading work, instead of blocking
    on_start itself until the model is fully loaded.

    WHY (mission "COMBINED MISSION" Phase 2, 2026-09-01): Beam does not
    start routing HTTP requests to the ASGI app until on_start AND
    web_server() have BOTH returned — a state machine that blocks inside
    on_start could never be OBSERVED mid-flight, because by the time
    /health is reachable at all, on_start has already finished (success or
    failure). Returning immediately and loading in a background thread
    means the container becomes reachable within seconds of starting, and
    /health can report REAL, live phase transitions
    (process_started -> tokenizer_loading -> model_loading -> ready, or
    -> startup_failed) while a first-ever ~4GB weight download is still in
    progress — `wait-ready` gets real signal throughout instead of
    blocking silently for minutes with zero information.

    Returns the SAME mutable dict `state` that `web_server()` closes over
    and both routes read live — CPython's GIL makes individual dict
    get/set operations atomic, which is all this needs (no invariant here
    spans more than one key at a time).

    REAL incident this file's error-capture already survived once
    (2026-09-01): the first deploy of this file returned a persistent
    HTTP 500 from /health with an empty weight-cache Volume, and this
    session's `beam logs` access was independently blocked by an
    unrelated local SSL/SNI error reaching Beam's realtime log websocket
    (`rt.beam.cloud`) — there was no way to see the real traceback.
    Catching here and storing the error STRING (never the exception
    object/traceback) means the NEXT attempt can self-diagnose via
    /health alone, with no dependency on `beam logs` working at all."""
    state: Dict[str, Any] = {
        "phase": "process_started",
        "tokenizer_loaded": False,
        "model_loaded": False,
        "device": None,
        "tokenizer_load_seconds": None,
        "model_load_seconds": None,
        "load_error": "",
        "tokenizer": None,
        "model": None,
    }

    def _worker() -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        try:
            state["phase"] = "tokenizer_loading"
            t0 = time.monotonic()
            tokenizer = AutoTokenizer.from_pretrained(
                MODEL_ID, trust_remote_code=True, cache_dir=CACHE_PATH)
            state["tokenizer"] = tokenizer
            state["tokenizer_loaded"] = True
            state["tokenizer_load_seconds"] = round(time.monotonic() - t0, 2)

            state["phase"] = "model_loading"
            t1 = time.monotonic()
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_ID, dtype=torch.bfloat16, device_map="auto",
                trust_remote_code=True, cache_dir=CACHE_PATH,
            )
            model.eval()
            state["model"] = model
            state["model_loaded"] = True
            state["model_load_seconds"] = round(time.monotonic() - t1, 2)
            state["device"] = str(next(model.parameters()).device)
            state["phase"] = "ready"
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see above
            state["load_error"] = f"{type(exc).__name__}: {exc}"
            state["phase"] = "startup_failed"

    threading.Thread(target=_worker, name="hymt2-model-loader", daemon=True).start()
    return state


def _extract_prompt_text(messages: List[Dict[str, str]]) -> str:
    """Fold an incoming OpenAI-shaped system+user message pair into ONE
    user-role string for Hy-MT2 (see module docstring's "DESIGN DECISION"
    section for why this preserves this repo's existing prompt engineering
    instead of discarding it for the bare official template)."""
    system_content = ""
    user_content = ""
    for m in messages:
        role = m.get("role")
        if role == "system" and not system_content:
            system_content = (m.get("content") or "").strip()
        elif role == "user":
            user_content = (m.get("content") or "").strip()
    if system_content and user_content:
        return f"{system_content}\n\n{user_content}"
    return user_content or system_content


@asgi(
    name="hymt2-1-8b-transformers",
    image=image,
    on_start=load_model,
    volumes=[Volume(name="hymt2-transformers-cache", mount_path=CACHE_PATH)],
    gpu="RTX4090",
    cpu=4,
    memory="16Gi",
    # Same real incident/citation as cover_illustrious_app.py's @endpoint:
    # Beam's default timeout (180s) can plausibly be exceeded by a fully
    # cold container (first-ever ~4GB weight download + model init +
    # generation on the same request). keep_warm_seconds intentionally
    # left at @asgi's own default - that is the separate scale-to-zero
    # knob, not this one.
    timeout=900,
)
def web_server(context):
    # REAL BUG (2026-09-01): `FastAPI`/`Request` were previously imported
    # LOCALLY inside this function. Combined with this file's own
    # `from __future__ import annotations` (PEP 563 postponed evaluation,
    # every annotation becomes a lazily-resolved STRING), FastAPI's own
    # `typing.get_type_hints(endpoint, globalns=endpoint.__globals__)`
    # could never resolve the `request: Request` annotation on the NESTED
    # `chat_completions`/`health` functions below - `__globals__` is
    # always the DEFINING MODULE's globals, never an enclosing function's
    # local scope, so a name imported only inside `web_server()` is
    # invisible to it. FastAPI silently fell back to treating `request`
    # as an ordinary (unresolvable) parameter, returning a REAL, live
    # HTTP 422 ("field required: query.request") instead of ever reaching
    # this function's body - reproduced locally via a real FastAPI
    # TestClient call, not assumed. Moving the import to module level
    # (see top of file) puts `Request` in the module's own `__globals__`,
    # which the postponed string annotation resolves against correctly.
    state = context.on_start_value
    app = FastAPI()

    @app.post("/health")
    async def health():
        # Mission Section E: MUST NOT run generation - reads `state` only,
        # never touches the model/tokenizer objects themselves. `status` is
        # the coarse 3-value field wait-ready keys off; `phase` is the full
        # granular state machine for humans/logs.
        phase = state["phase"]
        status = ("ready" if phase == "ready"
                 else "startup_failed" if phase == "startup_failed"
                 else "loading")
        return {
            "status": status,
            "phase": phase,
            "process_running": True,
            "tokenizer_loaded": state["tokenizer_loaded"],
            "model_loaded": state["model_loaded"],
            "device": state["device"],
            "tokenizer_load_seconds": state["tokenizer_load_seconds"],
            "model_load_seconds": state["model_load_seconds"],
            # Self-diagnosing on purpose (see load_model()'s own comment):
            # this is the ONLY way to see the real failure reason without
            # `beam logs` working. Exception STRING only, never a raw
            # traceback object.
            "load_error": state["load_error"],
        }

    @app.post("/chat/completions")
    async def chat_completions(request: Request):
        if state["phase"] == "startup_failed":
            return {"error": f"model failed to load: {state['load_error']}"}
        if state["phase"] != "ready":
            return {"error": f"model not ready yet (phase={state['phase']})"}
        import torch

        tokenizer = state["tokenizer"]
        model = state["model"]

        body = await request.json()
        messages = body.get("messages", [])
        prompt_text = _extract_prompt_text(messages)
        if not prompt_text:
            return {"error": "no user/system message content to translate"}

        gen_start = time.monotonic()
        chat_messages = [{"role": "user", "content": prompt_text}]
        inputs = tokenizer.apply_chat_template(
            chat_messages, add_generation_prompt=True, return_tensors="pt",
        ).to(model.device)
        input_token_count = int(inputs.shape[-1])

        with torch.inference_mode():
            outputs = model.generate(
                inputs,
                do_sample=True,
                temperature=GENERATION_PARAMS["temperature"],
                top_p=GENERATION_PARAMS["top_p"],
                top_k=GENERATION_PARAMS["top_k"],
                repetition_penalty=GENERATION_PARAMS["repetition_penalty"],
                max_new_tokens=GENERATION_PARAMS["max_new_tokens"],
                pad_token_id=tokenizer.eos_token_id,
            )
        generation_seconds = time.monotonic() - gen_start

        new_tokens = outputs[0][input_token_count:]
        output_token_count = int(new_tokens.shape[-1])
        completion = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

        return {
            "choices": [{"message": {"role": "assistant", "content": completion}}],
            "model": MODEL_ID,
            "usage": {
                "prompt_tokens": input_token_count,
                "completion_tokens": output_token_count,
                "total_tokens": input_token_count + output_token_count,
            },
            "model_load_seconds": state["model_load_seconds"],
            "tokenizer_load_seconds": state["tokenizer_load_seconds"],
            "generation_seconds": round(generation_seconds, 2),
        }

    return app
