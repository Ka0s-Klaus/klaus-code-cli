# 🔌 MCP — Model Context Protocol

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Extender las capacidades del agente con herramientas externas (bases de datos, APIs, sistemas de ficheros remotos) a través del protocolo estándar MCP.

**¿Cómo lo hago?** Configurando servidores MCP en `~/.Klaus/config.yaml`. Klaus arranca cada servidor como un subproceso al iniciar la sesión, registra sus tools automáticamente y las hace disponibles al agente igual que las tools integradas.

**¿Para qué lo hago?** Para que el agente pueda interactuar con cualquier sistema externo sin necesidad de escribir código Python — basta con un servidor MCP compatible (hay decenas disponibles en npm y PyPI).

---

## ⚙️ Configuración

En `~/.Klaus/config.yaml`:

```yaml
mcp_servers:
  - name: "filesystem"
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    env: {}

  - name: "postgres"
    command: ["npx", "-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: "postgresql://user:pass@localhost/mydb"

  - name: "github"
    command: ["npx", "-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"
```

O via `--mcp-config` en CLI:

```bash
Klaus run "lista las tablas de la base de datos" --mcp-config ./mcp.json
Klaus repl --mcp-config ~/.Klaus/mcp-servers.json
```

El fichero JSON tiene el mismo formato que `mcp_servers` en el yaml.

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

- ⚠️ **Las tools MCP se ejecutan sin confirmación** y **no están confinadas al workspace** de Klaus. El agente muestra la llamada, pero no la detiene. Un servidor como `filesystem` accede a todo lo que se le configure.
- Configura cada servidor con el **alcance mínimo** (directorios, scopes de token) y evita servidores con efectos secundarios en sesiones `--yolo`.
- Las tools MCP sí pasan por los hooks PreToolUse/PostToolUse, que pueden bloquearlas. Ver [🔐 Security](security.md).
- Las credenciales en `env` deben ser variables de entorno, no valores literales. Usar la sintaxis `${VAR}` si el shell expande variables en el config.
- **Nunca** commitear `mcp.json` o secciones de `config.yaml` que contengan tokens o credenciales.

---

## 🔗 Documentación relacionada

- [⚙️ Configuration](configuration.md) — sección `mcp_servers` del config.yaml
- [🔧 Tools](tools.md) — tools integradas disponibles sin MCP
- [🏗️ Architecture](architecture.md) — cómo MCPRegistry se integra en el agente
