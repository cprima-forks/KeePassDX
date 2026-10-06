#Requires -Version 7
<#
.SYNOPSIS
    Idempotently installs the Android build tools for KeePassDX on a chosen drive.

.DESCRIPTION
    Installs only the SDK packages that are missing under -Root, using sdkmanager.
    A second run with everything present changes nothing.

    Nothing is changed machine-wide: no registry, no persistent environment
    variables. The script prints the variables to set for a build session.

    Licenses are never accepted silently. Pass -AcceptLicenses to accept them.

    Package names below are UNVERIFIED against `sdkmanager --list`. If sdkmanager
    reports an unknown package, fix the name in -Packages.

.EXAMPLE
    ./cprima-fork/tools/Setup-AndroidBuild.ps1 -Dry
    ./cprima-fork/tools/Setup-AndroidBuild.ps1 -AcceptLicenses -WriteLocalProperties -WriteEnv

    Defaults for -Root, -GradleHome and -Jdk come from cprima-fork/tools/.env when it exists.
    An explicit parameter overrides it.
#>
[CmdletBinding()]
param(
    [string]$Root = 'O:\android-sdk',
    [string]$GradleHome = 'O:\gradle-home',
    # Folder that contains sdkmanager.bat. Default: look under -Root, then ANDROID_HOME.
    [string]$CmdlineToolsBin,
    [string]$Jdk = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot',
    [string[]]$Packages = @(
        'platform-tools',
        'platforms;android-36',
        'build-tools;36.0.0',
        'ndk;25.2.9519653',
        'cmake;3.22.1'
    ),
    # Refuse to install when the target drive has less free space than this.
    [double]$MinFreeGB = 6,
    [switch]$AcceptLicenses,
    [switch]$WriteLocalProperties,
    # Write JAVA_HOME, ANDROID_HOME and GRADLE_USER_HOME into cprima-fork/tools/.env (other lines are kept).
    [switch]$WriteEnv,
    # Run `gradlew --version` with GRADLE_USER_HOME set, to fetch the Gradle distribution.
    [switch]$WarmGradle,
    [switch]$Dry
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

# Defaults come from cprima-fork/tools/.env when present; an explicit parameter wins.
. (Join-Path $PSScriptRoot 'DotEnv.ps1')
$EnvFile = Join-Path $PSScriptRoot '.env'
$dotenv = Read-DotEnv -Path $EnvFile
if (-not $PSBoundParameters.ContainsKey('Root') -and $dotenv['ANDROID_HOME']) {
    $Root = $dotenv['ANDROID_HOME'] -replace '/', '\'
}
if (-not $PSBoundParameters.ContainsKey('GradleHome') -and $dotenv['GRADLE_USER_HOME']) {
    $GradleHome = $dotenv['GRADLE_USER_HOME'] -replace '/', '\'
}
if (-not $PSBoundParameters.ContainsKey('Jdk') -and $dotenv['JAVA_HOME']) {
    $Jdk = $dotenv['JAVA_HOME'] -replace '/', '\'
}

function Write-Step([string]$Text) { Write-Host "== $Text" -ForegroundColor Cyan }

function Get-PackageDir([string]$Package) {
    # sdkmanager lays packages out by replacing ';' with a path separator.
    Join-Path $Root ($Package -replace ';', '\')
}

function Find-SdkManager {
    $candidates = @()
    if ($CmdlineToolsBin) { $candidates += Join-Path $CmdlineToolsBin 'sdkmanager.bat' }
    $candidates += Join-Path $Root 'cmdline-tools\latest\bin\sdkmanager.bat'
    if ($env:ANDROID_HOME) {
        $candidates += Join-Path $env:ANDROID_HOME 'cmdline-tools\latest\bin\sdkmanager.bat'
    }
    $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

# --- Preflight -------------------------------------------------------------
Write-Step 'Preflight'

$javaExe = Join-Path $Jdk 'bin\java.exe'
if (-not (Test-Path $javaExe)) { throw "JDK not found: $javaExe (use -Jdk)" }
Write-Host "JDK         : $Jdk"

$sdkManager = Find-SdkManager
if (-not $sdkManager) {
    throw 'sdkmanager.bat not found. Pass -CmdlineToolsBin <folder containing sdkmanager.bat>.'
}
Write-Host "sdkmanager  : $sdkManager"
Write-Host "SDK root    : $Root"
Write-Host "Gradle home : $GradleHome"

$missing = @($Packages | Where-Object { -not (Test-Path (Get-PackageDir $_)) })
$present = @($Packages | Where-Object { Test-Path (Get-PackageDir $_) })

Write-Step 'Packages'
foreach ($p in $present) { Write-Host ("  present  {0}" -f $p) -ForegroundColor DarkGreen }
foreach ($p in $missing) { Write-Host ("  MISSING  {0}" -f $p) -ForegroundColor Yellow }

if ($missing.Count -gt 0) {
    $driveRoot = [System.IO.Path]::GetPathRoot($Root)
    if (-not (Test-Path $driveRoot)) { throw "Drive not available: $driveRoot" }
    $freeGB = [math]::Round(([System.IO.DriveInfo]::new($driveRoot).AvailableFreeSpace / 1GB), 1)
    Write-Host ("Free space on {0} : {1} GB (required: {2} GB)" -f $driveRoot, $freeGB, $MinFreeGB)
    if ($freeGB -lt $MinFreeGB) {
        $msg = "Not enough free space on $driveRoot. Free some space, lower -MinFreeGB, or choose another -Root."
        if ($Dry) { Write-Warning $msg } else { throw $msg }
    }
}

if ($Dry) {
    Write-Step 'Dry run: nothing changed'
    if ($missing.Count -gt 0) { Write-Host "Would install: $($missing -join ', ')" }
    else { Write-Host 'Would install nothing.' }
    return
}

# --- Install ---------------------------------------------------------------
$oldJavaHome = $env:JAVA_HOME
try {
    $env:JAVA_HOME = $Jdk   # process-local, restored below

    if ($missing.Count -gt 0) {
        Write-Step 'Installing missing packages'
        New-Item -ItemType Directory -Force -Path $Root | Out-Null
        $args = @("--sdk_root=$Root") + $missing
        if ($AcceptLicenses) {
            (1..30 | ForEach-Object { 'y' }) | & $sdkManager @args
        } else {
            & $sdkManager @args
        }
        if ($LASTEXITCODE -ne 0) { throw "sdkmanager failed with exit code $LASTEXITCODE" }

        $stillMissing = @($missing | Where-Object { -not (Test-Path (Get-PackageDir $_)) })
        if ($stillMissing.Count -gt 0) { throw "Not installed: $($stillMissing -join ', ')" }
    }

    # --- Gradle home -------------------------------------------------------
    New-Item -ItemType Directory -Force -Path $GradleHome | Out-Null

    # --- local.properties (git-ignored) -----------------------------------
    if ($WriteLocalProperties) {
        Write-Step 'local.properties'
        $lp = Join-Path $RepoRoot 'local.properties'
        $want = "sdk.dir=" + ($Root -replace '\\', '/') + "`n"
        $have = if (Test-Path $lp) { [System.IO.File]::ReadAllText($lp) } else { $null }
        if ($have -ne $want) {
            [System.IO.File]::WriteAllText($lp, $want, [System.Text.UTF8Encoding]::new($false))
            Write-Host "written: $lp"
        } else {
            Write-Host 'unchanged'
        }
    }

    # --- cprima-fork/tools/.env (git-ignored) ------------------------------------
    if ($WriteEnv) {
        Write-Step '.env'
        $changed = Update-DotEnv -Path $EnvFile -Values ([ordered]@{
            JAVA_HOME        = $Jdk -replace '\\', '/'
            ANDROID_HOME     = $Root -replace '\\', '/'
            GRADLE_USER_HOME = $GradleHome -replace '\\', '/'
        })
        Write-Host ($(if ($changed) { "written: $EnvFile" } else { 'unchanged' }))
    }

    # --- Optional: fetch the Gradle distribution --------------------------
    if ($WarmGradle) {
        Write-Step 'Gradle wrapper'
        $oldGradleHome = $env:GRADLE_USER_HOME
        try {
            $env:GRADLE_USER_HOME = $GradleHome
            Push-Location $RepoRoot
            & .\gradlew.bat --version
            if ($LASTEXITCODE -ne 0) { throw "gradlew failed with exit code $LASTEXITCODE" }
        } finally {
            Pop-Location
            $env:GRADLE_USER_HOME = $oldGradleHome
        }
    }
} finally {
    $env:JAVA_HOME = $oldJavaHome
}

# --- Result ----------------------------------------------------------------
Write-Step 'Done. For a build session, run:'
Write-Host "`$env:JAVA_HOME        = '$Jdk'"
Write-Host "`$env:ANDROID_HOME     = '$Root'"
Write-Host "`$env:GRADLE_USER_HOME = '$GradleHome'"
