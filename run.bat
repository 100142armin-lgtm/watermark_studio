@echo off
setlocal
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" "%~dp0app.py"
) else (
  python "%~dp0app.py"
)
