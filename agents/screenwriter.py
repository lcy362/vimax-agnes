"""Screenwriter agent — develops story and writes scene scripts using Agnes chat API."""

import base64
import json
import logging
import mimetypes
import os
import requests
from typing import List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

BASE_URL = "https://apihub.agnes-ai.com/v1"


class Screenwriter:
    """Develops stories from ideas and writes scripts scene by scene."""

    def __init__(self, api_key: str, model: str = "agnes-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """Call Agnes chat API and return content."""
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=self.headers,
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Call chat API and parse JSON response."""
        content = self._chat(system_prompt, user_prompt)
        # Try to extract JSON from response
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)

    def _image_to_b64_uri(self, path: str) -> str:
        """Convert a local image file to base64 data URI."""
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        mime = mimetypes.guess_type(path)[0] or "image/png"
        return f"data:{mime};base64,{b64}"

    def _chat_multimodal(self, system_prompt: str, text_prompt: str, image_paths: List[str]) -> str:
        """Call Agnes chat API with images and return text content.

        Uses multimodal message format to send images alongside text.
        Falls back to text-only if no images are provided.
        """
        messages = [{"role": "system", "content": system_prompt}]

        # Build user message with text + images
        user_content = [{"type": "text", "text": text_prompt}]
        for img_path in image_paths:
            if img_path.startswith(("http://", "https://")):
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_path},
                })
            elif os.path.exists(img_path):
                b64_uri = self._image_to_b64_uri(img_path)
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": b64_uri},
                })
        messages.append({"role": "user", "content": user_content})

        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=self.headers,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def describe_images(self, image_paths: List[str]) -> str:
        """Describe a sequence of images in detail — what's happening, who is in them, the style, colors, mood.

        Returns a single narrative text that ties the images together, suitable
        for feeding into story development.

        Args:
            image_paths: List of local file paths or URLs (e.g. end_frame_images).

        Returns:
            A paragraph describing the image content in natural language.
        """
        if not image_paths:
            return ""

        system_prompt = """\
You are a visual analyst. Look at these images in order and describe them as a \
continuous narrative. For each image, note:

- Who or what is in the image (character appearance, body type, clothing, pose)
- The environment / setting (indoor, outdoor, weather, time of day)
- Color palette and lighting (warm/cool, bright/dim, time of day)
- Art style (realistic, anime, cartoon, illustration, etc.)
- Any emotional tone or mood conveyed
- What action or moment is captured (static pose, mid-action, etc.)
- How the images relate to each other as a progression

Write 3-5 sentences per image, then 1-2 sentences summarizing the overall \
visual story these images tell. Use descriptive, visual language — as if you \
were dictating to an AI video generator. Output as plain text, no JSON, no \
markdown formatting. Write in the same language the images suggest (Chinese \
if the content appears Chinese, English otherwise). Do NOT mention \
"the image shows" or "in this image" — just describe the content directly.
"""
        user_text = f"Describe these {len(image_paths)} images in sequence."

        print(f"🔍 正在分析 {len(image_paths)} 张图片内容...", flush=True)
        logger.info(f"[Screenwriter] Describing {len(image_paths)} images via multimodal chat...")
        descriptions = self._chat_multimodal(system_prompt, user_text, image_paths)
        logger.info(f"[Screenwriter] Image descriptions: {len(descriptions)} chars")
        print(f"✅ 图片内容分析完成", flush=True)
        return descriptions

    def develop_story(self, idea: str, user_requirement: str, style: str, image_context: str = "") -> str:
        """Expand an idea into a full story.

        Args:
            image_context: Optional text describing images that accompany the idea.
                When provided, the story will be grounded in the visual content of
                these images rather than purely free-form.
        """
        system_prompt = """\
You are a seasoned creative story generation expert. You expand ideas into \
well-structured stories with clear scenes, characters, and dialogue.

[Output] A complete story in paragraphs with:
- Story Title
- Target Audience & Genre
- Story Outline (1 paragraph)
- Main Characters Introduction (with detailed appearance descriptions)
- Full Story Narrative (Introduction -> Development -> Climax -> Conclusion)

IMPORTANT: Write the story in the SAME LANGUAGE as the input idea.
Keep it concise but vivid, suitable for adaptation into short video scenes.
Include DETAILED character appearance descriptions (clothing, body type, \
hair, distinguishing features, color palette) to enable consistent image generation.
"""
        user_prompt = f"""\
<idea>
{idea}
</idea>

<user_requirement>
{user_requirement}
</user_requirement>

<style>
{style}
</style>
"""
        if image_context:
            user_prompt += f"""
<image_context>
The following describes actual images that will be used as keyframes in the video.
The story MUST align with the visual content described below — use the same
characters, settings, colors, and mood.

{image_context}
</image_context>
"""
        print(f"📖 正在生成故事...", flush=True)
        logger.info("[Screenwriter] Developing story..." + (" (with image context)" if image_context else ""))
        story = self._chat(system_prompt, user_prompt)
        logger.info(f"[Screenwriter] Story developed: {len(story)} chars")
        print(f"✅ 故事生成完成", flush=True)
        return story

    def write_script(self, story: str, user_requirement: str, style: str) -> List[str]:
        """Write a script divided by scenes from a story.

        Each scene description is a detailed visual prompt suitable for
        AI video generation (in English for best results).
        """
        system_prompt = """\
You are a professional video director and visual prompt engineer. Adapt the \
given story into detailed visual scene descriptions for AI video generation.

[Output Format] Return a JSON object:
{
  "scenes": [
    "Scene 1 visual prompt (detailed English description for video generation)...",
    "Scene 2 visual prompt...",
    ...
  ]
}

Rules:
- Each scene MUST be a detailed VISUAL DESCRIPTION in ENGLISH, suitable for AI video generation.
- Do NOT include character names in angle brackets or dialogue tags.
- Focus on: camera movement, lighting, colors, environment, character actions, atmosphere, mood.
- Include specific visual details: lens type (wide/telephoto), depth of field, camera angle, \
lighting direction, color grading, particle effects, weather.
- Each scene should be 80-150 words, rich in cinematic detail.
- Maintain visual consistency across scenes (same character appearance, coherent world).
- Number of scenes MUST respect the user requirement constraints.
- The art style should match the requested style (realistic cinematic, anime, etc.).
- Describe MOTION and ACTION, not static images — this is for video generation.
"""
        user_prompt = f"""\
<story>
{story}
</story>

<user_requirement>
{user_requirement}
</user_requirement>

<style>
{style}
</style>
"""
        print(f"📝 正在编写脚本...", flush=True)
        logger.info("[Screenwriter] Writing script (visual prompts for video generation)...")
        result = self._chat_json(system_prompt, user_prompt)
        scenes = result.get("scenes", [])
        logger.info(f"[Screenwriter] Script written: {len(scenes)} scenes")
        print(f"✅ 脚本完成，共 {len(scenes)} 个场景", flush=True)
        return scenes

    def extract_character_description(self, story: str, style: str) -> str:
        """Extract a detailed character reference image prompt from the story.

        Returns a single prompt string suitable for generating a character
        reference image that can be reused across all scenes for consistency.
        """
        system_prompt = """\
You are a visual design expert. Your job is to extract a detailed image \
generation prompt for the MAIN CHARACTER from the story, suitable for \
generating a CHARACTER REFERENCE IMAGE.

The reference image should show the main character in a clear, full-body \
or three-quarter view pose, in a neutral standing position, with distinctive \
features clearly visible. The image should capture the character's appearance \
exactly as described in the story, including:

- Body type and posture
- Clothing and accessories
- Hair style and color
- Facial features and expressions
- Skin color, texture, or material (for non-human characters)
- Any distinguishing marks, scars, or features
- Color palette of the character

The prompt should be in ENGLISH regardless of the story language, for best \
image generation results. It should be a single paragraph, 3-5 sentences, \
rich in visual detail. Include the art style (e.g., "realistic cinematic", \
"anime style", "watercolor illustration").

Output ONLY the image prompt text, no JSON, no explanation.
"""
        user_prompt = f"""\
<story>
{story}
</story>

<style>{style}</style>
"""
        logger.info("[Screenwriter] Extracting character reference prompt...")
        prompt = self._chat(system_prompt, user_prompt).strip()
        # Remove any markdown wrapping
        if prompt.startswith("```"):
            prompt = prompt.split("\n", 1)[1]
            if prompt.endswith("```"):
                prompt = prompt[:-3]
            prompt = prompt.strip()
        logger.info(f"[Screenwriter] Character prompt: {prompt[:100]}...")
        return prompt

    def generate_end_frame_prompts(self, scenes: List[str], style: str) -> List[str]:
        """Generate end-of-scene frame image prompts for keyframes mode.

        For each scene, generates a detailed STATIC image prompt describing
        what the scene looks like at its END — this becomes the last keyframe
        for the keyframes video generation mode.

        Returns list of prompt strings, one per scene.
        """
        scenes_text = ""
        for i, scene in enumerate(scenes):
            scenes_text += f"\nScene {i}: {scene}\n"

        system_prompt = """\
You are a visual prompt engineer for AI image generation. For each video scene \
description below, generate a STATIC image prompt that represents what the scene \
looks like at its very END — the final frame of the video.

[Output Format] Return a JSON object:
{
  "end_frames": [
    "End frame image prompt for Scene 0 (STATIC, detailed, English)...",
    "End frame image prompt for Scene 1...",
    ...
  ]
}

Rules:
- Each prompt must describe a STATIC frozen moment, NOT motion or action verbs.
- The end frame must be visually consistent with the scene description — \
same character, same outfit, same environment, same lighting.
- Focus on: pose, facial expression, hand position, body posture, camera angle, \
lighting, background elements — everything visible in a single frozen frame.
- Include art style matching the scene (e.g., "realistic cinematic", "anime").
- The character's appearance (face, body, clothing) must remain EXACTLY the same \
across ALL end frames — only the pose, expression, and environment change.
- Each prompt should be 3-5 sentences, rich in visual detail.
- MUST be in ENGLISH for best image generation results.
"""
        user_prompt = f"""\
<style>{style}</style>

{scenes_text}
"""
        print(f"🎬 正在生成关键帧提示词...", flush=True)
        logger.info("[Screenwriter] Generating end frame prompts for keyframes mode...")
        result = self._chat_json(system_prompt, user_prompt)
        end_frames = result.get("end_frames", [])
        logger.info(f"[Screenwriter] Generated {len(end_frames)} end frame prompts")
        print(f"✅ 关键帧提示词完成，共 {len(end_frames)} 个", flush=True)
        return end_frames

    def design_shots_for_scene(self, scene_text: str, style: str, max_shots: int = 5) -> list:
        """Design shot-level storyboard for a single scene."""
        system_prompt = """\
You are a professional storyboard artist. Design shots for a single scene.

[Output Format] Return a JSON object:
{
  "shots": [
    {
      "visual_desc": "Overall visual description of the shot",
      "variation_type": "large|medium|small",
      "ff_desc": "First frame — static snapshot description",
      "lf_desc": "Last frame — static snapshot description",
      "motion_desc": "Motion between frames. Include dialogue as: <Char> says: \\"text\\"",
      "audio_desc": "[Sound Effect] description"
    }
  ]
}

Rules:
- First shot must establish the scene environment.
- Last shot should end the scene naturally.
- variation_type: "large" (big scene change), "medium" (new element appears), "small" (minor movement)
- First/last frame descriptions are STATIC images — no motion words.
- Motion description includes all movement AND dialogue.
- Include rich visual details for image generation (lighting, colors, composition).
- Output in the SAME LANGUAGE as the input scene.
"""
        user_prompt = f"""\
<scene>
{scene_text}
</scene>

<style>{style}</style>
<max_shots>{max_shots}</max_shots>
"""
        logger.info(f"[Screenwriter] Designing shots for scene...")
        result = self._chat_json(system_prompt, user_prompt)
        shots = result.get("shots", [])
        logger.info(f"[Screenwriter] Designed {len(shots)} shots")
        return shots
