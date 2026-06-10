#!/usr/bin/env python3
"""ViMax-Agnes: Transform ideas into complete videos using Agnes AI.

Usage:
    # 从创意 YAML 文件加载（推荐）
    export AGNES_API_KEY="your-agnes-api-key"
    python main_idea2video.py creatives/singing_dancing.yaml

    # 使用自定义系统配置文件
    python main_idea2video.py creatives/singing_dancing.yaml -c configs/idea2video.yaml

    # 使用默认硬编码值（向后兼容）
    python main_idea2video.py

    # 查看帮助
    python main_idea2video.py --help
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

import yaml

from pipelines.idea2video_pipeline import Idea2VideoPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

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
DEFAULT_REFERENCE_IMAGE = "/home/z/my-project/upload/weixin-image.jpg"
DEFAULT_CHAINING_MODE = "keyframes"
DEFAULT_VIDEO_WIDTH = 768
DEFAULT_VIDEO_HEIGHT = 1152


def load_creative_config(path: str) -> Dict[str, Any]:
    """从 YAML 文件加载创意配置。

    Args:
        path: YAML 创意配置文件路径。

    Returns:
        包含所有创意参数的字典。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        yaml.YAMLError: YAML 解析错误时抛出。
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"创意配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 验证必需字段
    required_fields = ["name", "idea", "user_requirement", "style"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"创意配置文件缺少必需字段: {field}")

    return config


def resolve_api_key(cli_key: Optional[str] = None) -> str:
    """解析 API Key，优先级：命令行 > 环境变量 > 配置文件。

    Args:
        cli_key: 命令行传入的 API Key（可选）。

    Returns:
        解析后的 API Key 字符串。

    Raises:
        SystemExit: 未找到 API Key 时退出。
    """
    # 1. 命令行参数
    if cli_key:
        return cli_key

    # 2. 环境变量
    key = os.environ.get("AGNES_API_KEY", "")
    if key:
        return key

    # 3. 配置文件
    config_path = os.path.join(os.path.dirname(__file__), "configs", "idea2video.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        key = config.get("api_key", "")
        if key and key.startswith("${") and key.endswith("}"):
            env_name = key[2:-1]
            key = os.environ.get(env_name, "")
        if key:
            return key

    print("错误: 未设置 AGNES_API_KEY。")
    print("   请通过以下方式设置:")
    print("     export AGNES_API_KEY='your-api-key'")
    print("   或编辑 configs/idea2video.yaml")
    print("   或使用 --api-key / -k 参数")
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        配置好的 ArgumentParser 实例。
    """
    parser = argparse.ArgumentParser(
        description="ViMax-Agnes: 将创意转化为完整视频",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main_idea2video.py creatives/singing_dancing.yaml
  python main_idea2video.py creatives/example.yaml -k "your-api-key"
  python main_idea2video.py    # 使用默认硬编码值
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
        help="Agnes API Key（覆盖环境变量和配置文件）",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="系统配置文件路径（默认: configs/idea2video.yaml）",
    )
    return parser


async def main():
    """主函数：加载创意配置并运行视频生成流水线。"""
    import time as time_module

    log_dir = ".working_dir/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"main_{time_module.strftime('%Y%m%d_%H%M%S')}.log")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger().addHandler(file_handler)

    parser = build_parser()
    args = parser.parse_args()

    # 解析 API Key
    api_key = resolve_api_key(args.api_key)

    # 确定系统配置文件路径
    config_path = args.config or os.path.join(
        os.path.dirname(__file__), "configs", "idea2video.yaml"
    )

    # 确定创意参数
    if args.creative:
        # ── 从 YAML 文件加载创意参数 ──
        creative_config = load_creative_config(args.creative)
        idea = creative_config["idea"]
        user_requirement = creative_config["user_requirement"]
        style = creative_config["style"]
        reference_image = creative_config.get("reference_image", "")
        chaining_mode = creative_config.get("chaining_mode", "none")
        video_width = creative_config.get("video_width", DEFAULT_VIDEO_WIDTH)
        video_height = creative_config.get("video_height", DEFAULT_VIDEO_HEIGHT)

        print(f"\n{'='*60}")
        print(f"🎬 加载创意: {creative_config['name']}")
        print(f"   配置文件: {args.creative}")
        print(f"   串联模式: {chaining_mode}")
        print(f"   视频尺寸: {video_width}x{video_height}")
        if reference_image:
            print(f"   参考图:   {reference_image}")
        else:
            print(f"   参考图:   (自动生成角色参考图)")
        print(f"{'='*60}\n")
    else:
        # ── 使用默认硬编码值（向后兼容）──
        print(f"\n{'='*60}")
        print(f"🎬 使用默认硬编码创意参数（未指定 YAML 文件）")
        print(f"   提示: 可以使用 python main_idea2video.py creatives/singing_dancing.yaml")
        print(f"{'='*60}\n")

        idea = DEFAULT_IDEA
        user_requirement = DEFAULT_USER_REQUIREMENT
        style = DEFAULT_STYLE
        reference_image = DEFAULT_REFERENCE_IMAGE
        chaining_mode = DEFAULT_CHAINING_MODE
        video_width = DEFAULT_VIDEO_WIDTH
        video_height = DEFAULT_VIDEO_HEIGHT

    # 初始化流水线
    pipeline = Idea2VideoPipeline.init_from_config(config_path=config_path)

    # 使用环境变量或命令行 API Key 覆盖
    if api_key:
        pipeline.api_key = api_key
        pipeline.screenwriter.api_key = api_key
        pipeline.image_generator.api_key = api_key
        pipeline.video_generator.api_key = api_key
        for h in [
            pipeline.screenwriter.headers,
            pipeline.image_generator.headers,
            pipeline.video_generator.headers,
        ]:
            h["Authorization"] = f"Bearer {api_key}"

    final_path = await pipeline(
        idea=idea,
        user_requirement=user_requirement,
        style=style,
        reference_image=reference_image,
        chaining_mode=chaining_mode,
        video_width=video_width,
        video_height=video_height,
    )
    print(f"\n✅ 完成! 最终视频: {final_path}")


if __name__ == "__main__":
    asyncio.run(main())
