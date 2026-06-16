"""
测试：配置加载模块
"""

from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from src.config.loader import (
    AppConfig,
    load_config,
    OCRConfig,
    OFDConfig,
    ProcessingConfig,
    ExtractionConfig,
    LoggingConfig,
)


class TestAppConfigDefaults:
    """默认值测试"""

    def test_default_config(self):
        config = AppConfig()
        assert config.ocr.engine == "paddleocr"
        assert config.ofd.enabled is True
        assert config.processing.max_workers == 4
        assert config.processing.enable_dedup is True
        assert config.extraction.strategy == "ofd+xml+ocr"
        assert config.extraction.llm_provider == "qwen"
        assert config.extraction.confidence_threshold == 0.85
        assert config.logging.level == "INFO"
        assert config.logging.file == "processing.log"

    def test_ocr_engine_validation(self):
        with pytest.raises(ValueError):
            OCRConfig(engine="invalid_engine")

    def test_llm_provider_validation(self):
        with pytest.raises(ValueError):
            ExtractionConfig(llm_provider="unsupported")

    def test_confidence_threshold_range(self):
        with pytest.raises(ValueError):
            ExtractionConfig(confidence_threshold=1.5)

    def test_max_workers_positive(self):
        with pytest.raises(ValueError):
            ProcessingConfig(max_workers=-1)

    def test_logging_level_validation(self):
        with pytest.raises(ValueError):
            LoggingConfig(level="TRACE")


class TestLoadConfig:
    """配置文件加载测试"""

    def test_load_nonexistent_config(self):
        """配置文件不存在时返回默认值"""
        config = load_config("/nonexistent/config.yaml")
        assert isinstance(config, AppConfig)
        assert config.ocr.engine == "paddleocr"

    def test_load_yaml_override(self):
        """YAML 覆盖默认值"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump({
                "ocr": {"engine": "tesseract"},
                "processing": {"max_workers": 2},
            }, f)
            config_path = f.name

        try:
            config = load_config(config_path)
            assert config.ocr.engine == "tesseract"
            assert config.processing.max_workers == 2
            # 未覆盖的字段保留默认值
            assert config.ofd.enabled is True
            assert config.extraction.llm_provider == "qwen"
        finally:
            os.unlink(config_path)

    def test_load_partial_override(self):
        """部分覆盖不影响其他字段"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump({
                "ocr": {"timeout": 60},
            }, f)
            config_path = f.name

        try:
            config = load_config(config_path)
            assert config.ocr.timeout == 60
            assert config.ocr.engine == "paddleocr"  # 默认值
        finally:
            os.unlink(config_path)
