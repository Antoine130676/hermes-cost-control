#!/bin/bash
# Hermes Strict Provider Enforcement - Bash version
# Run this to start monitoring and ensure only Nous Portal is used

HERMES_MONITOR_DIR="$HOME/hermes-projects/hermes-monitor"
LOG_DIR="$HERMES_MONITOR_DIR/logs"
PID_FILE="$HERMES_MONITOR_DIR/.monitor_pid"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ensure_dirs() {
    mkdir -p "$LOG_DIR"
}

check_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        fi
    fi
    # Also check by process name
    if pgrep -f "monitor_agent.py" > /dev/null; then
        return 0
    fi
    return 1
}

start_monitor() {
    if check_running; then
        echo -e "${YELLOW}Monitor is already running.${NC}"
        return
    fi
    
    ensure_dirs
    
    local script="$HERMES_MONITOR_DIR/monitor_agent.py"
    if [ ! -f "$script" ]; then
        echo -e "${RED}Error: Monitor script not found: $script${NC}"
        return 1
    fi
    
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local log_file="$LOG_DIR/monitor_$timestamp.log"
    
    # Start in background
    nohup python "$script" > "$log_file" 2>&1 &
    local pid=$!
    
    echo $pid > "$PID_FILE"
    
    echo -e "${GREEN}Monitor started (PID: $pid)${NC}"
    echo -e "Logs: $LOG_DIR"
    echo -e "Alerts: $HERMES_MONITOR_DIR/alerts.log"
}

stop_monitor() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill "$pid" 2>/dev/null; then
            echo -e "${GREEN}Monitor stopped (PID: $pid)${NC}"
        else
            echo -e "${YELLOW}Monitor process not found (PID: $pid)${NC}"
        fi
        rm -f "$PID_FILE"
    fi
    
    # Also kill by process name
    pkill -f "monitor_agent.py" 2>/dev/null
}

show_status() {
    if check_running; then
        echo -e "${GREEN}✓ Monitor is RUNNING${NC}"
        
        # Show recent alerts
        if [ -f "$HERMES_MONITOR_DIR/alerts.log" ]; then
            echo -e "\n${YELLOW}Recent alerts:${NC}"
            tail -5 "$HERMES_MONITOR_DIR/alerts.log"
        fi
        
        # Show violations
        if [ -f "$HERMES_MONITOR_DIR/enforcement.log" ]; then
            local violations=$(grep -c "VIOLATION" "$HERMES_MONITOR_DIR/enforcement.log" 2>/dev/null || echo "0")
            echo -e "\n${YELLOW}Total violations detected: $violations${NC}"
        fi
    else
        echo -e "${RED}✗ Monitor is NOT RUNNING${NC}"
    fi
}

# Main
case "${1:-status}" in
    start)
        start_monitor
        ;;
    stop)
        stop_monitor
        ;;
    restart)
        stop_monitor
        sleep 1
        start_monitor
        ;;
    status|*)
        show_status
        ;;
esac
