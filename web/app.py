from __future__ import annotations

import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated

import requests
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from tools.config_loader import load_project_config


ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = ROOT / "data" / "jobs"
PROMPTS_DIR = ROOT / "data" / "prompts"
REFERENCE_DIR = ROOT / "assets" / "references"
LOG_DIR = ROOT / "logs"

CSV_FIELDS = [
    "episode_id",
    "scene_id",
    "shot_id",
    "character_ids",
    "scene_template_id",
    "duration",
    "seed",
    "motion_level",
    "prompt",
    "negative_prompt",
    "output_image",
    "output_video",
    "status",
]

DEFAULT_NOVEL_TEXT = (
    "苏晚在深夜的医院病房中醒来，窗外暴雨敲打玻璃。她看见床头的旧手机，"
    "日期竟然回到了三年前。上一世她被最信任的人背叛，这一次她决定改变命运。"
    "门外传来脚步声，那个曾经害她失去一切的男人即将推门而入。"
)

DEFAULT_BASE_PROMPT = (
    "young Chinese woman, 24 years old, long black wavy hair, pale skin, almond eyes, "
    "wearing a white shirt and black blazer, lying on a hospital bed at night, "
    "modern private hospital room, cold white fluorescent light, rain on window glass, "
    "IV stand beside the bed, tense dramatic atmosphere, she slowly opens her eyes and looks shocked, "
    "cinematic realism, realistic lighting, highly detailed, vertical composition, film still"
)

DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted face, extra fingers, bad hands, duplicated body, "
    "inconsistent clothing, low resolution, watermark, text, logo, deformed body, wrong anatomy, cartoon, anime"
)

app = FastAPI(title="AI Short Drama Pipeline")


def setup_logger(job_id: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(job_id)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(LOG_DIR / f"{job_id}_visual_generate.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(stream_handler)
    return logger


def clean_id(value: str, default: str) -> str:
    value = (value or "").strip()
    if not value:
        return default
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value)


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，\s]+", value or "") if item.strip()]


def parse_int_list(value: str, fallback: list[int]) -> list[int]:
    parsed: list[int] = []
    for item in parse_csv_list(value):
        try:
            parsed.append(int(item))
        except ValueError:
            continue
    return parsed or fallback


def resolve_user_path(value: str, default: Path) -> Path:
    if not value.strip():
        return default
    path = Path(value.strip())
    if not path.is_absolute():
        path = ROOT / path
    return path


async def save_uploads(files: list[UploadFile], target_dir: Path) -> list[str]:
    saved: list[str] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    for index, upload in enumerate(files, start=1):
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower() or ".bin"
        filename = f"ref_{index:02d}{suffix}"
        path = target_dir / filename
        content = await upload.read()
        path.write_bytes(content)
        saved.append(str(path.relative_to(ROOT)))
    return saved


