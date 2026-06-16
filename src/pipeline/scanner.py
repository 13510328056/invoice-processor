"""
发票批处理工具 — 文件扫描模块

递归扫描目录、格式分类、Magic Number 校验（可选）
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

from src.models.enums import FileType, EXTENSION_MAP
from src.models.result import ScannedFile
from src.utils.file_utils import classify_file, check_magic_number, get_relative_path

logger = logging.getLogger(__name__)


def scan_directory(
    root_dir: str,
    skip_directories: Optional[list[str]] = None,
    enable_magic_check: bool = False,
) -> list[ScannedFile]:
    """
    递归扫描目录，收集所有文件并进行格式分类

    Args:
        root_dir: 根目录路径
        skip_directories: 要跳过的目录名称列表
        enable_magic_check: 是否启用 Magic Number 校验

    Returns:
        扫描结果列表，按文件路径排序

    Raises:
        FileNotFoundError: 根目录不存在
        NotADirectoryError: 根路径不是目录
    """
    root = Path(root_dir)
    if not root.exists():
        raise FileNotFoundError(f"目录不存在: {root_dir}")
    if not root.is_dir():
        raise NotADirectoryError(f"路径不是目录: {root_dir}")

    skip_set = set(skip_directories or [])

    scanned: list[ScannedFile] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过忽略目录
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            parts = rel_dir.replace("\\", "/").split("/")
            if any(part in skip_set for part in parts):
                dirnames.clear()  # 不进入子目录
                continue

        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = get_relative_path(abs_path, root_dir)

            # 获取后缀名并分类
            _, ext = os.path.splitext(filename)
            file_type = classify_file(ext)

            # 获取文件元信息
            try:
                stat = os.stat(abs_path)
                file_size = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                file_size = 0
                mtime = 0.0

            # 可选 Magic Number 校验
            magic_valid = None
            if enable_magic_check and file_type != FileType.UNSUPPORTED.value:
                try:
                    magic_valid = check_magic_number(abs_path, file_type)
                except Exception:
                    magic_valid = False

            scanned.append(ScannedFile(
                abs_path=abs_path,
                rel_path=rel_path,
                file_type=file_type,
                magic_valid=magic_valid,
                file_size_bytes=file_size,
                modification_time=mtime,
            ))

    # 按路径排序，保证确定性顺序
    scanned.sort(key=lambda f: f.rel_path)

    logger.info(f"扫描完成: 共发现 {len(scanned)} 个文件")
    invoice_count = sum(1 for f in scanned if f.file_type != FileType.UNSUPPORTED.value)
    logger.info(f"  ├─ 电子发票文件: {invoice_count}")
    logger.info(f"  └─ 非电子发票文件: {len(scanned) - invoice_count}")

    return scanned


def classify_files(
    scanned_files: list[ScannedFile],
) -> tuple[list[ScannedFile], list[ScannedFile], list[ScannedFile]]:
    """
    将扫描结果分为三类

    Returns:
        (ofd_files, ocr_files, unsupported_files)
    """
    ofd_files: list[ScannedFile] = []
    ocr_files: list[ScannedFile] = []
    unsupported_files: list[ScannedFile] = []

    for f in scanned_files:
        if f.file_type == FileType.OFD.value:
            ofd_files.append(f)
        elif f.file_type == FileType.UNSUPPORTED.value:
            unsupported_files.append(f)
        else:
            ocr_files.append(f)

    return ofd_files, ocr_files, unsupported_files
