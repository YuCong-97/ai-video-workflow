# AGENTS.md

## 项目名称

AI Short Drama Pipeline / 小说转 AI 短剧流水线

## 项目目标

本项目用于把小说内容转成可批量生产的 AI 短剧 / 动画素材流水线。

目标流程：

```text
小说 → 剧本 → 分镜 → 角色设定 → 场景图 → 镜头提示词 → 批量视频 → 自动筛片 → 剪辑模板
```

核心目标不是一次性追求完全自动化，而是先跑通 MVP，再逐步优化为半自动、全自动生产线。

---

## Codex 总体任务

你是本项目的代码优化与工程化助手。你的职责是：

1. 维护清晰、稳定、可扩展的项目结构。
2. 将小说转短剧流程拆成可执行脚本。
3. 保证每一步都有明确输入、输出和日志。
4. 优先让流水线可跑通，再优化质量和自动化程度。
5. 不要破坏已有目录结构、命名规范和数据格式。
6. 修改代码前先理解上下游依赖。
7. 对每次修改给出清楚的变更说明。

---

## 项目阶段

### 阶段一：MVP 最小闭环

优先实现：

```text
小说章节 → 剧本 JSON → 分镜 JSON → 提示词 CSV → 图片/视频生成任务 → 人工选片 → ffmpeg 粗剪
```

阶段一不要过度追求：

- 全自动评分
- 全自动配音
- 全自动字幕
- Web 控制台
- 多用户平台化
- 复杂数据库

### 阶段二：半自动化

增加：

```text
角色卡
场景卡
提示词自动拼接
多 seed 批量生成
抽帧预览图
缩略图墙
视频基础评分
TTS 批量生成
字幕生成
```

### 阶段三：全自动化

增加：

```text
自动筛片
失败镜头自动重跑
自动配音
自动字幕
自动拼接
剪辑模板
任务队列
Web 控制台
```

---

## 推荐目录结构

Codex 优化项目时，应尽量保持以下结构：

```bash
ai-short-drama/
├─ input/
│  ├─ novel/
│  │  └─ novel.txt
│  └─ config/
│     ├─ project.yaml
│     ├─ characters.json
│     ├─ scene_templates.json
│     └─ style_presets.json
│
├─ data/
│  ├─ scripts/
│  │  ├─ ep01_script.json
│  │  └─ ep02_script.json
│  ├─ storyboards/
│  │  ├─ ep01_storyboard.json
│  │  └─ ep02_storyboard.json
│  ├─ prompts/
│  │  ├─ ep01_prompts.csv
│  │  └─ ep02_prompts.csv
│  └─ dialogue/
│     ├─ ep01_dialogue.json
│     └─ ep02_dialogue.json
│
├─ assets/
│  ├─ characters/
│  │  ├─ char_001/
│  │  │  ├─ ref_front.png
│  │  │  ├─ ref_halfbody.png
│  │  │  └─ ref_fullbody.png
│  │  └─ char_002/
│  ├─ scenes/
│  │  ├─ hospital_room_night/
│  │  └─ office_day/
│  ├─ bgm/
│  └─ sfx/
│
├─ outputs/
│  ├─ images/
│  │  └─ ep01/
│  ├─ videos/
│  │  ├─ raw/
│  │  ├─ scored/
│  │  └─ selected/
│  ├─ voices/
│  ├─ subtitles/
│  └─ final/
│
├─ logs/
├─ temp/
├─ scripts/
│  ├─ 01_novel_to_script.py
│  ├─ 02_script_to_storyboard.py
│  ├─ 03_generate_character_cards.py
│  ├─ 04_generate_prompts.py
│  ├─ 05_batch_image_gen.py
│  ├─ 06_batch_video_gen.py
│  ├─ 07_score_videos.py
│  ├─ 08_tts_generate.py
│  ├─ 09_make_subtitles.py
│  └─ 10_assemble_episode.py
│
├─ tools/
│  ├─ ffmpeg_utils.py
│  ├─ prompt_utils.py
│  ├─ path_utils.py
│  ├─ scoring_utils.py
│  └─ config_loader.py
│
├─ requirements.txt
├─ README.md
└─ AGENTS.md
```

---

## 总配置文件规范

主配置文件路径：

```text
input/config/project.yaml
```

