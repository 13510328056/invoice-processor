"""
响应 Pydantic 模型

定义所有 API 端点的标准化响应结构。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ── 错误响应 ──

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: str = ""


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


# ── 健康检查 ──

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    ocr_loaded: bool


# ── 单文件提取 ──

class SingleExtractSuccess(BaseModel):
    success: bool = True
    data: dict[str, Any]
    elapsed_seconds: float
    source: str


class SingleExtractFailed(BaseModel):
    success: bool = False
    error: ErrorDetail
    elapsed_seconds: float


# ── 批量处理 ──

class BatchCreateResponse(BaseModel):
    job_id: str
    status: str
    file_count: int
    message: str


class BatchStatusResponse(BaseModel):
    job_id: str
    status: str
    file_count: int
    created_at: float
    completed_at: Optional[float] = None
    progress: Optional[dict[str, int]] = None


class BatchResultsResponse(BaseModel):
    job_id: str
    status: str
    file_count: int
    file_names: list[str]
    results: list[dict[str, Any]]
    statistics: Optional[dict[str, Any]] = None
    created_at: float
    completed_at: Optional[float] = None
