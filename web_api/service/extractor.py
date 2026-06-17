"""
单文件 Web 处理封装

负责：
- 保存上传文件到临时目录
- 构建 ScannedFile 对象
- 在线程池中调用 process_single_file() 避免阻塞事件循环
- 处理完成后清理临时文件
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from src.config.loader import AppConfig
from src.models.enums import EXTENSION_MAP
from src.models.result import ProcessingResult, ScannedFile
from src.pipeline.orchestrator import process_single_file

from web_api.exceptions import InvalidFileTypeError

logger = logging.getLogger(__name__)

# 支持的文件后缀（来自现有 EXTENSION_MAP）
SUPPORTED_EXTENSIONS: set[str] = set(EXTENSION_MAP.keys())


def _validate_extension(filename: str, allowed: Optional[list[str]] = None) -> str:
    """校验文件后缀，返回小写后缀（含点）"""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    allowed_set = set(allowed or SUPPORTED_EXTENSIONS)
    if ext not in allowed_set:
        raise InvalidFileTypeError(filename, list(allowed_set))
    return ext


def _build_scanned_file(temp_path: Path, original_filename: str, ext: str) -> ScannedFile:
    """从临时文件构建 ScannedFile 对象"""
    from src.utils.file_utils import classify_file

    # 确保文件存在且有大小
    stat_result = os.stat(str(temp_path))
    file_type = classify_file(ext)

    return ScannedFile(
        abs_path=str(temp_path.resolve()),
        rel_path=original_filename,  # 保留原始文件名
        file_type=file_type,
        file_size_bytes=stat_result.st_size,
        modification_time=stat_result.st_mtime,
    )


async def process_uploaded_file(
    file: UploadFile,
    config: AppConfig,
    temp_dir: Path,
    allowed_extensions: Optional[list[str]] = None,
) -> ProcessingResult:
    """
    处理单个上传的发票文件

    在 asyncio 线程池中运行同步的 process_single_file()，
    避免阻塞 FastAPI 事件循环。

    Args:
        file: 上传的文件
        config: 应用配置
        temp_dir: 临时文件目录
        allowed_extensions: 允许的文件后缀列表

    Returns:
        ProcessingResult 处理结果

    Raises:
        InvalidFileTypeError: 不支持的文件类型
    """
    # 1. 校验后缀
    ext = _validate_extension(file.filename or "unknown", allowed_extensions)

    # 2. 写入临时文件
    safe_name = f"{uuid.uuid4().hex}{ext}"
    temp_path = temp_dir / safe_name

    content = await file.read()
    temp_path.write_bytes(content)

    # 3. 处理
    try:
        scanned_file = _build_scanned_file(temp_path, file.filename or safe_name, ext)
        loop = asyncio.get_running_loop()

        result = await loop.run_in_executor(
            None,  # 默认线程池
            process_single_file,
            scanned_file,
            config,
        )

        # 保证 ProcessingResult 携带正确的原始文件名
        if result and result.scanned_file:
            result.scanned_file.rel_path = file.filename or safe_name

        return result  # type: ignore[return-value]

    finally:
        # 4. 清理临时文件
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            logger.warning(f"Failed to clean up temp file: {temp_path}")