推荐字段：

```yaml
project_name: ai_short_drama
style: cinematic_realism
language: zh-CN

episode:
  target_duration_sec: 60
  shots_per_episode: 12
  avg_shot_duration_sec: 4

llm:
  provider: openai
  model_script: gpt-5
  model_storyboard: gpt-5-mini

image_gen:
  tool: comfyui
  model: flux
  width: 832
  height: 1216
  num_candidates: 4

video_gen:
  tool: hunyuanvideo
  mode: i2v
  duration_sec: 4
  fps: 24
  seeds: [1001, 1002, 1003]
  motion_levels: [low, medium]

tts:
  provider: edge_tts
  voice_default_female: zh-CN-XiaoxiaoNeural
  voice_default_male: zh-CN-YunxiNeural

screening:
  sharpness_weight: 0.2
  face_weight: 0.25
  consistency_weight: 0.3
  prompt_match_weight: 0.25
  auto_pass_score: 0.78

editing:
  subtitle_style: drama_default
  resolution: 1080x1920
  intro_sec: 2
  outro_sec: 2
```

Codex 修改代码时，应优先从 `project.yaml` 读取参数，不要把路径、模型名、seed、分辨率、时长写死在脚本里。

---

## 数据格式规范

### 1. 剧本 JSON

路径示例：

```text
data/scripts/ep01_script.json
```

格式：

```json
{
  "episode_id": "ep01",
  "title": "第一集：重生归来",
  "summary": "女主重生回到三年前，意识到自己还有机会改变命运。",
  "characters": ["char_001", "char_002"],
  "scenes": [
    {
      "scene_id": "ep01_sc01",
      "location": "医院病房",
      "time": "夜",
      "summary": "女主醒来，发现自己重生。",
      "emotion": "震惊、压抑",
      "conflict": "女主意识到自己回到了命运转折点。"
    }
  ]
}
```

### 2. 分镜 JSON

路径示例：

```text
data/storyboards/ep01_storyboard.json
```

格式：

```json
{
  "episode_id": "ep01",
  "shots": [
    {
      "shot_id": "ep01_sc01_sh01",
      "scene_id": "ep01_sc01",
      "shot_type": "中景",
      "camera_angle": "平视",
      "camera_movement": "缓慢推进",
      "duration": 4,
      "subject": "女主躺在病床上醒来",
      "action": "缓缓睁眼，转头看向窗外",
      "emotion": "震惊、恍惚",
      "dialogue": "我……回来了？",
      "visual_focus": "苍白脸色、医院灯光、夜雨窗户",
      "transition": "cut",
      "character_ids": ["char_001"],
      "scene_template_id": "hospital_room_night"
    }
  ]
}
```

### 3. 角色配置 JSON

路径：

```text
input/config/characters.json
```

格式：

```json
{
  "characters": [
    {
      "character_id": "char_001",
      "name": "苏晚",
      "gender": "女",
      "age": 24,
      "appearance": {
        "hair": "黑色长发，微卷",
        "eyes": "杏眼",
        "skin": "白皙",
        "body": "纤细"
      },
      "costume_default": "白色衬衫，黑色西装外套",
      "personality": "冷静、隐忍、聪明",
      "expression_tags": ["冷漠", "脆弱", "愤怒"],
      "voice_style": "清冷女声",
      "visual_prompt_base": "young Chinese woman, long black wavy hair, pale skin, almond eyes, elegant, cinematic realism"
    }
  ]
}
```

### 4. 场景模板 JSON

路径：

```text
input/config/scene_templates.json
```

格式：

```json
{
  "scene_templates": [
    {
      "scene_template_id": "hospital_room_night",
      "name": "医院病房-夜",
      "description": "现代医院单人病房，冷白灯光，窗外有夜雨，整体压抑安静。",
      "style": "cinematic realism",
      "key_elements": ["病床", "输液架", "窗户", "白色窗帘", "夜雨玻璃"],
      "camera_friendly_points": ["床侧", "窗边", "门口斜角"],
      "negative_elements": ["过多人群", "夸张装饰"]
    }
  ]
}
```

### 5. 提示词 CSV

路径示例：

```text
data/prompts/ep01_prompts.csv
```

字段建议：

