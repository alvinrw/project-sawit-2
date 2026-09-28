#Requires -Version 5.1
# build_firmware.ps1 — compile-only firmware lokal via bundled arduino-cli Arduino IDE.
# Menolak upload; upload via Arduino IDE GUI manual.
param(
  [string]$SketchDir = "rekam-new/src/firmware/RawSawitRecorder",
  [string]$Fqbn = "rakwireless:nrf52:WisCoreRAK4631Board",
  [string]$BuildDir = "rekam-new/src/firmware/build",
  [string]$Cli = ""
)

$ErrorActionPreference = "Stop"

# Temukan arduino-cli di PATH, di Arduino IDE, atau lewat -Cli.
$cli = $Cli
if (-not $cli) {
  $onPath = Get-Command arduino-cli -ErrorAction SilentlyContinue
  if ($onPath) {
    $cli = $onPath.Source
  } else {
    $ideGlobs = @(
      "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe",
      "$env:ProgramFiles\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe",
      "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
    )
    $cli = $ideGlobs | Where-Object { Test-Path $_ } | Select-Object -First 1
  }
}
if (-not $cli) {
  throw "arduino-cli tidak ditemukan. Pasang Arduino IDE, atau jalankan dengan -Cli <path ke arduino-cli>."
}
& $cli version
New-Item -ItemType Directory -Force $BuildDir | Out-Null
& $cli compile --fqbn $Fqbn --build-path $BuildDir $SketchDir
if ($LASTEXITCODE -ne 0) { throw "compile gagal (exit $LASTEXITCODE)" }
Write-Host "OK: compile sukses, output di $BuildDir (ignored). Upload via Arduino IDE manual."
