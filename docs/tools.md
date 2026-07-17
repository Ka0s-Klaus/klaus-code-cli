# 🔧 Tools

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago?** Proporcionar al agente un conjunto de herramientas con las que puede interactuar con el sistema de ficheros, ejecutar comandos, buscar en el código y operar con git.

**¿Cómo lo hago?** Cada tool es una función async registrada con un JSON Schema que el LLM usa para invocarla. Antes de ejecutar cualquier operación destructiva, la tool muestra un preview y pide confirmación.

**¿Para qué lo hago?** Para que el agente pueda completar tareas reales de codificación — leer ficheros, escribir cambios, ejecutar tests, hacer commits — con un humano en el loop que puede aprobar o rechazar cada acción.

---

## 📋 Catálogo de tools

| Tool | Módulo | Confirmación | Descripción |
|---|---|---|---|
| `read_file` | `tools/files.py` | ❌ Nunca | Lee el contenido de un fichero (con soporte de rango de líneas) |
| `list_directory` | `tools/files.py` | ❌ Nunca | Lista un directorio (respeta `.klausignore`) |
| `glob_search` | `tools/search.py` | ❌ Nunca | Busca ficheros por patrón glob |
| `grep_search` | `tools/search.py` | ❌ Nunca | Busca texto/regex en ficheros |
| `write_file` | `tools/write.py` | ✅ Siempre* | Crea o sobreescribe un fichero con diff preview |
| `edit_file` | `tools/write.py` | ✅ Siempre* | Edita un fichero reemplazando una cadena exacta |
| `delete_file` | `tools/write.py` | ✅ Siempre* | Elimina un fichero permanentemente |
| `run_bash` | `tools/bash.py` | ✅ Siempre* | Ejecuta un comando shell con timeout |
| `git_status` | `tools/git.py` | ❌ Nunca | Muestra el estado del repositorio git |
| `git_diff` | `tools/git.py` | ❌ Nunca | Muestra el diff (staged o unstaged) |
| `git_commit` | `tools/git.py` | ✅ Siempre* | Hace git add + git commit |

> *️⃣ *"Siempre" = salvo que `--yolo`, `--allow-writes` o `--allow-bash` estén activos.*

---

## 📖 Tools de lectura

### `read_file`

```
Lee el contenido completo de un fichero.
Trunca al límite configurado (max_file_read_lines) si el fichero es muy largo.
```

**Parámetros:**
- `path` (required) — ruta al fichero (absoluta o relativa al project dir)
- `start_line` (optional) — línea desde la que empezar (1-indexed)
- `end_line` (optional) — línea hasta la que leer inclusive

**Ejemplo de uso del agente:**
```
read_file("src/main.py", start_line=1, end_line=50)
```

### `list_directory`

**Parámetros:**
- `path` (optional) — directorio a listar (default: cwd)
- `recursive` (optional, default: false) — listar recursivamente

---

## 🔍 Tools de búsqueda

### `glob_search`

Busca ficheros por patrón glob. Respeta `.klausignore`.

```
glob_search("**/*.py")                    # Todos los ficheros Python
glob_search("tests/**/*_test.py")         # Tests con sufijo _test
glob_search("src/**/*.ts", base_path="./frontend")  # TypeScript en subdirectorio
```

### `grep_search`

Busca texto o expresiones regulares en ficheros.

```
grep_search("def parse_config", file_pattern="*.py")
grep_search("TODO|FIXME", case_sensitive=False, max_results=20)
grep_search("import.*requests", path="src/")
```

**Parámetros:**
- `pattern` (required) — texto o regex
- `path` (optional) — fichero o directorio donde buscar
- `file_pattern` (optional) — filtro glob para ficheros (e.g. `*.py`)
- `case_sensitive` (optional, default: false)
- `max_results` (optional, default: 50)

---

## ✏️ Tools de escritura

Todas muestran un **preview antes de ejecutar** y piden confirmación mediante el prompt enriquecido `[s/N/d/a]`:

| Opción | Acción |
|---|---|
| `s` / `sí` / `y` | Aprobar esta acción |
| `N` / `no` / Enter | Rechazar (no se ejecuta nada) |
| `d` | Ver el diff completo con números de línea |
| `a` | Aprobar esta y todas las acciones siguientes del plan actual |

### `write_file`

Crea o sobreescribe un fichero completo. Si el fichero existe, muestra un diff unificado.

**Parámetros:**
- `path` (required) — ruta destino
- `content` (required) — contenido completo a escribir

### `edit_file`

Edita un fichero existente reemplazando una cadena exacta. Más preciso que `write_file` para cambios puntuales.

**Parámetros:**
- `path` (required) — fichero a editar
- `old_string` (required) — cadena exacta a reemplazar (debe ser única)
- `new_string` (required) — reemplazo
- `replace_all` (optional, default: false) — reemplaza todas las ocurrencias

> ⚠️ Si `old_string` aparece más de una vez y `replace_all=false`, la tool devuelve un error y pide más contexto.

### `delete_file`

Elimina un fichero permanentemente.

**Parámetros:**
- `path` (required) — fichero a eliminar

---

## 💻 Tool de bash

### `run_bash`

Ejecuta un comando shell. Muestra el comando completo antes de ejecutar.

**Parámetros:**
- `command` (required) — comando shell a ejecutar
- `timeout` (optional, default: 30) — timeout en segundos

### 🔒 Patrones bloqueados siempre

Independientemente del modo (`--yolo` incluido), estos patrones están **permanentemente bloqueados**:

| Patrón | Riesgo |
|---|---|
| `rm -rf /` | Borrado del sistema de ficheros raíz |
| `rm -rf ~` | Borrado del home del usuario |
| `curl \| bash` / `wget \| sh` | Ejecución remota de código arbitrario |
| Fork bombs (`:(){ :|:& };:`) | Agotamiento de recursos del sistema |
| `dd if=... of=/dev/sd*` | Sobreescritura de discos |
| `mkfs.*` en dispositivos de bloque | Formateo de discos |

---

## 🔀 Tools de git

### `git_status`

Equivale a `git status --porcelain -b`. Solo lectura, sin confirmación.

### `git_diff`

**Parámetros:**
- `staged` (optional, default: false) — mostrar diff staged (`git diff --staged`)
- `path` (optional) — limitar a un fichero o directorio

### `git_commit`

Hace `git add` + `git commit`. Muestra un resumen y pide confirmación.

**Parámetros:**
- `message` (required) — mensaje de commit
- `paths` (optional) — lista de ficheros a añadir antes del commit
- `add_all` (optional, default: false) — equivalente a `git add -A`

---

## 🔗 Documentación relacionada

- [⚙️ Configuration](configuration.md) — cómo controlar confirmaciones globalmente
- [💡 Usage](usage.md) — flags `--yolo`, `--allow-writes`, `--allow-bash`
- [🔌 MCP](mcp.md) — tools adicionales vía MCP