```csv
episode_id,scene_id,shot_id,character_ids,scene_template_id,duration,seed,motion_level,prompt,negative_prompt,output_image,output_video,status
```

字段说明：

- `episode_id`：集编号，例如 `ep01`
- `scene_id`：场景编号，例如 `ep01_sc01`
- `shot_id`：镜头编号，例如 `ep01_sc01_sh01`
- `character_ids`：角色 ID，多个用 `|` 分隔
- `scene_template_id`：场景模板 ID
- `duration`：镜头时长，单位秒
- `seed`：生成 seed
- `motion_level`：运动强度，例如 `low`、`medium`
- `prompt`：正向提示词
- `negative_prompt`：负向提示词
- `output_image`：关键帧输出路径
- `output_video`：视频输出路径
- `status`：任务状态，例如 `pending`、`done`、`failed`、`selected`

---

## 命名规范

所有生成物必须尽量使用稳定命名。

### 集

```text
ep01
ep02
ep03
```

### 场景

```text
ep01_sc01
ep01_sc02
```

### 镜头

```text
ep01_sc01_sh01
ep01_sc01_sh02
```

### 图片

```text
ep01_sc01_sh01_ref_01.png
ep01_sc01_sh01_ref_02.png
```

### 视频

```text
ep01_sc01_sh01_seed1001_low.mp4
ep01_sc01_sh01_seed1002_medium.mp4
```

### 评分文件

```text
ep01_sc01_sh01_seed1001_low.score.json
```

### 字幕

```text
ep01.srt
```

### 最终视频

```text
ep01_final.mp4
```

---

## Prompt 拼接规则

Codex 优化提示词脚本时，应采用分层拼接，不要让每个镜头手写完整提示词。

推荐结构：

```text
final_prompt =
  character_prompt
  + scene_prompt
  + shot_prompt
  + camera_prompt
  + style_prompt
  + quality_prompt
```

推荐负向提示词：

```text
blurry, low quality, distorted face, extra fingers, bad hands, duplicated body, inconsistent clothing, low resolution, watermark, text
```

### 镜头提示词模板

```text
{character_prompt}, in {scene_prompt}. {subject}. {action}. Emotion: {emotion}. 
Shot type: {shot_type}. Camera angle: {camera_angle}. Camera movement: {camera_movement}. 
Visual focus: {visual_focus}. Style: cinematic realism, realistic lighting, highly detailed, film still.
```

---

## 各脚本职责

### scripts/01_novel_to_script.py

输入：

```text
input/novel/novel.txt
```

输出：

```text
data/scripts/ep01_script.json
```

职责：

- 读取小说章节。
- 调用 LLM 或本地规则拆分剧情。
- 输出结构化剧本 JSON。
- 每集包含标题、摘要、人物、场景、冲突点。

要求：

- 支持按章节生成。
- 支持指定 episode_id。
- 失败时写入 logs。
- 不要覆盖已有文件，除非传入 `--overwrite`。

---

### scripts/02_script_to_storyboard.py

输入：

```text
data/scripts/ep01_script.json
```

输出：

```text
data/storyboards/ep01_storyboard.json
```

职责：

- 将每个场景拆成 3~8 个镜头。
- 每个镜头包含景别、机位、运镜、时长、动作、情绪、台词。
- 自动生成 shot_id。

要求：

- 镜头时长默认 3~5 秒。
- 不要生成过于复杂动作。
- 对话镜头优先使用轻微运镜或静态镜头。
- 动作镜头要控制复杂度。

---

### scripts/03_generate_character_cards.py

输入：

```text
data/scripts/ep01_script.json
input/config/characters.json
```

输出：

```text
assets/characters/{character_id}/
```

职责：

- 检查剧本中角色是否存在于角色配置。
- 缺失时生成角色卡草稿。
- 为每个角色准备正面、半身、全身、表情图任务。

要求：

- 不要随意改变已有角色基础外观。
- 角色一致性优先于画面炫酷。
- 同一角色的发型、服装、年龄感、气质关键词必须稳定。

---

### scripts/04_generate_prompts.py

输入：

```text
data/storyboards/ep01_storyboard.json
input/config/characters.json
input/config/scene_templates.json
input/config/project.yaml
```

输出：

```text
data/prompts/ep01_prompts.csv
```

职责：

