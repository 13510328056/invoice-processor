"""
发票批处理工具 — 处理结果与统计数据模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import ProcessingStatus
from .invoice import InvoiceData


@dataclass
class ScannedFile:
    """扫描阶段发现的文件"""
    abs_path: str                         # 绝对路径
    rel_path: str                         # 相对路径（相对于用户指定根目录）
    file_type: str                        # 文件类型标识 (ofd/pdf/jpg/png/unsupported)
    magic_valid: Optional[bool] = None    # Magic Number 校验结果
    file_size_bytes: int = 0              # 文件大小
    modification_time: float = 0.0        # 文件修改时间戳

    @property
    def ext(self) -> str:
        """文件后缀（小写，含点）"""
        import os
        _, ext = os.path.splitext(self.rel_path)
        return ext.lower()


@dataclass
class RawParseResult:
    """解析阶段原始输出 — 供字段提取器使用"""
    scanned_file: ScannedFile
    source: str = ""                      # "ofd_xml" | "ocr" | "ofd_fallback_ocr"

    # OCR 路径
    ocr_text_blocks: list[dict] = field(default_factory=list)
    ocr_full_text: str = ""
    ocr_confidence: float = 0.0

    # OFD 路径
    ofd_xml_tree: Optional[object] = None  # lxml ElementTree 或 dict
    ofd_line_items: list[dict] = field(default_factory=list)  # 从 CustomTag 提取的商品明细

    # 错误记录
    parse_errors: list[str] = field(default_factory=list)
    parser_elapsed: float = 0.0


@dataclass
class ProcessingResult:
    """单个文件的最终处理结果"""
    scanned_file: ScannedFile
    status: ProcessingStatus = ProcessingStatus.FAILED
    invoice: Optional[InvoiceData] = None
    error_message: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class ProcessingStatistics:
    """整体处理统计"""
    total_scanned: int = 0
    total_invoice_files: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    total_wall_time: float = 0.0          # 总耗时
    total_parse_time: float = 0.0         # 解析总时间

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_invoice_files == 0:
            return 100.0
        return round(self.total_success / self.total_invoice_files * 100, 2)

    @property
    def validation_ok(self) -> bool:
        """校验关系：扫描总数 = 发票 + 非发票；发票 = 成功 + 失败"""
        return (
            self.total_scanned == self.total_invoice_files + self.total_skipped
            and self.total_invoice_files == self.total_success + self.total_failed
        )
