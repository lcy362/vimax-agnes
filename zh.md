# ViMax-Agnes

**基于 Agnes AI 的智能视频生成工具**

> 基于 [ViMax](https://github.com/HKUDS/ViMax) 轻量改造，用 Agnes AI API 替代 Google Veo/Gemini 进行图像和视频生成。

[English](README.md) | 中文

## 功能特性

- **创意即视频**：只需提供创意想法、风格和简单需求，即可生成完整视频
- **人物一致性**：先生成角色参考图，再通过 `ti2vid` 模式在所有场景中复用
- **全链路 Agnes 集成**：对话（故事/脚本）、图像生成、视频生成全部使用 Agnes AI
- **智能流水线**：故事 → 角色参考 → 脚本 → 场景视频 → 最终视频
- **缓存系统**：中间结果自动缓存，重复运行只生成缺失部分
- **进度反馈**：实时中文进度提示，支持文件日志

## 快速开始

### 1. 环境要求

- Python 3.10+
- Agnes AI API Key（[在此注册](https://platform.agnes-ai.com)）

### 2. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -r requirements.txt
```

### 3. 设置 API Key

```bash
export AGNES_API_KEY="your-agnes-api-key"
```

或编辑 `configs/idea2video.yaml`。

也可以直接编辑 `start.sh` 替换内置 API Key。

### 4. 运行

```bash
# 查看可用创意列表
./start.sh

# 运行指定创意
./start.sh <创意名称>
```

脚本会自动设置 API Key、使用虚拟环境、启动流水线。

### 5. 查看视频

输出：`.working_dir/<创意名称>/final_video.mp4`

日志：`.working_dir/logs/`

## 创意配置（YAML）

在 `creatives/` 目录下以 `.yaml` 文件定义创意：

```yaml
name: my_creative
idea: "一个机器人在洒满阳光的工作室里学画画"
user_requirement: "3-5 个场景，适合全年龄段"
style: "Cartoon"
chaining_mode: none          # "none" | "keyframes" | "ti2vid"
video_width: 768
video_height: 1152
reference_image: ""          # 可选：本地路径或 URL
```

## 系统架构

```
+------------------+
|   你的创意       |
| +（可选）        |
| 参考图片         |
+--------+--------+
         |
+-----------------+
|   编剧模块       | <- Agnes Chat API (agnes-2.0-flash)
|   故事 + 脚本    |
+--------+--------+
         |
+------------------+
| 角色参考图       | <- 用户提供，或通过
|                  |    Agnes Image API (agnes-image-2.1-flash)
+--------+--------+    从故事描述自动生成
         |
+-----------------+
| 视频生成器       | <- Agnes Video API (agnes-video-v2.0)
|  ti2vid 模式    |    每个场景使用同一参考图
|  （逐场景）      |    作为首帧保持一致性
+--------+--------+
         |
+-----------------+
|  视频拼接        | <- moviepy
|  最终成片        |
+-----------------+
```

## 流水线流程

1. **故事创作**：LLM 将创意扩展为结构化故事，包含详细的角色描述
2. **角色参考图**：使用提供的参考图，或从故事描述自动生成
3. **脚本编写**：LLM 将故事拆分为多个场景，包含对话和动作
4. **场景视频**：每个场景使用参考图（ti2vid 模式）作为首帧生成视频
5. **视频拼接**：所有场景视频拼接为最终成片

## 人物一致性

流水线通过两阶段方案保持人物一致性：

**阶段1（t2i）**：每个场景根据独特文本生成首帧，但所有提示词共享相同的风格关键词（画风、色调、光照、角色设计），锁定视觉身份。

**阶段2（ti2vid）**：首帧作为参考图传入视频模型。模型从该起始点进行动画化，保留角色设计、配色和构图。

> **提示**：卡通/Q版风格一致性效果最好。写实风格建议始终提供显式 `reference_image`。

## Agnes API 详情

| 用途 | 接口 | 模型 |
|------|------|------|
| 对话（故事/脚本） | POST `/v1/chat/completions` | agnes-2.0-flash |
| 角色参考图 | POST `/v1/images/generations` | agnes-image-2.1-flash |
| 图片上传 | POST `/v1/images/generations` (img2img) | agnes-image-2.1-flash |
| 场景视频 (ti2vid) | POST `/v1/videos` (image + mode=ti2vid) | agnes-video-v2.0 |
| 任务轮询 | GET `/v1/videos/{task_id}` | - |

### 时长配置

编辑 `configs/idea2video.yaml`：

```yaml
video_generator:
  init_args:
    default_duration: 5  # 每场景秒数（5, 10, 15, 18, 20）
```

| 时长 | num_frames | frame_rate |
|------|-----------|------------|
| 5秒 | 121 | 24 |
| 10秒 | 241 | 24 |
| 15秒 | 361 | 24 |
| 18秒 | 441 | 24 |
| 20秒 | 441 | 22 |

## 项目结构

```
vimax-agnes/
├── start.sh                     # 一键启动脚本
├── run_creative.py              # 创意 YAML 统一入口
├── main_idea2video.py           # 独立 idea2video 入口（编程式调用）
├── run_full_pipeline.py         # 完整流水线（含关键帧串联）
├── creatives/                   # 创意 YAML 配置文件
│   ├── example.yaml
│   ├── hot_spring_robot.yaml
│   └── singing_dancing.yaml
├── configs/
│   └── idea2video.yaml          # API 与流水线配置
├── agents/
│   └── screenwriter.py          # LLM 驱动的故事/脚本生成
├── tools/
│   ├── image_generator_agnes_api.py  # Agnes 图像生成 (t2i + i2i)
│   ├── video_generator_agnes_api.py  # Agnes 视频生成 (t2v, ti2vid, keyframes)
│   ├── render_backend.py             # 基于配置的后端初始化
│   └── protocols.py                  # 类型契约
├── interfaces/
│   ├── shot_description.py           # 镜头数据模型
│   ├── image_output.py               # 图像输出容器
│   └── video_output.py               # 视频输出容器
├── pipelines/
│   └── idea2video_pipeline.py        # 主编排流水线
├── prompts/                           # 场景提示词 JSON 文件（历史）
├── requirements.txt
└── LICENSE
```

## 致谢

- [ViMax](https://github.com/HKUDS/ViMax) — 原始智能视频生成框架
- [Agnes AI](https://platform.agnes-ai.com) — AI 生成 API

## 许可证

MIT
