#!/usr/bin/env python3
"""Full vimax pipeline: singing/dancing video with scene chaining.

Runs as a background daemon, checks on already-submitted tasks first.

用法:
    # 从创意 YAML 文件加载（推荐）
    python run_full_pipeline.py creatives/singing_dancing.yaml

    # 使用默认硬编码值（向后兼容）
    python run_full_pipeline.py

环境变量:
    AGNES_API_KEY: Agnes API 密钥（必需）
"""

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import requests

# ————————————————————————————————————————————————
# 常量：从环境变量读取 API Key
# ————————————————————————————————————————————————

API_KEY = os.environ.get("AGNES_API_KEY", "")
BASE_URL = "https://apihub.agnes-ai.com/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
WORK_DIR = ".working_dir/idea2video"
STATE_FILE = os.path.join(WORK_DIR, "task_state.json")
LOG_FILE = os.path.join(WORK_DIR, "pipeline_log.txt")
W, H, NF, FR = 768, 1152, 241, 24

# 默认参数（向后兼容）
DEFAULT_REF_IMG = "/home/z/my-project/upload/weixin-image.jpg"
DEFAULT_DL_DIR = "/home/z/my-project/download"
DEFAULT_FINAL_NAME = "singing_dancing_final.mp4"

# ═══════════════════════════════════════════════════════════════
# 默认创意参数（向后兼容：不传参数时使用）
# ═══════════════════════════════════════════════════════════════

DEFAULT_IDEA = """
唱歌跳舞：一位美丽的女孩站在绚丽的舞台上，先是深情演唱，然后切换为活力四射的舞蹈表演，最后以一个惊艳的定格动作结束
"""

DEFAULT_USER_REQUIREMENT = """
3个场景，每个场景10秒，电影质感，MV风格，竖屏拍摄
"""

DEFAULT_STYLE = "电影质感MV风格"


