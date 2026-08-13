#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# test_api.sh — cURL-based smoke tests for the Unified Document Viewer API.
#
# Prerequisites: All three servers must be running (see ./scripts/run_all.sh).
#
# Usage:
#   ./scripts/test_api.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
PASS=0
FAIL=0

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

# ── Helper ───────────────────────────────────────────────────────────────────
run_test() {
    local description="$1"
    local expected_status="$2"
    local url="$3"

    echo -ne "   ${CYAN}▶${NC} ${description}... "

    http_status=$(curl -s -o /tmp/udv_response.json -w "%{http_code}" "$url")

    if [ "$http_status" = "$expected_status" ]; then
        echo -e "${GREEN}✔ PASS${NC} ${DIM}(HTTP $http_status)${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗ FAIL${NC} — expected $expected_status, got $http_status"
        FAIL=$((FAIL + 1))
    fi

    # Pretty-print response body
    echo -e "     ${DIM}$(python3 -m json.tool /tmp/udv_response.json 2>/dev/null | head -25)${NC}"
    echo ""
}

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║         Unified Document Viewer — API Smoke Tests          ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Test 1: Health check ─────────────────────────────────────────────────────
echo -e "${CYAN}── 1. Health Check ──${NC}"
run_test "GET / (root)" "200" "$BASE_URL/"
echo ""

# ── Test 2: Valid VIN — full success ─────────────────────────────────────────
echo -e "${CYAN}── 2. Valid VIN (all sources respond) ──${NC}"
run_test "GET /api/v1/documents?vin=1HGCM82633A004352" "200" \
    "$BASE_URL/api/v1/documents?vin=1HGCM82633A004352"
echo ""

# ── Test 3: Valid VIN — no documents found ───────────────────────────────────
echo -e "${CYAN}── 3. Valid VIN with no matching documents ──${NC}"
run_test "GET /api/v1/documents?vin=00000000000000000" "200" \
    "$BASE_URL/api/v1/documents?vin=00000000000000000"
echo ""

# ── Test 4: Invalid VIN — too short ──────────────────────────────────────────
echo -e "${CYAN}── 4. Invalid VIN (too short → 422) ──${NC}"
run_test "GET /api/v1/documents?vin=ABC" "422" \
    "$BASE_URL/api/v1/documents?vin=ABC"
echo ""

# ── Test 5: Missing VIN parameter ────────────────────────────────────────────
echo -e "${CYAN}── 5. Missing VIN parameter (→ 422) ──${NC}"
run_test "GET /api/v1/documents (no vin param)" "422" \
    "$BASE_URL/api/v1/documents"
echo ""

# ── Test 6: Search History ───────────────────────────────────────────────────
echo -e "${CYAN}── 6. Search History ──${NC}"
run_test "GET /api/v1/history (all history)" "200" \
    "$BASE_URL/api/v1/history"
echo ""

run_test "GET /api/v1/history?vin=1HGCM82633A004352 (filter by VIN)" "200" \
    "$BASE_URL/api/v1/history?vin=1HGCM82633A004352"
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "   ${GREEN}✔ All $TOTAL tests passed!${NC}"
else
    echo -e "   ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} out of $TOTAL tests."
fi
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Clean up
rm -f /tmp/udv_response.json

exit "$FAIL"
