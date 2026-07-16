"""Tests para klaus.tools.write — write_file, edit_file, delete_file."""

from __future__ import annotations

import pytest
from pathlib import Path

import klaus.tools.write as wm


@pytest.mark.asyncio
async def test_write_file_creates_new(tmp_path):
    target = tmp_path / "hello.txt"
    result = await wm.write_file(str(target), "hola mundo", cwd=tmp_path)
    assert result["status"] == "ok"
    assert target.read_text() == "hola mundo"


@pytest.mark.asyncio
async def test_write_file_updates_existing(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("viejo")
    result = await wm.write_file(str(target), "nuevo", cwd=tmp_path)
    assert result["status"] == "ok"
    assert target.read_text() == "nuevo"


@pytest.mark.asyncio
async def test_write_file_no_changes(tmp_path):
    target = tmp_path / "same.txt"
    target.write_text("igual")
    result = await wm.write_file(str(target), "igual", cwd=tmp_path)
    assert result["status"] == "no_changes"


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "c.txt"
    result = await wm.write_file(str(target), "contenido", cwd=tmp_path)
    assert result["status"] == "ok"
    assert target.read_text() == "contenido"


@pytest.mark.asyncio
async def test_edit_file_simple(tmp_path):
    target = tmp_path / "edit.py"
    target.write_text("x = 1\ny = 2\n")
    result = await wm.edit_file(str(target), "x = 1", "x = 99", cwd=tmp_path)
    assert result["status"] == "ok"
    assert "x = 99" in target.read_text()


@pytest.mark.asyncio
async def test_edit_file_not_found(tmp_path):
    result = await wm.edit_file(str(tmp_path / "noexiste.py"), "a", "b", cwd=tmp_path)
    assert "error" in result


@pytest.mark.asyncio
async def test_edit_file_old_string_not_found(tmp_path):
    target = tmp_path / "f.py"
    target.write_text("abc")
    result = await wm.edit_file(str(target), "xyz", "123", cwd=tmp_path)
    assert "error" in result


@pytest.mark.asyncio
async def test_edit_file_multiple_occurrences_blocked(tmp_path):
    target = tmp_path / "dup.py"
    target.write_text("a\na\n")
    result = await wm.edit_file(str(target), "a", "b", cwd=tmp_path)
    assert "error" in result
    assert "2 veces" in result["error"]


@pytest.mark.asyncio
async def test_edit_file_replace_all(tmp_path):
    target = tmp_path / "dup2.py"
    target.write_text("a\na\n")
    result = await wm.edit_file(str(target), "a", "z", replace_all=True, cwd=tmp_path)
    assert result["status"] == "ok"
    assert target.read_text() == "z\nz\n"


@pytest.mark.asyncio
async def test_delete_file(tmp_path):
    target = tmp_path / "del.txt"
    target.write_text("x")
    result = await wm.delete_file(str(target), cwd=tmp_path)
    assert result["status"] == "ok"
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_file_not_found(tmp_path):
    result = await wm.delete_file(str(tmp_path / "noexiste.txt"), cwd=tmp_path)
    assert "error" in result
