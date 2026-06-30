from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.config_loader import load_project_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check ComfyUI and HunyuanVideo configuration.")
    parser.add_argument("--config", default="input/config/project.yaml")
    return parser.parse_args()


def is_unset(value: str) -> bool:
    return not value or "${" in value


def has_weight_files(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    return any(item.is_file() or item.is_symlink() for item in path.rglob("*"))


def validate_comfyui_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        workflow: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"ComfyUI workflow JSON is invalid: {exc}"]

    if "note" in workflow or "placeholders" in workflow:
        errors.append("ComfyUI workflow is still the placeholder/example file.")

    api_nodes = [
        node
        for node in workflow.values()
        if isinstance(node, dict) and "class_type" in node and isinstance(node.get("inputs"), dict)
    ]
    if not api_nodes:
        errors.append("ComfyUI workflow is not API format; expected nodes with class_type and inputs.")

    workflow_text = json.dumps(workflow, ensure_ascii=False)
    required_placeholders = [
        "__PROMPT__",
        "__NEGATIVE_PROMPT__",
        "__SEED__",
        "__WIDTH__",
        "__HEIGHT__",
        "__OUTPUT_PREFIX__",
    ]
    missing = [placeholder for placeholder in required_placeholders if placeholder not in workflow_text]
    if missing:
        errors.append(f"ComfyUI workflow missing placeholders: {', '.join(missing)}")

    return errors


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


def get_available_comfyui_checkpoints(comfyui_url: str) -> list[str]:
    response = requests.get(f"{comfyui_url}/object_info/CheckpointLoaderSimple", timeout=10)
    response.raise_for_status()
    data = response.json()
    node_info = data.get("CheckpointLoaderSimple", data)
    input_info = node_info.get("input", {}) if isinstance(node_info, dict) else {}
    required = input_info.get("required", {}) if isinstance(input_info, dict) else {}
    ckpt_config = required.get("ckpt_name", []) if isinstance(required, dict) else []
    if isinstance(ckpt_config, list) and ckpt_config and isinstance(ckpt_config[0], list):
        return [str(item) for item in ckpt_config[0]]
    return []


def main() -> None:
    args = parse_args()
    config = load_project_config(ROOT / args.config)
    image_gen = config.get("image_gen", {}) or {}
    video_gen = config.get("video_gen", {}) or {}

    errors: list[str] = []
    comfyui_url = str(image_gen.get("comfyui_url", "")).rstrip("/")
    workflow_path = ROOT / str(image_gen.get("workflow_path", "input/config/comfyui_workflow_api.json"))
    hunyuan_root = Path(str(video_gen.get("hunyuan_root", "")))
    hunyuan_ckpt = Path(str(video_gen.get("hunyuan_ckpt", "")))

    print("Real generation configuration check")
    print(f"COMFYUI_URL: {comfyui_url}")
    print(f"workflow_path: {workflow_path}")
    print(f"HUNYUAN_ROOT: {hunyuan_root}")
    print(f"HUNYUAN_CKPT: {hunyuan_ckpt}")

    if is_unset(comfyui_url):
        errors.append("COMFYUI_URL is not configured.")
    else:
        try:
            response = requests.get(f"{comfyui_url}/system_stats", timeout=5)
            if response.status_code >= 400:
                errors.append(f"ComfyUI responded with HTTP {response.status_code}.")
            else:
                print("ComfyUI reachable: OK")
        except Exception as exc:
            errors.append(f"ComfyUI not reachable: {exc}")

    if not workflow_path.exists():
        errors.append(f"ComfyUI API workflow missing: {workflow_path}")
    else:
        workflow_errors = validate_comfyui_workflow(workflow_path)
        if workflow_errors:
            errors.extend(workflow_errors)
        else:
            print("ComfyUI workflow file: OK")
            if not is_unset(comfyui_url):
                workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
                required_checkpoints = get_workflow_checkpoint_names(workflow, image_gen)
                if required_checkpoints:
                    try:
                        available_checkpoints = get_available_comfyui_checkpoints(comfyui_url)
                    except Exception as exc:
                        errors.append(f"Could not read ComfyUI checkpoint list: {exc}")
                    else:
                        missing = [name for name in required_checkpoints if name not in available_checkpoints]
                        if missing:
                            available_preview = ", ".join(available_checkpoints[:20]) if available_checkpoints else "<none>"
                            errors.append(
                                "ComfyUI checkpoint missing. "
                                f"Workflow requires: {', '.join(missing)}. "
                                f"Available checkpoints: {available_preview}. "
                                "Put the model under ComfyUI/models/checkpoints and restart ComfyUI, "
                                "or export a workflow that uses an installed checkpoint."
                            )
                        else:
                            print(f"ComfyUI checkpoint: OK ({', '.join(required_checkpoints)})")

    if is_unset(str(hunyuan_root)) or not hunyuan_root.exists():
        errors.append(f"HUNYUAN_ROOT missing: {hunyuan_root}")
    elif not (hunyuan_root / "sample_image2video.py").exists():
        errors.append(f"HUNYUAN_ROOT does not contain sample_image2video.py: {hunyuan_root}")
    else:
        print("HUNYUAN_ROOT: OK")

    if is_unset(str(hunyuan_ckpt)) or not hunyuan_ckpt.exists():
        errors.append(f"HUNYUAN_CKPT missing: {hunyuan_ckpt}")
    elif not has_weight_files(hunyuan_ckpt):
        errors.append(f"HUNYUAN_CKPT exists but appears empty: {hunyuan_ckpt}")
    else:
        print("HUNYUAN_CKPT: OK")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
