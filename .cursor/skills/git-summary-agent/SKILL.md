---
name: git-summary-agent
description: Summarize recent git history and working tree changes in Spanish, including the latest commit ID as a checkpoint. Use when the user asks for a git summary, wants to synchronize context with another AI/tool, or mentions aligning with another model on recent changes.
---

# Git Summary Agent

## Purpose

This skill helps the agent generate a concise but complete summary of recent git activity in this repository, tailored for synchronizing context between AI models (for example, between Cursor and Gemini).

The summary must:

- Be written in Spanish.
- Include the latest commit ID (HEAD) explicitly so future summaries can start "from that commit onward".
- Describe the main themes and intent of recent work (features, refactors, fixes, performance changes), not just file names.

## When to Use This Skill

Use this skill when:

- The user asks for a **resumen de git**, **historial de cambios**, or similar.
- The user wants to **alinear contexto con otro modelo** (e.g., Gemini) usando el historial de git.
- The user explicitly mentions:
  - "último id de commit",
  - "empezar el siguiente resumen desde aquí",
  - o "usar git para resumir cambios recientes".
- The user wants a periodic or repeated recap of changes in this repo.

If the user provides a specific starting commit hash, only summarize commits after that hash. If they do not, summarize the last 10–20 commits on the current branch plus any local, uncommitted changes.

## Workflow

When this skill applies, follow this process:

### 1. Identify Context and Scope

1. Determine the **current branch** and **HEAD commit**:
   - Run `git status -sb`.
   - Run `git log --oneline --decorate --graph -n 15`.
2. If the user provided a **previous checkpoint commit ID**, treat it as the "from" commit:
   - Use it in `git log <OLD_COMMIT>..HEAD --oneline --decorate --graph` for commits after that point.
3. If the user did *not* provide a checkpoint, default to the last 10–20 commits on the current branch (e.g., `-n 15`).

### 2. Inspect Changes

1. **Committed changes**:
   - Use `git log` output to identify:
     - New features,
     - Bug fixes,
     - Refactors,
     - Performance improvements,
     - Tooling / CI / docs changes.
   - When needed, run `git show --stat <commit>` or `git diff <commit>^!` for more detail on a specific commit.
2. **Uncommitted changes**:
   - Run `git diff` for unstaged changes.
   - Run `git diff --cached` for staged changes.
   - If there are many modified files, you can use `git diff --stat` to get an overview.

### 3. Synthesize the Summary (Spanish)

When writing the summary for the user:

1. **Encabezado básico**:
   - Indica rama actual.
   - Indica si hay cambios locales sin commitear.
   - Indica explícitamente el **HEAD actual** (último commit ID).
2. **Resumen de commits**:
   - Ordena desde lo más antiguo relevante hacia lo más nuevo (para dar narrativa).
   - Para cada commit relevante, incluye:
     - El hash corto (por ejemplo, `2e720ac`),
     - Un título claro de alto nivel (puede estar basado en el mensaje original, pero adaptado si ayuda),
     - 1–3 viñetas cortas describiendo el objetivo del cambio:
       - Tipo (nueva feature / refactor / fix / performance / tooling / docs),
       - Comportamiento o feature principal añadida o modificada,
       - Impacto en el juego o en el flujo de trabajo.
3. **Cambios locales** (si los hay):
   - Separa una subsección: "Cambios locales sin commitear".
   - Resume por archivo o por grupo de archivos lo que cambió (solo a alto nivel).
4. **Checkpoint para próximos resúmenes**:
   - Resalta el hash del HEAD actual como punto de corte.
   - Frase recomendada:
     - "El último commit actual es **`<HASH>`**. El próximo resumen puede empezar desde este commit hacia adelante."

### 4. Estilo de Respuesta

Sigue estas pautas de estilo:

- Escribe en **español claro y técnico**, manteniendo nombres de clases, funciones y archivos en inglés.
- Usa encabezados con `##` y `###` como máximo (no uses `#`).
- Usa viñetas (`- `) con palabras clave en **negrita** al inicio cuando resumas varios puntos.
- Mantén el resumen **conciso pero informativo**: enfócate en el "por qué" y el "qué", no tanto en el "cómo" del código.
- No pegues diffs de código grandes a menos que el usuario lo pida explícitamente.

### 5. Ejemplos de Formato de Salida

Ejemplo de estructura recomendada:

```markdown
## Estado actual

- **Branch actual**: fix/ghost-mode
- **Cambios locales**: sin cambios pendientes (working tree limpio).
- **HEAD actual (último commit)**: `2e720ac`

## Historial reciente (más relevante → más nuevo)

- **`120bfa6` – Visual Welcome + Ghost Participation**
  - **Tipo**: nueva feature de UX/gameplay.
  - **Contenido**: añade una bienvenida visual para nuevos usuarios y un sistema de participación "fantasma".

- **`4d7bdbf` – Optimización de GameEngine y física**
  - **Tipo**: optimización de rendimiento.
  - **Contenido**: ajusta parámetros de física y rutas críticas de `GameEngine` para mantener FPS estables.

- **`2e720ac` – Configuración y toggling de Ghost Mode** (HEAD)
  - **Tipo**: feature de configuración.
  - **Contenido**: permite configurar y activar/desactivar el modo ghost en tiempo de ejecución.

## Punto de corte para próximos resúmenes

El último commit actual es **`2e720ac`**. El próximo resumen puede empezar desde este commit hacia adelante.
```

### 6. Manejo de Errores y Casos Especiales

- Si el repositorio no tiene commits (caso muy raro aquí), explica que aún no hay historial de git para resumir.
- Si el hash proporcionado por el usuario no existe:
  - Indica brevemente el problema,
  - Propón usar el HEAD actual como nuevo punto de inicio,
  - Pregunta (si es relevante) si quieren que resumas "desde cero" o solo los últimos N commits.
- Si el historial es extremadamente largo, limita el resumen a un rango razonable (por ejemplo, últimos 20 commits) y menciónalo explícitamente.

## Notes for the Agent

- Assume the user already entiende git a nivel conceptual; no expliques qué es git o qué es un commit, salvo que lo pidan.
- Prioriza siempre la **visión de producto/juego**: cómo cambian las mecánicas, la UX del streamer/espectador y el rendimiento general.
- Mantén consistencia entre resúmenes sucesivos, reutilizando la misma estructura de secciones cuando sea posible.

