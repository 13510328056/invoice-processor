"""
发票批处理工具 — 测试共享配置与夹具
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from src.config.loader import AppConfig
from src.models.enums import FileType
from src.models.result import ScannedFile


@pytest.fixture
def sample_config() -> AppConfig:
    """返回默认应用配置"""
    return AppConfig()


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """创建临时目录"""
    tmp = tempfile.mkdtemp(prefix="invoice_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def _create_file(dir_path: str, rel_path: str, content: bytes = b"") -> str:
    """在临时目录中创建文件"""
    full_path = os.path.join(dir_path, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)
    return full_path


@pytest.fixture
def temp_with_files(temp_dir: str) -> str:
    """创建包含测试文件的目录结构"""
    # 有效文件（模拟各种格式）
    _create_file(temp_dir, "发票001.pdf", b"%PDF-1.4 mock content")
    _create_file(temp_dir, "发票002.jpg", b"\xff\xd8\xff mock jpeg")
    _create_file(temp_dir, "发票003.png", b"\x89PNG mock png")
    # OFD 文件（需要先模拟 ZIP 结构）
    _create_file(temp_dir, "发票004.ofd", b"PK\x03\x04 mock ofd")
    # 非发票文件
    _create_file(temp_dir, "readme.txt", b"just a text file")
    _create_file(temp_dir, "photo.bmp", b"bitmap data")
    # 嵌套子目录
    _create_file(temp_dir, "sub/发票005.pdf", b"%PDF-1.4 nested")
    # 忽略目录
    _create_file(temp_dir, "__pycache__/ignored.pyc", b"should skip")
    _create_file(temp_dir, "node_modules/lib/index.js", b"should skip")
    return temp_dir


@pytest.fixture
def scanned_pdf(temp_with_files: str) -> ScannedFile:
    """返回 PDF 扫描文件示例"""
    return ScannedFile(
        abs_path=os.path.join(temp_with_files, "发票001.pdf"),
        rel_path="发票001.pdf",
        file_type=FileType.PDF.value,
    )


@pytest.fixture
def scanned_ofd(temp_with_files: str) -> ScannedFile:
    """返回 OFD 扫描文件示例"""
    return ScannedFile(
        abs_path=os.path.join(temp_with_files, "发票004.ofd"),
        rel_path="发票004.ofd",
        file_type=FileType.OFD.value,
    )
