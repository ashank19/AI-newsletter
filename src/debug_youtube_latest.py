import os

from dotenv import load_dotenv

from newsletter import load_config, resolve_channel_id, YOUTUBE_RSS, _parse_youtube_feed, _fetch_url_text

import feedparser


def main() -> None:
    load_dotenv()
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    config = load_config(config_path)

    youtube = (config.get("sections") or {}).get("youtube") or {}
    channels = youtube.get("channels") or []
    overrides = youtube.get("channel_id_overrides") or {}
    if not channels:
        print("No youtube.channels found in config.yaml")
        return

    print(f"Channels: {len(channels)}")
    unresolved = []
    for channel_url in channels:
        channel_id = resolve_channel_id(channel_url, overrides)
        if not channel_id:
            print(f"\n- {channel_url}\n  ERROR: could not resolve channel_id")
            unresolved.append(channel_url)
            continue

        feed_url = YOUTUBE_RSS.format(channel_id=channel_id)
        feed = _parse_youtube_feed(feed_url)
        if not feed.entries:
            print(f"\n- {channel_url}\n  channel_id={channel_id}\n  ERROR: no feed entries")
            try:
                raw = _fetch_url_text(feed_url)
                snippet = raw[:300].replace("\n", " ").replace("\r", " ")
                print(f"  feed_snippet={snippet!r}")
            except Exception as e:
                print(f"  feed_fetch_error={e}")
            continue

        latest = feed.entries[0]
        title = latest.get("title", "").strip()
        link = latest.get("link", "").strip()
        published = latest.get("published", "").strip()

        print(f"\n- {channel_url}\n  channel_id={channel_id}\n  latest_title={title}\n  latest_url={link}\n  published={published}")

    if unresolved:
        print("\nUnresolved channel URLs (provide channel IDs for these in config.yaml -> youtube.channel_id_overrides):")
        for u in unresolved:
            print(f"- {u}")


if __name__ == "__main__":
    main()
