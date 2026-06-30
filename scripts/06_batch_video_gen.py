from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.config_loader import load_project_config

DEFAULT_HUNYUAN_FORCE_PIP_PACKAGES = "diffusers==0.31.0 transformers==4.47.1 tokenizers>=0.21,<0.22"
DEFAULT_HUNYUAN_EXTRA_PIP_PACKAGES = (
    "loguru imageio imageio-ffmpeg diffusers==0.31.0 "
    "transformers==4.47.1 tokenizers>=0.21,<0.22 deepspeed tensorboard"
)
DEFAULT_HUNYUAN_FLASH_ATTN_PACKAGE = "git+https://github.com/Dao-AILab/flash-attention.git@v2.6.3"
DEFAULT_HUNYUAN_TORCH_PACKAGES = "torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0"
HUNYUAN_RUNTIME_READY: set[Path] = set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch generate videos from keyframes and prompt CSV.")
    parser.add_argument("--config", default="input/config/project.yaml")
    parser.add_argument("--prompt-csv")
    parser.add_argument("--episode", default="ep01")
    parser.add_argument("--scene")
    parser.add_argument("--shot")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def setup_logger(episode_id: str) -> logging.Logger:
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("batch_video_gen")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    path = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}_{episode_id}_batch_video_gen.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def find_prompt_csv(episode_id: str, prompt_csv: str | None) -> Path:
    if prompt_csv:
        return resolve_path(prompt_csv)
    exact = ROOT / "data" / "prompts" / f"{episode_id}_prompts.csv"
    if exact.exists():
        return exact
    candidates = sorted(
        (ROOT / "data" / "prompts").glob(f"{episode_id}*_prompts.csv"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No prompt CSV found for episode {episode_id}")
    return candidates[0]


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def row_matches(row: dict[str, str], args: argparse.Namespace) -> bool:
    if args.episode and row.get("episode_id") != args.episode:
        return False
    if args.scene and row.get("scene_id") != args.scene:
        return False
    if args.shot and row.get("shot_id") != args.shot:
        return False
    return True


class CommandValues(dict[str, Any]):
    def __format__(self, format_spec: str) -> str:
        value = str(self["value"])
        if format_spec == "q":
            return shlex.quote(value)
        return value


def format_command(template: str, values: dict[str, Any]) -> str:
    formatted_values = {key: CommandValues(value=value) for key, value in values.items()}
    return template.format_map(formatted_values)


def default_hunyuan_command_template() -> str:
    return (
        "cd {hunyuan_root:q} && python3 sample_image2video.py "
        "--model HYVideo-T/2 "
        "--model-base {hunyuan_ckpt:q} "
        "--dit-weight {dit_weight:q} "
        "--i2v-dit-weight {i2v_dit_weight:q} "
        "--prompt {prompt:q} "
        "--i2v-mode "
        "--i2v-image-path {image:q} "
        "--i2v-resolution {resolution:q} "
        "--infer-steps {infer_steps} "
        "--video-length {video_length} "
        "--flow-reverse "
        "--flow-shift {flow_shift} "
        "--seed {seed} "
        "--embedded-cfg-scale {cfg_scale} "
        "--use-cpu-offload "
        "--save-path {save_dir:q}"
    )


def run_command(command: list[str], logger: logging.Logger, cwd: Path | None = None) -> None:
    logger.info("Running setup command: %s", " ".join(shlex.quote(item) for item in command))
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.stdout:
        logger.info("setup stdout: %s", result.stdout[-4000:])
    if result.stderr:
        logger.info("setup stderr: %s", result.stderr[-4000:])
    if result.returncode != 0:
        raise RuntimeError(f"Setup command failed exit={result.returncode}: {result.stderr[-2000:]}")


def compatible_requirements_path(requirements: Path, logger: logging.Logger) -> Path:
    compat_dir = ROOT / "temp"
    compat_dir.mkdir(parents=True, exist_ok=True)
    compat_path = compat_dir / "hunyuan_requirements_compat.txt"
    skipped: list[str] = []
    output: list[str] = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        normalized = line.strip().lower()
        package_name = re.split(r"[<>=!~;\[\s]", normalized, maxsplit=1)[0]
        if package_name == "tokenizers" and "==0.15.0" in normalized:
            skipped.append(line)
            continue
        if package_name in {"torch", "torchvision", "torchaudio", "transformers"}:
            skipped.append(line)
            continue
        output.append(line)
    compat_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    if skipped:
        logger.info(
            "Using compatible Hunyuan requirements, skipped incompatible package pin(s): %s",
            "; ".join(skipped),
        )
    return compat_path


def install_compatible_torch(python_bin: str, video_gen: dict[str, Any], logger: logging.Logger, cwd: Path) -> None:
    torch_package_string = config_string(video_gen, "torch_packages", DEFAULT_HUNYUAN_TORCH_PACKAGES)
    torch_packages = shlex.split(torch_package_string)
    torch_index_url = config_string(video_gen, "torch_index_url", os.environ.get("HUNYUAN_TORCH_INDEX_URL", "https://download.pytorch.org/whl/cu124"))
    if not torch_packages:
        return

    expected_torch = pinned_package_version(torch_package_string, "torch")
    probe = subprocess.run(
        [
            python_bin,
            "-c",
            (
                "import torch\n"
                "assert torch.cuda.is_available(), torch.version.cuda\n"
                f"expected = {expected_torch!r}\n"
                "actual = torch.__version__.split('+', 1)[0]\n"
                "assert not expected or actual == expected, (actual, expected)\n"
            ),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return

    logger.info("Installing CUDA-compatible torch packages: %s index=%s", " ".join(torch_packages), torch_index_url)
    command = [python_bin, "-m", "pip", "install", "--force-reinstall", *torch_packages]
    if torch_index_url:
        command.extend(["--index-url", torch_index_url])
    run_command(command, logger, cwd=cwd)

    probe = subprocess.run(
        [python_bin, "-c", "import torch; assert torch.cuda.is_available(), torch.version.cuda; print(torch.__version__, torch.version.cuda)"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            "Torch CUDA is not available after installing compatible packages. "
            f"stdout={probe.stdout[-1000:]} stderr={probe.stderr[-1000:]}"
        )
    logger.info("Torch CUDA available: %s", probe.stdout.strip())


def has_python_module(module: str, python_bin: str, cwd: Path, logger: logging.Logger) -> bool:
    result = subprocess.run(
        [python_bin, "-c", f"import {module}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.info("Missing Hunyuan python module=%s stderr=%s", module, result.stderr.strip()[-1000:])
        return False
    return True


def missing_python_modules(modules: list[str], python_bin: str, cwd: Path, logger: logging.Logger) -> list[str]:
    return [module for module in modules if not has_python_module(module, python_bin, cwd, logger)]


def pinned_package_version(packages: str, package_name: str) -> str | None:
    package_name = package_name.lower()
    for item in shlex.split(packages):
        normalized = item.strip()
        if normalized.lower().startswith(f"{package_name}=="):
            return normalized.split("==", 1)[1]
    return None


def python_package_version(package_name: str, python_bin: str, cwd: Path) -> str | None:
    script = (
        "from importlib.metadata import version, PackageNotFoundError\n"
        f"try:\n    print(version({package_name!r}))\n"
        "except PackageNotFoundError:\n    raise SystemExit(1)\n"
    )
    result = subprocess.run(
        [python_bin, "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def flash_attn_available(python_bin: str, cwd: Path) -> bool:
    script = "from flash_attn import flash_attn_varlen_func\nassert callable(flash_attn_varlen_func)\n"
    result = subprocess.run(
        [python_bin, "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def install_flash_attn(python_bin: str, video_gen: dict[str, Any], logger: logging.Logger, cwd: Path) -> None:
    if flash_attn_available(python_bin, cwd):
        return

    package = config_string(video_gen, "flash_attn_package", DEFAULT_HUNYUAN_FLASH_ATTN_PACKAGE)
    if not package or package.lower() in {"0", "false", "no", "none"}:
        logger.info("Flash Attention is unavailable and auto install is disabled.")
        return

    logger.info("Installing Flash Attention for Hunyuan: %s", package)
    run_command([python_bin, "-m", "pip", "install", "ninja", "packaging", "wheel", "setuptools"], logger, cwd=cwd)
    run_command([python_bin, "-m", "pip", "install", "--no-build-isolation", package], logger, cwd=cwd)

    if not flash_attn_available(python_bin, cwd):
        raise RuntimeError(
            "Flash Attention installed but flash_attn_varlen_func is still unavailable. "
            "Check CUDA, torch, and flash-attn build logs."
        )


def config_string(config: dict[str, Any], key: str, default: str = "") -> str:
    value = str(config.get(key, "") or "").strip()
    if not value or "${" in value:
        return default
    return value


def config_bool(config: dict[str, Any], key: str, default: bool = False) -> bool:
    value = str(config.get(key, "") or "").strip().lower()
    if not value or "${" in value:
        return default
    return value in {"1", "true", "yes", "on"}


def ensure_hunyuan_runtime(hunyuan_root: Path, video_gen: dict[str, Any], logger: logging.Logger) -> None:
    if str(video_gen.get("auto_install_deps", "true")).lower() in {"0", "false", "no"}:
        return

    runtime_key = hunyuan_root.resolve()
    if runtime_key in HUNYUAN_RUNTIME_READY:
        return

    python_bin = str(video_gen.get("python_bin", "python3"))
    install_compatible_torch(python_bin, video_gen, logger, hunyuan_root)
    default_required = "loguru imageio diffusers.models.autoencoders.autoencoder_kl deepspeed tensorboard"
    required_modules = shlex.split(config_string(video_gen, "required_modules", default_required))
    requirements = hunyuan_root / "requirements.txt"
    missing = missing_python_modules(required_modules, python_bin, hunyuan_root, logger)
    force_packages = config_string(video_gen, "force_pip_packages", DEFAULT_HUNYUAN_FORCE_PIP_PACKAGES)

    if requirements.exists() and missing:
        logger.info("Installing Hunyuan requirements because modules are missing: %s", ", ".join(missing))
        run_command(
            [python_bin, "-m", "pip", "install", "-r", str(compatible_requirements_path(requirements, logger))],
            logger,
            cwd=hunyuan_root,
        )

    expected_transformers = pinned_package_version(force_packages, "transformers")
    installed_transformers = python_package_version("transformers", python_bin, hunyuan_root) if expected_transformers else None
    missing = missing_python_modules(required_modules, python_bin, hunyuan_root, logger)
    if force_packages and (missing or (expected_transformers and installed_transformers != expected_transformers)):
        reason = ", ".join(missing) if missing else f"transformers {installed_transformers or '<missing>'} != {expected_transformers}"
        logger.info("Installing pinned Hunyuan packages because runtime is incompatible: %s", reason)
        run_command([python_bin, "-m", "pip", "install", "--force-reinstall", "--no-deps", *shlex.split(force_packages)], logger, cwd=hunyuan_root)

    extra_packages = config_string(video_gen, "extra_pip_packages", DEFAULT_HUNYUAN_EXTRA_PIP_PACKAGES)
    install_flash_attn(python_bin, video_gen, logger, hunyuan_root)

    missing = missing_python_modules(required_modules, python_bin, hunyuan_root, logger)
    if extra_packages and missing:
        logger.info("Installing Hunyuan extra packages because modules are missing: %s", ", ".join(missing))
        run_command([python_bin, "-m", "pip", "install", *shlex.split(extra_packages)], logger, cwd=hunyuan_root)

    HUNYUAN_RUNTIME_READY.add(runtime_key)


def ensure_hunyuan_i2v_weights(hunyuan_ckpt: Path, video_gen: dict[str, Any], logger: logging.Logger) -> None:
    i2v_weight = hunyuan_ckpt / "hunyuan-video-i2v-720p" / "transformers" / "mp_rank_00_model_states.pt"
    i2v_vae_config = i2v_vae_config_path(hunyuan_ckpt)
    text_encoder_config = text_encoder_i2v_config_path(hunyuan_ckpt)
    clip_encoder_config = text_encoder_2_config_path(hunyuan_ckpt)
    expected_files = [i2v_weight, i2v_vae_config, text_encoder_config, clip_encoder_config]
    if all(path.exists() for path in expected_files):
        return

    if not config_bool(video_gen, "auto_download_weights", False):
        raise FileNotFoundError(
            "Hunyuan I2V files missing: "
            + ", ".join(str(path) for path in expected_files if not path.exists())
            + ". "
            "Download with: python3 -m pip install -U 'huggingface_hub[cli]' hf_transfer && "
            f"HF_HUB_ENABLE_HF_TRANSFER=1 hf download tencent/HunyuanVideo-I2V --local-dir {shlex.quote(str(hunyuan_ckpt))}. "
            "Or set video_gen.auto_download_weights=true after confirming disk space."
        )

    model_repo = config_string(video_gen, "model_repo", "tencent/HunyuanVideo-I2V")
    text_encoder_repo = config_string(video_gen, "text_encoder_repo", "xtuner/llava-llama-3-8b-v1_1-transformers")
    clip_repo = config_string(video_gen, "clip_repo", "openai/clip-vit-large-patch14")
    hunyuan_ckpt.mkdir(parents=True, exist_ok=True)
    run_command(["python3", "-m", "pip", "install", "-U", "huggingface_hub[cli]", "hf_transfer"], logger)

    if not i2v_weight.exists() or not i2v_vae_config.exists():
        download_hf_repo(model_repo, hunyuan_ckpt, logger)
    if not text_encoder_config.exists():
        download_hf_repo(text_encoder_repo, hunyuan_ckpt / "text_encoder_i2v", logger)
    if not clip_encoder_config.exists():
        download_hf_repo(clip_repo, hunyuan_ckpt / "text_encoder_2", logger)

    missing = [path for path in expected_files if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Hunyuan I2V download finished but expected files are still missing: "
            + ", ".join(str(path) for path in missing)
        )


def download_hf_repo(repo_id: str, target_dir: Path, logger: logging.Logger) -> None:
    command = ["hf", "download", repo_id, "--local-dir", str(target_dir)]
    logger.info("Downloading Hugging Face repo=%s target=%s", repo_id, target_dir)
    env = os.environ.copy()
    env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if result.stdout:
        logger.info("download stdout: %s", result.stdout[-4000:])
    if result.stderr:
        logger.info("download stderr: %s", result.stderr[-4000:])
    if result.returncode != 0:
        raise RuntimeError(f"Hugging Face download failed repo={repo_id} exit={result.returncode}: {result.stderr[-2000:]}")


def i2v_weight_path(hunyuan_ckpt: Path) -> Path:
    return hunyuan_ckpt / "hunyuan-video-i2v-720p" / "transformers" / "mp_rank_00_model_states.pt"


def i2v_vae_config_path(hunyuan_ckpt: Path) -> Path:
    return hunyuan_ckpt / "hunyuan-video-i2v-720p" / "vae" / "config.json"


def text_encoder_i2v_config_path(hunyuan_ckpt: Path) -> Path:
    return hunyuan_ckpt / "text_encoder_i2v" / "config.json"


def text_encoder_2_config_path(hunyuan_ckpt: Path) -> Path:
    return hunyuan_ckpt / "text_encoder_2" / "config.json"


def resolve_hunyuan_root(configured: Path, logger: logging.Logger) -> Path:
    preferred = Path("/workspace/HunyuanVideo-I2V")
    if str(configured) == "/workspace/HunyuanVideo-1.5" and (preferred / "sample_image2video.py").exists():
        logger.info("Using preferred Hunyuan I2V root instead of legacy path: %s", preferred)
        return preferred
    return configured


def detect_hunyuan_ckpt(configured: Path, hunyuan_root: Path, logger: logging.Logger) -> Path:
    candidates = [
        configured,
        Path("/models/hunyuan/ckpts"),
        Path("/models/hunyuan"),
        Path("/workspace/models/hunyuan/ckpts"),
        Path("/workspace/models/hunyuan"),
        hunyuan_root / "ckpts",
        Path("/workspace/HunyuanVideo-1.5/ckpts"),
        Path("/workspace/HunyuanVideo-I2V/ckpts"),
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if i2v_weight_path(candidate).exists():
            if candidate != configured:
                logger.info("Detected HUNYUAN_CKPT=%s with required I2V weight", candidate)
            return candidate
    return configured


def ensure_hunyuan_ckpt_symlink(hunyuan_root: Path, hunyuan_ckpt: Path, logger: logging.Logger) -> None:
    link_path = hunyuan_root / "ckpts"
    required_paths = [
        i2v_weight_path(hunyuan_ckpt),
        i2v_vae_config_path(hunyuan_ckpt),
        text_encoder_i2v_config_path(hunyuan_ckpt),
        text_encoder_2_config_path(hunyuan_ckpt),
    ]
    missing_required = [path for path in required_paths if not path.exists()]
    if missing_required:
        raise FileNotFoundError(
            "Hunyuan checkpoint directory is incomplete. Missing: "
            + ", ".join(str(path) for path in missing_required)
        )

    if link_path.is_symlink():
        current_target = link_path.resolve()
        if current_target != hunyuan_ckpt.resolve():
            logger.info("Updating Hunyuan ckpts symlink: %s -> %s", link_path, hunyuan_ckpt)
            link_path.unlink()
            link_path.symlink_to(hunyuan_ckpt, target_is_directory=True)
        return

    if not link_path.exists():
        logger.info("Creating Hunyuan ckpts symlink: %s -> %s", link_path, hunyuan_ckpt)
        link_path.symlink_to(hunyuan_ckpt, target_is_directory=True)
        return

    if all(path.exists() for path in [
        i2v_weight_path(link_path),
        i2v_vae_config_path(link_path),
        text_encoder_i2v_config_path(link_path),
        text_encoder_2_config_path(link_path),
    ]):
        return

    backup_path = hunyuan_root / f"ckpts.local_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.warning("Backing up incomplete Hunyuan local ckpts directory: %s -> %s", link_path, backup_path)
    link_path.rename(backup_path)
    logger.info("Creating Hunyuan ckpts symlink: %s -> %s", link_path, hunyuan_ckpt)
    link_path.symlink_to(hunyuan_ckpt, target_is_directory=True)


def build_command(row: dict[str, str], video_gen: dict[str, Any], save_dir: Path) -> str:
    image = resolve_path(row["output_image"])
    output = resolve_path(row["output_video"])
    hunyuan_root = resolve_hunyuan_root(Path(str(video_gen.get("hunyuan_root", ""))), logging.getLogger("batch_video_gen"))
    hunyuan_ckpt = detect_hunyuan_ckpt(Path(str(video_gen.get("hunyuan_ckpt", ""))), hunyuan_root, logging.getLogger("batch_video_gen"))
    values = {
        "prompt": row.get("prompt", ""),
        "negative_prompt": row.get("negative_prompt", ""),
        "image": image,
        "output": output,
        "save_dir": save_dir,
        "seed": row.get("seed", ""),
        "motion_level": row.get("motion_level", ""),
        "duration": row.get("duration", video_gen.get("duration_sec", 4)),
        "fps": video_gen.get("fps", 24),
        "hunyuan_root": hunyuan_root,
        "hunyuan_ckpt": hunyuan_ckpt,
        "dit_weight": hunyuan_ckpt / "hunyuan-video-t2v-720p" / "transformers" / "mp_rank_00_model_states.pt",
        "i2v_dit_weight": hunyuan_ckpt / "hunyuan-video-i2v-720p" / "transformers" / "mp_rank_00_model_states.pt",
        "model_dir": video_gen.get("model_dir", ""),
        "resolution": video_gen.get("resolution", "720p"),
        "infer_steps": video_gen.get("infer_steps", 50),
        "video_length": video_gen.get("video_length", 129),
        "flow_shift": video_gen.get("flow_shift", 7.0 if row.get("motion_level") == "low" else 17.0),
        "cfg_scale": video_gen.get("cfg_scale", 6.0),
    }
    template = video_gen.get("command_template") or default_hunyuan_command_template()
    return format_command(str(template), values)


def copy_generated_video(save_dir: Path, output_video: Path) -> None:
    if output_video.exists():
        return
    candidates = sorted(save_dir.rglob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No generated mp4 found under {save_dir}")
    output_video.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates[0], output_video)


def generate_video(row: dict[str, str], video_gen: dict[str, Any], logger: logging.Logger) -> Path:
    image = resolve_path(row["output_image"])
    output_video = resolve_path(row["output_video"])
    if not image.exists():
        raise FileNotFoundError(f"Keyframe image missing: {image}")

    hunyuan_root = resolve_hunyuan_root(Path(str(video_gen.get("hunyuan_root", ""))), logger)
    if not hunyuan_root.exists():
        raise FileNotFoundError(f"HUNYUAN_ROOT does not exist: {hunyuan_root}")
    ensure_hunyuan_runtime(hunyuan_root, video_gen, logger)
    hunyuan_ckpt = detect_hunyuan_ckpt(Path(str(video_gen.get("hunyuan_ckpt", ""))), hunyuan_root, logger)
    if "${" in str(hunyuan_ckpt):
        raise FileNotFoundError(f"HUNYUAN_CKPT does not exist or is not configured: {hunyuan_ckpt}")
    if not hunyuan_ckpt.exists() and not config_bool(video_gen, "auto_download_weights", False):
        raise FileNotFoundError(f"HUNYUAN_CKPT does not exist or is not configured: {hunyuan_ckpt}")
    ensure_hunyuan_i2v_weights(hunyuan_ckpt, video_gen, logger)
    ensure_hunyuan_ckpt_symlink(hunyuan_root, hunyuan_ckpt, logger)

    save_dir = ROOT / "temp" / "hunyuan" / output_video.stem
    save_dir.mkdir(parents=True, exist_ok=True)
    command = build_command(row, video_gen, save_dir)
    logger.info("Running video command shot=%s command=%s", row.get("shot_id"), command)
    result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
    if result.stdout:
        logger.info("video stdout: %s", result.stdout[-4000:])
    if result.stderr:
        logger.info("video stderr: %s", result.stderr[-8000:])
    if result.returncode != 0:
        raise RuntimeError(f"Video command failed exit={result.returncode}: {result.stderr[-2000:]}")

    copy_generated_video(save_dir, output_video)
    logger.info("Saved video: %s", output_video)
    return output_video


def main() -> None:
    args = parse_args()
    logger = setup_logger(args.episode)
    config = load_project_config(resolve_path(args.config))
    video_gen = config.get("video_gen", {}) or {}
    prompt_csv = find_prompt_csv(args.episode, args.prompt_csv)
    rows = load_rows(prompt_csv)
    logger.info("script=06_batch_video_gen input=%s rows=%s dry_run=%s", prompt_csv, len(rows), args.dry_run)

    processed = 0
    success = 0
    failed = 0
    for row in rows:
        if not row_matches(row, args):
            continue
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        output_video = resolve_path(row["output_video"])
        if output_video.exists() and not args.overwrite:
            row["status"] = "done"
            success += 1
            logger.info("Skip existing video: %s", output_video)
            continue

        if args.dry_run:
            save_dir = ROOT / "temp" / "hunyuan" / output_video.stem
            logger.info("DRY RUN video row shot=%s command=%s", row.get("shot_id"), build_command(row, video_gen, save_dir))
            continue

        try:
            generate_video(row, video_gen, logger)
            row["status"] = "done"
            success += 1
        except Exception as exc:
            row["status"] = "failed"
            failed += 1
            logger.exception("Video generation failed shot=%s reason=%s", row.get("shot_id"), exc)

    if not args.dry_run:
        save_rows(prompt_csv, rows)
    logger.info("processed=%s success=%s failed=%s output=%s", processed, success, failed, prompt_csv)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
