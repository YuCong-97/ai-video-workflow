#!/usr/bin/env bash
set -Eeuo pipefail

HOST="0.0.0.0"
PORT="${APP_PORT:-7860}"
DEFAULT_HUNYUAN_ROOT="${DEFAULT_HUNYUAN_ROOT:-/workspace/HunyuanVideo-I2V}"
DEFAULT_HUNYUAN_TORCH_INDEX_URL="${DEFAULT_HUNYUAN_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
DEFAULT_HUNYUAN_TORCH_PACKAGES="${DEFAULT_HUNYUAN_TORCH_PACKAGES:-torch torchvision torchaudio}"
DEFAULT_COMFYUI_CKPT_URL="${DEFAULT_COMFYUI_CKPT_URL:-https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors}"
DEFAULT_COMFYUI_CKPT_NAME="${DEFAULT_COMFYUI_CKPT_NAME:-DreamShaper_8_pruned.safetensors}"

# Optional Hugging Face token for private/gated model downloads.
# Fill it manually if needed, for example:
# HF_TOKEN_MANUAL="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# An existing environment variable HF_TOKEN still has priority.
HF_TOKEN_MANUAL=""

NO_INSTALL=0
NO_VENV=0
COMFYUI_URL_ARG=""
HUNYUAN_ROOT_ARG=""
HUNYUAN_CKPT_ARG=""
WORKFLOW_ARG=""
CHECK_ONLY=0
SETUP_REAL_GEN=0
NO_MODEL=0
RUNPOD_FULL=0
INSTALL_SYSTEM=0
START_COMFYUI=0
COMFYUI_DIR_ARG=""
WORKFLOW_URL_ARG=""
COMFYUI_CKPT_URL_ARG=""
COMFYUI_CKPT_PATH_ARG=""
COMFYUI_CKPT_NAME_ARG=""
HUNYUAN_MODEL_REPO_ARG=""
HUNYUAN_REPO_ARG=""
UPDATE_CODE=0
FORCE_MODEL_DOWNLOAD=0

