"""
发票批处理工具 — 文件工具函数

Magic Number 校验、路径统一处理
"""

from __future__ import annotations

import os
from pathlib import Path

from src.models.enums import FileType, MagicNumber, EXTENSION_MAP


def classify_file(ext: str) -> str:
    """
    根据文件后缀名分类

    Args:
        ext: 文件后缀（含点，如 ".pdf"）

    Returns:
        FileType 值字符串
    """
    return EXTENSION_MAP.get(ext.lower(), FileType.UNSUPPORTED).value


def check_magic_number(file_path: str, file_type: str) -> bool:
    """
    校验文件 Magic Number 是否匹配声称的类型

    Args:
        file_path: 文件绝对路径
        file_type: FileType 值

    Returns:
        校验是否通过
    """
    magic_map = {
        FileType.OFD.value: MagicNumber.ZIP,
        FileType.PDF.value: MagicNumber.PDF,
        FileType.JPG.value: MagicNumber.JPEG,
        FileType.JPEG.value: MagicNumber.JPEG,
        FileType.PNG.value: MagicNumber.PNG,
    }
    expected = magic_map.get(file_type)
    if expected is None:
        return True  # 不支持校验的类型直接通过

    try:
        return MagicNumber.check(file_path, expected)
    except (OSError, IOError):
        return False


def get_relative_path(abs_path: str, root_dir: str) -> str:
    """
    计算文件相对于根目录的路径，统一使用正斜杠

    Args:
        abs_path: 文件绝对路径
        root_dir: 根目录路径

    Returns:
        相对路径（正斜杠分隔）
    """
    try:
        rel = os.path.relpath(abs_path, root_dir)
    except ValueError:
        # 跨驱动器时 fallback 到 basename
        rel = os.path.basename(abs_path)
    return rel.replace("\\", "/")


def ensure_directory(path: str) -> None:
    """确保目录存在，不存在则创建"""
    Path(path).mkdir(parents=True, exist_ok=True)
