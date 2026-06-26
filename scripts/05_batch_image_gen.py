from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.config_loader import load_project_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch generate keyframe images from prompt CSV.")
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
    logger = logging.getLogger("batch_image_gen")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    path = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}_{episode_id}_batch_image_gen.log"
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


def apply_workflow_placeholders(workflow: dict[str, Any], row: dict[str, str], image_gen: dict[str, Any]) -> dict[str, Any]:
    replacements = {
        "__PROMPT__": row.get("prompt", ""),
        "__NEGATIVE_PROMPT__": row.get("negative_prompt", ""),
        "__SEED__": str(row.get("seed", "")),
        "__WIDTH__": str(image_gen.get("width", 832)),
        "__HEIGHT__": str(image_gen.get("height", 1216)),
        "__SHOT_ID__": row.get("shot_id", ""),
        "__OUTPUT_PREFIX__": Path(row.get("output_image", "output.png")).stem,
    }
    text = json.dumps(workflow, ensure_ascii=False)
    for key, value in replacements.items():
        text = text.replace(key, str(value))
    return json.loads(text)


def require_comfyui_config(image_gen: dict[str, Any]) -> tuple[str, Path, int]:
    url = str(image_gen.get("comfyui_url", "")).strip().rstrip("/")
    workflow_path = resolve_path(image_gen.get("workflow_path", "input/config/comfyui_workflow_api.json"))
    timeout_sec = int(image_gen.get("timeout_sec", 900))
    if not url or "${" in url:
        raise ValueError("image_gen.comfyui_url is empty. Set COMFYUI_URL or project.yaml image_gen.comfyui_url.")
    if not workflow_path.exists():
        raise FileNotFoundError(
            f"ComfyUI workflow not found: {workflow_path}. Export API-format workflow to this path."
        )
    return url, workflow_path, timeout_sec


def ensure_comfyui_reachable(url: str, logger: logging.Logger) -> None:
    try:
        response = requests.get(f"{url}/system_stats", timeout=5)
        response.raise_for_status()
    except Exception as exc:
        logger.error("ComfyUI is not reachable: %s. Start ComfyUI or run ./start_visual.sh --start-comfyui.", url)
        raise RuntimeError(
            f"ComfyUI is not reachable: {url}. "
            "Start ComfyUI on port 8188, run ./start_visual.sh --start-comfyui, "
            "or set COMFYUI_URL to the correct service URL."
        ) from exc


def submit_comfyui_workflow(
    row: dict[str, str],
    image_gen: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    url, workflow_path, timeout_sec = require_comfyui_config(image_gen)
    output_path = resolve_path(row["output_image"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    prompt = apply_workflow_placeholders(workflow, row, image_gen)
    client_id = str(uuid.uuid4())
    logger.info("Submitting ComfyUI workflow shot=%s seed=%s url=%s", row.get("shot_id"), row.get("seed"), url)
    response = requests.post(f"{url}/prompt", json={"prompt": prompt, "client_id": client_id}, timeout=30)
    response.raise_for_status()
    prompt_id = response.json()["prompt_id"]

    deadline = time.time() + timeout_sec
    history: dict[str, Any] | None = None
    while time.time() < deadline:
        history_response = requests.get(f"{url}/history/{prompt_id}", timeout=30)
        history_response.raise_for_status()
        data = history_response.json()
        if data and prompt_id in data:
            history = data[prompt_id]
            break
        time.sleep(2)
    if history is None:
        raise TimeoutError(f"ComfyUI prompt timed out after {timeout_sec}s: {prompt_id}")

    outputs = history.get("outputs", {})
    images: list[dict[str, str]] = []
    for output in outputs.values():
        images.extend(output.get("images", []))
    if not images:
        raise RuntimeError(f"ComfyUI history has no images for prompt_id={prompt_id}")

    image = images[0]
    view_response = requests.get(
        f"{url}/view",
        params={
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        },
        timeout=120,
    )
    view_response.raise_for_status()
    output_path.write_bytes(view_response.content)
    logger.info("Saved ComfyUI image: %s", output_path)
    return output_path


def main() -> None:
    args = parse_args()
    logger = setup_logger(args.episode)
    config = load_project_config(resolve_path(args.config))
    image_gen = config.get("image_gen", {}) or {}
    prompt_csv = find_prompt_csv(args.episode, args.prompt_csv)
    rows = load_rows(prompt_csv)
    logger.info("script=05_batch_image_gen input=%s rows=%s dry_run=%s", prompt_csv, len(rows), args.dry_run)

    if not args.dry_run:
        try:
            url, _, _ = require_comfyui_config(image_gen)
            ensure_comfyui_reachable(url, logger)
        except Exception as exc:
            logger.error("Image generation preflight failed: %s", exc)
            raise SystemExit(1) from exc

    processed = 0
    success = 0
    failed = 0
    for row in rows:
        if not row_matches(row, args):
            continue
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        output_image = resolve_path(row["output_image"])
        if output_image.exists() and not args.overwrite:
            row["status"] = "image_done"
            success += 1
            logger.info("Skip existing image: %s", output_image)
            continue

        if args.dry_run:
            logger.info("DRY RUN image row shot=%s output=%s", row.get("shot_id"), output_image)
            continue

        try:
            submit_comfyui_workflow(row, image_gen, logger)
            row["status"] = "image_done"
            success += 1
        except Exception as exc:
            row["status"] = "failed"
            failed += 1
            logger.exception("Image generation failed shot=%s reason=%s", row.get("shot_id"), exc)

    if not args.dry_run:
        save_rows(prompt_csv, rows)
    logger.info("processed=%s success=%s failed=%s output=%s", processed, success, failed, prompt_csv)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
