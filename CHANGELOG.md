# Changelog — Klaus Code CLI

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

> Agrupa todo lo fusionado desde la Fase 15. Las versiones `0.x` anteriores son fases de desarrollo: nunca se etiquetaron ni publicaron (ver [🧪 Development](docs/development.md#-release)).

### Security
- **Tools MCP con confirmación**: antes se ejecutaban siempre sin preguntar (la documentación decía lo contrario). Política por servidor `mcp_servers[].confirm` = `auto` (default: pregunta salvo solo lectura o `--allow-writes`/`--yolo`) | `always` (también en YOLO) | `never`; `trust_read_only` para `readOnlyHint`. Sin TTY se deniega lo que requiere confirmación ([#61](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/61))
- **Workspace**: las tools de ficheros (`read_file`, `list_directory`, `glob_search`, `grep_search`, `write_file`, `edit_file`, `delete_file`, `read_image`) solo operan dentro del proyecto + `security.allowed_paths`. Se resuelven `~`, `..` y symlinks; fuera, se pregunta (también en `--yolo`) o se deniega sin TTY ([#56](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/56))
- **Sub-agentes**: `spawn_agent` ya no fuerza la auto-aprobación (antes evitaba las confirmaciones y las desactivaba para el padre el resto de la sesión), pasa por `_dispatch_tool` (hooks + validación) y valida su `cwd` ([#56](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/56))
- `_dispatch_tool` descarta el argumento `cwd` enviado por el modelo ([#56](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/56))
- **Hooks de proyecto**: requieren confianza explícita, por hash, en `~/.klaus/trusted_hooks.json`; se ejecutan de forma asíncrona ([#56](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/56))
- **run_bash**: denylist ampliada (*best effort*) y `security.bash_allowlist` para modo desatendido ([#56](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/56))
- **Pseudonymizer**: aplicado en `run`, `repl`, `/model` y `spawn_agent`; los modelos LiteLLM externos ya no se tratan como locales; se espera antes de la primera petición; con un proveedor directo no se envían los literales al tercero ([#55](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/55))

### Added
- **Paridad de funcionalidades (fases 1-9)**: `/model`, `--resume`, `web_fetch`/`web_search`, `todo_write`/`todo_read` + `/todos`, hooks Pre/PostToolUse/Stop/Notification, `spawn_agent`, `read_image`, comandos slash personalizados, `memory_write`/`memory_read` + `/memory`, checkpoints + `--restore` ([#46](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/46))
- Bloques de razonamiento (*thinking*) en tiempo real para modelos reasoning ([#44](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/44))
- Integración con la API de configuración dinámica del pseudonymizer de klaude-proxy ([#53](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/53))
- Directorio de trabajo inyectado en el system prompt ([#40](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/40))
- Variables de entorno del proxy (`KLAUS_PROXY_URL`, `KLAUS_MODEL`, `KLAUS_API_FORMAT`) ([#37](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/37), renombradas en [#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58))
- REPL: `/tokens`, indicador de modo YOLO ([#32](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/32))
- Secciones de config `pseudonymizer` y `security`
- **Batería de evaluación** (Fase 0): `klaus eval` ejecuta el agente sobre tareas aisladas y mide éxito, turnos, tokens, tiempo y bloqueos; `--verify-tasks` valida la batería sin modelo (job de CI). 12 tareas iniciales en 7 categorías, con tests ocultos, mutation testing y trampas de seguridad. `RunStats` en `run_agent_loop` ([#71](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/71))
- `klaus/compat.py`: avisos de obsolescencia para nombres anteriores ([#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58))
- Workflow de release: verifica que el tag coincide con la versión de `pyproject.toml` ([#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58))
- Documentación: `docs/security.md`, `docs/development.md` (CI y release), `CONTRIBUTING.md`; README reescrito según `DOCUMENTATION_STYLE.md`
- `docs/roadmap.md`: propuesta de roadmap (agente de código soberano, 4 fases con gates); `roadmap-feature-parity.md` queda como histórico ([#67](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/67))
- Tests: de 41 a más de 250 (seguridad, pseudonymizer, bucle del agente, compatibilidad)

### Changed
- **Nombres unificados en `klaus`** ([#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58)): `~/.klaus/`, `<proyecto>/.klaus/`, variables `KLAUS_*`, clave `context.max_klaus_md_tokens`, comando `klaus` en toda la documentación
- `klaus init --scan` genera `KLAUS.md` (antes `CLAUS.md`, que el contexto **no cargaba**) ([#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58))
- Versión con fuente única en `pyproject.toml` (`0.15.0`); `klaus.__version__` se lee de los metadatos ([#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58))
- `network.timeout_seconds`: 120 → 600 para modelos thinking ([#42](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/42))
- `KLAUS_API_KEY` opcional (no requerida con klaude-proxy) ([#40](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/40))
- Estado de contexto: la línea `📊` separa **contexto** actual y **consumo** acumulado ([#57](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/57))

### Deprecated
- Variables `KLAUDE_PROXY_URL`, `KLAUDE_API_KEY`, `KLAUDE_MODEL`, `KLAUDE_API_FORMAT` → `KLAUS_*` (siguen funcionando, con aviso)
- Directorios `~/.Klaus/` y `<proyecto>/.Klaus/` → `.klaus/` (se usan si son los únicos; se avisa con el comando `mv`)
- Clave `context.max_Klaus_md_tokens` → `max_klaus_md_tokens`

### Fixed
- `_dispatch_tool`: invocación única de cada tool (un `TypeError` interno repetía los efectos); validación contra los schemas activos (MCP incluido); error accionable ante parámetros desconocidos ([#57](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/57))
- Auto-compactación basada en el tamaño real del contexto (antes se sumaban los turnos), sin `tool_result` huérfanos, también en turnos sin tools del REPL; `/tokens` ya no se pone a 0 al compactar ([#57](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/57))
- `klaus init` genera los mismos defaults que el modelo (`timeout_seconds`, `max_agent_depth`) ([#57](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/57))
- MCP con `mcp` 2.x (`input_schema`); streaming OpenAI con `on_thinking`; portapapeles con ficheros en `read_image` ([#54](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/54))
- CI en verde: imports `klaus`, ruff y mypy ([#54](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/54))
- `OpenAIAdapter` enviaba las tools sin convertir al formato OpenAI (Ollama/Qwen3) ([#48](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/48))
- Parámetros requeridos validados antes de invocar el handler (bucle `read_file({})`) ([#50](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/50))
- Documentación: `klaus run --no-stream` y `--mcp-config` no existen (eliminados de las guías); `docs/mcp.md` decía que MCP pide confirmación ([#58](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/58), [#56](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/56))

---

## [0.15.0] — Fase 15: GitHub Actions CI/CD

### Added
- `.github/workflows/ci.yml`: CI pipeline on every push/PR — runs `ruff` lint, `mypy` typecheck, and `pytest` on Python 3.11 / 3.12 / 3.13
- `.github/workflows/release.yml`: Release pipeline on `v*.*.*` tags — builds and publishes to PyPI via OIDC trusted publishing (no hardcoded tokens)
- `pyproject.toml`: PyPI metadata and `[project.optional-dependencies] dev` group

**Files:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pyproject.toml`
**Issue:** [#29](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/29) · **PR:** [#30](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/30)

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
**Issue:** [#27](https://github.com/Ka0s-Klaus/klaus-code-cli/issues/27) · **PR:** [#28](https://github.com/Ka0s-Klaus/klaus-code-cli/pull/28)

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
