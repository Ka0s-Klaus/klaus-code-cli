#!/usr/bin/env bash
# Baseline de la batería de evaluación (Gate 0 del roadmap, #75).
#
# Uso:
#   evals/run_baseline.sh            # 4 modelos × 3 repeticiones
#   evals/run_baseline.sh -n 1       # pasada rápida (comprobar conexión)
#   MODELS="claude-haiku-5-5" evals/run_baseline.sh -n 1
#
# Variables:
#   MODELS       modelos externos (vía klaude-proxy, formato Anthropic; "" para omitirlos)
#   LOCAL_MODEL  modelo local en Ollama ("" para omitirlo)
#   OLLAMA_URL   endpoint OpenAI-compatible de Ollama
#   OUT_DIR      directorio de resultados
#
# Requisitos: KLAUS_API_KEY de la Claude Console (no vale una suscripción Pro),
# klaude-proxy accesible (KLAUS_PROXY_URL o config.yaml) y `ollama pull llama3.3`.
# Ver docs/evaluation.md#-baseline-gate-0-del-roadmap
set -euo pipefail

REPEAT=3
while getopts "n:" opt; do
  case "$opt" in
    n) REPEAT="$OPTARG" ;;
    *) echo "uso: $0 [-n repeticiones]" >&2; exit 2 ;;
  esac
done

MODELS="${MODELS-claude-opus-5-5 claude-sonnet-5-5 claude-haiku-5-5}"  # MODELS="" omite los externos
LOCAL_MODEL="${LOCAL_MODEL-llama3.3}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434/v1}"
OUT_DIR="${OUT_DIR:-evals/results}"
STAMP="$(date +%Y-%m-%d)"

cd "$(dirname "$0")/.."
mkdir -p "$OUT_DIR"

# La batería debe ser válida antes de gastar en modelos
klaus eval --verify-tasks

status=0
for model in $MODELS; do
  echo "── $model ──"
  klaus eval -m "$model" -n "$REPEAT" -o "$OUT_DIR/$STAMP-$model.json" || status=1
done

if [ -n "$LOCAL_MODEL" ]; then
  echo "── $LOCAL_MODEL (Ollama) ──"
  if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
    echo "Ollama no responde en ${OLLAMA_URL%/v1}; se omite $LOCAL_MODEL" >&2
    status=1
  else
    KLAUS_API_FORMAT=openai klaus eval -m "$LOCAL_MODEL" --base-url "$OLLAMA_URL" \
      -n "$REPEAT" -o "$OUT_DIR/$STAMP-${LOCAL_MODEL//:/_}.json" || status=1
  fi
fi

echo "Resultados en $OUT_DIR/"
exit $status
