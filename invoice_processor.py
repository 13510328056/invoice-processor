#!/usr/bin/env python3
"""
发票批处理工具 — CLI 入口

用法：
    python invoice_processor.py ./发票文件夹
    python invoice_processor.py ./发票文件夹 -v
    python invoice_processor.py ./发票文件夹 --config ./myconf.yaml
    python invoice_processor.py ./发票文件夹 --gui
    python invoice_processor.py --init-config
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    """CLI 入口函数"""
    parser = argparse.ArgumentParser(
        description="发票批处理工具 — 批量识别、提取与结构化导出电子发票",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python invoice_processor.py ./invoices
  python invoice_processor.py ./invoices -v
  python invoice_processor.py ./invoices --config ./prod_config.yaml
  python invoice_processor.py --gui
        """,
    )

    parser.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="发票文件夹路径（留空则使用 --gui 或当前目录）",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径（默认: config.yaml）",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="启用 DEBUG 级别日志",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="启用图形化文件夹选择对话框",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="生成默认配置文件 config.yaml",
    )

    args = parser.parse_args()

    # ── 初始化配置 ──
    if args.init_config:
        _init_default_config()
        return

    # ── 配置日志 ──
    from src.utils.logger import setup_logging
    from src.config.loader import load_config

    config = load_config(args.config)
    setup_logging(
        level=config.logging.level,
        log_file=config.logging.file if config.logging.file else None,
        verbose=args.verbose,
    )

    import logging
    logger = logging.getLogger(__name__)

    # ── 确定目录 ──
    root_dir = args.directory

    if args.gui or not root_dir:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root_dir = filedialog.askdirectory(title="选择发票文件夹")
            root.destroy()
            if not root_dir:
                logger.info("用户取消了文件夹选择")
                return
        except ImportError:
            logger.error("GUI 模式需要 tkinter，请使用命令行指定目录")
            sys.exit(1)

    if not root_dir:
        logger.error("请指定发票文件夹路径，或使用 --gui 参数")
        sys.exit(1)

    root_dir = str(Path(root_dir).resolve())

    # ── 运行管线 ──
    from src.pipeline.orchestrator import run_pipeline

    output_path = run_pipeline(root_dir, config)

    if output_path:
        logger.info(f"处理完成，输出文件: {output_path}")
    else:
        logger.error("处理失败")
        sys.exit(1)


def _init_default_config() -> None:
    """生成默认配置文件"""
    from src.config.defaults import (
        DEFAULT_OUTPUT_CONFIG,
        DEFAULT_OCR_CONFIG,
        DEFAULT_OCT_CONFIG,
        DEFAULT_OFD_CONFIG,
        DEFAULT_PROCESSING_CONFIG,
        DEFAULT_EXTRACTION_CONFIG,
        DEFAULT_LOGGING_CONFIG,
    )
    import yaml

    config_path = Path("config.yaml")

    if config_path.exists():
        print(f"配置文件已存在: {config_path}")
        overwrite = input("是否覆盖？(y/N): ").strip().lower()
        if overwrite != "y":
            print("已取消")
            return

    default_config = {
        "output": DEFAULT_OUTPUT_CONFIG,
        "ocr": DEFAULT_OCR_CONFIG,
        "ofd": DEFAULT_OFD_CONFIG,
        "processing": DEFAULT_PROCESSING_CONFIG,
        "extraction": DEFAULT_EXTRACTION_CONFIG,
        "logging": DEFAULT_LOGGING_CONFIG,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)

    print(f"默认配置文件已生成: {config_path}")


if __name__ == "__main__":
    main()
