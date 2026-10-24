# Installs the frontend dependencies OUTSIDE OneDrive and links them back.
# npm replaces a node_modules junction during install, so npm runs in the external folder and
# frontend\node_modules stays a junction to <ENV>\frontend_pkg\node_modules.
param([string]$Env = "$env:USERPROFILE\bda-env")
$fe  = Split-Path -Parent $PSScriptRoot
$pkg = Join-Path $Env "frontend_pkg"
New-Item -ItemType Directory -Force $pkg | Out-Null
Copy-Item (Join-Path $fe "package.json"), (Join-Path $fe "package-lock.json") $pkg -Force
Push-Location $pkg; npm ci --no-audit --no-fund; $code = $LASTEXITCODE; Pop-Location
if ($code -ne 0) { throw "npm ci failed ($code)" }
$link = Join-Path $fe "node_modules"
if ((Test-Path $link) -and -not (Get-Item $link -Force).LinkType) { throw "$link is a real folder; move it to $pkg first" }
if (-not (Test-Path $link)) { cmd /c mklink /J "$link" "$(Join-Path $pkg 'node_modules')" | Out-Null }
"node_modules -> " + ((Get-Item $link -Force).Target -join ",")
