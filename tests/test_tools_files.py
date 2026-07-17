"""Tests para klaus.tools.files — read_file, list_directory."""

from __future__ import annotations

import pytest

from klaus.tools.files import list_directory, read_file


@pytest.mark.asyncio
async def test_read_file_basic(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3")
    result = await read_file(str(f), cwd=tmp_path)
    assert result["content"] == "line1\nline2\nline3"
    assert result["total_lines"] == 3


@pytest.mark.asyncio
async def test_read_file_not_found(tmp_path):
    result = await read_file(str(tmp_path / "noexiste.txt"), cwd=tmp_path)
    assert "error" in result


@pytest.mark.asyncio
async def test_read_file_range(tmp_path):
    f = tmp_path / "multi.txt"
    f.write_text("a\nb\nc\nd\ne")
    result = await read_file(str(f), start_line=2, end_line=4, cwd=tmp_path)
    assert "b" in result["content"]
    assert not result["content"].startswith("a")


@pytest.mark.asyncio
async def test_list_directory_basic(tmp_path):
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.py").touch()
    (tmp_path / "subdir").mkdir()
    result = await list_directory(str(tmp_path), cwd=tmp_path)
    names = [e["name"] for e in result["entries"]]
    assert "a.txt" in names
    assert "b.py" in names
    assert "subdir" in names


@pytest.mark.asyncio
async def test_list_directory_not_found(tmp_path):
    result = await list_directory(str(tmp_path / "noexiste"), cwd=tmp_path)
    assert "error" in result
