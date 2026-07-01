param(
    [switch]$IncludeFfmpeg,
    [string]$FfmpegPath = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $ProjectRoot "dist\WatermarkStudio"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PackageDir = Join-Path $ReleaseRoot "WatermarkStudio"
$ZipPath = Join-Path $ReleaseRoot "WatermarkStudio_Portable.zip"

if (-not (Test-Path (Join-Path $Dist "WatermarkStudio.exe"))) {
    throw "dist\WatermarkStudio\WatermarkStudio.exe does not exist. Run build_exe.ps1 first."
}

if (Test-Path $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Copy-Item -LiteralPath $Dist -Destination $PackageDir -Recurse -Force

if ($IncludeFfmpeg) {
    $Candidates = @()
    if ($FfmpegPath) { $Candidates += $FfmpegPath }
    $Candidates += @(
        (Join-Path $ProjectRoot "ffmpeg.exe"),
        "C:\Program Files\ShareX\ffmpeg.exe",
        "C:\Program Files\BlueStacks_msi5\ffmpeg.exe",
        "C:\ffmpeg\bin\ffmpeg.exe"
    )

    $FoundFfmpeg = $null
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            $FoundFfmpeg = (Resolve-Path $Candidate).Path
            break
        }
    }

    if ($FoundFfmpeg) {
        Copy-Item -LiteralPath $FoundFfmpeg -Destination (Join-Path $PackageDir "ffmpeg.exe") -Force
        Write-Host "Included FFmpeg: $FoundFfmpeg"
    } else {
        Write-Host "FFmpeg was not found. The package will still work for images; videos need ffmpeg.exe."
    }
}

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force

$Bytes = (Get-Item $ZipPath).Length
Write-Host ""
Write-Host "Portable package created:"
Write-Host "  $ZipPath"
Write-Host ("  Size: {0} MB" -f ([math]::Round($Bytes / 1MB, 2)))