usage() {
  cat <<'EOF'
Usage:
  ./start_visual.sh [--port 7860] [--host 0.0.0.0] [--no-install] [--no-venv]
                    [--comfyui-url http://127.0.0.1:8188]
                    [--comfyui-dir /workspace/ComfyUI]
                    [--comfyui-ckpt-url https://example.com/model.safetensors]
                    [--comfyui-ckpt-path /path/to/model.safetensors]
                    [--comfyui-ckpt-name DreamShaper_8_pruned.safetensors]
                    [--hunyuan-root /workspace/HunyuanVideo-I2V]
                    [--hunyuan-ckpt /models/hunyuan/ckpts]
                    [--workflow /path/to/comfyui_workflow_api.json]
                    [--workflow-url https://example.com/workflow.json]
                    [--setup-real-gen] [--runpod-full] [--install-system]
                    [--start-comfyui] [--no-model]
                    [--update-code] [--force-model-download]
                    [--check-only]

Examples:
  ./start_visual.sh --port 7860
  bash start_visual.sh --port 8899
  ./start_visual.sh --workflow /workspace/workflows/your_comfyui_workflow_api.json
  ./start_visual.sh --hunyuan-root /workspace/HunyuanVideo-I2V --hunyuan-ckpt /models/hunyuan/ckpts
  ./start_visual.sh --setup-real-gen --workflow /workspace/workflows/your_comfyui_workflow_api.json
  ./start_visual.sh --runpod-full --port 7860

Notes:
  Use this script on Linux / RunPod.
  Use start_visual.ps1 on Windows PowerShell.
  --runpod-full defaults to the bundled ComfyUI workflow and downloads:
  DreamShaper_8_pruned.safetensors.
  ComfyUI checkpoint options can also be configured through .env:
  COMFYUI_CKPT_URL, COMFYUI_CKPT_PATH, COMFYUI_CKPT_NAME.
  Plain startup prepares paths and config. Use --runpod-full for a blank RunPod:
  system packages, Python deps, ComfyUI, HunyuanVideo-I2V, model download,
  ComfyUI background startup, then this web UI.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      PORT="${2:?Missing value for --port}"
      shift 2
      ;;
    --host)
      HOST="${2:?Missing value for --host}"
      shift 2
      ;;
    --no-install)
      NO_INSTALL=1
      shift
      ;;
    --no-venv)
      NO_VENV=1
      shift
      ;;
    --comfyui-url)
      COMFYUI_URL_ARG="${2:?Missing value for --comfyui-url}"
      shift 2
      ;;
    --comfyui-dir)
      COMFYUI_DIR_ARG="${2:?Missing value for --comfyui-dir}"
      shift 2
      ;;
    --hunyuan-root)
      HUNYUAN_ROOT_ARG="${2:?Missing value for --hunyuan-root}"
      shift 2
      ;;
    --hunyuan-ckpt)
      HUNYUAN_CKPT_ARG="${2:?Missing value for --hunyuan-ckpt}"
      shift 2
      ;;
    --workflow)
      WORKFLOW_ARG="${2:?Missing value for --workflow}"
      shift 2
      ;;
    --workflow-url)
      WORKFLOW_URL_ARG="${2:?Missing value for --workflow-url}"
      shift 2
      ;;
    --comfyui-ckpt-url)
      COMFYUI_CKPT_URL_ARG="${2:?Missing value for --comfyui-ckpt-url}"
      shift 2
      ;;
    --comfyui-ckpt-path)
      COMFYUI_CKPT_PATH_ARG="${2:?Missing value for --comfyui-ckpt-path}"
      shift 2
      ;;
    --comfyui-ckpt-name)
      COMFYUI_CKPT_NAME_ARG="${2:?Missing value for --comfyui-ckpt-name}"
      shift 2
      ;;
    --setup-real-gen)
      SETUP_REAL_GEN=1
      shift
      ;;
    --runpod-full)
      RUNPOD_FULL=1
      SETUP_REAL_GEN=1
      INSTALL_SYSTEM=1
      START_COMFYUI=1
      shift
      ;;
    --install-system)
      INSTALL_SYSTEM=1
      shift
      ;;
    --start-comfyui)
      START_COMFYUI=1
      shift
      ;;
    --hunyuan-repo)
      HUNYUAN_REPO_ARG="${2:?Missing value for --hunyuan-repo}"
      shift 2
      ;;
    --hunyuan-model-repo)
      HUNYUAN_MODEL_REPO_ARG="${2:?Missing value for --hunyuan-model-repo}"
      shift 2
      ;;
    --update-code)
      UPDATE_CODE=1
      shift
      ;;
    --force-model-download)
      FORCE_MODEL_DOWNLOAD=1
      shift
      ;;
    --no-model)
      NO_MODEL=1
      shift
      ;;
    --check-only)
      CHECK_ONLY=1
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

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

install_system_packages() {
  if [[ "$(id -u)" -ne 0 || ! -x "$(command -v apt-get 2>/dev/null || true)" ]]; then
    echo "System package install skipped: root + apt-get are required."
    echo "Install manually if needed: git git-lfs curl wget ffmpeg python3 python3-venv python3-pip build-essential"
    return 0
  fi

  echo "Installing RunPod/Ubuntu system packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    ca-certificates \
    curl \
    wget \
    git \
    git-lfs \
    ffmpeg \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    build-essential \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1
  git lfs install --skip-repo || true
}

if [[ "$INSTALL_SYSTEM" -eq 1 ]]; then
  install_system_packages
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python is not installed or not available in PATH."
  exit 1
fi
SYSTEM_PYTHON_BIN="$PYTHON_BIN"

