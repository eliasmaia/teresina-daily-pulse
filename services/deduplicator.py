import math
import os
from typing import Any
from google import genai

PREFERRED_EMBEDDING_MODELS = (
    "gemini-embedding-001",
    "text-embedding-004",
)

SUMMARY_CHAR_LIMIT = 350

def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _resolve_embedding_model(client: genai.Client) -> str:
    """Descobre automaticamente qual modelo de embedding está habilitado na chave."""
    try:
        available: list[str] = []
        for model in client.models.list():
            actions = (
                getattr(model, "supported_actions", None)
                or getattr(model, "supported_generation_methods", None)
                or []
            )
            if "embedContent" in actions and model.name:
                available.append(model.name.removeprefix("models/"))

        for preferred in PREFERRED_EMBEDDING_MODELS:
            if preferred in available:
                return preferred
        if available:
            return available[0]
    except Exception as exc:
        print(f"   [Aviso] Falha ao listar modelos de embedding ({exc}); usando padrão.")
    return PREFERRED_EMBEDDING_MODELS[0]

def _fetch_embeddings(client: genai.Client, articles: list[dict[str, str]]) -> list[list[float]]:
    embed_model = _resolve_embedding_model(client)
    print(f"   Usando modelo de embeddings: {embed_model}")

    texts_to_embed = [
        f"{item.get('title', '')}. {item.get('summary', '')[:SUMMARY_CHAR_LIMIT]}"
        for item in articles
    ]
    embedding_response = client.models.embed_content(model=embed_model, contents=texts_to_embed)

    return [emb.values for emb in embedding_response.embeddings if emb.values]


def _cluster_articles(articles: list[dict[str, str]], embeddings: list[list[float]], similarity_threshold: float,) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []

    for article, vec in zip(articles, embeddings):
        matched_cluster: dict[str, Any] | None = None
        best_score = 0.0

        for cluster in clusters:
            score = _cosine_similarity(vec, cluster["anchor_vector"])
            if score >= similarity_threshold and score > best_score:
                best_score = score
                matched_cluster = cluster

        source = article.get("source", "Fonte desconhecida")
        title = article.get("title", "")
        summary = article.get("summary", "")

        if matched_cluster is not None:
            if source not in matched_cluster["sources"]:
                matched_cluster["sources"].append(source)
            matched_cluster["extra_details"].append(f"[{source}] {title}: {summary}")
            print(
                f"   [Merge Semântico | score={best_score:.2f}] "
                f"'{title[:45]}...' agrupada com '{matched_cluster['title'][:45]}...'"
            )
        else:
            clusters.append({
                "title": title,
                "link": article.get("link", ""),
                "sources": [source],
                "main_summary": summary,
                "extra_details": [],
                "anchor_vector": vec,
            })

    return clusters


def _format_consolidated_topics(clusters: list[dict[str, Any]], max_topics: int,) -> list[dict[str, str]]:
    if max_topics <= 0:
        return []

    prioritized_clusters = sorted(
        clusters,
        key=lambda cluster: len(cluster.get("sources", [])),
        reverse = True
    )
    
    consolidated: list[dict[str, str]] = []
    for cluster in prioritized_clusters[:max_topics]:
        combined_text = cluster.get("main_summary", "")
        extra_details = cluster.get("extra_details", [])
        if extra_details:
            combined_text += " | Complemento de outras fontes: " + " ; ".join(extra_details)

        consolidated.append({
            "source": " + ".join(cluster.get("sources", [])),
            "title": cluster.get("title", ""),
            "link": cluster.get("link", ""),
            "summary": combined_text,
        })
    return consolidated


def deduplicate_articles(articles: list[dict[str, str]], similarity_threshold: float = 0.82, max_topics: int = 10,) -> list[dict[str, str]]:
    """Agrupa notícias semanticamente semelhantes usando Embeddings."""
    if not articles or max_topics <= 0:
        return []

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("[Aviso] GEMINI_API_KEY ausente; pulando deduplicação por embeddings.")
        return articles[:max_topics]

    try:
        client = genai.Client(api_key=gemini_key)
        embeddings = _fetch_embeddings(client, articles)
        
        if len(embeddings) != len(articles):
            print("[Aviso] Quantidade de embeddings divergente; seguindo sem merge semântico.")
            return articles[:max_topics]

        clusters = _cluster_articles(articles, embeddings, similarity_threshold)
        return _format_consolidated_topics(clusters, max_topics)

    except Exception as exc:
        print(f"   [Aviso] Falha nos embeddings ({exc}); seguindo sem merge semântico.")
        return articles[:max_topics]