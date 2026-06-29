# AI Short Drama Pipeline - RunPod Linux 部署说明

本项目用于在 RunPod Linux 主机上搭建小说转 AI 短剧 / 动画素材流水线。

当前 README 只面向 RunPod / Ubuntu / Linux 主机环境。

目标 MVP 流程：

```text
小说章节 -> 剧本 JSON -> 分镜 JSON -> 提示词 CSV -> ComfyUI 关键帧 -> HunyuanVideo 视频 -> 人工选片 -> ffmpeg 粗剪
```

## 1. RunPod 推荐环境

建议使用 RunPod GPU Pod，并挂载 Network Volume 保存模型、ComfyUI、HunyuanVideo 和输出文件。

最低建议：

| 用途 | GPU | 磁盘 / Volume |
| --- | --- | --- |
| MVP 测试 | RTX 3090 / RTX 4090 24GB | Container Disk 80GB，Network Volume 200GB+ |
| 批量生成 | RTX A6000 / L40S / A40 48GB | Container Disk 100GB+，Network Volume 500GB+ |
| 更高质量 / 更长视频 | A100 / H100 80GB | Container Disk 150GB+，Network Volume 1TB+ |

推荐目录：

```text
/workspace/aiVideoWorkFlow        本项目
/workspace/ComfyUI                ComfyUI
/workspace/HunyuanVideo-I2V       HunyuanVideo-I2V
/models/hunyuan/ckpts             HunyuanVideo 权重
```

## 2. 创建 Pod

RunPod Pod 建议配置：

| 项目 | 建议值 |
| --- | --- |
| 镜像 | RunPod PyTorch / CUDA / Ubuntu 类镜像 |
| HTTP Port | `7860` |
| ComfyUI Port | `8188`，内部访问即可 |
| Volume Mount | `/workspace` 和 `/models` |
| Python | Python 3.10+ |
| 系统依赖 | `git`、`git-lfs`、`ffmpeg`、`python3-venv`、`build-essential` |

如果是空白 RunPod 主机，后面的 `--runpod-full` 会自动安装常见系统依赖、Python 依赖、ComfyUI、HunyuanVideo-I2V，并尝试下载模型。

## 3. 获取项目

在 RunPod Web Terminal 或 SSH 中执行：

```bash
cd /workspace
git clone <your-repo-url> aiVideoWorkFlow
cd /workspace/aiVideoWorkFlow
chmod +x start_visual.sh scripts/linux/*.sh
```

如果项目已经存在：

```bash
cd /workspace/aiVideoWorkFlow
git pull --ff-only
chmod +x start_visual.sh scripts/linux/*.sh
```

如果不用 git，也可以把项目压缩成 zip 后上传到 RunPod。建议在打包时排除临时文件、输出文件、模型权重和虚拟环境：

```bash
zip -r aiVideoWorkFlow.zip aiVideoWorkFlow \
  -x "aiVideoWorkFlow/.git/*" \
  -x "aiVideoWorkFlow/.env" \
  -x "aiVideoWorkFlow/.venv/*" \
  -x "aiVideoWorkFlow/models/*" \
  -x "aiVideoWorkFlow/outputs/*" \
  -x "aiVideoWorkFlow/logs/*" \
  -x "aiVideoWorkFlow/temp/*" \
  -x "aiVideoWorkFlow/**/__pycache__/*"
```

把 `aiVideoWorkFlow.zip` 上传到 RunPod 的 `/workspace` 后，在 Linux 主机上解压：

```bash
cd /workspace
apt-get update && apt-get install -y unzip
unzip aiVideoWorkFlow.zip
cd /workspace/aiVideoWorkFlow
chmod +x start_visual.sh scripts/linux/*.sh
```

如果 zip 解压后多了一层目录，例如 `/workspace/aiVideoWorkFlow-main/aiVideoWorkFlow`，可以移动成推荐目录：

```bash
cd /workspace
mv aiVideoWorkFlow-main/aiVideoWorkFlow ./aiVideoWorkFlow
cd /workspace/aiVideoWorkFlow
chmod +x start_visual.sh scripts/linux/*.sh
```

如果目标目录已经存在，先改名备份，不要直接覆盖已有输出：

```bash
cd /workspace
mv aiVideoWorkFlow aiVideoWorkFlow_backup_$(date +%Y%m%d_%H%M%S)
unzip aiVideoWorkFlow.zip
cd /workspace/aiVideoWorkFlow
chmod +x start_visual.sh scripts/linux/*.sh
```

## 4. 配置环境变量

首次运行脚本会从 `.env.example` 创建 `.env`。也可以手动创建：

```bash
cp .env.example .env
```

RunPod Linux 推荐配置：

```bash
APP_PORT=7860
OPENAI_API_KEY=
HF_TOKEN=

COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_DIR=/workspace/ComfyUI
COMFYUI_PYTHON_BIN=/usr/bin/python3
COMFYUI_TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
COMFYUI_TORCH_PACKAGES="torch torchvision torchaudio"
COMFYUI_NUMPY_PACKAGE="numpy>=1.26,<3"
COMFYUI_EXTRA_PIP_PACKAGES="SQLAlchemy alembic blake3 tqdm GitPython toml"

MODEL_DIR=/models
HUNYUAN_ROOT=/workspace/HunyuanVideo-I2V
HUNYUAN_CKPT=/models/hunyuan/ckpts
```

