#!/usr/bin/env bash
# Pre-demo check: is every service reachable on the LAN address the phone app uses?
# Usage: ./scripts/demo-check.sh [LAN_IP]   (default: first non-loopback, non-docker IPv4)
ip_addr="${1:-$(ip -4 -o addr show | awk '$2 !~ /^(lo|docker|br-|veth)/ {split($4,a,"/"); print a[1]; exit}')}"
apk_url=$(grep -s '^EXPO_PUBLIC_API_BASE_URL=' "$(dirname "$0")/../mobile/.env" | cut -d= -f2-)
echo "Laptop LAN IP : $ip_addr"
echo "APK points to : ${apk_url:-unknown}"
[ -n "$apk_url" ] && [[ "$apk_url" != *"$ip_addr"* ]] && echo "  !! IP changed since the APK was built: rebuild it (mobile/.env) or fix the network"
check() {  # name url expected-substring
  body=$(curl -s -m 5 "$2") && [[ "$body" == *"$3"* ]] && echo "  OK    $1  $2" || echo "  FAIL  $1  $2"
}
check "core (phone app → here)" "http://$ip_addr:8080/actuator/health" '"UP"'
check "agent service          " "http://$ip_addr:8000/ready" '"ready"'
check "complaint module       " "http://$ip_addr:8001/api/simulation/status" 'auto_tick'
check "emergency routing      " "http://$ip_addr:8002/api/health" 'ONLINE'
check "demo login (dashboard) " "http://$ip_addr:8000/health" '"ok"'
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' -X POST "http://$ip_addr:8080/api/auth/login" \
  -H 'content-type: application/json' -d '{"email":"citizen@citysense.dev","password":"citysense123"}')
[ "$code" = 200 ] && echo "  OK    seeded login citizen@citysense.dev" || echo "  FAIL  seeded login (HTTP $code)"
echo
echo "Dashboard (laptop): http://localhost:8000/ui     Dashboard (phone browser): http://$ip_addr:8000/ui"
echo "If OK here but the phone can't connect: open http://$ip_addr:8080/actuator/health in the phone browser."
