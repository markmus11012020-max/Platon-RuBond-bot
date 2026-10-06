#!/usr/bin/env bash
# ============================================================================
#  Platon-RuBond-bot Platform — start.sh
#  Оркестрация: stop → clean cache → venv + deps → streamlit
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV_DIR="${ROOT}/.venv"
PYTHON_VENV="${VENV_DIR}/bin/python"
PIP_VENV="${VENV_DIR}/bin/pip"
STREAMLIT_VENV="${VENV_DIR}/bin/streamlit"
APP_FILE="app.py"
REQUIREMENTS="requirements.txt"
PORT="${PORT:-8501}"
HOST="${HOST:-0.0.0.0}"

echo ""
echo "============================================================"
echo "  Platon-RuBond-bot Platform — deploy / start"
echo "============================================================"
echo "  Root: ${ROOT}"
echo ""

# ---------- 1. Stop old processes ----------
echo "[1/4] Stopping old processes..."
pkill -f "streamlit run .*${APP_FILE}" 2>/dev/null || true
pkill -f "streamlit.*platon_rubond" 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
elif command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${PIDS}" ]]; then
    echo "      Freeing port ${PORT}: ${PIDS}"
    kill -9 ${PIDS} 2>/dev/null || true
  fi
fi
sleep 1
echo "      Done."
echo ""

# ---------- 2. Clear cache ----------
echo "[2/4] Clearing cache..."
find "$ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -type d -name ".pytest_cache" -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
rm -f "${ROOT}/tool_cache.db" 2>/dev/null || true
rm -rf "${ROOT}/.streamlit/cache" 2>/dev/null || true
echo "      Done."
echo ""

# ---------- 3. Environment + dependencies ----------
echo "[3/4] Environment and dependencies..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  exit 1
fi

if [[ ! -x "${PYTHON_VENV}" ]]; then
  echo "      Creating venv: ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
else
  echo "      Using existing venv: ${VENV_DIR}"
fi

echo "      Upgrading pip..."
"${PYTHON_VENV}" -m pip install --upgrade pip setuptools wheel -q || true

if [[ ! -f "${ROOT}/${REQUIREMENTS}" ]]; then
  echo "ERROR: ${REQUIREMENTS} not found."
  exit 1
fi

echo "      Installing requirements..."
"${PIP_VENV}" install -r "${ROOT}/${REQUIREMENTS}"

if [[ ! -f "${ROOT}/.env" && -f "${ROOT}/.env.example" ]]; then
  echo "      .env missing — copying from .env.example"
  cp "${ROOT}/.env.example" "${ROOT}/.env"
  echo "      Fill API keys in .env before production use."
fi

echo "      Done."
echo ""

# ---------- 4. Start project ----------
echo "[4/4] Starting Streamlit..."
if [[ ! -f "${ROOT}/${APP_FILE}" ]]; then
  echo "ERROR: ${APP_FILE} not found."
  exit 1
fi

echo ""
echo "  URL:  http://localhost:${PORT}"
echo "  Stop: Ctrl+C"
echo "============================================================"
echo ""

exec "${STREAMLIT_VENV}" run "${ROOT}/${APP_FILE}" \
  --server.port "${PORT}" \
  --server.address "${HOST}" \
  --browser.gatherUsageStats false