ensure_dir() {
  mkdir -p "$1"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local file=".env"

  if [[ ! -f "$file" ]]; then
    touch "$file"
  fi

  "$PYTHON_BIN" - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import re
import shlex
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]


def format_env_value(raw: str) -> str:
    if raw == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,~-]+", raw):
        return raw
    return shlex.quote(raw)


line = f"{key}={format_env_value(value)}"

lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
written = False
out = []
for item in lines:
    if item.strip().startswith(f"{key}="):
        out.append(line)
        written = True
    else:
        out.append(item)
if not written:
    out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

set_env_value "APP_PORT" "$PORT"

if grep -q '^COMFYUI_URL=http://host.docker.internal:8188' .env 2>/dev/null; then
  set_env_value "COMFYUI_URL" "http://127.0.0.1:8188"
fi

if [[ -n "$COMFYUI_URL_ARG" ]]; then
  set_env_value "COMFYUI_URL" "$COMFYUI_URL_ARG"
fi

if [[ -n "$COMFYUI_DIR_ARG" ]]; then
  set_env_value "COMFYUI_DIR" "$COMFYUI_DIR_ARG"
fi

if [[ -n "$COMFYUI_CKPT_URL_ARG" ]]; then
  set_env_value "COMFYUI_CKPT_URL" "$COMFYUI_CKPT_URL_ARG"
fi

if [[ -n "$COMFYUI_CKPT_PATH_ARG" ]]; then
  set_env_value "COMFYUI_CKPT_PATH" "$COMFYUI_CKPT_PATH_ARG"
fi

if [[ -n "$COMFYUI_CKPT_NAME_ARG" ]]; then
  set_env_value "COMFYUI_CKPT_NAME" "$COMFYUI_CKPT_NAME_ARG"
fi

if [[ -n "$HUNYUAN_ROOT_ARG" ]]; then
  set_env_value "HUNYUAN_ROOT" "$HUNYUAN_ROOT_ARG"
fi

if [[ -n "$HUNYUAN_CKPT_ARG" ]]; then
  set_env_value "HUNYUAN_CKPT" "$HUNYUAN_CKPT_ARG"
fi

set_env_value "HUNYUAN_TORCH_INDEX_URL" "$DEFAULT_HUNYUAN_TORCH_INDEX_URL"
set_env_value "HUNYUAN_TORCH_PACKAGES" "$DEFAULT_HUNYUAN_TORCH_PACKAGES"

set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ -z "${HF_TOKEN:-}" && -n "$HF_TOKEN_MANUAL" ]]; then
  export HF_TOKEN="$HF_TOKEN_MANUAL"
fi

if [[ -z "${COMFYUI_PYTHON_BIN:-}" ]]; then
  if [[ -x "/usr/bin/python3" ]]; then
    export COMFYUI_PYTHON_BIN="/usr/bin/python3"
  else
    export COMFYUI_PYTHON_BIN="$SYSTEM_PYTHON_BIN"
  fi
fi

if [[ "$RUNPOD_FULL" -eq 1 ]]; then
  if [[ -z "$HUNYUAN_ROOT_ARG" && ( -z "${HUNYUAN_ROOT:-}" || "${HUNYUAN_ROOT:-}" == "/workspace/HunyuanVideo-1.5" ) ]]; then
    export HUNYUAN_ROOT="$DEFAULT_HUNYUAN_ROOT"
    set_env_value "HUNYUAN_ROOT" "$HUNYUAN_ROOT"
  fi
  if [[ -z "${COMFYUI_CKPT_URL:-}" && -z "${COMFYUI_CKPT_PATH:-}" ]]; then
    export COMFYUI_CKPT_URL="$DEFAULT_COMFYUI_CKPT_URL"
    set_env_value "COMFYUI_CKPT_URL" "$COMFYUI_CKPT_URL"
  fi
  if [[ -z "${COMFYUI_CKPT_NAME:-}" ]]; then
    export COMFYUI_CKPT_NAME="$DEFAULT_COMFYUI_CKPT_NAME"
    set_env_value "COMFYUI_CKPT_NAME" "$COMFYUI_CKPT_NAME"
  fi
