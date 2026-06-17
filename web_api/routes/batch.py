"""
批量处理端点

POST   /api/v1/batch              — 创建批量任务
GET    /api/v1/batch/{job_id}     — 查询任务状态
GET    /api/v1/batch/{job_id}/results  — 获取 JSON 结果
GET    /api/v1/batch/{job_id}/download — 下载 Excel 结果
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, Request
from fastapi.responses import FileResponse

from src.config.loader import AppConfig

from web_api.config import WebConfig
from web_api.dependencies import get_app_config, get_temp_dir, get_web_config
from web_api.exceptions import FileTooLargeError
from web_api.models.responses import (
    BatchCreateResponse,
    BatchStatusResponse,
    BatchResultsResponse,
)
from web_api.service import batch_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Batch"])


@router.post(
    "/api/v1/batch",
    summary="批量识别发票",
    description="上传多张发票文件，返回任务 ID，通过 GET 接口查询进度和结果",
    response_model=BatchCreateResponse,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary",
                                    "title": "发票文件",
                                    "description": "发票文件（OFD/PDF/JPG/PNG）",
                                },
                                "description": "发票文件列表（每个文件支持 OFD/PDF/JPG/PNG）",
                            },
                            "enable_dedup": {
                                "type": "boolean",
                                "default": True,
                                "description": "是否启用业务去重（默认 true）",
                            },
                        },
                        "required": ["files"],
                    }
                }
            }
        }
    },
)
async def create_batch(
    request: Request,
    app_config: AppConfig = Depends(get_app_config),
    web_config: WebConfig = Depends(get_web_config),
    temp_dir: Path = Depends(get_temp_dir),
):
    """
    创建批量处理任务

    - **files**: 发票文件列表（每个文件支持 OFD/PDF/JPG/PNG）
    - **enable_dedup**: 是否启用业务去重（默认 true）
    """
    # 从原始请求中获取上传文件列表和参数
    form = await request.form()
    files: list[UploadFile] = form.getlist("files")
    enable_dedup = form.get("enable_dedup", "true")
    enable_dedup = enable_dedup.lower() in ("true", "1", "yes")

    if not files:
        from web_api.exceptions import WebAPIError
        raise WebAPIError(
            status_code=422,
            code="NO_FILES",
            message="At least one file is required",
        )

    # 文件大小校验（逐个）
    max_bytes = web_config.max_upload_size_mb * 1024 * 1024
    for f in files:
        content = await f.read()
        if len(content) > max_bytes:
            raise FileTooLargeError(web_config.max_upload_size_mb)
        await f.seek(0)

    job_id = await batch_manager.create_job(
        files=files,
        config=app_config,
        web_temp_dir=temp_dir,
        enable_dedup=enable_dedup,
    )

    return BatchCreateResponse(
        job_id=job_id,
        status="pending",
        file_count=len(files),
        message=f"Batch job created with {len(files)} file(s)",
    )


@router.get(
    "/api/v1/batch/{job_id}",
    summary="查询任务状态",
    response_model=BatchStatusResponse,
)
async def get_batch_status(job_id: str):
    """查询批量处理任务的当前状态"""
    job = await batch_manager.get_job(job_id)
    return BatchStatusResponse(
        job_id=job.job_id,
        status=job.status,
        file_count=job.file_count,
        created_at=job.created_at,
        completed_at=job.completed_at,
        progress={
            "total": job.file_count,
        } if job.status == "running" else None,
    )


@router.get(
    "/api/v1/batch/{job_id}/results",
    summary="获取 JSON 结果",
    response_model=BatchResultsResponse,
)
async def get_batch_results(job_id: str):
    """获取批量处理的详细结果（JSON 格式）"""
    results = await batch_manager.get_job_results(job_id)
    return BatchResultsResponse(**results)


@router.get(
    "/api/v1/batch/{job_id}/download",
    summary="下载 Excel 结果",
    description="下载批处理生成的 Excel 文件",
)
async def download_batch_results(job_id: str):
    """下载批处理生成的 Excel 文件"""
    excel_path = await batch_manager.get_job_download_path(job_id)
    return FileResponse(
        path=excel_path,
        filename="发票信息统计.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