如果 Hugging Face 模型需要授权，把 token 写入 `.env` 的 `HF_TOKEN`，不要提交到 git。

## 5. 准备 ComfyUI API Workflow

真实图片生成需要 ComfyUI API 格式 workflow：

```text
input/config/comfyui_workflow_api.json
```

这个文件必须是从 ComfyUI 导出的真实 API workflow，不能使用 `input/config/comfyui_workflow_api.example.json`，也不能使用脚本自动创建的 placeholder JSON。否则提交到 ComfyUI `/prompt` 时会失败。

workflow 中应包含这些占位符，脚本会在生成时替换：

```text
__PROMPT__
__NEGATIVE_PROMPT__
__SEED__
__WIDTH__
__HEIGHT__
__OUTPUT_PREFIX__
```

如果已有 workflow 文件，例如 `/workspace/workflows/your_comfyui_workflow_api.json`，启动时传入：

```bash
./start_visual.sh --workflow /workspace/workflows/your_comfyui_workflow_api.json --port 7860
```

也可以从 URL 下载：

```bash
./start_visual.sh --workflow-url https://example.com/comfyui_workflow_api.json --port 7860
```

快速检查 workflow 是否还是占位文件：

```bash
cd /workspace/ai-video-workflow
grep -n '"note"\|"placeholders"' input/config/comfyui_workflow_api.json
```

如果有输出，说明还不是可用于生成的真实 ComfyUI API workflow。

## 6. 一键部署空白 RunPod

空白 RunPod 首次部署：

```bash
cd /workspace/aiVideoWorkFlow
chmod +x start_visual.sh scripts/linux/*.sh
./start_visual.sh \
  --runpod-full \
  --workflow /workspace/workflows/your_comfyui_workflow_api.json \
  --port 7860
```

注意：`--workflow` 后面的文件必须已经存在。如果还没有 ComfyUI API workflow，先不要传 `--workflow` 参数，等 ComfyUI 启动后导出真实 workflow 再补。

`--runpod-full` 会执行：

- 安装 Ubuntu 常见依赖。
- 创建 Python 虚拟环境并安装 `requirements.txt`。
- 准备 ComfyUI 和 ComfyUI-Manager。
- 准备 HunyuanVideo-I2V。
- 下载或复用 HunyuanVideo 模型权重。
- 启动 ComfyUI 后台服务。
- 检查真实生成依赖。
- 启动本项目 Web 页面。

已有模型和代码目录时，脚本默认会复用，不会强制覆盖或删除历史输出。

## 7. 只安装代码，不下载大模型

如果想先检查链路，不下载 HunyuanVideo 权重：

```bash
./start_visual.sh \
  --setup-real-gen \
  --no-model \
  --workflow /workspace/workflows/your_comfyui_workflow_api.json \
  --port 7860
```

之后手动准备权重，再执行检查：

```bash
python scripts/check_real_generation.py
```

## 8. 复用已有 ComfyUI / HunyuanVideo

如果 RunPod Volume 里已经有 ComfyUI、HunyuanVideo 和模型：

```bash
./start_visual.sh \
  --port 7860 \
  --comfyui-url http://127.0.0.1:8188 \
  --comfyui-dir /workspace/ComfyUI \
  --hunyuan-root /workspace/HunyuanVideo-I2V \
  --hunyuan-ckpt /models/hunyuan/ckpts \
  --workflow /workspace/workflows/your_comfyui_workflow_api.json
```

如果 ComfyUI 已经由别的进程启动，只要保证 `COMFYUI_URL` 可访问即可。

## 9. 启动 Web 页面

常规启动：

```bash
./start_visual.sh --port 7860
```

RunPod 控制台里打开 HTTP Service 对应的 `7860` 端口。

启动后页面会写入这些文件：

```text
input/novel/{episode}_{job_id}.txt
assets/references/{job_id}/
data/prompts/{episode}_{job_id}_prompts.csv
data/jobs/{job_id}/job_config.json
outputs/images/
outputs/videos/raw/
logs/{job_id}_visual_generate.log
```

## 10. 真实生成检查

只检查依赖，不启动页面：

```bash
./start_visual.sh --check-only
```

或直接执行：

```bash
python scripts/check_real_generation.py
```

检查项包括：

- `COMFYUI_URL` 是否可访问。
- `input/config/comfyui_workflow_api.json` 是否存在。
- `HUNYUAN_ROOT` 是否存在并包含 `sample_image2video.py`。
- `HUNYUAN_CKPT` 是否存在且包含权重文件。

## 11. 单镜头调试

生成提示词：

```bash
python scripts/04_generate_prompts.py --episode ep01 --overwrite
```

只生成一条关键帧任务：

```bash
python scripts/05_batch_image_gen.py \
  --episode ep01 \
  --prompt-csv data/prompts/ep01_prompts.csv \
  --limit 1
```

