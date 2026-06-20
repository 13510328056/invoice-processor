"""
健康检查端点

GET /api/v1/health
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from typing import Optional

from src.config.loader import AppConfig
from src.parser.ocr_parser import OCRParser

from web_api.config import WebConfig
from web_api.dependencies import get_app_config, get_web_config
from web_api.models.responses import HealthResponse

router = APIRouter(tags=["Health"])

# 服务启动时间（在 main.py 中设置）
_start_time: float = time.monotonic()


def set_start_time() -> None:
    """在 app 启动时调用"""
    global _start_time
    _start_time = time.monotonic()


@router.get("/api/v1/health", response_model=HealthResponse)
async def health_check(
    app_config: AppConfig = Depends(get_app_config),
    web_config: WebConfig = Depends(get_web_config),
):
    """健康检查 — 返回服务状态"""
    uptime = time.monotonic() - _start_time

    # 检查 OCR 是否已预热（检查类级共享实例，兼容预热开启/关闭两种场景）
    ocr_loaded = False
    try:
        ocr_loaded = OCRParser._shared_instance is not None
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        version="1.0.0",
        uptime_seconds=round(uptime, 2),
        ocr_loaded=ocr_loaded,
    )
