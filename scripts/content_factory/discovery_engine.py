"""
Discovery Engine — Content Factory v2.

Purely READ-ONLY candidate discovery for RoyalRoad:
- Discovers candidates via search query, fandom keywords, or direct URLs.
- Gathers rich candidate metadata (no chapter body crawling).
- Runs cheap deterministic filters before LLM evaluation.
- Evaluates candidate synopsis and metadata using Gemini (via AgyAccountPool).
- Fetches sample single chapters on explicit owner demand for inspection only.
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from scripts.content_factory.crawler_adapters.royalroad_adapter import RoyalRoadAdapter, USER_AGENT
from scripts.content_factory.discovery_models import (
    CandidateState,
    DeterministicFilterConfig,
    DeterministicFilterResult,
    DiscoveredCandidate,
    GeminiCandidateEvaluation,
)
from scripts.content_factory.discovery_store import DiscoveryStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _fetch_html(url: str, timeout: int = 25, connect_timeout: int = 10) -> str:
    cmd = [
        "curl.exe", "-s", "-L",
        "--connect-timeout", str(connect_timeout),
        "--max-time", str(timeout),
        "-A", USER_AGENT,
        url,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"Failed to fetch {url}: {proc.stderr or 'Empty response'}")
    return proc.stdout


class DiscoveryEngine:
    """Read-only candidate discovery and evaluation engine."""

    def __init__(self, store: Optional[DiscoveryStore] = None):
        self.store = store or DiscoveryStore()
        self.rr_adapter = RoyalRoadAdapter()

    def get_production_work_ids(self) -> Set[str]:
        """Queries the live production registry to find already ingested works."""
        db_path = PROJECT_ROOT / "raw_spool" / "living_novel_registry.sqlite"
        if not db_path.exists():
            return set()
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT source_work_id FROM source_novel_registry WHERE source_platform = 'royalroad'"
                ).fetchall()
                return {str(r[0]) for r in rows}
        except Exception:
            return set()

    def search_royalroad(
        self,
        query: str,
        fandom_filter: Optional[str] = None,
        max_results: int = 20,
    ) -> List[DiscoveredCandidate]:
        """Searches RoyalRoad for candidate fictions (READ-ONLY, metadata only)."""
        clean_q = query.strip()
        encoded_q = quote_plus(clean_q)
        url = f"https://www.royalroad.com/fictions/search?title={encoded_q}"

        try:
            html = _fetch_html(url)
        except Exception as e:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("div", class_="fiction-list-item")
        candidates: List[DiscoveredCandidate] = []

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for it in items[:max_results]:
            try:
                # 1. Title & URL
                title_link = it.find("h2", class_="fiction-title").find("a")
                rel_url = title_link.get("href", "")
                full_url = urljoin("https://www.royalroad.com", rel_url)
                title = title_link.get_text(strip=True)

                m_id = re.search(r"/fiction/(\d+)", rel_url)
                if not m_id:
                    continue
                work_id = m_id.group(1)

                # 2. Status & Tags
                labels = [span.get_text(strip=True) for span in it.find_all("span", class_="label")]
                status = "ongoing"
                for lbl in labels:
                    lbl_low = lbl.lower()
                    if "completed" in lbl_low:
                        status = "completed"
                    elif "hiatus" in lbl_low:
                        status = "hiatus"

                tags = []
                for a in it.find_all("a", class_="fiction-tag"):
                    t = a.get_text(strip=True)
                    if t:
                        tags.append(t)

                # Fandom detection
                fandom = fandom_filter or "Fanfiction"
                t_lower = (title + " " + " ".join(tags)).lower()
                if "naruto" in t_lower:
                    fandom = "Naruto"
                elif "one piece" in t_lower:
                    fandom = "One Piece"
                elif "harry potter" in t_lower:
                    fandom = "Harry Potter"
                elif "bleach" in t_lower:
                    fandom = "Bleach"
                elif "genshin" in t_lower:
                    fandom = "Genshin Impact"
                elif "dragon ball" in t_lower or "dbz" in t_lower:
                    fandom = "Dragon Ball"

                # 3. Stats (Followers, Rating, Pages, Views, Chapters, Last Update)
                followers = 0
                views = 0
                pages = 0
                chapters = 0
                last_update = ""
                rating = 0.0

                stats_div = it.find("div", class_="stats")
                if stats_div:
                    for stat_col in stats_div.find_all("div", class_="col-sm-6"):
                        txt = stat_col.get_text(" ", strip=True)
                        if "Followers" in txt:
                            m_num = re.search(r"([\d,]+)", txt)
                            if m_num: followers = int(m_num.group(1).replace(",", ""))
                        elif "Views" in txt:
                            m_num = re.search(r"([\d,]+)", txt)
                            if m_num: views = int(m_num.group(1).replace(",", ""))
                        elif "Pages" in txt:
                            m_num = re.search(r"([\d,]+)", txt)
                            if m_num: pages = int(m_num.group(1).replace(",", ""))
                        elif "Chapters" in txt:
                            m_num = re.search(r"([\d,]+)", txt)
                            if m_num: chapters = int(m_num.group(1).replace(",", ""))

                    # Rating
                    star_span = stats_div.find("span", class_="star")
                    if star_span and star_span.get("title"):
                        try:
                            rating = float(star_span["title"])
                        except ValueError:
                            pass

                    # Time
                    time_tag = stats_div.find("time")
                    if time_tag:
                        last_update = time_tag.get("datetime") or time_tag.get("title") or time_tag.get_text(strip=True)

                # 4. Description / Synopsis
                desc_div = it.find("div", id=re.compile(r"^description-\d+"))
                desc = desc_div.get_text("\n\n", strip=True) if desc_div else ""

                # 5. Cover
                img = it.find("figure").find("img") if it.find("figure") else None
                cover_url = urljoin("https://www.royalroad.com", img["src"]) if img and img.get("src") else ""

                cand = DiscoveredCandidate(
                    source_platform="royalroad",
                    source_work_id=work_id,
                    url=full_url,
                    title=title,
                    description=desc,
                    status=status,
                    chapter_count=chapters,
                    tags=tags,
                    fandom=fandom,
                    rating=rating,
                    followers=followers,
                    views=views,
                    pages=pages,
                    last_update=last_update,
                    cover_url=cover_url,
                    crawlability_status="OK",
                    state=CandidateState.DISCOVERED,
                    discovered_at=now_str,
                )
                cand.calculate_estimates()
                candidates.append(cand)
            except Exception:
                continue

        return candidates

    def discover_from_url(self, url: str) -> Optional[DiscoveredCandidate]:
        """Discovers and parses a single candidate from a direct RoyalRoad URL."""
        try:
            meta = self.rr_adapter.fetch_metadata(url)
            work_id = meta["source_id"]
            title = meta["title"]
            desc = meta.get("description", "")
            tags = meta.get("tags", [])
            fandom = meta.get("fandom", "Fanfiction")
            status = meta.get("source_status", "ongoing")
            cover_url = meta.get("cover_url", "")

            # Get chapter count from TOC without crawling chapter bodies
            chs = self.rr_adapter.list_chapters(url)
            chapter_count = len(chs)

            cand = DiscoveredCandidate(
                source_platform="royalroad",
                source_work_id=work_id,
                url=meta["source_url"],
                title=title,
                author=meta.get("author", "Unknown Author"),
                description=desc,
                status=status,
                chapter_count=chapter_count,
                tags=tags,
                fandom=fandom,
                cover_url=cover_url,
                crawlability_status="OK",
                state=CandidateState.DISCOVERED,
                discovered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            cand.calculate_estimates()
            return cand
        except Exception as e:
            return None

    def apply_deterministic_filters(
        self,
        candidate: DiscoveredCandidate,
        config: Optional[DeterministicFilterConfig] = None,
        prod_work_ids: Optional[Set[str]] = None,
    ) -> DeterministicFilterResult:
        """Applies fast, cheap deterministic rejection filters before any LLM evaluation."""
        cfg = config or self.store.load_filter_config()
        prod_ids = prod_work_ids if prod_work_ids is not None else self.get_production_work_ids()

        reasons = []
        warnings = []

        # 1. Already exists in production
        if cfg.reject_already_in_production and candidate.source_work_id in prod_ids:
            reasons.append(f"Tác phẩm đã có trên Fanfic World Production (source_work_id: {candidate.source_work_id}).")

        # 2. Previously rejected in discovery store
        if cfg.reject_previously_rejected and self.store.is_work_rejected(candidate.source_platform, candidate.source_work_id):
            reasons.append("Tác phẩm đã bị từ chối trong các phiên trước.")

        # 3. Source inaccessible / blocked
        if cfg.reject_inaccessible and candidate.crawlability_status != "OK":
            reasons.append(f"Nguồn không thể thu thập được: {candidate.crawlability_status}.")

        # 4. Too few chapters (configurable)
        if candidate.chapter_count > 0 and candidate.chapter_count < cfg.min_chapters:
            reasons.append(f"Số chương quá ít ({candidate.chapter_count} < {cfg.min_chapters} chương yêu cầu).")

        # 5. Extremely short word count (configurable)
        if candidate.estimated_word_count > 0 and candidate.estimated_word_count < cfg.min_words:
            reasons.append(f"Dung lượng quá ngắn (~{candidate.estimated_word_count:,} từ < {cfg.min_words:,} từ yêu cầu).")

        # 6. Abandoned check (configurable, only if not completed)
        if cfg.max_days_abandoned > 0 and candidate.status != "completed" and candidate.last_update:
            try:
                # Try parsing ISO or rough date
                clean_date = candidate.last_update[:10]
                up_dt = datetime.datetime.fromisoformat(clean_date)
                days_since = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - up_dt).days
                if days_since > cfg.max_days_abandoned:
                    reasons.append(f"Tác phẩm bị bỏ dở (hơn {days_since} ngày chưa cập nhật mới; giới hạn: {cfg.max_days_abandoned} ngày).")
            except Exception:
                pass

        passed = len(reasons) == 0
        candidate.deterministic_passed = passed
        candidate.rejection_reasons = reasons

        if not passed:
            candidate.state = CandidateState.REJECTED

        return DeterministicFilterResult(passed=passed, rejection_reasons=reasons, warnings=warnings)

    def evaluate_candidate_with_gemini(
        self,
        candidate: DiscoveredCandidate,
        model: str = "gemini-3.8-flash-high",
    ) -> GeminiCandidateEvaluation:
        """
        Evaluates candidate synopsis and metadata using Gemini via AgyAccountPool.
        Evaluates only metadata & synopsis — does NOT crawl or translate chapters.
        """
        prompt = f"""Bạn là Giám Đốc Biên Tập Nội Dung cho nền tảng Fanfic World (audiobook & web novel).
