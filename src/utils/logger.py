"""
发票批处理工具 — 日志框架

支持自定义 SUCCESS 日志级别、控制台和文件双输出
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

# ── 自定义 SUCCESS 日志级别 (介于 INFO 与 WARNING 之间) ──
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


class SuccessLogger(logging.Logger):
    """支持 success() 方法的 Logger"""

    def success(self, msg, *args, **kwargs):
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, msg, args, **kwargs)


logging.setLoggerClass(SuccessLogger)


class ColoredFormatter(logging.Formatter):
    """控制台带颜色的日志格式"""

    COLORS = {
        "DEBUG": "\033[90m",      # 灰色
        "INFO": "\033[97m",       # 白色
        "SUCCESS": "\033[92m",    # 绿色
        "WARNING": "\033[93m",    # 黄色
        "ERROR": "\033[91m",      # 红色
        "CRITICAL": "\033[91;1m", # 红加粗
    }
    RESET = "\033[0m"

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.RESET)
        record.levelname = f"{color}{levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = "processing.log",
    verbose: bool = False,
) -> None:
    """
    配置全局日志

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径，None 或空字符串则不输出文件
        verbose: 是否启用 DEBUG 级别
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── 控制台 Handler ──
    console = logging.StreamHandler(sys.stdout)
    effective_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO)
    console.setLevel(effective_level)
    console.setFormatter(ColoredFormatter("[%(levelname)s] %(message)s"))
    root.addHandler(console)

    # ── 文件 Handler ──
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        root.addHandler(file_handler)

    # 抑制第三方库的嘈杂日志
    logging.getLogger("paddleocr").setLevel(logging.WARNING)
    logging.getLogger("ppocr").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> SuccessLogger:
    """获取命名的 SuccessLogger 实例"""
    return logging.getLogger(name)
