import json
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape


def update_podcast_rss(
    episodes_dir: str = "public/episodes",
    feed_path: str = "public/feed.xml",
    base_url: str | None = None,
    owner_email: str | None = None,
) -> str:
    """Gera ou atualiza o feed.xml do podcast a partir dos episódios salvos."""
    resolved_base_url = (
        base_url
        or os.getenv("PODCAST_BASE_URL")
        or "https://eliasmaia.github.io/teresina-daily-pulse"
    ).rstrip("/")

    resolved_owner_email = (
        owner_email
        or os.getenv("PODCAST_OWNER_EMAIL")
        or "seu-email@dominio.com"
    )

    os.makedirs(episodes_dir, exist_ok=True)
    metadata_files = sorted(
        [f for f in os.listdir(episodes_dir) if f.endswith(".json")],
        reverse=True,
    )

    items_xml = []
    for meta_file in metadata_files[:30]:
        meta_path = os.path.join(episodes_dir, meta_file)
        with open(meta_path, "r", encoding="utf-8") as f:
            ep = json.load(f)

        pub_dt = datetime.fromisoformat(ep["published_at"])
        pub_date_rfc = format_datetime(pub_dt.astimezone(timezone.utc))
        mp3_url = f"{resolved_base_url}/episodes/{ep['mp3_filename']}"
        file_size = int(ep.get("file_size_bytes", 0))

        segments_lines = [
            f"- [{s.get('category', 'Geral')}] {s.get('headline', '')} ({s.get('location', 'Teresina')})"
            for s in ep.get("segments", [])
        ]
        description = (
            f"{ep['episode_title']}\n\nDestaques desta edição:\n" + "\n".join(segments_lines)
            if segments_lines
            else ep["episode_title"]
        )

        items_xml.append(f"""    <item>
      <title>{escape(ep['episode_title'])}</title>
      <description>{escape(description)}</description>
      <pubDate>{pub_date_rfc}</pubDate>
      <guid isPermaLink="false">{escape(ep['guid'])}</guid>
      <enclosure url="{escape(mp3_url)}" length="{file_size}" type="audio/mpeg" />
      <itunes:author>Teresina Daily Pulse</itunes:author>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Teresina Daily Pulse</title>
    <link>{escape(resolved_base_url)}</link>
    <language>pt-BR</language>
    <description>Boletim diário automatizado com as principais notícias de Teresina e do Piauí.</description>
    <itunes:author>Elias Moraes</itunes:author>
    <itunes:image href="{escape(resolved_base_url)}/cover.jpg" />
    <itunes:owner>
      <itunes:name>Elias Moraes</itunes:name>
      <itunes:email>{escape(resolved_owner_email)}</itunes:email>
    </itunes:owner>
    <itunes:category text="News">
      <itunes:category text="Daily News" />
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items_xml)}
  </channel>
</rss>
"""

    os.makedirs(os.path.dirname(feed_path), exist_ok=True)
    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(rss_content)

    return feed_path