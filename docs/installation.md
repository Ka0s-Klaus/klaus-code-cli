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
pip install Klaus-code-cli
```

### Opción B — desde source (desarrollo)

```bash
git clone https://github.com/Ka0s-Klaus/Klaus-code-cli.git
cd Klaus-code-cli
pip install -e ".[dev]"
```

El grupo `dev` incluye: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

### Opción C — con `uv` (más rápido)

```bash
uv pip install Klaus-code-cli
# O en un virtualenv aislado:
uv run --with Klaus-code-cli Klaus run "hola"
```

---

## ⚙️ Configuración inicial

### 1️⃣ Generar config por defecto

```bash
Klaus init
```

Crea `~/.Klaus/config.yaml` con todos los valores por defecto. El fichero es seguro para editar — sin credenciales embebidas.

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

Editar `~/.Klaus/config.yaml`:

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
Klaus config show
Klaus run "di hola" --no-stream
```

---

## 🔍 Escaneo automático del proyecto

```bash
Klaus init --scan
```

Analiza el proyecto en el directorio actual y genera un fichero `CLAUS.md` con el contexto del proyecto — estructura, stack, convenciones detectadas. Este fichero se inyecta automáticamente como contexto del sistema en cada sesión.

---

## 🔗 Documentación relacionada

- [⚙️ Configuration](configuration.md) — referencia completa del config.yaml
- [💡 Usage](usage.md) — todos los comandos disponibles
