#!/usr/bin/env bash
set -Eeuo pipefail

COMFYUI_DIR="${COMFYUI_DIR:-/workspace/ComfyUI}"
COMFYUI_REPO_URL="${COMFYUI_REPO_URL:-https://github.com/comfyanonymous/ComfyUI.git}"
COMFYUI_MANAGER_REPO_URL="${COMFYUI_MANAGER_REPO_URL:-https://github.com/ltdrdata/ComfyUI-Manager.git}"
WORKFLOW_URL="${WORKFLOW_URL:-}"
WORKFLOW_PATH="${WORKFLOW_PATH:-}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
TARGET_WORKFLOW="${TARGET_WORKFLOW:-$PROJECT_DIR/input/config/comfyui_workflow_api.json}"
NO_MANAGER=0
NO_INSTALL=0

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

Environment:
  COMFYUI_DIR, COMFYUI_REPO_URL, COMFYUI_MANAGER_REPO_URL, WORKFLOW_URL, WORKFLOW_PATH
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
need_cmd python3

mkdir -p "$(dirname "$TARGET_WORKFLOW")"

if [[ ! -d "$COMFYUI_DIR/.git" ]]; then
  mkdir -p "$(dirname "$COMFYUI_DIR")"
  git clone "$COMFYUI_REPO_URL" "$COMFYUI_DIR"
else
  git -C "$COMFYUI_DIR" pull --ff-only || true
fi

if [[ "$NO_MANAGER" -eq 0 ]]; then
  manager_dir="$COMFYUI_DIR/custom_nodes/ComfyUI-Manager"
  if [[ ! -d "$manager_dir/.git" ]]; then
    git clone "$COMFYUI_MANAGER_REPO_URL" "$manager_dir"
  else
    git -C "$manager_dir" pull --ff-only || true
  fi
fi

if [[ "$NO_INSTALL" -eq 0 ]]; then
  python3 -m pip install --upgrade pip
  python3 -m pip install -r "$COMFYUI_DIR/requirements.txt"
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
echo "  cd $COMFYUI_DIR && python3 main.py --listen 0.0.0.0 --port 8188"

