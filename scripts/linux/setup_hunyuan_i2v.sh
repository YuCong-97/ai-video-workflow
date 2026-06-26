#!/usr/bin/env bash
set -Eeuo pipefail

HUNYUAN_ROOT="${HUNYUAN_ROOT:-/workspace/HunyuanVideo-I2V}"
HUNYUAN_REPO_URL="${HUNYUAN_REPO_URL:-https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V.git}"
HUNYUAN_CKPT="${HUNYUAN_CKPT:-/models/hunyuan/ckpts}"
HUNYUAN_MODEL_REPO="${HUNYUAN_MODEL_REPO:-tencent/HunyuanVideo-I2V}"

# Optional Hugging Face token for private/gated model downloads.
# Fill it manually if needed, for example:
# HF_TOKEN_MANUAL="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# An existing environment variable HF_TOKEN still has priority.
HF_TOKEN_MANUAL=""
HF_TOKEN="${HF_TOKEN:-$HF_TOKEN_MANUAL}"

NO_MODEL=0
NO_INSTALL=0

usage() {
  cat <<'EOF'
Usage:
  scripts/linux/setup_hunyuan_i2v.sh [options]

Options:
  --root PATH             HunyuanVideo-I2V install directory. Default: /workspace/HunyuanVideo-I2V
  --ckpt PATH             Model checkpoint directory. Default: /models/hunyuan/ckpts
  --repo URL              Git repository URL.
  --model-repo HF_ID      Hugging Face model repo. Default: tencent/HunyuanVideo-I2V
  --no-model              Clone/install code only; skip model download.
  --no-install            Clone/download only; skip pip install.

Environment:
  HUNYUAN_ROOT, HUNYUAN_CKPT, HUNYUAN_REPO_URL, HUNYUAN_MODEL_REPO, HF_TOKEN

Notes:
  Large model downloads can take a long time and consume substantial disk space.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      HUNYUAN_ROOT="${2:?Missing value for --root}"
      shift 2
      ;;
    --ckpt)
      HUNYUAN_CKPT="${2:?Missing value for --ckpt}"
      shift 2
      ;;
    --repo)
      HUNYUAN_REPO_URL="${2:?Missing value for --repo}"
      shift 2
      ;;
    --model-repo)
      HUNYUAN_MODEL_REPO="${2:?Missing value for --model-repo}"
      shift 2
      ;;
    --no-model)
      NO_MODEL=1
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

if [[ ! -d "$HUNYUAN_ROOT/.git" ]]; then
  mkdir -p "$(dirname "$HUNYUAN_ROOT")"
  git clone "$HUNYUAN_REPO_URL" "$HUNYUAN_ROOT"
else
  git -C "$HUNYUAN_ROOT" pull --ff-only || true
fi

if [[ "$NO_INSTALL" -eq 0 ]]; then
  python3 -m pip install --upgrade pip
  if [[ -f "$HUNYUAN_ROOT/requirements.txt" ]]; then
    python3 -m pip install -r "$HUNYUAN_ROOT/requirements.txt"
  fi
  python3 -m pip install "huggingface_hub[cli]" hf_transfer
fi

if [[ "$NO_MODEL" -eq 0 ]]; then
  mkdir -p "$HUNYUAN_CKPT"
  export HF_HUB_ENABLE_HF_TRANSFER=1
  hf_args=(download "$HUNYUAN_MODEL_REPO" --local-dir "$HUNYUAN_CKPT")
  if [[ -n "$HF_TOKEN" ]]; then
    hf_args+=(--token "$HF_TOKEN")
  fi
  if command -v hf >/dev/null 2>&1; then
    hf "${hf_args[@]}"
  elif command -v huggingface-cli >/dev/null 2>&1; then
    huggingface-cli "${hf_args[@]}"
  else
    python3 - "$HUNYUAN_MODEL_REPO" "$HUNYUAN_CKPT" "$HF_TOKEN" <<'PY'
from huggingface_hub import snapshot_download
import sys

repo_id = sys.argv[1]
local_dir = sys.argv[2]
token = sys.argv[3] or None
snapshot_download(repo_id=repo_id, local_dir=local_dir, token=token)
PY
  fi
fi

echo ""
echo "HunyuanVideo-I2V prepared:"
echo "  HUNYUAN_ROOT=$HUNYUAN_ROOT"
echo "  HUNYUAN_CKPT=$HUNYUAN_CKPT"
echo ""
echo "Add to .env:"
echo "  HUNYUAN_ROOT=$HUNYUAN_ROOT"
echo "  HUNYUAN_CKPT=$HUNYUAN_CKPT"
