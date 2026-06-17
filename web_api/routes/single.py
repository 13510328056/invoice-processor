"""
单文件提取端点

POST /api/v1/extract
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.config.loader import AppConfig
from src.models.enums import ProcessingStatus

from web_api.config import WebConfig
from web_api.dependencies import get_app_config, get_temp_dir, get_web_config
from web_api.exceptions import ProcessingFailedError, FileTooLargeError
from web_api.models.responses import SingleExtractSuccess, SingleExtractFailed, ErrorDetail
from web_api.service.extractor import process_uploaded_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Extract"])


@router.post(
    "/api/v1/extract",
    summary="识别单张发票",
    description="上传单张发票文件（OFD/PDF/JPG/PNG），返回结构化提取结果",
    responses={
        200: {"model": SingleExtractSuccess},
        422: {"model": SingleExtractFailed},
        413: {"description": "File too large"},
    },
)
async def extract_single(
    file: UploadFile = File(
        ...,
        description="发票文件（OFD/PDF/JPG/PNG）",
    ),
    enable_dedup: bool = Form(
        True,
        description="是否启用业务去重（默认 true）",
    ),
    app_config: AppConfig = Depends(get_app_config),
    web_config: WebConfig = Depends(get_web_config),
    temp_dir: Path = Depends(get_temp_dir),
):
    """
    单张发票提取

    - **file**: 发票文件（OFD/PDF/JPG/PNG）
    - **enable_dedup**: 是否启用业务去重（默认 true）
    """
    # 文件大小校验
    max_bytes = web_config.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise FileTooLargeError(web_config.max_upload_size_mb)

    # 重新设置文件位置指针
    await file.seek(0)

    # 处理
    result = await process_uploaded_file(
        file=file,
        config=app_config,
        temp_dir=temp_dir,
        allowed_extensions=web_config.allowed_extensions,
    )

    elapsed = round(result.elapsed_seconds, 2)

    if result.status == ProcessingStatus.SUCCESS and result.invoice:
        return SingleExtractSuccess(
            data=result.invoice.to_dict(),
            elapsed_seconds=elapsed,
            source=result.invoice.extraction_source,
        )
    else:
        error_msg = result.error_message or "无法识别发票号码或价税合计"
        return JSONResponse(
            status_code=422,
            headers={"Content-Type": "application/json; charset=utf-8"},
            content=SingleExtractFailed(
                error=ErrorDetail(
                    code="EXTRACTION_FAILED",
                    message="发票字段提取失败",
                    details=error_msg,
                ),
                elapsed_seconds=elapsed,
            ).model_dump(),
        )
