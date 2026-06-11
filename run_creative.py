#!/usr/bin/env python3
"""ViMax-Agnes 统一创意启动脚本。

根据创意 YAML 配置文件自动判断使用哪种 pipeline 并调用。

用法:
    # 列出所有可用创意
    python run_creative.py --list

    # 运行指定创意
    python run_creative.py creatives/singing_dancing.yaml

    # 指定 API Key
    python run_creative.py creatives/singing_dancing.yaml -k "your-api-key"

    # 查看帮助
    python run_creative.py --help

环境变量:
    AGNES_API_KEY: Agnes API 密钥
"""

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import yaml

# 创意文件默认目录
CREATIVES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creatives")


def list_creatives(creatives_dir: str = CREATIVES_DIR) -> List[Dict[str, Any]]:
    """列出 creatives/ 目录下所有可用的创意配置。

    Args:
        creatives_dir: 创意配置目录路径。

    Returns:
        创意配置摘要列表，每个元素包含 name, path, idea_preview。
    """
    if not os.path.isdir(creatives_dir):
        print(f"错误: 创意目录不存在: {creatives_dir}")
        return []

    creatives: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(creatives_dir)):
        if not filename.endswith((".yaml", ".yml")):
            continue
        filepath = os.path.join(creatives_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                continue
            name = config.get("name", filename.rsplit(".", 1)[0])
            idea = config.get("idea", "")
            # 截取第一行作为预览
            idea_preview = idea.strip().split("\n")[0][:80] if idea else "(无描述)"
            chaining_mode = config.get("chaining_mode", "none")
            creatives.append({
                "name": name,
                "path": filepath,
                "idea_preview": idea_preview,
                "chaining_mode": chaining_mode,
            })
        except Exception as e:
            print(f"警告: 无法解析 {filename}: {e}", file=sys.stderr)

    return creatives


def print_creatives_list(creatives: List[Dict[str, Any]]) -> None:
    """格式化打印创意列表。

    Args:
        creatives: 创意配置摘要列表。
    """
    if not creatives:
        print("没有找到可用的创意配置。")
        print(f"请在 {CREATIVES_DIR} 目录下创建 .yaml 文件。")
        return

    print(f"\n{'='*60}")
    print(f"🎬 可用创意列表 ({len(creatives)} 个)")
    print(f"{'='*60}\n")

    for i, c in enumerate(creatives):
        print(f"  [{i}] {c['name']}")
        print(f"      文件:     {os.path.basename(c['path'])}")
        print(f"      描述:     {c['idea_preview']}...")
        print(f"      串联模式: {c['chaining_mode']}")
        print()


def load_creative_config(path: str) -> Dict[str, Any]:
    """从 YAML 文件加载创意配置。

    Args:
        path: YAML 创意配置文件路径。

    Returns:
        包含所有创意参数的字典。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: 缺少必需字段时抛出。
        yaml.YAMLError: YAML 解析错误时抛出。
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"创意配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    required_fields = ["name", "idea", "user_requirement", "style"]
    for field in required_fields:
        if field not in config or not config[field]:
            raise ValueError(f"创意配置文件缺少必需字段: {field}")

    return config


def resolve_api_key(cli_key: Optional[str] = None) -> str:
    """解析 API Key，优先级：命令行 > 环境变量 > 配置文件。

    Args:
        cli_key: 命令行传入的 API Key。

    Returns:
        解析后的 API Key。

    Raises:
        SystemExit: 未找到 API Key 时退出。
    """
    if cli_key:
        return cli_key

    key = os.environ.get("AGNES_API_KEY", "")
    if key:
        return key

    # 尝试从系统配置文件读取
    config_path = os.path.join(
        os.path.dirname(__file__), "configs", "idea2video.yaml"
    )
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
    print("   或使用 --api-key / -k 参数")
    sys.exit(1)


def detect_pipeline_type(config: Dict[str, Any]) -> str:
    """根据创意配置自动判断使用哪种 pipeline。

    判断逻辑：
    - 如果 chaining_mode 为 "keyframes" 或 "ti2vid"，使用标准 idea2video pipeline
    - 如果 reference_image 指向本地文件且需要上传，也使用标准 pipeline
    - 默认使用标准 idea2video pipeline

    Args:
        config: 创意配置字典。

    Returns:
        Pipeline 类型字符串: "idea2video" 或 "full"。
    """
    # 目前主要支持标准 idea2video pipeline
    # full pipeline 需要预先生成的 script.json，不适合自动化
    return "idea2video"


async def run_idea2video_pipeline(config: Dict[str, Any], api_key: str) -> str:
    """使用标准 Idea2Video pipeline 运行创意。

    Args:
        config: 创意配置字典。
        api_key: Agnes API Key。

    Returns:
        最终视频文件路径。
    """
    from pipelines.idea2video_pipeline import Idea2VideoPipeline

    config_path = os.path.join(
        os.path.dirname(__file__), "configs", "idea2video.yaml"
    )

    pipeline = Idea2VideoPipeline.init_from_config(config_path=config_path)

    # 覆盖 API Key
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

    # 使用创意名称定制工作目录
    creative_name = config["name"]
    pipeline.working_dir = os.path.join(".working_dir", creative_name)
    os.makedirs(pipeline.working_dir, exist_ok=True)

    final_path = await pipeline(
        idea=config["idea"],
        user_requirement=config["user_requirement"],
        style=config["style"],
        reference_image=config.get("reference_image", ""),
        chaining_mode=config.get("chaining_mode", "none"),
        video_width=config.get("video_width", 0),
        video_height=config.get("video_height", 0),
        end_frame_images=config.get("end_frame_images", None),
    )
    return final_path


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        配置好的 ArgumentParser 实例。
    """
    parser = argparse.ArgumentParser(
        description="ViMax-Agnes 统一创意启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_creative.py --list                          # 列出所有可用创意
  python run_creative.py creatives/singing_dancing.yaml  # 运行指定创意
  python run_creative.py creatives/example.yaml -k "key" # 指定 API Key
        """,
    )
    parser.add_argument(
        "creative",
        nargs="?",
        default=None,
        help="创意 YAML 配置文件路径",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        default=False,
        help="列出 creatives/ 目录下所有可用创意",
    )
    parser.add_argument(
        "--api-key", "-k",
        default=None,
        help="Agnes API Key（覆盖环境变量和配置文件）",
    )
    parser.add_argument(
        "--creatives-dir", "-d",
        default=CREATIVES_DIR,
        help=f"创意配置文件目录（默认: {CREATIVES_DIR}）",
    )
    return parser


def main() -> int:
    """主函数。

    Returns:
        退出码（0 表示成功）。
    """
    import logging
    import time as time_module

    log_dir = ".working_dir/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"run_{time_module.strftime('%Y%m%d_%H%M%S')}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logger = logging.getLogger(__name__)
    logger.info(f"日志文件: {log_file}")

    parser = build_parser()
    args = parser.parse_args()

    # ── --list 模式：列出所有可用创意 ──
    if args.list:
        creatives = list_creatives(args.creatives_dir)
        print_creatives_list(creatives)
        return 0

    # ── 需要提供创意文件 ──
    if not args.creative:
        parser.print_help()
        print("\n错误: 请提供创意 YAML 文件路径，或使用 --list 查看可用创意。")
        print("示例: python run_creative.py creatives/singing_dancing.yaml")
        return 1

    # ── 加载创意配置 ──
    try:
        creative_config = load_creative_config(args.creative)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("   使用 --list 查看可用创意")
        return 1
    except ValueError as e:
        print(f"错误: {e}")
        return 1
    except yaml.YAMLError as e:
        print(f"错误: YAML 解析失败: {e}")
        return 1

    # ── 解析 API Key ──
    try:
        api_key = resolve_api_key(args.api_key)
    except SystemExit:
        return 1

    # ── 打印加载信息 ──
    creative_name = creative_config["name"]
    chaining_mode = creative_config.get("chaining_mode", "none")
    vw = creative_config.get("video_width", 768)
    vh = creative_config.get("video_height", 1152)
    ref_img = creative_config.get("reference_image", "")

    print(f"\n{'='*60}")
    print(f"🎬 ViMax-Agnes 统一启动器")
    print(f"{'='*60}")
    print(f"   创意名称: {creative_name}")
    print(f"   配置文件: {args.creative}")
    print(f"   串联模式: {chaining_mode}")
    print(f"   视频尺寸: {vw}x{vh}")
    if ref_img:
        print(f"   参考图:   {ref_img}")
    else:
        print(f"   参考图:   (自动生成角色参考图)")
    end_frame_imgs = creative_config.get("end_frame_images", [])
    if end_frame_imgs:
        print(f"   自定义尾帧: {len(end_frame_imgs)} 张")
    print(f"   工作目录: .working_dir/{creative_name}")
    print(f"{'='*60}\n")

    # ── 检测并运行对应 pipeline ──
    pipeline_type = detect_pipeline_type(creative_config)
    print(f"📋 检测到 pipeline 类型: {pipeline_type}")

    if pipeline_type == "idea2video":
        final_path = asyncio.run(
            run_idea2video_pipeline(creative_config, api_key)
        )
    else:
        print(f"错误: 不支持的 pipeline 类型: {pipeline_type}")
        return 1

    print(f"\n✅ 完成! 最终视频: {final_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
