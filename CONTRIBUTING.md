---
tags: [proyecto/klaus-code-cli, tipo/guia, agente/herramientas]
---

# 🤝 Contribuir a Klaus Code CLI

> **Ningún cambio llega a `main` sin issue, rama y PR aprobado por una persona.** Esta guía explica el flujo y las convenciones del proyecto.

---

## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago:** Defino el flujo obligatorio de trabajo, la convención de nombres y los requisitos de un PR.

**¿Cómo lo hago:** Con un flujo issue → rama → PR verificado por el CI (`ruff`, `mypy` y `pytest` en 3.11 / 3.12 / 3.13), y una revisión humana antes de cada merge.

**¿Para qué lo hago:** Para que cada cambio sea trazable (por qué se hizo, qué se decidió) y para que `main` esté siempre en verde. Los commits directos a `main` dejaron el CI roto durante semanas (#54).

---

## 🔄 Flujo obligatorio

Aplica a **todo**: funcionalidades, fixes, refactors y documentación.

| Paso | Qué | Ejemplo |
|---|---|---|
| 1️⃣ **Issue** | Contexto, criterios de aceptación y referencias | `#57 fix(agent): doble ejecución de tools…` |
| 2️⃣ **Rama** | `<tipo>/<n-issue>-<descripcion-corta>` desde `main` | `fix/57-agent-loop-correctness` |
| 3️⃣ **Commits** | Referencian la issue: `tipo(ámbito): resumen (#n)` | `fix(agent): invocación única de tools (#57)` |
| 4️⃣ **Issue actualizada** | Decisiones tomadas y desviaciones respecto a los criterios | Comentario en la issue |
| 5️⃣ **PR** | Hacia `main`, con `Closes #n`, CI en verde y **aprobación humana** | Nunca merge sin revisión |

**Tipos de rama/commit:** `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`.

```bash
gh issue create -t "fix(x): …" -F cuerpo.md
git switch main && git pull
git switch -c fix/<n>-<descripcion>
# … cambios + tests …
ruff check . && mypy . && pytest tests/ -q
git commit -m "fix(x): … (#<n>)"
git push -u origin HEAD
gh pr create --base main --fill   # añadir "Closes #<n>" al cuerpo
```

---

## ✅ Checklist del PR

- [ ] `ruff check .`, `mypy .` y `pytest` en verde (ver [🧪 Development](docs/development.md))
- [ ] Tests de regresión para cada bug corregido
- [ ] Documentación actualizada si cambia algún comportamiento visible (`docs/`, README, `klaus init`)
- [ ] Entrada en `CHANGELOG.md` → `[Unreleased]`
- [ ] La documentación sigue [📚 DOCUMENTATION_STYLE.md](DOCUMENTATION_STYLE.md)
- [ ] `Closes #<n>` en el cuerpo del PR

---

## 🔤 Convención de nombres

| Ámbito | Nombre | Nombre anterior (obsoleto, aún aceptado) |
|---|---|---|
| Paquete Python y comando | `klaus` | `Klaus` |
| Directorio de usuario | `~/.klaus/` | `~/.Klaus/` |
| Directorio de proyecto | `<proyecto>/.klaus/` (hooks, commands) | `<proyecto>/.Klaus/` |
| Fichero de contexto | `KLAUS.md` (fallback: `CLAUDE.md`) | `CLAUS.md` |
| Fichero de exclusiones | `.klausignore` | — |
| Variables de entorno | `KLAUS_PROXY_URL`, `KLAUS_API_KEY`, `KLAUS_MODEL`, `KLAUS_API_FORMAT` | `KLAUDE_*` |
| Claves de config | `snake_case` en minúsculas (`max_klaus_md_tokens`) | `max_Klaus_md_tokens` |
| Nombre del producto en prosa | **Klaus Code CLI** / **Klaus** | — |
| Clases Python | `PascalCase` (`KlausConfig`) | — |

- Los nombres obsoletos siguen funcionando con un aviso, una vez por proceso (`klaus/compat.py`). Código nuevo y documentación nueva usan **solo** los canónicos.
- **klaude-proxy** es otro componente y conserva su nombre.

---

## 🔐 Seguridad

Los cambios en tools, despacho, hooks o sub-agentes deben respetar el modelo de [🔐 Security](docs/security.md): workspace, confirmaciones y hooks. Si introduces una vía nueva de ejecución, pasa por `_dispatch_tool` y añade tests en `tests/test_security.py`.

---

## 📄 Licencia

Al contribuir aceptas que tu código se publique bajo la [licencia MIT](LICENSE) del proyecto.
