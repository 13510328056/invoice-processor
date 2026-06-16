"""
发票批处理工具 — 枚举类型定义
"""

from enum import Enum, auto


class FileType(str, Enum):
    """文件类型枚举"""
    OFD = "ofd"
    PDF = "pdf"
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    UNSUPPORTED = "unsupported"


EXTENSION_MAP: dict[str, FileType] = {
    ".ofd": FileType.OFD,
    ".pdf": FileType.PDF,
    ".jpg": FileType.JPG,
    ".jpeg": FileType.JPEG,
    ".png": FileType.PNG,
}


class ProcessingStatus(str, Enum):
    """处理状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvoiceType(str, Enum):
    """发票类型枚举"""
    VAT_SPECIAL = "增值税专用发票"
    VAT_NORMAL = "增值税电子普通发票"
    VAT_ROLL = "卷式发票"
    TOLL_ROAD = "通行费发票"
    OTHER = "其他"


class ExtractionSource(str, Enum):
    """提取来源枚举"""
    OFD_XML = "ofd_xml"               # OFD XML 直接解析
    OCR = "ocr"                        # OCR 识别
    OFD_FALLBACK_OCR = "ofd_fallback_ocr"  # OFD 降级 OCR
    PDF_METADATA = "pdf_metadata"      # PDF 元数据（预留）


class MagicNumber(bytes, Enum):
    """Magic Number 文件头标识"""
    ZIP = b"PK\x03\x04"       # 504B0304 — ZIP / OFD
    PDF = b"%PDF"              # 25504446
    JPEG = b"\xff\xd8\xff"    # FFD8FF
    PNG = b"\x89PNG"           # 89504E47

    @classmethod
    def check(cls, path: str, expected: "MagicNumber") -> bool:
        """检查文件前 N 字节是否匹配 Magic Number"""
        n = len(expected.value)
        with open(path, "rb") as f:
            header = f.read(n)
        return header == expected.value
