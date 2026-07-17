# 🤖 Klaus Code CLI

> **Agente de codificación agnóstico de proveedor** — conecta cualquier modelo (Anthropic, OpenAI, local via LiteLLM/Ollama) con tu codebase a través de una interfaz CLI potente y sin fricciones.

[![CI](https://github.com/Ka0s-Klaus/Klaus-code-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Ka0s-Klaus/Klaus-code-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ ¿Qué es Klaus Code CLI?

Klaus Code CLI es un agente de IA para codificación que opera directamente en tu terminal. A diferencia de las extensiones de editor, Klaus es **proveedor-agnóstico**: apunta a Anthropic, OpenAI, o cualquier servidor compatible con la API de Anthropic/OpenAI (LiteLLM, Ollama, vLLM...) cambiando una línea de configuración.

### 🎯 Características principales

| Feature | Descripción |
|---|---|
| 🔌 **Multi-proveedor** | Anthropic, OpenAI, LiteLLM, Ollama — sin cambiar código |
| 💬 **REPL interactivo** | Sesión de conversación persistente con historial |
| 📦 **11 tools integradas** | read, write, edit, delete, bash, glob, grep, git_status, git_diff, git_commit, list_directory |
| 🔐 **Confirmaciones** | Toda acción destructiva pide confirmación antes de ejecutar |
| ⚡ **Modo YOLO** | `--yolo` desactiva confirmaciones para workflows automatizados |
| 📋 **Plan mode** | `--plan` genera un plan de acción antes de ejecutar |
| 🧠 **Gestión de contexto** | Auto-compact cuando el contexto supera el 80% del límite |
| 💾 **Sesiones persistentes** | Historial de conversación guardado entre sesiones |
| 🔧 **MCP client** | Integra herramientas externas vía Model Context Protocol |
| ⚡ **Streaming** | Respuestas token a token con Rich live rendering |

---

## 🚀 Instalación rápida

```bash
# Desde PyPI
pip install Klaus-code-cli

# Desde source
git clone https://github.com/Ka0s-Klaus/Klaus-code-cli.git
cd Klaus-code-cli
pip install -e ".[dev]"
```

### Requisitos

- Python 3.11+
- Una API key válida (Anthropic, OpenAI, o servidor compatible)

### Configuración inicial

```bash
# Crear config con valores por defecto
Klaus init

# Establecer API key
export KLAUS_API_KEY="sk-ant-..."  # o la variable que configures

# Verificar configuración
Klaus config show
```

---

## 💡 Uso básico

### Modo agente (una tarea)

```bash
# Ejecutar una tarea con el agente
Klaus run "Refactoriza la función parse_config en config.py para usar dataclasses"

# Con streaming desactivado
Klaus run "Explica la arquitectura del proyecto" --no-stream

# Con plan previo (muestra el plan y pide confirmación antes de actuar)
Klaus run "Añade tests para el módulo sessions.py" --plan

# Modo YOLO — sin confirmaciones interactivas
Klaus run "Formatea todos los ficheros Python con black" --yolo
```

### REPL interactivo

```bash
# Iniciar sesión interactiva
Klaus repl

# Con nombre de sesión para recuperarla después
Klaus repl --session mi-proyecto

# Retomar sesión existente
Klaus repl --session mi-proyecto  # si existe, se reanuda automáticamente

# Con un modelo específico
Klaus repl --model claude-opus-4-8
```

### Comandos especiales en el REPL

| Comando | Acción |
|---|---|
| `/help` | Muestra la ayuda |
| `/clear` | Limpia el historial de conversación |
| `/history` | Muestra los mensajes de la sesión |
| `/sessions` | Lista sesiones guardadas |
| `/tokens` | Muestra el conteo de tokens acumulados |
| `/exit` o `/quit` | Sale del REPL |

---

## 📁 Estructura del proyecto

```
Klaus-code-cli/
├── Klaus/                    # Paquete principal
│   ├── cli.py               # Punto de entrada CLI (Typer)
│   ├── agent.py             # Loop del agente multi-turn
│   ├── repl.py              # REPL interactivo
│   ├── config.py            # Configuración (Pydantic)
│   ├── sessions.py          # Persistencia de sesiones
│   ├── streaming.py         # StreamRenderer (Rich live)
│   ├── context.py           # Gestión de contexto + auto-compact
│   ├── provider/            # Adapters de proveedor
│   │   ├── base.py          # ProviderAdapter (abstract)
│   │   ├── anthropic.py     # Adapter Anthropic API
│   │   └── openai_fmt.py    # Adapter OpenAI-compatible
│   ├── tools/               # Herramientas del agente
│   │   ├── files.py         # read_file, list_directory
│   │   ├── write.py         # write_file, edit_file, delete_file
│   │   ├── bash.py          # run_bash
│   │   ├── git.py           # git_status, git_diff, git_commit
│   │   └── search.py        # glob_search, grep_search
│   └── mcp/                 # Cliente MCP
│       └── client.py        # MCPRegistry
├── tests/                   # Suite pytest (41 tests)
├── docs/                    # Documentación detallada
├── .github/workflows/       # CI/CD (lint + typecheck + tests + release)
├── pyproject.toml           # Metadata + dependencias
└── CHANGELOG.md             # Historial de versiones
```

---

## 📚 Documentación

| Doc | Contenido |
|---|---|
| [📦 Installation](docs/installation.md) | Requisitos, pip install, config inicial, env vars |
| [💡 Usage](docs/usage.md) | Todos los comandos, flags y ejemplos |
| [⚙️ Configuration](docs/configuration.md) | Referencia completa de `~/.Klaus/config.yaml` |
| [🔧 Tools](docs/tools.md) | Las 11 tools integradas — cómo funcionan y cómo controlarlas |
| [🔌 MCP](docs/mcp.md) | Integración de servidores MCP externos |
| [🏗️ Architecture](docs/architecture.md) | Arquitectura interna — diagramas y módulos |

---

## 🤝 Contribuir

1. Fork del repositorio
2. `git checkout -b feat/mi-feature`
3. `pip install -e ".[dev]"` para instalar dependencias de desarrollo
4. `pytest` para ejecutar tests
5. `ruff check .` y `mypy Klaus/` para lint y tipado
6. Pull request contra `main`

---

## 📄 Licencia

MIT © Ka0s-Klaus
