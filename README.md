# AI Short Drama Pipeline

小说转 AI 短剧 / 动画素材流水线。当前目标是先跑通 MVP：小说章节到剧本、分镜、提示词 CSV、图片/视频任务、人工选片和 ffmpeg 粗剪。

## 目录结构

- `input/novel/`: 小说输入
- `input/config/`: 项目、角色、场景和风格配置
- `data/scripts/`: 剧本 JSON
- `data/storyboards/`: 分镜 JSON
- `data/prompts/`: 提示词 CSV
- `data/dialogue/`: 台词 JSON
- `assets/`: 角色、场景、BGM、音效素材
- `outputs/`: 图片、视频、配音、字幕和最终成片
- `logs/`: 脚本运行日志
- `temp/`: ffmpeg 等中间文件
- `scripts/`: 流水线脚本
- `tools/`: 可复用工具模块

## Docker 环境

推荐用 Docker 统一 Python、ffmpeg、Edge-TTS、OpenAI 客户端、OpenCV 等运行环境。FLUX / SDXL、HunyuanVideo-1.5 和模型权重通常很大，默认通过外部服务或目录挂载接入，不打包进本项目镜像。

## 可视化页面

最终入口是 `start_visual.ps1`。它会完成环境配置、创建挂载目录、构建 Docker 镜像，并启动 Web 页面。

Windows PowerShell：

```bash
.\start_visual.ps1 -Port 7860
```

Linux / RunPod：

```bash
chmod +x start_visual.sh
./start_visual.sh --port 7860
```

完全空白的 RunPod 首次部署，使用一键全量模式：

```bash
chmod +x start_visual.sh scripts/linux/*.sh
./start_visual.sh --runpod-full --port 7860
```

如果已经有 ComfyUI API workflow，建议首次部署时一并传入：

```bash
./start_visual.sh \
  --runpod-full \
  --workflow /workspace/workflows/comfyui_workflow_api.json \
  --port 7860
```

`--runpod-full` 会安装 Ubuntu/RunPod 常见系统依赖、Python 依赖、ComfyUI、ComfyUI-Manager、HunyuanVideo-I2V、Hunyuan 模型权重，并后台启动 ComfyUI 后再启动本项目 Web 页面。ComfyUI 的 FLUX/SDXL 具体模型和 workflow 强相关，如果你的 workflow 需要私有或授权模型，请先通过环境变量、Volume 或手动下载放到 ComfyUI 对应模型目录。

如果 Hugging Face 模型需要授权，直接打开 `start_visual.sh`，把顶部的 `HF_TOKEN_MANUAL=""` 改成你的 token，例如 `HF_TOKEN_MANUAL="hf_xxx"`，然后再运行 `./start_visual.sh --runpod-full --port 7860`。

如果安装 Hunyuan 依赖时报 `tokenizers==0.15.0` 和 `transformers==4.48.0` 冲突，当前 `scripts/linux/setup_hunyuan_i2v.sh` 会自动生成临时兼容版 requirements，跳过旧的 `tokenizers==0.15.0` 固定版本，让 `transformers` 安装匹配的 `tokenizers>=0.21,<0.22`。

如果启动停在 `Starting ComfyUI in background`，通常是在等 ComfyUI 首次加载。可以另开一个终端查看日志：

```bash
tail -n 80 logs/comfyui.log
```

更新后的脚本会每 10 秒打印等待状态，并在超时后自动显示 ComfyUI 日志尾部。

如果 HunyuanVideo、权重或 ComfyUI workflow 不在默认位置，可以启动时直接传入：

```bash
./start_visual.sh \
  --port 7860 \
  --comfyui-url http://127.0.0.1:8188 \
  --workflow /workspace/workflows/comfyui_workflow_api.json \
  --hunyuan-root /workspace/HunyuanVideo-1.5 \
  --hunyuan-ckpt /models/hunyuan/ckpts
```

只检查真实生成依赖，不启动页面：

```bash
./start_visual.sh --check-only
```

