from __future__ import annotations

import argparse
import csv
import logging
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


def ensure_hunyuan_runtime(hunyuan_root: Path, video_gen: dict[str, Any], logger: logging.Logger) -> None:
    if str(video_gen.get("auto_install_deps", "true")).lower() in {"0", "false", "no"}:
        return

    python_bin = str(video_gen.get("python_bin", "python3"))
    required_modules = shlex.split(
        str(video_gen.get("required_modules", "loguru imageio diffusers deepspeed tensorboard") or "")
    )
    requirements = hunyuan_root / "requirements.txt"
    missing = missing_python_modules(required_modules, python_bin, hunyuan_root, logger)
    if requirements.exists() and missing:
        logger.info("Installing Hunyuan requirements because modules are missing: %s", ", ".join(missing))
        run_command([python_bin, "-m", "pip", "install", "-r", str(requirements)], logger, cwd=hunyuan_root)

    extra_packages = str(video_gen.get("extra_pip_packages", "") or "").strip()
    missing = missing_python_modules(required_modules, python_bin, hunyuan_root, logger)
    if extra_packages and missing:
        logger.info("Installing Hunyuan extra packages because modules are missing: %s", ", ".join(missing))
        run_command([python_bin, "-m", "pip", "install", *shlex.split(extra_packages)], logger, cwd=hunyuan_root)


def build_command(row: dict[str, str], video_gen: dict[str, Any], save_dir: Path) -> str:
    image = resolve_path(row["output_image"])
    output = resolve_path(row["output_video"])
    hunyuan_root = Path(str(video_gen.get("hunyuan_root", "")))
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
        "hunyuan_ckpt": video_gen.get("hunyuan_ckpt", ""),
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

    hunyuan_root = Path(str(video_gen.get("hunyuan_root", "")))
    if not hunyuan_root.exists():
        raise FileNotFoundError(f"HUNYUAN_ROOT does not exist: {hunyuan_root}")
    ensure_hunyuan_runtime(hunyuan_root, video_gen, logger)

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
