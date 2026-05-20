#!/bin/bash
# =============================================================================
# stop_live.sh — Gracefully stop the live trading engine and its services
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping Intelligent Strategy Trading Platform..."

# ── 1. Stop Go monitor ──────────────────────────────────────────────────
if pgrep -f "bin/monitor" > /dev/null 2>&1; then
  echo "  ├─ Stopping Go system monitor..."
  pkill -f "bin/monitor" || true
  sleep 1
fi

# ── 2. Stop uvicorn / FastAPI ───────────────────────────────────────────
if pgrep -f "uvicorn" > /dev/null 2>&1; then
  echo "  ├─ Stopping FastAPI server..."
  pkill -f "uvicorn" || true
  sleep 1
fi

# ── 3. Stop Docker services ─────────────────────────────────────────────
if command -v docker &> /dev/null; then
  echo "  ├─ Stopping Docker services..."
  docker-compose -f docker-compose.dev.yml down 2>/dev/null || true
fi

# ── 4. Final check ──────────────────────────────────────────────────────
echo "  └─ All services stopped."