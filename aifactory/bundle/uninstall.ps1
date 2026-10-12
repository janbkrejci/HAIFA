# Uninstalls HAIFA (the `factory` tool) on Windows. -Purge also deletes the HAIFA home
# (library, logs, env), -KeepData keeps it; without either the script asks. Dependencies
# (git, uv, gh, node, claude, codex) and the repositories' .factory/ stay. Started by
# uninstall.bat; ASCII only, PowerShell 5.1 reads it as ANSI.
param([switch]$Purge, [switch]$KeepData)
$ErrorActionPreference = 'Stop'

function Fail([string]$Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

# The same rules as aifactory.home.haifa_home.
function Get-HaifaHome {
    if ($env:HAIFA_HOME) { return $env:HAIFA_HOME }
    if ($env:XDG_CONFIG_HOME) { return Join-Path $env:XDG_CONFIG_HOME 'haifa' }
    $base = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
    return Join-Path (Join-Path $base '.config') 'haifa'
}

if ($Purge -and $KeepData) {
    Fail 'use -Purge or -KeepData, not both'
}
if (-not (Get-Command 'uv' -ErrorAction SilentlyContinue)) {
    Fail 'uv is not on PATH; factory was installed with uv, uninstall it with: uv tool uninstall aifactory'
}

$home_dir = Get-HaifaHome
$purge_home = [bool]$Purge
if (-not $Purge -and -not $KeepData -and (Test-Path -LiteralPath $home_dir)) {
    $answer = Read-Host "Delete also the HAIFA data in $home_dir (library with unpushed changes, logs, settings)? [y/N]"
    $purge_home = $answer -match '^(y|yes|a|ano)$'
}

$listed = uv tool list | Out-String
if ($listed -match '(?m)^aifactory ') {
    uv tool uninstall aifactory
    if ($LASTEXITCODE -ne 0) {
        Fail 'uv tool uninstall aifactory failed; close running factory processes (the dashboard) and run again'
    }
    Write-Host 'factory uninstalled.'
} else {
    Write-Host 'factory is not installed.'
}

if ($purge_home -and (Test-Path -LiteralPath $home_dir)) {
    Remove-Item -LiteralPath $home_dir -Recurse -Force
    Write-Host "Deleted $home_dir"
    if ($env:HAIFA_LIBRARY) {
        Write-Host "The library $env:HAIFA_LIBRARY (HAIFA_LIBRARY) is outside it and stays."
    }
} elseif (Test-Path -LiteralPath $home_dir) {
    Write-Host "HAIFA data stay in $home_dir"
}
Write-Host 'Dependencies (git, uv, gh, node, claude, codex) and .factory/ in repositories stay.'
