"""
发票批处理工具 — 自定义异常层次
"""


class InvoiceProcessorError(Exception):
    """基类异常"""
    pass


class FileScanError(InvoiceProcessorError):
    """文件扫描错误"""
    pass


class ParseError(InvoiceProcessorError):
    """解析基类异常"""
    pass


class OFDParseError(ParseError):
    """OFD 解析失败"""
    pass


class OCRParseError(ParseError):
    """OCR 处理失败"""
    pass


class FieldExtractionError(InvoiceProcessorError):
    """字段提取失败"""
    pass


class LLMFallbackError(InvoiceProcessorError):
    """LLM API 调用失败"""
    pass


class ExcelWriteError(InvoiceProcessorError):
    """Excel 写入失败（重试后）"""
    pass


class ConfigValidationError(InvoiceProcessorError):
    """配置校验失败"""
    pass
