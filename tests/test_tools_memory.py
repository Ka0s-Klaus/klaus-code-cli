"""Tests para Klaus.tools.memory — memory_write y memory_read."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def patch_memory_dir(memory_dir: Path):
    """Redirige el directorio de memorias a un directorio temporal."""
    with patch("Klaus.tools.memory._MEMORY_DIR", memory_dir):
        yield


class TestMemoryWrite:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_write

        result = await memory_write(
            name="test-memory",
            content="Este es el contenido de la memoria.",
            memory_type="project",
            description="Una memoria de prueba",
        )

        assert result["status"] == "ok"
        assert result["action"] == "created"
        mem_file = memory_dir / "test-memory.md"
        assert mem_file.exists()

    @pytest.mark.asyncio
    async def test_write_updates_existing(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_write

        await memory_write(name="update-test", content="Versión 1")
        result = await memory_write(name="update-test", content="Versión 2")

        assert result["action"] == "updated"

    @pytest.mark.asyncio
    async def test_write_creates_index(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_write

        await memory_write(name="indexed-mem", content="Contenido", description="Desc corta")

        index = memory_dir / "MEMORY.md"
        assert index.exists()
        content = index.read_text()
        assert "indexed-mem" in content

    @pytest.mark.asyncio
    async def test_write_slugifies_name(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_write

        result = await memory_write(name="Mi Memoria Con Espacios", content="test")
        assert "-" in result["name"]
        assert " " not in result["name"]

    @pytest.mark.asyncio
    async def test_write_empty_name_returns_error(self) -> None:
        from Klaus.tools.memory import memory_write

        result = await memory_write(name="", content="contenido")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_write_frontmatter_format(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_write

        await memory_write(
            name="frontmatter-test",
            content="Contenido de prueba",
            memory_type="user",
            description="Descripción de prueba",
        )

        mem_file = memory_dir / "frontmatter-test.md"
        text = mem_file.read_text()
        assert text.startswith("---")
        assert "type: user" in text
        assert "Contenido de prueba" in text


class TestMemoryRead:
    @pytest.mark.asyncio
    async def test_read_all_when_empty(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_read

        result = await memory_read()
        assert result["count"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_read_after_write(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_read, memory_write

        await memory_write(name="readable", content="Contenido leíble", description="Para leer")
        result = await memory_read()

        assert result["count"] == 1
        assert result["results"][0]["name"] == "readable"

    @pytest.mark.asyncio
    async def test_read_filters_by_query(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_read, memory_write

        await memory_write(name="python-notes", content="Python notas")
        await memory_write(name="js-notes", content="JavaScript notas")

        result = await memory_read(query="python")
        assert result["count"] == 1
        assert result["results"][0]["name"] == "python-notes"

    @pytest.mark.asyncio
    async def test_read_filters_by_type(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_read, memory_write

        await memory_write(name="user-mem", content="user content", memory_type="user")
        await memory_write(name="proj-mem", content="project content", memory_type="project")

        result = await memory_read(memory_type="user")
        assert result["count"] == 1
        assert result["results"][0]["name"] == "user-mem"

    @pytest.mark.asyncio
    async def test_read_skips_index_file(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import memory_read, memory_write

        await memory_write(name="real-memory", content="contenido real")
        result = await memory_read()

        names = [m["name"] for m in result["results"]]
        assert "MEMORY" not in names


class TestMemoryIndex:
    def test_get_memory_index_content_empty(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import get_memory_index_content

        assert get_memory_index_content() == ""

    @pytest.mark.asyncio
    async def test_get_memory_index_content_after_write(self, memory_dir: Path) -> None:
        from Klaus.tools.memory import get_memory_index_content, memory_write

        await memory_write(name="index-test", content="test", description="Descripción índice")
        content = get_memory_index_content()

        assert "index-test" in content