- 读取分镜、角色卡、场景卡。
- 自动拼接正向提示词和负向提示词。
- 按 seed 和 motion_level 展开多条候选任务。
- 为图片和视频输出路径预生成文件名。

要求：

- 一个镜头通常生成多条候选任务。
- 默认 seed 来自 `project.yaml`。
- 默认 motion_level 来自 `project.yaml`。
- 输出 CSV 保持字段稳定。

---

### scripts/05_batch_image_gen.py

输入：

```text
data/prompts/ep01_prompts.csv
```

输出：

```text
outputs/images/ep01/
```

职责：

- 根据 prompt 批量生成关键帧图片。
- 支持调用 ComfyUI / Forge / A1111 / 外部 API。
- 更新 CSV 中 output_image 和 status。

要求：

- 允许 dry-run。
- 允许指定 shot_id 只生成单个镜头。
- 出错不中断全部任务，应记录 failed。
- 生成前检查图片是否已存在，避免重复浪费。

---

### scripts/06_batch_video_gen.py

输入：

```text
data/prompts/ep01_prompts.csv
outputs/images/ep01/
```

输出：

```text
outputs/videos/raw/
```

职责：

- 根据关键帧图片和 prompt 批量生成视频。
- 优先支持 HunyuanVideo-1.5 图生视频。
- 每个镜头按 seed 和 motion_level 生成多条候选视频。
- 更新 CSV 中 output_video 和 status。

要求：

- 支持从失败任务继续。
- 支持指定 episode_id / scene_id / shot_id。
- 生成命令必须可打印，方便复制调试。
- HunyuanVideo 路径、ckpt 路径、输出路径从配置读取，不要写死。
- 生成日志必须保存到 logs。

---

### scripts/07_score_videos.py

输入：

```text
outputs/videos/raw/
```

输出：

```text
outputs/videos/scored/
*.score.json
```

职责：

- 对候选视频进行基础评分。
- 生成缩略图和抽帧图。
- 输出评分 JSON。
- 将高分视频复制或软链接到 `outputs/videos/selected/`。

推荐评分维度：

```text
sharpness_score
face_score
consistency_score
motion_score
prompt_match_score
final_score
```

评分 JSON 示例：

```json
{
  "video": "ep01_sc01_sh01_seed1002_medium.mp4",
  "sharpness_score": 0.82,
  "face_score": 0.76,
  "consistency_score": 0.80,
  "motion_score": 0.72,
  "prompt_match_score": 0.74,
  "final_score": 0.78,
  "recommend": true
}
```

要求：

- MVP 阶段可以先实现清晰度评分和抽帧预览。
- 不要为了复杂评分阻塞主流程。
- 自动筛片结果必须允许人工复核。

---

### scripts/08_tts_generate.py

输入：

```text
data/dialogue/ep01_dialogue.json
```

输出：

```text
outputs/voices/
```

职责：

- 根据角色声线批量生成台词音频。
- MVP 阶段优先使用 Edge-TTS。
- 后期可替换 CosyVoice / GPT-SoVITS。

要求：

- 语音文件命名使用 line_id。
- 每条语音输出 duration 信息。
- 角色 voice 配置从 `characters.json` 或 `project.yaml` 读取。

---

### scripts/09_make_subtitles.py

输入：

```text
data/dialogue/ep01_dialogue.json
outputs/voices/
```

输出：

```text
outputs/subtitles/ep01.srt
```

职责：

- 根据台词和语音时长生成 SRT 字幕。
- 支持短剧风格字幕。
- 字幕时间轴要尽量对齐镜头。

要求：

- 默认输出 SRT。
- 后续可增加 ASS 样式字幕。
- 文本过长时自动断行。

---

### scripts/10_assemble_episode.py

输入：

```text
outputs/videos/selected/
outputs/voices/
outputs/subtitles/
assets/bgm/
```

输出：

```text
outputs/final/ep01_final.mp4
```

职责：

- 使用 ffmpeg 拼接选中视频。
- 添加配音、BGM、字幕。
- 输出竖屏短剧视频。

要求：

- 默认输出 1080x1920。
- 支持无配音粗剪。
- 支持无字幕粗剪。
- 支持片头片尾。
- 拼接顺序以 storyboard 或 selected manifest 为准。

---

## 工具模块职责

### tools/config_loader.py

