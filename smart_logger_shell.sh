#!/usr/bin/env bash

LOGFILE="logs.txt"
ALERT_FILE="alert_history.txt"
ARCHIVE_DIR="archives"
MAXSIZE=50000
CPU_LIMIT=80
MEM_LIMIT=80
INTERVAL=3

mkdir -p "$ARCHIVE_DIR"
touch "$LOGFILE" "$ALERT_FILE"

# -------- LOG FUNCTION --------
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" >> "$LOGFILE"
}

# -------- ALERT FUNCTION (log only, GUI handles popup) --------
send_alert() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1: $2" >> "$ALERT_FILE"
}

# -------- LOG ROTATION --------
rotate_log() {
    size=$(wc -c < "$LOGFILE")
    if (( size > MAXSIZE )); then
        file="$ARCHIVE_DIR/log_$(date +%s).txt"
        mv "$LOGFILE" "$file"
        touch "$LOGFILE"
        log "INFO" "Logs archived → $file"
    fi
}

# -------- MAIN LOOP --------
while true; do

    # CPU
    cpu=$(powershell -Command "Get-CimInstance Win32_Processor | Select -ExpandProperty LoadPercentage" 2>/dev/null)

    # MEMORY (fixed)
    free_mem=$(powershell -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory" 2>/dev/null)
    total_mem=$(powershell -Command "(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize" 2>/dev/null)

    if [[ -n "$free_mem" && -n "$total_mem" && "$total_mem" -ne 0 ]]; then
        mem=$(( ( (total_mem - free_mem) * 100 ) / total_mem ))
    else
        mem=0
    fi

    # DISK
    free=$(powershell -Command "(Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\").FreeSpace" 2>/dev/null)
    total=$(powershell -Command "(Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\").Size" 2>/dev/null)

    if [[ -n "$free" && -n "$total" && "$total" -ne 0 ]]; then
        disk=$(( ( (total - free) * 100 ) / total ))
    else
        disk=0
    fi

    # PROCESS COUNT
    proc=$(powershell -Command "(Get-Process).Count" 2>/dev/null)

    # MAIN LOG ENTRY
    log "INFO" "CPU:${cpu}% MEM:${mem}% DISK:${disk}% PROC:${proc}"

    # -------- PROCESS LIST --------
    log "INFO" "TOP_PROCESSES"

    # Clean output for GUI table
    powershell -Command "
        Get-Process |
        Sort-Object CPU -Descending |
        Select-Object -First 5 `
            Id,
            ProcessName,
            @{Name='CPU';Expression={[int]\$_.CPU}},
            @{Name='MEM';Expression={[int](\$_.WorkingSet/1MB)}} |
        ForEach-Object {
            \"\$($_.Id) \$($_.ProcessName) \$($_.CPU) \$($_.MEM)\"
        }
    " 2>/dev/null >> "$LOGFILE"

    # -------- ALERT CONDITIONS --------
    if (( cpu > CPU_LIMIT )); then
        send_alert "High CPU" "CPU ${cpu}%"
    fi

    if (( mem > MEM_LIMIT )); then
        send_alert "High Memory" "Memory ${mem}%"
    fi

    # -------- ROTATE LOG --------
    rotate_log

    sleep "$INTERVAL"
done