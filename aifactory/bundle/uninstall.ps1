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
    if ($env:GIRO_HOME) { return $env:GIRO_HOME }
    if ($env:HAIFA_HOME) { return $env:HAIFA_HOME }
    if ($env:XDG_CONFIG_HOME) { return Join-Path $env:XDG_CONFIG_HOME 'giro' }
    $base = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
    return Join-Path (Join-Path $base '.config') 'giro'
}

if ($Purge -and $KeepData) {
    Fail 'use -Purge or -KeepData, not both'
}
if (-not (Get-Command 'uv' -ErrorAction SilentlyContinue)) {
    Fail 'uv is not on PATH; factory was installed with uv, uninstall it with: uv tool uninstall aifactory'
}

$bin = (uv tool dir --bin | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $bin) { Fail 'uv tool dir --bin failed' }
$launcher = Join-Path $bin 'giro.exe'
if (Test-Path -LiteralPath $launcher -PathType Leaf) {
    $home_dir = (& $launcher --data-home | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'Cannot safely resolve the GIRO data home' }
} else {
    $home_dir = Get-HaifaHome
    $legacy = Join-Path (Split-Path $home_dir -Parent) 'haifa'
    if (-not $env:GIRO_HOME -and -not $env:HAIFA_HOME -and (Test-Path -LiteralPath $legacy)) {
        Fail 'Legacy data exist; inspect and set GIRO_HOME explicitly before uninstalling.'
    }
}
if ($home_dir -eq '~' -or $home_dir.StartsWith('~/') -or $home_dir.StartsWith('~\')) {
    $base = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
    $home_dir = if ($home_dir -eq '~') { $base } else { Join-Path $base $home_dir.Substring(2) }
} elseif ($home_dir.StartsWith('~')) {
    Fail 'Cannot safely resolve this home without the installed GIRO launcher.'
}
if ($env:GIRO_HOME -and $env:HAIFA_HOME -and $env:GIRO_HOME -ne $env:HAIFA_HOME) {
    Write-Warning 'GIRO_HOME conflicts with HAIFA_HOME; GIRO_HOME wins.'
}
$purge_home = [bool]$Purge
if (-not $Purge -and -not $KeepData -and (Test-Path -LiteralPath $home_dir)) {
    $answer = Read-Host "Delete also the GIRO data in $home_dir (library with unpushed changes, logs, settings)? [y/N]"
    $purge_home = $answer -match '^(y|yes|a|ano)$'
}

if ($purge_home -and (Test-Path -LiteralPath (Join-Path $home_dir 'giro-migration.json'))) {
    Fail 'Migration data are protected; use -KeepData and follow the rollback instructions.'
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
    $library = if ($env:GIRO_LIBRARY) { $env:GIRO_LIBRARY } else { $env:HAIFA_LIBRARY }
    if ($library) {
        Write-Host "The external library $library stays."
    }
} elseif (Test-Path -LiteralPath $home_dir) {
    Write-Host "GIRO data stay in $home_dir"
}
Write-Host 'Dependencies (git, uv, gh, node, claude, codex) and .factory/ in repositories stay.'
