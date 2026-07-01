param(
    [switch]$InstallPyInstaller,
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }
$AppPy = Join-Path $ProjectRoot "app.py"
$Icon = Join-Path $ProjectRoot "assets\icon.ico"
$Assets = Join-Path $ProjectRoot "assets"
$Vendor = Join-Path $ProjectRoot "vendor"
$Dist = Join-Path $ProjectRoot "dist"
$Build = Join-Path $ProjectRoot "build"
$ExeName = "WatermarkStudio"

Write-Host "Python: $Python"

$UserSite = & $Python -c "import site; print(site.getusersitepackages())"
if ($UserSite -and (Test-Path $UserSite)) {
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$UserSite;$env:PYTHONPATH"
    } else {
        $env:PYTHONPATH = $UserSite
    }
}

$HasPyInstaller = & $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    if ($InstallPyInstaller) {
        Write-Host "Installing PyInstaller..."
        & $Python -m pip install --user pyinstaller
    } else {
        Write-Host ""
        Write-Host "PyInstaller is not installed."
        Write-Host "Run this command to install it and build:"
        Write-Host "  .\build_exe.ps1 -InstallPyInstaller"
        exit 2
    }
}

$ModeArgs = if ($OneFile) { @("--onefile") } else { @("--onedir") }
$IconArgs = if (Test-Path $Icon) { @("--icon", $Icon) } else { @() }
$PathArgs = if (Test-Path $Vendor) { @("--paths", $Vendor) } else { @() }
$AddDataArgs = if (Test-Path $Assets) { @("--add-data", "$Assets;assets") } else { @() }
$CollectDataArgs = @()
& $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('tkinterdnd2') else 1)"
if ($LASTEXITCODE -eq 0) {
    $CollectDataArgs += @("--collect-data", "tkinterdnd2")
}
$ArabicArgs = @()
if (Test-Path (Join-Path $Vendor "arabic_reshaper")) {
    $ArabicArgs += @("--hidden-import", "arabic_reshaper", "--hidden-import", "bidi.algorithm")
}

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed"
) + $ModeArgs + @(
    "--name",
    $ExeName,
    "--distpath",
    $Dist,
    "--workpath",
    $Build,
    "--specpath",
    $Build
) + $IconArgs + $PathArgs + $AddDataArgs + $CollectDataArgs + $ArabicArgs + @(
    $AppPy
)

& $Python -m PyInstaller @PyInstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$BuiltExe = if ($OneFile) {
    Join-Path $Dist "$ExeName.exe"
} else {
    Join-Path $Dist "$ExeName\$ExeName.exe"
}

Write-Host ""
Write-Host "Build finished:"
Write-Host "  $BuiltExe"
