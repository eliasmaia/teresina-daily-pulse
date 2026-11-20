import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
from bs4 import BeautifulSoup
from curl_cffi import requests

CV_URL_PATTERN = re.compile(
    r"cidadeverde\.com/(?:ultimas|noticias|economia|esportes|cidades|politica)/\d+/"
)
G1_URL_PATTERN = re.compile(
    r"g1\.globo\.com/pi/piaui/noticia/\d{4}/\d{2}/\d{2}/"
)
PMT_URL_PATTERN = re.compile(
    r"pmt\.pi\.gov\.br/\d{4}/\d{2}/\d{2}/"
)
GOV_PI_URL_PATTERN = re.compile(
    r"pi\.gov\.br/[^\"'?\s#]+(?:/\d{4}/|/noticia|/noticias|/agencia)"
)


def _normalize_url(href: str, base_url: str) -> str:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return ""
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"{base_url.rstrip('/')}{href}"
    return href


def _fetch_article_body(url: str) -> str:
    """Acessa a página da matéria e extrai os primeiros parágrafos com o contexto completo."""
    try:
        resp = requests.get(url, impersonate="chrome", timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        content_div = (
            soup.find("div", class_="texto-noticia")       # Cidade Verde
            or soup.find("div", class_="mc-article-body")  # G1 Piauí
            or soup.find("div", class_="entry-content")    # WordPress (PMT / Gov PI)
            or soup.find("article")
            or soup.body
        )

        paragraphs = []
        for p in content_div.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) > 45 and not text.lower().startswith(
                ("foto:", "crédito:", "leia também", "sigam", "veja também", "assista")
            ):
                paragraphs.append(text)
            if len(paragraphs) >= 3:
                break

        return " ".join(paragraphs)[:650]
    except Exception as exc:
        print(f"   [Aviso] Falha ao ler corpo de {url}: {exc}")
        return ""


def _enrich_candidates(candidates: List[Dict[str, str]], source_name: str) -> List[Dict[str, str]]:
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=5) as executor:
        bodies = list(executor.map(lambda x: _fetch_article_body(x["link"]), candidates))

    return [
        {
            "source": source_name,
            "title": item["title"],
            "link": item["link"],
            "summary": body if body else item.get("headline_summary", ""),
        }
        for item, body in zip(candidates, bodies)
    ]


