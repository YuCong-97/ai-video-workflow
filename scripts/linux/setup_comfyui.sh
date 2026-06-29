#!/usr/bin/env bash
set -Eeuo pipefail

COMFYUI_DIR="${COMFYUI_DIR:-/workspace/ComfyUI}"
COMFYUI_REPO_URL="${COMFYUI_REPO_URL:-https://github.com/comfyanonymous/ComfyUI.git}"
COMFYUI_MANAGER_REPO_URL="${COMFYUI_MANAGER_REPO_URL:-https://github.com/ltdrdata/ComfyUI-Manager.git}"
COMFYUI_EXTRA_PIP_PACKAGES="${COMFYUI_EXTRA_PIP_PACKAGES:-SQLAlchemy alembic blake3 tqdm GitPython toml}"
COMFYUI_PYTHON_BIN="${COMFYUI_PYTHON_BIN:-python3}"
COMFYUI_TORCH_PACKAGES="${COMFYUI_TORCH_PACKAGES:-torch torchvision torchaudio}"
COMFYUI_TORCH_INDEX_URL="${COMFYUI_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
COMFYUI_NUMPY_PACKAGE="${COMFYUI_NUMPY_PACKAGE:-numpy>=1.26,<3}"
WORKFLOW_URL="${WORKFLOW_URL:-}"
WORKFLOW_PATH="${WORKFLOW_PATH:-}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
TARGET_WORKFLOW="${TARGET_WORKFLOW:-$PROJECT_DIR/input/config/comfyui_workflow_api.json}"
NO_MANAGER=0
NO_INSTALL=0
UPDATE_CODE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/linux/setup_comfyui.sh [options]

Options:
  --dir PATH              ComfyUI install directory. Default: /workspace/ComfyUI
  --workflow-url URL      Download API workflow JSON from URL.
  --workflow PATH         Copy local API workflow JSON.
  --target PATH           Target workflow path. Default: input/config/comfyui_workflow_api.json
  --no-manager            Do not install ComfyUI-Manager.
  --no-install            Clone/copy only; skip pip install.
  --update-code           Pull latest code when repositories already exist.

Environment:
  COMFYUI_DIR, COMFYUI_REPO_URL, COMFYUI_MANAGER_REPO_URL, COMFYUI_EXTRA_PIP_PACKAGES,
  COMFYUI_PYTHON_BIN, COMFYUI_TORCH_PACKAGES, COMFYUI_TORCH_INDEX_URL, COMFYUI_NUMPY_PACKAGE,
  WORKFLOW_URL, WORKFLOW_PATH
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      COMFYUI_DIR="${2:?Missing value for --dir}"
      shift 2
      ;;
    --workflow-url)
      WORKFLOW_URL="${2:?Missing value for --workflow-url}"
      shift 2
      ;;
    --workflow)
      WORKFLOW_PATH="${2:?Missing value for --workflow}"
      shift 2
      ;;
    --target)
      TARGET_WORKFLOW="${2:?Missing value for --target}"
      shift 2
      ;;
    --no-manager)
      NO_MANAGER=1
      shift
      ;;
    --no-install)
      NO_INSTALL=1
      shift
      ;;
    --update-code)
      UPDATE_CODE=1
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

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1"
    exit 1
  fi
}

need_cmd git
need_cmd "$COMFYUI_PYTHON_BIN"

comfyui_torch_ok() {
  "$COMFYUI_PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import torch
torch.cuda.current_device()
PY
}

comfyui_numpy_ok() {
  "$COMFYUI_PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import numpy.dtypes  # noqa: F401
PY
}

comfyui_extra_deps_ok() {
  "$COMFYUI_PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sqlalchemy  # noqa: F401
import blake3  # noqa: F401
import tqdm  # noqa: F401
import git  # noqa: F401
import toml  # noqa: F401
PY
}

mkdir -p "$(dirname "$TARGET_WORKFLOW")"

if [[ ! -d "$COMFYUI_DIR/.git" ]]; then
  mkdir -p "$(dirname "$COMFYUI_DIR")"
  git clone "$COMFYUI_REPO_URL" "$COMFYUI_DIR"
