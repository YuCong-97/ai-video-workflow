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
    configured_ckpt = str(image_gen.get("ckpt_name", "")).strip()
    replacements = {
        "__PROMPT__": row.get("prompt", ""),
        "__NEGATIVE_PROMPT__": row.get("negative_prompt", ""),
        "__SEED__": int(row.get("seed") or 0),
        "__WIDTH__": int(image_gen.get("width", 832)),
        "__HEIGHT__": int(image_gen.get("height", 1216)),
        "__SHOT_ID__": row.get("shot_id", ""),
        "__OUTPUT_PREFIX__": Path(row.get("output_image", "output.png")).stem,
    }
    if configured_ckpt and "${" not in configured_ckpt:
        replacements["__CKPT_NAME__"] = configured_ckpt

    def replace_value(value: Any) -> Any:
        if isinstance(value, str):
            if value in replacements:
                return replacements[value]
            for key, replacement in replacements.items():
                value = value.replace(key, str(replacement))
            return value
        if isinstance(value, list):
            return [replace_value(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_value(item) for key, item in value.items()}
        return value

    return replace_value(workflow)


def validate_comfyui_api_workflow(workflow: dict[str, Any], workflow_path: Path) -> None:
    if "note" in workflow or "placeholders" in workflow:
        raise ValueError(
            f"ComfyUI workflow is a placeholder, not an API workflow: {workflow_path}. "
            "Open ComfyUI, export a real API-format workflow, and save it to this path."
        )

    valid_nodes = [
        node
        for node in workflow.values()
        if isinstance(node, dict) and "class_type" in node and isinstance(node.get("inputs"), dict)
    ]
    if not valid_nodes:
        raise ValueError(
            f"Invalid ComfyUI API workflow: {workflow_path}. "
            "The file should be the API-format JSON exported from ComfyUI and contain nodes with class_type/inputs."
        )


def get_workflow_checkpoint_names(workflow: dict[str, Any], image_gen: dict[str, Any]) -> list[str]:
    configured_ckpt = str(image_gen.get("ckpt_name", "")).strip()
    names: list[str] = []
    for node in workflow.values():
        if not isinstance(node, dict) or node.get("class_type") != "CheckpointLoaderSimple":
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        ckpt_name = str(inputs.get("ckpt_name", "")).strip()
        if ckpt_name == "__CKPT_NAME__":
            ckpt_name = configured_ckpt
        if ckpt_name and "${" not in ckpt_name:
            names.append(ckpt_name)
    return sorted(set(names))


def get_available_comfyui_checkpoints(url: str) -> list[str]:
    response = requests.get(f"{url}/object_info/CheckpointLoaderSimple", timeout=10)
    response.raise_for_status()
    data = response.json()
    node_info = data.get("CheckpointLoaderSimple", data)
    input_info = node_info.get("input", {}) if isinstance(node_info, dict) else {}
    required = input_info.get("required", {}) if isinstance(input_info, dict) else {}
    ckpt_config = required.get("ckpt_name", []) if isinstance(required, dict) else []
    if isinstance(ckpt_config, list) and ckpt_config and isinstance(ckpt_config[0], list):
        return [str(item) for item in ckpt_config[0]]
    return []


def ensure_workflow_models_available(
    url: str,
    workflow_path: Path,
    image_gen: dict[str, Any],
    logger: logging.Logger,
) -> None:
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    validate_comfyui_api_workflow(workflow, workflow_path)
    required_checkpoints = get_workflow_checkpoint_names(workflow, image_gen)
    if not required_checkpoints:
        return

    available_checkpoints = get_available_comfyui_checkpoints(url)
    missing = [name for name in required_checkpoints if name not in available_checkpoints]
    if missing:
        available_preview = ", ".join(available_checkpoints[:20]) if available_checkpoints else "<none>"
        logger.error(
            "ComfyUI checkpoint preflight failed. required=%s available=%s",
            ", ".join(missing),
            available_preview,
        )
        raise RuntimeError(
            "ComfyUI checkpoint missing. "
            f"Workflow requires: {', '.join(missing)}. "
            f"Available checkpoints: {available_preview}. "
            "Put the model file under ComfyUI/models/checkpoints, restart ComfyUI, "
            "or update input/config/comfyui_workflow_api.json to use an installed checkpoint."
        )


def raise_for_comfyui_error(response: requests.Response, context: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = response.text.strip()
        if len(body) > 2000:
            body = body[:2000] + "...[truncated]"
        raise requests.HTTPError(f"{context}: {exc}; response_body={body}", response=response) from exc


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
    validate_comfyui_api_workflow(workflow, workflow_path)
    prompt = apply_workflow_placeholders(workflow, row, image_gen)
    client_id = str(uuid.uuid4())
    logger.info("Submitting ComfyUI workflow shot=%s seed=%s url=%s", row.get("shot_id"), row.get("seed"), url)
    response = requests.post(f"{url}/prompt", json={"prompt": prompt, "client_id": client_id}, timeout=30)
    raise_for_comfyui_error(response, "ComfyUI /prompt failed")
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
            url, workflow_path, _ = require_comfyui_config(image_gen)
            ensure_comfyui_reachable(url, logger)
            ensure_workflow_models_available(url, workflow_path, image_gen, logger)
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
