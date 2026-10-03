# Fork-only task runner. Not part of any upstream PR (see FORK-WORKFLOW.md).
# Values come from cprima-fork/tools/.env (copy cprima-fork/tools/.env.example).

set shell := ["pwsh", "-NoProfile", "-Command"]
set dotenv-path := "cprima-fork/tools/.env"
set dotenv-load := true
set dotenv-override := true

mod fork 'cprima-fork/tools'
mod fixture 'cprima-fork/test-fixtures/tel'

# List all recipes, including those of the modules
default:
    @just --list --list-submodules

# Show the environment this fork uses
env:
    Write-Host "JAVA_HOME        = $env:JAVA_HOME"
    Write-Host "ANDROID_HOME     = $env:ANDROID_HOME"
    Write-Host "GRADLE_USER_HOME = $env:GRADLE_USER_HOME"
    Write-Host "BUILD_TMP        = $env:BUILD_TMP"
    Write-Host "ANDROID_SERIAL   = $(if ($env:ANDROID_SERIAL) { '<set>' } else { '<not set>' })"

# Run Gradle with the fork environment. TEMP and TMP point to BUILD_TMP for this run only.
gradle *args:
    New-Item -ItemType Directory -Force $env:BUILD_TMP | Out-Null; $env:TEMP = $env:BUILD_TMP; $env:TMP = $env:BUILD_TMP; ./gradlew.bat {{args}}

# Build the debug APK of the free flavor (installs next to the F-Droid app)
build: (gradle "assembleFreeDebug")

# List connected Android devices
devices:
    & "$env:ANDROID_HOME/platform-tools/adb.exe" devices -l
