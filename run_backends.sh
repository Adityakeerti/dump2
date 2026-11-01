#!/usr/bin/env bash
# Start/stop/status for the CitySense local stack:
#   8000 agent service · 8001 complaint module · 8002 emergency routing      (SmartCity/.venv)
#   8003 live digital twin + RL (CITY SENSE RL repo, its own .venv)
#   8090 llama-server with Gemma-4-E2B (local LLM for the population agents)
#   8004 population simulator (LangGraph people-cluster agents, SmartCity/.venv)
#   8005 civic simulator (residents -> complaint portal -> municipal/police agents, RL root-cause policy)
#   5173 React operations dashboard (Vite dev server)
# Paths can be overridden: RL_DIR, LLAMA_SERVER, GEMMA_MODEL, LLAMA_ARGS.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/.." && pwd)"
VENV_UVICORN="$ROOT_DIR/.venv/bin/uvicorn"
RL_DIR="${RL_DIR:-$(cd "$ROOT_DIR/.." && pwd)/CITY SENSE RL}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama-fork/build/bin/llama-server}"
GEMMA_MODEL="${GEMMA_MODEL:-$HOME/AI/models/Gemma-4-E2B/gemma-4-E2B_q4_0-it.gguf}"
LLAMA_ARGS="${LLAMA_ARGS:--ngl 99 -c 16384 -np 4 --reasoning off}"

if [ ! -f "$VENV_UVICORN" ]; then
  echo "Error: Virtual environment uvicorn not found at $VENV_UVICORN"
  exit 1
fi

listening() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }  # ss ships with iproute2; lsof is often missing

ACTION="${1:-status}"

