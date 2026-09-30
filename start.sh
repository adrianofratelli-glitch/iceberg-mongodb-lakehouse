#!/bin/bash
set -u

BASE="$(cd "$(dirname "$0")" && pwd)"
BACKEND_LOG="${TMPDIR:-/tmp}/iceberg-mongodb-backend.log"
FRONTEND_LOG="${TMPDIR:-/tmp}/iceberg-mongodb-frontend.log"

fail() {
  echo "❌ $1" >&2
  exit 1
}

cleanup() {
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}

wait_for_url() {
  local url="$1"
  local attempts="${2:-30}"
  for ((i = 1; i <= attempts; i++)); do
    if curl --fail --silent --max-time 2 "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

command -v curl >/dev/null || fail "curl não encontrado."
command -v npm >/dev/null || fail "npm não encontrado."
[[ -x "$BASE/backend/venv/bin/uvicorn" ]] || fail "Virtualenv do backend ausente. Veja o README."
[[ -d "$BASE/frontend/node_modules" ]] || fail "Dependências do frontend ausentes. Execute npm install em frontend/."
[[ -f "$BASE/.env" ]] || fail "Arquivo .env ausente. Copie .env.example e preencha."

for port in 8250 5250; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "Porta $port já está ocupada; o processo existente foi preservado."
  fi
done

echo "🧊 Iceberg + MongoDB"
echo "===================="

echo "▶ Iniciando backend (porta 8250)..."
cd "$BASE/backend"
UVICORN_ARGS=(main:app --host 127.0.0.1 --port 8250)
[[ "${POV_DEV:-0}" == "1" ]] && UVICORN_ARGS+=(--reload)
venv/bin/uvicorn "${UVICORN_ARGS[@]}" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "  PID: $BACKEND_PID"

if ! wait_for_url "http://127.0.0.1:8250/health/live" 30; then
  echo "❌ Backend não ficou pronto. Últimas linhas do log:" >&2
  tail -n 25 "$BACKEND_LOG" >&2
  cleanup
  exit 1
fi

echo "▶ Iniciando frontend (porta 5250)..."
cd "$BASE/frontend"
if [[ "${POV_DEV:-0}" != "1" ]] && {
  [[ ! -f dist/index.html ]] ||
  [[ -n "$(find src -type f -newer dist/index.html -print -quit)" ]] ||
  [[ package-lock.json -nt dist/index.html ]] ||
  [[ vite.config.js -nt dist/index.html ]];
}; then
  echo "  Gerando frontend otimizado..."
  npm run build > "$FRONTEND_LOG" 2>&1 || fail "Build do frontend falhou; veja $FRONTEND_LOG."
fi
if [[ "${POV_DEV:-0}" == "1" ]]; then
  FRONTEND_CMD=(node_modules/.bin/vite --host 127.0.0.1 --port 5250 --strictPort)
else
  FRONTEND_CMD=(node_modules/.bin/vite preview --host 127.0.0.1 --port 5250 --strictPort)
fi
"${FRONTEND_CMD[@]}" > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo "  PID: $FRONTEND_PID"

if ! wait_for_url "http://127.0.0.1:5250" 30; then
  echo "❌ Frontend não ficou pronto. Últimas linhas do log:" >&2
  tail -n 25 "$FRONTEND_LOG" >&2
  cleanup
  exit 1
fi

echo ""
echo "✅ PoV rodando!"
echo "   Frontend: http://localhost:5250"
echo "   API:      http://localhost:8250"
echo ""
echo "Para parar: kill $BACKEND_PID $FRONTEND_PID"

PREFLIGHT_STATUS="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 8 \
  "http://127.0.0.1:8250/preflight" || true)"
if [[ "$PREFLIGHT_STATUS" != "200" ]]; then
  echo "⚠️  Backend vivo, mas o preflight retornou HTTP ${PREFLIGHT_STATUS:-indisponível}."
fi

if [[ "${1:-}" == "--foreground" ]]; then
  trap cleanup INT TERM EXIT
  echo "Modo foreground ativo. Pressione Ctrl+C para encerrar."
  wait "$BACKEND_PID" "$FRONTEND_PID"
fi
