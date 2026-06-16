"""
测试：文件扫描模块
"""

from __future__ import annotations

import os

import pytest

from src.models.enums import FileType
from src.models.result import ScannedFile
from src.pipeline.scanner import scan_directory, classify_files


class TestScanDirectory:
    """测试目录扫描"""

    def test_scan_valid_directory(self, temp_with_files: str):
        """正常目录扫描"""
        files = scan_directory(
            temp_with_files,
            skip_directories=["__pycache__", "node_modules"],
        )
        assert len(files) > 0
        # 检查发现的文件数（应该跳过 __pycache__ 和 node_modules）
        rel_paths = {f.rel_path for f in files}
        assert "发票001.pdf" in rel_paths
        assert "发票002.jpg" in rel_paths
        assert "发票003.png" in rel_paths
        assert "发票004.ofd" in rel_paths
        assert "readme.txt" in rel_paths
        assert "sub/发票005.pdf" in rel_paths
        # 忽略目录中的文件不应出现
        assert "__pycache__/ignored.pyc" not in rel_paths
        assert "node_modules/lib/index.js" not in rel_paths

    def test_scan_nonexistent_directory(self):
        """不存在的目录应抛出异常"""
        with pytest.raises(FileNotFoundError):
            scan_directory("/nonexistent/path")

    def test_scan_empty_directory(self, temp_dir: str):
        """空目录"""
        files = scan_directory(temp_dir)
        assert len(files) == 0

    def test_scan_with_magic_check(self, temp_dir: str):
        """Magic Number 校验"""
        # 创建文件类型不匹配的文件
        file_path = os.path.join(temp_dir, "fake.pdf")
        with open(file_path, "wb") as f:
            f.write(b"this is not a PDF")

        files = scan_directory(temp_dir, enable_magic_check=True)
        assert len(files) == 1
        # Magic Number 应该不匹配（内容不是 %PDF）
        assert files[0].magic_valid is False


class TestClassifyFiles:
    """测试文件分类"""

    def test_all_types(self, temp_with_files: str):
        files = scan_directory(
            temp_with_files,
            skip_directories=["__pycache__", "node_modules"],
        )
        ofd, ocr, unsupported = classify_files(files)

        assert all(f.file_type == FileType.OFD.value for f in ofd)
        assert all(f.file_type in (FileType.PDF.value, FileType.JPG.value, FileType.PNG.value) for f in ocr)
        assert all(f.file_type == FileType.UNSUPPORTED.value for f in unsupported)

        assert len(ofd) == 1  # 1 个 OFD
        assert len(ocr) == 4  # 3 个根目录 + 1 个子目录
        assert len(unsupported) == 2  # readme.txt + photo.bmp
