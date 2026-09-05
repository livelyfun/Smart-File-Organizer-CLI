<#
.SYNOPSIS
    Smart File Organizer - Windows PowerShell One-Step Installer
#>

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "    Smart File Organizer - Installer (Windows)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Detect Python
$pythonCmd = $null
foreach ($cmd in @("python", "py")) {
    try {
        $verStr = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($verStr) {
            $parts = $verStr.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 9) {
                $pythonCmd = $cmd
                break
            }
        }
    } catch {
        # Continue trying next command
    }
}

if (-not $pythonCmd) {
    Write-Error "Python 3.9 or newer was not found. Please install Python from https://www.python.org/downloads/ (check 'Add python.exe to PATH')."
    exit 1
}

$pyVer = & $pythonCmd --version
Write-Host "Found Python: $pyVer" -ForegroundColor Green

# 2. Setup paths
$scriptDir = Split-Path -Parent $PSScriptRoot
$installDir = Join-Path $env:LOCALAPPDATA "SmartFileOrganizer"
$venvDir = Join-Path $installDir "venv"
$binDir = Join-Path $installDir "bin"

Write-Host "Setting up application environment in $installDir..." -ForegroundColor Yellow
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# 3. Create virtual environment
& $pythonCmd -m venv $venvDir

# 4. Install package
$pipExe = Join-Path $venvDir "Scripts\pip.exe"
$organizerExe = Join-Path $venvDir "Scripts\smart-organizer.exe"

Write-Host "Installing Smart File Organizer..." -ForegroundColor Yellow
& $pipExe install --upgrade pip | Out-Null
& $pipExe install $scriptDir | Out-Null

# 5. Create launcher batch script in binDir
if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null
}

$launcherBat = Join-Path $binDir "smart-organizer.cmd"
"@echo off`r`n`"$organizerExe`" %*" | Out-File -FilePath $launcherBat -Encoding ascii

# 6. Add bin directory to user PATH if not present
$userPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
if ($userPath -notlike "*$binDir*") {
    $newPath = "$userPath;$binDir"
    [Environment]::SetEnvironmentVariable("Path", $newPath, [EnvironmentVariableTarget]::User)
    $env:Path = "$env:Path;$binDir"
    Write-Host "Added $binDir to User PATH." -ForegroundColor Green
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  ✓ Installation Successful!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now run Smart File Organizer anywhere using:"
Write-Host ""
Write-Host "    smart-organizer" -ForegroundColor Yellow
Write-Host ""
Write-Host "To organize existing files directly in Downloads:"
Write-Host "    smart-organizer --organize-existing"
Write-Host ""
Write-Host "To view status and configuration:"
Write-Host "    smart-organizer --status"
Write-Host ""
