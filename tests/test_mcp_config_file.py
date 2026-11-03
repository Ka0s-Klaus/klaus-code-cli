"""Tests de --mcp-config (#70)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import klaus.config as cm
from klaus.config import (
    MCPConfigError,
    MCPServerConfig,
    load_mcp_config_file,
    merge_mcp_servers,
)


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


# ── Formatos ────────────────────────────────────────────────────────────────


def test_list_format_yaml(tmp_path: Path) -> None:
    p = write(tmp_path, "mcp.yaml", "- name: fs\n  command: [npx, server-fs, /w]\n  confirm: always\n")
    [s] = load_mcp_config_file(p)
    assert s.name == "fs" and s.command == ["npx", "server-fs", "/w"] and s.confirm == "always"


def test_mcp_servers_key_json(tmp_path: Path) -> None:
    p = write(tmp_path, "mcp.json", json.dumps({"mcp_servers": [{"name": "a", "command": ["x"]}]}))
    assert [s.name for s in load_mcp_config_file(p)] == ["a"]


def test_mcpservers_format(tmp_path: Path) -> None:
    """El formato habitual de otros clientes MCP se convierte a command + args."""
    data = {
        "mcpServers": {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            },
            "db": {"type": "stdio", "command": "uvx", "args": ["mcp-pg"], "trust_read_only": False},
        }
    }
    servers = {s.name: s for s in load_mcp_config_file(write(tmp_path, "c.json", json.dumps(data)))}
    assert servers["github"].command == ["npx", "-y", "@modelcontextprotocol/server-github"]
    assert servers["github"].env == {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
    assert servers["db"].command == ["uvx", "mcp-pg"]
    assert servers["db"].trust_read_only is False


def test_remote_servers_skipped_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import klaus.compat as compat

    compat._warned.clear()
    data = {"mcpServers": {"remote": {"url": "https://x/mcp"}, "local": {"command": "x"}}}
    servers = load_mcp_config_file(write(tmp_path, "c.json", json.dumps(data)))
    assert [s.name for s in servers] == ["local"]
    assert "remote" in capsys.readouterr().err


# ── Errores ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "content", "fragment"),
    [
        ("bad.json", "{not json", "no es JSON/YAML válido"),
        ("odd.yaml", "foo: bar\n", "formato no reconocido"),
        ("missing.yaml", "- name: x\n", "servidor inválido"),
        ("wrong.json", json.dumps({"mcpServers": {"a": "npx"}}), "mal formado"),
    ],
)
def test_invalid_files(tmp_path: Path, name: str, content: str, fragment: str) -> None:
    with pytest.raises(MCPConfigError, match=fragment):
        load_mcp_config_file(write(tmp_path, name, content))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(MCPConfigError, match="no existe"):
        load_mcp_config_file(tmp_path / "nope.json")


# ── Combinación con config.yaml ─────────────────────────────────────────────


def test_merge_cli_overrides_by_name() -> None:
    base = [MCPServerConfig(name="a", command=["old"]), MCPServerConfig(name="b", command=["b"])]
    extra = [MCPServerConfig(name="a", command=["new"]), MCPServerConfig(name="c", command=["c"])]
    merged = {s.name: s.command for s in merge_mcp_servers(base, extra)}
    assert merged == {"a": ["new"], "b": ["b"], "c": ["c"]}


def test_load_config_with_several_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = write(tmp_path, "config.yaml", "mcp_servers:\n  - name: base\n    command: [x]\n")
    monkeypatch.setattr(cm, "CONFIG_PATH", cfg)
    f1 = write(tmp_path, "one.yaml", "- name: one\n  command: [y]\n")
    f2 = write(tmp_path, "two.json", json.dumps({"mcpServers": {"two": {"command": "z"}}}))
    config = cm.load_config(mcp_config_files=[str(f1), str(f2)])
    assert [s.name for s in config.mcp_servers] == ["base", "one", "two"]


# ── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_invalid_file_exits_with_config_error(tmp_path: Path) -> None:
    from klaus.cli import app

    result = CliRunner().invoke(app, ["run", "hola", "--mcp-config", str(tmp_path / "nope.json")])
    assert result.exit_code == 4
    assert "no existe" in result.output


def test_cli_passes_servers_to_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`klaus run --mcp-config` llega a la config que recibe el agente."""
    import klaus.cli as cli

    monkeypatch.setattr(cm, "CONFIG_PATH", tmp_path / "none.yaml")
    seen: dict[str, list[str]] = {}

    async def fake_run(prompt: str, config: cm.KlausConfig, project_root: Path) -> int:
        seen["servers"] = [s.name for s in config.mcp_servers]
        return 0

    monkeypatch.setattr(cli, "_run_async", fake_run)
    f = write(tmp_path, "m.json", json.dumps({"mcpServers": {"gh": {"command": "npx"}}}))
    result = CliRunner().invoke(cli.app, ["run", "hola", "--mcp-config", str(f)])
    assert result.exit_code == 0, result.output
    assert seen["servers"] == ["gh"]


async def test_end_to_end_with_real_server(tmp_path: Path) -> None:
    """El fichero arranca un servidor MCP real y sus tools quedan registradas."""
    pytest.importorskip("mcp.server.mcpserver")
    from klaus.mcp.client import MCPRegistry

    fake = Path(__file__).parent / "fixtures" / "mcp_fake_server.py"
    data = {
        "mcpServers": {
            "fake": {
                "command": sys.executable,
                "args": [str(fake)],
                "env": {"FAKE_MCP_LOG": str(tmp_path / "log")},
            }
        }
    }
    servers = load_mcp_config_file(write(tmp_path, "m.json", json.dumps(data)))
    reg = MCPRegistry()
    try:
        await reg.startup(servers)
        assert "mcp_fake_lookup" in reg.handlers
    finally:
        await reg.shutdown()
