from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml


def load_project_env(start: Path | None = None) -> None:
    current = (start or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        env_path = path / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict[str, Any]:
    load_project_env(path.parent)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return expand_env(data)


def load_project_config(path: Path = Path("input/config/project.yaml")) -> dict[str, Any]:
    config = load_yaml(path)
    required = ["project_name", "style", "language", "episode"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")
    return config
