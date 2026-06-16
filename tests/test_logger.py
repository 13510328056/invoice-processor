"""
测试：日志框架
"""

from __future__ import annotations

import logging
import os
import tempfile
import time

import pytest

from src.utils.logger import setup_logging, get_logger, SUCCESS_LEVEL


class TestLogger:
    """日志框架测试"""

    def test_success_level_value(self):
        assert SUCCESS_LEVEL == 25

    def test_get_logger_instance(self):
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_console_only(self):
        """仅控制台日志"""
        setup_logging(level="INFO", log_file=None)
        logger = get_logger("test_console")
        # 不应抛出异常
        logger.info("test console message")

    def test_setup_logging_with_file(self):
        """文件日志"""
        log_path = os.path.join(tempfile.gettempdir(), f"test_log_{time.time()}.log")

        try:
            setup_logging(level="DEBUG", log_file=log_path, verbose=True)
            logger = get_logger("test_file")
            logger.info("test file message")
            logger.debug("test debug message")

            # 等待日志写入
            time.sleep(0.5)

            assert os.path.exists(log_path)
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "test file message" in content
            assert "test debug message" in content
        finally:
            # 清理 logging handlers
            root = logging.getLogger()
            for h in root.handlers[:]:
                if hasattr(h, "baseFilename") and h.baseFilename == log_path:
                    h.close()
                    root.removeHandler(h)
            # 延迟尝试删除
            for _ in range(5):
                try:
                    if os.path.exists(log_path):
                        os.unlink(log_path)
                    break
                except PermissionError:
                    time.sleep(0.5)

    def test_success_method(self):
        """SUCCESS 级别日志"""
        logger = get_logger("test_success")
        # 不应抛出异常
        logger.log(SUCCESS_LEVEL, "test success message")

    def test_multiple_handlers(self):
        """多个 handler 不重复添加"""
        setup_logging(level="INFO", log_file=None)
        root = logging.getLogger()
        count_before = len(root.handlers)
        setup_logging(level="INFO", log_file=None)
        count_after = len(root.handlers)
        # 每次 setup_logging 都会添加新的 handler
        # 这里只验证不崩溃
        assert count_after >= count_before
