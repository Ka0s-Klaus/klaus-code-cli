# ⚙️ Configuración

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Personalizar el comportamiento de Klaus Code CLI — proveedor, modelo, confirmaciones, sesiones, límites de contexto y servidores MCP.

**¿Cómo lo hago?** Editando `~/.Klaus/config.yaml` (generado por `Klaus init`) o pasando flags en cada invocación de CLI.

**¿Para qué lo hago?** Para adaptar Klaus a cualquier entorno — desarrollo local con klaude-proxy, staging con otro proxy compatible — y para controlar el nivel de autonomía del agente según el contexto.

---

## 📁 Ubicación del fichero de config

```
~/.Klaus/config.yaml
```

Creado automáticamente por `Klaus init`. Si no existe, Klaus usa los valores por defecto de cada sección.

---

## 🤖 Integración con klaude-proxy

Klaus Code CLI se diseñó para conectarse exclusivamente a **klaude-proxy** — el proxy semántico con caché vectorial Qdrant que intercepta las llamadas a Anthropic y devuelve respuestas cacheadas ante preguntas similares.

### Variables de entorno (responsabilidad del usuario)

| Variable | Descripción | Ejemplo |
| --- | --- | --- |
| `KLAUDE_PROXY_URL` | URL completa del proxy, incluyendo `/v1` | `http://192.168.1.50:8080/v1` |
| `KLAUDE_API_KEY` | API key enviada al proxy como `x-api-key` | `sk-ant-api03-...` |

> 🔑 **Estas dos variables son responsabilidad del usuario** — no se definen en el config.yaml por motivos de seguridad. Cada entorno tiene su propio proxy y su propia key.

### Configuración mínima

```bash
# En ~/.bashrc, ~/.zshrc o el entorno de tu shell
export KLAUDE_PROXY_URL="http://192.168.1.50:8080/v1"
export KLAUDE_API_KEY="sk-ant-api03-..."
```

### Prioridad de configuración

```
KLAUDE_PROXY_URL (env) > config.yaml > default (localhost:8080/v1)
      │                       │                │
  más alta                  media           más baja
```

```mermaid
flowchart LR
    CLI["--base-url flag"] --> MRG["Merge final"]
    ENV["KLAUDE_PROXY_URL\nenv var"] --> MRG
    YAML["~/.Klaus/config.yaml\nbase_url"] --> MRG
    DEF["Default\nlocalhost:8080/v1"] --> MRG
    MRG --> CFG["KlausConfig.provider.base_url"]
```

> CLI flag > KLAUDE_PROXY_URL > config.yaml > default

---

## 🔌 Sección `provider`

Configura el proveedor de IA y el modelo.

```yaml
provider:
  # URL base de klaude-proxy (incluye /v1).
  # Sobreescribible sin tocar este fichero: export KLAUDE_PROXY_URL="http://<host>:8080/v1"
  base_url: "http://localhost:8080/v1"
  # Nombre de la variable de entorno con la API key.
  # Sobreescribible: export KLAUDE_API_KEY="sk-ant-..."
  api_key_env: "KLAUDE_API_KEY"
  api_format: "anthropic"                # Formato de API: "anthropic" | "openai"
  model: "claude-haiku-4-5-20251001"     # Modelo por defecto
  max_tokens: 4096                       # Máximo de tokens en la respuesta
  temperature: 0.2                       # Temperatura (0.0–1.0)
```

### Configuraciones habituales

| Escenario | `base_url` | `api_format` | Notas |
| --- | --- | --- | --- |
| **klaude-proxy local** | `http://localhost:8080/v1` | `anthropic` | Default — proxy en la misma máquina |
| **klaude-proxy en red** | `http://192.168.1.50:8080/v1` | `anthropic` | Proxy en otro host de la LAN |
| **Anthropic directo** | `https://api.anthropic.com` | `anthropic` | Sin proxy — coste y latencia directos |
| **Ollama** | `http://localhost:11434/v1` | `openai` | Modelos locales open-source |
| **OpenAI** | `https://api.openai.com/v1` | `openai` | GPT-4o y familia |

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
  timeout_seconds: 600       # Timeout por request al proveedor (600s para modelos thinking como kdev:latest)
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
