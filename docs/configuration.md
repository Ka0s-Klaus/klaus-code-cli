# ⚙️ Configuración

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Personalizar el comportamiento de Klaus Code CLI — proveedor, modelo, confirmaciones, sesiones, límites de contexto y servidores MCP.

**¿Cómo lo hago?** Editando `~/.Klaus/config.yaml` (generado por `Klaus init`) o pasando flags en cada invocación de CLI.

**¿Para qué lo hago?** Para adaptar Klaus a cualquier entorno — desarrollo local con Ollama, staging con LiteLLM, producción con Anthropic — y para controlar el nivel de autonomía del agente según el contexto.

---

## 📁 Ubicación del fichero de config

```
~/.Klaus/config.yaml
```

Creado automáticamente por `Klaus init`. Si no existe, Klaus usa los valores por defecto de cada sección.

---

## 🔌 Sección `provider`

Configura el proveedor de IA y el modelo.

```yaml
provider:
  base_url: "http://localhost:8080/v1"   # URL base del proveedor
  api_key_env: "KLAUS_API_KEY"           # Nombre de la env var con la API key
  api_format: "anthropic"                # Formato de API: "anthropic" | "openai"
  model: "claude-haiku-4-5-20251001"     # Modelo por defecto
  max_tokens: 4096                       # Máximo de tokens en la respuesta
  temperature: 0.2                       # Temperatura (0.0–1.0)
```

### Valores recomendados por proveedor

| Proveedor | `base_url` | `api_format` | Modelo ejemplo |
|---|---|---|---|
| **Anthropic directo** | `https://api.anthropic.com` | `anthropic` | `claude-sonnet-4-6` |
| **LiteLLM local** | `http://localhost:8080/v1` | `anthropic` | `claude-haiku-4-5-20251001` |
| **Ollama** | `http://localhost:11434/v1` | `openai` | `llama3.2` |
| **OpenAI** | `https://api.openai.com/v1` | `openai` | `gpt-4o` |
| **vLLM** | `http://localhost:8000/v1` | `openai` | `mistral-7b` |

> ⚠️ La API key **nunca** va en el config.yaml. Usa la variable de entorno definida en `api_key_env`.

---

## 🧠 Sección `behavior`

Controla el comportamiento del agente — confirmaciones, límite de turnos y modo plan.

```yaml
behavior:
  auto_approve_reads: true    # Las lecturas nunca piden confirmación
  auto_approve_writes: false  # Las escrituras piden confirmación (true = --allow-writes)
  auto_approve_bash: false    # Los comandos bash piden confirmación (true = --allow-bash)
  max_agent_turns: 25         # Máximo de llamadas al LLM por sesión de agente
  plan_mode: false            # Activar plan mode por defecto (--plan en CLI)
  streaming: true             # Streaming de respuestas por defecto
```

### Niveles de autonomía

```
Más seguro ◄─────────────────────────────────────────► Más autónomo
    │                                                        │
 default          --allow-writes          --yolo
 (todo pide       (escrituras auto,    (sin ninguna
 confirmación)    bash pide)           confirmación)
```

> 🔒 **Excepción de seguridad**: Los patrones peligrosos de bash (`rm -rf /`, `curl | bash`, fork bombs, etc.) están **siempre** bloqueados, incluso con `--yolo`.

---

## 💾 Sección `session`

Gestiona la persistencia del historial de conversación entre sesiones.

```yaml
session:
  storage_path: "~/.Klaus/sessions/"  # Directorio donde se guardan las sesiones
  persist: true                        # Guardar sesión en disco por defecto
  lock_enabled: true                   # File lock para prevenir escrituras concurrentes
```

---

## 🧠 Sección `context`

Controla los límites del contexto y el auto-compact.

```yaml
context:
  max_context_tokens: 100000    # Límite de tokens de contexto
  auto_compact: true            # Compactar automáticamente al llegar al 80% del límite
  max_file_read_lines: 2000     # Líneas máximas al leer un fichero
  max_Klaus_md_tokens: 4000     # Tokens máximos para CLAUS.md inyectado como contexto
```

### Cómo funciona el auto-compact

```mermaid
flowchart LR
    MSG["Mensajes acumulados"] --> EST["Estimar tokens"]
    EST --> CHK{"> 80% del límite?"}
    CHK -->|"No"| CONT["Continuar normalmente"]
    CHK -->|"Sí"| COMPACT["Compactar: eliminar\nmensajes intermedios\nconservando el primero\ny los últimos N"]
    COMPACT --> CONT
```

---

## 🌐 Sección `network`

Controla reintentos y timeouts hacia el proveedor.

```yaml
network:
  max_retries: 3             # Reintentos ante errores 5xx
  backoff_base_seconds: 1.5  # Base del backoff exponencial (1.5, 2.25, 3.375...)
  timeout_seconds: 120       # Timeout por request al proveedor
```

---

## 🔌 Sección `mcp_servers`

Define servidores MCP externos. Ver [🔌 MCP](mcp.md) para detalles.

```yaml
mcp_servers:
  - name: "filesystem"
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    env: {}

  - name: "postgres"
    command: ["npx", "-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: "postgresql://user:pass@localhost/mydb"
```

---

## 🔗 Documentación relacionada

- [📦 Installation](installation.md) — cómo instalar y generar el config inicial
- [💡 Usage](usage.md) — flags de CLI que hacen override del config
- [🔌 MCP](mcp.md) — configuración detallada de servidores MCP
