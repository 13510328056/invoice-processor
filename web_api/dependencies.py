"""
FastAPI 依赖注入

提供应用级依赖项：配置、临时目录等。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import Depends, Request

from src.config.loader import AppConfig

from web_api.config import WebConfig

logger = logging.getLogger(__name__)


def get_app_config(request: Request) -> AppConfig:
    """获取应用配置（注入到路由处理器）"""
    config: Optional[AppConfig] = getattr(request.app.state, "app_config", None)
    if config is None:
        from src.config.loader import load_config
        config = load_config()
        request.app.state.app_config = config
    return config


def get_web_config(request: Request) -> WebConfig:
    """获取 Web 配置"""
    config: Optional[WebConfig] = getattr(request.app.state, "web_config", None)
    if config is None:
        from web_api.config import load_web_config
        config = load_web_config()
        request.app.state.web_config = config
    return config


def get_temp_dir(
    web_config: WebConfig = Depends(get_web_config),
) -> Path:
    """获取临时文件目录"""
    import tempfile

    if web_config and web_config.temp_dir:
        temp_dir = Path(web_config.temp_dir)
    else:
        temp_dir = Path(tempfile.gettempdir()) / "invoice_processor_web"

    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
