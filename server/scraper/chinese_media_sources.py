"""Source/channel registry — Chinese Media Watcher foundation (2026-09-02).

Real candidate channels for AI 动态漫/AI漫剧/有声小说动画/AI短剧 content, found via
web research (see docs/reports/chinese-media-factory-2026-09-02.md for the
search trail). NOT a claim that any of these channels holds verified
redistribution rights for their uploads — that question is answered PER
EPISODE by `classify_rights()` below, at discovery time, never assumed from
the channel alone.

Polling is via YouTube's public RSS feed
(`https://www.youtube.com/feeds/videos.xml?channel_id=...`) — no API key,
no login, no scraping, officially documented, and exactly what this feed
exists for. Three sources below have a channel_id already resolved (real,
independently confirmed); the rest are known real channels whose id needs
a one-time resolution before they can be polled (deliberately left
unresolved rather than guessed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class ChineseMediaSource:
    source_id: str
    platform: str
    display_name: str
    #: Real YouTube channel id (UC...). Empty = known real channel, id not
    #: yet resolved -- `chinese_media_watcher.py` skips these rather than
    #: guessing an id.
    channel_id: str
    category: str
    channel_url: str
    notes: str = ""


#: Every entry here is a REAL channel found via web search, not invented.
#: `channel_id` empty means "known, not yet actionable for RSS polling" --
#: tracked honestly rather than silently dropped.
SOURCES: Tuple[ChineseMediaSource, ...] = (
    ChineseMediaSource(
        source_id="bobo_manju",
        platform="youtube",
        display_name="波波漫剧",
        channel_id="UCWQbu4dfyp91GjgodVznXaQ",
        category="AI漫剧",
        channel_url="https://www.youtube.com/channel/UCWQbu4dfyp91GjgodVznXaQ",
    ),
    ChineseMediaSource(
        source_id="dongman_shuwu",
        platform="youtube",
        display_name="動漫書屋",
        channel_id="UCp-6a0eO9j2vhm80_thYO2g",
        category="有声小说动画",
        channel_url="https://www.youtube.com/channel/UCp-6a0eO9j2vhm80_thYO2g",
        notes="Đã xác nhận (tìm kiếm 2026-09-02): tự mô tả sản xuất nội dung "
             "audiobook kèm hình ảnh AI-generated -- khớp đúng thể loại "
             "'có声小说动画'.",
    ),
    ChineseMediaSource(
        source_id="tiantian_xiaoshuo_dongman",
        platform="youtube",
        display_name="天天小說動漫",
        channel_id="UC1WCXZHBHi2sfgd2IgnpN8g",
        category="有声小说动画",
        channel_url="https://www.youtube.com/channel/UC1WCXZHBHi2sfgd2IgnpN8g",
    ),
    ChineseMediaSource(
        source_id="kk_aikan",
        platform="youtube",
        display_name="KK爱看",
        channel_id="",
        category="AI漫剧",
        channel_url="https://www.youtube.com/@KKAIKAN",
        notes="Da dung lam ung vien video-draft mission truoc (2026-09-01) — "
             "channel that, nhung channel_id (UC...) chua duoc giai (trang "
             "kenh la SPA, WebFetch khong lay duoc metadata JS-render).",
    ),
    ChineseMediaSource(
        source_id="guanguan_manju",
        platform="youtube",
        display_name="关关漫剧 / 关关解说",
        channel_id="",
        category="AI漫剧",
        channel_url="https://www.youtube.com/@%E5%85%B3%E5%85%B3%E8%A7%A3%E8%AF%B4",
        notes="Cung ly do voi kk_aikan — channel that, id chua giai.",
    ),
    ChineseMediaSource(
        source_id="tepi_dongman",
        platform="youtube",
        display_name="TePi动漫推荐",
        channel_id="",
        category="AI动画",
        channel_url="https://www.youtube.com/@TePi%E5%8A%A8%E6%BC%AB%E6%8E%A8%E8%8D%90",
        notes="Cung ly do voi kk_aikan — channel that, id chua giai.",
    ),
)


def actionable_sources() -> Tuple[ChineseMediaSource, ...]:
    """Nguon co the poll THAT SU ngay bay gio (co channel_id)."""
    return tuple(s for s in SOURCES if s.channel_id)


#: Cum tu bao hieu QUYEN PHAN PHOI LAI that su duoc cho phep — EN + ZH, cac
#: dang thuong gap tren YouTube/bilibili. Khop THEO CUM TU treen mo ta video
#: (RSS <media:description>), khong phai doan mau cua toan bo trang — mot
#: false positive o day dua rights_mode len REHOST_ALLOWED, nen danh sach
#: nay CHU DICH ngan va cu the, khong doan rong.
_REHOST_MARKERS = (
    "creative commons", "cc by", "cc-by",
    "知识共享", "免费商用", "免费使用", "授权转载", "版权授权",
    "royalty free", "royalty-free", "free to use",
)


def classify_rights(*, description: str, has_real_captions: bool) -> str:
    """Phan loai rights_mode CHO TUNG episode, khong bao gio suy tu channel.

    1. Mo ta co cum tu cho phep phan phoi lai ro rang -> REHOST_ALLOWED.
    2. Co track phu de THAT (khong phai burned-in — xem
       `find_source_captions` trong chinese_media_pipeline.py) -> EMBED_ONLY:
       mot kenh cung cap phu de that thuong duoc quan ly/chinh thuc hon,
       nhung day KHONG PHAI bang chung quyen re-host, chi la mot tin hieu
       yeu de chon EMBED thay vi tham chieu suong.
    3. Mac dinh AN TOAN NHAT: REFERENCE_ONLY — khong sao chep gi ca, chi
       transcript/phu de/dub cua RIENG chung ta.
    """
    text = (description or "").lower()
    if any(marker in text for marker in _REHOST_MARKERS):
        return "REHOST_ALLOWED"
    if has_real_captions:
        return "EMBED_ONLY"
    return "REFERENCE_ONLY"


def source_by_id(source_id: str) -> Optional[ChineseMediaSource]:
    for s in SOURCES:
        if s.source_id == source_id:
            return s
    return None
