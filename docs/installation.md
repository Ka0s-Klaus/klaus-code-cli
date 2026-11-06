---
tags: [proyecto/klaus-code-cli, tipo/guia, agente/configuracion]
---

# 📦 Instalación

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Instalar Klaus Code CLI y configurarlo para conectar con tu proveedor de IA preferido.

**¿Cómo lo hago?** Mediante `pip install`, generación de config inicial y configuración de variables de entorno con la API key.

**¿Para qué lo hago?** Para tener un agente de codificación operativo en tu terminal en menos de 5 minutos, apuntando a cualquier proveedor — Anthropic, OpenAI, LiteLLM local o Ollama.

---

## 📋 Requisitos

| Requisito | Versión mínima | Notas |
|---|---|---|
| 🐍 Python | 3.11+ | Recomendado: 3.12 |
| 📦 pip | 23+ | O `uv` para instalaciones más rápidas |
| 🔑 API Key | — | Anthropic / OpenAI / servidor compatible |
| 🖥️ Terminal | — | ANSI color support recomendado (iTerm2, Windows Terminal, etc.) |

---

## 🚀 Instalación

### Opción A — PyPI (recomendada)

```bash
pip install klaus-code-cli
```

### Opción B — desde source (desarrollo)

```bash
git clone https://github.com/Ka0s-klaus/klaus-code-cli.git
cd klaus-code-cli
pip install -e ".[dev]"
```

El grupo `dev` incluye: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

### Opción C — con `uv` (más rápido)

```bash
uv pip install klaus-code-cli
# O en un virtualenv aislado:
uv run --with klaus-code-cli klaus run "hola"
```

---

## ⚙️ Configuración inicial

### 1️⃣ Generar config por defecto

```bash
klaus init                      # perfil dev (desarrollo local, valores por defecto)
klaus init --profile cliente    # equipo de un cliente / datos sensibles
klaus init --profile ci         # CI / automatización con --yolo
```

Crea `~/.klaus/config.yaml` con todos los valores, comentados. El fichero es seguro para editar — sin credenciales embebidas. Si ya existe, no se toca: para cambiar de perfil, muévelo y repite `klaus init`.

| Perfil | Qué cambia respecto a `dev` |
|---|---|
| 💻 `dev` | nada |
| 🏢 `cliente` | `outside_workspace: deny`, `project_hooks: never`, `pseudonymizer.required: true`, ejemplo MCP con `confirm: always` |
| 🤖 `ci` | `outside_workspace: deny`, `project_hooks: trust`, `bash_allowlist` con `pytest`, `ruff check`, `mypy`, `git status`, `git diff` |

El porqué de cada ajuste está en [🔐 Security](security.md#️-configuración-recomendada-por-entorno).

### 2️⃣ Configurar la API key

La API key **nunca** va en el config.yaml. Se pasa como variable de entorno:

```bash
# Anthropic
export KLAUS_API_KEY="sk-ant-api03-..."

# OpenAI
export KLAUS_API_KEY="sk-proj-..."

# LiteLLM / servidor local (puede ser cualquier string si el servidor no requiere auth)
export KLAUS_API_KEY="dummy-key"
```

Añadir al `.bashrc` / `.zshrc` para que persista entre sesiones.

### 3️⃣ Apuntar al proveedor

Editar `~/.klaus/config.yaml`:

```yaml
provider:
  # Anthropic (producción)
  base_url: "https://api.anthropic.com"
  api_format: "anthropic"
  model: "claude-sonnet-4-6"

  # O LiteLLM local
  base_url: "http://localhost:8080/v1"
  api_format: "anthropic"   # LiteLLM expone formato Anthropic
  model: "claude-haiku-4-5-20251001"

  # O OpenAI
  base_url: "https://api.openai.com/v1"
  api_format: "openai"
  model: "gpt-4o"
```

### 4️⃣ Verificar

```bash
klaus config show
klaus run "di hola"
```

---

## 🔍 Escaneo automático del proyecto

```bash
klaus init --scan
```

Analiza el proyecto en el directorio actual y genera un fichero `KLAUS.md` con el contexto del proyecto — estructura, stack, convenciones detectadas. Este fichero se inyecta automáticamente como contexto del sistema en cada sesión.

---

## 🔗 Documentación relacionada

- [⚙️ Configuration](configuration.md) — referencia completa del config.yaml
- [💡 Usage](usage.md) — todos los comandos disponibles
