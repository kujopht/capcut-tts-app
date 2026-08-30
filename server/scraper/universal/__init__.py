"""
Universal Source Intelligence (Story Harvester V5) — provider-neutral
acquisition/adapter/identity layer sitting ALONGSIDE the existing V4
fiction-only pipeline (`server/scraper/contract.py`,
`server/scraper/adapters/`), not replacing it.

Layout:
    acquisition.py          — SourceClass, AcquisitionResult (Phase 1)
    adapter.py               — SourceAdapter contract + StoryProvider bridge (Phase 4)
    router.py                 — AcquisitionRouter, tiered strategy selection (Phase 2)
    network_intelligence.py  — endpoint candidate validation, never auto-trust (Phase 3)
    identity.py               — CanonicalIdentity, cross-source dedup (Phase 9)
    units.py                  — normalized domain units (Story/Video/Document/Feed) (Phase 10)
    change_detection.py      — UnitChangeKind, generic change classification (Phase 11)
    fingerprint.py            — deterministic SourceFingerprint for unknown sources (Phase 8)
    schema_proposal.py        — LLM-proposal seam + deterministic validation/promotion (Phase 8)
    semantic.py                — optional semantic-ready derived artifacts (Phase 12)

See `docs/UNIVERSAL_SOURCE_INTELLIGENCE.md` for the full design + security model.
"""