首次在 RunPod 准备 ComfyUI + HunyuanVideo-I2V + 模型权重：

```bash
chmod +x start_visual.sh scripts/linux/*.sh
./start_visual.sh \
  --runpod-full \
  --workflow /workspace/workflows/comfyui_workflow_api.json \
  --port 7860
```

如果只想安装代码、不下载大模型：

```bash
./start_visual.sh --setup-real-gen --no-model --workflow /workspace/workflows/comfyui_workflow_api.json
```

也可以单独运行 Linux 下载脚本：

```bash
scripts/linux/setup_comfyui.sh --workflow /workspace/workflows/comfyui_workflow_api.json
scripts/linux/setup_hunyuan_i2v.sh --root /workspace/HunyuanVideo-I2V --ckpt /models/hunyuan/ckpts
scripts/linux/setup_real_generation.sh --workflow /workspace/workflows/comfyui_workflow_api.json
```

打开：

```text
http://localhost:7860
```

换端口：

```bash
.\start_visual.ps1 -Port 8899
./start_visual.sh --port 8899
```

页面可输入小说文本、正向 Prompt、负向 Prompt、参考图片、seed、运动强度、镜头时长、FPS 和输出路径。点击生成后会写入：

- `input/novel/{episode}_{job_id}.txt`
- `assets/references/{job_id}/`
- `data/prompts/{episode}_{job_id}_prompts.csv`
- `data/jobs/{job_id}/job_config.json`
- `logs/{job_id}_visual_generate.log`

注意：当前 Web 页面默认会尝试真实 AI 生成：先调用 ComfyUI 生成关键帧，再调用 HunyuanVideo 生成视频。下拉框里的 **链路测试视频（非AI）** 只用于验证端口、页面、后端、日志、CSV、输出路径和 mp4 写入链路，会生成 `{输出路径}/videos/raw/*.mp4`，但画面不是 AI 结果。

页面里的 **生成内容** 选项：

- `关键帧 + 视频`：先运行 `scripts/05_batch_image_gen.py`，再运行 `scripts/06_batch_video_gen.py`。
- `只生成关键帧`：只调用 ComfyUI / FLUX / SDXL 生成图片。
- `只生成视频`：跳过图片生成，直接读取 CSV 中已有 `output_image` 调 HunyuanVideo 生成视频。

真实 AI 生成前必须准备：

1. 启动 ComfyUI，并确保 `COMFYUI_URL` 可访问，例如 `http://127.0.0.1:8188`。
2. 在 ComfyUI 里导出 API 格式工作流到 `input/config/comfyui_workflow_api.json`。
3. 工作流里用占位符填关键字段：`__PROMPT__`、`__NEGATIVE_PROMPT__`、`__SEED__`、`__WIDTH__`、`__HEIGHT__`、`__OUTPUT_PREFIX__`。
4. 安装或挂载 HunyuanVideo 到 `HUNYUAN_ROOT`。
5. 模型权重放到 `HUNYUAN_CKPT`。
6. 如果你的 HunyuanVideo 启动命令不同，修改 `input/config/project.yaml` 里的 `video_gen.command_template`。

`start_visual.sh` 会自动处理一部分准备工作：

- 自动把 `.env` 里的 `COMFYUI_URL=http://host.docker.internal:8188` 改成 RunPod 常用的 `http://127.0.0.1:8188`。
- 自动探测常见 HunyuanVideo 目录：`/workspace/HunyuanVideo-1.5`、`/workspace/HunyuanVideo-I2V`、`/workspace/HunyuanVideo`。
- 自动探测常见权重目录：`/models/hunyuan/ckpts`、`/workspace/models/hunyuan/ckpts`、Hunyuan 项目内 `ckpts`。
- 使用 `--workflow` 时会把指定 ComfyUI API workflow 复制到 `input/config/comfyui_workflow_api.json`。
- 启动前会运行 `python scripts/check_real_generation.py`，把缺失项打印出来。
- 显式传入 `--runpod-full` 时，会安装系统依赖、准备 ComfyUI、HunyuanVideo-I2V 和模型权重，并后台启动 ComfyUI。
- 显式传入 `--setup-real-gen` 时，会调用 `scripts/linux/setup_real_generation.sh` 准备 ComfyUI、HunyuanVideo-I2V 和模型权重。

