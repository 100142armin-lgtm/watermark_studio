$ErrorActionPreference = "Stop"

$bundledPython = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$app = Join-Path $PSScriptRoot "app.py"

if (Test-Path $bundledPython) {
    & $bundledPython $app
} else {
    python $app
}
