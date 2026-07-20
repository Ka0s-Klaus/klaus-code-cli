"""Tests para Klaus.tools.web — web_fetch y web_search."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    return tmp_path


class TestWebFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_content(self, cwd: Path) -> None:
        from Klaus.tools.web import web_fetch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>Hola mundo</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await web_fetch(url="https://example.com", cwd=cwd)

        assert "error" not in result
        assert result["status_code"] == 200
        assert "content" in result

    @pytest.mark.asyncio
    async def test_fetch_invalid_url(self, cwd: Path) -> None:
        from Klaus.tools.web import web_fetch

        result = await web_fetch(url="not-a-url", cwd=cwd)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fetch_http_error(self, cwd: Path) -> None:
        import httpx
        from Klaus.tools.web import web_fetch

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Not found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            ))
            mock_client_cls.return_value = mock_client

            result = await web_fetch(url="https://example.com/404", cwd=cwd)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_fetch_json_content(self, cwd: Path) -> None:
        from Klaus.tools.web import web_fetch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"key": "value"}'
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await web_fetch(url="https://api.example.com/data", cwd=cwd)

        assert result["status_code"] == 200
        assert "value" in result["content"]


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, cwd: Path) -> None:
        from Klaus.tools.web import web_search

        ddg_response = MagicMock()
        ddg_response.status_code = 200
        ddg_response.headers = {"content-type": "application/json"}
        ddg_response.json = MagicMock(return_value={
            "Abstract": "Python es un lenguaje de programación.",
            "AbstractURL": "https://python.org",
            "RelatedTopics": [
                {"Text": "Python 3 — Versión 3.x", "FirstURL": "https://python.org/3"},
                {"Text": "PyPI — repositorio de paquetes", "FirstURL": "https://pypi.org"},
            ],
        })

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=ddg_response)
            mock_client_cls.return_value = mock_client

            result = await web_search(query="python programming", cwd=cwd)

        assert "error" not in result
        assert "results" in result
        assert isinstance(result["results"], list)

    @pytest.mark.asyncio
    async def test_search_empty_query(self, cwd: Path) -> None:
        from Klaus.tools.web import web_search

        result = await web_search(query="", cwd=cwd)
        # Query vacía: puede devolver error o lista vacía; no debe crashear
        assert "error" in result or result.get("count", 0) == 0

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, cwd: Path) -> None:
        from Klaus.tools.web import web_search

        ddg_response = MagicMock()
        ddg_response.status_code = 200
        ddg_response.headers = {"content-type": "application/json"}
        ddg_response.json = MagicMock(return_value={
            "Abstract": "",
            "AbstractURL": "",
            "RelatedTopics": [
                {"Text": f"Result {i}", "FirstURL": f"https://example.com/{i}"}
                for i in range(20)
            ],
        })

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=ddg_response)
            mock_client_cls.return_value = mock_client

            result = await web_search(query="test", max_results=3, cwd=cwd)

        assert "results" in result
        assert len(result["results"]) <= 3