def load_creative_config(path: str) -> Dict[str, Any]:
    """从 YAML 文件加载创意配置。

    Args:
        path: YAML 创意配置文件路径。

    Returns:
        包含所有创意参数的字典。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ImportError: yaml 模块不可用时抛出。
    """
    import yaml

    if not os.path.exists(path):
        raise FileNotFoundError(f"创意配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    required_fields = ["name", "idea", "user_requirement", "style"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"创意配置文件缺少必需字段: {field}")

    return config


def resolve_api_key(cli_key: Optional[str] = None) -> str:
    """解析 API Key。"""
    if cli_key:
        return cli_key
    key = os.environ.get("AGNES_API_KEY", "")
    if key:
        return key
    print("错误: 未设置 AGNES_API_KEY。请通过以下方式设置:")
    print("  export AGNES_API_KEY='your-api-key'")
    print("  或使用 --api-key / -k 参数")
    sys.exit(1)


def log(msg: str) -> None:
    """记录日志到控制台和文件。"""
    print(msg, flush=True)
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def load_state() -> Dict[str, Any]:
    """加载任务状态。"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(s: Dict[str, Any]) -> None:
    """保存任务状态。"""
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def img_to_url(path: str) -> str:
    """将本地图片上传为托管 URL。"""
    with open(path, "rb") as f:
        b64 = __import__("base64").b64encode(f.read()).decode()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    uri = f"data:{mime};base64,{b64}"
    resp = requests.post(
        f"{BASE_URL}/images/generations",
        headers=HEADERS,
        json={
            "model": "agnes-image-2.1-flash",
            "prompt": "Keep the image exactly as it is",
            "n": 1,
            "size": "1024x1024",
            "extra_body": {"response_format": "url", "image": uri},
        },
        timeout=120,
    )
    resp.raise_for_status()
    url = resp.json()["data"][0]["url"]
    log(f"  Uploaded: {url[:80]}...")
    return url


def submit_video(prompt: str, img_url: Optional[str] = None) -> str:
    """提交视频生成任务。"""
    payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": W,
        "height": H,
        "num_frames": NF,
        "frame_rate": FR,
    }
    if img_url:
        payload["image"] = img_url
        payload["mode"] = "ti2vid"
    log("  Submitting video...")
    resp = requests.post(
        f"{BASE_URL}/videos", headers=HEADERS, json=payload, timeout=300
    )
    resp.raise_for_status()
    tid = resp.json().get("task_id") or resp.json().get("id")
    log(f"  Task: {tid[:30]}...")
    return tid


def poll_task(tid: str, max_wait: int = 480) -> str:
    """轮询等待视频任务完成，返回视频 URL。"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            resp = requests.get(f"{BASE_URL}/videos/{tid}", headers=HEADERS, timeout=15)
            r = resp.json()
            st = r.get("status", "")
            pr = r.get("progress", 0)
            if st in ("completed", "COMPLETED"):
                url = (
                    r.get("video_url")
                    or r.get("url")
                    or r.get("remixed_from_video_id")
                )
                if not url:
                    d = r.get("data", {})
                    if isinstance(d, dict):
                        url = d.get("video_url") or d.get("url")
                log(f"  Completed! URL: {url[:100]}...")
                return url
            if st in ("failed", "FAILED"):
                log(f"  FAILED: {r.get('error', 'unknown')}")
                raise RuntimeError(f"Video failed: {r.get('error')}")
            log(f"  ... {st} {pr}%")
        except RuntimeError:
            raise
        except Exception as e:
            log(f"  Poll err: {e}")
        time.sleep(15)
    raise TimeoutError(f"Timed out after {max_wait}s")


def download(url: str, path: str) -> None:
    """下载文件到本地。"""
    log(f"  Downloading to {path}...")
    r = requests.get(url, timeout=300, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    sz = os.path.getsize(path)
    log(f"  Saved: {path} ({sz // 1024}KB)")


def extract_last_frame(vid: str, out: str) -> None:
    """从视频中提取最后一帧。"""
    subprocess.run(
        [
            "ffmpeg", "-y", "-sseof", "-1", "-i", vid,
            "-frames:v", "1", "-update", "1", out,
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    log(f"  Last frame: {out}")


def gen_transition(img_url: str, next_prompt: str, out: str) -> None:
    """生成场景过渡帧。"""
    prompt = (
        "Cinematic transition frame blending end of current scene into "
        "beginning of next. Keep same person and face exactly. "
        f"Next scene: {next_prompt[:200]}"
    )
    log("  Generating transition via img2img...")
    resp = requests.post(
        f"{BASE_URL}/images/generations",
        headers=HEADERS,
        json={
            "model": "agnes-image-2.0-flash",
            "prompt": prompt,
            "size": "768x1152",
            "n": 1,
            "extra_body": {"response_format": "url", "image": img_url},
        },
        timeout=120,
    )
    resp.raise_for_status()
    url = resp.json()["data"][0].get("url", "")
    if url:
        r2 = requests.get(url, timeout=60)
        r2.raise_for_status()
        with open(out, "wb") as f:
            f.write(r2.content)
    log(f"  Transition: {out}")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="Full vimax pipeline: 场景串联视频生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_full_pipeline.py creatives/singing_dancing.yaml
  python run_full_pipeline.py    # 使用默认硬编码值
        """,
    )
    parser.add_argument(
        "creative",
        nargs="?",
        default=None,
        help="创意 YAML 配置文件路径（可选，不传则使用默认硬编码值）",
    )
    parser.add_argument(
        "--api-key", "-k",
        default=None,
        help="Agnes API Key（覆盖环境变量）",
    )
    parser.add_argument(
        "--script",
        default=None,
        help="Scenes JSON 文件路径（覆盖 YAML 中的设置）",
    )
    return parser


def main() -> None:
    """主函数。"""
    global API_KEY, HEADERS, WORK_DIR

    parser = build_parser()
    args = parser.parse_args()

    # 解析 API Key
    api_key = resolve_api_key(args.api_key)
    API_KEY = api_key
    HEADERS = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    os.makedirs(WORK_DIR, exist_ok=True)
    state = load_state()

    # ── 解析创意参数 ──
    if args.creative:
        creative_config = load_creative_config(args.creative)
        creative_name = creative_config["name"]
        ref_img = creative_config.get("reference_image", "") or DEFAULT_REF_IMG
        dl_final_name = f"{creative_name}_final.mp4"

        log(f"\n{'='*60}")
        log(f"🎬 加载创意: {creative_name}")
        log(f"   配置文件: {args.creative}")
        log(f"   参考图:   {ref_img}")
        log(f"{'='*60}")

        # 使用创意名称定制工作目录
        WORK_DIR = f".working_dir/{creative_name}"
        global STATE_FILE, LOG_FILE
        STATE_FILE = os.path.join(WORK_DIR, "task_state.json")
        LOG_FILE = os.path.join(WORK_DIR, "pipeline_log.txt")
        os.makedirs(WORK_DIR, exist_ok=True)
    else:
        creative_name = "singing_dancing"
        ref_img = DEFAULT_REF_IMG
        dl_final_name = DEFAULT_FINAL_NAME
        log(f"\n{'='*60}")
        log("🎬 使用默认硬编码创意参数")
        log(f"{'='*60}")

    # ── 加载场景脚本 ──
    script_path = args.script or os.path.join(WORK_DIR, "script.json")
    if not os.path.exists(script_path):
        log(f"错误: 脚本文件不存在: {script_path}")
        log("   请先运行 main_idea2video.py 生成场景脚本")
        sys.exit(1)

    with open(script_path) as f:
        scenes: List[str] = json.load(f)
    log(f"加载了 {len(scenes)} 个场景")

    video_paths: List[str] = []

    for scene_idx in range(len(scenes)):
        scene_dir = os.path.join(WORK_DIR, f"scene_{scene_idx}")
        os.makedirs(scene_dir, exist_ok=True)
        video_path = os.path.join(scene_dir, "video.mp4")

        if os.path.exists(video_path) and os.path.getsize(video_path) > 10000:
            log(f"Scene {scene_idx} exists, skip.")
            video_paths.append(video_path)
            tp = os.path.join(scene_dir, "transition_to_next.png")
            if os.path.exists(tp):
                state["current_image"] = tp
                save_state(state)
            continue

        log(f"\n{'='*50}")
        log(f"SCENE {scene_idx}")
        log(f"{'='*50}")

        # 检查是否有已存在的任务
        existing_tid = state.get(f"scene{scene_idx}_task_id")

        if scene_idx == 0:
            current_img = ref_img
        else:
            current_img = state.get("current_image", ref_img)

        # 上传图片
        if os.path.exists(current_img) and not current_img.startswith("http"):
            img_url = img_to_url(current_img)
        else:
            img_url = current_img
            log(f"  Using URL: {img_url[:80]}...")

        if existing_tid:
            log(f"  Checking existing task: {existing_tid[:30]}...")
            try:
                resp = requests.get(
                    f"{BASE_URL}/videos/{existing_tid}", headers=HEADERS, timeout=15
                )
                r = resp.json()
                st = r.get("status", "")
                if st in ("completed", "COMPLETED"):
                    vurl = (
                        r.get("video_url")
                        or r.get("url")
                        or r.get("remixed_from_video_id")
                    )
                    if vurl:
                        download(vurl, video_path)
                        video_paths.append(video_path)
                        state[f"scene{scene_idx}_url"] = vurl
                        save_state(state)
                        log("  Downloaded from existing task!")
                    else:
                        existing_tid = None
                elif st in ("failed", "FAILED"):
                    log("  Existing task failed, re-submitting...")
                    existing_tid = None
                else:
                    log(f"  Existing task still {st} {r.get('progress')}%, polling...")
                    vurl = poll_task(existing_tid)
                    download(vurl, video_path)
                    video_paths.append(video_path)
                    state[f"scene{scene_idx}_url"] = vurl
                    save_state(state)
            except Exception as e:
                log(f"  Error checking task: {e}")
                existing_tid = None

        if (
            not existing_tid
            or not os.path.exists(video_path)
            or os.path.getsize(video_path) < 10000
        ):
            tid = submit_video(scenes[scene_idx], img_url)
            state[f"scene{scene_idx}_task_id"] = tid
            save_state(state)
            vurl = poll_task(tid)
            download(vurl, video_path)
            video_paths.append(video_path)
            state[f"scene{scene_idx}_url"] = vurl
            save_state(state)

        # 场景串联：提取最后一帧并生成过渡帧
        if scene_idx + 1 < len(scenes):
            lf = os.path.join(scene_dir, "last_frame.jpg")
            extract_last_frame(video_path, lf)
            lf_url = img_to_url(lf)
            tp = os.path.join(scene_dir, f"transition_to_{scene_idx + 1}.png")
            gen_transition(lf_url, scenes[scene_idx + 1], tp)
            state["current_image"] = tp
            save_state(state)

    # ── 拼接最终视频 ──
    final = os.path.join(WORK_DIR, "final_video.mp4")
    if not os.path.exists(final) or os.path.getsize(final) < 10000:
        log(f"Concatenating {len(video_paths)} videos...")
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = [VideoFileClip(p) for p in video_paths]
        fc = concatenate_videoclips(clips, method="compose")
        fc.write_videofile(final, logger="bar")
        for c in clips:
            c.close()

    # 复制到下载目录
    dl = os.path.join(DEFAULT_DL_DIR, dl_final_name)
    os.makedirs(DEFAULT_DL_DIR, exist_ok=True)
    shutil.copy2(final, dl)
    log(f"\n🎉 ALL DONE! Final: {dl}")

    # 保存完成标记
    state["final_video"] = dl
    state["completed"] = True
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"PIPELINE ERROR: {e}")
        import traceback

        log(traceback.format_exc())