fi

if [[ "$SETUP_REAL_GEN" -eq 1 ]]; then
  setup_args=(
    --comfyui-dir "${COMFYUI_DIR:-/workspace/ComfyUI}"
    --hunyuan-root "${HUNYUAN_ROOT:-$DEFAULT_HUNYUAN_ROOT}"
    --hunyuan-ckpt "${HUNYUAN_CKPT:-/models/hunyuan/ckpts}"
  )
  if [[ -n "$WORKFLOW_ARG" ]]; then
    setup_args+=(--workflow "$WORKFLOW_ARG")
  fi
  if [[ -n "$WORKFLOW_URL_ARG" ]]; then
    setup_args+=(--workflow-url "$WORKFLOW_URL_ARG")
  fi
  if [[ -n "${COMFYUI_CKPT_URL:-}" ]]; then
    setup_args+=(--comfyui-ckpt-url "$COMFYUI_CKPT_URL")
  fi
  if [[ -n "${COMFYUI_CKPT_PATH:-}" ]]; then
    setup_args+=(--comfyui-ckpt-path "$COMFYUI_CKPT_PATH")
  fi
  if [[ -n "${COMFYUI_CKPT_NAME:-}" ]]; then
    setup_args+=(--comfyui-ckpt-name "$COMFYUI_CKPT_NAME")
  fi
  if [[ -n "$HUNYUAN_REPO_ARG" ]]; then
    setup_args+=(--hunyuan-repo "$HUNYUAN_REPO_ARG")
  fi
  if [[ -n "$HUNYUAN_MODEL_REPO_ARG" ]]; then
    setup_args+=(--hunyuan-model-repo "$HUNYUAN_MODEL_REPO_ARG")
  fi
  if [[ "$UPDATE_CODE" -eq 1 ]]; then
    setup_args+=(--update-code)
  fi
  if [[ "$FORCE_MODEL_DOWNLOAD" -eq 1 ]]; then
    setup_args+=(--force-model-download)
  fi
  if [[ "$NO_MODEL" -eq 1 ]]; then
    setup_args+=(--no-model)
  fi
  bash scripts/linux/setup_real_generation.sh "${setup_args[@]}"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

is_missing_path() {
  local value="${1:-}"
  [[ -z "$value" || "$value" == *'${'* || ! -e "$value" ]]
}