else
  if [[ "$UPDATE_CODE" -eq 1 ]]; then
    git -C "$COMFYUI_DIR" pull --ff-only || true
  else
    echo "ComfyUI already exists, skipping git pull: $COMFYUI_DIR"
  fi
fi

if [[ "$NO_MANAGER" -eq 0 ]]; then
  manager_dir="$COMFYUI_DIR/custom_nodes/ComfyUI-Manager"
  if [[ ! -d "$manager_dir/.git" ]]; then
    git clone "$COMFYUI_MANAGER_REPO_URL" "$manager_dir"
  else
    if [[ "$UPDATE_CODE" -eq 1 ]]; then
      git -C "$manager_dir" pull --ff-only || true
    else
      echo "ComfyUI-Manager already exists, skipping git pull: $manager_dir"
    fi
  fi
fi

if [[ "$NO_INSTALL" -eq 0 ]]; then
  "$COMFYUI_PYTHON_BIN" -m pip install --upgrade pip
  "$COMFYUI_PYTHON_BIN" -m pip install -r "$COMFYUI_DIR/requirements.txt"
  if [[ -n "$COMFYUI_NUMPY_PACKAGE" ]]; then
    if comfyui_numpy_ok; then
      echo "ComfyUI numpy.dtypes check passed, skipping numpy reinstall."
    else
      "$COMFYUI_PYTHON_BIN" -m pip install --upgrade --force-reinstall "$COMFYUI_NUMPY_PACKAGE"
    fi
  fi
  if [[ -n "$COMFYUI_TORCH_PACKAGES" && -n "$COMFYUI_TORCH_INDEX_URL" ]]; then
    if comfyui_torch_ok; then
      echo "ComfyUI torch CUDA check passed, skipping torch reinstall."
    else
      # Match RunPod images with NVIDIA driver 12.4; newer CUDA wheels can fail at torch.cuda init.
      "$COMFYUI_PYTHON_BIN" -m pip install --force-reinstall $COMFYUI_TORCH_PACKAGES --index-url "$COMFYUI_TORCH_INDEX_URL"
    fi
  fi
  if [[ -n "$COMFYUI_EXTRA_PIP_PACKAGES" ]]; then
    if comfyui_extra_deps_ok; then
      echo "ComfyUI extra dependency check passed, skipping extra package install."
    else
      "$COMFYUI_PYTHON_BIN" -m pip install $COMFYUI_EXTRA_PIP_PACKAGES
    fi
  fi
fi

if [[ -n "$WORKFLOW_URL" ]]; then
  if command -v curl >/dev/null 2>&1; then
    curl -L "$WORKFLOW_URL" -o "$TARGET_WORKFLOW"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$TARGET_WORKFLOW" "$WORKFLOW_URL"
  else
    echo "Need curl or wget to download workflow URL."
    exit 1
  fi
elif [[ -n "$WORKFLOW_PATH" ]]; then
  if [[ ! -f "$WORKFLOW_PATH" ]]; then
    echo "Workflow file not found: $WORKFLOW_PATH"
    exit 1
  fi
  cp "$WORKFLOW_PATH" "$TARGET_WORKFLOW"
elif [[ ! -f "$TARGET_WORKFLOW" ]]; then
  cat > "$TARGET_WORKFLOW" <<'EOF'
{
  "note": "Replace this file with a real ComfyUI API workflow exported from ComfyUI.",
  "required_placeholders": [
    "__PROMPT__",
    "__NEGATIVE_PROMPT__",
    "__SEED__",
    "__WIDTH__",
    "__HEIGHT__",
    "__OUTPUT_PREFIX__"
  ]
}
EOF
  echo "Created placeholder workflow at $TARGET_WORKFLOW"
fi

echo ""
echo "ComfyUI prepared:"
echo "  COMFYUI_DIR=$COMFYUI_DIR"
echo "  Workflow=$TARGET_WORKFLOW"
echo ""
echo "Start ComfyUI:"
echo "  cd $COMFYUI_DIR && $COMFYUI_PYTHON_BIN main.py --listen 0.0.0.0 --port 8188"