它默认不会自动下载 HunyuanVideo 或模型权重，避免误占用大量磁盘和流量。只有显式使用 `--runpod-full`、`--setup-real-gen` 或手动运行 `scripts/linux/setup_hunyuan_i2v.sh` 时才会下载。

真实生成可单独调试：

```bash
python scripts/check_real_generation.py
python scripts/05_batch_image_gen.py --episode ep01 --prompt-csv data/prompts/你的_prompts.csv --limit 1
python scripts/06_batch_video_gen.py --episode ep01 --prompt-csv data/prompts/你的_prompts.csv --limit 1
```

停止页面：

```bash
docker compose stop web
```

一键初始化：

```bash
.\docker_setup.ps1
```

如果只想检查 compose 配置、不构建镜像：

```bash
.\docker_setup.ps1 -NoBuild -NoCheck
```

手动步骤：

```bash
Copy-Item .env.example .env
docker compose build
docker compose run --rm pipeline python --version
docker compose run --rm pipeline ffmpeg -version
```

进入容器：

```bash
docker compose run --rm pipeline
```

在容器中运行单步脚本：

```bash
docker compose run --rm pipeline python scripts/04_generate_prompts.py --episode ep01
docker compose run --rm pipeline python scripts/06_batch_video_gen.py --episode ep01 --shot ep01_sc01_sh01 --dry-run
```

默认挂载：

- 项目目录挂载到 `/app`
- 主机 `./models` 挂载到容器 `/models`
- 主机 `./external/HunyuanVideo-1.5` 挂载到容器 `/workspace/HunyuanVideo-1.5`
- ComfyUI 默认地址是 `http://host.docker.internal:8188`

## RunPod 服务器配置推荐

RunPod 上建议用 **Pod + Docker 镜像 + Network Volume** 的方式部署。RunPod 官方 Pod Template 支持配置容器镜像、硬件规格、容器磁盘、Volume、端口、环境变量和启动命令；环境变量适合放 `OPENAI_API_KEY`、`COMFYUI_URL`、`HUNYUAN_ROOT`、`HUNYUAN_CKPT` 这类配置，不要写进代码或镜像。

> 说明：GPU 库存和价格变化很快，创建 Pod 前以 RunPod 当前 Pricing 页面为准。HunyuanVideo-1.5 官方要求 NVIDIA CUDA GPU，开启模型 offload 时最低约 14GB VRAM；实际批量生产建议至少 24GB VRAM，追求速度和稳定性建议 48GB-80GB。

### 推荐档位

| 档位 | 推荐 GPU | 适合用途 | 建议配置 |
| --- | --- | --- | --- |
| MVP 测试 | RTX 4090 24GB / RTX 3090 24GB | ComfyUI、FLUX/SDXL 关键帧、小批量 HunyuanVideo-1.5 I2V 测试 | 8-16 vCPU，48-64GB RAM，Container Disk 40-80GB，Network Volume 150-300GB |
| 批量生产 | RTX A6000 48GB / L40S 48GB / A40 48GB | 多 seed、多 motion level 批量生成，减少 OOM 和重跑 | 16-24 vCPU，96-128GB RAM，Container Disk 80-120GB，Network Volume 300-800GB |
| 高质量/长视频 | A100 80GB / H100 80GB | 更高分辨率、更长时长、更高吞吐、后续训练或 LoRA | 24-32 vCPU，128-256GB RAM，Container Disk 120-200GB，Network Volume 800GB-2TB |

### 本项目首选配置

当前项目阶段推荐从 **RTX 4090 24GB + 64GB RAM + 300GB Network Volume** 起步：

