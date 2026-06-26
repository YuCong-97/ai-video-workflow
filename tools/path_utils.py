from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def script_path(episode_id: str) -> Path:
    return Path("data/scripts") / f"{episode_id}_script.json"


def storyboard_path(episode_id: str) -> Path:
    return Path("data/storyboards") / f"{episode_id}_storyboard.json"


def prompts_path(episode_id: str) -> Path:
    return Path("data/prompts") / f"{episode_id}_prompts.csv"


def image_output_path(episode_id: str, shot_id: str, candidate_index: int) -> Path:
    return Path("outputs/images") / episode_id / f"{shot_id}_ref_{candidate_index:02d}.png"


def video_output_path(shot_id: str, seed: int, motion_level: str) -> Path:
    return Path("outputs/videos/raw") / f"{shot_id}_seed{seed}_{motion_level}.mp4"


def score_output_path(video_name: str) -> Path:
    stem = Path(video_name).stem
    return Path("outputs/videos/scored") / f"{stem}.score.json"

