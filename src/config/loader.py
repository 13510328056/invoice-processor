"""
发票批处理工具 — 配置加载器

Pydantic 模型定义 + YAML 文件覆盖
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from .defaults import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_EXTRACTION_CONFIG,
    DEFAULT_LOGGING_CONFIG,
    DEFAULT_OCR_CONFIG,
    DEFAULT_OFD_CONFIG,
    DEFAULT_OUTPUT_CONFIG,
    DEFAULT_PROCESSING_CONFIG,
)


class OutputConfig(BaseModel):
    filename: str = DEFAULT_OUTPUT_CONFIG["filename"]
    sheet_success: str = DEFAULT_OUTPUT_CONFIG["sheet_success"]
    sheet_failed: str = DEFAULT_OUTPUT_CONFIG["sheet_failed"]
    sheet_skipped: str = DEFAULT_OUTPUT_CONFIG["sheet_skipped"]
    sheet_statistics: str = DEFAULT_OUTPUT_CONFIG["sheet_statistics"]


class OCRConfig(BaseModel):
    engine: str = DEFAULT_OCR_CONFIG["engine"]
    lang: str = DEFAULT_OCR_CONFIG["lang"]
    use_gpu: bool = DEFAULT_OCR_CONFIG["use_gpu"]
    timeout: int = Field(default=DEFAULT_OCR_CONFIG["timeout"], ge=5, le=120)
    enable_vilayout: bool = DEFAULT_OCR_CONFIG["enable_vilayout"]

    @model_validator(mode="after")
    def validate_engine(self):
        allowed = {"paddleocr", "tesseract", "windows_ocr"}
        if self.engine not in allowed:
            raise ValueError(f"ocr.engine 必须是 {allowed} 之一，收到: {self.engine}")
        return self


class OFDConfig(BaseModel):
    enabled: bool = DEFAULT_OFD_CONFIG["enabled"]
    mapping_path: str = DEFAULT_OFD_CONFIG["mapping_path"]
    extract_preview: bool = DEFAULT_OFD_CONFIG["extract_preview"]
    fallback_to_ocr: bool = DEFAULT_OFD_CONFIG["fallback_to_ocr"]


class ProcessingConfig(BaseModel):
    max_workers: int = Field(default=DEFAULT_PROCESSING_CONFIG["max_workers"], ge=0)
    retry_count: int = Field(default=DEFAULT_PROCESSING_CONFIG["retry_count"], ge=0)
    enable_dedup: bool = DEFAULT_PROCESSING_CONFIG["enable_dedup"]
    skip_directories: list[str] = Field(default_factory=lambda: DEFAULT_PROCESSING_CONFIG["skip_directories"])
    pdf_passwords: list[str] = Field(default_factory=lambda: DEFAULT_PROCESSING_CONFIG["pdf_passwords"])


class ExtractionConfig(BaseModel):
    strategy: str = DEFAULT_EXTRACTION_CONFIG["strategy"]
    llm_fallback: bool = DEFAULT_EXTRACTION_CONFIG["llm_fallback"]
    llm_provider: str = DEFAULT_EXTRACTION_CONFIG["llm_provider"]
    normalize_date: bool = DEFAULT_EXTRACTION_CONFIG["normalize_date"]
    normalize_amount: bool = DEFAULT_EXTRACTION_CONFIG["normalize_amount"]
    confidence_threshold: float = Field(
        default=DEFAULT_EXTRACTION_CONFIG["confidence_threshold"],
        ge=0.0, le=1.0,
    )

    @model_validator(mode="after")
    def validate_provider(self):
        allowed = {"qwen", "claude", "gemini"}
        if self.llm_provider not in allowed:
            raise ValueError(f"extraction.llm_provider 必须是 {allowed} 之一，收到: {self.llm_provider}")
        return self


class LoggingConfig(BaseModel):
    level: str = DEFAULT_LOGGING_CONFIG["level"]
    file: str = DEFAULT_LOGGING_CONFIG["file"]

    @model_validator(mode="after")
    def validate_level(self):
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if self.level.upper() not in allowed:
            raise ValueError(f"logging.level 必须是 {allowed} 之一，收到: {self.level}")
        return self


class AppConfig(BaseModel):
    """应用级完整配置"""
    output: OutputConfig = OutputConfig()
    ocr: OCRConfig = OCRConfig()
    ofd: OFDConfig = OFDConfig()
    processing: ProcessingConfig = ProcessingConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    logging: LoggingConfig = LoggingConfig()


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    加载配置：从默认值开始，叠加 YAML 文件覆盖

    Args:
        config_path: 配置文件路径，None 则使用默认路径

    Returns:
        校验后的 AppConfig 实例
    """
    config = AppConfig()

    path = Path(config_path) if config_path else Path(DEFAULT_CONFIG_PATH)
    if not path.exists():
        return config

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        return config

    # 逐层覆盖
    if "output" in raw:
        config.output = OutputConfig(**{**config.output.model_dump(), **raw["output"]})
    if "ocr" in raw:
        config.ocr = OCRConfig(**{**config.ocr.model_dump(), **raw["ocr"]})
    if "ofd" in raw:
        config.ofd = OFDConfig(**{**config.ofd.model_dump(), **raw["ofd"]})
    if "processing" in raw:
        config.processing = ProcessingConfig(**{**config.processing.model_dump(), **raw["processing"]})
    if "extraction" in raw:
        config.extraction = ExtractionConfig(**{**config.extraction.model_dump(), **raw["extraction"]})
    if "logging" in raw:
        config.logging = LoggingConfig(**{**config.logging.model_dump(), **raw["logging"]})

    return config