Hãy đánh giá tiềm năng xuất bản tiếng Việt cho tác phẩm sau dựa trên metadata và tóm tắt:

TIÊU ĐỀ: {candidate.title}
FANDOM / THỂ LOẠI: {candidate.fandom}
THẺ TAGS: {", ".join(candidate.tags)}
SỐ CHƯƠNG: {candidate.chapter_count} chương (~{candidate.estimated_word_count:,} từ)
TRẠNG THÁI NGUỒN: {candidate.status}
ĐÁNH GIÁ ĐỘC GIẢ NGUỒN: {candidate.rating}/5 ({candidate.followers:,} followers, {candidate.views:,} views)
TÓM TẮT (SYNOPSIS):
{candidate.description[:2000] if candidate.description else 'Không có tóm tắt chi tiết.'}

HÃY CHẤM ĐIỂM TỪ 0 ĐẾN 10 CHO TỪNG TIÊU CHÍ SAU:
1. story_quality: Tiềm năng cốt truyện, văn phong, sức hút độc giả.
2. fandom_fit: Mức độ tương thích và độ hot của fandom tại Việt Nam (Naruto, One Piece, Harry Potter, v.v.).
3. translation_value: Giá trị khi chuyển ngữ sang tiếng Việt (độ mượt, thuật ngữ, sự hấp dẫn văn bản).
4. catalog_uniqueness: Tính độc đáo, không trùng lặp mô-típ quá nhàm chán trong kho truyện.
5. update_health: Tình trạng duy trì tác phẩm (độ dài, tiến độ).
6. crawlability: Cấu trúc văn bản và tính khả thi thu thập.

