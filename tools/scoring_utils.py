from __future__ import annotations

from pathlib import Path


def placeholder_score(video_path: Path) -> dict[str, float | str | bool]:
    return {
        "video": video_path.name,
        "sharpness_score": 0.0,
        "face_score": 0.0,
        "consistency_score": 0.0,
        "motion_score": 0.0,
        "prompt_match_score": 0.0,
        "final_score": 0.0,
        "recommend": False,
    }

