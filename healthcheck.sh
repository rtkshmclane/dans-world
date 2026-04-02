#!/bin/bash
#
# healthcheck.sh - Monitor Dan's World apps and alert via Slack
# Runs via cron every 5 minutes. Only sends alerts on failures or recovery.
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_FILE="/tmp/dw_health_state"
NOTIFY="$SCRIPT_DIR/slack_notify.sh"

# Endpoints to check (name|url|expected_status)
ENDPOINTS=(
    "Gateway|http://localhost:443|301"
    "Admin|http://localhost:80|301"
    "Ticketmaker|http://localhost:5000/|200"
    "Detections|http://localhost:5555/|200"
    "Cloud Live|http://localhost:5004/|200"
    "Network Graph|http://localhost:3334/|200"
    "Okta IS|http://localhost:5005/health|200"
    "Analytic Stories|http://localhost:8089/api/v1/stats|200"
)

# Check each endpoint inside the apps container or directly
FAILURES=""
RECOVERIES=""
PREV_FAILURES=""

# Load previous state
[ -f "$STATE_FILE" ] && PREV_FAILURES=$(cat "$STATE_FILE")

# Check Docker containers first
for CONTAINER in dw-gateway dw-admin dw-apps; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null)
    if [ "$STATUS" != "running" ]; then
        FAILURES="$FAILURES\n- Container $CONTAINER is $STATUS"
    fi
done

# Check app health endpoints (inside dw-apps container)
for EP in "${ENDPOINTS[@]}"; do
    IFS='|' read -r NAME URL EXPECTED <<< "$EP"

    # Route checks through the right container
    if [[ "$URL" == *"localhost:443"* ]] || [[ "$URL" == *"localhost:80"* ]]; then
        HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 5 "$URL" 2>/dev/null)
    elif [[ "$URL" == *"localhost:5050"* ]]; then
        HTTP_CODE=$(docker exec dw-admin curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$URL" 2>/dev/null)
    else
        HTTP_CODE=$(docker exec dw-apps curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$URL" 2>/dev/null)
    fi

    if [ "$HTTP_CODE" != "$EXPECTED" ]; then
        FAILURES="$FAILURES\n- $NAME: HTTP $HTTP_CODE (expected $EXPECTED)"
    fi
done

# Check disk usage
DISK_PCT=$(df /mnt/data --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
if [ -n "$DISK_PCT" ] && [ "$DISK_PCT" -gt 90 ]; then
    FAILURES="$FAILURES\n- Disk /mnt/data at ${DISK_PCT}%"
fi

ROOT_PCT=$(df / --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
if [ -n "$ROOT_PCT" ] && [ "$ROOT_PCT" -gt 90 ]; then
    FAILURES="$FAILURES\n- Disk / at ${ROOT_PCT}%"
fi

# Check memory
MEM_AVAIL=$(free -m | awk '/Mem:/ {print $7}')
if [ -n "$MEM_AVAIL" ] && [ "$MEM_AVAIL" -lt 256 ]; then
    FAILURES="$FAILURES\n- Low memory: ${MEM_AVAIL}MB available"
fi

# Save current state
echo -e "$FAILURES" > "$STATE_FILE"

# Determine if we need to alert
if [ -n "$FAILURES" ] && [ -z "$PREV_FAILURES" ]; then
    # New failure -- alert
    "$NOTIFY" "$(echo -e "Issues detected on octo.rtkwlf.io:\n$FAILURES\n\nChecked at $(date '+%H:%M UTC')")" "Dan's World Alert" sam
elif [ -z "$FAILURES" ] && [ -n "$PREV_FAILURES" ]; then
    # Recovery -- all clear
    "$NOTIFY" "All services recovered on octo.rtkwlf.io at $(date '+%H:%M UTC')" "Dan's World Recovery" sam
fi
