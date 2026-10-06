#!/usr/bin/env pwsh
# Hermes Strict Provider Enforcement - Windows Startup Script
# This script starts the monitoring agent as a background process

$ErrorActionPreference = "Stop"

$MonitorDir = "$env:USERPROFILE\hermes-projects\hermes-monitor"
$LogDir = "$env:USERPROFILE\hermes-projects\hermes-monitor\logs"
$PythonPath = "python"

# Ensure directories exist
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Function to check if monitor is already running
function Test-MonitorRunning {
    $processes = Get-Process -Name "python" -ErrorAction SilentlyContinue
    foreach ($proc in $processes) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
            if ($cmdLine -match "monitor_agent.py") {
                return $true
            }
        } catch {
            continue
        }
    }
    return $false
}

# Function to start monitor
function Start-Monitor {
    param(
        [switch]$Background
    )
    
    if (Test-MonitorRunning) {
        Write-Host "Monitor is already running." -ForegroundColor Yellow
        return
    }
    
    $scriptPath = "$MonitorDir\monitor_agent.py"
    
    if (-not (Test-Path $scriptPath)) {
        Write-Error "Monitor script not found: $scriptPath"
        return
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logFile = "$LogDir\monitor_$timestamp.log"
    
    if ($Background) {
        # Start in background with window hidden
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $PythonPath
        $psi.Arguments = "$scriptPath"
        $psi.WorkingDirectory = $MonitorDir
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.Start() | Out-Null
        
        # Save PID
        $process.Id | Out-File "$MonitorDir\.monitor_pid" -Force
        
        Write-Host "Monitor started in background (PID: $($process.Id))" -ForegroundColor Green
        Write-Host "Logs: $LogDir" -ForegroundColor Cyan
    } else {
        # Start in foreground
        Write-Host "Starting monitor in foreground (Ctrl+C to stop)..." -ForegroundColor Green
        & $PythonPath $scriptPath
    }
}

# Function to stop monitor
function Stop-Monitor {
    $pidFile = "$MonitorDir\.monitor_pid"
    
    if (Test-Path $pidFile) {
        $monitorPid = Get-Content $pidFile
        try {
            Stop-Process -Id $monitorPid -Force -ErrorAction Stop
            Remove-Item $pidFile -Force
            Write-Host "Monitor stopped (PID: $monitorPid)" -ForegroundColor Green
        } catch {
            Write-Error "Failed to stop monitor: $_"
        }
    } else {
        # Try to find and kill by command line
        $processes = Get-Process -Name "python" -ErrorAction SilentlyContinue
        foreach ($proc in $processes) {
            try {
                $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
                if ($cmdLine -match "monitor_agent.py") {
                    Stop-Process -Id $proc.Id -Force
                    Write-Host "Monitor stopped (PID: $($proc.Id))" -ForegroundColor Green
                    return
                }
            } catch {
                continue
            }
        }
        Write-Host "No monitor process found." -ForegroundColor Yellow
    }
}

# Function to show status
function Show-MonitorStatus {
    if (Test-MonitorRunning) {
        Write-Host "Monitor is RUNNING" -ForegroundColor Green
        
        # Show recent alerts
        $alertFile = "$MonitorDir\alerts.log"
        if (Test-Path $alertFile) {
            Write-Host "\nRecent alerts:" -ForegroundColor Yellow
            Get-Content $alertFile -Tail 5
        }
        
        # Show credit status
        $creditFile = "$MonitorDir\credit_tracker.json"
        if (Test-Path $creditFile) {
            $credit = Get-Content $creditFile | ConvertFrom-Json
            Write-Host "\nCurrent session cost: `$ $($credit.current_cost)" -ForegroundColor Cyan
            Write-Host "Alert threshold: `$ $($credit.threshold)" -ForegroundColor Cyan
        }
    } else {
        Write-Host "Monitor is NOT RUNNING" -ForegroundColor Red
    }
}

# Main
param(
    [Parameter()]
    [ValidateSet("start", "stop", "status", "restart")]
    [string]$Action = "status"
)

switch ($Action) {
    "start" { Start-Monitor -Background }
    "stop" { Stop-Monitor }
    "restart" { Stop-Monitor; Start-Sleep -Seconds 1; Start-Monitor -Background }
    "status" { Show-MonitorStatus }
}
