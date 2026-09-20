param([Parameter(ValueFromRemainingArguments=$true)][string[]]$PilotArgs)
$ErrorActionPreference = 'Stop'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pythonCommand = if (Test-Path -LiteralPath $localPython) { $localPython } elseif (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { 'python' }
Push-Location $PSScriptRoot
try {
    if (-not $PilotArgs -or $PilotArgs.Count -eq 0) {
        & $pythonCommand -m lqa_pilot --help
    } else {
        & $pythonCommand -m lqa_pilot @PilotArgs
    }
    exit $LASTEXITCODE
} finally { Pop-Location }
