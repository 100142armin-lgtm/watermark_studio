@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0package_portable.ps1" %*
