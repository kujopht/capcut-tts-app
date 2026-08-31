"""
T4 DOCUMENT Acquisition Plugin — Universal Acquisition Engine.

Tier T4 (`AcquisitionTier.T4_DOCUMENT`) is the document seam (PDF/OCR) of the
T0-T5 ladder. This module provides ONLY the interface declaration plus a
dependency-free helper — no PDF/OCR library is a dependency of this repo today
(see `server/requirements.txt`: no pypdf/PyMuPDF/pytesseract/pdfplumber/etc),
so the plugin is an honest `available() == False` stub that the router never
selects, matching the `NotConfiguredCoverProvider` convention in
`server/cover_pipeline.py`. Building a real document importer is an explicit
dependency decision, not made by this module.
"""
from __future__ import annotations

from server.scraper.universal.acquisition import (
    AcquisitionError, AcquisitionMethod, AcquisitionResult, AcquisitionStatus,
    SourceClass,
)
from server.scraper.universal.router import AcquisitionPlugin, AcquisitionTier


class UnsupportedDocumentFormatError(Exception):
    """Raised by a future real T4 implementation when a document's format is
    not parseable. Declared here now so callers can catch the same type
    whether it comes from this module or a future concrete implementation."""


class NotConfiguredDocumentPlugin(AcquisitionPlugin):
    """T4 DOCUMENT tier stub - no PDF/OCR library is a dependency of this
    repo today (see server/requirements.txt). available() honestly
    reports False so the router NEVER selects this plugin in production
    until a real implementation replaces it - matches the established
    NotConfiguredCoverProvider pattern in server/cover_pipeline.py.

    Per AcquisitionPlugin's result-returning contract (the router's for-loop
    only handles AcquisitionResult, not exceptions), acquire() must NEVER
    raise - it translates its own "not implemented" state into a normal
    FAILED AcquisitionResult with a clear message."""

    tier = AcquisitionTier.T4_DOCUMENT
    name = "not_configured_document"

    def available(self) -> bool:
        return False

    def acquire(self, url: str, *,
                source_hint: SourceClass = SourceClass.UNKNOWN) -> AcquisitionResult:
        return AcquisitionResult(
            final_url=url, source_type=source_hint,
            status=AcquisitionStatus.FAILED,
            acquisition_method=AcquisitionMethod.DOCUMENT,
            errors=[AcquisitionError(
                stage="acquire", recoverable=False,
                message="T4 (DOCUMENT) chua duoc cau hinh - chua co thu vien "
                       "PDF/OCR nao la dependency cua repo nay.")])


def sniff_document_kind(content_type: str, first_bytes: bytes) -> str:
    """Best-effort, dependency-free sniff of a fetched body's real
    document kind by magic bytes/content-type, returning one of:
    "pdf", "plain_text", "html", "unknown". Real, useful in isolation
    even before any T4 plugin implementation exists - e.g. a T0 fetch
    that returns %PDF-1.x magic bytes is a signal a caller should route
    to T4 rather than trying to parse the body as HTML."""
    if first_bytes.startswith(b"%PDF-"):
        return "pdf"
    if "text/html" in content_type.lower() or first_bytes.startswith(b"<"):
        return "html"
    if "text/plain" in content_type.lower():
        return "plain_text"
    return "unknown"
