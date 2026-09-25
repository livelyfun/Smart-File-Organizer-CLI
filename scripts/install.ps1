<#
.SYNOPSIS
    Smart File Organizer - one-step installer for Windows.

.DESCRIPTION
    By default this downloads a prebuilt, self-contained installer. Python is
    NOT required. Use -FromSource to install from a git checkout instead,
    which does require Python 3.9 or newer.

    The downloaded installer is verified against the SHA-256 checksum
    published alongside the release before it is run.

.PARAMETER Version
    Install a specific release, for example "1.2.0". Defaults to the latest.

.PARAMETER FromSource
    Install from this checkout using pip into a private virtual environment,
    instead of downloading a prebuilt release.

.PARAMETER System
    Install per-machine (requires elevation) instead of per-user.

.EXAMPLE
    .\scripts\install.ps1
    .\scripts\install.ps1 -Version 1.2.0
    .\scripts\install.ps1 -FromSource
#>

[CmdletBinding()]
param(
    [string] $Version = "",
    [switch] $FromSource,
    [switch] $System
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$AppName    = "smart-organizer"
$Repo       = "livelyfun/Smart-File-Organizer-CLI"
$ReleasesApi = "https://api.github.com/repos/$Repo/releases/latest"

if ($System) {
    $InstallRoot = Join-Path $env:ProgramFiles "SmartFileOrganizer"
} else {
    $InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\SmartFileOrganizer"
}

function Write-Step($Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Fail($Message) { Write-Host "error: $Message" -ForegroundColor Red; exit 1 }

function Get-Sha256($Path) {
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    # Windows PowerShell 5.1 without Get-FileHash.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        try {
            return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
        } finally { $stream.Dispose() }
    } finally { $sha.Dispose() }
}

function Get-RemoteFile($Url, $Destination) {
    # TLS 1.2+ only. Windows PowerShell 5.1 still defaults to older
    # protocols, where GitHub simply refuses the connection.
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch { }

    Write-Step "Downloading $(Split-Path -Leaf $Destination)"
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -MaximumRedirection 5
    } catch {
        Fail "could not download $Url`n$($_.Exception.Message)"
    }
}

function Get-LatestVersion {
    Write-Step "Looking up the latest release"
    try {
        $response = Invoke-RestMethod -Uri $ReleasesApi -UseBasicParsing -Headers @{
            'User-Agent' = 'smart-file-organizer-installer'
            'Accept'     = 'application/vnd.github+json'
        }
        $tag = [string]$response.tag_name
        return $tag.TrimStart('v', 'V')
    } catch {
        Fail "could not query the latest release from GitHub`n$($_.Exception.Message)"
    }
}

function Install-FromSource {
    Write-Step "Installing from source into $InstallRoot"

    $pythonCmd = $null
    foreach ($candidate in @("python", "py")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            try {
                $raw = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if ($raw) {
                    $parts = $raw.Trim().Split('.')
                    if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 9) { $pythonCmd = $candidate; break }
                }
            } catch { }
        }
    }
    if (-not $pythonCmd) {
        Fail "Python 3.9 or newer was not found. Install it, or drop -FromSource to install the prebuilt release."
    }

    $scriptDir = Split-Path -Parent $PSScriptRoot
    $venvPath  = Join-Path $InstallRoot "venv"

    & $pythonCmd -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { Fail "could not create a virtual environment" }

    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet $scriptDir
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }

    Write-Host ""
    Write-Host "Installed from source. Python 3.9+ is required for this mode." -ForegroundColor Green
    Write-Host "Add to PATH: $venvPath\Scripts"
    return
}

# ---------------------------------------------------------------- main

Write-Host "=================================================="
Write-Host "    Smart File Organizer - Installer (Windows)"
Write-Host "=================================================="
Write-Host ""

if ($FromSource) { Install-FromSource; return }

if ([string]::IsNullOrWhiteSpace($Version)) { $Version = Get-LatestVersion }
Write-Step "Installing $AppName $Version"

$arch = $env:PROCESSOR_ARCHITECTURE
if ($arch -ne "AMD64") {
    Fail "no prebuilt release for $arch. Use -FromSource to build from a checkout."
}

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sfo-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    $setupName = "SmartFileOrganizer-$Version-setup.exe"
    $baseUrl   = "https://github.com/$Repo/releases/download/v$Version"

    $setupPath = Join-Path $tempDir $setupName
    $sumPath   = Join-Path $tempDir "$setupName.sha256"

    Get-RemoteFile "$baseUrl/$setupName" $setupPath
    Get-RemoteFile "$baseUrl/$setupName.sha256" $sumPath

    $expected = ((Get-Content $sumPath -Raw) -split '\s+')[0].ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($expected)) {
        Fail "checksum file for $setupName was empty or malformed"
    }

    $actual = Get-Sha256 $setupPath
    if ($actual -ne $expected) {
        Remove-Item $setupPath -Force -ErrorAction SilentlyContinue
        Fail "checksum mismatch for $setupName.`n  expected: $expected`n  actual:   $actual`nThe download has been discarded. If this persists, the release may have been tampered with; please report it on the project's issue tracker."
    }
    Write-Step "Checksum verified"

    Write-Step "Running $setupName"
    # Per-user installs must not be elevated; a machine-wide install will ask
    # through the installer itself, which is the normal UAC prompt.
    $process = Start-Process -FilePath $setupPath -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        Fail "the installer exited with code $($process.ExitCode)"
    }
} finally {
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

# A frozen build must run. Prove it rather than leaving the user to find out.
$exe = Join-Path $InstallRoot "$AppName.exe"
if (-not (Test-Path $exe)) {
    $found = Get-ChildItem -Path $InstallRoot -Filter "$AppName.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $exe = $found.FullName } else { Fail "could not find $AppName.exe under $InstallRoot" }
}

try {
    $versionOutput = & $exe --version 2>&1
    Write-Step "Installed: $versionOutput"
} catch {
    Fail "the installed executable failed to run. Re-run with -FromSource, or report this on the project's issue tracker."
}

Write-Host ""
Write-Host "=================================================="
Write-Host "  Installation Successful"
Write-Host "=================================================="
Write-Host ""
Write-Host "Installed to: $exe"
Write-Host ""
Write-Host "Then try:"
Write-Host "    $AppName --status"
Write-Host "    $AppName"
