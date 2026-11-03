# 🔌 MCP — Model Context Protocol

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Extender las capacidades del agente con herramientas externas (bases de datos, APIs, sistemas de ficheros remotos) a través del protocolo estándar MCP.

**¿Cómo lo hago?** Configurando servidores MCP en `~/.klaus/config.yaml`. Klaus arranca cada servidor como un subproceso al iniciar la sesión, registra sus tools automáticamente y las hace disponibles al agente igual que las tools integradas.

**¿Para qué lo hago?** Para que el agente pueda interactuar con cualquier sistema externo sin necesidad de escribir código Python — basta con un servidor MCP compatible (hay decenas disponibles en npm y PyPI).

---

## ⚙️ Configuración

En `~/.klaus/config.yaml`:

```yaml
mcp_servers:
  - name: "filesystem"
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    env: {}
    confirm: "auto"           # auto | always | never (ver "Confirmación")
    trust_read_only: true     # en auto: no preguntar en tools declaradas de solo lectura

  - name: "postgres"
    command: ["npx", "-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: "postgresql://user:pass@localhost/mydb"

  - name: "github"
    command: ["npx", "-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"
```

> ℹ️ Los servidores MCP se configuran **solo** en `mcp_servers` de `~/.klaus/config.yaml`. La opción `--mcp-config` que mencionaban versiones anteriores de esta guía no está implementada.

---

## ✅ Confirmación

Cada tool MCP puede tener efectos fuera de tu máquina (crear issues, escribir en una base de datos, borrar ficheros), así que se trata como una escritura. La política se fija **por servidor** con `confirm`:

| `confirm` | Tool de solo lectura¹ | Tool con efectos | Con `--allow-writes` / `--yolo` | Sin TTY (CI) |
|---|---|---|---|---|
| `auto` (default) | ✅ Sin preguntar | ❓ Pregunta | ✅ Sin preguntar | ❌ Deniega lo que habría preguntado |
| `always` | ❓ Pregunta | ❓ Pregunta | ❓ **Pregunta igualmente** | ❌ Deniega |
| `never` | ✅ Sin preguntar | ✅ Sin preguntar | ✅ Sin preguntar | ✅ Ejecuta |

¹ Tools en las que el servidor declara `annotations.readOnlyHint: true`. El agente las ve marcadas como `[MCP:servidor · solo lectura]`. Con `trust_read_only: false`, el hint se ignora y se pregunta también por ellas.

> 💡 **¿Por qué confiar en el hint por defecto?** El servidor MCP ya es código que se ejecuta en tu máquina con tus permisos: si quisiera hacer daño, no necesitaría mentir en un hint. Si el servidor es de un tercero y no lo has revisado, usa `trust_read_only: false` o `confirm: always`.

Al denegar o cancelar, el modelo recibe un resultado explicativo (`status: cancelled` o `error`) y puede seguir con otra estrategia.

---

## 🚀 Ciclo de vida de un servidor MCP

```mermaid
sequenceDiagram
    participant K as Klaus CLI
    participant R as MCPRegistry
    participant S as MCP Server

    K->>R: inicializar()
    loop Por cada servidor configurado
        R->>S: subprocess.Popen(command, env)
        R->>S: initialize request (JSON-RPC)
        S-->>R: capabilities + tool schemas
        R->>R: Registrar tools del servidor
    end
    Note over K,R: Sesión activa — tools disponibles para el agente

    K->>R: shutdown()
    loop Por cada servidor
        R->>S: SIGTERM
        S-->>R: proceso termina
    end
```

---

## 🔧 Servidores MCP recomendados

| Servidor | Package npm | Uso |
|---|---|---|
| **filesystem** | `@modelcontextprotocol/server-filesystem` | Acceso a ficheros fuera del cwd |
| **postgres** | `@modelcontextprotocol/server-postgres` | Consultas SQL a PostgreSQL |
| **sqlite** | `@modelcontextprotocol/server-sqlite` | Base de datos SQLite |
| **github** | `@modelcontextprotocol/server-github` | Issues, PRs, repos de GitHub |
| **fetch** | `@modelcontextprotocol/server-fetch` | HTTP requests |
| **puppeteer** | `@modelcontextprotocol/server-puppeteer` | Browser automation |
| **memory** | `@modelcontextprotocol/server-memory` | Knowledge graph persistente |

---

## 🔒 Seguridad

- Las tools con efectos **piden confirmación** según `confirm` (ver [✅ Confirmación](#-confirmación)).
- ⚠️ Las tools MCP **no están confinadas al workspace** de Klaus: el alcance lo decide el servidor. Un servidor `filesystem` accede a todo lo que se le configure. Configura cada servidor con el **alcance mínimo** (directorios, scopes de token).
- Con `--yolo`, las tools con efectos de servidores en `auto` se ejecutan sin preguntar. Para servidores críticos (producción, datos de cliente), usa `confirm: always`.
- Las tools MCP pasan por el mismo despacho que las integradas: validación de parámetros requeridos y hooks PreToolUse/PostToolUse, que pueden bloquearlas. Ver [🔐 Security](security.md).
- Las credenciales en `env` deben ser variables de entorno, no valores literales. Usar la sintaxis `${VAR}` si el shell expande variables en el config.
- **Nunca** commitear `mcp.json` o secciones de `config.yaml` que contengan tokens o credenciales.

---

## 🔗 Documentación relacionada

- [⚙️ Configuration](configuration.md) — sección `mcp_servers` del config.yaml
- [🔧 Tools](tools.md) — tools integradas disponibles sin MCP
- [🏗️ Architecture](architecture.md) — cómo MCPRegistry se integra en el agente
