param(
    [int]$Port = 7860,
    [switch]$NoBuild,
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $line = "$Key=$Value"
    if (-not (Test-Path -LiteralPath $Path)) {
        Set-Content -LiteralPath $Path -Value $line -Encoding UTF8
        return
    }

    $content = Get-Content -LiteralPath $Path -Encoding UTF8
    $matched = $false
    $updated = foreach ($item in $content) {
        if ($item -match "^\s*$([regex]::Escape($Key))\s*=") {
            $matched = $true
            $line
        } else {
            $item
        }
    }

    if (-not $matched) {
        $updated += $line
    }
    Set-Content -LiteralPath $Path -Value $updated -Encoding UTF8
}

function Ensure-Directory {
    param([string]$Path)
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example"
}

Set-DotEnvValue -Path ".env" -Key "APP_PORT" -Value "$Port"

$dirs = @(
    "models",
    "models/hunyuan/ckpts",
    "external",
    "external/HunyuanVideo-1.5",
    "data/jobs",
    "data/prompts",
    "assets/references",
    "outputs/jobs",
    "outputs/images",
    "outputs/videos/raw",
    "logs",
    "temp"
)

foreach ($dir in $dirs) {
    Ensure-Directory -Path $dir
}

docker compose config | Out-Null
Write-Host "Docker Compose config OK"

try {
    docker info | Out-Null
} catch {
    Write-Host ""
    Write-Host "Docker Engine is not running. Start Docker Desktop, then run this script again."
    throw
}

if (-not $NoBuild) {
    docker compose build web
}

$upArgs = @("compose", "up", "-d", "web")
if ($Recreate) {
    $upArgs = @("compose", "up", "-d", "--force-recreate", "web")
}

docker @upArgs

Write-Host ""
Write-Host "Visual page is running:"
Write-Host "http://localhost:$Port"
Write-Host ""
Write-Host "Stop it with:"
Write-Host "docker compose stop web"