YÊU CẦU TRẢ VỀ DUY NHẤT MỘT JSON OBJECT (không thêm văn bản ngoài):
{{
  "story_quality": 8.5,
  "fandom_fit": 9.0,
  "translation_value": 8.0,
  "catalog_uniqueness": 7.5,
  "update_health": 8.5,
  "crawlability": 9.5,
  "overall_score": 8.5,
  "reasons": "Lý do súc tích vì sao tác phẩm này đáng hoặc không đáng duyệt...",
  "risks": "Các rủi ro cần lưu ý (vd: OC quá đà, thuật ngữ nhẫn thuật phức tạp, bỏ dở giữa chừng)...",
  "potential_translation_issues": ["Thuật ngữ chakra/jutsu", "Biệt danh tiếng Anh"],
  "recommended_for_owner_review": true
}}"""

        try:
            from scripts.content_factory.gemini_evaluator import call_gemini
            raw_res = call_gemini(prompt, model=model, timeout_seconds=45)

            # Clean markdown fences
            clean_res = re.sub(r"^```json\s*", "", raw_res.strip(), flags=re.IGNORECASE)
            clean_res = re.sub(r"^```\s*", "", clean_res)
            clean_res = re.sub(r"\s*```$", "", clean_res)

            data = json.loads(clean_res)
            eval_res = GeminiCandidateEvaluation(
                story_quality=float(data.get("story_quality", 0.0)),
                fandom_fit=float(data.get("fandom_fit", 0.0)),
                translation_value=float(data.get("translation_value", 0.0)),
                catalog_uniqueness=float(data.get("catalog_uniqueness", 0.0)),
                update_health=float(data.get("update_health", 0.0)),
                crawlability=float(data.get("crawlability", 0.0)),
                overall_score=float(data.get("overall_score", 0.0)),
                reasons=str(data.get("reasons", "")),
                risks=str(data.get("risks", "")),
                potential_translation_issues=data.get("potential_translation_issues", []),
                recommended_for_owner_review=bool(data.get("recommended_for_owner_review", False)),
                model_used=model,
            )
        except Exception as e:
            # Fallback heuristic evaluation when Gemini accounts are unavailable
            # Ensures Discovery Mode NEVER breaks!
            base_score = min(10.0, max(1.0, candidate.rating * 1.8))
            eval_res = GeminiCandidateEvaluation(
                story_quality=round(base_score, 1),
                fandom_fit=8.5 if candidate.fandom in ("Naruto", "One Piece", "Harry Potter") else 7.0,
                translation_value=7.5,
                catalog_uniqueness=7.0,
                update_health=8.0 if candidate.status == "ongoing" else 6.0,
                crawlability=9.0,
                overall_score=round(base_score * 0.9, 1),
                reasons=f"Đánh giá sơ bộ từ chỉ số nguồn ({candidate.rating} sao, {candidate.followers:,} followers). Đang chờ LLM rà soát thêm.",
                risks="Chưa có đánh giá chi tiết từ LLM (Fallback mode).",
                potential_translation_issues=[],
                recommended_for_owner_review=(candidate.followers > 1000 and candidate.rating >= 4.2),
                model_used="heuristic-fallback",
            )

        candidate.gemini_eval = eval_res
        candidate.overall_score = eval_res.overall_score
        candidate.evaluated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return eval_res

    def fetch_sample_chapter(self, candidate: DiscoveredCandidate, chapter_order: int = 1) -> Dict[str, Any]:
        """
        Fetches ONE sample chapter for quality inspection.
        READ-ONLY: Does NOT translate or synthesize TTS.
        """
        chs = self.rr_adapter.list_chapters(candidate.url)
        target_ch = None
        for ch in chs:
            if ch["order"] == chapter_order:
                target_ch = ch
                break
        if not target_ch and chs:
            target_ch = chs[0]

        if not target_ch:
            return {"error": "Không tìm thấy chương mẫu nào."}

        raw_ch = self.rr_adapter.fetch_chapter(target_ch)
        return {
            "source_work_id": candidate.source_work_id,
            "chapter_order": raw_ch.source_order,
            "chapter_title": raw_ch.source_title,
            "word_count": len(raw_ch.source_text.split()),
            "character_count": len(raw_ch.source_text),
            "sample_paragraphs": raw_ch.source_text.split("\n\n")[:5],
            "full_text_snippet": raw_ch.source_text[:1500],
        }
