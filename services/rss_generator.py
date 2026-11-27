import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

MAX_FEED_EPISODES = 30
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
DEFAULT_BASE_URL = "https://eliasmaia.github.io/teresina-daily-pulse"
DEFAULT_OWNER_EMAIL = "seu-email@dominio.com"

def _format_pub_date(iso_timestamp: str) -> str:
    parsed_dt = datetime.fromisoformat(iso_timestamp)
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    return format_datetime(parsed_dt.astimezone(timezone.utc))

def _build_episode_description(episode: dict[str, Any]) -> str:
    title = str(episode.get("episode_title", ""))
    segments = episode.get("segments", [])

    if not segments:
        return title

    highlights = [
        f"- [{seg.get('category', 'Geral')}] {seg.get('headline', '')} ({seg.get('location', 'Teresina')})"
        for seg in segments
    ]
    return f"{title}\n\nDestaques desta edição:\n" + "\n".join(highlights)

def _load_recent_episodes(episodes_dir: Path, limit: int) -> list[dict[str, Any]]:
    episodes_dir.mkdir(parents=True, exist_ok=True)
    metadata_files = sorted(
        (path for path in episodes_dir.iterdir() if path.is_file() and path.suffix == ".json"),
         key=lambda path: path.name,
         reverse=True
    )

    episodes: list[dict[str, Any]] = []
    for meta_path in metadata_files[:limit]:
        with meta_path.open("r", encoding="utf-8") as file:
            episodes.append(json.load(file))
    return episodes

def _append_episode_item(channel: ET.Element, episode: dict[str, Any], base_url: str) -> None:
    item = ET.SubElement(channel, "item")

    ET.SubElement(item, "item").text = str(episode.get("episode_title", ""))
    ET.SubElement(item, "description").text = _build_episode_description(episode)
    ET.SubElement(item, "pubDate").text = _format_pub_date(episode['published_at'])

    guid = ET.SubElement(item, "guid", isPermaLink="false")
    guid.text = str(episode.get("guid", episode.get("mp3_filename", "")))

    mp3_url = f"{base_url}/episode/{episode['mp3_filename']}"
    file_size = str(int(episode.get("file_size_bytes", 0)))
    ET.SubElement(item, "enclosure", url=mp3_url, length=file_size, type="audio/mpeg")

    ET.SubElement(item, "itunes:author").text = "Teresina Daily Pulse"
    ET.SubElement(item, "itunes:explicit").text = "false"

def _build_rss_tree(episodes: list[dict[str, Any]], base_url: str, owner_email: str) -> ET.ElementTree:
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:itunes": ITUNES_NS})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Teresina Daily Pulse"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "language").text = "pt-BR"
    ET.SubElement(channel, "description").text = ("Boletim diário automatizado com as principais noticias de Teresina e do Piauí.")
    ET.SubElement(channel, "itunes:author").text = "Elias Moraes"
    ET.SubElement(channel, "itunes:image", href=f"{base_url}/cover.jpg")

    owner = ET.SubElement(channel, "itunes:owner")
    ET.SubElement(owner, "itunes:name").text = "Elias Moraes"
    ET.SubElement(owner, "itunes:email").text = owner_email

    category = ET.SubElement(channel, "itunes:category", text="News")
    ET.SubElement(category, "itunes:category", text="Daily News")
    ET.SubElement(channel, "itunes:explicit").text = "false"

    for episode in episodes:
        _append_episode_item(channel, episode, base_url)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    return tree

def update_podcast_rss(episodes_dir: str = "public/episodes", feed_path: str = "public/feed.xml", base_url: str | None = None, owner_email: str | None = None,) -> str:
    """Gera ou atualiza o feed.xml do podcast a partir dos episódios salvos"""
    resolved_base_url = (
        base_url
        or os.getenv("PODCAST_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")

    resolved_owner_email = (
        owner_email
        or os.getenv("PODCAST_OWNER_EMAIL")
        or DEFAULT_OWNER_EMAIL
    )

    episodes = _load_recent_episodes(Path(episodes_dir), MAX_FEED_EPISODES)
    rss_tree = _build_rss_tree(episodes, resolved_base_url, resolved_owner_email)

    target_feed = Path(feed_path)
    target_feed.parent.mkdir(parents=True, exist_ok=True)
    rss_tree.write(target_feed, encoding="utf-8", xml_declaration=True)

    return str(target_feed)

