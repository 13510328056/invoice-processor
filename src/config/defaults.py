"""
发票批处理工具 — 配置模块默认值
"""

# 默认配置文件路径（相对于运行目录）
DEFAULT_CONFIG_PATH = "config.yaml"

# 默认 Sheet 名称
DEFAULT_SHEET_NAMES = {
    "success": "成功处理",
    "failed": "失败处理",
    "skipped": "非电子发票",
    "statistics": "处理统计",
}

# 默认 output 配置
DEFAULT_OUTPUT_CONFIG = {
    "filename": "发票信息统计.xlsx",
    "sheet_success": "成功处理",
    "sheet_failed": "失败处理",
    "sheet_skipped": "非电子发票",
    "sheet_statistics": "处理统计",
}

# 默认 OCR 配置
DEFAULT_OCR_CONFIG = {
    "engine": "paddleocr",
    "lang": "ch",
    "use_gpu": False,
    "timeout": 30,
    "enable_vilayout": True,
}

# 默认 OFD 配置
DEFAULT_OFD_CONFIG = {
    "enabled": True,
    "mapping_path": "",
    "extract_preview": False,
    "fallback_to_ocr": True,
}

# 默认 processing 配置
DEFAULT_PROCESSING_CONFIG = {
    "max_workers": 4,
    "retry_count": 3,
    "enable_dedup": True,
    "skip_directories": ["__pycache__", "node_modules", ".git"],
    "pdf_passwords": ["", "123456", "password"],
}

# 默认 extraction 配置
DEFAULT_EXTRACTION_CONFIG = {
    "strategy": "ofd+xml+ocr",
    "llm_fallback": True,
    "llm_provider": "qwen",
    "normalize_date": True,
    "normalize_amount": True,
    "confidence_threshold": 0.85,
}

# 默认 logging 配置
DEFAULT_LOGGING_CONFIG = {
    "level": "INFO",
    "file": "processing.log",
}
