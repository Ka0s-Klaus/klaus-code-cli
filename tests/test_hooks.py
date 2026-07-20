"""Tests para Klaus.hooks — HookRunner."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def hooks_dir(tmp_path: Path) -> Path:
    d = tmp_path / "hooks"
    d.mkdir()
    return d


def _make_script(directory: Path, filename: str, script_content: str) -> Path:
    """Crea un script ejecutable en el directorio dado."""
    script = directory / filename
    script.write_text(script_content)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


class TestHookRunner:
    @pytest.mark.asyncio
    async def test_pre_tool_allows_when_no_hooks(self, tmp_path: Path) -> None:
        from Klaus.hooks import HookRunner

        runner = HookRunner(project_root=tmp_path)
        allowed = await runner.run_pre_tool("read_file", {"path": "test.py"})
        assert allowed is True

    @pytest.mark.asyncio
    async def test_pre_tool_blocks_on_nonzero_exit(self, hooks_dir: Path, tmp_path: Path) -> None:
        from Klaus.hooks import HookRunner

        _make_script(hooks_dir, "PreToolUse.sh", "#!/bin/sh\nexit 1\n")
        runner = HookRunner(project_root=tmp_path)
        # Redirigir _global_dir al directorio de hooks de prueba
        runner._global_dir = hooks_dir

        allowed = await runner.run_pre_tool("write_file", {"path": "secret.py"})
        assert allowed is False

    @pytest.mark.asyncio
    async def test_pre_tool_allows_on_zero_exit(self, hooks_dir: Path, tmp_path: Path) -> None:
        from Klaus.hooks import HookRunner

        _make_script(hooks_dir, "PreToolUse.sh", "#!/bin/sh\nexit 0\n")
        runner = HookRunner(project_root=tmp_path)
        runner._global_dir = hooks_dir

        allowed = await runner.run_pre_tool("write_file", {"path": "file.py"})
        assert allowed is True

    @pytest.mark.asyncio
    async def test_post_tool_hook_receives_json(self, hooks_dir: Path, tmp_path: Path) -> None:
        """El hook post-tool recibe un JSON en stdin con tool_name, args y result."""
        received_file = tmp_path / "received.json"
        _make_script(
            hooks_dir,
            "PostToolUse.sh",
            f"#!/bin/sh\ncat > {received_file}\n",
        )

        from Klaus.hooks import HookRunner

        runner = HookRunner(project_root=tmp_path)
        runner._global_dir = hooks_dir

        await runner.run_post_tool(
            "read_file",
            {"path": "test.py"},
            {"content": "print('hello')"},
        )

        assert received_file.exists()
        data = json.loads(received_file.read_text())
        assert data["tool_name"] == "read_file"
        assert "tool_input" in data
        assert "tool_result" in data

    @pytest.mark.asyncio
    async def test_stop_hook_executed(self, hooks_dir: Path, tmp_path: Path) -> None:
        flag = tmp_path / "stop.flag"
        _make_script(
            hooks_dir,
            "Stop.sh",
            f"#!/bin/sh\ntouch {flag}\n",
        )

        from Klaus.hooks import HookRunner

        runner = HookRunner(project_root=tmp_path)
        runner._global_dir = hooks_dir

        await runner.run_stop()
        assert flag.exists()

    @pytest.mark.asyncio
    async def test_hooks_not_found_no_crash(self, tmp_path: Path) -> None:
        """Sin directorio de hooks, no debe lanzar excepción."""
        from Klaus.hooks import HookRunner

        runner = HookRunner(project_root=tmp_path)
        runner._global_dir = tmp_path / "no-existe"
        result = await runner.run_pre_tool("run_bash", {"command": "ls"})
        assert result is True

    @pytest.mark.asyncio
    async def test_pre_tool_decision_block_via_stdout(self, hooks_dir: Path, tmp_path: Path) -> None:
        """Un hook que sale con 0 pero emite JSON con decision=block también bloquea."""
        _make_script(
            hooks_dir,
            "PreToolUse.sh",
            '#!/bin/sh\necho \'{"decision": "block"}\'\nexit 0\n',
        )

        from Klaus.hooks import HookRunner

        runner = HookRunner(project_root=tmp_path)
        runner._global_dir = hooks_dir

        allowed = await runner.run_pre_tool("run_bash", {"command": "rm -rf /"})
        assert allowed is False
