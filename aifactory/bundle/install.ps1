# Installs HAIFA (the `factory` tool) from this bundle on Windows: checks and installs the
# dependencies, installs factory with uv and seeds the library. Windows PowerShell 5.1 and
# PowerShell 7. Started by install.bat; ASCII only, PowerShell 5.1 reads it as ANSI.
$ErrorActionPreference = 'Stop'

$Wheel = '@WHEEL@'
$Version = '@VERSION@'

# name on PATH, how to install it, the package
$Dependencies = @(
    @('git', 'winget', 'Git.Git'),
    @('uv', 'winget', 'astral-sh.uv'),
    @('gh', 'winget', 'GitHub.cli'),
    @('node', 'winget', 'OpenJS.NodeJS.LTS'),
    @('claude', 'npm', '@anthropic-ai/claude-code'),
    @('codex', 'npm', '@openai/codex')
)

function Fail([string]$Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Step([string]$Message) {
    Write-Host ''
    Write-Host "== $Message"
}

function Test-Tool([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Native([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Fail "$What failed (exit code $LASTEXITCODE)"
    }
}

# An installer puts its directory on the Machine or User PATH in the registry; this session
# still has the old PATH, so the registry entries it lacks are appended.
function Update-SessionPath {
    $seen = @{}
    $parts = New-Object System.Collections.Generic.List[string]
    $all = @($env:Path -split ';') +
        @(([Environment]::GetEnvironmentVariable('Path', 'Machine') + '') -split ';') +
        @(([Environment]::GetEnvironmentVariable('Path', 'User') + '') -split ';')
    foreach ($entry in $all) {
        if (-not $entry) { continue }
        $expanded = [Environment]::ExpandEnvironmentVariables($entry)
        $key = $expanded.TrimEnd('\').ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $parts.Add($expanded)
    }
    $env:Path = $parts -join ';'
}

function Install-Dependency([string]$Name, [string]$Via, [string]$Package) {
    if (Test-Tool $Name) {
        Write-Host "  $Name ok"
        return
    }
    Write-Host "  $Name missing, installing $Package with $Via"
    if ($Via -eq 'winget') {
        if (-not (Test-Tool 'winget')) {
            Fail "$Name is missing and winget is not available. Install $Name yourself ($Package), then run install.bat again."
        }
        Invoke-Native "winget install $Package" {
            winget install --id $Package -e --accept-source-agreements --accept-package-agreements
        }
    } else {
        Invoke-Native "npm install -g $Package" { npm install -g $Package }
    }
    if (-not (Test-Tool $Name)) {
        Update-SessionPath
    }
    if (-not (Test-Tool $Name)) {
        Fail "$Name was installed but is not on PATH. Open a new terminal and run install.bat again."
    }
}

# .NET instead of Get-FileHash: Windows PowerShell started from PowerShell 7 inherits its
# PSModulePath and does not find Get-FileHash.
function Get-Sha256([string]$Path) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $bytes = $sha.ComputeHash($stream)
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Test-GitValue([string]$Key) {
    $value = git config --get $Key
    return ($LASTEXITCODE -eq 0) -and [bool]("$value".Trim())
}

Set-Location $PSScriptRoot
Write-Host "Installing HAIFA $Version"

Step 'Verifying SHA256SUMS'
foreach ($line in Get-Content -LiteralPath 'SHA256SUMS') {
    if (-not $line.Trim()) { continue }
    $digest, $name = $line -split '  ', 2
    if (-not (Test-Path -LiteralPath $name -PathType Leaf)) {
        Fail "SHA256SUMS: $name is missing"
    }
    $actual = Get-Sha256 (Join-Path $PSScriptRoot $name)
    if ($actual -ne $digest.ToLowerInvariant()) {
        Fail "SHA256SUMS: $name does not match; the bundle is damaged, download it again"
    }
    Write-Host "  ${name}: OK"
}

Step 'Checking dependencies'
foreach ($dep in $Dependencies) {
    Install-Dependency $dep[0] $dep[1] $dep[2]
}

Step 'Checking git identity'
foreach ($pair in @(@('user.name', 'Your name for git commits'), @('user.email', 'Your e-mail for git commits'))) {
    if (Test-GitValue $pair[0]) {
        Write-Host "  $($pair[0]) ok"
        continue
    }
    $value = Read-Host "  $($pair[1])"
    if (-not "$value".Trim()) {
        Fail "git $($pair[0]) is not set; run: git config --global $($pair[0]) <value>"
    }
    Invoke-Native "git config --global $($pair[0])" { git config --global $pair[0] "$value".Trim() }
}

Step 'Installing factory'
Invoke-Native 'uv tool install' { uv tool install --force $Wheel --constraints constraints.txt }
Invoke-Native 'uv tool update-shell' { uv tool update-shell }
$bin = (uv tool dir --bin | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $bin) {
    Fail 'uv tool dir --bin failed'
}
$factory = Join-Path $bin 'factory.exe'
if (-not (Test-Path -LiteralPath $factory -PathType Leaf)) {
    Fail "factory is not at $factory after uv tool install"
}

Step 'Seeding the library'
$status = (& $factory library status --json | Out-String) | ConvertFrom-Json
if ($status.ok) {
    Invoke-Native 'factory library seed' { & $factory library seed }
} elseif ($status.error.code -eq 'library_missing') {
    Invoke-Native 'factory library init' { & $factory library init }
} else {
    Fail "factory library status: $($status.error.message)"
}

Write-Host ''
Write-Host "HAIFA $Version installed."
Write-Host 'Log in where you have not yet: gh auth login, claude auth login, codex login'
Write-Host 'Then open a new terminal and check prerequisites and logins with: factory check'
