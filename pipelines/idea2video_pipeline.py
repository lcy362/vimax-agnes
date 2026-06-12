"""Idea2Video Pipeline — orchestrates the full idea-to-video generation flow.

Flow:
  idea -> story -> character reference image -> script (scenes) -> videos -> final

Chaining modes:
  - "none": each scene independent, same reference image (ti2vid)
  - "ti2vid": sequential, img2img transition between scenes
  - "keyframes": sequential, first+last frame keyframes for smooth transitions
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess

import yaml
from moviepy import VideoFileClip, concatenate_videoclips

from agents.screenwriter import Screenwriter
from tools.image_generator_agnes_api import ImageGeneratorAgnesAPI
from tools.video_generator_agnes_api import VideoGeneratorAgnesAPI

logger = logging.getLogger(__name__)


class Idea2VideoPipeline:
    """End-to-end pipeline: idea -> story -> character ref -> scenes -> videos -> final."""

    def __init__(
        self,
        api_key: str,
        chat_model: str = "agnes-2.0-flash",
        image_model: str = "agnes-image-2.1-flash",
        video_model: str = "agnes-video-v2.0",
        video_duration: int = 5,
        video_width: int = 1152,
        video_height: int = 768,
        working_dir: str = ".working_dir/idea2video",
    ):
        self.api_key = api_key
        self.video_duration = video_duration
        self.video_width = video_width
        self.video_height = video_height
        self.working_dir = working_dir
        os.makedirs(working_dir, exist_ok=True)

        self.screenwriter = Screenwriter(api_key=api_key, model=chat_model)
        self.image_generator = ImageGeneratorAgnesAPI(api_key=api_key, model=image_model)
        self.video_generator = VideoGeneratorAgnesAPI(
            api_key=api_key, model=video_model, default_duration=video_duration
        )

    @classmethod
    def init_from_config(cls, config_path: str) -> "Idea2VideoPipeline":
        """Initialize pipeline from YAML config file."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        api_key = (
            config.get("api_key")
            or os.environ.get("AGNES_API_KEY", "")
        )
        chat_cfg = config.get("chat_model", {}).get("init_args", {})
        img_cfg = config.get("image_generator", {}).get("init_args", {})
        vid_cfg = config.get("video_generator", {}).get("init_args", {})

        if not img_cfg.get("api_key"):
            img_cfg["api_key"] = api_key
        if not vid_cfg.get("api_key"):
            vid_cfg["api_key"] = api_key
        if not chat_cfg.get("api_key"):
            chat_cfg["api_key"] = api_key

        return cls(
            api_key=api_key,
            chat_model=chat_cfg.get("model", "agnes-2.0-flash"),
            image_model=img_cfg.get("model", "agnes-image-2.1-flash"),
            video_model=vid_cfg.get("model", "agnes-video-v2.0"),
            video_duration=vid_cfg.get("default_duration", 5),
            video_width=vid_cfg.get("width", 1152),
            video_height=vid_cfg.get("height", 768),
            working_dir=config.get("working_dir", ".working_dir/idea2video"),
        )

    # ────────────────────────────────────────────────────
    # Step: Generate character reference image
    # ────────────────────────────────────────────────────

    async def _get_character_reference(self, story: str, style: str) -> str:
        """Generate (or load cached) character reference image. Returns local file path."""
        ref_prompt_path = os.path.join(self.working_dir, "character_ref_prompt.txt")
        ref_img_path = os.path.join(self.working_dir, "character_reference.png")

        # Check cache
        if os.path.exists(ref_img_path) and os.path.exists(ref_prompt_path):
            logger.info("Character reference image loaded from cache.")
            return ref_img_path

        # Extract character description from story
        char_prompt = self.screenwriter.extract_character_description(story, style)
        with open(ref_prompt_path, "w") as f:
            f.write(char_prompt)

        # Generate reference image
        print(f"\n{'='*60}")
        print(f"🎨 CHARACTER REFERENCE PROMPT:\n{char_prompt}")
        print(f"{'='*60}\n")

        print("🖼️ Generating character reference image...")
        img_output = await self.image_generator.generate_single_image(
            prompt=char_prompt,
            size="1152x768",
        )
        img_output.save(ref_img_path)
        logger.info(f"Character reference saved: {ref_img_path}")
        print(f"✅ Character reference image saved: {ref_img_path}")

        return ref_img_path

    # ────────────────────────────────────────────────────
    # Pre-generate all end frames (i2i with reference image)
    # ────────────────────────────────────────────────────

    async def _pregenerate_all_end_frames(
        self,
        scenes: list,
        end_frame_prompts: list,
        reference_image: str,
        vw: int = 1152,
        vh: int = 768,
        end_frame_images: list = None,
    ) -> dict:
        """Pre-generate all scene end frames using i2i with reference image.

        Each scene's end frame is generated individually via image-to-image,
        using the character reference image as the visual anchor. Custom
        end frames provided by the user take priority.

        Returns a dict mapping scene_idx -> end_frame_path.
        """
        print(f"\n{'='*60}")
        print(f"🖼️  预生成所有场景尾帧 (共 {len(scenes)} 个场景)")
        print(f"   参考图: {os.path.basename(reference_image) if os.path.exists(reference_image) else reference_image}")
        print(f"   模式: i2i (基于参考图)")
        print(f"{'='*60}\n")

        pregenerated = {}

        for scene_idx in range(len(scenes)):
            scene_dir = os.path.join(self.working_dir, f"scene_{scene_idx}")
            os.makedirs(scene_dir, exist_ok=True)
            end_frame_path = os.path.join(scene_dir, "end_frame.png")

            user_ef = (
                end_frame_images[scene_idx]
                if end_frame_images and scene_idx < len(end_frame_images) and end_frame_images[scene_idx]
                else None
            )

            if user_ef:
                print(f"📸 [场景 {scene_idx+1}/{len(scenes)}] 使用自定义尾帧: {user_ef}", flush=True)
                if os.path.exists(user_ef):
                    dest = os.path.join(scene_dir, "end_frame.png")
                    subprocess.run([
                        "ffmpeg", "-y", "-i", user_ef,
                        "-vf", f"scale={vw}:{vh}:force_original_aspect_ratio=decrease,pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2",
                        dest
                    ], capture_output=True, check=True, timeout=30)
                    end_frame_path = dest
                    print(f"  📐 已适配尺寸: {vw}x{vh}", flush=True)
                pregenerated[scene_idx] = end_frame_path
                continue

            if os.path.exists(end_frame_path):
                print(f"📦 [场景 {scene_idx+1}/{len(scenes)}] 尾帧已缓存，跳过生成", flush=True)
                pregenerated[scene_idx] = end_frame_path
                continue

            end_frame_prompt = end_frame_prompts[scene_idx]
            print(f"🖼️  [场景 {scene_idx+1}/{len(scenes)}] 基于参考图生成尾帧 (i2i)...", flush=True)
            logger.info(f"[EndFrame] Generating {scene_idx+1}/{len(scenes)} via i2i: {end_frame_prompt[:80]}...")

            for attempt in range(3):
                try:
                    img_output = await self.image_generator.generate_single_image(
                        prompt=end_frame_prompt,
                        reference_image_paths=[reference_image],
                        size=f"{vw}x{vh}",
                    )
                    img_output.save(end_frame_path)
                    pregenerated[scene_idx] = end_frame_path
                    print(f"✅ [场景 {scene_idx+1}/{len(scenes)}] 尾帧已保存: {end_frame_path}", flush=True)
                    logger.info(f"[EndFrame] Scene {scene_idx} saved: {end_frame_path}")
                    break
                except Exception as e:
                    if attempt < 2:
                        wait = (attempt + 1) * 10
                        logger.warning(f"[EndFrame] Scene {scene_idx} attempt {attempt+1} failed: {e}, retrying in {wait}s...")
                        print(f"  ⚠️ 第 {attempt+1} 次尝试失败，{wait}s 后重试...", flush=True)
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"[EndFrame] Scene {scene_idx} failed after 3 attempts: {e}")
                        print(f"❌ [场景 {scene_idx+1}/{len(scenes)}] 尾帧生成失败: {e}", flush=True)
                        raise

            if scene_idx < len(scenes) - 1:
                await asyncio.sleep(2)

        print(f"\n✅ 尾帧预生成全部完成 ({len(pregenerated)}/{len(scenes)})")
        return pregenerated

    # ────────────────────────────────────────────────────
    # Scene Chaining: sequential generation with frame continuity
    # ────────────────────────────────────────────────────

    async def _extract_last_frame(self, video_path: str, output_path: str) -> str:
        """Extract the last frame from a video using ffmpeg. Returns output_path."""
        cmd = [
            "ffmpeg", "-y",
            "-sseof", "-1",
            "-i", video_path,
            "-frames:v", "1",
            "-update", "1",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        return output_path

    # ────────────────────────────────────────────────────
    # Keyframes Chaining: first+last frame for each scene
    # ────────────────────────────────────────────────────

    async def _generate_keyframe_chained_scenes(
        self,
        scenes: list,
        end_frame_prompts: list,
        reference_image: str,
        vw: int = 1152,
        vh: int = 768,
        end_frame_images: list = None,
    ) -> list:
        """Generate scenes with keyframes chaining (first + last frame).

        Two-phase approach:
          1. Submit all video tasks at once (so they process in parallel on server)
          2. Wait for results sequentially

        All end frames are pre-generated before this method is called, so
        there is no inter-scene dependency on video generation order.

        Returns list of video file paths.
        """
        current_first_frame = reference_image
        BASE_URL = "https://apihub.agnes-ai.com/v1"

        def _make_curl(video_id: str) -> str:
            return f'curl -s -H "Authorization: Bearer $AGNES_API_KEY" "{BASE_URL}/videos/{video_id}"'

        def _save_task(scene_dir: str, video_id: str):
            task_file = os.path.join(scene_dir, "task.json")
            with open(task_file, "w") as f:
                json.dump({"video_id": video_id}, f, indent=2)
            curl_file = os.path.join(scene_dir, "curl.sh")
            with open(curl_file, "w") as f:
                f.write(_make_curl(video_id) + "\n")

        def _load_task(scene_dir: str):
            task_file = os.path.join(scene_dir, "task.json")
            if os.path.exists(task_file):
                try:
                    with open(task_file, "r") as f:
                        data = json.load(f)
                    return data.get("video_id") or data.get("task_id")
                except Exception:
                    pass
            return None

        # ── Phase 0: Collect scenes that need generation ──
        pending = []
        for scene_idx, scene_text in enumerate(scenes):
            scene_dir = os.path.join(self.working_dir, f"scene_{scene_idx}")
            os.makedirs(scene_dir, exist_ok=True)
            video_path = os.path.join(scene_dir, "video.mp4")

            if os.path.exists(video_path):
                logger.info(f"Scene {scene_idx} exists, skipping.")
                end_frame_path = os.path.join(scene_dir, "end_frame.png")
                if os.path.exists(end_frame_path):
                    current_first_frame = end_frame_path
                continue

            # Check if this scene was already submitted (resume after restart)
            existing_video_id = _load_task(scene_dir)
            if existing_video_id:
                logger.info(f"Scene {scene_idx}: resuming from video {existing_video_id[:20]}...")
                end_frame_path = os.path.join(scene_dir, "end_frame.png")
                print(f"📦 Scene {scene_idx}: 从 task.json 恢复 (video: {existing_video_id[:20]}...)", flush=True)
                print(f"  🔍 手动查询: {_make_curl(existing_video_id)}", flush=True)
                pending.append({
                    "scene_idx": scene_idx,
                    "video_path": video_path,
                    "video_id": existing_video_id,
                    "scene_dir": scene_dir,
                    "already_submitted": True,
                })
                current_first_frame = end_frame_path
                continue

            # Resolve end frame
            user_ef = (
                end_frame_images[scene_idx]
                if end_frame_images and scene_idx < len(end_frame_images) and end_frame_images[scene_idx]
                else None
            )
            if user_ef:
                print(f"📸 Scene {scene_idx}: 使用自定义尾帧: {user_ef}", flush=True)
                if os.path.exists(user_ef):
                    dest = os.path.join(scene_dir, "end_frame.png")
                    subprocess.run([
                        "ffmpeg", "-y", "-i", user_ef,
                        "-vf", f"scale={vw}:{vh}:force_original_aspect_ratio=decrease,pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2",
                        dest
                    ], capture_output=True, check=True, timeout=30)
                    end_frame_path = dest
                else:
                    end_frame_path = user_ef
            else:
                end_frame_path = os.path.join(scene_dir, "end_frame.png")
                if not os.path.exists(end_frame_path):
                    end_frame_prompt = end_frame_prompts[scene_idx]
                    print(f"  🖼️ 自动生成尾帧 (t2i)...", flush=True)
                    img_output = await self.image_generator.generate_single_image(
                        prompt=end_frame_prompt,
                        size=f"{vw}x{vh}",
                    )
                    img_output.save(end_frame_path)
                    print(f"  ✅ 自动生成完成: {end_frame_path}", flush=True)

            # Upload both frames to hosted URLs
            first_frame_url = self.video_generator._resolve_image_ref(current_first_frame)
            end_frame_url = self.video_generator._resolve_image_ref(end_frame_path)

            pending.append({
                "scene_idx": scene_idx,
                "scene_text": scene_text,
                "video_path": video_path,
                "first_frame_url": first_frame_url,
                "end_frame_url": end_frame_url,
                "end_frame_path": end_frame_path,
                "scene_dir": scene_dir,
                "already_submitted": False,
            })

            current_first_frame = end_frame_path

        # ── Phase 1: Submit pending video tasks (skip already-submitted) ──
        new_submissions = [i for i in pending if not i.get("already_submitted")]
        if new_submissions:
            print(f"\n{'='*60}")
            print(f"🎬 提交 {len(new_submissions)} 个视频任务 (keyframes)")
            print(f"{'='*60}")

        for info in new_submissions:
            scene_idx = info["scene_idx"]
            print(f"  📤 提交 Scene {scene_idx}...", flush=True)
            video_id = self.video_generator.submit_video(
                prompt=info["scene_text"],
                reference_image_paths=[info["first_frame_url"], info["end_frame_url"]],
                duration=self.video_duration,
                width=vw,
                height=vh,
            )
            info["video_id"] = video_id
            info["already_submitted"] = True
            _save_task(info["scene_dir"], video_id)
            print(f"  ✅ Scene {scene_idx} 已提交 (video: {video_id[:20]}...)", flush=True)
            print(f"  🔍 手动查询: {_make_curl(video_id)}", flush=True)

        # ── Phase 2: Wait for results sequentially ──
        if pending:
            print(f"\n{'='*60}")
            print(f"⏳ 等待 {len(pending)} 个视频生成完成...")
            print(f"{'='*60}")

        for info in pending:
            scene_idx = info["scene_idx"]
            print(f"\n{'─'*50}")
            print(f"🎞️  Scene {scene_idx} (keyframes chain)")
            print(f"  ⏳ 等待视频生成完成...", flush=True)
            try:
                video_output = await self.video_generator.wait_for_video(info["video_id"])
                video_output.save(info["video_path"])
                print(f"  ✅ Video saved: {info['video_path']}")
            except Exception as e:
                logger.error(f"Scene {scene_idx} video failed: {e}")
                print(f"  ❌ Scene {scene_idx} 视频生成失败: {e}", flush=True)
                task_file = os.path.join(info["scene_dir"], "task.json")
                if os.path.exists(task_file):
                    os.remove(task_file)
                    logger.info(f"Removed {task_file} for retry on next run")
                raise

        # Collect all video paths in scene order
        all_video_paths = []
        for scene_idx in range(len(scenes)):
            video_path = os.path.join(self.working_dir, f"scene_{scene_idx}", "video.mp4")
            if os.path.exists(video_path):
                all_video_paths.append(video_path)

        return all_video_paths

    # ────────────────────────────────────────────────────
    # Scene Chaining (ti2vid + img2img transition): original mode
    # ────────────────────────────────────────────────────

    async def _generate_chained_scenes(self, scenes: list, reference_image: str, vw: int = 1152, vh: int = 768) -> list:
        """Generate scenes sequentially with frame chaining for continuity.

        Flow for each scene:
          1. Use current_image as ti2vid first frame -> generate video
          2. Extract last frame from video via ffmpeg
          3. Upload last frame via img2img API to get hosted URL
          4. Use img2img to generate next scene's starting frame
          5. Repeat until all scenes done

        Returns list of video file paths.
        """
        all_video_paths = []
        current_image = reference_image

        for scene_idx, scene_text in enumerate(scenes):
            print(f"\n{'─'*50}")
            print(f"🔗 Scene {scene_idx} (chained)")
            print(f"{'─'*50}")

            scene_dir = os.path.join(self.working_dir, f"scene_{scene_idx}")
            os.makedirs(scene_dir, exist_ok=True)
            video_path = os.path.join(scene_dir, "video.mp4")

            # Skip if video already exists
            if os.path.exists(video_path):
                logger.info(f"Scene {scene_idx} exists, skipping.")
                all_video_paths.append(video_path)
                last_frame_path = os.path.join(scene_dir, "last_frame.jpg")
                if os.path.exists(last_frame_path):
                    current_image = last_frame_path
                continue

            # Step A: Generate video with ti2vid using current_image as first frame
            print(f"  🎬 Generating video (ti2vid, scene {scene_idx})...")
            video_output = await self.video_generator.generate_single_video(
                prompt=scene_text,
                reference_image_paths=[current_image],
                duration=self.video_duration,
                width=vw,
                height=vh,
            )
            video_output.save(video_path)
            all_video_paths.append(video_path)
            print(f"  ✅ Video saved: {video_path}")

            # Step B: Extract last frame (only if there's a next scene)
            if scene_idx + 1 < len(scenes):
                last_frame_path = os.path.join(scene_dir, "last_frame.jpg")
                await self._extract_last_frame(video_path, last_frame_path)
                print(f"  🖼️  Last frame extracted: {last_frame_path}")

                # Step C: Upload last frame to get hosted URL
                last_frame_url = self.video_generator._resolve_image_ref(last_frame_path)
                print(f"  📤 Last frame uploaded to hosted URL")

                # Step D: Generate transition frame for next scene via img2img
                next_scene_text = scenes[scene_idx + 1]
                transition_prompt = (
                    f"Cinematic transition frame, blending the end of the current scene "
                    f"into the beginning of the next. Keep the same person and face exactly. "
                    f"Next scene: {next_scene_text[:200]}"
                )
                transition_path = os.path.join(scene_dir, f"transition_to_{scene_idx+1}.png")

                print(f"  🔄 Generating transition frame for scene {scene_idx+1}...")
                img_output = await self.image_generator.generate_single_image(
                    prompt=transition_prompt,
                    reference_image_paths=[last_frame_url],
                    size="768x1152",
                )
                img_output.save(transition_path)
                current_image = transition_path
                print(f"  ✅ Transition frame saved: {transition_path}")

        return all_video_paths

    # ────────────────────────────────────────────────────
    # Main pipeline
    # ────────────────────────────────────────────────────

    async def run(
        self,
        idea: str,
        user_requirement: str,
        style: str,
        reference_image: str = "",
        chaining_mode: str = "none",
        video_width: int = 0,
        video_height: int = 0,
        end_frame_images: list = None,
    ) -> str:
        """Run the full pipeline and return the path to the final video.

        Args:
            idea: Creative concept / story idea.
            user_requirement: Constraints (audience, scenes, duration, etc.).
            style: Visual style (e.g. "Realistic", "Anime", "Cartoon").
            reference_image: Optional path or URL to a reference image.
                If provided, this image is used as the first-frame reference
                for ALL scene videos (ti2vid mode) instead of auto-generating
                a character reference. Supports local file paths and URLs.
            chaining_mode: Scene chaining strategy.
                - "none": each scene independent, same reference image (default)
                - "ti2vid": sequential with img2img transition frames
                - "keyframes": sequential with first+last frame keyframes
            video_width: Video width in pixels (0 = use default from config).
            video_height: Video height in pixels (0 = use default from config).
        """
        # Resolve video dimensions
        vw = video_width or self.video_width
        vh = video_height or self.video_height

        # ── Step 0: Analyze provided images (reference + end_frames) ──
        image_context = ""
        # Collect all user-provided images: reference_image first, then end_frame_images
        images_to_analyze = []
        if reference_image:
            ref_valid = reference_image.startswith(("http://", "https://")) or os.path.exists(reference_image)
            if ref_valid:
                images_to_analyze.append(reference_image)
        if end_frame_images:
            for p in end_frame_images:
                if p and (p.startswith(("http://", "https://")) or os.path.exists(p)):
                    images_to_analyze.append(p)

        if images_to_analyze:
            print(f"\n{'='*60}")
            print(f"🔍 Step 0: 图片内容分析")
            print(f"{'='*60}")
            print(f"   图片数量: {len(images_to_analyze)} 张")
            for i, img in enumerate(images_to_analyze):
                label = "起始帧" if i == 0 else f"尾帧 {i-1}"
                display = os.path.basename(img) if os.path.exists(img) else img[:60]
                print(f"   [{label}] {display}")
            print()
            # describe_images handles incremental caching internally
            image_context = self.screenwriter.describe_images(images_to_analyze, cache_dir=self.working_dir)
            print(f"\n📸 分析结果 ({len(image_context)} 字符):")
            print(f"   {image_context[:250]}...")
            print()

        # ── Step 1: Develop Story ──
        story_path = os.path.join(self.working_dir, "story.txt")
        if os.path.exists(story_path):
            with open(story_path, "r") as f:
                story = f.read()
            logger.info("Story loaded from cache.")
        else:
            story = self.screenwriter.develop_story(idea, user_requirement, style, image_context)
            with open(story_path, "w") as f:
                f.write(story)
            logger.info(f"Story saved to {story_path}")

        print(f"\n{'='*60}")
        print(f"📖 STORY:\n{story[:500]}...")
        print(f"{'='*60}\n")

        # ── Step 2: Character Reference Image ──
        # This ensures character consistency across all scenes.
        # If the user provided a reference image, use it directly;
        # otherwise, auto-generate one from the story's character description.
        if reference_image:
            character_ref_path = reference_image
            logger.info(f"Using user-provided reference image: {reference_image}")
            print(f"📌 Using user-provided reference image: {reference_image}")
        else:
            character_ref_path = await self._get_character_reference(story, style)

        # ── Step 3: Write Script ──
        script_path = os.path.join(self.working_dir, "script.json")
        if os.path.exists(script_path):
            with open(script_path, "r") as f:
                scenes = json.load(f)
            logger.info(f"Script loaded from cache ({len(scenes)} scenes).")
        else:
            scenes = self.screenwriter.write_script(story, user_requirement, style)
            with open(script_path, "w") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            logger.info(f"Script saved ({len(scenes)} scenes)")

        print(f"🎬 SCENES: {len(scenes)}")
        for i, scene in enumerate(scenes):
            print(f"  Scene {i}: {scene[:100]}...")
        print(f"📌 Character reference: {character_ref_path}")
        print(f"🔗 Chaining mode: {chaining_mode}")
        print()

        # ── Step 4: For each scene -> generate video ──
        all_video_paths = []

        if chaining_mode == "keyframes":
            # Keyframes chaining: first+last frame for each scene
            # Generate end-frame prompts for each scene
            end_frames_path = os.path.join(self.working_dir, "end_frame_prompts.json")
            if os.path.exists(end_frames_path):
                with open(end_frames_path, "r") as f:
                    end_frame_prompts = json.load(f)
                logger.info("End frame prompts loaded from cache.")
            else:
                character_appearance = self.screenwriter.get_character_appearance(story)
                end_frame_prompts = self.screenwriter.generate_end_frame_prompts(
                    scenes, style, character_appearance
                )
                with open(end_frames_path, "w") as f:
                    json.dump(end_frame_prompts, f, ensure_ascii=False, indent=2)

            print(f"🖼️  END FRAME PROMPTS:")
            for i, p in enumerate(end_frame_prompts):
                print(f"  End Frame {i}: {p[:100]}...")
            print()

            pregenerated_end_frames = await self._pregenerate_all_end_frames(
                scenes, end_frame_prompts, character_ref_path, vw, vh, end_frame_images
            )

            all_video_paths = await self._generate_keyframe_chained_scenes(
                scenes, end_frame_prompts, character_ref_path, vw, vh, end_frame_images
            )

        elif chaining_mode == "ti2vid":
            # Scene chaining: sequential generation with frame continuity
            all_video_paths = await self._generate_chained_scenes(
                scenes, character_ref_path, vw, vh
            )
        else:
            # Original parallel mode: same reference image for all scenes
            for scene_idx, scene_text in enumerate(scenes):
                print(f"\n{'─'*50}")
                print(f"🎥 Processing Scene {scene_idx}")
                print(f"{'─'*50}")

                scene_dir = os.path.join(self.working_dir, f"scene_{scene_idx}")
                os.makedirs(scene_dir, exist_ok=True)

                video_path = os.path.join(scene_dir, "video.mp4")

                # Skip if video already exists
                if os.path.exists(video_path):
                    logger.info(f"Scene {scene_idx} video exists, skipping.")
                    all_video_paths.append(video_path)
                    continue

                # Generate video using character reference image (ti2vid mode)
                print(f"  🎬 Generating video for scene {scene_idx} (ti2vid with character ref)...")
                video_output = await self.video_generator.generate_single_video(
                    prompt=scene_text,
                    reference_image_paths=[character_ref_path],
                    duration=self.video_duration,
                    width=vw,
                    height=vh,
                )
                video_output.save(video_path)
                logger.info(f"  ✅ Video saved: {video_path}")
                all_video_paths.append(video_path)

        # ── Step 5: Concatenate all scene videos ──
        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(final_video_path):
            logger.info(f"Final video already exists: {final_video_path}")
        elif len(all_video_paths) > 1:
            logger.info(f"Concatenating {len(all_video_paths)} scene videos...")
            clips = [VideoFileClip(p) for p in all_video_paths]
            final = concatenate_videoclips(clips, method="compose")
            final.write_videofile(final_video_path, logger="bar")
            for c in clips:
                c.close()
            logger.info(f"Final video: {final_video_path}")
        elif all_video_paths:
            shutil.copy2(all_video_paths[0], final_video_path)
            logger.info(f"Final video (single scene): {final_video_path}")
        else:
            raise RuntimeError("No videos were generated!")

        print(f"\n{'='*60}")
        print(f"🎉 FINAL VIDEO: {final_video_path}")
        print(f"{'='*60}\n")

        return final_video_path

    async def __call__(
        self,
        idea: str,
        user_requirement: str,
        style: str,
        reference_image: str = "",
        chaining_mode: str = "none",
        video_width: int = 0,
        video_height: int = 0,
        end_frame_images: list = None,
    ) -> str:
        """Alias for run()."""
        return await self.run(
            idea=idea,
            user_requirement=user_requirement,
            style=style,
            reference_image=reference_image,
            chaining_mode=chaining_mode,
            video_width=video_width,
            video_height=video_height,
            end_frame_images=end_frame_images,
        )
