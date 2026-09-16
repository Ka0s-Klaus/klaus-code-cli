# 📚 Guía de Estilo de Documentación

Este documento define el estándar de formato para toda la documentación del proyecto **Klaus-code-cli** a partir de septiembre 2026.

## 🎯 Estructura de README.md

### Portada
```markdown
# 🤖 Nombre del Proyecto

> **Tagline en negrita.** Contexto adicional.

[![Badge1](url)](url) [![Badge2](url)](url)

---
```

### Sección: "¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?"
```markdown
## 🤔 ¿Qué hago? ¿Cómo lo hago? ¿Y para qué lo hago?

**¿Qué hago:** [Párrafo descripción]
**¿Cómo lo hago:** [Párrafo técnica]
**¿Para qué lo hago:** [Párrafo valor]

---
```

### Características
```markdown
## 🎯 Características principales

| Feature | Descripción |
|---|---|
| 🔌 Feature 1 | Descripción |
| 💬 Feature 2 | Descripción |

---
```

### Instalación
```markdown
## 🚀 Instalación rápida

### Requisitos
- Python 3.11+
- [Otra req]

### Pasos

\`\`\`bash
comando 1
comando 2
\`\`\`

---
```

### Uso
```markdown
## 💡 Uso

### Modo 1
[Descripción y código]

### Modo 2
[Descripción y código]

| Comando | Acción |
|---|---|
| `/help` | Muestra ayuda |
| `/exit` | Sale |

---
```

### Arquitectura
```markdown
## 🏗️ Arquitectura

\`\`\`mermaid
graph TD
    A["Component A"] --> B["Component B"]
\`\`\`

**Stack:**
- Componente: tecnología

---
```

### Documentación
```markdown
## 📚 Documentación

| Doc | Contenido |
|---|---|
| [📦 Installation](docs/install.md) | Setup |
| [💡 Usage](docs/usage.md) | Comandos |
| [⚙️ Configuration](docs/config.md) | Config |

---
```

### Contribuir
```markdown
## 🤝 Contribuir

1. Fork el repositorio
2. Rama: `git checkout -b feat/feature`
3. Commit: `git commit -m "Add feature"`
4. Push y PR

---

## 📄 Licencia

[MIT](LICENSE) © Ka0s-Klaus
```

## 🎨 Emojis consistentes

| Sección | Emoji |
|---|---|
| Título | 🤖 (proyecto) |
| ¿Qué? | 🤔 |
| Características | 🎯 |
| Instalación | 🚀 |
| Uso | 💡 |
| Arquitectura | 🏗️ |
| Documentación | 📚 |
| Tests | 🧪 |
| Contribuir | 🤝 |
| Licencia | 📄 |

## ✅ Checklist

- [ ] Portada con emoji + tagline + badges
- [ ] Sección "¿Qué? ¿Cómo? ¿Para qué?"
- [ ] Separadores `---`
- [ ] Características en tabla con emojis
- [ ] Instalación con requisitos y pasos
- [ ] Uso con ejemplos en bash
- [ ] Arquitectura con Mermaid (si aplica)
- [ ] Documentación: tabla con links a docs/
- [ ] Contribuir: pasos claros
- [ ] Licencia MIT

## 📝 Ver README.md como referencia aplicada.
