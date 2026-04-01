#!/usr/bin/env bash

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGFILE="$BASE_DIR/logs.txt"
ARCHIVE_DIR="$BASE_DIR/archives"
APP_HISTORY_FILE="$BASE_DIR/app_history.txt"
CPU_SERIES_FILE="$BASE_DIR/cpu_series.txt"
STATUS_FILE="$BASE_DIR/status.txt"

MAXSIZE=50000
CPU_LIMIT=80
MEM_LIMIT=80
INTERVAL=3

mkdir -p "$ARCHIVE_DIR"
touch "$LOGFILE" "$APP_HISTORY_FILE" "$CPU_SERIES_FILE" "$STATUS_FILE"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" >> "$LOGFILE"
}

trim_file_lines() {
    local file="$1"
    local max_lines="$2"

    if [ -f "$file" ]; then
        local lines
        lines=$(wc -l < "$file" 2>/dev/null)
        lines=${lines:-0}
        if (( lines > max_lines )); then
            tail -n "$max_lines" "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
        fi
    fi
}

rotate_log() {
    if [ -f "$LOGFILE" ]; then
        local size
        size=$(wc -c < "$LOGFILE" 2>/dev/null)
        size=${size:-0}

        if (( size > MAXSIZE )); then
            local archive_file="$ARCHIVE_DIR/log_$(date +%Y%m%d_%H%M%S).txt"
            mv "$LOGFILE" "$archive_file"
            touch "$LOGFILE"
            log "INFO" "Logs archived -> $archive_file"
        fi
    fi
}

get_stats() {
    powershell.exe -NoProfile -Command '& {
        try {
            $cpu = [int]((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average)

            $os = Get-CimInstance Win32_OperatingSystem
            if ($os.TotalVisibleMemorySize -gt 0) {
                $mem = [int]((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 100) / $os.TotalVisibleMemorySize)
            } else {
                $mem = 0
            }

            $diskObj = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DeviceID -eq "C:" } | Select-Object -First 1
            if ($diskObj -and $diskObj.Size -gt 0) {
                $disk = [int]((($diskObj.Size - $diskObj.FreeSpace) * 100) / $diskObj.Size)
            } else {
                $disk = 0
            }

            $proc = (Get-Process).Count

            $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
            $span = (Get-Date) - $boot
            $uptime = "$($span.Days)d $($span.Hours)h $($span.Minutes)m"

            Write-Output "$cpu|$mem|$disk|$proc|$uptime"
        }
        catch {
            Write-Output "0|0|0|0|Unknown"
        }
    }' | tr -d '\r'
}

write_top_apps() {
    local timestamp="$1"
    {
        echo "[$timestamp] Top Applications"
        powershell.exe -NoProfile -Command '& {
            try {
                Get-Process |
                Sort-Object CPU -Descending |
                Select-Object -First 5 Id, ProcessName,
                    @{Name="CPU";Expression={ if ($_.CPU) { [math]::Round($_.CPU,2) } else { 0 } }},
                    @{Name="MEM";Expression={ [math]::Round($_.WorkingSet / 1MB, 2) }} |
                ForEach-Object {
                    "{0,-8} {1,-24} CPU:{2,-8} MEM:{3}MB" -f $_.Id, $_.ProcessName, $_.CPU, $_.MEM
                }
            }
            catch {
                "Unable to read app history"
            }
        }' | tr -d '\r'
        echo ""
    } >> "$APP_HISTORY_FILE"
}

log "INFO" "System monitor backend started"

while true; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    stats=$(get_stats)
    IFS='|' read -r cpu mem disk proc uptime <<< "$stats"

    [[ "$cpu" =~ ^[0-9]+$ ]] || cpu=0
    [[ "$mem" =~ ^[0-9]+$ ]] || mem=0
    [[ "$disk" =~ ^[0-9]+$ ]] || disk=0
    [[ "$proc" =~ ^[0-9]+$ ]] || proc=0
    [ -n "$uptime" ] || uptime="Unknown"

    {
        echo "TIMESTAMP=$timestamp"
        echo "CPU=$cpu"
        echo "MEM=$mem"
        echo "DISK=$disk"
        echo "PROC=$proc"
        echo "UPTIME=$uptime"
    } > "$STATUS_FILE"

    echo "$timestamp|$cpu" >> "$CPU_SERIES_FILE"

    log "INFO" "CPU:${cpu}% MEM:${mem}% DISK:${disk}% PROC:${proc} UPTIME:${uptime}"

    write_top_apps "$timestamp"

    trim_file_lines "$CPU_SERIES_FILE" 100
    trim_file_lines "$APP_HISTORY_FILE" 300
    rotate_log

    sleep "$INTERVAL"
done