first_existing_dir() {
  for candidate in "$@"; do
    if [[ -d "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

detect_hunyuan_root() {
  for candidate in \
    "${HUNYUAN_ROOT:-}" \
    "/workspace/HunyuanVideo-I2V" \
    "/workspace/HunyuanVideo" \
    "/workspace/HunyuanVideo-1.5" \
    "/workspace/HunyuanVideo-1.5/HunyuanVideo-I2V" \
    "/workspace/aiVideoWorkFlow/external/HunyuanVideo-I2V" \
    "/workspace/aiVideoWorkFlow/external/HunyuanVideo-1.5"
  do
    if [[ -d "$candidate" && -f "$candidate/sample_image2video.py" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

detect_hunyuan_ckpt() {
  for candidate in \
    "${HUNYUAN_CKPT:-}" \
    "/models/hunyuan/ckpts" \
    "/models/hunyuan" \
    "/workspace/models/hunyuan/ckpts" \
    "/workspace/models/hunyuan" \
    "/workspace/HunyuanVideo-I2V/ckpts" \
    "/workspace/HunyuanVideo-1.5/ckpts" \
    "/workspace/aiVideoWorkFlow/models/hunyuan/ckpts"
  do
    if [[ -d "$candidate" ]] && find "$candidate" -mindepth 1 -maxdepth 2 \( -type f -o -type l \) | grep -q .; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_dir "models"
ensure_dir "models/hunyuan/ckpts"
ensure_dir "external"
ensure_dir "external/HunyuanVideo-I2V"
ensure_dir "data/jobs"
ensure_dir "data/prompts"
ensure_dir "assets/references"
ensure_dir "outputs/jobs"
ensure_dir "outputs/images"
ensure_dir "outputs/videos/raw"
ensure_dir "logs"
ensure_dir "temp"

if is_missing_path "${HUNYUAN_ROOT:-}"; then
  if detected_root="$(detect_hunyuan_root)"; then
    set_env_value "HUNYUAN_ROOT" "$detected_root"
    export HUNYUAN_ROOT="$detected_root"
    echo "Detected HUNYUAN_ROOT=$HUNYUAN_ROOT"
  fi
fi

if is_missing_path "${HUNYUAN_CKPT:-}"; then
  if detected_ckpt="$(detect_hunyuan_ckpt)"; then
    set_env_value "HUNYUAN_CKPT" "$detected_ckpt"
    export HUNYUAN_CKPT="$detected_ckpt"
    echo "Detected HUNYUAN_CKPT=$HUNYUAN_CKPT"
  fi
fi

WORKFLOW_TARGET="input/config/comfyui_workflow_api.json"
if [[ -n "$WORKFLOW_ARG" ]]; then
  if [[ ! -f "$WORKFLOW_ARG" ]]; then
    echo "ComfyUI workflow file not found: $WORKFLOW_ARG"
    exit 1
  fi
  cp "$WORKFLOW_ARG" "$WORKFLOW_TARGET"
  echo "Copied ComfyUI workflow to $WORKFLOW_TARGET"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is not installed."
  if [[ "$(id -u)" -eq 0 ]] && command -v apt-get >/dev/null 2>&1; then
    echo "Installing ffmpeg with apt-get..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ffmpeg
  else
    echo "Please install ffmpeg before generating test videos."
    echo "Debian/Ubuntu: apt-get update && apt-get install -y ffmpeg"
    exit 1
  fi
fi

if [[ "$NO_VENV" -eq 0 ]]; then
  if [[ ! -d ".venv" ]]; then
    echo "Creating Python virtual environment: .venv"
    if ! "$PYTHON_BIN" -m venv .venv; then
      echo "Could not create .venv; continuing with system Python."
      NO_VENV=1
    fi
  fi

  if [[ "$NO_VENV" -eq 0 ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    PYTHON_BIN="python"
  fi
fi

if [[ "$NO_INSTALL" -eq 0 ]]; then
  echo "Installing Python dependencies..."
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -r requirements.txt
fi

start_comfyui_background() {
  local comfy_dir="${COMFYUI_DIR:-/workspace/ComfyUI}"
  local comfy_url="${COMFYUI_URL:-http://127.0.0.1:8188}"
  local comfy_port="8188"
  local log_path="$PROJECT_DIR/logs/comfyui.log"
  local comfy_python="${COMFYUI_PYTHON_BIN:-/usr/bin/python3}"
  local extra_packages="${COMFYUI_EXTRA_PIP_PACKAGES:-SQLAlchemy alembic blake3 tqdm GitPython toml}"
  local torch_packages="${COMFYUI_TORCH_PACKAGES:-torch torchvision torchaudio}"
  local torch_index_url="${COMFYUI_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
  local numpy_package="${COMFYUI_NUMPY_PACKAGE:-numpy>=1.26,<3}"

  if [[ ! -x "$comfy_python" ]]; then
    comfy_python="$(command -v python3 || true)"
  fi
  if [[ -z "$comfy_python" ]]; then
    echo "Cannot find Python for ComfyUI. Set COMFYUI_PYTHON_BIN."
    return 1
  fi

  if [[ "$comfy_url" =~ :([0-9]+)$ ]]; then
    comfy_port="${BASH_REMATCH[1]}"
  fi

  if [[ ! -d "$comfy_dir" ]]; then
    echo "ComfyUI directory does not exist, cannot start: $comfy_dir"
    return 1
  fi

  if command -v curl >/dev/null 2>&1 && curl --max-time 5 -fsS "$comfy_url/system_stats" >/dev/null 2>&1; then
    echo "ComfyUI already running: $comfy_url"
    return 0
  fi

  mkdir -p logs temp
  if [[ "${AUTO_INSTALL_COMFYUI_DEPS:-1}" != "0" ]]; then
    if ! "$comfy_python" - <<'PY' >/dev/null 2>&1
import sqlalchemy  # noqa: F401
import numpy.dtypes  # noqa: F401
import blake3  # noqa: F401
import tqdm  # noqa: F401
import git  # noqa: F401
import toml  # noqa: F401
import torch
torch.cuda.current_device()
PY
    then
      echo "Installing missing ComfyUI runtime dependencies..."
      if [[ -f "$comfy_dir/requirements.txt" ]]; then
        "$comfy_python" -m pip install -r "$comfy_dir/requirements.txt"
      fi
      if [[ -n "$numpy_package" ]]; then
        "$comfy_python" -m pip install --upgrade --force-reinstall "$numpy_package"
      fi
      if [[ -n "$torch_packages" && -n "$torch_index_url" ]]; then
        "$comfy_python" -m pip install --force-reinstall $torch_packages --index-url "$torch_index_url"
      fi
      if [[ -n "$extra_packages" ]]; then
        "$comfy_python" -m pip install $extra_packages
      fi
    fi
  fi

  echo "Starting ComfyUI in background: $comfy_url"
  (
    cd "$comfy_dir"
    nohup "$comfy_python" main.py --listen 0.0.0.0 --port "$comfy_port" > "$log_path" 2>&1 &
    echo $! > "$PROJECT_DIR/temp/comfyui.pid"
  )
  echo "ComfyUI log: $log_path"

  if command -v curl >/dev/null 2>&1; then
    for attempt in $(seq 1 60); do
      if curl --max-time 5 -fsS "$comfy_url/system_stats" >/dev/null 2>&1; then
        echo "ComfyUI is ready: $comfy_url"
        return 0
      fi
      if (( attempt % 5 == 0 )); then
        echo "Waiting for ComfyUI... $((attempt * 2))s elapsed"
      fi
      sleep 2
    done
  fi

  echo "ComfyUI startup was requested, but readiness check did not pass yet."
  echo "Log: $log_path"
  if [[ -f "$log_path" ]]; then
    echo ""
    echo "Last 80 ComfyUI log lines:"
    tail -n 80 "$log_path" || true
  fi
  return 0
}

if [[ "$START_COMFYUI" -eq 1 ]]; then
  start_comfyui_background
fi

echo ""
echo "Checking real generation dependencies..."
if "$PYTHON_BIN" scripts/check_real_generation.py; then
  echo "Real generation check: OK"
else
  echo ""
  echo "Real generation is not ready yet. The visual page can still start, but true AI video generation will fail until the items above are fixed."
  echo "Quick fixes:"
  echo "  - Start ComfyUI on port 8188, or pass --comfyui-url URL"
  echo "  - Export ComfyUI API workflow, or pass --workflow /path/to/workflow.json"
  echo "  - Install/mount HunyuanVideo, or pass --hunyuan-root PATH"
  echo "  - Mount model weights, or pass --hunyuan-ckpt PATH"
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  exit 0
fi

echo ""
echo "Visual page is starting:"
echo "  http://localhost:${PORT}"
echo ""
echo "On RunPod, open the HTTP service for port ${PORT} from the RunPod dashboard."
echo "Press Ctrl+C to stop."
echo ""

exec "$PYTHON_BIN" -m uvicorn web.app:app --host "$HOST" --port "$PORT"
