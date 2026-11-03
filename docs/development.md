# 🧪 Desarrollo y CI

> **Cómo reproducir en local exactamente lo que valida el CI.** Si estos tres comandos pasan en tu máquina, el PR pasará los checks.

---

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago:** Describo el entorno de desarrollo, los checks obligatorios (lint, tipado y tests) y las convenciones que mantienen el CI en verde.

**¿Cómo lo hago:** El workflow `.github/workflows/ci.yml` ejecuta en cada push y PR tres jobs independientes: `ruff check .`, `mypy .` y `pytest` en Python 3.11, 3.12 y 3.13. Esta guía replica esos jobs en local.

**¿Para qué lo hago:** Para que ningún cambio llegue a `main` con el CI roto (ver #54). Un CI rojo oculta regresiones reales: al restaurarlo aparecieron dos bugs de runtime que llevaban semanas en `main`.

---

## 🚀 Entorno local

### Requisitos
- Python 3.11+ (el CI cubre 3.11, 3.12 y 3.13)
- `git` y [`gh`](https://cli.github.com/) para el flujo issue → rama → PR

### Pasos

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # mismo set de dependencias que el CI
# opcional: pip install -e ".[dev,all]" para probar web/imagen
```

> ⚠️ El CI instala **solo** `.[dev]`. Si un test necesita un extra opcional (`web`, `multimodal`), debe saltarse limpiamente cuando el extra no esté (`pytest.importorskip`).

---

## ✅ Checks obligatorios

| Check | Comando | Config |
|---|---|---|
| 🧹 Lint | `ruff check .` | `[tool.ruff]` en `pyproject.toml` |
| 🔎 Tipado | `mypy .` | `[tool.mypy]` en `pyproject.toml` |
| 🧪 Tests | `pytest tests/ -v --tb=short` | `[tool.pytest.ini_options]` |
| 📏 Batería de evaluación | `klaus eval --verify-tasks` | `evals/tasks/` ([📏 Evaluation](evaluation.md)) |

Todo de una vez, antes de abrir un PR:

```bash
ruff check . && mypy . && pytest tests/ -q && klaus eval --verify-tasks
```

`ruff check . --fix` corrige automáticamente imports y modernizaciones (`UP`). Revisa el diff antes de commitear.

---

## 📐 Convenciones que evitan romper el CI

| Regla | Motivo |
|---|---|
| El paquete es **`klaus`** (minúsculas) en imports, `patch("klaus...")` y docstrings | En Linux y en el import system de Python, `Klaus` ≠ `klaus`. Fue la causa principal del CI roto (#54) |
| Imports solo para tipos → bloque `if TYPE_CHECKING:` | Evita imports circulares sin dejar nombres indefinidos (`F821`) |
| Los adaptadores de `provider/` respetan **la firma completa** de `ProviderAdapter` | Los llamadores pasan los mismos kwargs a todos (p. ej. `on_thinking`); una firma distinta revienta en runtime |
| Dependencias externas con API cambiante (p. ej. `mcp`) → acceso compatible entre versiones + test | `pyproject` admite `mcp>=1.0`, pero hoy se instala la 2.x |
| Tests aislados del entorno del desarrollador | `tests/conftest.py` limpia las variables `KLAUS_*`/`KLAUDE_*`, el estado de seguridad y desactiva confirmaciones |
| Nombres: ver [convención en CONTRIBUTING](../CONTRIBUTING.md#-convención-de-nombres). Variables `KLAUS_*` (alias obsoletos `KLAUDE_*`) | `tests/conftest.py` limpia ambas familias para aislar los tests |

---

## 🗂️ Estructura de tests

| Fichero | Cubre |
|---|---|
| `test_agent_dispatch.py` | Despacho de tools y validación de parámetros |
| `test_provider_openai.py` | Conversión de formatos y streaming del adaptador OpenAI |
| `test_mcp_client.py` | Compatibilidad de schemas MCP entre versiones del SDK |
| `test_tools_*.py` | Una suite por familia de tools |
| `test_sessions.py`, `test_checkpoints.py` | Persistencia y checkpoints |
| `test_config.py`, `test_context.py`, `test_hooks.py`, `test_streaming.py` | Configuración, contexto, hooks y renderizado |

---

## 📦 Release

La versión tiene **una sola fuente de verdad**: `[project].version` en `pyproject.toml`. `klaus.__version__` la lee de los metadatos del paquete instalado.

1. PR que sube `version` en `pyproject.toml` y mueve `[Unreleased]` del CHANGELOG a `[X.Y.Z] — fecha`
2. Tras el merge: `git tag vX.Y.Z && git push origin vX.Y.Z`
3. `.github/workflows/release.yml` **comprueba que el tag coincide** con la versión de `pyproject.toml` (si no, falla) y publica en PyPI por OIDC (trusted publishing, sin tokens)

> ℹ️ Las versiones `0.x` del CHANGELOG hasta `0.15.0` son **fases de desarrollo** y nunca se etiquetaron ni publicaron. La primera release real será la primera que se etiquete.

---

## 🤝 Contribuir

El flujo obligatorio (issue → rama → PR con aprobación humana) y la convención de nombres están en [🤝 CONTRIBUTING.md](../CONTRIBUTING.md).
