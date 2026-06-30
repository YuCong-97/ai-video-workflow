#!/usr/bin/env bash
set -Eeuo pipefail

HUNYUAN_ROOT="${HUNYUAN_ROOT:-/workspace/HunyuanVideo-I2V}"
HUNYUAN_REPO_URL="${HUNYUAN_REPO_URL:-https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V.git}"
HUNYUAN_CKPT="${HUNYUAN_CKPT:-/models/hunyuan/ckpts}"
HUNYUAN_MODEL_REPO="${HUNYUAN_MODEL_REPO:-tencent/HunyuanVideo-I2V}"
HUNYUAN_TEXT_ENCODER_REPO="${HUNYUAN_TEXT_ENCODER_REPO:-xtuner/llava-llama-3-8b-v1_1-transformers}"
HUNYUAN_CLIP_REPO="${HUNYUAN_CLIP_REPO:-openai/clip-vit-large-patch14}"
HUNYUAN_TORCH_INDEX_URL="${HUNYUAN_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
HUNYUAN_TORCH_PACKAGES="${HUNYUAN_TORCH_PACKAGES:-torch torchvision torchaudio}"

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
  --text-encoder-repo ID  MLLM text encoder repo. Default: xtuner/llava-llama-3-8b-v1_1-transformers
  --clip-repo ID          CLIP text encoder repo. Default: openai/clip-vit-large-patch14
  --no-model              Clone/install code only; skip model download.
  --no-install            Clone/download only; skip pip install.
  --update-code           Pull latest code when repository already exists.
  --force-model-download  Run Hugging Face download even if model files exist.

Environment:
  HUNYUAN_ROOT, HUNYUAN_CKPT, HUNYUAN_REPO_URL, HUNYUAN_MODEL_REPO,
  HUNYUAN_TEXT_ENCODER_REPO, HUNYUAN_CLIP_REPO, HF_TOKEN,
  HUNYUAN_TORCH_INDEX_URL, HUNYUAN_TORCH_PACKAGES

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
    --text-encoder-repo)
      HUNYUAN_TEXT_ENCODER_REPO="${2:?Missing value for --text-encoder-repo}"
      shift 2
      ;;
    --clip-repo)
      HUNYUAN_CLIP_REPO="${2:?Missing value for --clip-repo}"
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

has_hunyuan_i2v_weight() {
  local path="$1"
  [[ -f "$path/hunyuan-video-i2v-720p/transformers/mp_rank_00_model_states.pt" ]]
}

has_hunyuan_i2v_vae() {
  local path="$1"
  [[ -f "$path/hunyuan-video-i2v-720p/vae/config.json" ]]
}

has_hunyuan_text_encoder() {
  local path="$1"
  [[ -f "$path/text_encoder_i2v/config.json" ]]
}

has_hunyuan_clip_encoder() {
  local path="$1"
  [[ -f "$path/text_encoder_2/config.json" ]]
}

hf_download_repo() {
  local repo="$1"
  local target="$2"
  export HF_HUB_ENABLE_HF_TRANSFER=1
  hf_args=(download "$repo" --local-dir "$target")
  if [[ -n "$HF_TOKEN" ]]; then
    hf_args+=(--token "$HF_TOKEN")
  fi
  if command -v hf >/dev/null 2>&1; then
    hf "${hf_args[@]}"
  elif command -v huggingface-cli >/dev/null 2>&1; then
    huggingface-cli "${hf_args[@]}"
  else
    python3 - "$repo" "$target" "$HF_TOKEN" <<'PY'
from huggingface_hub import snapshot_download
import sys

repo_id = sys.argv[1]
local_dir = sys.argv[2]
token = sys.argv[3] or None
snapshot_download(repo_id=repo_id, local_dir=local_dir, token=token)
PY
  fi
}

ensure_local_ckpts_link() {
  local link_path="$HUNYUAN_ROOT/ckpts"
  local backup_path=""

  if ! has_hunyuan_i2v_weight "$HUNYUAN_CKPT" || ! has_hunyuan_i2v_vae "$HUNYUAN_CKPT" || ! has_hunyuan_text_encoder "$HUNYUAN_CKPT" || ! has_hunyuan_clip_encoder "$HUNYUAN_CKPT"; then
    echo "Hunyuan checkpoint directory is incomplete:"
    echo "  expected weight: $HUNYUAN_CKPT/hunyuan-video-i2v-720p/transformers/mp_rank_00_model_states.pt"
    echo "  expected VAE config: $HUNYUAN_CKPT/hunyuan-video-i2v-720p/vae/config.json"
    echo "  expected MLLM config: $HUNYUAN_CKPT/text_encoder_i2v/config.json"
    echo "  expected CLIP config: $HUNYUAN_CKPT/text_encoder_2/config.json"
    return 1
  fi

  if [[ -L "$link_path" ]]; then
    if [[ "$(readlink -f "$link_path")" != "$(readlink -f "$HUNYUAN_CKPT")" ]]; then
      rm -f "$link_path"
      ln -s "$HUNYUAN_CKPT" "$link_path"
    fi
    return 0
  fi

  if [[ ! -e "$link_path" ]]; then
    ln -s "$HUNYUAN_CKPT" "$link_path"
    return 0
  fi

  if has_hunyuan_i2v_weight "$link_path" && has_hunyuan_i2v_vae "$link_path" && has_hunyuan_text_encoder "$link_path" && has_hunyuan_clip_encoder "$link_path"; then
    return 0
  fi

  backup_path="$HUNYUAN_ROOT/ckpts.local_backup_$(date +%Y%m%d_%H%M%S)"
  echo "Backing up incomplete local ckpts directory: $link_path -> $backup_path"
  mv "$link_path" "$backup_path"
  ln -s "$HUNYUAN_CKPT" "$link_path"
}

