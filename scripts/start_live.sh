#!/bin/bash
# =============================================================================
# start_live.sh — Launch the live trading engine and all supporting services
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting Intelligent Strategy Trading Platform..."

# ── 1. Activate Python virtual environment (if present) ──────────────────
if [ -d "venv" ]; then
  echo "  ├─ Activating Python virtual environment..."
  source venv/bin/activate
elif [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# ── 2. Start Go system monitor (background) ─────────────────────────────
if [ -f "monitor/main.go" ]; then
  echo "  ├─ Starting Go system monitor on :9090..."
  cd monitor
  go build -o bin/monitor . 2>/dev/null || echo "  │  (go build skipped — binary may already exist)"
  ./bin/monitor &
  MONITOR_PID=$!
  cd "$PROJECT_DIR"
  echo "  │  Monitor PID: $MONITOR_PID"
fi

# ── 3. Start Docker services (Redis + PostgreSQL) ───────────────────────
if command -v docker &> /dev/null; then
  echo "  ├─ Starting Docker services (redis, db)..."
  docker-compose -f docker-compose.dev.yml up -d db redis 2>/dev/null || true
fi

# ── 4. Start FastAPI application ────────────────────────────────────────
echo "  └─ Starting FastAPI server on :8000..."
python -m uvicorn ist.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --log-level info

# ── Cleanup on exit ─────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "🛑 Shutting down..."
  [ -n "${MONITOR_PID:-}" ] && kill "$MONITOR_PID" 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM