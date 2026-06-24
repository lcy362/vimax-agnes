# ViMax-Agnes

> ⚠️ **本项目已迁移至 [agnes-video-generator](https://github.com/lcy362/agnes-video-generator)** —— 代码更整洁、架构更优、功能更丰富，后续所有开发将在新仓库进行。
>
> **[:globe_with_meridians: 官网](https://video.lichuanyang.top) · [:pencil: 中文博客](https://lichuanyang.top/posts/22470/) · [:pencil: English Blog](https://lichuanyang.top/en/posts/22470/)**

**免费 AI 视频生成 —— 用 Agnes AI 免费模型把任意创意变成多场景视频，角色一致、自动拼接。**

> 使用 Agnes AI 免费模型（`agnes-video-v2.0`、`agnes-image-2.1-flash`、`agnes-2.0-flash`）从文本生成视频 —— 无需 GPU、无需信用卡，只需一个 API Key。

[English](README.md) | 中文

---

## 示例视频

> 暗黑童话 —— 《青蛙王子》，5 个场景，关键帧串联，全自动生成。

[![观看演示视频](https://img.shields.io/badge/▶%20观看演示-FF0050?style=for-the-badge&logo=tiktok&logoColor=white)](https://v.douyin.com/L4F6KdGnD6U/)

<sub>点击在抖音观看</sub>

---

## 这是什么

ViMax-Agnes 是一个开源的 Agentic 视频生成框架，使用 [Agnes AI](https://platform.agnes-ai.com) API 自动将文字创意变成完整视频。三个 Agnes 免费模型协同工作：

- **agnes-2.0-flash**（对话）—— 从你的创意生成故事、脚本和视觉 prompt
- **agnes-image-2.1-flash**（图片）—— 通过 text-to-image 生成角色参考图和关键帧
- **agnes-video-v2.0**（视频）—— 通过 text-to-video（t2v）、image-to-video（ti2vid）、keyframes 模式生成场景视频

无需注册费、无需信用卡 —— [免费获取 Agnes API Key](https://platform.agnes-ai.com) 即可开始生成。

## 核心功能

**一条命令，创意变视频**
写一个 YAML 文件描述创意，运行 `./start.sh <名称>`，等待出片。故事、图片、视频、拼接 —— 全流程自动执行。

**跨场景角色一致性**
两阶段方案锁定视觉身份：先生成（或你提供）一张角色参考图，然后每个场景视频都以它为起始帧通过 `ti2vid` 模式生成，保持外貌、服装和风格统一。

**三种场景串联模式**
- `none` — 每个场景独立生成，共用同一张参考图。速度最快。
- `keyframes` — 顺序生成，AI 计算首帧 + 尾帧关键帧，场景过渡最平滑。**（推荐）**
- `ti2vid` — 顺序生成，通过 img2img 生成场景间的过渡帧。

**智能缓存与断点续跑**
每个中间结果（故事、脚本、参考图、场景视频）都会持久化到磁盘。重新运行时只生成缺失部分 —— 天然支持崩溃恢复。

**多模态图片分析**
提供自己的参考图或自定义尾帧图片，系统会通过多模态 LLM 分析图片内容，将视觉信息融入故事和生成 prompt。

**实时进度反馈**
中文进度提示 + emoji 标记，支持文件日志，适合后台运行。

## 快速开始

### 环境要求

- Python 3.10+
- Agnes AI API Key — [免费注册](https://platform.agnes-ai.com)

### 安装

```bash
git clone https://github.com/lcy362/vimax-agnes.git
cd vimax-agnes
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 设置 API Key

在项目根目录创建 `.api_key` 文件：

```bash
echo "你的Agnes API Key" > .api_key
```

> 其他方式：环境变量 `AGNES_API_KEY`，或编辑 `configs/idea2video.yaml`。
> 优先级：命令行 `-k` 参数 > 环境变量 > 配置文件 > `.api_key` 文件。

### 运行

```bash
# 查看可用创意列表
./start.sh

# 运行指定创意
./start.sh frog
```

### 查看结果

- 最终视频：`.working_dir/<创意名称>/final_video.mp4`
- 运行日志：`.working_dir/logs/`

## 创意配置

在 `creatives/` 目录下用 YAML 定义你的视频创意：

```yaml
name: "my_video"

idea: |
  一个机器人在洒满阳光的工作室里学画画，
  逐渐创作出一幅融合科技与艺术的杰作。

user_requirement: |
  3个场景，每个场景10秒，电影质感

style: "电影质感写实风格"

chaining_mode: keyframes     # none | keyframes | ti2vid
video_width: 768             # 竖屏 768x1152
video_height: 1152
reference_image: ""          # 可选：本地路径或 URL
# end_frame_images:          # 可选：自定义每场景尾帧
#   - /path/to/end_0.png
```

然后运行：`./start.sh my_video`

## 系统架构

```
creatives/*.yaml           ← 你的创意
        │
        ▼
┌─────────────────┐
│  run_creative.py │  ← 统一入口
└────────┬────────┘
         │
┌────────▼────────┐
│   编剧模块       │  Agnes Chat (agnes-2.0-flash)
│   故事 + 脚本    │  → 故事、场景、尾帧 prompt
└────────┬────────┘
         │
┌────────▼────────┐
│   图片生成器     │  Agnes Image (agnes-image-2.1-flash)
│   角色参考图     │  → 参考图、尾帧图片
└────────┬────────┘
         │
┌────────▼────────┐
│   视频生成器     │  Agnes Video (agnes-video-v2.0)
│   逐场景视频     │  → t2v / ti2vid / keyframes
└────────┬────────┘
         │
┌────────▼────────┐
│   视频拼接       │  moviepy
│   final_video   │
└─────────────────┘
```

## 角色一致性原理

1. **阶段一（t2i）** — 从故事的角色描述中生成一张角色参考图，也可以由你直接提供。
2. **阶段二（ti2vid）** — 每个场景视频以该参考图作为起始帧生成。视频模型从同一视觉锚点出发进行动画化，保留角色设计、配色和构图。

> **提示**：卡通/风格化画风一致性效果最好。写实风格建议直接提供 `reference_image`。

## 使用的 Agnes AI 模型

本项目通过 OpenAI 兼容 API（`https://apihub.agnes-ai.com/v1`）使用三个 Agnes 免费模型：

| 用途 | Agnes 模型 | API 接口 | 模式 |
|------|-----------|---------|------|
| 故事和脚本编写 | `agnes-2.0-flash` | `POST /chat/completions` | 对话 |
| 角色参考图和关键帧 | `agnes-image-2.1-flash` | `POST /images/generations` | text-to-image (t2i) |
| 图片编辑和过渡帧 | `agnes-image-2.0-flash` | `POST /images/generations` | image-to-image (i2i) |
| 场景视频生成 | `agnes-video-v2.0` | `POST /videos` | t2v / ti2vid / keyframes |
| 视频任务轮询 | — | `GET /videos/{task_id}` | 异步轮询 |

所有模型均**免费使用**，只需 Agnes API Key —— 无需信用卡、无需 GPU。

## 配置

编辑 `configs/idea2video.yaml` 调整每场景视频时长：

```yaml
video_generator:
  init_args:
    default_duration: 10  # 每场景秒数（5, 10, 15, 18, 20）
```

| 时长 | 帧数 | 帧率 |
|------|------|------|
| 5秒 | 121 | 24 |
| 10秒 | 241 | 24 |
| 15秒 | 361 | 24 |
| 18秒 | 441 | 24 |
| 20秒 | 441 | 22 |

## 项目结构

```
vimax-agnes/
├── start.sh                          # 一键启动脚本
├── run_creative.py                   # 统一入口
├── main_idea2video.py                # 编程式入口
├── creatives/                        # 创意 YAML 配置
│   ├── child.yaml
│   ├── example.yaml
│   ├── frog.yaml
│   ├── girldunk.yaml
│   ├── hot_spring_robot.yaml
│   └── singing_dancing.yaml
├── configs/idea2video.yaml           # 系统配置
├── agents/screenwriter.py            # LLM 编剧 Agent
├── tools/
│   ├── image_generator_agnes_api.py  # 图片生成（t2i + i2i）
│   └── video_generator_agnes_api.py  # 视频生成（t2v/ti2vid/keyframes）
├── interfaces/                       # Pydantic 数据模型
├── pipelines/idea2video_pipeline.py  # 核心编排流水线
├── requirements.txt
└── LICENSE
```

## 致谢

- [ViMax](https://github.com/HKUDS/ViMax) — 原始 Agentic 视频生成框架
- [Agnes AI](https://platform.agnes-ai.com) — AI 生成 API

## 许可证

MIT
