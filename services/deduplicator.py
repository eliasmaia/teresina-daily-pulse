import math
import os
from typing import Dict, List
from dotenv import load_dotenv
from google import genai

load_dotenv()

PREFERRED_EMBEDDING_MODELS = [
    "gemini-embedding-001",
    "text-embedding-004",
]


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _resolve_embedding_model(client: genai.Client) -> str:
    """Descobre automaticamente qual modelo de embedding está habilitado na chave."""
    try:
        available = [
            m.name.replace("models/", "")
            for m in client.models.list()
            if "embedContent" in (getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or [])
        ]
        for pref in PREFERRED_EMBEDDING_MODELS:
            if pref in available:
                return pref
        if available:
            return available[0]
    except Exception:
        pass
    return PREFERRED_EMBEDDING_MODELS[0]


def deduplicate_articles(
    articles: List[Dict[str, str]],
    similarity_threshold: float = 0.82,
    max_topics: int = 10,
) -> List[Dict[str, str]]:
    """
    Agrupa notícias semanticamente semelhantes usando Embeddings.
    """
    if not articles:
        return []

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("   [Aviso] GEMINI_API_KEY ausente; pulando deduplicação por embeddings.")
        return articles[:max_topics]

    try:
        client = genai.Client(api_key=gemini_key)
        embed_model = _resolve_embedding_model(client)
        print(f"   Usando modelo de embeddings: {embed_model}")

        texts_to_embed = [
            f"{item['title']}. {item.get('summary', '')[:350]}" for item in articles
        ]

        result = client.models.embed_content(
            model=embed_model,
            contents=texts_to_embed,
        )
        embeddings = [emb.values for emb in result.embeddings]

        clusters: List[Dict] = []

        for article, vec in zip(articles, embeddings):
            matched_cluster = None
            best_score = 0.0

            for cluster in clusters:
                score = _cosine_similarity(vec, cluster["centroid"])
                if score >= similarity_threshold and score > best_score:
                    best_score = score
                    matched_cluster = cluster

            if matched_cluster:
                if article["source"] not in matched_cluster["sources"]:
                    matched_cluster["sources"].append(article["source"])
                matched_cluster["extra_details"].append(
                    f"[{article['source']}] {article['title']}: {article.get('summary', '')}"
                )
                print(
                    f"   [Merge Semântico | score={best_score:.2f}] "
                    f"'{article['title'][:45]}...' agrupada com '{matched_cluster['title'][:45]}...'"
                )
            else:
                clusters.append({
                    "title": article["title"],
                    "link": article["link"],
                    "sources": [article["source"]],
                    "main_summary": article.get("summary", ""),
                    "extra_details": [],
                    "centroid": vec,
                })

        consolidated = []
        for c in clusters[:max_topics]:
            combined_text = c["main_summary"]
            if c["extra_details"]:
                combined_text += " | Complemento de outras fontes: " + " ".join(c["extra_details"])

            consolidated.append({
                "source": " + ".join(c["sources"]),
                "title": c["title"],
                "link": c["link"],
                "summary": combined_text,
            })

        return consolidated

    except Exception as exc:
        print(f"   [Aviso] Falha nos embeddings ({exc}); seguindo sem merge semântico.")
        return articles[:max_topics]