def get_cidade_verde_news(limit: int = 8) -> List[Dict[str, str]]:
    url = "https://cidadeverde.com/"
    try:
        resp = requests.get(url, impersonate="chrome", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        raw_items = []

        for h2 in soup.find_all("h2", class_="manchete"):
            a = h2.find("a", href=True)
            if a:
                raw_items.append({
                    "title": a.get_text(" ", strip=True),
                    "link": _normalize_url(a["href"], url),
                    "headline_summary": a.get("title", "").strip(),
                })

        for li in soup.find_all("li"):
            caption = li.find("div", class_="caption")
            if caption and (a_tag := caption.find("a", href=True)):
                raw_items.append({
                    "title": a_tag.get_text(" ", strip=True),
                    "link": _normalize_url(a_tag["href"], url),
                    "headline_summary": a_tag.get("title", "").strip(),
                })

        for a_tag in soup.find_all("a", href=True):
            link = _normalize_url(a_tag["href"], url)
            title = a_tag.get_text(" ", strip=True)
            if CV_URL_PATTERN.search(link) and len(title) >= 25:
                raw_items.append({
                    "title": title,
                    "link": link,
                    "headline_summary": a_tag.get("title", "").strip(),
                })

        candidates, seen = [], set()
        for item in raw_items:
            if item["link"] and item["link"] not in seen and len(item["title"]) >= 20:
                seen.add(item["link"])
                candidates.append(item)
                if len(candidates) >= limit:
                    break

        return _enrich_candidates(candidates, "Cidade Verde")
    except Exception as exc:
        print(f"   [Erro] Cidade Verde: {exc}")
        return []


def get_g1_piaui_news(limit: int = 8) -> List[Dict[str, str]]:
    url = "https://g1.globo.com/pi/piaui/"
    try:
        resp = requests.get(url, impersonate="chrome", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        candidates, seen = [], set()
        for a_tag in soup.find_all("a", href=True):
            link = _normalize_url(a_tag["href"], "https://g1.globo.com")
            title = a_tag.get_text(" ", strip=True)
            if G1_URL_PATTERN.search(link) and link not in seen and len(title) >= 25:
                seen.add(link)
                candidates.append({"title": title, "link": link, "headline_summary": ""})
                if len(candidates) >= limit:
                    break

        return _enrich_candidates(candidates, "G1 Piauí")
    except Exception as exc:
        print(f"   [Erro] G1 Piauí: {exc}")
        return []

CLUBE_NEWS_URL_PATTERN = re.compile(
    r"(?:portalclubenews|clubenews)\.(?:com|com\.br)/[^\"'?\s#]+/\d+/"
)


def get_clube_news(limit: int = 6) -> List[Dict[str, str]]:
    url = "https://www.portalclubenews.com/"
    try:
        resp = requests.get(url, impersonate="chrome", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        candidates, seen = [], set()
        for a_tag in soup.find_all("a", href=True):
            link = _normalize_url(a_tag["href"], url)
            title = a_tag.get_text(" ", strip=True)
            if CLUBE_NEWS_URL_PATTERN.search(link) and link not in seen and len(title) >= 25:
                seen.add(link)
                candidates.append({"title": title, "link": link, "headline_summary": ""})
                if len(candidates) >= limit:
                    break

        return _enrich_candidates(candidates, "Portal Clube News")
    except Exception as exc:
        print(f"   [Aviso] Portal Clube News indisponível ({exc}); seguindo com os demais portais.")
        return []


def _fetch_wp_or_rss(
    source_name: str,
    api_url: str,
    rss_url: str,
    base_url: str,
    url_pattern: re.Pattern,
    limit: int,
) -> List[Dict[str, str]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, application/xml, text/xml, text/html",
    }

    # 1. Tenta REST API do WordPress
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            posts = json.loads(resp.read().decode("utf-8", errors="ignore"))

        results = []
        for post in posts:
            title = BeautifulSoup(post.get("title", {}).get("rendered", ""), "html.parser").get_text(" ", strip=True)
            raw_html = post.get("content", {}).get("rendered") or post.get("excerpt", {}).get("rendered", "")
            body_soup = BeautifulSoup(raw_html, "html.parser")
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in body_soup.find_all("p")
                if len(p.get_text(" ", strip=True)) > 40
            ]
            summary = " ".join(paragraphs[:3])[:600]
            if title and post.get("link"):
                results.append({
                    "source": source_name,
                    "title": title,
                    "link": post["link"],
                    "summary": summary,
                })
        if results:
            return results
    except Exception:
        pass

    # 2. Tenta Feed RSS oficial
    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        results = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc_html = item.findtext("description") or ""
            summary = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
            if title and link:
                results.append({
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "summary": summary[:600],
                })
        if results:
            return results
    except Exception:
        pass

    # 3. Fallback HTML leve
    try:
        req = urllib.request.Request(base_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        candidates, seen = [], set()
        for a_tag in soup.find_all("a", href=True):
            link = _normalize_url(a_tag["href"], base_url)
            title = a_tag.get_text(" ", strip=True)
            if url_pattern.search(link) and link not in seen and len(title) >= 25:
                seen.add(link)
                candidates.append({"title": title, "link": link, "headline_summary": ""})
                if len(candidates) >= limit:
                    break

        return _enrich_candidates(candidates, source_name)
    except Exception as exc:
        print(f"   [Aviso] {source_name} indisponível ({exc}); seguindo com os demais portais.")
        return []


def get_pmt_news(limit: int = 5) -> List[Dict[str, str]]:
    return _fetch_wp_or_rss(
        source_name="Prefeitura de Teresina",
        api_url=f"https://pmt.pi.gov.br/wp-json/wp/v2/posts?per_page={limit}&_fields=title,link,excerpt,content",
        rss_url="https://pmt.pi.gov.br/feed/",
        base_url="https://pmt.pi.gov.br/noticias/",
        url_pattern=PMT_URL_PATTERN,
        limit=limit,
    )


def get_governo_pi_news(limit: int = 5) -> List[Dict[str, str]]:
    return _fetch_wp_or_rss(
        source_name="Governo do Piauí",
        api_url=f"https://www.pi.gov.br/wp-json/wp/v2/posts?per_page={limit}&_fields=title,link,excerpt,content",
        rss_url="https://www.pi.gov.br/feed/",
        base_url="https://www.pi.gov.br/noticias/",
        url_pattern=GOV_PI_URL_PATTERN,
        limit=limit,
    )

def get_all_teresina_news() -> List[Dict[str, str]]:
    """Coleta notícias de Cidade Verde, G1 Piauí e Portal Clube News."""
    print("   -> Coletando Cidade Verde...")
    cv = get_cidade_verde_news(limit=8)
    print("   -> Coletando G1 Piauí...")
    g1 = get_g1_piaui_news(limit=8)
    print("   -> Coletando Portal Clube News...")
    clube = get_clube_news(limit=6)
    return cv + g1 + clube