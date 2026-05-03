param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path -LiteralPath $ProjectDir).Path
$RuntimeDir = Join-Path $ProjectDir ".runtime"
$PidFile = Join-Path $RuntimeDir "server.pid"
$Stopped = New-Object System.Collections.Generic.List[int]

function Stop-ByPid {
    param([int]$ProcessId)
    try {
        $Process = Get-Process -Id $ProcessId -ErrorAction Stop
        Stop-Process -Id $Process.Id -Force -ErrorAction Stop
        $Stopped.Add($Process.Id) | Out-Null
    } catch {
    }
}

if (Test-Path -LiteralPath $PidFile) {
    $PidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $TargetPid = 0
    if ([int]::TryParse($PidText, [ref]$TargetPid)) {
        Stop-ByPid -ProcessId $TargetPid
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

$ProjectNeedle = $ProjectDir.ToLowerInvariant()
$PythonProcesses = Get-CimInstance Win32_Process -Filter "name = 'python.exe' or name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine.ToLowerInvariant().Contains($ProjectNeedle) -and
        ($_.CommandLine -match "app\.py|start\.py")
    }

foreach ($Process in $PythonProcesses) {
    Stop-ByPid -ProcessId ([int]$Process.ProcessId)
}

$PortOwners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($OwnerPid in $PortOwners) {
    $Owner = Get-CimInstance Win32_Process -Filter "ProcessId = $OwnerPid" -ErrorAction SilentlyContinue
    if ($Owner -and $Owner.CommandLine -and $Owner.CommandLine.ToLowerInvariant().Contains($ProjectNeedle)) {
        Stop-ByPid -ProcessId ([int]$OwnerPid)
    }
}

if ($Stopped.Count -gt 0) {
    $UniqueStopped = $Stopped | Select-Object -Unique
    Write-Host "Stopped background service PID: $($UniqueStopped -join ', ')"
} else {
    Write-Host "No running background service found for this project."
}
