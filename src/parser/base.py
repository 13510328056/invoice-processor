"""
发票批处理工具 — 解析器基类
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.result import ScannedFile, RawParseResult
from src.config.loader import AppConfig


class InvoiceParser(ABC):
    """发票解析器抽象基类"""

    @abstractmethod
    def parse(self, scanned_file: ScannedFile, config: AppConfig) -> RawParseResult:
        """
        解析单个发票文件

        Args:
            scanned_file: 扫描结果
            config: 应用配置

        Returns:
            解析结果（包含结构化数据或原始文本块）
        """
        ...