职责：

- 加载 YAML / JSON 配置。
- 校验关键字段。
- 提供默认值。
- 报错信息要清晰。

### tools/path_utils.py

职责：

- 创建目录。
- 生成标准路径。
- 根据 episode_id、scene_id、shot_id 生成文件名。

### tools/prompt_utils.py

职责：

- 拼接角色 prompt。
- 拼接场景 prompt。
- 拼接镜头 prompt。
- 生成 negative prompt。

### tools/ffmpeg_utils.py

职责：

- 检查 ffmpeg 是否可用。
- 抽帧。
- 拼接视频。
- 添加音频。
- 添加字幕。
- 转换分辨率。

### tools/scoring_utils.py

职责：

- 视频抽帧。
- 清晰度评分。
- 运动幅度评分。
- 生成人工预览图。
- 后期可加入 CLIP / 人脸检测。

---

## RunPod / HunyuanVideo 运行规范

如果项目使用 RunPod + HunyuanVideo-1.5，Codex 生成脚本时应满足：

1. 所有路径可配置。
2. 支持从失败任务继续。
3. 支持单镜头测试。
4. 支持批量 CSV 驱动。
5. 每条命令可打印。
6. 日志保存到 `logs/`。
7. 输出文件名包含 shot_id、seed、motion_level。
8. 不要依赖交互式输入。
9. 不要默认删除模型、缓存或历史输出。
10. 出错时跳过当前任务，继续处理后续任务。

示例生成命令应通过脚本构造，不要写死在多个位置。

---

## 自动筛片策略

MVP 阶段：

```text
抽帧 → 生成缩略图墙 → 人工选择
```

进阶阶段：

```text
清晰度评分
人脸稳定性评分
动作平滑度评分
画面闪烁评分
prompt 匹配评分
最终推荐分
```

推荐阈值：

```text
final_score >= 0.78：自动候选
0.65 <= final_score < 0.78：人工复查
final_score < 0.65：淘汰
```

不要让自动评分成为唯一决策依据，必须保留人工复核入口。

---

## 剪辑输出规范

默认目标：

```text
竖屏短剧
1080x1920
24fps 或 30fps
H.264 mp4
```

粗剪输出：

```text
outputs/final/ep01_rough.mp4
```

终版输出：

```text
outputs/final/ep01_final.mp4
```

ffmpeg 拼接时应注意：

- 分辨率统一
- 帧率统一
- 音频采样率统一
- 缺失音频时不要报错中断
- 每个中间文件写入 temp
- 完成后保留可选清理参数

---

## 日志规范

所有脚本应写日志到：

```text
logs/
```

日志文件名示例：

```text
2026-06-26_ep01_batch_video_gen.log
```

日志必须包含：

- 当前脚本
- 输入文件
- 输出文件
- 处理数量
- 成功数量
- 失败数量
- 错误原因
- 关键外部命令

---

## 命令行参数规范

每个脚本尽量支持：

```bash
--config input/config/project.yaml
--episode ep01
--scene ep01_sc01
--shot ep01_sc01_sh01
--overwrite
--dry-run
--limit 10
```

示例：

```bash
python scripts/04_generate_prompts.py --episode ep01
python scripts/06_batch_video_gen.py --episode ep01 --shot ep01_sc01_sh01 --dry-run
python scripts/07_score_videos.py --episode ep01
python scripts/10_assemble_episode.py --episode ep01
```

---

## Codex 修改优先级

当你优化项目时，按以下优先级执行：

### P0：能跑通

- 修复路径错误
- 修复依赖错误
- 修复配置读取错误
- 修复文件不存在
- 修复 ffmpeg 命令错误
- 修复 CSV / JSON 解析错误

### P1：可恢复

- 支持断点续跑
- 已存在文件跳过
- 失败任务记录
- 支持单镜头重跑

### P2：可批量

- CSV 批量驱动
- 多 seed 展开
- 多 motion level 展开
- 批量生成日志

### P3：可维护

- 抽离工具函数
- 配置集中管理
- 减少硬编码
- 增加类型注解
- 增加 README 示例

### P4：质量优化

- prompt 模板优化
- 自动筛片优化
- 角色一致性优化
- 场景一致性优化
- 剪辑效果优化

### P5：平台化

