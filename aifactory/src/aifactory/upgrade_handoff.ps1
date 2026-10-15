# Installs a verified HAIFA bundle once the factory process that unpacked it has exited.
# Windows locks the files of a running Python, so `uv tool install --force` cannot replace
# the tool environment the dashboard or `factory upgrade` runs from (aifactory.upgrade).
# After the install the new factory.exe refreshes the library to the new seed (status, clone
# --seed-fallback when missing, seed --all); a failure is logged and does not stop the restart.
# The only argument is the JSON plan written by aifactory.upgrade.hand_off.
param([Parameter(Mandatory = $true)][string]$PlanFile)

$plan = [IO.File]::ReadAllText($PlanFile) | ConvertFrom-Json

function Write-Log([string]$Text) {
    [IO.File]::AppendAllText($plan.log, ('{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Text) + "`r`n")
}

function Wait-Exit([int]$Id, [string]$Name) {
    try { $process = [Diagnostics.Process]::GetProcessById($Id) } catch { return }
    if ($Name -and $process.ProcessName -ne $Name) { return }
    try { $exited = $process.WaitForExit(120000) } catch { return }
    if (-not $exited) { Write-Log "process $Id did not exit within 2 minutes" }
}

Write-Log "HAIFA $($plan.version): waiting for process $($plan.pid)"
Wait-Exit $plan.pid ''
# The uv launcher factory.exe waits for its python.exe child and holds its own file.
Wait-Exit $plan.launcher 'factory'

$code = 1
for ($attempt = 1; $attempt -le 3; $attempt++) {
    Push-Location -LiteralPath $plan.cwd
    try { $output = & $plan.uv @($plan.args) 2>&1 | Out-String; $code = $LASTEXITCODE }
    finally { Pop-Location }
    Write-Log "uv tool install (attempt $attempt) exited with ${code}:`r`n$output"
    if ($code -eq 0) { break }
    Start-Sleep -Seconds 3
}

function Update-Library {
    $bin = (& $plan.uv tool dir --bin 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $bin) {
        Write-Log "library not refreshed: uv tool dir --bin failed: $bin"
        return
    }
    $factory = Join-Path $bin 'factory.exe'
    if (-not (Test-Path -LiteralPath $factory -PathType Leaf)) {
        Write-Log "library not refreshed: factory is not at $factory"
        return
    }
    $output = & $factory library status --json 2>$null | Out-String
    if ($LASTEXITCODE -ne 0) {
        $status = $null
        try { $status = $output | ConvertFrom-Json } catch { }
        if (-not $status -or $status.error.code -ne 'library_missing') {
            Write-Log "library not refreshed: factory library status failed:`r`n$output"
            return
        }
        $output = & $factory library clone --seed-fallback 2>&1 | Out-String
        Write-Log "factory library clone --seed-fallback exited with ${LASTEXITCODE}:`r`n$output"
        if ($LASTEXITCODE -ne 0) { return }
    }
    $output = & $factory library seed --all 2>&1 | Out-String
    Write-Log "factory library seed --all exited with ${LASTEXITCODE}:`r`n$output"
}

if ($code -eq 0) {
    try { Update-Library } catch { Write-Log "library not refreshed: $_" }
}

if ($plan.restart) {
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $plan.restart[0]
    $start.Arguments = ($plan.restart | Select-Object -Skip 1 | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $start.UseShellExecute = $true
    [void][Diagnostics.Process]::Start($start)
    Write-Log "dashboard started: $($plan.restart -join ' ')"
}

Remove-Item -LiteralPath $plan.work -Recurse -Force -ErrorAction SilentlyContinue
exit $code
