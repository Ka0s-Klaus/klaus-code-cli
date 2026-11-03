# 🔐 Seguridad

> **Qué protege Klaus, qué no protege y cómo configurarlo para cada entorno.** Léelo antes de usar `--yolo` o de desplegar Klaus en el equipo de un cliente.

---

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago:** Describo el modelo de amenazas de Klaus y las barreras que lo limitan: workspace, confirmaciones, denylist y allowlist de bash, confianza en hooks y sub-agentes.

**¿Cómo lo hago:** Cada barrera está en una capa distinta (tools, despacho, hooks), y su configuración vive en la sección `security` de `~/.Klaus/config.yaml`. La política se fija al arrancar `klaus run` / `klaus repl` y la heredan los sub-agentes.

**¿Para qué lo hago:** Un agente que lee ficheros, escribe código y ejecuta comandos actúa con **tus permisos**. El modelo puede equivocarse o ser manipulado por contenido que lee (prompt injection en un README, un issue o una web). Las barreras acotan el daño posible en ambos casos.

---

## 🎯 Modelo de amenazas

| Amenaza | Ejemplo | Barrera |
|---|---|---|
| El modelo lee secretos fuera del proyecto | `read_file("~/.ssh/id_rsa")`, `../../.aws/credentials`, symlink hacia fuera | 📁 Workspace |
| El modelo escribe o borra fuera del proyecto | `write_file("~/.bashrc")` | 📁 Workspace |
| Comando destructivo por error | `rm -rf build /` (espacio de más) | 🧱 Denylist + ✅ confirmación |
| Comando arbitrario en modo desatendido | `--yolo` en CI ejecutando lo que pida el modelo | 📋 Allowlist de bash |
| Un repo clonado ejecuta código al usar Klaus | `.Klaus/hooks/PreToolUse` malicioso | 🪝 Confianza en hooks |
| Eludir confirmaciones o hooks delegando en un sub-agente | `spawn_agent("escribe ~/.bashrc")` | 🤖 Sub-agentes heredan la política |
| Datos personales hacia modelos externos | Rutas y username en el prompt | 🔒 [Pseudonymizer](configuration.md#-sección-pseudonymizer) |

---

## 🧱 Barreras

### 📁 Workspace

Las tools de ficheros (`read_file`, `list_directory`, `glob_search`, `grep_search`, `write_file`, `edit_file`, `delete_file`, `read_image`) y el `cwd` de `spawn_agent` solo operan **dentro del proyecto** más los directorios de `security.allowed_paths`.

- Las rutas se resuelven antes de comprobarlas: `~`, `..` y **symlinks** incluidos. Un enlace dentro del proyecto que apunta fuera cuenta como fuera.
- `glob_search` y `grep_search` descartan en silencio los resultados que caen fuera (patrones con `..`, enlaces).
- El modelo no puede cambiar el directorio de trabajo: si envía un argumento `cwd`, se descarta.

| `outside_workspace` | Con usuario delante (TTY) | Sin TTY (CI, pipes) |
|---|---|---|
| `ask` (default) | Pregunta, **también con `--yolo`**; lo aprobado vale para la sesión | ❌ Deniega |
| `deny` | ❌ Deniega | ❌ Deniega |

> ⚠️ **`run_bash` no está confinado.** Un comando shell puede acceder a cualquier ruta del usuario. Su barrera real es la confirmación (o la allowlist en modo desatendido).

### ✅ Confirmaciones

Las escrituras, `git_commit` y `run_bash` piden confirmación salvo con `--allow-writes`, `--allow-bash` o `--yolo` (ver [🔧 Tools](tools.md)). Las lecturas no piden confirmación, y por eso el workspace es su barrera.

### 🧱 Denylist de `run_bash`: *best effort*

Hay patrones que se bloquean **siempre**, sin opción de confirmar: `rm -rf` (en cualquier orden de flags), `find / -delete`, pipe a un intérprete de shell, ejecución de base64 decodificado, `eval $(...)`, escritura en `~/.ssh`, `dd`/`mkfs` sobre discos, fork bombs… La lista completa está en `klaus/tools/bash.py`.

> 🚨 **No es una frontera de seguridad.** Detecta errores y descuidos habituales, pero un comando ofuscado (variables, alias, scripts intermedios) puede evadirla. No relajes las confirmaciones confiando en ella.

### 📋 Allowlist de `run_bash` (modo desatendido)

Con bash auto-aprobado (`--allow-bash` / `--yolo`) y `security.bash_allowlist` definida, **solo** se ejecutan sin preguntar los comandos que cumplen dos condiciones:

1. Empiezan por un prefijo de la lista (`"pytest"`, `"git status"`…). Las asignaciones iniciales `VAR=valor` se ignoran.
2. Son simples: sin `;`, `&`, `|`, `` ` ``, `$(`, `>`, `<` ni saltos de línea.

Cualquier otro comando se confirma con el usuario, o se **rechaza** si no hay TTY. Una lista vacía (el default) mantiene el comportamiento anterior.

### 🪝 Confianza en hooks de proyecto

Los hooks de `~/.Klaus/hooks/` son tuyos y se ejecutan siempre. Los de `<proyecto>/.Klaus/hooks/` vienen con el repositorio, así que pueden ser de un tercero:

| `project_hooks` | Comportamiento |
|---|---|
| `ask` (default) | La primera vez pregunta y muestra los ficheros. La confianza se guarda en `~/.Klaus/trusted_hooks.json` asociada al **hash** del contenido: cualquier cambio vuelve a preguntar. Sin TTY no se ejecutan |
| `trust` | Siempre se ejecutan. Solo para repos propios en CI |
| `never` | Nunca se ejecutan |

Los hooks se ejecutan como subproceso asíncrono, con un timeout de 10 s, sin bloquear el agente.

> 💡 Si un hook de proyecto es una protección (un PreToolUse que bloquea), no confiar en él significa que **no protege**. Klaus avisa con `⚠️ Hooks de proyecto NO ejecutados`.

### 🤖 Sub-agentes

`spawn_agent` aplica la misma política que el agente que lo lanza:

- **Hereda las confirmaciones.** No puede aprobar escrituras ni bash que el padre no aprobaría, y no altera las confirmaciones del padre.
- Sus tools pasan por el mismo despacho: validación de parámetros y hooks PreToolUse/PostToolUse.
- Su `cwd` debe estar dentro del workspace.

---

## ⚙️ Configuración recomendada por entorno

**💻 Desarrollo local (default):** nada que tocar.

```yaml
security:
  outside_workspace: ask
  project_hooks: ask
```

**🏢 Equipo de un cliente / datos sensibles:**

```yaml
security:
  outside_workspace: deny
  project_hooks: never        # o ask, revisando cada hook
pseudonymizer:
  required: true
```

Y **sin** `--yolo`.

**🤖 CI / automatización con `--yolo`:**

```yaml
security:
  outside_workspace: deny
  project_hooks: trust        # solo si el repo es tuyo
  bash_allowlist: ["pytest", "ruff check", "mypy", "git status", "git diff"]
```

---

## ⚠️ Limitaciones conocidas

| Limitación | Mitigación |
|---|---|
| `run_bash` puede acceder a cualquier ruta | Confirmación interactiva; allowlist en modo desatendido; ejecutar Klaus en un contenedor para aislamiento real |
| La denylist es evadible | Es *best effort* por diseño; no sustituye a la confirmación |
| Las tools **MCP no piden confirmación** y no están confinadas al workspace (un servidor `filesystem` accede a lo que se le configure) | Configurar servidores MCP solo con el alcance mínimo. Seguimiento en una issue propia |
| `git_*` y `web_fetch` no pasan por el workspace | `git` opera sobre el repo del `cwd`; `web_fetch` no accede al disco |

---

## 📚 Documentación relacionada

| Doc | Contenido |
|---|---|
| [⚙️ Configuration](configuration.md) | Sección `security` y `pseudonymizer` |
| [🔧 Tools](tools.md) | Confirmaciones por tool |
| [🔌 MCP](mcp.md) | Servidores MCP y su alcance |
