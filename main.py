import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from services.deduplicator import deduplicate_articles
from services.rss_generator import update_podcast_rss
from services.scraper import get_all_teresina_news
from services.summarizer import generate_structured_bulletin
from services.tts import generate_audio_mp3

app = FastAPI(title="Teresina Daily Pulse", version="2.0.0")

os.makedirs("public/episodes", exist_ok=True)
app.mount("/public", StaticFiles(directory="public"), name="public")


def execute_daily_pipeline() -> dict:
    tz = ZoneInfo("America/Fortaleza")
    now = datetime.now(tz)
    date_slug = now.strftime("%Y-%m-%d")

    raw_news = get_all_teresina_news()
    if not raw_news:
        raise RuntimeError("Nenhuma notícia foi coletada nas fontes configuradas.")

    unique_topics = deduplicate_articles(
        raw_news,
        similarity_threshold=0.82,
        max_topics=12,
    )
    bulletin = generate_structured_bulletin(unique_topics)

    mp3_filename = f"teresina-daily-{date_slug}.mp3"
    mp3_path = os.path.join("public/episodes", mp3_filename)
    generate_audio_mp3(bulletin.audio_script, mp3_path)

    meta_path = os.path.join("public/episodes", f"teresina-daily-{date_slug}.json")
    episode_meta = {
        "guid": f"teresina-daily-{date_slug}",
        "published_at": now.isoformat(),
        "episode_title": bulletin.episode_title,
        "mp3_filename": mp3_filename,
        "file_size_bytes": os.path.getsize(mp3_path),
        "audio_script": bulletin.audio_script,
        "segments": [s.model_dump() for s in bulletin.segments],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(episode_meta, f, ensure_ascii=False, indent=2)

    feed_path = update_podcast_rss()

    return {
        "status": "success",
        "episode_title": bulletin.episode_title,
        "topics_count": len(bulletin.segments),
        "mp3_path": mp3_path,
        "feed_path": feed_path,
    }


@app.get("/")
def read_root():
    return {"status": "online", "service": "Teresina Daily Pulse"}


@app.post("/pipeline/run")
def run_pipeline():
    return execute_daily_pipeline()


if __name__ == "__main__":
    result = execute_daily_pipeline()
    print("\nPipeline concluído com sucesso:")
    print(json.dumps(result, indent=2, ensure_ascii=False))