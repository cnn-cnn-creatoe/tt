param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [string]$Version = "v1.0"
)

$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path -LiteralPath $ProjectDir).Path
$DistDir = Join-Path $ProjectDir "dist"
$PackageName = "AI-News-$Version.zip"
$PackagePath = Join-Path $DistDir $PackageName
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("AI-News-package-" + [guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (Test-Path -LiteralPath $PackagePath) {
    Remove-Item -LiteralPath $PackagePath -Force
}
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

$ExcludedDirs = @(
    "\.git\",
    "\.venv\",
    "\__pycache__\",
    "\.runtime\",
    "\logs\",
    "\dist\"
)

$ExcludedFileNames = @(
    "config.json"
)

try {
    $Files = Get-ChildItem -LiteralPath $ProjectDir -Recurse -File -Force | Where-Object {
        $FullName = $_.FullName
        $Relative = $FullName.Substring($ProjectDir.Length).TrimStart("\")

        foreach ($Dir in $ExcludedDirs) {
            if ($FullName.Contains($Dir)) {
                return $false
            }
        }

        if ($ExcludedFileNames -contains $_.Name) {
            return $false
        }

        if ($Relative -like "data\tweets_*.json" -or $Relative -like "data\*.backup") {
            return $false
        }

        return $true
    }

    foreach ($File in $Files) {
        $Relative = $File.FullName.Substring($ProjectDir.Length).TrimStart("\")
        $Target = Join-Path $TempDir $Relative
        $TargetDir = Split-Path -Parent $Target
        New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
        Copy-Item -LiteralPath $File.FullName -Destination $Target -Force
    }

    Compress-Archive -Path (Join-Path $TempDir "*") -DestinationPath $PackagePath -Force
    Write-Host "Package created: $PackagePath"
} finally {
    if (Test-Path -LiteralPath $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
}
