"""
T2 BROWSER_RENDERED acquisition plugin — Universal Acquisition Engine
Hardening (2026-08-31).

No browser-automation library (Playwright/Selenium/Puppeteer-equivalent) is
a dependency of this repo today (confirmed: `server/requirements.txt` has
none) — adding one is a real, explicit dependency decision, out of scope
for this module (see `AI_ROUTER.md` "khong xay truoc khi co bang chung").
This module therefore defines the PLUGIN SEAM (`BrowserRenderer` protocol +
`BrowserRenderedPlugin`) that a future real renderer (Playwright, or a
remote browser service) plugs into, plus a `NotConfiguredBrowserRenderer`
stub matching the established `NotConfiguredCoverProvider`/
`DriveArchiveBackend` "honest, zero-dependency stub" pattern.

REAL PROOF that T2 is a genuine, necessary tier (not a hypothetical) was
gathered THIS SESSION via a real, ordinary, unauthenticated browser session
(`mcp__claude-in-chrome__*` tools — ordinary visitor path, no injected
decryption code, no key extraction, no CAPTCHA bypass) against
docln.net/truyen/14376-thien-su-nha-ben — see `docs/reports/
t2-browser-rendered-proof-2026-08-31.md` for the full evidence: T0 direct
HTTP retrieves only a server-side XOR-shuffle-encrypted blob
(`id="chapter-c-protected"`, `data-s="xor_shuffle"`) with zero readable
chapter text; the SAME page, rendered by the site's own ordinary JavaScript
in a real browser, produces full readable Vietnamese chapter text in the
DOM with no challenge presented to an ordinary visitor. That gap — T0
retrieves ciphertext, T2 (browser rendering) retrieves the real content the
site's own JS already produces for everyone — is exactly what this tier
exists to bridge, and is not achievable by any smarter T0/T1 heuristic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from server.scraper.universal.acquisition import (
    AcquisitionError, AcquisitionMethod, AcquisitionResult, AcquisitionStatus,
    SourceClass,
)
from server.scraper.universal.router import AcquisitionPlugin, AcquisitionTier


@dataclass(frozen=True)
class BrowserRenderResult:
    """What a real renderer hands back after loading *url* in an ordinary
    (unauthenticated, no injected script beyond normal page JS) browser
    session and letting the page's own JavaScript finish running.

    `challenge_detected`: the renderer's own honest signal that it hit a
    CAPTCHA/bot-challenge/access-denial page instead of real content — a
    `BrowserRenderedPlugin` must surface this as BLOCKED, never silently
    treat challenge-page HTML as if it were real content."""

    final_url: str
    html: str
    visible_text: str
    status_code: int = 200
    challenge_detected: bool = False


class BrowserRenderer(Protocol):
    """The seam a real renderer implements — Playwright, a remote browser
    service, or (as used for this session's real proof) a human-in-the-loop
    interactive browser tool. `render()` must NEVER raise for a normal
    navigation failure/challenge — report it via `BrowserRenderResult`
    (empty html + `challenge_detected=True`, or a non-200 `status_code`)
    so `BrowserRenderedPlugin.acquire()` can translate it into a clean
    AcquisitionResult instead of propagating an exception out of the
    router's acquisition loop."""

    def render(self, url: str) -> BrowserRenderResult: ...


class NotConfiguredBrowserRenderer:
    """Honest zero-dependency stub — matches `NotConfiguredCoverProvider`
    (`server/cover_pipeline.py`) and `DriveArchiveBackend`
    (`server/storage_backend.py`): no real renderer is wired in by
    default, and this reports that honestly via a challenge-flagged
    result rather than pretending to succeed."""

    def render(self, url: str) -> BrowserRenderResult:
        return BrowserRenderResult(
            final_url=url, html="", visible_text="", status_code=0,
            challenge_detected=False)


class BrowserRenderedPlugin(AcquisitionPlugin):
    """T2 tier — wraps an injected `BrowserRenderer`. `available()` is
    honest: False when no real renderer is configured (the
    `NotConfiguredBrowserRenderer` default), so `AcquisitionRouter` never
    silently selects a non-functional T2 path — it simply continues down
    the tier ladder to T3/T4/T5 or reports FAILED, exactly like any other
    unavailable plugin (see `test_unavailable_plugin_is_skipped` in
    `server/tests/test_universal_router.py`)."""

    tier = AcquisitionTier.T2_BROWSER_RENDERED
    name = "browser_rendered"

    def __init__(self, renderer: Optional[BrowserRenderer] = None) -> None:
        self._renderer: BrowserRenderer = renderer or NotConfiguredBrowserRenderer()
        self._configured = renderer is not None

    def available(self) -> bool:
        return self._configured

    def acquire(self, url: str, *,
               source_hint: SourceClass = SourceClass.UNKNOWN) -> AcquisitionResult:
        try:
            result = self._renderer.render(url)
        except Exception as exc:  # noqa: BLE001 — a renderer must never crash the router
            return AcquisitionResult(
                final_url=url, source_type=source_hint,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.BROWSER_RENDER,
                errors=[AcquisitionError(
                    stage="fetch", recoverable=True,
                    message=f"Loi renderer T2 khi tai {url}: {exc}"[:500])])

        if result.challenge_detected:
            return AcquisitionResult(
                final_url=result.final_url, source_type=source_hint,
                status=AcquisitionStatus.BLOCKED,
                acquisition_method=AcquisitionMethod.BROWSER_RENDER,
                errors=[AcquisitionError(
                    stage="fetch", recoverable=False,
                    message="Renderer T2 phat hien CAPTCHA/bot-challenge/tu choi "
                           "truy cap - KHONG coi trang challenge la noi dung that.")])

        if not result.html and not result.visible_text:
            return AcquisitionResult(
                final_url=result.final_url, source_type=source_hint,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.BROWSER_RENDER,
                errors=[AcquisitionError(
                    stage="fetch", recoverable=True,
                    message=f"Renderer T2 tra ve rong cho {url} (status_code="
                           f"{result.status_code}).")])

        return AcquisitionResult(
            final_url=result.final_url, source_type=source_hint,
            status=AcquisitionStatus.OK,
            acquisition_method=AcquisitionMethod.BROWSER_RENDER,
            content_type="text/html",
            html=result.html or None,
            text_markdown=result.visible_text or None,
            metadata={"status_code": result.status_code},
            provenance="BrowserRenderedPlugin/t2_browser_rendered")
