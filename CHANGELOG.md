# Changelog — Klaus Code CLI

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — Fix: KLAUDE_API_KEY opcional

### Fixed
- `cli.py`: eliminadas guardas `if not config.api_key` en `run()`, `repl()` e `init --scan` — ya no bloquean el arranque cuando no hay API key definida en el cliente
- `config.py`: `KlausConfig.api_key` ahora devuelve `str | None` en lugar de `""` cuando la variable de entorno no está definida
- `anthropic_fmt.py`: header `x-api-key` solo se incluye si `api_key` no es `None`
- `openai_fmt.py`: header `Authorization: Bearer` solo se incluye si `api_key` no es `None`

### Context
Cuando se usa klaude-proxy como backend, la API key de Anthropic vive en el proxy.
El cliente (Klaus) solo necesita `KLAUDE_PROXY_URL` — no tiene por qué conocer la key real.

**Files:** `Klaus/config.py`, `Klaus/provider/anthropic_fmt.py`, `Klaus/provider/openai_fmt.py`, `Klaus/cli.py`
**Issue:** [#39](https://github.com/Ka0s-Klaus/Klaus-code-cli/issues/39)

---


## [Unreleased] — Fase 16: Developer UX

### Added
- `repl.py`: `/tokens` REPL command — shows cumulative session token counts (input / output / total)
- `repl.py`: Session-level token accumulation across turns (`session_input_tokens`, `session_output_tokens`)
- `repl.py`: YOLO mode indicator in REPL welcome panel — shown when `--yolo` is active
- `repl.py`: `yolo` parameter propagated through `run_repl` → `_print_welcome`
- `cli.py`: `yolo` flag forwarded from `repl` command through `_repl_async` → `run_repl`
- `repl.py`: `_run_turn` now returns `tuple[list, int, int]` — messages + per-turn token counts
- `CHANGELOG.md`: this file

**Files:** `Klaus/repl.py`, `Klaus/cli.py`, `CHANGELOG.md`
**Issue:** [#31](https://github.com/Ka0s-Klaus/Klaus-code-cli/issues/31)

---

## [0.15.0] — Fase 15: GitHub Actions CI/CD

### Added
- `.github/workflows/ci.yml`: CI pipeline on every push/PR — runs `ruff` lint, `mypy` typecheck, and `pytest` on Python 3.11 / 3.12 / 3.13
- `.github/workflows/release.yml`: Release pipeline on `v*.*.*` tags — builds and publishes to PyPI via OIDC trusted publishing (no hardcoded tokens)
- `pyproject.toml`: PyPI metadata and `[project.optional-dependencies] dev` group

**Files:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pyproject.toml`
**Issue:** [#29](https://github.com/Ka0s-Klaus/Klaus-code-cli/issues/29) · **PR:** [#30](https://github.com/Ka0s-Klaus/Klaus-code-cli/pull/30)

---

## [0.14.0] — Fase 14: pytest suite

### Added
- `tests/conftest.py`: autouse fixture — disables all confirmations during tests
- `tests/test_tools_write.py`: 11 tests for `write_file`, `edit_file`, `delete_file`
- `tests/test_tools_files.py`: 5 tests for `read_file`, `list_directory`
- `tests/test_tools_bash.py`: 5 tests for `run_bash` (execution, danger patterns, exit codes)
- `tests/test_streaming.py`: 4 tests for `StreamRenderer`
- `tests/test_sessions.py`: 10 tests for `SessionManager`, `SessionLock`, session CRUD helpers
- `tests/test_config.py`: 6 tests for `KlausConfig` defaults, env overrides, file loading
- `pyproject.toml`: `[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.mypy]`

**Files:** `tests/` (7 files), `pyproject.toml`
**Issue:** [#27](https://github.com/Ka0s-Klaus/Klaus-code-cli/issues/27) · **PR:** [#28](https://github.com/Ka0s-Klaus/Klaus-code-cli/pull/28)

---

## [0.13.0] — Fase 13: MCP client

### Added
- `Klaus/mcp/`: MCP client module — `MCPRegistry`, server lifecycle, schema + handler injection
- `Klaus/cli.py`: `--mcp-config` option for `run` and `repl` commands

---

## [0.12.0] — Fase 12: Context management & auto-compact

### Added
- `Klaus/context.py`: `load_project_context`, `compact_messages`
- `Klaus/agent.py` + `Klaus/repl.py`: auto-compact at 80% of `max_context_tokens`
- `Klaus/config.py`: `ContextConfig`

---

## [0.11.0] — Fase 11: Streaming responses

### Added
- `Klaus/streaming.py`: `StreamRenderer` — Rich live streaming of token chunks
- Provider `stream_message` abstract + Anthropic implementation
- `Klaus/repl.py`: streaming mode in `_run_turn`; `--no-stream` CLI flag

---

## [0.10.0] — Fase 10: Sessions persistence

### Added
- `Klaus/sessions.py`: `SessionManager`, `SessionLock`, session CRUD helpers
- `Klaus/cli.py`: `sessions` subcommand group (`list`, `show`, `clear`)
- `/sessions` REPL command

---

## [0.9.0] — Fase 9: Plan mode

### Added
- `Klaus/agent.py`: `_run_plan_phase` — plan generation → confirmation → execution
- `Klaus/cli.py`: `--plan` flag

---

## [0.8.0] — Fase 8: REPL interactivo

### Added
- `Klaus/repl.py`: interactive REPL loop with history and special commands
- Rich welcome panel, `/exit /quit /clear /help /history /sessions`

---

## [0.7.0] — Fase 7: Git tools

### Added
- `Klaus/tools/git.py`: `git_status`, `git_diff`, `git_commit` with confirmation

---

## [0.6.0] — Fase 6: Search tools

### Added
- `Klaus/tools/search.py`: `glob_search`, `grep_search` with `.klausignore` support

---

## [0.5.0] — Fase 5: --yolo mode

### Added
- `CONFIRM_WRITES` / `CONFIRM_BASH` flags; `configure_confirmations()`
- `--yolo`, `--allow-writes`, `--allow-bash` CLI flags
- Danger patterns in `run_bash` always blocked regardless of `--yolo`

---

## [0.4.0] — Fase 4: Bash tool

### Added
- `Klaus/tools/bash.py`: `run_bash` with danger-pattern blocking and timeout

---

## [0.3.0] — Fase 3: Write tools

### Added
- `Klaus/tools/write.py`: `write_file`, `edit_file`, `delete_file` with diff preview

---

## [0.2.0] — Fase 2: Read tools

### Added
- `Klaus/tools/files.py`: `read_file`, `list_directory`

---

## [0.1.0] — Fase 1: Estructura base + provider Anthropic

### Added
- Package skeleton, Typer CLI, `KlausConfig`, Anthropic provider adapter, multi-turn agent loop
