# Minimal dotenv support for the fork tools. Dot-source it:
#
#   . .\cprima-fork/tools\DotEnv.ps1
#   Import-DotEnv            # sets the variables in the current session
#
# Format: KEY="value" per line. Blank lines and lines starting with # are ignored.
# Surrounding double quotes are removed. No escapes, no interpolation.
# Use forward slashes in paths. just requires the quotes when a value has spaces.

function Read-DotEnv {
    param([string]$Path = (Join-Path $PSScriptRoot '.env'))
    $map = [ordered]@{}
    if (-not (Test-Path $Path)) { return $map }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $value = $line -split '=', 2
        $value = $value.Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $map[$key.Trim()] = $value
    }
    return $map
}

function Import-DotEnv {
    param([string]$Path = (Join-Path $PSScriptRoot '.env'))
    $map = Read-DotEnv -Path $Path
    foreach ($key in $map.Keys) { Set-Item -Path "Env:$key" -Value $map[$key] }
    return $map
}

function Update-DotEnv {
    # Sets the given keys, keeps every other line, and rewrites the file only on change.
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Values
    )
    $lines = if (Test-Path $Path) { [System.Collections.Generic.List[string]]@(Get-Content -LiteralPath $Path) }
             else { [System.Collections.Generic.List[string]]::new() }
    foreach ($key in $Values.Keys) {
        $new = "$key=`"$($Values[$key])`""
        $index = $lines.FindIndex({ param($l) $l -match "^\s*$([regex]::Escape($key))\s*=" })
        if ($index -ge 0) { $lines[$index] = $new } else { $lines.Add($new) }
    }
    $text = ($lines -join "`n") + "`n"
    $current = if (Test-Path $Path) { [System.IO.File]::ReadAllText($Path) } else { $null }
    if ($current -ne $text) {
        [System.IO.File]::WriteAllText($Path, $text, [System.Text.UTF8Encoding]::new($false))
        return $true
    }
    return $false
}
