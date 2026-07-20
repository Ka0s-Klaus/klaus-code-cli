"""Tools de búsqueda web: web_fetch y web_search.

web_fetch: descarga una URL y extrae el texto como markdown.
web_search: búsqueda en DuckDuckGo (sin API key).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

_USER_AGENT = "Mozilla/5.0 (compatible; Klaus-code-cli/1.0)"
_FETCH_TIMEOUT = 30
_MAX_CONTENT_CHARS = 50_000


async def web_fetch(
    url: str,
    timeout: int = _FETCH_TIMEOUT,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Descarga una URL y devuelve el contenido como texto/markdown.

    Para HTML usa html2text si está disponible; si no, extrae texto plano.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        raw_text = response.text

        if "html" in content_type:
            content = _html_to_text(raw_text)
        else:
            content = raw_text

        # Truncar al límite
        truncated = len(content) > _MAX_CONTENT_CHARS
        if truncated:
            content = content[:_MAX_CONTENT_CHARS]

        result: dict[str, Any] = {
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content": content,
            "chars": len(content),
        }
        if truncated:
            result["truncated"] = True
        return result

    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} al acceder a {url}"}
    except httpx.TimeoutException:
        return {"error": f"Timeout ({timeout}s) al acceder a {url}"}
    except Exception as e:
        return {"error": f"Error al acceder a {url}: {e}"}


def _html_to_text(html: str) -> str:
    """Convierte HTML a texto legible. Usa html2text si está disponible."""
    try:
        import html2text as h2t

        converter = h2t.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0  # sin wrap
        return converter.handle(html)
    except ImportError:
        pass

    # Fallback: extracción simple con regex
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


async def web_search(
    query: str,
    max_results: int = 10,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Busca en la web usando DuckDuckGo Instant Answer API (sin clave de API).

    Para resultados más ricos, usa la API HTML de DDG como fallback.
    """
    # Intentar primero con la Instant Answer API (JSON)
    try:
        results = await _ddg_instant(query, max_results)
        if results:
            return {"query": query, "results": results, "count": len(results), "source": "ddg-ia"}
    except Exception:
        pass

    # Fallback: DDG HTML scraping
    try:
        results = await _ddg_html(query, max_results)
        return {"query": query, "results": results, "count": len(results), "source": "ddg-html"}
    except Exception as e:
        return {"error": f"No se pudo completar la búsqueda: {e}"}


async def _ddg_instant(query: str, max_results: int) -> list[dict[str, Any]]:
    """DuckDuckGo Instant Answer API — devuelve resultados relacionados."""
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(url, params=params, headers={"User-Agent": _USER_AGENT})
        data = r.json()

    results: list[dict[str, Any]] = []

    # AbstractText (respuesta directa)
    if data.get("AbstractText"):
        results.append({
            "title": data.get("Heading", query),
            "url": data.get("AbstractURL", ""),
            "snippet": data["AbstractText"],
        })

    # RelatedTopics
    for topic in data.get("RelatedTopics", []):
        if len(results) >= max_results:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            url_val = topic.get("FirstURL", "")
            results.append({
                "title": topic["Text"][:80],
                "url": url_val,
                "snippet": topic["Text"],
            })

    return results


async def _ddg_html(query: str, max_results: int) -> list[dict[str, Any]]:
    """DuckDuckGo HTML fallback — parsea la página HTML de resultados."""
    url = "https://html.duckduckgo.com/html/"

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.post(
            url,
            data={"q": query},
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    html = r.text
    results: list[dict[str, Any]] = []

    # Extraer links, títulos y snippets del HTML de DDG
    link_pat = re.compile(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
    snippet_pat = re.compile(r'class="result__snippet"[^>]*>(.*?)</span>', re.DOTALL)

    links = link_pat.findall(html)
    snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pat.findall(html)]

    for i, (href, title_html) in enumerate(links):
        if i >= max_results:
            break
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snippet = snippets[i] if i < len(snippets) else ""
        results.append({"title": title, "url": href, "snippet": snippet})

    return results
