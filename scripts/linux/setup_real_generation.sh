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
COMFYUI_CKPT_URL="${COMFYUI_CKPT_URL:-}"
COMFYUI_CKPT_PATH="${COMFYUI_CKPT_PATH:-}"
COMFYUI_CKPT_NAME="${COMFYUI_CKPT_NAME:-}"
NO_MODEL=0
UPDATE_CODE=0
FORCE_MODEL_DOWNLOAD=0

usage() {
  cat <<'EOF'
Usage:
  scripts/linux/setup_real_generation.sh [options]

Options:
  --workflow PATH         Copy local ComfyUI API workflow JSON.
  --workflow-url URL      Download ComfyUI API workflow JSON.
  --comfyui-dir PATH      ComfyUI install directory.
  --comfyui-ckpt-url URL  Download a ComfyUI checkpoint.
  --comfyui-ckpt-path PATH Copy an existing ComfyUI checkpoint.
  --comfyui-ckpt-name NAME Target checkpoint filename.
  --hunyuan-root PATH     HunyuanVideo-I2V install directory.
  --hunyuan-ckpt PATH     HunyuanVideo model directory.
  --hunyuan-repo URL      HunyuanVideo git repository URL.
  --hunyuan-model-repo ID Hugging Face model repo ID.
  --no-model              Skip model download.
  --update-code           Pull latest code when repositories already exist.
  --force-model-download  Run model download even if model files exist.

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
    --comfyui-ckpt-url)
      COMFYUI_CKPT_URL="${2:?Missing value for --comfyui-ckpt-url}"
      shift 2
      ;;
    --comfyui-ckpt-path)
      COMFYUI_CKPT_PATH="${2:?Missing value for --comfyui-ckpt-path}"
      shift 2
      ;;
    --comfyui-ckpt-name)
      COMFYUI_CKPT_NAME="${2:?Missing value for --comfyui-ckpt-name}"
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
    --update-code)
      UPDATE_CODE=1
      shift
      ;;
    --force-model-download)
      FORCE_MODEL_DOWNLOAD=1
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
if [[ "$UPDATE_CODE" -eq 1 ]]; then
  comfy_args+=(--update-code)
fi
if [[ -n "$WORKFLOW_ARG" ]]; then
  comfy_args+=(--workflow "$WORKFLOW_ARG")
fi
if [[ -n "$WORKFLOW_URL_ARG" ]]; then
  comfy_args+=(--workflow-url "$WORKFLOW_URL_ARG")
fi
if [[ -n "$COMFYUI_CKPT_URL" ]]; then
  comfy_args+=(--ckpt-url "$COMFYUI_CKPT_URL")
fi
if [[ -n "$COMFYUI_CKPT_PATH" ]]; then
  comfy_args+=(--ckpt-path "$COMFYUI_CKPT_PATH")
fi
if [[ -n "$COMFYUI_CKPT_NAME" ]]; then
  comfy_args+=(--ckpt-name "$COMFYUI_CKPT_NAME")
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
if [[ "$UPDATE_CODE" -eq 1 ]]; then
  hunyuan_args+=(--update-code)
fi
if [[ "$FORCE_MODEL_DOWNLOAD" -eq 1 ]]; then
  hunyuan_args+=(--force-model-download)
fi
bash "$SCRIPT_DIR/setup_hunyuan_i2v.sh" "${hunyuan_args[@]}"

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
fi

python3 - "$PROJECT_DIR/.env" "$COMFYUI_URL" "$HUNYUAN_ROOT" "$HUNYUAN_CKPT" "$PORT" \
  "$COMFYUI_CKPT_URL" "$COMFYUI_CKPT_PATH" "$COMFYUI_CKPT_NAME" <<'PY'
from pathlib import Path
import re
import shlex
import sys

path = Path(sys.argv[1])
values = {
    "COMFYUI_URL": sys.argv[2],
    "HUNYUAN_ROOT": sys.argv[3],
    "HUNYUAN_CKPT": sys.argv[4],
    "APP_PORT": sys.argv[5],
}
optional_values = {
    "COMFYUI_CKPT_URL": sys.argv[6],
    "COMFYUI_CKPT_PATH": sys.argv[7],
    "COMFYUI_CKPT_NAME": sys.argv[8],
    "HUNYUAN_TEXT_ENCODER_REPO": "xtuner/llava-llama-3-8b-v1_1-transformers",
    "HUNYUAN_CLIP_REPO": "openai/clip-vit-large-patch14",
    "HUNYUAN_TORCH_INDEX_URL": "https://download.pytorch.org/whl/cu124",
    "HUNYUAN_TORCH_PACKAGES": "torch torchvision torchaudio",
}
values.update({key: value for key, value in optional_values.items() if value})


def format_env_value(raw: str) -> str:
    if raw == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,~-]+", raw):
        return raw
    return shlex.quote(raw)


lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out = []
seen = set()
for line in lines:
    key = line.split("=", 1)[0].strip()
    if key in values:
        out.append(f"{key}={format_env_value(values[key])}")
        seen.add(key)
    else:
        out.append(line)
for key, value in values.items():
    if key not in seen:
        out.append(f"{key}={format_env_value(value)}")
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
