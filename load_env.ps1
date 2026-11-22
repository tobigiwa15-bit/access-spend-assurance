# Copy the settings in .env into this PowerShell session's environment.
# Python scripts read .env themselves (python-dotenv), but dbt doesn't, so run
# this once per terminal before using dbt:
#     . .\load_env.ps1
# (the leading dot and space matter: they run it in the current session)
# It prints the setting names it loaded, never their values.

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Error "No .env file found. Copy .env.example to .env and fill it in."
    return
}

Get-Content $envFile | ForEach-Object {
    $line = $_.TrimStart([char]0xFEFF)   # ignore the invisible marker some editors add
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        # Drop surrounding spaces and quotes, as python-dotenv does.
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "env:$($Matches[1])" -Value $value
        Write-Host "loaded $($Matches[1])"
    }
}
