"""Tests para load_project_context."""

from __future__ import annotations

from pathlib import Path

import pytest

from klaus.context import load_project_context


def test_no_claude_md_injects_cwd(tmp_path: Path) -> None:
    """Sin CLAUDE.md, el system_prompt debe ser solo 'Working directory: <path>'."""
    result = load_project_context(tmp_path)
    assert result["root"] == str(tmp_path)
    assert result["system_prompt"] == f"Working directory: {tmp_path}"
    assert "system_prompt_source" not in result


def test_with_claude_md_prepends_cwd(tmp_path: Path) -> None:
    """Con CLAUDE.md, el system_prompt = 'Working directory: ...\n\n' + contenido."""
    md = tmp_path / "CLAUDE.md"
    md.write_text("# My Project\n\nDo stuff.", encoding="utf-8")

    result = load_project_context(tmp_path)
    assert result["system_prompt"].startswith(f"Working directory: {tmp_path}\n\n")
    assert "# My Project" in result["system_prompt"]
    assert result["system_prompt_source"] == "CLAUDE.md"


def test_with_klaus_md_takes_priority(tmp_path: Path) -> None:
    """Klaus.md tiene prioridad sobre CLAUDE.md."""
    (tmp_path / "CLAUDE.md").write_text("claude content", encoding="utf-8")
    (tmp_path / "KLAUS.md").write_text("Klaus content", encoding="utf-8")

    result = load_project_context(tmp_path)
    assert result["system_prompt_source"] == "KLAUS.md"
    assert "Klaus content" in result["system_prompt"]
    assert result["system_prompt"].startswith(f"Working directory: {tmp_path}")


def test_truncation_respects_max_tokens(tmp_path: Path) -> None:
    """Contenido largo se trunca al límite de tokens."""
    md = tmp_path / "CLAUDE.md"
    md.write_text("x" * 10_000, encoding="utf-8")

    result = load_project_context(tmp_path, max_tokens=100)
    assert "[TRUNCADO]" in result["system_prompt"]
    assert len(result["system_prompt"]) < 10_100
