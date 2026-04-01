#!/usr/bin/env bash

LOGFILE="logs.txt"
ALERT_FILE="alert_history.txt"
ARCHIVE_DIR="archives"
MAXSIZE=50000
CPU_LIMIT=80
MEM_LIMIT=80
INTERVAL=5

mkdir -p "$ARCHIVE_DIR"
touch "$LOGFILE" "$ALERT_FILE"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" >> "$LOGFILE"
}

send_alert() {
    osascript -e "display notification \"$2\" with title \"$1\""
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1: $2" >> "$ALERT_FILE"
}

rotate_log() {
    size=$(stat -f%z "$LOGFILE" 2>/dev/null || echo 0)
    if (( size > MAXSIZE )); then
        file="$ARCHIVE_DIR/log_$(date +%s).txt"
        mv "$LOGFILE" "$file"
        touch "$LOGFILE"
        log "INFO" "Logs archived → $file"
    fi
}

while true; do
    cpu=$(top -l 1 | grep "CPU usage" | awk '{print int($3)}')
    mem=$(vm_stat | awk '/Pages active/ {a=$3} /Pages wired down/ {w=$4} END {print int((a+w)/10000)}')
    disk=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
    proc=$(ps aux | wc -l)

    log "INFO" "CPU:${cpu}% MEM:${mem}% DISK:${disk}% PROC:${proc}"

    log "INFO" "TOP_PROCESSES"
    ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -n 6 >> "$LOGFILE"

    (( cpu > CPU_LIMIT )) && send_alert "High CPU" "CPU ${cpu}%"
    (( mem > MEM_LIMIT )) && send_alert "High Memory" "Memory ${mem}%"

    rotate_log
    sleep "$INTERVAL"
done