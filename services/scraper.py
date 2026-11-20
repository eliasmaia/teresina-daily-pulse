import re
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests
from bs4 import BeautifulSoup

# Padrão típico de URLs de matérias do Cidade Verde (ex: /ultimas/466502/... ou /noticias/123456/...)
ARTICLE_URL_PATTERN = re.compile(r"cidadeverde\.com/(?:ultimas|noticias|economia|esportes|cidades|politica)/\d+/")


def _normalize_url(href: str) -> str:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return ""
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"https://cidadeverde.com{href}"
    return href


def _fetch_article_body(url: str) -> str:
    """Acessa a página da matéria e extrai os primeiros parágrafos com o contexto completo."""
    try:
        resp = requests.get(url, impersonate="chrome", timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        content_div = (
            soup.find("div", class_="texto-noticia")
            or soup.find("div", class_="materia-conteudo")
            or soup.find("article")
            or soup.body
        )

        paragraphs = []
        for p in content_div.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) > 50 and not text.lower().startswith(("foto:", "crédito:", "leia também", "sigam")):
                paragraphs.append(text)
            if len(paragraphs) >= 3:
                break

        return " ".join(paragraphs)
    except Exception as exc:
        print(f"   [Aviso] Falha ao ler corpo de {url}: {exc}")
        return ""


def get_cidade_verde_news(limit: int = 11):
    """
    Raspa a manchete principal, o slideshow e a lista lateral de destaques do Cidade Verde,
    e busca o corpo de cada matéria em paralelo.
    """
    url = "https://cidadeverde.com/"

    try:
        response = requests.get(url, impersonate="chrome", timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        raw_items = []

        # 1. Manchete principal (h2.manchete)
        for h2 in soup.find_all("h2", class_="manchete"):
            a = h2.find("a", href=True)
            if a:
                raw_items.append({
                    "title": a.get_text(" ", strip=True),
                    "link": _normalize_url(a["href"]),
                    "headline_summary": a.get("title", "").strip(),
                })

        # 2. Slideshow e blocos com div.caption
        for li in soup.find_all("li"):
            caption = li.find("div", class_="caption")
            if caption:
                a_tag = caption.find("a", href=True)
                if a_tag:
                    raw_items.append({
                        "title": a_tag.get_text(" ", strip=True),
                        "link": _normalize_url(a_tag["href"]),
                        "headline_summary": a_tag.get("title", "").strip(),
                    })

        # 3. Lista lateral e demais destaques da capa (links de matérias com título relevante)
        for a_tag in soup.find_all("a", href=True):
            link = _normalize_url(a_tag["href"])
            title = a_tag.get_text(" ", strip=True)
            if ARTICLE_URL_PATTERN.search(link) and len(title) >= 25:
                raw_items.append({
                    "title": title,
                    "link": link,
                    "headline_summary": a_tag.get("title", "").strip(),
                })

        # 4. Deduplica mantendo a ordem de importância da capa
        candidates = []
        seen_links = set()
        for item in raw_items:
            link = item["link"]
            if not link or link in seen_links or len(item["title"]) < 20:
                continue
            seen_links.add(link)
            candidates.append(item)
            if len(candidates) >= limit:
                break

        print(f"   Buscando conteúdo completo de {len(candidates)} matérias em paralelo...")

        # 5. Busca o texto das matérias simultaneamente
        with ThreadPoolExecutor(max_workers=5) as executor:
            bodies = list(executor.map(lambda x: _fetch_article_body(x["link"]), candidates))

        enriched_news = []
        for item, body in zip(candidates, bodies):
            enriched_news.append({
                "source": "Cidade Verde",
                "title": item["title"],
                "link": item["link"],
                "summary": body if body else item["headline_summary"],
            })

        return enriched_news

    except Exception as e:
        print(f"Error scraping Cidade Verde: {e}")
        return []


if __name__ == "__main__":
    articles = get_cidade_verde_news(limit=11)
    print(f"\nTotal coletado: {len(articles)} notícias.\n")
    for i, article in enumerate(articles, 1):
        print(f"[{i}] {article['title']}")
        print(f"    Link: {article['link']}")
        print(f"    Resumo: {article['summary'][:160]}...\n")