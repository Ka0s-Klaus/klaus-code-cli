# ⚙️ Configuración

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Personalizar el comportamiento de Klaus Code CLI — proveedor, modelo, confirmaciones, sesiones, límites de contexto y servidores MCP.

**¿Cómo lo hago?** Editando `~/.klaus/config.yaml` (generado por `klaus init`) o pasando flags en cada invocación de CLI.

**¿Para qué lo hago?** Para adaptar Klaus a cualquier entorno — desarrollo local con klaude-proxy, staging con otro proxy compatible — y para controlar el nivel de autonomía del agente según el contexto.

---

## 📁 Ubicación del fichero de config

```
~/.klaus/config.yaml
```

Creado automáticamente por `klaus init`. Si no existe, Klaus usa los valores por defecto de cada sección.

> ♻️ **Migración desde `~/.Klaus`:** si solo existe el directorio con el nombre anterior, Klaus lo sigue usando y avisa al arrancar con el comando exacto para renombrarlo (`mv ~/.Klaus ~/.klaus`). Lo mismo con `<proyecto>/.Klaus`. Klaus nunca mueve tus datos automáticamente. En macOS (sistema de ficheros sin distinción de mayúsculas) ambos nombres son el mismo directorio y no hay nada que hacer.
>
> La clave `context.max_Klaus_md_tokens` se renombra a `max_klaus_md_tokens`; la anterior se acepta con aviso.

---

## 🤖 Integración con klaude-proxy

Klaus Code CLI se diseñó para conectarse exclusivamente a **klaude-proxy** — el proxy semántico con caché vectorial Qdrant que intercepta las llamadas a Anthropic y devuelve respuestas cacheadas ante preguntas similares.

### Variables de entorno (responsabilidad del usuario)

| Variable | Descripción | Ejemplo |
| --- | --- | --- |
| `KLAUS_PROXY_URL` | URL completa del proxy, incluyendo `/v1` | `http://192.168.1.50:8080/v1` |
| `KLAUS_API_KEY` | API key enviada al proxy como `x-api-key` | `sk-ant-api03-...` |

> 🔑 **Estas dos variables son responsabilidad del usuario** — no se definen en el config.yaml por motivos de seguridad. Cada entorno tiene su propio proxy y su propia key.

Otras variables: `KLAUS_MODEL` y `KLAUS_API_FORMAT` (sobrescriben `provider.model` y `provider.api_format`).

> ♻️ **Migración desde `KLAUDE_*`:** los nombres anteriores (`KLAUDE_PROXY_URL`, `KLAUDE_API_KEY`, `KLAUDE_MODEL`, `KLAUDE_API_FORMAT`) siguen funcionando, con un aviso de obsolescencia. Si están definidos los dos, gana `KLAUS_*`. Renómbralos en tu shell:
>
> ```bash
> sed -i.bak -E 's/KLAUDE_(PROXY_URL|API_KEY|MODEL|API_FORMAT)/KLAUS_\1/g' ~/.zshrc
> ```

### Configuración mínima

```bash
# En ~/.bashrc, ~/.zshrc o el entorno de tu shell
export KLAUS_PROXY_URL="http://192.168.1.50:8080/v1"
export KLAUS_API_KEY="sk-ant-api03-..."
```

### Prioridad de configuración

```
KLAUS_PROXY_URL (env) > config.yaml > default (localhost:8080/v1)
      │                       │                │
  más alta                  media           más baja
```

```mermaid
flowchart LR
    CLI["--base-url flag"] --> MRG["Merge final"]
    ENV["KLAUS_PROXY_URL\nenv var"] --> MRG
    YAML["~/.klaus/config.yaml\nbase_url"] --> MRG
    DEF["Default\nlocalhost:8080/v1"] --> MRG
    MRG --> CFG["KlausConfig.provider.base_url"]
```

> CLI flag > KLAUS_PROXY_URL > config.yaml > default

---

## 🔌 Sección `provider`

Configura el proveedor de IA y el modelo.

