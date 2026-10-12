# Installs a verified HAIFA bundle once the factory process that unpacked it has exited.
# Windows locks the files of a running Python, so `uv tool install --force` cannot replace
# the tool environment the dashboard or `factory upgrade` runs from (aifactory.upgrade).
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