- FastAPI
- 队列
- 数据库
- Web 控制台
- MinIO / OSS
- 多用户管理

---

## 不要做的事情

Codex 不应主动做以下事情，除非用户明确要求：

1. 不要重构成复杂框架导致 MVP 跑不起来。
2. 不要引入大型依赖替代简单脚本。
3. 不要删除已有输出视频或图片。
4. 不要硬编码绝对路径。
5. 不要把所有逻辑塞进一个超大脚本。
6. 不要在没有配置的情况下强行调用付费 API。
7. 不要默认覆盖用户已有 JSON / CSV。
8. 不要把密钥写入代码。
9. 不要把模型下载写成自动强制执行。
10. 不要为了自动化牺牲可调试性。

---

## 代码风格

Python 代码建议：

- Python 3.10+
- 使用 `pathlib.Path`
- 使用 `argparse`
- 使用 `logging`
- 尽量加类型注解
- JSON 输出使用 `ensure_ascii=False`
- CSV 使用 UTF-8
- 外部命令使用 `subprocess.run`
- 命令失败要捕获并记录
- 工具函数放入 `tools/`

示例风格：

```python
from pathlib import Path
import argparse
import logging
import json


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, path: Path, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

---

## 推荐依赖

MVP 阶段：

```text
pyyaml
pandas
opencv-python
edge-tts
tqdm
```

可选：

```text
Pillow
moviepy
numpy
scenedetect
openai
requests
```

如果使用 HunyuanVideo / ComfyUI / Forge，请将其作为外部工具或子模块，不要把大模型权重提交到项目仓库。

---

## 环境变量规范

密钥和外部服务地址使用环境变量：

```bash
OPENAI_API_KEY=
COMFYUI_URL=http://127.0.0.1:8188
HUNYUAN_ROOT=/workspace/HunyuanVideo-1.5
HUNYUAN_CKPT=/workspace/HunyuanVideo-1.5/ckpts
```

不要把密钥提交到仓库。

---

## README 应包含的内容

Codex 更新 README 时，至少包含：

1. 项目简介
2. 目录结构
3. 安装依赖
4. 配置文件说明
5. 最小运行流程
6. 单镜头测试
7. 批量视频生成
8. 自动筛片
9. ffmpeg 粗剪
10. 常见问题

---

## 最小运行流程示例

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备小说
mkdir -p input/novel
cp novel.txt input/novel/novel.txt

# 3. 生成剧本
python scripts/01_novel_to_script.py --episode ep01

# 4. 生成分镜
python scripts/02_script_to_storyboard.py --episode ep01

# 5. 生成提示词
python scripts/04_generate_prompts.py --episode ep01

# 6. 生成关键帧
python scripts/05_batch_image_gen.py --episode ep01

# 7. 批量生成视频
python scripts/06_batch_video_gen.py --episode ep01

# 8. 视频评分 / 抽帧预览
python scripts/07_score_videos.py --episode ep01

# 9. 组装粗剪
python scripts/10_assemble_episode.py --episode ep01
```

---

## 当前最推荐的落地方案

当前阶段推荐：

```text
LLM 负责：小说解析、剧本、分镜、提示词
FLUX / SDXL 负责：角色图、场景图、关键帧
HunyuanVideo-1.5 负责：图生视频批量生成
Edge-TTS 负责：基础配音
ffmpeg 负责：粗剪、拼接、字幕、导出
Python 负责：全部编排
```

关键镜头可使用商业工具补强，例如：

```text
Kling / 即梦 / Runway / Pika / Luma
```

但工程主线应保持开源和可批量运行。

---

## 给 Codex 的执行建议

当用户要求“优化项目”时，请先检查：

1. 当前目录结构是否符合规范。
2. 是否存在 `input/config/project.yaml`。
3. 是否存在 `data/prompts/*.csv`。
4. HunyuanVideo 路径是否可配置。
5. 是否存在断点续跑能力。
6. 输出命名是否规范。
7. 日志是否可追踪。
8. ffmpeg 是否可用。
9. 脚本是否支持单镜头测试。
10. 是否有 README 最小运行流程。

优先提出可执行的改动，不要只给抽象建议。

---

## 一句话原则

```text
先跑通，再批量；先稳定，再自动；先低成本出粗片，再用商业工具补关键镜头。
```
