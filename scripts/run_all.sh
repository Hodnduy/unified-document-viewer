#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# run_all.sh — Start the entire Unified Document Viewer stack with one command.
#
# Launches:
#   1. Mock Sales API        (port 8001)
#   2. Mock Service API      (port 8002)
#   3. Main Application API  (port 8000)
#
# Usage:
#   ./scripts/run_all.sh          # start all servers
#   ./scripts/run_all.sh --stop   # kill all background servers
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$PROJECT_DIR/.pids"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

# ── Stop mode ────────────────────────────────────────────────────────────────
stop_servers() {
    echo -e "${YELLOW}⏹  Stopping all servers...${NC}"
    if [ -d "$PID_DIR" ]; then
        for pid_file in "$PID_DIR"/*.pid; do
            [ -f "$pid_file" ] || continue
            pid=$(cat "$pid_file")
            name=$(basename "$pid_file" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && echo -e "   ${RED}✗${NC} Stopped ${name} (PID $pid)"
            fi
            rm -f "$pid_file"
        done
        rmdir "$PID_DIR" 2>/dev/null || true
    fi
    echo -e "${GREEN}✔  All servers stopped.${NC}"
    exit 0
}

if [ "${1:-}" = "--stop" ]; then
    stop_servers
fi

# ── Pre-flight checks ───────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo -e "${RED}Error: 'uv' is not installed. Please install it first: https://docs.astral.sh/uv/${NC}"
    exit 1
fi

# ── Clean up any previous PIDs ───────────────────────────────────────────────
[ -d "$PID_DIR" ] && stop_servers 2>/dev/null || true
mkdir -p "$PID_DIR"

# ── Helper: start a server in the background ─────────────────────────────────
start_server() {
    local name="$1"
    local module="$2"
    local port="$3"

    echo -ne "   ${CYAN}▶${NC} Starting ${name} on port ${port}... "
    uv run uvicorn "$module" --port "$port" &>/dev/null &
    local pid=$!
    echo "$pid" > "$PID_DIR/${name}.pid"
    echo -e "${GREEN}✔${NC}  (PID $pid)"
}

# ── Trap: clean up on exit (Ctrl+C) ─────────────────────────────────────────
cleanup() {
    echo ""
    stop_servers
}
trap cleanup INT TERM

# ── Launch ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Unified Document Viewer — Starting All Servers       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

start_server "mock-sales-api"   "src.mock_servers.sales_api:app"   8001
start_server "mock-service-api" "src.mock_servers.service_api:app" 8002

# Small delay so mock servers are ready before the main app tries to connect
sleep 1

start_server "main-api"         "src.main:app"                     8000

echo ""
echo -e "${GREEN}✔  All servers are running!${NC}"
echo ""
echo -e "   ${CYAN}Main API:${NC}          http://127.0.0.1:8000"
echo -e "   ${CYAN}Swagger UI:${NC}        http://127.0.0.1:8000/docs"
echo -e "   ${CYAN}Mock Sales API:${NC}    http://127.0.0.1:8001"
echo -e "   ${CYAN}Mock Service API:${NC}  http://127.0.0.1:8002"
echo ""
echo -e "   Press ${YELLOW}Ctrl+C${NC} to stop all servers."
echo -e "   Or run: ${YELLOW}./scripts/run_all.sh --stop${NC}"
echo ""

# Keep script alive so Ctrl+C can trigger cleanup
wait
