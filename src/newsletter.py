import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
from urllib.parse import urlparse
import glob

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

from summarizer import summarize_content
from asr import find_audio_for_video, normalize_audio_to_wav, transcribe_audio_to_english_text
from audio_fetcher import fetch_audio_for_video

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


def _channel_name_from_url(channel_url: str) -> str:
    """
    Best-effort channel label derived from the URL path after youtube.com.
    Examples:
    - https://www.youtube.com/ThinkSchool -> ThinkSchool
    - https://www.youtube.com/@ThinkSchool -> ThinkSchool
    - https://www.youtube.com/channel/UC... -> UC...
    - https://www.youtube.com/c/Foo -> Foo
    - https://www.youtube.com/user/Foo -> Foo
    """
    try:
        path = urlparse(channel_url).path.strip("/")
    except Exception:
        path = ""
    if not path:
        return "YouTube"

    # /@Handle
    if path.startswith("@"):
        path = path[1:]

    for prefix in ("channel/", "c/", "user/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    return path.split("/")[0] or "YouTube"


def _channel_id_from_url(url: str) -> str:
    if "/channel/" in url:
        return url.split("/channel/")[-1].split("/")[0]

    # Handle @handle or custom URLs by fetching page and extracting channelId
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code >= 400:
            return ""
        # YouTube HTML often contains either channelId or browseId.
        match = re.search(r'"channelId":"(UC[^"]+)"', response.text)
        if match:
            return match.group(1)
        match = re.search(r'"browseId":"(UC[^"]+)"', response.text)
        if match:
            return match.group(1)
    except requests.RequestException:
        return ""

    return ""


def resolve_channel_id(channel_url: str, overrides: Dict[str, str]) -> str:
    """
    Resolve a YouTube channel URL to a UC... channel ID.

    Supports:
    - /channel/UC...
    - /@handle (and also a user-provided handle without '@', e.g. /ThinkSchool)
    - optional overrides in config.yaml
    """
    if not channel_url:
        return ""

    channel_url = channel_url.strip().rstrip("/")

    # Exact override match
    if overrides and channel_url in overrides and overrides[channel_url]:
        return overrides[channel_url].strip()

    # Try direct
    cid = _channel_id_from_url(channel_url)
    if cid:
        return cid

    # If user provided a handle URL without '@', try adding it.
    # Example: https://www.youtube.com/ThinkSchool -> https://www.youtube.com/@ThinkSchool
    m = re.match(r"^https?://(www\\.)?youtube\\.com/([^/]+)$", channel_url)
    if m:
        slug = m.group(2)
        if slug and not slug.startswith("@") and slug not in {"channel", "c", "user", "feeds", "watch"}:
            with_at = f"https://www.youtube.com/@{slug}"
            if overrides and with_at in overrides and overrides[with_at]:
                return overrides[with_at].strip()
            cid = _channel_id_from_url(with_at)
            if cid:
                return cid

    # If user provided @handle and asked to remove '@', try the no-@ variant too.
    if "/@" in channel_url:
        no_at = channel_url.replace("/@", "/")
        if overrides and no_at in overrides and overrides[no_at]:
            return overrides[no_at].strip()
        cid = _channel_id_from_url(no_at)
        if cid:
            return cid

    return ""


def _fetch_url_text(url: str) -> str:
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.text


def _parse_youtube_feed(feed_url: str) -> Any:
    # feedparser can fail silently under some network/DNS oddities; fetch explicitly.
    try:
        xml = _fetch_url_text(feed_url)
        return feedparser.parse(xml)
    except Exception:
        return feedparser.parse(feed_url)


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
        # Fall back to local audio transcription (if available).
        pass

    try:
        audio_dir = os.getenv(
            "AUDIO_CACHE_DIR",
            os.path.join(os.path.dirname(__file__), "..", ".cache", "audio"),
        )
        audio_path = find_audio_for_video(video_id, audio_dir)
        fetched_by_agent = False
        if not audio_path and os.getenv("ENABLE_AUDIO_FETCHER", "").lower() in {"1", "true", "yes"}:
            # Optional hook: user-provided audio fetcher.
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            audio_path = fetch_audio_for_video(video_url, video_id, audio_dir)
            fetched_by_agent = bool(audio_path)
        if not audio_path:
            return ""

        wav_dir = os.path.join(os.path.dirname(__file__), "..", ".cache", "normalized")
        wav_path = os.path.join(wav_dir, f"{video_id}.wav")
        try:
            normalize_audio_to_wav(audio_path, wav_path)
            return transcribe_audio_to_english_text(wav_path)
        finally:
            # User preference: don't persist fetched audio after a successful/failed run.
            cleanup = os.getenv("CLEANUP_FETCHED_AUDIO", "true").lower() in {"1", "true", "yes"}
            if cleanup and fetched_by_agent:
                # Remove any fetched artifacts for this video from the audio cache + normalized cache.
                for path in glob.glob(os.path.join(audio_dir, f"{video_id}.*")):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
    except Exception as e:
        # Never crash the whole newsletter for one video; just treat it as "no transcript" and keep scanning.
        if os.getenv("DEBUG_YOUTUBE", "").lower() in {"1", "true", "yes"}:
            print(f"[youtube] transcript/audio fallback failed for {video_id}: {e}")
        return ""


def fetch_youtube_items(
    channels: List[str],
    max_items: int,
    channel_id_overrides: Dict[str, str] = None,
    channel_name_overrides: Dict[str, str] = None,
    max_attempts: int = 5,
    max_age_days: int = 3,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    overrides = channel_id_overrides or {}
    name_overrides = channel_name_overrides or {}
    for channel in channels:
        channel_id = resolve_channel_id(channel, overrides)
        if not channel_id:
            continue
        # Prefer a friendly display name override (by channel_id or exact URL), otherwise derive from URL.
        channel_name = (
            (name_overrides.get(channel_id) or "").strip()
            or (name_overrides.get(channel) or "").strip()
            or _channel_name_from_url(channel)
        )
        feed_url = YOUTUBE_RSS.format(channel_id=channel_id)
        feed = _parse_youtube_feed(feed_url)
        if not feed.entries:
            continue
        entry = _pick_entry_with_transcript(feed.entries, max_attempts=max_attempts, max_age_days=max_age_days)
        if not entry:
            continue
        video_id = _extract_video_id(entry)
        transcript_text = _fetch_transcript_text(video_id)
        summary = summarize_content(transcript_text[:30000], "YouTube video content", bullet_count=5) if transcript_text else ""
        summary = _normalize_summary(summary)
        items.append({
            "channel_name": channel_name,
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": "YouTube",
            "video_id": video_id,
            "summary": summary,
        })
    return items[:max_items]


def fetch_google_news(query: str, max_items: int, max_age_days: int = 2) -> List[Dict[str, Any]]:
    url = GOOGLE_NEWS_RSS.format(query=requests.utils.quote(query))
    feed = feedparser.parse(url)
    results = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    for entry in feed.entries:
        published = entry.get("published_parsed")
        if published:
            published_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
            if published_dt < cutoff:
                continue
        results.append(
            {
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": "Google News",
            }
        )
        if len(results) >= max_items:
            break
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
    lines = [line.strip() for line in summary.splitlines() if line.strip()]
    if not lines:
        return ""

    cleaned: List[str] = []
    for line in lines:
        # Drop common LLM preambles like: "Here are the N bullet points..."
        low = line.lower()
        if "here are" in low and "bullet" in low:
            continue

        # Keep only actual bullets (or numbered items) to avoid preamble text leaking into emails.
        if line.startswith(("-", "•", "*")):
            text = line.lstrip("-•* ").strip()
            if text:
                cleaned.append(f"- {text}")
            continue

        m = re.match(r"^\\d+\\s*[\\).:-]\\s*(.+)$", line)
        if m:
            text = m.group(1).strip()
            if text:
                cleaned.append(f"- {text}")
            continue

    return "\n".join(cleaned).strip()


def _pick_entry_with_transcript(entries: List[Any], max_attempts: int = 5, max_age_days: int = 3) -> Any:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    attempts = 0
    for entry in entries:
        published = entry.get("published_parsed")
        if published:
            published_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
            if published_dt < cutoff:
                # Skip older videos; if the feed is unsorted we don't want to stop early.
                continue
        video_id = _extract_video_id(entry)
        if not video_id:
            continue

        # Count attempts only for candidates within the age cutoff.
        if attempts >= max_attempts:
            break
        attempts += 1

        transcript_text = _fetch_transcript_text(video_id)
        if transcript_text:
            return entry
    return None


def render_text(sections: Dict[str, Dict[str, Any]]) -> str:
    lines = []
    lines.append("Daily Newsletter")
    lines.append("")

    for section in sections.values():
        if not section["items"]:
            continue
        lines.append(section["title"])
        for item in section["items"]:
            # For YouTube, show "<channel> - <video title>" (no extra labels).
            if item.get("source") == "YouTube":
                channel = (item.get("channel_name") or "").strip()
                title = (item.get("title") or "").strip()
                if channel and title:
                    lines.append(f"{channel} - {title}")
                else:
                    lines.append(title or channel)
            else:
                lines.append(f"- {item.get('title', '')}")

            if item.get("summary"):
                for bullet in item["summary"].splitlines():
                    lines.append(f"  {bullet}")
        lines.append("")

    return "\n".join(lines)


def render_html(sections: Dict[str, Dict[str, Any]]) -> str:
    parts = []
    parts.append("<h2>Daily Newsletter</h2>")

    for section in sections.values():
        if not section["items"]:
            continue
        parts.append(f"<h3>{section['title']}</h3>")
        parts.append("<ul>")
        for item in section["items"]:
            title = item.get("title") or "Untitled"
            if item.get("source") == "YouTube":
                channel = (item.get("channel_name") or "").strip()
                if channel:
                    title = f"{channel} - {title}"
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
            overrides = meta.get("channel_id_overrides", {}) or {}
            name_overrides = meta.get("channel_name_overrides", {}) or {}
            yt_attempts = int(meta.get("max_attempts", 5))
            yt_age_days = int(meta.get("max_age_days", 3))
            items = fetch_youtube_items(
                channels,
                max_items,
                channel_id_overrides=overrides,
                channel_name_overrides=name_overrides,
                max_attempts=yt_attempts,
                max_age_days=yt_age_days,
            )
        elif key == "hacker_news":
            query = meta.get("query", "AI")
            items = fetch_hacker_news(query, max_items)
        elif key.startswith("google_news"):
            query = meta.get("query", "AI")
            gn_age_days = int(meta.get("max_age_days", 2))
            items = fetch_google_news(query, max_items, max_age_days=gn_age_days)
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

    return sections
