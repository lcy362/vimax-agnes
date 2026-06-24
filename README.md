# ViMax-Agnes

> ⚠️ **This project has moved to [agnes-video-generator](https://github.com/lcy362/agnes-video-generator)** — a complete rewrite with cleaner code, better architecture, and new features. All future development happens there.
>
> **[:globe_with_meridians: Official Website](https://video.lichuanyang.top) · [:pencil: Blog (中文)](https://lichuanyang.top/posts/22470/) · [:pencil: Blog (English)](https://lichuanyang.top/en/posts/22470/)**

**Free AI Video Generation with Agnes AI — Turn any idea into a multi-scene video with consistent characters.**

> Use Agnes AI's free models (`agnes-video-v2.0`, `agnes-image-2.1-flash`, `agnes-2.0-flash`) to generate videos from text — no GPU, no credit card, just an API key.

English | [中文](zh.md)

---

## Demo

> A dark-twist fairytale — *The Frog Prince*, 5 scenes, keyframes chaining, fully auto-generated.

[![The Frog Prince — Demo Video](https://img.shields.io/badge/▶%20Watch%20Demo-FF0050?style=for-the-badge&logo=tiktok&logoColor=white)](https://v.douyin.com/L4F6KdGnD6U/)

<sub>Click to watch on Douyin.</sub>

---

## What It Does

ViMax-Agnes is an open-source agentic video generation framework that uses the [Agnes AI](https://platform.agnes-ai.com) API to automatically produce complete videos from text ideas. All three Agnes free models work together:

- **agnes-2.0-flash** (Chat) — writes stories, scripts, and visual prompts from your idea
- **agnes-image-2.1-flash** (Image) — generates character reference images and keyframes via text-to-image
- **agnes-video-v2.0** (Video) — produces scene videos via text-to-video (t2v), image-to-video (ti2vid), and keyframes modes

No registration fee, no credit card — [get a free Agnes API key](https://platform.agnes-ai.com) and start generating.

## Key Features

**Idea → Video in One Command**
Write a YAML file describing your idea, run `./start.sh <name>`, get a video. The entire pipeline — story, images, videos, concatenation — runs automatically.

**Character Consistency Across Scenes**
A two-stage approach locks visual identity: first, a character reference image is generated (or provided by you); then every scene video uses it as the starting frame via `ti2vid` mode, preserving appearance, clothing, and style.

**Three Scene Chaining Modes**
- `none` — Each scene is independent, sharing the same reference image. Fastest.
- `keyframes` — Sequential generation with AI-computed first + last frame keyframes. Smoothest transitions. **(Recommended)**
- `ti2vid` — Sequential generation with img2img transition frames between scenes.

**Smart Caching & Resume**
Every intermediate result (story, script, reference image, scene videos) is cached to disk. Re-running the pipeline only generates what's missing — crash recovery is built in.

**Multimodal Image Analysis**
Provide your own reference images or custom end-frame images per scene. The system analyzes them via multimodal LLM and weaves the visual content into the story and generation prompts.

**Real-time Progress**
Chinese progress indicators with emoji markers, plus full file-based logging for background runs.

## Quick Start

### Prerequisites

- Python 3.10+
- An Agnes AI API Key — [register free](https://platform.agnes-ai.com)

### Install

```bash
git clone https://github.com/lcy362/vimax-agnes.git
cd vimax-agnes
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Set API Key

Create a `.api_key` file in the project root:

```bash
echo "your-agnes-api-key" > .api_key
```

> Other options: environment variable `AGNES_API_KEY`, or edit `configs/idea2video.yaml`.
> Priority: CLI `-k` flag > env var > config file > `.api_key` file.

### Run

```bash
# List available creatives
./start.sh

# Run a specific creative
./start.sh frog
```

### Output

- Final video: `.working_dir/<creative_name>/final_video.mp4`
- Logs: `.working_dir/logs/`

## Creative Config

Define your video ideas as YAML files in `creatives/`:

```yaml
name: "my_video"

idea: |
  A robot learns to paint in a sunlit studio, gradually
  creating a masterpiece that blends art and technology.

user_requirement: |
  3 scenes, 10 seconds each, cinematic quality

style: "Cinematic realistic"

chaining_mode: keyframes     # none | keyframes | ti2vid
video_width: 768             # 768x1152 for portrait
video_height: 1152
reference_image: ""          # optional: path or URL
# end_frame_images:          # optional: custom end frames per scene
#   - /path/to/end_0.png
```

Then run: `./start.sh my_video`

## Architecture

```
creatives/*.yaml          ← your ideas
        │
        ▼
┌─────────────────┐
│  run_creative.py │  ← unified entry point
└────────┬────────┘
         │
┌────────▼────────┐
│  Screenwriter    │  Agnes Chat (agnes-2.0-flash)
│  story + script  │  → story, scenes, end-frame prompts
└────────┬────────┘
         │
┌────────▼────────┐
│  Image Generator │  Agnes Image (agnes-image-2.1-flash)
│  character ref   │  → reference image, end-frame images
└────────┬────────┘
         │
┌────────▼────────┐
│  Video Generator │  Agnes Video (agnes-video-v2.0)
│  per-scene video │  → t2v / ti2vid / keyframes
└────────┬────────┘
         │
┌────────▼────────┐
│  Concatenation   │  moviepy
│  final_video.mp4 │
└─────────────────┘
```

## How Character Consistency Works

1. **Stage 1 (t2i)** — A character reference image is generated from the story's character description, or you provide one directly.
2. **Stage 2 (ti2vid)** — Each scene video starts from this reference image. The video model animates from the same visual anchor, preserving character design, colors, and composition across all scenes.

> **Tip**: Cartoon/stylized art gets the best consistency. For photorealistic output, providing an explicit `reference_image` is recommended.

## Agnes AI Models Used

This project uses three free Agnes AI models via the OpenAI-compatible API at `https://apihub.agnes-ai.com/v1`:

| Purpose | Agnes Model | API Endpoint | Mode |
|---------|-------------|--------------|------|
| Story & script writing | `agnes-2.0-flash` | `POST /chat/completions` | Chat |
| Character reference & keyframes | `agnes-image-2.1-flash` | `POST /images/generations` | text-to-image (t2i) |
| Image editing & transitions | `agnes-image-2.0-flash` | `POST /images/generations` | image-to-image (i2i) |
| Scene video generation | `agnes-video-v2.0` | `POST /videos` | t2v / ti2vid / keyframes |
| Video task polling | — | `GET /videos/{task_id}` | Async polling |

All models are **free to use** with an Agnes API key — no credit card, no GPU required.

## Configuration

Edit `configs/idea2video.yaml` to adjust per-scene video duration:

```yaml
video_generator:
  init_args:
    default_duration: 10  # seconds per scene (5, 10, 15, 18, 20)
```

| Duration | Frames | FPS |
|----------|--------|-----|
| 5s | 121 | 24 |
| 10s | 241 | 24 |
| 15s | 361 | 24 |
| 18s | 441 | 24 |
| 20s | 441 | 22 |

## Project Structure

```
vimax-agnes/
├── start.sh                          # One-click launcher
├── run_creative.py                   # Unified entry point
├── main_idea2video.py                # Programmatic entry
├── creatives/                        # Creative YAML configs
│   ├── child.yaml
│   ├── example.yaml
│   ├── frog.yaml
│   ├── girldunk.yaml
│   ├── hot_spring_robot.yaml
│   └── singing_dancing.yaml
├── configs/idea2video.yaml           # System configuration
├── agents/screenwriter.py            # LLM story/script agent
├── tools/
│   ├── image_generator_agnes_api.py  # Image generation (t2i + i2i)
│   └── video_generator_agnes_api.py  # Video generation (t2v/ti2vid/keyframes)
├── interfaces/                       # Pydantic data models
├── pipelines/idea2video_pipeline.py  # Core orchestration
├── requirements.txt
└── LICENSE
```

## Credits

- [ViMax](https://github.com/HKUDS/ViMax) — Original agentic video generation framework
- [Agnes AI](https://platform.agnes-ai.com) — AI generation API

## License

MIT
