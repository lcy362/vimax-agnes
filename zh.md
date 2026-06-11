# ViMax-Agnes

**Agentic 视频生成 —— 从创意到成片，完全由 Agnes AI 驱动。**

[English](README.md) | 中文

---

## 示例视频

> 暗黑童话 —— 《青蛙王子》，5 个场景，关键帧串联，全自动生成。

[![观看演示视频](https://img.shields.io/badge/▶%20观看演示-FF0050?style=for-the-badge&logo=tiktok&logoColor=white)](https://v.douyin.com/L4F6KdGnD6U/)

<sub>点击在抖音观看。更多示例：[女孩扣篮](https://v.douyin.com/L4F6KdGnD6U/) · [海边舞蹈](https://v.douyin.com/L4F6KdGnD6U/)</sub>

---

## 这是什么

ViMax-Agnes 是一个轻量级 Agentic 视频生成框架，能把一段**文字创意**自动变成一个**完整的多场景视频** —— 全流程无需人工干预。

只需提供创意描述、风格偏好和简单约束，系统会自动完成：

1. **创作故事** — 生成有角色、有情节的完整故事
2. **生成角色参考图** — 锁定视觉一致性
3. **拆分场景脚本** — 将故事转化为电影级视觉 prompt
4. **逐场景生成视频** — 每个场景保持角色一致
5. **拼接成片** — 输出最终视频

全部由 [Agnes AI](https://platform.agnes-ai.com) 单一 API 驱动（免费，无需信用卡）。

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

## 配置

编辑 `configs/idea2video.yaml`：

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
