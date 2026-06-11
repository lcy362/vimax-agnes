# ViMax-Agnes

**Agentic Video Generation powered entirely by Agnes AI.**

> A lightweight adaptation of [ViMax](https://github.com/HKUDS/ViMax) that replaces Google Veo/Gemini with Agnes AI's API for image and video generation.

English | [中文](zh.md)

## Features

- **Idea → Video**: Provide a creative idea, style, and simple requirements — get a complete video
- **Character Consistency**: Generates a character reference image, then reuses it across all scenes via `ti2vid` mode
- **Full Agnes Integration**: Uses Agnes AI for chat (story/script), image generation, and video generation
- **Smart Pipeline**: Story → Character Reference → Script → Scene Videos → Final Video
- **Cache System**: Intermediate results are cached — re-run only generates missing parts
- **Progress Feedback**: Real-time Chinese progress indicators with file-logging support

## Example

🎬 **The Frog Prince** — a dark-twist fairytale, 5 scenes generated with auto-generated keyframes:

[v.douyin.com/L4F6KdGnD6U/](https://v.douyin.com/L4F6KdGnD6U/)

## Quick Start

### 1. Requirements

- Python 3.10+
- Agnes AI API Key ([register here](https://platform.agnes-ai.com))

### 2. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -r requirements.txt
```

### 3. Set API Key

Three options (the first one found wins):

**Option A — `.api_key` file (recommended, used by `start.sh`):**

```bash
echo "your-agnes-api-key" > .api_key
```

This file is gitignored — safe for local use.

**Option B — environment variable:**

```bash
export AGNES_API_KEY="your-agnes-api-key"
```

**Option C — config file:**

Edit `configs/idea2video.yaml` and set the `api_key` field.

> `run_creative.py` resolves the key in order: CLI `-k` → env var → config file.

### 4. Run

```bash
# List available creatives
./start.sh

# Run a specific creative
./start.sh <creative_name>
```

The script will automatically set the API key, use the virtual environment, and launch the pipeline.

### 5. Find Your Video

Output: `.working_dir/<creative_name>/final_video.mp4`

Logs: `.working_dir/logs/`

## Creative Configs (YAML)

Place your creative definitions in `creatives/` as `.yaml` files:

```yaml
name: my_creative
idea: "A robot learns to paint in a sunlit studio"
user_requirement: "3-5 scenes, suitable for all ages"
style: "Cartoon"
chaining_mode: none          # "none" | "keyframes" | "ti2vid"
video_width: 768
video_height: 1152
reference_image: ""          # optional: local path or URL
# end_frame_images:             # optional: custom end frame per scene (local files auto-resized)
#   - /path/to/scene0_end.png
```

> **Custom End Frames**: `end_frame_images` is optional. When provided, the system uses
> your images directly instead of auto-generating. Local files are auto-resized to the
> target video dimensions. One path/URL per scene; extra scenes fall back to auto-generation.

## Architecture

```
+------------------+
|   Your Idea     |
| + (Optional)    |
| Reference Image |
+--------+--------+
         |
+-----------------+
|  Screenwriter   | <- Agnes Chat API (agnes-2.0-flash)
|  Story + Script |
+--------+--------+
         |
+------------------+
| Character Ref    | <- User-provided, or auto-generated
| Image            |    via Agnes Image API (agnes-image-2.1-flash)
+--------+--------+
         |
+-----------------+
|  Video Generator| <- Agnes Video API (agnes-video-v2.0)
|  ti2vid mode    |    Each scene uses the SAME reference image
|  (per scene)    |    as first frame for consistency
+--------+--------+
         |
+-----------------+
|  Concatenation  | <- moviepy
|  Final Video    |
+-----------------+
```

## Pipeline Flow

1. **Story Development**: LLM expands your idea into a structured story with detailed character descriptions
2. **Character Reference**: Uses the provided reference image, or auto-generates one from the story
3. **Script Writing**: LLM divides the story into scenes with dialogue and actions
4. **Scene Videos**: Each scene generates a video using the reference image (ti2vid mode) as the first frame
5. **Concatenation**: All scene videos are joined into the final output

## Character Consistency

The pipeline maintains character consistency across scenes through a two-stage approach:

**Stage 1 (t2i)**: Each scene generates a unique first frame from text, but all prompts share the same style keywords (art style, color palette, lighting, character design) to lock the visual identity.

**Stage 2 (ti2vid)**: The first frame is passed to the video model as a reference image. The model animates from this starting point, preserving character design, colors, and composition.

> **Tip**: Cartoon/chibi styles work best for consistency. For photorealistic styles, always provide an explicit `reference_image`.

## Agnes API Details

| Purpose | Endpoint | Model |
|---------|----------|-------|
| Chat (Story/Script) | POST `/v1/chat/completions` | agnes-2.0-flash |
| Character Reference | POST `/v1/images/generations` | agnes-image-2.1-flash |
| Image Upload | POST `/v1/images/generations` (img2img) | agnes-image-2.1-flash |
| Scene Video (ti2vid) | POST `/v1/videos` (image + mode=ti2vid) | agnes-video-v2.0 |
| Task Polling | GET `/v1/videos/{task_id}` | - |

### Duration Config

Edit `configs/idea2video.yaml`:

```yaml
video_generator:
  init_args:
    default_duration: 5  # seconds per scene (5, 10, 15, 18, 20)
```

| Duration | num_frames | frame_rate |
|----------|-----------|------------|
| 5s | 121 | 24 |
| 10s | 241 | 24 |
| 15s | 361 | 24 |
| 18s | 441 | 24 |
| 20s | 441 | 22 |

## Project Structure

```
vimax-agnes/
├── start.sh                     # One-click launcher
├── run_creative.py              # Creative YAML runner (unified entry point)
├── main_idea2video.py           # Standalone idea2video entry (programmatic use)
├── run_full_pipeline.py         # Full pipeline with keyframes chaining
├── creatives/                   # Creative YAML configurations
│   ├── example.yaml
│   ├── hot_spring_robot.yaml
│   └── singing_dancing.yaml
├── configs/
│   └── idea2video.yaml          # API and pipeline configuration
├── agents/
│   └── screenwriter.py          # LLM-powered story/script generation
├── tools/
│   ├── image_generator_agnes_api.py  # Agnes image generation (t2i + i2i)
│   ├── video_generator_agnes_api.py  # Agnes video generation (t2v, ti2vid, keyframes)
│   ├── render_backend.py             # Config-based backend initialization
│   └── protocols.py                  # Type contracts
├── interfaces/
│   ├── shot_description.py           # Shot data model
│   ├── image_output.py               # Image output container
│   └── video_output.py               # Video output container
├── pipelines/
│   └── idea2video_pipeline.py        # Main orchestration pipeline
├── prompts/                           # Scene prompt JSON files (historical)
├── requirements.txt
└── LICENSE
```

## Credits

- [ViMax](https://github.com/HKUDS/ViMax) — Original agentic video generation framework
- [Agnes AI](https://platform.agnes-ai.com) — AI generation API

## License

MIT
