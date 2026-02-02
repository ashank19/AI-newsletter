import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

from summarizer import summarize_content

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
YOUTUBE_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
HN_ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _clean_text(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value)
    return text.strip()


def _channel_id_from_url(url: str) -> str:
    if "/channel/" in url:
        return url.split("/channel/")[-1].split("/")[0]

    # Handle @handle or custom URLs by fetching page and extracting channelId
    try:
        response = requests.get(url, timeout=20)
        if response.status_code >= 400:
            return ""
        match = re.search(r'"channelId":"(UC[^"]+)"', response.text)
        if match:
            return match.group(1)
    except requests.RequestException:
        return ""

    return ""


def _extract_video_id(entry: Any) -> str:
    video_id = entry.get("yt_videoid")
    if video_id:
        return video_id
    link = entry.get("link", "")
    match = re.search(r"v=([\\w-]+)", link)
    if match:
        return match.group(1)
    return ""


def _fetch_transcript_text(video_id: str) -> str:
    if not video_id:
        return ""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(chunk.get("text", "") for chunk in transcript)
    except (TranscriptsDisabled, NoTranscriptFound, Exception):
        return ""


def fetch_youtube_items(channels: List[str], max_items: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for channel in channels:
        channel_id = _channel_id_from_url(channel)
        if not channel_id:
            continue
        feed_url = YOUTUBE_RSS.format(channel_id=channel_id)
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            continue
        entry = _pick_entry_with_transcript(feed.entries, max_attempts=5, max_age_days=3)
        if not entry:
            continue
        video_id = _extract_video_id(entry)
        transcript_text = _fetch_transcript_text(video_id)
        summary = summarize_content(transcript_text[:30000], "YouTube video content", bullet_count=5) if transcript_text else ""
        summary = _normalize_summary(summary)
        items.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": "YouTube",
            "video_id": video_id,
            "summary": summary,
        })
    return items[:max_items]


def fetch_google_news(query: str, max_items: int) -> List[Dict[str, Any]]:
    url = GOOGLE_NEWS_RSS.format(query=requests.utils.quote(query))
    feed = feedparser.parse(url)
    results = []
    for entry in feed.entries[:max_items]:
        results.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": "Google News",
        })
    return results


def fetch_hacker_news(query: str, max_items: int) -> List[Dict[str, Any]]:
    results = []
    hits_per_page = max(max_items, 10)
    params = {
        "query": query,
        "tags": "story",
        "hitsPerPage": hits_per_page,
    }
    response = requests.get(HN_ALGOLIA, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    for hit in data.get("hits", []):
        if len(results) >= max_items:
            break
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        article_text = fetch_article_text(url)
        if not article_text:
            continue
        summary = summarize_content(article_text[:12000], "Hacker News linked article", bullet_count=3)
        summary = _normalize_summary(summary)
        if not summary:
            continue
        results.append({
            "title": hit.get("title", ""),
            "url": url,
            "published": hit.get("created_at", ""),
            "source": "Hacker News",
            "summary": summary,
        })

    return results[:max_items]


def fetch_moltbook(feed_url: str, max_items: int) -> List[Dict[str, Any]]:
    if not feed_url:
        return []

    feed = feedparser.parse(feed_url)
    if feed.entries:
        results = []
        for entry in feed.entries[:max_items]:
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": "Moltbook",
            })
        return results

    # Fallback: try JSON list if RSS is not available
    try:
        response = requests.get(feed_url, timeout=20)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            results = []
            for item in data[:max_items]:
                results.append({
                    "title": _clean_text(str(item.get("title", ""))),
                    "url": item.get("url") or item.get("link") or "",
                    "published": item.get("published") or item.get("created_at") or "",
                    "source": "Moltbook",
                })
            return results
    except Exception:
        return []

    return []


def fetch_article_text(url: str) -> str:
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code >= 400:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(t.get_text(separator=" ", strip=True) for t in soup.find_all("p"))
        return _clean_text(text)
    except requests.RequestException:
        return ""


def _normalize_summary(summary: str) -> str:
    if not summary:
        return ""
    bullets = [line.strip() for line in summary.splitlines() if line.strip()]
    if not bullets:
        return ""
    cleaned = []
    for line in bullets:
        if not line.startswith("-"):
            line = f"- {line.lstrip('- ').strip()}"
        cleaned.append(line)
    return "\n".join(cleaned)


def _pick_entry_with_transcript(entries: List[Any], max_attempts: int = 5, max_age_days: int = 3) -> Any:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    attempts = 0
    for entry in entries:
        if attempts >= max_attempts:
            break
        attempts += 1
        published = entry.get("published_parsed")
        if published:
            published_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
            if published_dt < cutoff:
                break
        video_id = _extract_video_id(entry)
        if not video_id:
            continue
        transcript_text = _fetch_transcript_text(video_id)
        if transcript_text:
            return entry
    return None


def render_text(sections: Dict[str, Dict[str, Any]]) -> str:
    lines = []
    lines.append("Daily Newsletter")
    lines.append("")

    for section in sections.values():
        lines.append(section["title"])
        if not section["items"]:
            continue
        for item in section["items"]:
            lines.append(f"- {item['title']}")
            if item.get("summary"):
                for bullet in item["summary"].splitlines():
                    lines.append(f"  {bullet}")
        lines.append("")

    return "\n".join(lines)


def render_html(sections: Dict[str, Dict[str, Any]]) -> str:
    parts = []
    parts.append("<h2>Daily Newsletter</h2>")

    for section in sections.values():
        parts.append(f"<h3>{section['title']}</h3>")
        if not section["items"]:
            continue
        parts.append("<ul>")
        for item in section["items"]:
            title = item.get("title") or "Untitled"
            summary = item.get("summary")
            parts.append(f"<li><strong>{title}</strong>")
            if summary:
                parts.append("<ul>")
                for bullet in summary.splitlines():
                    parts.append(f"<li>{bullet.lstrip('- ').strip()}</li>")
                parts.append("</ul>")
            parts.append("</li>")
        parts.append("</ul>")

    return "\n".join(parts)


def build_sections(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    sections: Dict[str, Dict[str, Any]] = {}
    section_config = config.get("sections", {})

    for key, meta in section_config.items():
        sections[key] = {"title": meta.get("title", key), "items": []}
        max_items = int(meta.get("max_items", 5))
        if max_items <= 0:
            continue

        if key == "youtube":
            channels = meta.get("channels", [])
            items = fetch_youtube_items(channels, max_items)
        elif key == "hacker_news":
            query = meta.get("query", "AI")
            items = fetch_hacker_news(query, max_items)
        elif key.startswith("google_news"):
            query = meta.get("query", "AI")
            items = fetch_google_news(query, max_items)
            # Summarize combined headlines into 3 bullets (no links in email)
            combined = " ".join(item.get("title", "") for item in items)
            if combined:
                summary = summarize_content(combined, f"{meta.get('title', 'News')} headlines", bullet_count=3)
                summary = _normalize_summary(summary)
                items = [{
                    "title": meta.get("title", "News"),
                    "summary": summary,
                }]
        else:
            items = []

        sections[key]["items"] = items

    # If no recent YouTube items, keep Google News sections; otherwise drop them.
    youtube_items = sections.get("youtube", {}).get("items", [])
    if youtube_items:
        for key in list(sections.keys()):
            if key.startswith("google_news"):
                sections.pop(key, None)

    return sections
