param(
    [switch]$NoBuild,
    [switch]$NoCheck
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example"
}

$dirs = @(
    "models",
    "models/hunyuan/ckpts",
    "external",
    "external/HunyuanVideo-1.5"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

docker compose config | Out-Null
Write-Host "Docker Compose config OK"

if (-not $NoBuild) {
    docker compose build
}

if (-not $NoCheck) {
    docker compose run --rm pipeline python --version
    docker compose run --rm pipeline ffmpeg -version
    docker compose run --rm pipeline python -c "import cv2, edge_tts, openai, pandas, yaml; print('Python modules OK')"
}

