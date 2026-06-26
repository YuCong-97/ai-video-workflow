from __future__ import annotations

from typing import Any


DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted face, extra fingers, bad hands, "
    "duplicated body, inconsistent clothing, low resolution, watermark, text"
)


def character_prompt(character: dict[str, Any]) -> str:
    return character.get("visual_prompt_base") or character.get("name", "")


def scene_prompt(scene_template: dict[str, Any]) -> str:
    parts = [
        scene_template.get("description", ""),
        ", ".join(scene_template.get("key_elements", [])),
        scene_template.get("style", ""),
    ]
    return ", ".join(part for part in parts if part)


def shot_prompt(shot: dict[str, Any]) -> str:
    return (
        f"{shot.get('subject', '')}. {shot.get('action', '')}. "
        f"Emotion: {shot.get('emotion', '')}. "
        f"Shot type: {shot.get('shot_type', '')}. "
        f"Camera angle: {shot.get('camera_angle', '')}. "
        f"Camera movement: {shot.get('camera_movement', '')}. "
        f"Visual focus: {shot.get('visual_focus', '')}."
    )


def build_prompt(
    characters: list[dict[str, Any]],
    scene_template: dict[str, Any],
    shot: dict[str, Any],
    style_prompt: str,
) -> str:
    character_part = ", ".join(character_prompt(character) for character in characters)
    parts = [
        character_part,
        f"in {scene_prompt(scene_template)}" if scene_template else "",
        shot_prompt(shot),
        style_prompt,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())

