param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [Parameter(Mandatory = $true)]
    [string]$PythonPath,

    [string]$HostName = "127.0.0.1",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path -LiteralPath $ProjectDir).Path
$RuntimeDir = Join-Path $ProjectDir ".runtime"
$LogDir = Join-Path $ProjectDir "logs"
$PidFile = Join-Path $RuntimeDir "server.pid"
$OutLog = Join-Path $LogDir "server.out.log"
$ErrLog = Join-Path $LogDir "server.err.log"
$AppFile = Join-Path $ProjectDir "app.py"

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir | Out-Null

function Test-ProcessAlive {
    param([int]$ProcessId)
    try {
        Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $ExistingPid = 0
    if ([int]::TryParse($ExistingPidText, [ref]$ExistingPid) -and (Test-ProcessAlive -ProcessId $ExistingPid)) {
        Write-Host "Service is already running. PID: $ExistingPid"
        exit 0
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

$PortOwner = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($PortOwner) {
    throw "Port $Port is already used by process $($PortOwner.OwningProcess). Run end.bat first, or close the program using this port."
}

$env:HOST = $HostName
$env:PORT = [string]$Port
$env:FLASK_DEBUG = "0"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Process = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList @("-u", $AppFile) `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

$Process.Id | Set-Content -LiteralPath $PidFile -Encoding ASCII

$Url = "http://$HostName`:$Port/"
$Deadline = (Get-Date).AddSeconds(15)
$Ready = $false

while ((Get-Date) -lt $Deadline) {
    if ($Process.HasExited) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        throw "Service failed to start. See $ErrLog"
    }

    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
        $Ready = $true
        break
    } catch {
        Start-Sleep -Milliseconds 700
    }
}

if ($Ready) {
    Write-Host "Service started: $Url"
} else {
    Write-Host "Service process started and is still initializing in background: $Url"
}