只生成一条视频任务：

```bash
python scripts/06_batch_video_gen.py \
  --episode ep01 \
  --prompt-csv data/prompts/ep01_prompts.csv \
  --limit 1
```

指定镜头 dry-run，检查命令但不生成：

```bash
python scripts/06_batch_video_gen.py \
  --episode ep01 \
  --shot ep01_sc01_sh01 \
  --dry-run
```

## 12. MVP 命令行流程

```bash
python scripts/01_novel_to_script.py --episode ep01 --overwrite
python scripts/02_script_to_storyboard.py --episode ep01 --overwrite
python scripts/03_generate_character_cards.py --episode ep01
python scripts/04_generate_prompts.py --episode ep01 --overwrite
python scripts/05_batch_image_gen.py --episode ep01
python scripts/06_batch_video_gen.py --episode ep01
python scripts/07_score_videos.py --episode ep01
python scripts/10_assemble_episode.py --episode ep01
```

如果只是验证流程，可以先使用 `--dry-run`：

```bash
python scripts/05_batch_image_gen.py --episode ep01 --dry-run --limit 1
python scripts/06_batch_video_gen.py --episode ep01 --dry-run --limit 1
```

## 13. 重要配置文件

主配置：

```text
input/config/project.yaml
```

关键字段：

- `image_gen.comfyui_url`：ComfyUI 地址，默认从 `COMFYUI_URL` 读取。
- `image_gen.workflow_path`：ComfyUI API workflow。
- `video_gen.hunyuan_root`：HunyuanVideo-I2V 代码目录。
- `video_gen.hunyuan_ckpt`：HunyuanVideo 权重目录。
- `video_gen.command_template`：视频生成命令模板。
- `video_gen.seeds`：候选 seed 列表。
- `video_gen.motion_levels`：候选运动强度列表。

修改模型路径、分辨率、seed、时长时，优先改 `project.yaml` 或 `.env`，不要改脚本里的硬编码。

## 14. 日志

主要日志位置：

```text
logs/comfyui.log
logs/{job_id}_visual_generate.log
logs/*_batch_video_gen.log
```

查看 ComfyUI 日志：

```bash
tail -n 100 logs/comfyui.log
```

查看最近日志：

```bash
ls -lt logs | head
```

## 15. 常见故障

### ComfyUI 启动很久

首次启动会安装依赖、加载模型和扫描节点，先看日志：

```bash
tail -n 100 logs/comfyui.log
```

### `COMFYUI_URL` 不可访问

确认 ComfyUI 在 8188 端口：

```bash
curl http://127.0.0.1:8188/system_stats
```

如果失败，可让启动脚本拉起 ComfyUI：

```bash
./start_visual.sh --start-comfyui --port 7860
```

### 缺少 ComfyUI workflow

把 ComfyUI 导出的 API workflow 放到：

```text
input/config/comfyui_workflow_api.json
```

或启动时传入：

```bash
./start_visual.sh --workflow /workspace/workflows/your_comfyui_workflow_api.json --port 7860
```

### HunyuanVideo 路径不对

显式传入路径：

```bash
./start_visual.sh \
  --hunyuan-root /workspace/HunyuanVideo-I2V \
  --hunyuan-ckpt /models/hunyuan/ckpts \
  --port 7860
```

### 模型下载中断

复用相同目录重新运行即可。需要强制下载或续传时：

```bash
./start_visual.sh \
  --runpod-full \
  --workflow /workspace/workflows/your_comfyui_workflow_api.json \
  --force-model-download \
  --port 7860
```

### PyTorch CUDA wheel 与驱动不匹配

默认使用 CUDA 12.4 wheel：

```bash
COMFYUI_TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
```

如 RunPod 镜像驱动不同，在 `.env` 中改 `COMFYUI_TORCH_INDEX_URL`，再重新启动。

### HunyuanVideo 依赖冲突

`scripts/linux/setup_hunyuan_i2v.sh` 会跳过旧的 `tokenizers==0.15.0` 固定版本，让 `transformers` 安装匹配版本。仍失败时，优先查看 pip 报错和 HunyuanVideo 当前 requirements。

### 显存不足

先降低这些配置：

- `input/config/project.yaml` 中的 `image_gen.width`、`image_gen.height`。
- `video_gen.resolution`。
- `video_gen.video_length`。
- 单次生成数量和 `--limit`。

必要时换 48GB 或 80GB GPU。

## 16. 停止服务

前台运行时按：

```text
Ctrl+C
```

如果 ComfyUI 由脚本后台启动，可以查看 PID：

```bash
cat temp/comfyui.pid
```

停止 ComfyUI：

```bash
kill "$(cat temp/comfyui.pid)"
```

## 17. 部署原则

- 模型权重放在 `/models` 或 Network Volume，不提交到 git。
- 输出视频和图片保存在 `outputs/`，重要结果及时同步或备份。
- 不在脚本里写死密钥、模型路径或绝对输出路径。
- 大模型下载必须显式触发，避免误占用磁盘和流量。
- 先用 `--check-only` 和 `--dry-run` 跑通链路，再批量生成。
