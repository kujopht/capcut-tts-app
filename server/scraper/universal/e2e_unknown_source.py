"""
E2E Scenario E — unknown-source reconnaissance, full pipeline.

Proves the required flow end to end on fixtures: unknown source ->
evidence collection (`fingerprint.build_fingerprint`) -> LLM proposal
(`schema_proposal.propose_extraction_schema`, injected fake llm_fn - a
real provider is a follow-up integration, the seam itself is what's being
proven here) -> deterministic schema validation -> fixture generation
(the two fixture pages below) -> multi-page validation
(`validate_schema_against_fixtures`) -> candidate adapter -> explicit
promotion (`promote_to_trusted_adapter`).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from server.scraper.universal.fingerprint import build_fingerprint
from server.scraper.universal.schema_proposal import (
    ProposedSchema, ValidationReport, promote_to_trusted_adapter,
    propose_extraction_schema, validate_schema_against_fixtures,
)

FIXTURE_PAGE_1 = '<html><body><h1>Article One</h1><span class="author">Alice</span></body></html>'
FIXTURE_PAGE_2 = '<html><body><h1>Article Two</h1><span class="author">Bob</span></body></html>'
#: A third, deliberately non-matching page - proves promotion correctly
#: refuses when a real candidate adapter would NOT generalize.
FIXTURE_PAGE_MISMATCHED = '<html><body><p>No article structure here at all.</p></body></html>'


def _minimal_selector_extractor(html: str, hint: str) -> Optional[str]:
    """Minimal reference extractor for this scenario only - understands
    exactly two hint shapes: a bare tag name ("h1") or ".classname" (first
    element carrying that class). NOT a general CSS engine - a real
    candidate adapter plugs in its own extractor via the `extractor_fn`
    seam in `schema_proposal.validate_schema_against_fixtures`."""
    if hint.startswith("."):
        cls = hint[1:]
        match = re.search(rf'class="[^"]*\b{re.escape(cls)}\b[^"]*"[^>]*>([^<]*)<', html)
        return match.group(1).strip() if match else None
    match = re.search(rf"<{re.escape(hint)}[^>]*>([^<]*)</{re.escape(hint)}>", html)
    return match.group(1).strip() if match else None


def _fake_llm(prompt: str) -> str:
    """Deterministic stand-in proving the propose->validate->promote
    pipeline - `propose_extraction_schema`'s `llm_fn` seam is provider-
    agnostic by design (see schema_proposal.py); wiring a real LLM
    provider through it is a follow-up integration, not part of what this
    scenario needs to prove."""
    return json.dumps({
        "fields": {"title": "h1", "author": ".author"},
        "confidence": 0.9, "rationale": "consistent h1+author pattern across fixtures",
    })


def run_scenario(*, mismatched_third_fixture: bool = False) -> dict:
    fingerprint = build_fingerprint(FIXTURE_PAGE_1, "https://unknown-source.example/article-1")
    schema: ProposedSchema = propose_extraction_schema(fingerprint, llm_fn=_fake_llm)

    fixtures = [FIXTURE_PAGE_1, FIXTURE_PAGE_2]
    if mismatched_third_fixture:
        fixtures.append(FIXTURE_PAGE_MISMATCHED)

    report: ValidationReport = validate_schema_against_fixtures(
        schema, fixtures, extractor_fn=_minimal_selector_extractor)
    promoted = promote_to_trusted_adapter(report)

    return {
        "fingerprint_signature": fingerprint.content_signature(),
        "proposed_fields": dict(schema.fields),
        "confidence": schema.confidence,
        "pages_validated": len(report.per_fixture),
        "pages_fully_matched": report.pages_fully_matched,
        "promoted": promoted,
    }
