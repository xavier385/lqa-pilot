param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled) { $PythonPath = $bundled }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $PythonPath = (Get-Command python).Source }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $PythonPath = (& py -3 -c 'import sys; print(sys.executable)').Trim() }
    else { throw 'Installare Python 3.11 o successivo, oppure avviare Setup.ps1 -PythonPath percorso\python.exe.' }
}
& $PythonPath -c 'import sys; assert sys.version_info >= (3,11), "Serve Python 3.11+"'
if ($LASTEXITCODE -ne 0) { throw 'Versione Python non compatibile.' }
$venvDirectory = Join-Path $PSScriptRoot '.venv'
& $PythonPath -m venv $venvDirectory
if ($LASTEXITCODE -ne 0) { throw 'Creazione ambiente Python non riuscita.' }
$pilotPython = Join-Path $venvDirectory 'Scripts\python.exe'
& $pilotPython -m pip install $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze non riuscita. Verificare la connessione Internet.' }
Write-Host 'Installazione completata. Avviare MuMu e il gioco; usare Start.cmd login con il proprio account ChatGPT, quindi Start.cmd doctor.'