def write_prompt_csv(
    path: Path,
    episode_id: str,
    prompt: str,
    negative_prompt: str,
    output_dir: Path,
    duration: int,
    seeds: list[int],
    motion_levels: list[str],
) -> list[dict[str, str | int]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images" / episode_id
    video_dir = output_dir / "videos" / "raw"
    image_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    shot_id = f"{episode_id}_sc01_sh01"
    scene_id = f"{episode_id}_sc01"
    rows = []
    candidate_index = 1
    for seed in seeds:
        for motion_level in motion_levels:
            output_image = image_dir / f"{shot_id}_ref_{candidate_index:02d}.png"
            output_video = video_dir / f"{shot_id}_seed{seed}_{motion_level}.mp4"
            rows.append(
                {
                    "episode_id": episode_id,
                    "scene_id": scene_id,
                    "shot_id": shot_id,
                    "character_ids": "",
                    "scene_template_id": "",
                    "duration": duration,
                    "seed": seed,
                    "motion_level": motion_level,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "output_image": str(output_image.relative_to(ROOT)) if output_image.is_relative_to(ROOT) else str(output_image),
                    "output_video": str(output_video.relative_to(ROOT)) if output_video.is_relative_to(ROOT) else str(output_video),
                    "status": "pending",
                }
            )
            candidate_index += 1

    save_prompt_rows(path, rows)
    return rows


def save_prompt_rows(path: Path, rows: list[dict[str, str | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def is_comfyui_reachable(comfyui_url: str, timeout_sec: int = 5) -> bool:
    try:
        response = requests.get(f"{comfyui_url.rstrip('/')}/system_stats", timeout=timeout_sec)
        return response.status_code < 400
    except Exception:
        return False


def read_tail(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def ensure_comfyui_runtime_deps(comfyui_dir: Path, logger: logging.Logger) -> list[str]:
    auto_install = os.environ.get("AUTO_INSTALL_COMFYUI_DEPS", "1").strip().lower()
    if auto_install in {"0", "false", "no", "off"}:
        return []

    python_bin = os.environ.get("COMFYUI_PYTHON_BIN")
    if not python_bin:
        python_bin = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else shutil.which("python3")
    python_bin = python_bin or sys.executable
    probe = subprocess.run(
        [python_bin, "-c", "import sqlalchemy; import torch; torch.cuda.current_device()"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return []

    requirements_path = comfyui_dir / "requirements.txt"
    extra_packages = os.environ.get("COMFYUI_EXTRA_PIP_PACKAGES", "SQLAlchemy alembic").split()
    torch_packages = os.environ.get("COMFYUI_TORCH_PACKAGES", "torch torchvision torchaudio").split()
    torch_index_url = os.environ.get("COMFYUI_TORCH_INDEX_URL", "https://download.pytorch.org/whl/cu124")
    commands: list[list[str]] = []
    if requirements_path.exists():
        commands.append([python_bin, "-m", "pip", "install", "-r", str(requirements_path)])
    if torch_packages and torch_index_url:
        commands.append(
            [python_bin, "-m", "pip", "install", "--force-reinstall", *torch_packages, "--index-url", torch_index_url]
        )
    if extra_packages:
        commands.append([python_bin, "-m", "pip", "install", *extra_packages])
    for command in commands:
        logger.info("Installing missing ComfyUI runtime dependencies: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
        output = "\n".join(part for part in [result.stdout, result.stderr] if part)
        if output:
            logger.info("ComfyUI dependency install output:\n%s", output[-12000:])
        if result.returncode != 0:
            return [f"Failed to install ComfyUI dependencies exit={result.returncode}:\n{output[-4000:]}"]
    return []


def start_comfyui_if_needed(comfyui_url: str, logger: logging.Logger) -> list[str]:
    errors: list[str] = []
    comfyui_url = comfyui_url.rstrip("/")
    if is_comfyui_reachable(comfyui_url):
        logger.info("ComfyUI reachable: %s", comfyui_url)
        return errors

    auto_start = os.environ.get("AUTO_START_COMFYUI", "1").strip().lower()
    if auto_start in {"0", "false", "no", "off"}:
        return [f"ComfyUI is not reachable: {comfyui_url}. AUTO_START_COMFYUI is disabled."]

    comfyui_dir = Path(os.environ.get("COMFYUI_DIR", "/workspace/ComfyUI"))
    main_py = comfyui_dir / "main.py"
    if not main_py.exists():
        return [
            f"ComfyUI is not reachable: {comfyui_url}. COMFYUI_DIR does not contain main.py: {comfyui_dir}"
        ]

    errors.extend(ensure_comfyui_runtime_deps(comfyui_dir, logger))
    if errors:
        return errors

    port_match = re.search(r":(\d+)(?:/)?$", comfyui_url)
    port = port_match.group(1) if port_match else "8188"
    python_bin = os.environ.get("COMFYUI_PYTHON_BIN")
    if not python_bin:
        python_bin = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else shutil.which("python3")
    python_bin = python_bin or sys.executable
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "temp").mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "comfyui.log"
    pid_path = ROOT / "temp" / "comfyui.pid"

    logger.info("ComfyUI is not reachable; starting it from %s", comfyui_dir)
    command = [python_bin, "main.py", "--listen", "0.0.0.0", "--port", port]
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            command,
            cwd=comfyui_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path.write_text(str(process.pid), encoding="utf-8")
    logger.info("Started ComfyUI pid=%s log=%s", process.pid, log_path)

    timeout_sec = int(os.environ.get("COMFYUI_START_TIMEOUT", "180"))
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if process.poll() is not None:
            tail = read_tail(log_path)
            errors.append(
                f"ComfyUI exited early with code {process.returncode}. Log: {log_path}\n{tail}"
            )
            return errors
        if is_comfyui_reachable(comfyui_url):
            logger.info("ComfyUI is ready: %s", comfyui_url)
            return errors
        time.sleep(2)

    tail = read_tail(log_path)
    errors.append(
        f"ComfyUI did not become reachable within {timeout_sec}s: {comfyui_url}. "
        f"Log: {log_path}\n{tail}"
    )
    return errors


def create_placeholder_image(path: Path, label: str, logger: logging.Logger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (832, 1216), color=(30, 42, 56))
        draw = ImageDraw.Draw(image)
        draw.rectangle((48, 48, 784, 1168), outline=(132, 186, 201), width=4)
        draw.text((80, 90), "AI Short Drama Pipeline", fill=(255, 255, 255))
        draw.text((80, 140), label[:120], fill=(218, 232, 238))
        image.save(path)
        logger.info("Created placeholder image: %s", path)
    except Exception as exc:
        logger.exception("Failed to create placeholder image: %s", path)
        raise RuntimeError(f"Failed to create placeholder image {path}: {exc}") from exc


def create_test_video(path: Path, duration: int, fps: int, logger: logging.Logger) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg is not available. On RunPod run: apt-get update && apt-get install -y ffmpeg"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    drawtext = (
        "drawtext=text='FFMPEG LINK TEST - NOT AI VIDEO':"
        "fontcolor=white:fontsize=48:x=(w-text_w)/2:y=120,"
        "drawtext=text='Only verifies output path and mp4 writing':"
        "fontcolor=white:fontsize=34:x=(w-text_w)/2:y=190"
    )
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=1080x1920:rate={fps}:duration={duration}",
        "-vf",
        drawtext,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    logger.info("Running ffmpeg test video command: %s", " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout:
        logger.info("ffmpeg stdout: %s", result.stdout[-2000:])
    if result.stderr:
        logger.info("ffmpeg stderr: %s", result.stderr[-4000:])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}: {result.stderr[-1000:]}")
    logger.info("Created test video: %s", path)


def generate_test_assets(
    rows: list[dict[str, str | int]],
    duration: int,
    fps: int,
    logger: logging.Logger,
) -> list[str]:
    created: list[str] = []
    for row in rows:
        image_path = resolve_output_path(str(row["output_image"]))
        video_path = resolve_output_path(str(row["output_video"]))
        label = f"{row['shot_id']} seed={row['seed']} motion={row['motion_level']}"
        create_placeholder_image(image_path, label, logger)
        create_test_video(video_path, duration, fps, logger)
        row["status"] = "done"
        created.append(str(video_path.relative_to(ROOT)) if video_path.is_relative_to(ROOT) else str(video_path))
    return created


def validate_real_generation_config(project_config: dict, logger: logging.Logger) -> list[str]:
    errors: list[str] = []
    image_gen = project_config.get("image_gen", {}) or {}
    video_gen = project_config.get("video_gen", {}) or {}

    comfyui_url = str(image_gen.get("comfyui_url", "")).strip()
    workflow_path_raw = str(image_gen.get("workflow_path", "input/config/comfyui_workflow_api.json")).strip()
    workflow_path = resolve_user_path(workflow_path_raw, ROOT / "input" / "config" / "comfyui_workflow_api.json")
    hunyuan_root_raw = str(video_gen.get("hunyuan_root", "")).strip()
    hunyuan_ckpt_raw = str(video_gen.get("hunyuan_ckpt", "")).strip()
    hunyuan_root = Path(hunyuan_root_raw) if hunyuan_root_raw else None
    hunyuan_ckpt = Path(hunyuan_ckpt_raw) if hunyuan_ckpt_raw else None

    if not comfyui_url or "${" in comfyui_url:
        errors.append("COMFYUI_URL is not configured; cannot generate FLUX/SDXL keyframes.")
    else:
        errors.extend(start_comfyui_if_needed(comfyui_url, logger))
    if not workflow_path.exists():
        errors.append(f"ComfyUI API workflow does not exist: {workflow_path}")
    if not hunyuan_root or not hunyuan_root.exists():
        errors.append(f"HUNYUAN_ROOT does not exist: {hunyuan_root_raw or '<empty>'}")
    elif not (hunyuan_root / "sample_image2video.py").exists():
        errors.append(f"HUNYUAN_ROOT does not contain sample_image2video.py: {hunyuan_root}")
    if not hunyuan_ckpt or not hunyuan_ckpt.exists():
        errors.append(f"HUNYUAN_CKPT does not exist: {hunyuan_ckpt_raw or '<empty>'}")
    elif not any(item.is_file() or item.is_symlink() for item in hunyuan_ckpt.rglob("*")):
        errors.append(f"HUNYUAN_CKPT exists but appears empty: {hunyuan_ckpt}")

    if errors:
        logger.error("Real generation config check failed: %s", " | ".join(errors))
    return errors


def run_pipeline_step(command: list[str], timeout_sec: int, logger: logging.Logger) -> tuple[bool, str]:
    logger.info("Running pipeline command: %s", " ".join(command))
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout_sec, check=False)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    if output:
        logger.info("Pipeline command output:\n%s", output[-12000:])
    if result.returncode != 0:
        return False, f"Command failed exit={result.returncode}: {' '.join(command)}\n{output[-4000:]}"
    return True, output[-4000:]


def collect_generated_videos(prompt_csv: Path) -> list[str]:
    videos: list[str] = []
    with prompt_csv.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            output_video = resolve_output_path(row.get("output_video", ""))
            if output_video.exists():
                videos.append(str(output_video.relative_to(ROOT)) if output_video.is_relative_to(ROOT) else str(output_video))
    return videos


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


@app.get("/api/config")
def config() -> dict:
    project_config = load_project_config(ROOT / "input" / "config" / "project.yaml")
    return {
        "project": project_config.get("project_name", "ai_short_drama"),
        "style": project_config.get("style", "cinematic_realism"),
        "default_seeds": project_config.get("video_gen", {}).get("seeds", [1001, 1002, 1003]),
        "default_motion_levels": project_config.get("video_gen", {}).get("motion_levels", ["low", "medium"]),
        "default_duration": project_config.get("video_gen", {}).get("duration_sec", 4),
        "default_fps": project_config.get("video_gen", {}).get("fps", 24),
        "default_novel_text": DEFAULT_NOVEL_TEXT,
        "default_base_prompt": DEFAULT_BASE_PROMPT,
        "default_negative_prompt": DEFAULT_NEGATIVE_PROMPT,
        "default_output_dir": "outputs/jobs/test_ep01",
        "default_mode": "real_generation",
        "default_generation_target": "image_and_video",
    }


@app.post("/api/generate")
async def generate(
    episode_id: Annotated[str, Form()] = "ep01",
    novel_text: Annotated[str, Form()] = "",
    base_prompt: Annotated[str, Form()] = "",
    negative_prompt: Annotated[str, Form()] = "",
    output_dir: Annotated[str, Form()] = "outputs/jobs",
    seeds: Annotated[str, Form()] = "1001,1002,1003",
    motion_levels: Annotated[str, Form()] = "low,medium",
    duration: Annotated[int, Form()] = 4,
    fps: Annotated[int, Form()] = 24,
    mode: Annotated[str, Form()] = "create_tasks",
    generation_target: Annotated[str, Form()] = "image_and_video",
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> JSONResponse:
    episode_id = clean_id(episode_id, "ep01")
    job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{episode_id}"
    logger = setup_logger(job_id)
    logger.info(
        "Visual generate request received mode=%s target=%s episode=%s",
        mode,
        generation_target,
        episode_id,
    )

    project_config = load_project_config(ROOT / "input" / "config" / "project.yaml")
    negative_prompt = negative_prompt.strip() or DEFAULT_NEGATIVE_PROMPT
    base_prompt = base_prompt.strip() or DEFAULT_BASE_PROMPT
    novel_text = novel_text.strip() or DEFAULT_NOVEL_TEXT

    selected_seeds = parse_int_list(seeds, project_config.get("video_gen", {}).get("seeds", [1001]))
    selected_motion_levels = parse_csv_list(motion_levels) or project_config.get("video_gen", {}).get("motion_levels", ["low"])
    target_output_dir = resolve_user_path(output_dir, ROOT / "outputs" / "jobs" / job_id)
    job_dir = JOBS_DIR / job_id
    upload_dir = REFERENCE_DIR / job_id

    job_dir.mkdir(parents=True, exist_ok=True)
    target_output_dir.mkdir(parents=True, exist_ok=True)

    novel_path = ROOT / "input" / "novel" / f"{episode_id}_{job_id}.txt"
    novel_path.write_text(novel_text, encoding="utf-8")

    saved_images = await save_uploads(images or [], upload_dir)
    prompt_csv = PROMPTS_DIR / f"{episode_id}_{job_id}_prompts.csv"
    rows = write_prompt_csv(
        prompt_csv,
        episode_id=episode_id,
        prompt=base_prompt,
        negative_prompt=negative_prompt,
        output_dir=target_output_dir,
        duration=duration,
        seeds=selected_seeds,
        motion_levels=selected_motion_levels,
    )
    task_count = len(rows)
    logger.info("Prompt CSV created: %s rows=%s", prompt_csv, task_count)

    generated_videos: list[str] = []
    errors: list[str] = []
    if mode == "generate_test_video":
        try:
            logger.info("Generating ffmpeg link-test assets for %s rows. These are NOT AI results.", task_count)
            generated_videos = generate_test_assets(rows, duration, fps, logger)
            save_prompt_rows(prompt_csv, rows)
        except Exception as exc:
            logger.exception("Test video generation failed")
            errors.append(str(exc))
    elif mode == "real_generation":
        if generation_target not in {"image_and_video", "image_only", "video_only"}:
            errors.append(f"Unknown generation_target: {generation_target}")
        errors.extend(validate_real_generation_config(project_config, logger))
        if not errors:
            timeout_sec = int((project_config.get("pipeline", {}) or {}).get("real_generation_timeout_sec", 7200))
            image_command = [
                sys.executable,
                str(ROOT / "scripts" / "05_batch_image_gen.py"),
                "--config",
                str(ROOT / "input" / "config" / "project.yaml"),
                "--prompt-csv",
                str(prompt_csv),
                "--episode",
                episode_id,
            ]
            video_command = [
                sys.executable,
                str(ROOT / "scripts" / "06_batch_video_gen.py"),
                "--config",
                str(ROOT / "input" / "config" / "project.yaml"),
                "--prompt-csv",
                str(prompt_csv),
                "--episode",
                episode_id,
            ]
            if generation_target in {"image_and_video", "image_only"}:
                ok, message = run_pipeline_step(image_command, timeout_sec, logger)
                if not ok:
                    errors.append(message)
            if not errors and generation_target in {"image_and_video", "video_only"}:
                ok, message = run_pipeline_step(video_command, timeout_sec, logger)
                if not ok:
                    errors.append(message)
            generated_videos = collect_generated_videos(prompt_csv)
    else:
        logger.info("Mode %s does not run video generation; only task files were created", mode)

    manifest = {
        "job_id": job_id,
        "mode": mode,
        "generation_target": generation_target,
        "episode_id": episode_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "novel_path": str(novel_path.relative_to(ROOT)),
        "prompt_csv": str(prompt_csv.relative_to(ROOT)),
        "output_dir": str(target_output_dir.relative_to(ROOT)) if target_output_dir.is_relative_to(ROOT) else str(target_output_dir),
        "reference_images": saved_images,
        "duration": duration,
        "fps": fps,
        "seeds": selected_seeds,
        "motion_levels": selected_motion_levels,
        "task_count": task_count,
        "status": "done" if generated_videos and not errors else "ready" if not errors else "failed",
        "generated_videos": generated_videos,
        "errors": errors,
        "next_steps": [
            f"python scripts/05_batch_image_gen.py --episode {episode_id}",
            f"python scripts/06_batch_video_gen.py --episode {episode_id}",
            f"python scripts/07_score_videos.py --episode {episode_id}",
            f"python scripts/10_assemble_episode.py --episode {episode_id}",
        ],
    }
    manifest_path = job_dir / "job_config.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(
        "Created manifest=%s prompt_csv=%s task_count=%s generated_videos=%s errors=%s",
        manifest_path,
        prompt_csv,
        task_count,
        len(generated_videos),
        len(errors),
    )
    if generated_videos and not errors and mode == "real_generation":
        message = "真实 AI 视频已生成。"
    elif generated_videos and not errors:
        message = "链路测试视频已生成，注意它不是 AI 结果。"
    else:
        message = "任务已创建，但未生成真实视频；请查看 errors 和日志。"

    return JSONResponse(
        {
            "ok": not errors,
            "message": message,
            "job": manifest,
            "manifest_path": str(manifest_path.relative_to(ROOT)),
        },
        status_code=200 if not errors else 500,
    )


HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Short Drama Pipeline</title>
  <style>
    :root {
      --bg: #f4f5f7;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #697586;
      --line: #d9dee7;
      --accent: #256d85;
      --accent-dark: #1f596e;
      --ok: #1b7f4d;
      --warn: #9a5b12;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    header h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }
    header span {
      font-size: 13px;
      color: var(--muted);
    }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 1.2fr) minmax(320px, 0.8fr);
      gap: 16px;
      padding: 16px;
      max-width: 1440px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }
    textarea {
      min-height: 130px;
      resize: vertical;
      line-height: 1.45;
    }
    .wide { grid-column: 1 / -1; }
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 14px;
    }
    button {
      border: 0;
      border-radius: 6px;
      padding: 11px 16px;
      background: var(--accent);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    button:disabled { opacity: 0.55; cursor: wait; }
    .status {
      min-height: 22px;
      color: var(--muted);
      font-size: 13px;
    }
    .result {
      white-space: pre-wrap;
      font-family: Consolas, monospace;
      font-size: 12px;
      line-height: 1.55;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      min-height: 300px;
      overflow: auto;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      background: #eaf3f6;
      color: var(--accent-dark);
      font-size: 12px;
      margin-right: 6px;
      margin-bottom: 6px;
    }
    .note {
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    @media (max-width: 900px) {
      header { padding: 0 14px; }
      main { grid-template-columns: 1fr; padding: 12px; }
      .grid { grid-template-columns: 1fr; }
      .wide { grid-column: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>AI Short Drama Pipeline</h1>
    <span id="runtime">loading</span>
  </header>
  <main>
    <section>
      <h2>生成任务</h2>
      <form id="generateForm">
        <div class="grid">
          <div>
            <label for="episode_id">集编号</label>
            <input id="episode_id" name="episode_id" value="ep01" />
          </div>
          <div>
            <label for="mode">模式</label>
            <select id="mode" name="mode">
              <option value="real_generation">真实 AI 生成</option>
              <option value="create_tasks">只创建真实生成任务</option>
              <option value="generate_test_video">链路测试视频（非AI）</option>
              <option value="dry_run">只生成配置</option>
            </select>
          </div>
          <div>
            <label for="generation_target">生成内容</label>
            <select id="generation_target" name="generation_target">
              <option value="image_and_video">关键帧 + 视频</option>
              <option value="image_only">只生成关键帧</option>
              <option value="video_only">只生成视频</option>
            </select>
          </div>
          <div class="wide">
            <label for="novel_text">小说 / 剧情文本</label>
            <textarea id="novel_text" name="novel_text" placeholder="粘贴小说章节、剧情梗概或本集文本">苏晚在深夜的医院病房中醒来，窗外暴雨敲打玻璃。她看见床头的旧手机，日期竟然回到了三年前。上一世她被最信任的人背叛，这一次她决定改变命运。门外传来脚步声，那个曾经害她失去一切的男人即将推门而入。</textarea>
          </div>
          <div class="wide">
            <label for="base_prompt">正向 Prompt</label>
            <textarea id="base_prompt" name="base_prompt" placeholder="角色、场景、镜头、风格、质量词等，可先写一版总提示词">young Chinese woman, 24 years old, long black wavy hair, pale skin, almond eyes, wearing a white shirt and black blazer, lying on a hospital bed at night, modern private hospital room, cold white fluorescent light, rain on window glass, IV stand beside the bed, tense dramatic atmosphere, she slowly opens her eyes and looks shocked, cinematic realism, realistic lighting, highly detailed, vertical composition, film still</textarea>
          </div>
          <div class="wide">
            <label for="negative_prompt">负向 Prompt</label>
            <textarea id="negative_prompt" name="negative_prompt">blurry, low quality, distorted face, extra fingers, bad hands, duplicated body, inconsistent clothing, low resolution, watermark, text, logo, deformed body, wrong anatomy, cartoon, anime</textarea>
          </div>
          <div>
            <label for="seeds">Seeds</label>
            <input id="seeds" name="seeds" value="1001,1002,1003" />
          </div>
          <div>
            <label for="motion_levels">运动强度</label>
            <input id="motion_levels" name="motion_levels" value="low,medium" />
          </div>
          <div>
            <label for="duration">镜头时长 / 秒</label>
            <input id="duration" name="duration" type="number" min="1" max="30" value="4" />
          </div>
          <div>
            <label for="fps">FPS</label>
            <input id="fps" name="fps" type="number" min="1" max="120" value="24" />
          </div>
          <div class="wide">
            <label for="output_dir">输出路径</label>
            <input id="output_dir" name="output_dir" value="outputs/jobs/test_ep01" />
          </div>
          <div class="wide">
            <label for="images">参考图 / 角色图 / 场景图</label>
            <input id="images" name="images" type="file" accept="image/*" multiple />
          </div>
        </div>
        <div class="actions">
          <button id="submitBtn" type="submit">生成</button>
          <div class="status" id="status">等待输入</div>
        </div>
      </form>
    </section>

    <section>
      <h2>任务输出</h2>
      <div>
        <span class="pill">小说输入</span>
        <span class="pill">参考图保存</span>
        <span class="pill">Prompt CSV</span>
        <span class="pill">Job JSON</span>
        <span class="pill">测试 MP4 非AI</span>
      </div>
      <p class="note">默认会尝试真实 AI 生成：先调用 ComfyUI 生成关键帧，再调用 HunyuanVideo 生成视频。链路测试 MP4 只验证路径和写文件，不代表 AI 画面。</p>
      <div id="result" class="result">暂无任务</div>
    </section>
  </main>

  <script>
    const form = document.getElementById("generateForm");
    const statusBox = document.getElementById("status");
    const resultBox = document.getElementById("result");
    const submitBtn = document.getElementById("submitBtn");

    async function loadConfig() {
      const res = await fetch("/api/config");
      const cfg = await res.json();
      document.getElementById("runtime").textContent = `${cfg.project} · ${cfg.style}`;
      document.getElementById("seeds").value = cfg.default_seeds.join(",");
      document.getElementById("motion_levels").value = cfg.default_motion_levels.join(",");
      document.getElementById("duration").value = cfg.default_duration;
      document.getElementById("fps").value = cfg.default_fps;
      document.getElementById("novel_text").value = cfg.default_novel_text;
      document.getElementById("base_prompt").value = cfg.default_base_prompt;
      document.getElementById("negative_prompt").value = cfg.default_negative_prompt;
      document.getElementById("output_dir").value = cfg.default_output_dir;
      document.getElementById("mode").value = cfg.default_mode;
      document.getElementById("generation_target").value = cfg.default_generation_target;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submitBtn.disabled = true;
      statusBox.textContent = "正在创建任务...";
      resultBox.textContent = "";
      try {
        const data = new FormData(form);
        const res = await fetch("/api/generate", { method: "POST", body: data });
        const payload = await res.json();
        resultBox.textContent = JSON.stringify(payload, null, 2);
        if (!res.ok || !payload.ok) {
          statusBox.textContent = "未生成真实视频，请查看右侧 errors";
          return;
        }
        statusBox.textContent = payload.job.generated_videos?.length ? payload.message : "任务已创建";
      } catch (error) {
        statusBox.textContent = "生成失败";
        resultBox.textContent = String(error);
      } finally {
        submitBtn.disabled = false;
      }
    });

    loadConfig().catch(() => {
      document.getElementById("runtime").textContent = "config unavailable";
    });
  </script>
</body>
</html>
"""