torch_cuda_ok() {
  python3 - <<'PY' >/dev/null 2>&1
import torch
assert torch.cuda.is_available(), torch.version.cuda
PY
}

install_compatible_torch() {
  if [[ -z "$HUNYUAN_TORCH_PACKAGES" ]]; then
    return 0
  fi
  if torch_cuda_ok; then
    echo "Hunyuan torch CUDA check passed, skipping torch reinstall."
    return 0
  fi
  echo "Installing Hunyuan torch packages from $HUNYUAN_TORCH_INDEX_URL"
  if [[ -n "$HUNYUAN_TORCH_INDEX_URL" ]]; then
    python3 -m pip install --force-reinstall $HUNYUAN_TORCH_PACKAGES --index-url "$HUNYUAN_TORCH_INDEX_URL"
  else
    python3 -m pip install --force-reinstall $HUNYUAN_TORCH_PACKAGES
  fi
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
    if package_name in {"torch", "torchvision", "torchaudio"}:
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
  install_compatible_torch
  install_hunyuan_requirements
  python3 -m pip install "huggingface_hub[cli]" hf_transfer
fi

if [[ "$NO_MODEL" -eq 0 ]]; then
  mkdir -p "$HUNYUAN_CKPT"
  if [[ "$FORCE_MODEL_DOWNLOAD" -eq 0 ]] && has_hunyuan_i2v_weight "$HUNYUAN_CKPT" && has_hunyuan_i2v_vae "$HUNYUAN_CKPT"; then
    echo "Hunyuan I2V base files already exist, skipping base model download: $HUNYUAN_CKPT"
    echo "Use --force-model-download to force Hugging Face download/resume."
  else
    if has_model_files "$HUNYUAN_CKPT"; then
      echo "Some Hunyuan model files exist, but required I2V files are missing:"
      echo "  $HUNYUAN_CKPT/hunyuan-video-i2v-720p/transformers/mp_rank_00_model_states.pt"
      echo "  $HUNYUAN_CKPT/hunyuan-video-i2v-720p/vae/config.json"
      echo "Running Hugging Face download/resume."
    fi
    hf_download_repo "$HUNYUAN_MODEL_REPO" "$HUNYUAN_CKPT"
  fi

  if [[ "$FORCE_MODEL_DOWNLOAD" -eq 0 ]] && has_hunyuan_text_encoder "$HUNYUAN_CKPT"; then
    echo "Hunyuan MLLM text encoder already exists, skipping: $HUNYUAN_CKPT/text_encoder_i2v"
  else
    echo "Downloading Hunyuan MLLM text encoder: $HUNYUAN_TEXT_ENCODER_REPO"
    hf_download_repo "$HUNYUAN_TEXT_ENCODER_REPO" "$HUNYUAN_CKPT/text_encoder_i2v"
  fi

  if [[ "$FORCE_MODEL_DOWNLOAD" -eq 0 ]] && has_hunyuan_clip_encoder "$HUNYUAN_CKPT"; then
    echo "Hunyuan CLIP text encoder already exists, skipping: $HUNYUAN_CKPT/text_encoder_2"
  else
    echo "Downloading Hunyuan CLIP text encoder: $HUNYUAN_CLIP_REPO"
    hf_download_repo "$HUNYUAN_CLIP_REPO" "$HUNYUAN_CKPT/text_encoder_2"
  fi
fi

ensure_local_ckpts_link

echo ""
echo "HunyuanVideo-I2V prepared:"
echo "  HUNYUAN_ROOT=$HUNYUAN_ROOT"
echo "  HUNYUAN_CKPT=$HUNYUAN_CKPT"
echo ""
echo "Add to .env:"
echo "  HUNYUAN_ROOT=$HUNYUAN_ROOT"
echo "  HUNYUAN_CKPT=$HUNYUAN_CKPT"