```yaml
provider:
  # URL base de klaude-proxy (incluye /v1).
  # Sobreescribible sin tocar este fichero: export KLAUS_PROXY_URL="http://<host>:8080/v1"
  base_url: "http://localhost:8080/v1"
  # Nombre de la variable de entorno con la API key.
  # Sobreescribible: export KLAUS_API_KEY="sk-ant-..."
  api_key_env: "KLAUS_API_KEY"
  api_format: "anthropic"                # Formato de API: "anthropic" | "openai"
  model: "claude-haiku-4-5-20251001"     # Modelo por defecto
  max_tokens: 16000                      # Máximo de tokens por respuesta, razonamiento incluido
  temperature: 0.2                       # Temperatura (0.0–1.0)
```

### Configuraciones habituales

| Escenario | `base_url` | `api_format` | Notas |
| --- | --- | --- | --- |
| **klaude-proxy local** | `http://localhost:8080/v1` | `anthropic` | Default — proxy en la misma máquina |
| **klaude-proxy en red** | `http://192.168.1.50:8080/v1` | `anthropic` | Proxy en otro host de la LAN |
| **Anthropic directo** | `https://api.anthropic.com` | `anthropic` | Sin proxy: coste y latencia directos y **sin seudonimización** (ver [🔒 pseudonymizer](#-sección-pseudonymizer)) |
| **Ollama** | `http://localhost:11434/v1` | `openai` | Modelos locales open-source |
| **OpenAI** | `https://api.openai.com/v1` | `openai` | GPT-4o y familia, **sin seudonimización** |

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
  max_agent_depth: 3          # Profundidad máxima de sub-agentes anidados (spawn_agent)
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

> 🔒 **Lo que `--yolo` no desactiva:** la denylist de bash (*best effort*), el confinamiento al workspace de las tools de ficheros, la `bash_allowlist` (si está definida) y la confianza en hooks de proyecto. Ver [🔐 Security](security.md).

---

## 💾 Sección `session`

Gestiona la persistencia del historial de conversación entre sesiones.

```yaml
session:
  storage_path: "~/.klaus/sessions/"  # Directorio donde se guardan las sesiones
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
  max_klaus_md_tokens: 4000     # Tokens máximos para KLAUS.md inyectado como contexto
```

### Cómo funciona el auto-compact

```mermaid
flowchart LR
    RESP["Respuesta del modelo"] --> CTX["Contexto actual =\ninput_tokens de esa respuesta"]
    CTX --> CHK{"≥ 80% de\nmax_context_tokens?"}
    CHK -->|"No"| CONT["Continuar normalmente"]
    CHK -->|"Sí"| COMPACT["Compactar: conservar el primero\n+ marcador + los últimos 6,\nsin tool_result huérfanos"]
    COMPACT --> CONT
```

- **Contexto actual ≠ consumo.** Cada petición reenvía el historial completo, así que el `input_tokens` de la última respuesta *es* el tamaño del contexto. La línea de estado muestra ambos: `📊 contexto: 42,000 (42%) | consumo — input: 180,000 · output: 3,200`. El consumo acumulado es lo que se factura; no se usa para decidir la compactación.
- Se comprueba tras cada respuesta del modelo, también en turnos sin tools del REPL.
- Si la ventana recortada empezaría por un `tool_result` cuyo `tool_use` se ha eliminado, ese mensaje se descarta también: la API rechaza resultados huérfanos.

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

## 🔒 Sección `pseudonymizer`

Klaus registra en klaude-proxy los datos que identifican al usuario (**ruta del proyecto, home y username**). Así el proxy los sustituye por seudónimos antes de enviar la petición a un modelo externo.

```yaml
pseudonymizer:
  enabled: true                 # Registrar los literales en el proxy
  required: false               # true → abortar si no se puede garantizar la seudonimización
  local_models: ["kdev*", "ollama/*", "ollama_chat/*"]   # Glob, sin distinguir mayúsculas
  timeout_seconds: 2.0          # Tope total de la llamada al proxy
```

### Cuándo se configura

El registro se **espera** (con un máximo de `timeout_seconds`) **antes de la primera petición al modelo** en todos los caminos:

| Camino | Momento |
| --- | --- |
| `klaus run` | Al arrancar, antes del primer turno |
| `klaus repl` | Al arrancar la sesión |
| `/model <nombre>` | Al cambiar de modelo (p. ej. de local a externo) |
| `spawn_agent` | Antes de lanzar el sub-agente, que puede usar otro modelo |

Un registro correcto se recuerda durante el proceso: los sub-agentes y los cambios de modelo posteriores no repiten la llamada.

### Qué cuenta como modelo local

**Solo los modelos que coinciden con `local_models`.** Cualquier otro se trata como externo y se configura. Los nombres en formato LiteLLM (`openai/gpt-4o`, `anthropic/claude-...`) son **externos**, aunque contengan `/`.

> 💡 Si usas Ollama directamente con nombres sin prefijo (`llama3`), añádelos a `local_models` (p. ej. `"llama3*"`) para evitar el aviso.

### Qué pasa si falla

| Situación | `required: false` (default) | `required: true` |
| --- | --- | --- |
| Proxy caído, timeout o error HTTP | ⚠️ Aviso y continúa | 🔒 Aborta sin llamar al modelo (`/model` mantiene el modelo anterior) |
| `base_url` apunta a la API pública de un proveedor (sin proxy) | ⚠️ Aviso y continúa. **No se envía nada** al endpoint de configuración | 🔒 Aborta |
| Modelo en `local_models` | ✅ Continúa sin configurar | ✅ Continúa sin configurar |

> 🔐 **Despliegues con cliente / datos sensibles:** usa `required: true`. Es la única forma de garantizar que ninguna petición salga hacia un modelo externo sin seudonimizar. Con `false`, Klaus prioriza la disponibilidad y solo avisa.

> ⚠️ **Limitación conocida:** el registro vive en memoria del proxy. Si klaude-proxy se reinicia durante una sesión de Klaus, hay que reiniciar Klaus para volver a registrar los literales.

---

## 🛡️ Sección `security`

Límites del agente. El detalle y el modelo de amenazas están en [🔐 Security](security.md).

```yaml
security:
  allowed_paths: []            # Directorios extra (además del proyecto) para las tools de ficheros
  outside_workspace: "ask"     # "ask" (pregunta incluso en --yolo; sin TTY deniega) | "deny"
  project_hooks: "ask"         # Hooks de <proyecto>/.klaus/hooks: "ask" | "trust" | "never"
  bash_allowlist: []           # Con bash auto-aprobado, solo estos prefijos corren sin preguntar
```

| Clave | Default | Efecto |
| --- | --- | --- |
| `allowed_paths` | `[]` | Rutas (admiten `~`) accesibles además del proyecto |
| `outside_workspace` | `ask` | Qué hacer con rutas fuera del workspace |
| `project_hooks` | `ask` | Confianza por hash, guardada en `~/.klaus/trusted_hooks.json` |
| `bash_allowlist` | `[]` | Vacío = sin filtro. Ej.: `["pytest", "ruff check", "git status"]` |

---

## 🔌 Sección `mcp_servers`

Define servidores MCP externos. Ver [🔌 MCP](mcp.md) para detalles.

```yaml
mcp_servers:
  - name: "filesystem"
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    env: {}
    confirm: "auto"            # auto | always | never
    trust_read_only: true      # en auto, no preguntar en tools con readOnlyHint

  - name: "postgres"
    command: ["npx", "-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: "postgresql://user:pass@localhost/mydb"
```

| Clave | Default | Efecto |
| --- | --- | --- |
| `name` | — | Prefijo de las tools: `mcp_<name>_<tool>` |
| `command` | — | Comando que arranca el servidor (stdio) |
| `env` | `{}` | Variables extra; `${VAR}` se expande desde el entorno |
| `confirm` | `auto` | Confirmación de sus tools ([✅ detalle](mcp.md#-confirmación)) |
| `trust_read_only` | `true` | En `auto`, confiar en `readOnlyHint` del servidor |

---

## 🔗 Documentación relacionada

- [📦 Installation](installation.md) — cómo instalar y generar el config inicial
- [💡 Usage](usage.md) — flags de CLI que hacen override del config
- [🔌 MCP](mcp.md) — configuración detallada de servidores MCP
