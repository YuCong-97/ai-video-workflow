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
UPDATE_CODE=0
FORCE_MODEL_DOWNLOAD=0

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
  --update-code           Pull latest code when repository already exists.
  --force-model-download  Run Hugging Face download even if model files exist.

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

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1"
    exit 1
  fi
}

need_cmd git
need_cmd python3

has_model_files() {
  local path="$1"
  [[ -d "$path" ]] || return 1
  find "$path" -type f \
    \( -name '*.safetensors' -o -name '*.pt' -o -name '*.pth' -o -name '*.bin' -o -name '*.gguf' -o -name '*.model' \) \
    -size +10M \
    ! -path '*/.cache/*' \
    | grep -q .
}

install_hunyuan_requirements() {
  local requirements_path="$HUNYUAN_ROOT/requirements.txt"
  local compat_path="/tmp/hunyuan_requirements_compat.txt"

  if [[ ! -f "$requirements_path" ]]; then
    return 0
  fi

  python3 - "$requirements_path" "$compat_path" <<'PY'
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])

skipped: list[str] = []
out: list[str] = []
for line in source.read_text(encoding="utf-8").splitlines():
    normalized = line.strip().lower()
    package_name = re.split(r"[<>=!~;\[\s]", normalized, maxsplit=1)[0]
    if package_name == "tokenizers" and "==0.15.0" in normalized:
        skipped.append(line)
        continue
    out.append(line)

target.write_text("\n".join(out) + "\n", encoding="utf-8")

if skipped:
    print("Using compatible Hunyuan requirements: skipped old tokenizers pin(s):")
    for item in skipped:
        print(f"  {item}")
    print("transformers will install a matching tokenizers version automatically.")
PY

  python3 -m pip install -r "$compat_path"
}

if [[ ! -d "$HUNYUAN_ROOT/.git" ]]; then
  mkdir -p "$(dirname "$HUNYUAN_ROOT")"
  git clone "$HUNYUAN_REPO_URL" "$HUNYUAN_ROOT"
else
  if [[ "$UPDATE_CODE" -eq 1 ]]; then
    git -C "$HUNYUAN_ROOT" pull --ff-only || true
  else
    echo "HunyuanVideo already exists, skipping git pull: $HUNYUAN_ROOT"
  fi
fi

if [[ "$NO_INSTALL" -eq 0 ]]; then
  python3 -m pip install --upgrade pip
  install_hunyuan_requirements
  python3 -m pip install "huggingface_hub[cli]" hf_transfer
fi

if [[ "$NO_MODEL" -eq 0 ]]; then
  mkdir -p "$HUNYUAN_CKPT"
  if [[ "$FORCE_MODEL_DOWNLOAD" -eq 0 ]] && has_model_files "$HUNYUAN_CKPT"; then
    echo "Hunyuan model files already exist, skipping model download: $HUNYUAN_CKPT"
    echo "Use --force-model-download to force Hugging Face download/resume."
  else
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
fi

echo ""
echo "HunyuanVideo-I2V prepared:"
echo "  HUNYUAN_ROOT=$HUNYUAN_ROOT"
echo "  HUNYUAN_CKPT=$HUNYUAN_CKPT"
echo ""
echo "Add to .env:"
echo "  HUNYUAN_ROOT=$HUNYUAN_ROOT"
echo "  HUNYUAN_CKPT=$HUNYUAN_CKPT"