- 先跑通 MVP：小说输入、prompt CSV、关键帧任务、HunyuanVideo dry-run、ffmpeg 粗剪。
- 图片生成和视频生成分开跑，避免一个容器里同时占满显存。
- HunyuanVideo-1.5 如果 OOM，先降低分辨率、时长、batch、候选数量，或启用 offload。
- 批量任务稳定后再升级到 48GB 或 80GB GPU。

### Pod Template 建议

| 项目 | 建议值 |
| --- | --- |
| Container Image | 先用本项目 Dockerfile 构建的镜像；或基于 RunPod PyTorch/CUDA 模板后拉取本仓库 |
| HTTP Port | `7860`，对应 `start_visual.ps1 -Port 7860` |
| TCP/SSH | 按需开启，生产时尽量只开放必要端口 |
| Container Disk | 80GB 起步，放系统依赖、Python 包、临时构建缓存 |
| Network Volume Mount | `/workspace` 或 `/models` |
| 模型目录 | `/models` |
| HunyuanVideo 目录 | `/workspace/HunyuanVideo-1.5` |
| 输出目录 | `/app/outputs` 或挂载到 Volume 的 `/workspace/outputs` |

### 环境变量

```bash
APP_PORT=7860
OPENAI_API_KEY=
COMFYUI_URL=http://127.0.0.1:8188
MODEL_DIR=/models
HUNYUAN_ROOT=/workspace/HunyuanVideo-1.5
HUNYUAN_CKPT=/models/hunyuan/ckpts
```

### RunPod 启动流程

1. 创建 Network Volume，建议与目标 GPU 选择同一区域。
2. 创建 GPU Pod，优先选择 24GB 以上显存。
3. 选择自定义 Docker 镜像，或使用 PyTorch/CUDA 模板后克隆本项目。
4. 挂载 Volume 到 `/models` 和 `/workspace`，模型权重不要放进 git。
5. 配置环境变量和 HTTP 端口 `7860`。
6. 启动后进入容器运行：

```bash
chmod +x start_visual.sh scripts/linux/*.sh
./start_visual.sh --runpod-full --port 7860
```

后续 Pod 已经复用同一个 Network Volume、有模型缓存时，可以只启动页面：

```bash
./start_visual.sh --port 7860
```

如果使用本项目 Docker Compose：

```bash
docker compose up -d web
```

### 成本控制建议

- 开发期选 Community Cloud 或低成本 24GB GPU；稳定生产再考虑 Secure Cloud。
- 大模型、ComfyUI custom nodes、HunyuanVideo 权重放 Network Volume，避免每次重建 Pod 重新下载。
- 输出视频及时同步到对象存储或本地，避免 Volume 越积越大。
- 不生成时停止 Pod；需要 API 常驻时再考虑 Serverless 或常驻 Secure Cloud。
- 不要在启动脚本里强制下载大模型，模型下载应手动执行并可断点续传。

参考链接：

- [RunPod GPU Pricing](https://www.runpod.io/pricing)
- [RunPod Pod Templates](https://docs.runpod.io/pods/templates/overview)
- [RunPod Environment Variables](https://docs.runpod.io/pods/templates/environment-variables)
- [HunyuanVideo-1.5 GitHub](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5)

## 本地安装依赖

```bash
pip install -r requirements.txt
```

## 最小运行流程

```bash
python scripts/01_novel_to_script.py --episode ep01
python scripts/02_script_to_storyboard.py --episode ep01
python scripts/04_generate_prompts.py --episode ep01
python scripts/05_batch_image_gen.py --episode ep01 --dry-run
python scripts/06_batch_video_gen.py --episode ep01 --dry-run
python scripts/07_score_videos.py --episode ep01
python scripts/10_assemble_episode.py --episode ep01
```

## 单镜头测试

```bash
python scripts/06_batch_video_gen.py --episode ep01 --shot ep01_sc01_sh01 --dry-run
```

## 配置

主配置文件是 `input/config/project.yaml`。模型、seed、运动强度、分辨率、时长和外部工具路径应优先从配置读取，不要写死在脚本里。

## 状态

当前仓库已搭好目录骨架和占位脚本，后续按 MVP 顺序逐步实现每个步骤。