case "$ACTION" in
  start)
    echo "=================================================="
    echo "Starting CitySense Monorepo Backends"
    echo "=================================================="

    # 1. Agent Service on Port 8000
    if listening 8000; then
      echo "[-] Port 8000 (Agent Service) already listening."
    else
      echo "[+] Starting Agent Service (voice agent + RAG) on port 8000..."
      # Point the agent's tools at the live sibling services (override any of these in the shell).
      (cd "$DIR/agent_service" && \
        COMPLAINT_SERVICE_URL="${COMPLAINT_SERVICE_URL:-http://localhost:8001}" \
        EMERGENCY_SERVICE_URL="${EMERGENCY_SERVICE_URL:-http://localhost:8002}" \
        CORE_SERVICE_URL="${CORE_SERVICE_URL:-http://localhost:8080}" \
        nohup "$VENV_UVICORN" src.main:app --host 0.0.0.0 --port 8000 > "$DIR/agent_service/service.log" 2>&1 &) </dev/null >/dev/null 2>&1
    fi

    # 2. Complaint Module on Port 8001
    if listening 8001; then
      echo "[-] Port 8001 (Complaint Module) already listening."
    else
      echo "[+] Starting Complaint Module on port 8001..."
      (cd "$DIR/complaint_module" && nohup "$VENV_UVICORN" app.server:app --host 0.0.0.0 --port 8001 > "$DIR/complaint_module/service.log" 2>&1 &) </dev/null >/dev/null 2>&1
    fi

    # 3. Emergency Routing on Port 8002
    if listening 8002; then
      echo "[-] Port 8002 (Emergency Routing) already listening."
    else
      echo "[+] Starting Emergency Routing on port 8002..."
      (cd "$DIR/emergency_routing" && nohup "$VENV_UVICORN" server:app --host 0.0.0.0 --port 8002 > "$DIR/emergency_routing/service.log" 2>&1 &) </dev/null >/dev/null 2>&1
    fi

    # 4. Live digital twin (CTM + online DQN) on Port 8003
    if listening 8003; then
      echo "[-] Port 8003 (Digital Twin) already listening."
    elif [ -x "$RL_DIR/.venv/bin/python" ]; then
      echo "[+] Starting Digital Twin + RL from '$RL_DIR' on port 8003..."
      (cd "$RL_DIR" && nohup .venv/bin/python scripts/serve_twin.py > "$DIR/city_sim/twin.log" 2>&1 &) </dev/null >/dev/null 2>&1
    else
      echo "[!] Skipping Digital Twin: no venv at '$RL_DIR/.venv' (set RL_DIR)."
    fi

    # 5. Local Gemma via llama-server on Port 8090
    if listening 8090; then
      echo "[-] Port 8090 (llama-server) already listening."
    elif [ -x "$LLAMA_SERVER" ] && [ -f "$GEMMA_MODEL" ]; then
      echo "[+] Starting llama-server (Gemma-4-E2B) on port 8090..."
      # shellcheck disable=SC2086
      nohup "$LLAMA_SERVER" -m "$GEMMA_MODEL" $LLAMA_ARGS --host 127.0.0.1 --port 8090 > "$DIR/city_sim/llama.log" 2>&1 &
    else
      echo "[!] Skipping llama-server: set LLAMA_SERVER and GEMMA_MODEL. Agents will use the rule fallback."
    fi

    # 6. Population simulator (LangGraph agents) on Port 8004
    if listening 8004; then
      echo "[-] Port 8004 (Population Simulator) already listening."
    else
      echo "[+] Starting Population Simulator on port 8004..."
      (cd "$DIR/city_sim" && nohup "$VENV_UVICORN" app.server:app --host 127.0.0.1 --port 8004 > "$DIR/city_sim/service.log" 2>&1 &) </dev/null >/dev/null 2>&1
    fi

    # 6b. Civic simulator (complaints, departments, RL investigation policy) on Port 8005
    if listening 8005; then
      echo "[-] Port 8005 (Civic Simulator) already listening."
    else
      echo "[+] Starting Civic Simulator on port 8005..."
      (cd "$DIR/civic_sim" && COMPLAINT_SERVICE_URL="${COMPLAINT_SERVICE_URL:-http://localhost:8001}" \
        nohup "$VENV_UVICORN" app.server:app --host 127.0.0.1 --port 8005 > "$DIR/civic_sim/service.log" 2>&1 &) </dev/null >/dev/null 2>&1
    fi

    # 7. Dashboard dev server on Port 5173
    if listening 5173; then
      echo "[-] Port 5173 (Dashboard) already listening."
    elif [ -d "$DIR/dashboard/node_modules" ]; then
      echo "[+] Starting Dashboard (Vite) on port 5173..."
      (cd "$DIR/dashboard" && nohup npx vite --port 5173 --strictPort > "$DIR/dashboard/vite.log" 2>&1 &) </dev/null >/dev/null 2>&1
    else
      echo "[!] Skipping Dashboard: run 'cd dashboard && npm install' first."
    fi

    sleep 3
    "$0" status
    ;;

  stop)
    echo "Stopping CitySense stack on ports 8000-8005, 8090, 5173..."
    for p in 8000 8001 8002 8003 8004 8005 8090 5173; do fuser -k "$p/tcp" 2>/dev/null || true; done
    echo "All stopped."
    ;;

  status)
    echo "--------------------------------------------------"
    echo "Backend Status:"
    echo "--------------------------------------------------"
    echo -n "• Agent Service (Port 8000): "
    if curl -s http://localhost:8000/health | grep -q '"status":"ok"'; then echo "ONLINE"; else echo "OFFLINE"; fi

    echo -n "• Complaint Module (Port 8001): "
    if curl -s http://localhost:8001/api/simulation/status | grep -q 'auto_tick_enabled'; then echo "ONLINE"; else echo "OFFLINE"; fi

    echo -n "• Emergency Routing (Port 8002): "
    if curl -s http://localhost:8002/api/health | grep -q '"ONLINE"'; then echo "ONLINE"; else echo "OFFLINE"; fi

    echo -n "• Digital Twin + RL (Port 8003): "
    if curl -s http://localhost:8003/api/twin/health | grep -q '"twin"'; then echo "ONLINE"; else echo "OFFLINE"; fi

    echo -n "• llama-server / Gemma (Port 8090): "
    if curl -s http://localhost:8090/health | grep -q 'ok'; then echo "ONLINE"; else echo "OFFLINE (loading takes ~10 s)"; fi

    echo -n "• Population Simulator (Port 8004): "
    if curl -s http://localhost:8004/api/city/health | grep -q '"status":"ok"'; then echo "ONLINE"; else echo "OFFLINE"; fi

    echo -n "• Civic Simulator (Port 8005): "
    if curl -s http://localhost:8005/api/civic/health | grep -q '"ok":true'; then echo "ONLINE"; else echo "OFFLINE"; fi

    echo -n "• Dashboard (Port 5173): "
    if curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/ | grep -q 200; then echo "ONLINE  → http://localhost:5173"; else echo "OFFLINE"; fi
    echo "--------------------------------------------------"
    ;;

  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
