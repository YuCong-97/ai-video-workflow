#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

PORT="${APP_PORT:-7860}"
COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"
COMFYUI_DIR="${COMFYUI_DIR:-/workspace/ComfyUI}"
HUNYUAN_ROOT="${HUNYUAN_ROOT:-/workspace/HunyuanVideo-I2V}"
HUNYUAN_CKPT="${HUNYUAN_CKPT:-/models/hunyuan/ckpts}"
HUNYUAN_REPO_URL="${HUNYUAN_REPO_URL:-}"
HUNYUAN_MODEL_REPO="${HUNYUAN_MODEL_REPO:-}"
WORKFLOW_ARG=""
NO_MODEL=0

usage() {
  cat <<'EOF'
Usage:
  scripts/linux/setup_real_generation.sh [options]

Options:
  --workflow PATH         Copy local ComfyUI API workflow JSON.
  --workflow-url URL      Download ComfyUI API workflow JSON.
  --comfyui-dir PATH      ComfyUI install directory.
  --hunyuan-root PATH     HunyuanVideo-I2V install directory.
  --hunyuan-ckpt PATH     HunyuanVideo model directory.
  --hunyuan-repo URL      HunyuanVideo git repository URL.
  --hunyuan-model-repo ID Hugging Face model repo ID.
  --no-model              Skip model download.

This prepares ComfyUI + HunyuanVideo-I2V and updates .env for start_visual.sh.
EOF
}

WORKFLOW_URL_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --workflow)
      WORKFLOW_ARG="${2:?Missing value for --workflow}"
      shift 2
      ;;
    --workflow-url)
      WORKFLOW_URL_ARG="${2:?Missing value for --workflow-url}"
      shift 2
      ;;
    --comfyui-dir)
      COMFYUI_DIR="${2:?Missing value for --comfyui-dir}"
      shift 2
      ;;
    --hunyuan-root)
      HUNYUAN_ROOT="${2:?Missing value for --hunyuan-root}"
      shift 2
      ;;
    --hunyuan-ckpt)
      HUNYUAN_CKPT="${2:?Missing value for --hunyuan-ckpt}"
      shift 2
      ;;
    --hunyuan-repo)
      HUNYUAN_REPO_URL="${2:?Missing value for --hunyuan-repo}"
      shift 2
      ;;
    --hunyuan-model-repo)
      HUNYUAN_MODEL_REPO="${2:?Missing value for --hunyuan-model-repo}"
      shift 2
      ;;
    --no-model)
      NO_MODEL=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

cd "$PROJECT_DIR"

comfy_args=(--dir "$COMFYUI_DIR" --target "$PROJECT_DIR/input/config/comfyui_workflow_api.json")
if [[ -n "$WORKFLOW_ARG" ]]; then
  comfy_args+=(--workflow "$WORKFLOW_ARG")
fi
if [[ -n "$WORKFLOW_URL_ARG" ]]; then
  comfy_args+=(--workflow-url "$WORKFLOW_URL_ARG")
fi
bash "$SCRIPT_DIR/setup_comfyui.sh" "${comfy_args[@]}"

hunyuan_args=(--root "$HUNYUAN_ROOT" --ckpt "$HUNYUAN_CKPT")
if [[ -n "$HUNYUAN_REPO_URL" ]]; then
  hunyuan_args+=(--repo "$HUNYUAN_REPO_URL")
fi
if [[ -n "$HUNYUAN_MODEL_REPO" ]]; then
  hunyuan_args+=(--model-repo "$HUNYUAN_MODEL_REPO")
fi
if [[ "$NO_MODEL" -eq 1 ]]; then
  hunyuan_args+=(--no-model)
fi
bash "$SCRIPT_DIR/setup_hunyuan_i2v.sh" "${hunyuan_args[@]}"

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
fi

python3 - "$PROJECT_DIR/.env" "$COMFYUI_URL" "$HUNYUAN_ROOT" "$HUNYUAN_CKPT" "$PORT" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
values = {
    "COMFYUI_URL": sys.argv[2],
    "HUNYUAN_ROOT": sys.argv[3],
    "HUNYUAN_CKPT": sys.argv[4],
    "APP_PORT": sys.argv[5],
}
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out = []
seen = set()
for line in lines:
    key = line.split("=", 1)[0].strip()
    if key in values:
        out.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in values.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

echo ""
echo "Real generation setup complete."
echo "Run checks:"
echo "  python scripts/check_real_generation.py"
echo ""
echo "Start services:"
echo "  cd $COMFYUI_DIR && python3 main.py --listen 0.0.0.0 --port 8188"
echo "  cd $PROJECT_DIR && ./start_visual.sh --port $PORT"
