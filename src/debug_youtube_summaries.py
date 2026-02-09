import os
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

from newsletter import (
    load_config,
    resolve_channel_id,
    YOUTUBE_RSS,
    _parse_youtube_feed,
    _extract_video_id,
    _fetch_transcript_text,
    summarize_content,
    _normalize_summary,
    _fetch_url_text,
)


def _published_dt(entry) -> datetime | None:
    published = entry.get("published_parsed")
    if not published:
        return None
    return datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)


def main() -> None:
    load_dotenv()
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    config = load_config(config_path)

    youtube = (config.get("sections") or {}).get("youtube") or {}
    channels = youtube.get("channels") or []
    overrides = youtube.get("channel_id_overrides") or {}
    max_items = int(youtube.get("max_items", 5))
    max_attempts = int(youtube.get("max_attempts", 5))
    max_age_days = int(youtube.get("max_age_days", 3))

    if not channels:
        print("No youtube.channels found in config.yaml")
        return

    enable_audio_fetcher = os.getenv("ENABLE_AUDIO_FETCHER", "").lower() in {"1", "true", "yes"}
    audio_cache_dir = os.getenv("AUDIO_CACHE_DIR", ".cache/audio")
    print(f"ENABLE_AUDIO_FETCHER={enable_audio_fetcher} AUDIO_CACHE_DIR={audio_cache_dir}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    summaries = []

    for channel_url in channels:
        channel_id = resolve_channel_id(channel_url, overrides)
        if not channel_id:
            print(f"\n- {channel_url}\n  ERROR: could not resolve channel_id")
            continue

        feed_url = YOUTUBE_RSS.format(channel_id=channel_id)
        feed = _parse_youtube_feed(feed_url)
        if not feed.entries:
            print(f"\n- {channel_url}\n  channel_id={channel_id}\n  ERROR: no feed entries")
            try:
                raw = _fetch_url_text(feed_url)
                snippet = raw[:200].replace("\n", " ").replace("\r", " ")
                print(f"  feed_snippet={snippet!r}")
            except Exception as e:
                print(f"  feed_fetch_error={e}")
            continue

        print(f"\n- {channel_url}\n  channel_id={channel_id}")

        picked = None
        for idx, entry in enumerate(feed.entries[:max_attempts], start=1):
            vid = _extract_video_id(entry)
            pub = _published_dt(entry)
            pub_str = pub.isoformat() if pub else "(unknown)"
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()

            if pub and pub < cutoff:
                print(f"  skip: entry {idx} is older than cutoff ({pub_str})")
                continue

            print(f"  candidate {idx}: video_id={vid} published={pub_str}")
            print(f"    title={title}")

            transcript = _fetch_transcript_text(vid)
            if transcript:
                print(f"    transcript_chars={len(transcript)}")
                picked = (title, vid, transcript)
                break
            else:
                print("    no transcript/audio available")

        if not picked:
            continue

        title, vid, transcript = picked
        summary = summarize_content(transcript[:30000], "YouTube video content", bullet_count=5)
        summary = _normalize_summary(summary)
        if not summary:
            print("    summary empty (unexpected)")
            continue

        summaries.append({"title": title, "video_id": vid, "summary": summary, "channel_url": channel_url})
        if len(summaries) >= max_items:
            break

    if not summaries:
        print("\nNo YouTube items summarized (this means: no video within max_age_days had captions, and no audio fallback was available).")
        return

    print("\n=== SUMMARIES ===")
    for item in summaries:
        print("\n" + (item.get("title") or "Untitled"))
        print(f"video_id={item['video_id']}")
        print(item["summary"])


if __name__ == "__main__":
    main()
